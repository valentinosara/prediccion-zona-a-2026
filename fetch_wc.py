"""
fetch_wc.py - Fetch + cache + fallback de TODO lo que el sistema necesita.

El sistema "baja todo solo" cada vez que corre. Con fetch automatico la resiliencia es
parte del pipeline: cada fuente se intenta EN VIVO y, si falla, cae al ultimo CACHE y,
en ultima instancia, al SEED versionado en el repo. Cada seccion deja constancia de su
PROCEDENCIA (live/cache/seed + timestamp) para mostrarla honestamente en el HTML.

Fuentes REALES (verificadas contra los esquemas en vivo del Mundial 2026):
  - Fixtures/resultados/estado : ESPN hidden API (sin key)
      scoreboard por dia : .../sports/soccer/fifa.world/scoreboard?dates=YYYYMMDD
      grupos A-L          : .../v2/sports/soccer/fifa.world/standings?season=2026
  - Cuotas 1X2/O-U/AH (sin key): ESPN core API por evento
      .../v2/.../events/{id}/competitions/{id}/odds  (moneyline -> decimal)
      Fallback opcional con key: The Odds API (ODDS_API_KEY).
  - Fuerza (Elo)              : eloratings.net  (World.tsv + en.teams.tsv)

El draw real (48 selecciones, 12 grupos A-L) esta anclado en TEAMS_TABLE: es un HECHO del
sorteo, no una opinion; se cruza-verifica contra ESPN standings al construir el seed. Los
horarios se guardan en hora de Argentina (ART, UTC-3) para que el HTML los muestre tal cual.

Si la red bloquea una fuente, esa seccion corre en MODO DEGRADADO con cache/seed y el HTML
lo avisa. No se inventan resultados ni cuotas: todo sale del fetch.
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data_mundial")
SEED = os.path.join(DATA, "seed")
CACHE = os.path.join(DATA, "cache")
os.makedirs(CACHE, exist_ok=True)

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
ESPN_STANDINGS = "https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings"
ESPN_CORE_ODDS = ("https://sports.core.api.espn.com/v2/sports/soccer/leagues/fifa.world/"
                  "events/{eid}/competitions/{eid}/odds")
ODDS_API = "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds"
ELO_WORLD = "https://www.eloratings.net/World.tsv"
ELO_NAMES = "https://www.eloratings.net/en.teams.tsv"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ProdeMundial2026/1.0)",
           "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}
TIMEOUT = 12

# Hora de Argentina (sin DST). Los horarios de ESPN vienen en UTC; los guardamos en ART.
ART = timezone(timedelta(hours=-3))

# --- Draw REAL del Mundial 2026 (verificado en vivo via ESPN standings) -------------
# (iso2 interno, nombre ES, codigo FIFA-3 de ESPN, grupo A-L)
TEAMS_TABLE = [
    ("MX", "Mexico",                 "MEX", "A"),
    ("CZ", "Chequia",                "CZE", "A"),
    ("KR", "Corea del Sur",          "KOR", "A"),
    ("ZA", "Sudafrica",              "RSA", "A"),
    ("CA", "Canada",                 "CAN", "B"),
    ("BA", "Bosnia y Herzegovina",   "BIH", "B"),
    ("CH", "Suiza",                  "SUI", "B"),
    ("QA", "Qatar",                  "QAT", "B"),
    ("BR", "Brasil",                 "BRA", "C"),
    ("GB-SCT", "Escocia",            "SCO", "C"),
    ("HT", "Haiti",                  "HAI", "C"),
    ("MA", "Marruecos",              "MAR", "C"),
    ("PY", "Paraguay",               "PAR", "D"),
    ("TR", "Turquia",                "TUR", "D"),
    ("AU", "Australia",              "AUS", "D"),
    ("US", "Estados Unidos",         "USA", "D"),
    ("EC", "Ecuador",                "ECU", "E"),
    ("DE", "Alemania",               "GER", "E"),
    ("CI", "Costa de Marfil",        "CIV", "E"),
    ("CW", "Curazao",                "CUW", "E"),
    ("NL", "Paises Bajos",           "NED", "F"),
    ("SE", "Suecia",                 "SWE", "F"),
    ("JP", "Japon",                  "JPN", "F"),
    ("TN", "Tunez",                  "TUN", "F"),
    ("BE", "Belgica",                "BEL", "G"),
    ("IR", "Iran",                   "IRN", "G"),
    ("EG", "Egipto",                 "EGY", "G"),
    ("NZ", "Nueva Zelanda",          "NZL", "G"),
    ("ES", "Espana",                 "ESP", "H"),
    ("UY", "Uruguay",                "URU", "H"),
    ("SA", "Arabia Saudita",         "KSA", "H"),
    ("CV", "Cabo Verde",             "CPV", "H"),
    ("NO", "Noruega",                "NOR", "I"),
    ("FR", "Francia",                "FRA", "I"),
    ("SN", "Senegal",                "SEN", "I"),
    ("IQ", "Irak",                   "IRQ", "I"),
    ("AR", "Argentina",              "ARG", "J"),
    ("AT", "Austria",                "AUT", "J"),
    ("DZ", "Argelia",                "ALG", "J"),
    ("JO", "Jordania",               "JOR", "J"),
    ("CO", "Colombia",               "COL", "K"),
    ("PT", "Portugal",               "POR", "K"),
    ("UZ", "Uzbekistan",             "UZB", "K"),
    ("CD", "RD del Congo",           "COD", "K"),
    ("GB-ENG", "Inglaterra",         "ENG", "L"),
    ("HR", "Croacia",                "CRO", "L"),
    ("PA", "Panama",                 "PAN", "L"),
    ("GH", "Ghana",                  "GHA", "L"),
]
HOST_CODES = {"MX", "CA", "US"}

FIFA3_TO_ISO = {abbr: iso for iso, _n, abbr, _g in TEAMS_TABLE}
ISO_NAME = {iso: name for iso, name, _a, _g in TEAMS_TABLE}
ISO_GROUP = {iso: g for iso, _n, _a, g in TEAMS_TABLE}

# Variantes en ingles (ESPN + eloratings) -> iso2 interno, para cruzar nombres entre fuentes.
_ALIAS_SRC = {
    "MX": ["Mexico"], "CZ": ["Czechia", "Czech Republic"],
    "KR": ["South Korea", "Korea Republic"], "ZA": ["South Africa"],
    "CA": ["Canada"], "BA": ["Bosnia and Herzegovina", "Bosnia-Herzegovina"],
    "CH": ["Switzerland"], "QA": ["Qatar"], "BR": ["Brazil"], "GB-SCT": ["Scotland"],
    "HT": ["Haiti"], "MA": ["Morocco"], "PY": ["Paraguay"],
    "TR": ["Turkey", "Turkiye", "Turkey (Turkiye)"], "AU": ["Australia"],
    "US": ["United States", "USA"], "EC": ["Ecuador"], "DE": ["Germany"],
    "CI": ["Ivory Coast", "Cote d'Ivoire"], "CW": ["Curacao"], "NL": ["Netherlands"],
    "SE": ["Sweden"], "JP": ["Japan"], "TN": ["Tunisia"], "BE": ["Belgium"],
    "IR": ["Iran"], "EG": ["Egypt"], "NZ": ["New Zealand"], "ES": ["Spain"],
    "UY": ["Uruguay"], "SA": ["Saudi Arabia"], "CV": ["Cape Verde", "Cabo Verde"],
    "NO": ["Norway"], "FR": ["France"], "SN": ["Senegal"], "IQ": ["Iraq"],
    "AR": ["Argentina"], "AT": ["Austria"], "DZ": ["Algeria"], "JO": ["Jordan"],
    "CO": ["Colombia"], "PT": ["Portugal"], "UZ": ["Uzbekistan"],
    "CD": ["DR Congo", "Congo DR", "Democratic Republic of the Congo"],
    "GB-ENG": ["England"], "HR": ["Croatia"], "PA": ["Panama"], "GH": ["Ghana"],
}


# ----------------------------------------------------------------------- helpers ----

def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _norm(s):
    """Normaliza un nombre para matchear entre fuentes (sin acentos, minusculas)."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


