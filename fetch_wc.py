"""
fetch_wc.py - Fetch + cache + fallback de TODO lo que el sistema necesita.

El sistema "baja todo solo" cada vez que corre. Con fetch automatico la resiliencia es
parte del pipeline: cada fuente se intenta EN VIVO y, si falla, cae al ultimo CACHE y,
en ultima instancia, al SEED versionado en el repo. Cada seccion deja constancia de su
PROCEDENCIA (live/cache/seed + timestamp) para mostrarla honestamente en el HTML.

Fuentes (verificar/adaptar los endpoints al correr; cambian seguido):
  - Fixtures/resultados : ESPN hidden API (sin key) -> football-data.org -> Wikipedia.
  - Cuotas (1X2/O-U/AH) : The Odds API (key gratis, ODDS_API_KEY) -> API-Football.
  - Fuerza (Elo)        : eloratings.net  ;  ranking FIFA como secundario.

Importante sobre la red: este sistema necesita salida hacia esos dominios. Si la
politica de red del entorno los bloquea (403), corre en MODO DEGRADADO con cache/seed
y el HTML lo avisa. La whitelist necesaria esta documentada en el README.
"""
import json
import os
import time
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data_mundial")
SEED = os.path.join(DATA, "seed")
CACHE = os.path.join(DATA, "cache")
os.makedirs(CACHE, exist_ok=True)

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
ODDS_API = "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds"
ELO_URL = "https://www.eloratings.net/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ProdeMundial2026/1.0)",
           "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}
TIMEOUT = 8


# ----------------------------------------------------------------------- helpers ----

def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _seed(name):
    return json.load(open(os.path.join(SEED, name), encoding="utf-8"))


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


# --------------------------------------------------------------------- secciones ----

def load_teams():
    """48 selecciones (nombre, Elo, ranking FIFA, grupo, sede, bandera).
    El draw/Elo base sale del seed; si eloratings.net responde, refresca el Elo."""
    base = _seed("teams.json")
    teams = base["teams"]
    prov = {"source": "seed", "fetched_at": base.get("meta", {}).get("generated_at"),
            "detail": "draw + Elo base del seed versionado"}
    # Intento de refresco de Elo en vivo (best-effort; si la red bloquea, queda el seed).
    html, err = _http_get_text(ELO_URL)
    if html:
        try:
            live = _parse_eloratings(html, teams)
            if live:
                for iso, e in live.items():
                    if iso in teams:
                        teams[iso]["elo"] = e
                prov = {"source": "live", "fetched_at": _now(),
                        "detail": f"Elo de eloratings.net ({len(live)} selecciones)"}
                _cache_write("teams.json", {"teams": teams})
        except Exception:
            pass
    elif _cache_read("teams.json"):
        c = _cache_read("teams.json")
        teams = c["teams"]
        prov = {"source": "cache", "fetched_at": c.get("_cached_at"), "detail": "Elo cacheado"}
    return teams, prov


def load_fixtures():
    """Fixtures + resultados ya jugados. Live: ESPN scoreboard por dia. Fallback: seed."""
    seed = _seed("fixtures.json")
    fixtures = seed["fixtures"]
    prov = {"source": "seed", "fetched_at": seed.get("meta", {}).get("generated_at"),
            "detail": "fixtures + resultados del seed versionado"}
    live = _fetch_espn_fixtures(fixtures)
    if live:
        _merge_results(fixtures, live)
        prov = {"source": "live", "fetched_at": _now(),
                "detail": f"ESPN scoreboard ({len(live)} partidos con dato)"}
        _cache_write("fixtures.json", {"fixtures": fixtures})
    elif _cache_read("fixtures.json"):
        c = _cache_read("fixtures.json")
        fixtures = c["fixtures"]
        prov = {"source": "cache", "fetched_at": c.get("_cached_at"), "detail": "fixtures cacheados"}
    return fixtures, prov


def load_odds():
    """Cuotas 1X2 / O-U / handicap por partido. Live: The Odds API. Fallback: seed."""
    seed = _seed("odds.json")
    odds = seed["odds"]
    prov = {"source": "seed", "fetched_at": seed.get("meta", {}).get("generated_at"),
            "detail": "cuotas del seed versionado"}
    key = os.environ.get("ODDS_API_KEY")
    if key:
        data, err = http_get_json(ODDS_API, params={
            "apiKey": key, "regions": "eu", "markets": "h2h,totals,spreads",
            "oddsFormat": "decimal", "bookmakers": "pinnacle"})
        if data:
            try:
                live = _parse_odds_api(data)
                if live:
                    odds.update(live)
                    prov = {"source": "live", "fetched_at": _now(),
                            "detail": f"The Odds API ({len(live)} partidos)"}
                    _cache_write("odds.json", {"odds": odds})
            except Exception:
                pass
    elif _cache_read("odds.json"):
        c = _cache_read("odds.json")
        odds = c["odds"]
        prov = {"source": "cache", "fetched_at": c.get("_cached_at"), "detail": "cuotas cacheadas"}
    return odds, prov


