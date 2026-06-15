"""
analyze_fifaphy.py - Valida el EFECTO del xG REAL (bajado de FIFA via scrape_fifaphy.py)
sobre la forma in-tournament del pipeline. Compara, con los MISMOS partidos jugados del
seed, los multiplicadores de ataque/defensa que salen de usar GOLES CRUDOS vs xG REAL, y
el efecto sobre el Elo. Es honesto: muestra donde el xG corrige y donde casi no cambia.

No usa cuotas ni red: lee el seed (data_mundial/seed/) ya con home_xg/away_xg pegados, y
llama a las MISMAS funciones que usa update_wc.py (ratings_wc.fit_form / update_ratings).

  python analyze_fifaphy.py
"""
import json
import os
import sys
from datetime import datetime

import fetch_wc
import ratings_wc

# La consola por defecto en Windows es cp1252 y no puede imprimir Δ/→/·; forzamos UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = fetch_wc.HERE
HOSTS = fetch_wc.HOST_CODES


def _load():
    teams = json.load(open(os.path.join(fetch_wc.SEED, "teams.json"), encoding="utf-8"))["teams"]
    fixtures = json.load(open(os.path.join(fetch_wc.SEED, "fixtures.json"), encoding="utf-8"))["fixtures"]
    elo0 = {iso: float(t["elo"]) for iso, t in teams.items()}
    hist = []
    for f in fixtures:
        if f.get("status") == "played" and f.get("home_score") is not None:
            hist.append({"id": f["id"], "home": f["home"], "away": f["away"],
                         "hs": f["home_score"], "as": f["away_score"],
                         "hxg": f.get("home_xg"), "axg": f.get("away_xg"),
                         "date": f["kickoff"][:10], "kickoff": f["kickoff"]})
    hist.sort(key=lambda m: m["kickoff"])
    return teams, elo0, hist


def sec(t):
    print("\n" + "=" * 78 + f"\n  {t}\n" + "=" * 78)


