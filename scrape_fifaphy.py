"""
scrape_fifaphy.py - Baja el xG REAL por partido del Mundial 2026 y lo pega sobre los
fixtures ya jugados del seed (home_xg / away_xg), con su PROCEDENCIA.

Fuente: la API publica de FIFA (la misma que alimenta https://fifaphy.vercel.app/, web de
stats fisicas/de juego del Mundial 2026). NO se scrapea el DOM: se usan los endpoints JSON,
mucho mas robustos:

  1) Calendario:  https://api.fifa.com/api/v3/calendar/matches?idSeason=285023
       -> 104 partidos. Cada uno: MatchStatus (0=jugado), Home/Away (IdTeam, Abbreviation,
          TeamName), HomeTeamScore/AwayTeamScore, y Properties.IdIFES (id de stats).
  2) Stats por equipo:  https://fdh-api.fifa.com/v1/stats/match/{IdIFES}/teams.json
       -> { idEquipo: [["XG", valor, esPorcentaje], ["AttemptAtGoal", ...], ...] }
          145 metricas EFI por equipo EN PARTIDOS CERRADOS (el xG se publica al cerrar; un
          partido en vivo trae solo ~36 metricas basicas, sin xG -> por eso solo tomamos
          MatchStatus==0).

Solo se usa el xG (alta utilidad: alimenta la fuerza para la fecha siguiente via
ratings_wc.XG_WEIGHT). Se guardan tiros / a-puerta / threat al lado SOLO para transparencia;
NO entran al modelo (el xG ya los resume). Las stats EN VIVO no se usan para predecir ese
mismo partido: el xG entra como insumo POST-partido para recalibrar la fecha que viene.

El cruce de nombres equipo<->iso2 reusa fetch_wc (FIFA3_TO_ISO + ALIASES + _norm). El pegado
sobre el fixture matchea por PAR no-ordenado de equipos y orienta el xG al local/visita del
seed (robusto si alguna fuente invierte la localia).

Uso:
  python scrape_fifaphy.py                # Playwright (fallback a requests) + pega al seed
  python scrape_fifaphy.py --requests     # fuerza el camino requests (sin navegador)
  python scrape_fifaphy.py --no-apply     # solo escribe data_mundial/fifaphy_xg.json
"""
import json
import os
import sys
from datetime import datetime, timezone

import fetch_wc

# La consola por defecto en Windows es cp1252 y no puede imprimir ▶/·; forzamos UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ID_SEASON = "285023"   # Mundial 2026 en la API de FIFA
CAL_URL = ("https://api.fifa.com/api/v3/calendar/matches?language=en&count=500&idSeason="
           + ID_SEASON)