def load_all():
    """Carga teams + fixtures + odds con su procedencia. Punto de entrada del pipeline."""
    teams, p_t = load_teams()
    fixtures, p_f = load_fixtures()
    odds, p_o = load_odds()
    return {"teams": teams, "fixtures": fixtures, "odds": odds,
            "provenance": {"teams": p_t, "fixtures": p_f, "odds": p_o}}


# ------------------------------------------------- parsers en vivo (best-effort) ----
# Estos parsers cubren el "camino feliz" con red. Los esquemas reales cambian seguido;
# si no matchean, el pipeline cae a cache/seed sin romperse.

def _http_get_text(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200 and len(r.text) > 200:
            return r.text, None
        return None, f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return None, type(e).__name__


def _name_index(teams):
    """Indice nombre/codigo -> ISO para cruzar datos en vivo con nuestras selecciones."""
    idx = {}
    for iso, t in teams.items():
        idx[t["name"].lower()] = iso
        idx[iso.lower()] = iso
    return idx


def _fetch_espn_fixtures(fixtures):
    """Intenta ESPN scoreboard para los dias del fixture y devuelve {id_o_nombre: (hs,as)}.
    Devuelve {} si la red no responde (modo degradado)."""
    days = sorted({f["kickoff"][:10].replace("-", "") for f in fixtures})
    found = {}
    for day in days:
        data, err = http_get_json(ESPN_SCOREBOARD, params={"dates": day}, retries=1)
        if not data:
            continue
        for ev in data.get("events", []):
            try:
                comp = ev["competitions"][0]
                cs = comp["competitors"]
                home = next(c for c in cs if c["homeAway"] == "home")
                away = next(c for c in cs if c["homeAway"] == "away")
                if comp.get("status", {}).get("type", {}).get("completed"):
                    key = (home["team"]["displayName"].lower(),
                           away["team"]["displayName"].lower())
                    found[key] = (int(home["score"]), int(away["score"]))
            except Exception:
                continue
    return found


def _merge_results(fixtures, live):
    """Aplica resultados en vivo (por nombres) sobre el fixture si hay match."""
    # `live` viene indexado por nombres en ingles de ESPN; cruce best-effort por substring.
    for f in fixtures:
        for (hn, an), (hs, as_) in live.items():
            if f["home"].lower() in hn or f["away"].lower() in an:
                f.update(status="played", home_score=hs, away_score=as_)
                break


def _parse_eloratings(html, teams):
    """Parser best-effort de eloratings.net -> {ISO: elo}. (Esquema HTML variable.)"""
    return {}   # se completa al adaptar al HTML real; por ahora deja el Elo del seed/cache


def _parse_odds_api(data):
    """The Odds API -> {match_id_o_nombre: {h2h, totals, spreads}}. Best-effort."""
    out = {}
    for ev in data:
        home = ev.get("home_team", "").lower()
        away = ev.get("away_team", "").lower()
        block = {"bookmaker": "pinnacle"}
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                outs = {o["name"].lower(): o["price"] for o in mk.get("outcomes", [])}
                if mk["key"] == "h2h":
                    block["h2h"] = [outs.get(home), outs.get("draw"), outs.get(away)]
                elif mk["key"] == "totals":
                    pts = mk["outcomes"][0].get("point", 2.5)
                    block["totals"] = {"line": pts,
                                       "over": next((o["price"] for o in mk["outcomes"] if o["name"].lower() == "over"), None),
                                       "under": next((o["price"] for o in mk["outcomes"] if o["name"].lower() == "under"), None)}
        out[f"{home}|{away}"] = block
    return out


if __name__ == "__main__":
    bundle = load_all()
    for k, p in bundle["provenance"].items():
        print(f"{k:9s} <- {p['source']:5s}  {p.get('detail', '')}")
    print(f"equipos={len(bundle['teams'])}  fixtures={len(bundle['fixtures'])}  "
          f"odds={len(bundle['odds'])}")