ALIASES = {_norm(v): iso for iso, vs in _ALIAS_SRC.items() for v in vs}
ALIASES.update({_norm(name): iso for iso, name, _a, _g in TEAMS_TABLE})


def _flag(iso2):
    """Bandera emoji desde el iso2 (regional indicators; subdivisiones para UK)."""
    if iso2 == "GB-ENG":
        return "\U0001F3F4" + "".join(chr(0xE0000 + ord(c)) for c in "gbeng") + "\U000E007F"
    if iso2 == "GB-SCT":
        return "\U0001F3F4" + "".join(chr(0xE0000 + ord(c)) for c in "gbsct") + "\U000E007F"
    cc = iso2.upper()[:2]
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in cc)


def _am2dec(american):
    """Moneyline americana -> cuota decimal. Acepta int/float/str ('+110','-135')."""
    if american is None:
        return None
    try:
        a = float(str(american).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    dec = 1.0 + (a / 100.0 if a > 0 else 100.0 / abs(a))
    return round(dec, 4)


def _seed(name):
    return json.load(open(os.path.join(SEED, name), encoding="utf-8"))


def _seed_safe(name):
    try:
        return _seed(name)
    except Exception:
        return None


def _cache_path(name):
    return os.path.join(CACHE, name)


def _cache_read(name):
    p = _cache_path(name)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return None
    return None


def _cache_write(name, payload):
    payload = dict(payload, _cached_at=_now())
    json.dump(payload, open(_cache_path(name), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def http_get_json(url, params=None, retries=3, backoff=2.0):
    """GET JSON resiliente. Reintenta SOLO ante errores transitorios (timeout/conexion/
    5xx) con backoff exponencial; 403/401/404 son terminales (no se reintenta)."""
    err = "sin intento"
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json(), None
            if r.status_code in (401, 403, 404):
                return None, f"HTTP {r.status_code} (terminal)"
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = type(e).__name__
        if attempt < retries - 1:
            time.sleep(backoff * (2 ** attempt))
    return None, err


def _http_get_text(url, retries=3, backoff=2.0, encoding=None):
    err = "sin intento"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200 and len(r.content) > 100:
                if encoding:
                    r.encoding = encoding  # eloratings sirve UTF-8 sin charset -> forzarlo
                return r.text, None
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = type(e).__name__
        if attempt < retries - 1:
            time.sleep(backoff * (2 ** attempt))
    return None, err


def _to_art(utc_iso):
    """'2026-06-14T17:00Z' (UTC) -> '2026-06-14T14:00:00' (ART naive, lo que muestra el HTML)."""
    s = (utc_iso or "").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return utc_iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ART).strftime("%Y-%m-%dT%H:%M:%S")


# ------------------------------------------------- parsers en vivo (esquema real) ----

def _parse_eloratings(world_tsv, names_tsv):
    """eloratings World.tsv + en.teams.tsv -> {iso2: elo}. Cruza por nombre ingles."""
    code2name = {}
    for ln in (names_tsv or "").splitlines():
        p = ln.split("\t")
        if len(p) >= 2:
            code2name[p[0]] = p[1]
    out = {}
    for ln in (world_tsv or "").splitlines():
        p = ln.split("\t")
        if len(p) < 4:
            continue
        code, raw_elo = p[2], p[3]
        name = code2name.get(code)
        if not name:
            continue
        iso = ALIASES.get(_norm(name))
        if not iso:
            continue
        try:
            out[iso] = int(raw_elo)
        except ValueError:
            continue
    return out


def _fetch_elo():
    """Trae Elo real de eloratings.net. Devuelve ({iso2: elo}, detalle|None)."""
    world, e1 = _http_get_text(ELO_WORLD, encoding="utf-8")
    names, e2 = _http_get_text(ELO_NAMES, encoding="utf-8")
    if not world or not names:
        return {}, (e1 or e2)
    elo = _parse_eloratings(world, names)
    return elo, (None if elo else "TSV sin matches")


def _espn_team_iso(team):
    """Resuelve el iso2 interno de un equipo ESPN (por abbr FIFA-3 o por nombre)."""
    abbr = (team or {}).get("abbreviation")
    if abbr in FIFA3_TO_ISO:
        return FIFA3_TO_ISO[abbr]
    return ALIASES.get(_norm((team or {}).get("displayName", "")))


def _fetch_espn_groups():
    """ESPN standings -> {grupo: [iso2,...]}. Para cruz-verificar el draw del seed."""
    data, err = http_get_json(ESPN_STANDINGS, params={"season": 2026})
    if not data:
        return None
    groups = {}
    for ch in data.get("children", []):
        g = (ch.get("name") or "").replace("Group ", "").strip()
        ents = ch.get("standings", {}).get("entries", [])
        isos = [_espn_team_iso(e.get("team", {})) for e in ents]
        groups[g] = [i for i in isos if i]
    return groups


def _fetch_espn_scoreboard(day_yyyymmdd):
    """Un dia del scoreboard. Devuelve lista de eventos crudos del Mundial."""
    data, err = http_get_json(ESPN_SCOREBOARD, params={"dates": day_yyyymmdd}, retries=2)
    rows = []
    if not data:
        return rows, err
    for ev in data.get("events", []):
        try:
            comp = ev["competitions"][0]
            cs = comp["competitors"]
            home = next(c for c in cs if c["homeAway"] == "home")
            away = next(c for c in cs if c["homeAway"] == "away")
            hiso = _espn_team_iso(home.get("team", {}))
            aiso = _espn_team_iso(away.get("team", {}))
            if not hiso or not aiso:
                continue
            st = comp.get("status", {}).get("type", {})
            venue = comp.get("venue", {}) or ev.get("venue", {}) or {}
            vname = venue.get("fullName", "")
            vcity = (venue.get("address", {}) or {}).get("city", "")
            rows.append({
                "espn_id": ev.get("id"),
                "utc": ev.get("date"),
                "home": hiso, "away": aiso,
                "completed": bool(st.get("completed")),
                "state": st.get("state"),
                "hs": _safe_int(home.get("score")),
                "as": _safe_int(away.get("score")),
                "venue": vname + (f", {vcity}" if vcity else ""),
            })
        except (KeyError, IndexError, StopIteration):
            continue
    return rows, None


def _safe_int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _sweep_scoreboard(start="2026-06-11", end="2026-06-28"):
    """Barre el scoreboard dia por dia y junta los eventos de fase de grupos (mismo grupo)."""
    d0 = datetime.strptime(start, "%Y-%m-%d")
    d1 = datetime.strptime(end, "%Y-%m-%d")
    raw = []
    d = d0
    while d <= d1:
        rows, _err = _fetch_espn_scoreboard(d.strftime("%Y%m%d"))
        raw.extend(rows)
        d += timedelta(days=1)
    # dedup por espn_id, conservando fase de grupos (ambos equipos en el mismo grupo)
    seen, group_rows = set(), []
    for r in raw:
        if r["espn_id"] in seen:
            continue
        seen.add(r["espn_id"])
        if ISO_GROUP.get(r["home"]) and ISO_GROUP.get(r["home"]) == ISO_GROUP.get(r["away"]):
            group_rows.append(r)
    return group_rows


def _espn_core_odds(espn_id):
    """ESPN core API por evento -> bloque de cuotas (1X2/O-U/AH) en decimal, sin key."""
    if not espn_id:
        return None
    data, err = http_get_json(ESPN_CORE_ODDS.format(eid=espn_id), retries=2)
    if not data:
        return None
    items = [it for it in data.get("items", []) if it]
    if not items:
        return None
    it = items[0]  # proveedor preferido (priority 1)
    prov = it.get("provider") or {}
    block = {"bookmaker": prov.get("name") or "ESPN"}
    h2h = [_am2dec((it.get("homeTeamOdds") or {}).get("moneyLine")),
           _am2dec((it.get("drawOdds") or {}).get("moneyLine")),
           _am2dec((it.get("awayTeamOdds") or {}).get("moneyLine"))]
    if all(v is not None for v in h2h):
        block["h2h"] = h2h
    ou, over, under = it.get("overUnder"), it.get("overOdds"), it.get("underOdds")
    od, ud = _am2dec(over), _am2dec(under)
    if ou is not None and od is not None and ud is not None:
        block["totals"] = {"line": float(ou), "over": od, "under": ud}
    sp = it.get("spread")
    hsp = (((it.get("homeTeamOdds") or {}).get("current") or {}).get("spread") or {}).get("value")
    asp = (((it.get("awayTeamOdds") or {}).get("current") or {}).get("spread") or {}).get("value")
    if sp is not None and hsp and asp:
        block["spreads"] = {"line": float(sp), "home": round(float(hsp), 4),
                            "away": round(float(asp), 4)}
    return block if "h2h" in block else None


def _parse_odds_api(data):
    """The Odds API -> {iso2_pair: bloque}. Fallback opcional (requiere ODDS_API_KEY)."""
    out = {}
    for ev in data:
        hiso = ALIASES.get(_norm(ev.get("home_team", "")))
        aiso = ALIASES.get(_norm(ev.get("away_team", "")))
        if not hiso or not aiso:
            continue
        block = {"bookmaker": "pinnacle"}
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                outs = {o["name"].lower(): o["price"] for o in mk.get("outcomes", [])}
                hn = _norm(ev.get("home_team", ""))
                an = _norm(ev.get("away_team", ""))
                if mk["key"] == "h2h":
                    block["h2h"] = [outs.get(ev.get("home_team", "").lower()),
                                    outs.get("draw"),
                                    outs.get(ev.get("away_team", "").lower())]
                elif mk["key"] == "totals":
                    pts = mk["outcomes"][0].get("point", 2.5)
                    block["totals"] = {
                        "line": pts,
                        "over": next((o["price"] for o in mk["outcomes"] if o["name"].lower() == "over"), None),
                        "under": next((o["price"] for o in mk["outcomes"] if o["name"].lower() == "under"), None)}
        out[f"{hiso}|{aiso}"] = block
    return out


# ------------------------------------------------------- construccion del dataset ----

def build_real(verbose=True, fetch_odds=True):
    """Construye teams + fixtures + odds REALES desde las fuentes en vivo.
    Devuelve (teams, fixtures, odds, report). No escribe a disco (eso lo hace build_seed)."""
    rep = {"ts": _now(), "warnings": []}

    # 1) Elo real -> teams
    elo, elo_detail = _fetch_elo()
    rep["elo"] = {"n": len(elo), "detail": elo_detail}
    missing_elo = [iso for iso, *_ in TEAMS_TABLE if iso not in elo]
    if missing_elo:
        rep["warnings"].append(f"Elo faltante (queda fallback) para: {missing_elo}")
    # ranking interno por Elo (1 = mas fuerte); para los sin Elo, valor minimo - i
    base_min = min(elo.values()) if elo else 1500
    full_elo = {iso: elo.get(iso, base_min - 50) for iso, *_ in TEAMS_TABLE}
    order = sorted(full_elo, key=lambda i: full_elo[i], reverse=True)
    rank = {iso: i + 1 for i, iso in enumerate(order)}
    teams = {}
    for iso, name, abbr, g in TEAMS_TABLE:
        teams[iso] = {"name": name, "iso2": iso, "flag": _flag(iso),
                      "elo": int(full_elo[iso]), "fifa_rank": rank[iso],
                      "group": g, "host": iso in HOST_CODES}

    # 2) Cruz-verificacion del draw contra ESPN standings (no rompe; solo avisa)
    live_groups = _fetch_espn_groups()
    if live_groups:
        for g, isos in live_groups.items():
            ours = {i for i, _n, _a, gg in TEAMS_TABLE if gg == g}
            live = set(isos)
            if live and live != ours:
                rep["warnings"].append(f"Grupo {g}: ESPN={sorted(live)} seed={sorted(ours)}")
        rep["groups_checked"] = True
    else:
        rep["groups_checked"] = False
        rep["warnings"].append("No se pudo verificar grupos contra ESPN standings")

    # 3) Fixtures reales desde el scoreboard
    raw = _sweep_scoreboard()
    rep["scoreboard_events"] = len(raw)
    if len(raw) < 60:
        rep["warnings"].append(f"Scoreboard trajo solo {len(raw)} partidos de grupo (esperado 72)")
    raw.sort(key=lambda r: (r["utc"] or "", r["espn_id"] or ""))
    # matchday por grupo: ordenar los 6 del grupo por fecha y emparejar (0,1)=F1 ...
    by_group = {}
    for r in raw:
        by_group.setdefault(ISO_GROUP[r["home"]], []).append(r)
    md_of = {}
    for g, rows in by_group.items():
        rows.sort(key=lambda r: (r["utc"] or "", r["espn_id"] or ""))
        for i, r in enumerate(rows):
            md_of[r["espn_id"]] = (i // 2) + 1
    fixtures, played = [], 0
    for idx, r in enumerate(raw, 1):
        status = "played" if (r["completed"] and r["hs"] is not None and r["as"] is not None) else "scheduled"
        if status == "played":
            played += 1
        fixtures.append({
            "id": f"WC2026-{idx:03d}",
            "espn_id": r["espn_id"],
            "group": ISO_GROUP[r["home"]],
            "matchday": md_of.get(r["espn_id"], 0),
            "home": r["home"], "away": r["away"],
            "kickoff": _to_art(r["utc"]),
            "venue": r["venue"],
            "status": status,
            "home_score": r["hs"] if status == "played" else None,
            "away_score": r["as"] if status == "played" else None,
        })
    rep["fixtures"] = len(fixtures)
    rep["played"] = played
    # chequeo de integridad: cada (grupo, fecha) deberia tener 2 partidos
    for g, rows in by_group.items():
        for md in (1, 2, 3):
            n = sum(1 for f in fixtures if f["group"] == g and f["matchday"] == md)
            if n != 2:
                rep["warnings"].append(f"Grupo {g} Fecha {md}: {n} partidos (esperado 2)")

    # 4) Cuotas reales por fixture (ESPN core API)
    odds = {}
    if fetch_odds:
        ok = 0
        for f in fixtures:
            block = _espn_core_odds(f["espn_id"])
            if block:
                odds[f["id"]] = block
                ok += 1
        rep["odds"] = {"n": ok, "of": len(fixtures)}
        if ok < len(fixtures):
            rep["warnings"].append(f"Cuotas: {ok}/{len(fixtures)} fixtures con odds en vivo")

    if verbose:
        print(f"[build_real] elo={len(elo)} teams={len(teams)} fixtures={len(fixtures)} "
              f"jugados={played} odds={len(odds)}")
        for w in rep["warnings"]:
            print("  ! " + w)
    return teams, fixtures, odds, rep


def build_seed(verbose=True):
    """Baja datos REALES y los escribe como seed versionado (anclaje offline) + cache."""
    teams, fixtures, odds, rep = build_real(verbose=verbose, fetch_odds=True)
    meta = {"_note": "Datos REALES del Mundial 2026 bajados de ESPN + eloratings.net. "
                     "Horarios en hora de Argentina (ART, UTC-3).",
            "generated_at": _now(),
            "sources": {"fixtures_results": "ESPN scoreboard/standings (sin key)",
                        "odds": "ESPN core API (sin key)",
                        "elo": "eloratings.net (World.tsv + en.teams.tsv)"},
            "n_teams": len(teams), "n_fixtures": len(fixtures), "n_odds": len(odds),
            "warnings": rep["warnings"]}
    for name, payload in [("teams.json", {"meta": meta, "teams": teams}),
                          ("fixtures.json", {"meta": meta, "fixtures": fixtures}),
                          ("odds.json", {"meta": meta, "odds": odds})]:
        json.dump(payload, open(os.path.join(SEED, name), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    # cache espejo (misma data, marcada live)
    _cache_write("teams.json", {"teams": teams})
    _cache_write("fixtures.json", {"fixtures": fixtures})
    _cache_write("odds.json", {"odds": odds})
    if verbose:
        print(f"[build_seed] escrito seed + cache en {SEED}")
    return rep


# --------------------------------------------------------------------- secciones ----

def load_teams():
    """48 selecciones (nombre, Elo, ranking, grupo, sede, bandera).
    Draw/Elo base del seed; si eloratings.net responde, refresca el Elo en vivo."""
    base = _seed_safe("teams.json") or _cache_read("teams.json") or {"teams": {}}
    teams = base["teams"]
    prov = {"source": "seed", "fetched_at": base.get("meta", {}).get("generated_at"),
            "detail": "draw + Elo base del seed versionado"}
    elo, detail = _fetch_elo()
    if elo:
        for iso, e in elo.items():
            if iso in teams:
                teams[iso]["elo"] = e
        # re-rankear por Elo refrescado
        order = sorted(teams, key=lambda i: teams[i]["elo"], reverse=True)
        for i, iso in enumerate(order):
            teams[iso]["fifa_rank"] = i + 1
        prov = {"source": "live", "fetched_at": _now(),
                "detail": f"Elo de eloratings.net ({len(elo)} selecciones)"}
        _cache_write("teams.json", {"teams": teams})
    elif _cache_read("teams.json"):
        c = _cache_read("teams.json")
        teams = c["teams"]
        prov = {"source": "cache", "fetched_at": c.get("_cached_at"), "detail": "Elo cacheado"}
    return teams, prov


def load_fixtures():
    """Fixtures + resultados. Live: ESPN scoreboard (cruce por espn_id). Fallback: cache/seed."""
    base = _seed_safe("fixtures.json") or _cache_read("fixtures.json") or {"fixtures": []}
    fixtures = base["fixtures"]
    prov = {"source": "seed", "fetched_at": base.get("meta", {}).get("generated_at"),
            "detail": "fixtures + resultados del seed versionado"}
    live = _sweep_scoreboard() if fixtures else []
    if live:
        n = _merge_results(fixtures, live)
        prov = {"source": "live", "fetched_at": _now(),
                "detail": f"ESPN scoreboard ({n} resultados aplicados)"}
        _cache_write("fixtures.json", {"fixtures": fixtures})
    elif _cache_read("fixtures.json"):
        c = _cache_read("fixtures.json")
        fixtures = c["fixtures"]
        prov = {"source": "cache", "fetched_at": c.get("_cached_at"), "detail": "fixtures cacheados"}
    return fixtures, prov


def _merge_results(fixtures, live):
    """Aplica resultados/estado en vivo sobre el fixture, cruzando por espn_id (robusto)."""
    by_id = {r["espn_id"]: r for r in live if r.get("espn_id")}
    applied = 0
    for f in fixtures:
        r = by_id.get(f.get("espn_id"))
        if not r:
            continue
        if r["completed"] and r["hs"] is not None and r["as"] is not None:
            f.update(status="played", home_score=r["hs"], away_score=r["as"])
            applied += 1
        elif not (f.get("status") == "played" and f.get("home_score") is not None):
            # Un resultado ya finalizado (seed/FIFA, con score) es 'sticky': no lo degradamos
            # a 'scheduled' por un dato en vivo transitorio (en juego / hueco del scoreboard /
            # FIFA dice final y ESPN todavia no). Solo marcamos scheduled lo que aun no es resultado.
            f["status"] = "scheduled"
    return applied


def load_odds(fixtures=None, refresh_window_days=5):
    """Cuotas por fixture. Live: ESPN core API para los PENDIENTES proximos. Fallback: cache/seed."""
    base = _seed_safe("odds.json") or _cache_read("odds.json") or {"odds": {}}
    odds = base["odds"]
    prov = {"source": "seed", "fetched_at": base.get("meta", {}).get("generated_at"),
            "detail": "cuotas del seed versionado"}

    # Fallback opcional con The Odds API (requiere key); cruza pares iso2 -> id de fixture.
    key = os.environ.get("ODDS_API_KEY")
    if key and fixtures:
        data, _err = http_get_json(ODDS_API, params={
            "apiKey": key, "regions": "eu", "markets": "h2h,totals,spreads",
            "oddsFormat": "decimal", "bookmakers": "pinnacle"})
        if data:
            try:
                pair_odds = _parse_odds_api(data)
                pair2id = {f"{f['home']}|{f['away']}": f["id"] for f in fixtures}
                for pair, block in pair_odds.items():
                    if pair in pair2id and block.get("h2h"):
                        odds[pair2id[pair]] = block
            except Exception:
                pass

    refreshed = 0
    if fixtures:
        now = datetime.now()
        for f in fixtures:
            if f.get("status") == "played" or not f.get("espn_id"):
                continue
            # solo refrescar los pendientes "proximos" para acotar las llamadas
            try:
                ko = datetime.strptime(f["kickoff"][:19], "%Y-%m-%dT%H:%M:%S")
                if (ko - now).days > refresh_window_days:
                    continue
            except ValueError:
                pass
            block = _espn_core_odds(f["espn_id"])
            if block:
                odds[f["id"]] = block
                refreshed += 1
    if refreshed:
        prov = {"source": "live", "fetched_at": _now(),
                "detail": f"ESPN core API ({refreshed} partidos proximos refrescados)"}
        _cache_write("odds.json", {"odds": odds})
    elif not _seed_safe("odds.json") and _cache_read("odds.json"):
        c = _cache_read("odds.json")
        odds = c["odds"]
        prov = {"source": "cache", "fetched_at": c.get("_cached_at"), "detail": "cuotas cacheadas"}
    return odds, prov


def load_all():
    """Carga teams + fixtures + odds con su procedencia. Punto de entrada del pipeline."""
    teams, p_t = load_teams()
    fixtures, p_f = load_fixtures()
    odds, p_o = load_odds(fixtures)
    return {"teams": teams, "fixtures": fixtures, "odds": odds,
            "provenance": {"teams": p_t, "fixtures": p_f, "odds": p_o}}


if __name__ == "__main__":
    if "--build-seed" in sys.argv:
        build_seed(verbose=True)
    else:
        bundle = load_all()
        for k, p in bundle["provenance"].items():
            print(f"{k:9s} <- {p['source']:5s}  {p.get('detail', '')}")
        print(f"equipos={len(bundle['teams'])}  fixtures={len(bundle['fixtures'])}  "
              f"odds={len(bundle['odds'])}")
