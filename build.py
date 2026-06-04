"""
build.py - Pipeline: de los JSON por temporada (worldfootball) al resultado
final (top-3 de rachas de victorias por temporada) + export a results.json.

- Agrupa los archivos por temporada (las temporadas con 2 zonas tienen 2 JSON).
- Combina los partidos de las zonas (cada equipo juega solo en su zona, asi que
  agrupar por equipo es correcto). Dedupe defensivo por match_id.
- Calcula, por equipo, la racha maxima de victorias consecutivas en ORDEN
  CRONOLOGICO (data-datetime; ronda como desempate) -> ver analyze.py.
- Top-3 por temporada, marcando empates en el corte.
"""
import json
import os

from analyze import (load_season_file, season_ranking, parse_dt, parse_score,
                      round_num)
from teams import canon  # normalizacion de nombres

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# ---- Registro de temporadas (orden cronologico) -------------------------
# files: JSON de la(s) zona(s).  fmt: descripcion del formato.  status:
# 'complete' | 'covid' | 'ongoing'.  fuente: URL worldfootball de cada zona.
def U(se, slug):
    return (f"https://www.worldfootball.net/competition/co1787/"
            f"argentina-primera-nacional/{se}/{slug}/all-matches/")

SEASONS = [
    dict(label="2010/2011", files=["wf_se6101_2010-2011.json"], status="complete",
         fmt="20 equipos, zona unica, todos contra todos ida y vuelta (38 fechas).",
         src=[U("se6101", "2010-2011")]),
    dict(label="2011/2012", files=["wf_se7241_2011-2012.json"], status="complete",
         fmt="20 equipos, zona unica, ida y vuelta (38 fechas).",
         src=[U("se7241", "2011-2012")]),
    dict(label="2012/2013", files=["wf_se9362_2012-2013.json"], status="complete",
         fmt="20 equipos, zona unica, ida y vuelta (38 fechas).",
         src=[U("se9362", "2012-2013")]),
    dict(label="2013/2014", files=["wf_se12992_2013-2014.json"], status="complete",
         fmt="22 equipos, zona unica, ida y vuelta (42 fechas).",
         src=[U("se12992", "2013-2014")]),
    dict(label="2014", files=["wf_se15670_2014.json"], status="complete",
         fmt="Torneo de transicion (ago-dic 2014). 22 equipos en 2 zonas de 11, "
             "ida y vuelta (cada equipo jugo 20 PJ; 22 fechas en el calendario).",
         src=[U("se15670", "2014")]),
    dict(label="2015", files=["wf_se17039_2015.json"], status="complete",
         fmt="22 equipos, zona unica, ida y vuelta (42 fechas).",
         src=[U("se17039", "2015")]),
    dict(label="2016", files=["wf_se20122_2016.json"], status="complete",
         fmt="Torneo corto (feb-jun 2016). 22 equipos, zona unica, solo ida (21 fechas).",
         src=[U("se20122", "2016")]),
    dict(label="2016/2017", files=["wf_se21929_2016-2017.json"], status="complete",
         fmt="23 equipos, zona unica, ida y vuelta (46 fechas).",
         src=[U("se21929", "2016-2017")]),
    dict(label="2017/2018", files=["wf_se24611_2017-2018.json"], status="complete",
         fmt="25 equipos, zona unica, solo ida (25 fechas).",
         src=[U("se24611", "2017-2018")]),
    dict(label="2018/2019", files=["wf_se29215_2018-2019.json"], status="complete",
         fmt="25 equipos, zona unica, solo ida (25 fechas).",
         src=[U("se29215", "2018-2019")]),
    dict(label="2019/2020", files=["wf_se32639_2019-2020-zona-a.json",
                                    "wf_se32638_2019-2020-zona-b.json"], status="covid",
         fmt="32 equipos en 2 zonas de 16, ida y vuelta (30 fechas c/u). "
             "SUSPENDIDO por COVID-19 (marzo 2020) y luego ANULADO por AFA: "
             "no se completo ni se definio campeon/descensos por mesa.",
         src=[U("se32639", "2019-2020-zona-a"), U("se32638", "2019-2020-zona-b")]),
    dict(label="2021", files=["wf_se38348_2021-grupo-a.json",
                              "wf_se38347_2021-grupo-b.json"], status="complete",
         fmt="35 equipos en 2 zonas (A=17, B=18), ida y vuelta (34 fechas).",
         src=[U("se38348", "2021-grupo-a"), U("se38347", "2021-grupo-b")]),
    dict(label="2022", files=["wf_se42905_2022.json"], status="complete",
         fmt="37 equipos, zona unica, solo ida (37 fechas).",
         src=[U("se42905", "2022")]),
    dict(label="2023", files=["wf_se49762_2023-grupo-a.json",
                              "wf_se49761_2023-grupo-b.json"], status="complete",
         fmt="37 equipos en 2 zonas (A=19, B=18), ida y vuelta.",
         src=[U("se49762", "2023-grupo-a"), U("se49761", "2023-grupo-b")]),
    dict(label="2024", files=["wf_se62387_2024.json"], status="complete",
         fmt="38 equipos en 2 zonas de 19. Todos contra todos ida y vuelta dentro "
             "de la zona (36 PJ) + 1 rival interzonal ida y vuelta (2 PJ) = 38 PJ "
             "y 38 fechas. Los interzonales son fase regular (cuentan para la tabla).",
         src=[U("se62387", "2024")]),
    dict(label="2025", files=["wf_se85625_2025.json"], status="complete",
         fmt="36 equipos en 2 zonas de 18, ida y vuelta (34 fechas).",
         src=[U("se85625", "2025")]),
    dict(label="2026", files=["wf_se112408_2026.json"], status="ongoing",
         fmt="36 equipos. TEMPORADA EN CURSO: datos parciales al 26/05/2026.",
         src=[U("se112408", "2026")]),
]