FDH_URL = "https://fdh-api.fifa.com/v1/stats/match/{ifes}/teams.json"
SITE = "https://fifaphy.vercel.app/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
OUT_JSON = os.path.join(fetch_wc.DATA, "fifaphy_xg.json")


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _dump_json(path, obj):
    """Escritura ATOMICA: vuelca a un temporal y reemplaza, para no dejar nunca el archivo
    (sobre todo el seed, que es el ancla) a medias si el proceso se interrumpe."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _iso(team):
    """Equipo de la API de FIFA -> codigo iso2 interno (por abbr FIFA-3, o por nombre)."""
    abbr = (team or {}).get("Abbreviation")
    if abbr in fetch_wc.FIFA3_TO_ISO:
        return fetch_wc.FIFA3_TO_ISO[abbr]
    name = ""
    tn = (team or {}).get("TeamName")
    if isinstance(tn, list) and tn:
        name = tn[0].get("Description", "")
    elif isinstance(tn, str):
        name = tn
    return fetch_wc.ALIASES.get(fetch_wc._norm(name))


def _metric(team_stats, name):
    """Saca una metrica (tupla [nombre, valor, %]) del array de stats de un equipo.
    Tolera filas malformadas (cortas / sin valor) sin romper el scrape."""
    if not isinstance(team_stats, list):
        return None
    for row in team_stats:
        if isinstance(row, (list, tuple)) and len(row) >= 2 and row[0] == name:
            try:
                return round(float(row[1]), 3)
            except (TypeError, ValueError, IndexError):
                return None
    return None


# ----------------------------------------------------- fetchers intercambiables ----

def _fetcher_requests():
    """Camino sin navegador: requests directo (anda en local; en la nube el host se bloquea)."""
    import requests
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Accept": "application/json"})

    def get(url):
        r = sess.get(url, timeout=20)
        r.raise_for_status()
        return r.json()
    return get, (lambda: None)


def _fetcher_playwright():
    """Camino Playwright: abre fifaphy (origen legitimo) y hace fetch del JSON desde la
    pagina (esquiva bloqueos por User-Agent / bot y replica el camino real del sitio)."""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = None
    try:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(locale="es-AR", user_agent=UA)
        page = ctx.new_page()
        page.goto(SITE, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(800)
    except Exception:
        # setup fallido (timeout de goto, etc.): cerramos todo antes de caer a requests
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        pw.stop()
        raise

    def get(url):
        return page.evaluate(
            "async (u) => { const r = await fetch(u); if(!r.ok) throw new Error('HTTP '+r.status);"
            " return await r.json(); }", url)

    def cleanup():
        browser.close()
        pw.stop()
    return get, cleanup


def _build_fetcher(prefer_requests=False):
    """Devuelve (get, cleanup, engine). Playwright primero; si falla, cae a requests."""
    if not prefer_requests:
        try:
            get, cleanup = _fetcher_playwright()
            return get, cleanup, "playwright"
        except Exception as e:
            print(f"  ! Playwright no disponible ({type(e).__name__}: {e}); uso requests.")
    get, cleanup = _fetcher_requests()
    return get, cleanup, "requests"


# ----------------------------------------------------------------- scrape core ----

def scrape(get):
    """Baja calendario + stats por partido y devuelve (jugados_con_xG, salteados).
    Si el calendario falla, devuelve ([], [aviso]) sin reventar (degradacion limpia: el
    seed no se toca). Una respuesta malformada de un partido se saltea, no aborta el resto."""
    try:
        cal = get(CAL_URL)
    except Exception as e:
        return [], [{"reason": f"calendario inaccesible ({type(e).__name__})"}]
    results = cal.get("Results", []) if isinstance(cal, dict) else []
    finished = [m for m in results if m.get("MatchStatus") == 0]
    out, skipped = [], []
    for m in finished:
        ifes = (m.get("Properties") or {}).get("IdIFES")
        home, away = m.get("Home") or {}, m.get("Away") or {}
        h_iso, a_iso = _iso(home), _iso(away)
        if not ifes or not h_iso or not a_iso:
            skipped.append({"abbr": (home.get("Abbreviation"), away.get("Abbreviation")),
                            "reason": "sin IdIFES" if not ifes else "sin iso2"})
            continue
        try:  # red + parseo de stats: cualquier shape rara se saltea, no mata el scrape
            tj = get(FDH_URL.format(ifes=ifes))
            if not isinstance(tj, dict):
                raise ValueError("stats no es un objeto JSON")
            h_stats = tj.get(str(home.get("IdTeam")))
            a_stats = tj.get(str(away.get("IdTeam")))
            h_xg, a_xg = _metric(h_stats, "XG"), _metric(a_stats, "XG")
        except Exception as e:
            skipped.append({"match": f"{h_iso}-{a_iso}", "reason": f"stats {type(e).__name__}"})
            continue
        hs, as_ = m.get("HomeTeamScore"), m.get("AwayTeamScore")
        if h_xg is None or a_xg is None or hs is None or as_ is None:
            skipped.append({"match": f"{h_iso}-{a_iso}", "reason": "sin XG/score (partido sin cerrar?)"})
            continue
        out.append({
            "home": h_iso, "away": a_iso,
            "home_name": _name(home), "away_name": _name(away),
            "date": (m.get("Date") or "")[:10],
            "home_score": hs, "away_score": as_,
            "home_xg": h_xg, "away_xg": a_xg,
            # extras solo-transparencia (NO entran al modelo):
            "home_shots": _metric(h_stats, "AttemptAtGoal"),
            "away_shots": _metric(a_stats, "AttemptAtGoal"),
            "home_sot": _metric(h_stats, "AttemptAtGoalOnTarget"),
            "away_sot": _metric(a_stats, "AttemptAtGoalOnTarget"),
            "ifes": str(ifes),
        })
    return out, skipped


def _name(team):
    tn = (team or {}).get("TeamName")
    if isinstance(tn, list) and tn:
        return tn[0].get("Description", "")
    return tn or ""


# --------------------------------------------------------------- pegado al seed ----

def _inject(path, matches, prov):
    """Pega home_xg/away_xg sobre los fixtures de un archivo (seed o cache), por par de
    equipos y orientado al local/visita del fixture. Como FIFA publica xG SOLO de partidos
    cerrados, tambien marca played con el score real (status<->score atados: nunca played sin
    score). Marca la procedencia por-fixture (xg_source) y avisa si el score de FIFA difiere
    del que ya estaba (ESPN). Devuelve (aplicados, mismatches)."""
    if not os.path.exists(path):
        return 0, []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    by_pair = {frozenset((f["home"], f["away"])): f for f in data.get("fixtures", [])}
    applied, mismatches = 0, []
    for mm in matches:
        f = by_pair.get(frozenset((mm["home"], mm["away"])))
        if not f or mm.get("home_score") is None or mm.get("away_score") is None:
            continue
        same = f["home"] == mm["home"]
        new_hs, new_as = ((mm["home_score"], mm["away_score"]) if same
                          else (mm["away_score"], mm["home_score"]))
        if f.get("home_score") is not None and (f["home_score"], f["away_score"]) != (new_hs, new_as):
            mismatches.append(f"{f['id']} {f['home']}-{f['away']}: seed "
                              f"{f['home_score']}-{f['away_score']} vs FIFA {new_hs}-{new_as}")
        f["status"] = "played"
        f["home_score"], f["away_score"] = new_hs, new_as
        f["home_xg"], f["away_xg"] = ((mm["home_xg"], mm["away_xg"]) if same
                                      else (mm["away_xg"], mm["home_xg"]))
        f["xg_source"] = "fifaphy"
        applied += 1
    data.setdefault("meta", {})["xg_provenance"] = dict(prov, n_applied=applied)
    _dump_json(path, data)
    return applied, mismatches


def apply_to_fixtures(matches, engine):
    """Inyecta el xG en seed/ (ancla) y cache/ (si existe). Devuelve (conteos, mismatches)."""
    prov = {"source": "FIFA EFI (api.fifa.com + fdh-api.fifa.com) via fifaphy",
            "engine": engine, "fetched_at": _now(), "metric": "XG (Expected Goals)",
            "n_matches": len(matches)}
    seed_n, seed_mm = _inject(os.path.join(fetch_wc.SEED, "fixtures.json"), matches, prov)
    cache_n, cache_mm = _inject(os.path.join(fetch_wc.CACHE, "fixtures.json"), matches, prov)
    return {"seed": seed_n, "cache": cache_n}, sorted(set(seed_mm + cache_mm))


def main():
    prefer_requests = "--requests" in sys.argv
    do_apply = "--no-apply" not in sys.argv

    print("▶ Bajando xG real del Mundial 2026 (API publica de FIFA)")
    get, cleanup, engine = _build_fetcher(prefer_requests)
    try:
        matches, skipped = scrape(get)
    finally:
        cleanup()
    print(f"   motor: {engine} · partidos jugados con xG: {len(matches)}"
          + (f" · salteados: {len(skipped)}" if skipped else ""))
    for s in skipped:
        print(f"     - salteado: {s}")

    prov = {"source": "FIFA EFI (api.fifa.com + fdh-api.fifa.com) via fifaphy",
            "engine": engine, "fetched_at": _now(), "n_matches": len(matches)}
    _dump_json(OUT_JSON, {"meta": prov, "matches": matches})
    print(f"   escrito {os.path.relpath(OUT_JSON, fetch_wc.HERE)}")

    if do_apply and matches:
        res, mismatches = apply_to_fixtures(matches, engine)
        print("▶ Pegado de home_xg/away_xg sobre fixtures jugados:")
        print(f"   seed: {res['seed']} fixtures · cache: {res['cache']} fixtures")
        for mm in mismatches:
            print(f"   ⚠ score difiere (uso FIFA): {mm}")
        print("   Listo. Ahora 'python update_wc.py --fecha N' usa el xG real en la forma.")
    elif not matches:
        print("   (sin partidos con xG: no se toca el seed)")


if __name__ == "__main__":
    main()