def main():
    teams, elo0, hist = _load()
    name = {iso: teams[iso]["name"] for iso in teams}
    n_xg = sum(1 for m in hist if m["hxg"] is not None)

    sec("DATOS: partidos jugados del seed (con xG real de FIFA pegado)")
    print(f"  {len(hist)} partidos jugados · {n_xg} con xG real (XG_WEIGHT={ratings_wc.XG_WEIGHT})")
    if n_xg == 0:
        print("  ! No hay xG en el seed. Corré primero:  python scrape_fifaphy.py")
        return

    # acumulado por equipo: goles a favor/contra y xG a favor/contra
    agg = {}
    for m in hist:
        for code, gf, ga, xf, xa in ((m["home"], m["hs"], m["as"], m["hxg"], m["axg"]),
                                     (m["away"], m["as"], m["hs"], m["axg"], m["hxg"])):
            d = agg.setdefault(code, [0, 0, 0.0, 0.0, 0])
            d[0] += gf; d[1] += ga
            d[2] += xf or 0.0; d[3] += xa or 0.0; d[4] += 1

    asof = datetime.now()
    # Espejamos EXACTO al pipeline (predict_wc.run): mismo mu0/k_mis calibrados de lo jugado.
    mu0_cal, k_mis_cal = ratings_wc.calibrate_totals(hist, elo0, HOSTS)
    print(f"  (calibrado como en update_wc: mu0={mu0_cal:.2f}, k_mis={k_mis_cal:.3f})")
    form_goals = ratings_wc.fit_form(hist, elo0, asof, mu0=mu0_cal, host_codes=HOSTS,
                                     k_mis=k_mis_cal, xg_weight=0.0)
    form_xg = ratings_wc.fit_form(hist, elo0, asof, mu0=mu0_cal, host_codes=HOSTS,
                                  k_mis=k_mis_cal, xg_weight=ratings_wc.XG_WEIGHT)

    sec("1) FORMA: multiplicadores de ATAQUE y DEFENSA — goles crudos vs xG real")
    print("  atk>1 = ataca mas que lo que su rival deberia conceder · def>1 = concede de mas")
    print(f"  {'equipo':18s} {'PJ':>2s} {'GF':>3s} {'xGF':>5s} {'GA':>3s} {'xGA':>5s} | "
          f"{'atkGol':>6s} {'atkxG':>6s} {'Δ':>6s} | {'defGol':>6s} {'defxG':>6s} {'Δ':>6s}")
    rows = []
    for code in agg:
        gf, ga, xf, xa, pj = agg[code]
        ag, lg, _ = form_goals.get(code, (1.0, 1.0, 0))
        ax, lx, _ = form_xg.get(code, (1.0, 1.0, 0))
        rows.append((code, pj, gf, xf, ga, xa, ag, ax, ax - ag, lg, lx, lx - lg))
    # ordenar por mayor cambio total (donde el xG mas corrige)
    rows.sort(key=lambda r: abs(r[8]) + abs(r[11]), reverse=True)
    for (code, pj, gf, xf, ga, xa, ag, ax, dA, lg, lx, dD) in rows:
        print(f"  {name[code][:18]:18s} {pj:>2d} {gf:>3d} {xf:>5.2f} {ga:>3d} {xa:>5.2f} | "
              f"{ag:>6.2f} {ax:>6.2f} {dA:>+6.2f} | {lg:>6.2f} {lx:>6.2f} {dD:>+6.2f}")

    sec("2) CASOS TESTIGO: donde el resultado engania y el xG corrige")
    notes = [
        ("NL", "Paises Bajos 2-2 Japon con xG 0.63-0.34: definieron de chiripa -> con goles"),
        ("TR", "Turquia perdio 0-2 con Australia pero genero MAS xG (1.66 vs 0.99): con goles"),
        ("CH", "Suiza empato 1-1 con Qatar dominando (xG 3.14 vs 0.52): con goles parece parejo"),
    ]
    for code, txt in notes:
        if code in form_goals:
            ag = form_goals[code][0]; ax = form_xg[code][0]
            lg = form_goals[code][1]; lx = form_xg[code][1]
            print(f"  · {txt}")
            print(f"      {name[code]}: atk {ag:.2f}→{ax:.2f}  ·  def {lg:.2f}→{lx:.2f}")

    sec("3) ELO post-Fecha-1: el xG RE-ESCALA la magnitud del cambio (no su signo)")
    print("  El signo lo fija el resultado; el xG solo escala la magnitud. Modera goleadas con")
    print("  poco xG (ej. EE.UU. 4-1 con xG 1.88: +29 -> +25 de Elo); y para un FAVORITO que")
    print("  dominó pero no ganó, AGRANDA la perdida (ej. Suiza 1-1 con xG 3.14: cae mas, no menos).")
    elo_goals = ratings_wc.update_ratings(elo0, [dict(m, hxg=None, axg=None) for m in hist], HOSTS)
    elo_xg = ratings_wc.update_ratings(elo0, hist, HOSTS)
    diffs = sorted(((abs((elo_xg[i] - elo0[i]) - (elo_goals[i] - elo0[i])), i) for i in elo0),
                   reverse=True)[:8]
    print(f"  {'equipo':18s} {'Elo0':>6s} {'ΔGoles':>7s} {'ΔxG':>7s}  (cambio de rating tras la fecha)")
    for _, i in diffs:
        print(f"  {name[i][:18]:18s} {elo0[i]:>6.0f} {elo_goals[i]-elo0[i]:>+7.1f} {elo_xg[i]-elo0[i]:>+7.1f}")

    sec("RESUMEN HONESTO")
    big = [r for r in rows if abs(r[8]) >= 0.08 or abs(r[11]) >= 0.08]
    print(f"  El xG mueve de forma apreciable la forma de {len(big)}/{len(rows)} selecciones.")
    print("  En la Fecha 1 el peso de la forma sobre la prediccion es bajo (w_form ~0 con")
    print("  pocos PJ); el aporte CRECE en Fecha 2/3, cuando la forma manda mas. El efecto")
    print("  estructural ya esta: el modelo deja de premiar/castigar finiquitos de chiripa.")


if __name__ == "__main__":
    main()