# Las cadenas 'fmt' se escribieron sin tildes en el fuente; se restauran aqui
# para la presentacion (es-AR).
_ACC = {
    "zona unica": "zona única", "transicion": "transición",
    "se completo": "se completó", "definio": "definió",
    "unica diferencia": "única diferencia",
}


def _accents(s):
    for a, b in _ACC.items():
        s = s.replace(a, b)
    return s


def load_season_matches(season):
    matches = []
    seen = set()
    for fn in season["files"]:
        d = load_season_file(os.path.join(DATA, fn))
        for m in d["matches"]:
            mid = m.get("match_id")
            if mid and mid in seen:
                continue
            if mid:
                seen.add(mid)
            matches.append(m)
    return matches


def dd(g):
    dt = parse_dt(g["dt"])
    return dt.strftime("%d/%m/%Y") if dt else "?"


def _team_entry(r):
    run = r["run"]
    return {
        "team": canon(r["team"], r["team_id"]),
        "team_raw": r["team"],
        "team_id": r["team_id"],
        "streak": r["streak"],
        "played": r["played"],
        "start": dd(run[0]) if run else None,
        "end": dd(run[-1]) if run else None,
        "wins": [
            {"round": g["round"], "date": dd(g), "vs": canon(g["opp"]),
             "home": g["home"], "gf": g["gf"], "ga": g["ga"]}
            for g in run
        ],
    }


def compute_season(season):
    matches = load_season_matches(season)
    ranking = season_ranking(matches, team_key="id")  # agrupar por teID estable
    played = sum(1 for m in matches if parse_score(m["score"]))
    total = len(matches)

    # Top-3 por LONGITUD DISTINTA de racha (puesto 1/2/3).
    # Si varios equipos comparten una longitud, se listan todos en ese puesto.
    by_len = {}
    for r in ranking:
        if r["streak"] <= 0:
            continue
        by_len.setdefault(r["streak"], []).append(_team_entry(r))
    from datetime import datetime as _dt

    def _start_key(t):
        try:
            return _dt.strptime(t["start"], "%d/%m/%Y")
        except Exception:
            return _dt.max

    ranks = []
    for i, L in enumerate(sorted(by_len, reverse=True)[:3], 1):
        # empate en una longitud: ordenar por fecha real de inicio de la racha
        teams = sorted(by_len[L], key=lambda t: (_start_key(t), t["team"]))
        ranks.append({"rank": i, "streak": L, "teams": teams})

    season["fmt"] = _accents(season["fmt"])
    return {
        "label": season["label"], "status": season["status"], "fmt": season["fmt"],
        "src": season["src"], "total_matches": total, "played_matches": played,
        "ranks": ranks,
    }


def main():
    results = [compute_season(s) for s in SEASONS]
    with open(os.path.join(DATA, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # tabla legible por consola
    for r in results:
        flag = {"complete": "", "covid": "  [COVID: anulada]",
                "ongoing": "  [EN CURSO/parcial]"}[r["status"]]
        print(f"\n=== {r['label']}{flag}  ({r['played_matches']}/{r['total_matches']} PJ) ===")
        for rk in r["ranks"]:
            teams = rk["teams"]
            if len(teams) == 1:
                t = teams[0]
                print(f"  {rk['rank']}) {rk['streak']} victorias - {t['team']}  ({t['start']} -> {t['end']})")
            else:
                names = ", ".join(t["team"] for t in teams)
                print(f"  {rk['rank']}) {rk['streak']} victorias - {len(teams)} equipos: {names}")
    print(f"\nresults.json escrito con {len(results)} temporadas.")


if __name__ == "__main__":
    main()
