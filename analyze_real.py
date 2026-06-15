"""
analyze_real.py - Analiza las fechas YA jugadas del Mundial 2026 (datos reales levantados
por busqueda web) y muestra los AJUSTES del modelo: calibracion del total de goles,
impacto de usar xG vs goles crudos, y un backtest del prode (modelo viejo vs nuevo).
Tambien predice los partidos de HOY con el modelo nuevo y genera docs/mundial_hoy.html.

Datos: data_mundial/real/md1.json (resultados reales + xG donde estaba publicado + Elo
aproximado pre-torneo). Esto NO usa cuotas (no hay red): es una comparacion solo-modelo,
para aislar la calidad del motor de fuerza. Con cuotas en vivo el mercado afila todo.
"""
import json
import os
from datetime import datetime

import numpy as np

import model_wc
import prode_wc
import predict_cli
import predict_wc
import ratings_wc

HERE = os.path.dirname(os.path.abspath(__file__))
REAL = os.path.join(HERE, "data_mundial", "real", "md1.json")
RHO = model_wc.RHO_DEFAULT


def model_pred(home, away, elo, hosts, mu0, k_mis):
    """Prediccion solo-modelo de un partido: matriz P, 1X2 y jugada del prode."""
    ha = ratings_wc.HOST_BONUS if home in hosts else 0.0
    lh, la = ratings_wc.lambdas_from_elo(elo[home], elo[away], mu0, ha, RHO, k_mis)
    P = model_wc.dc_matrix(lh, la, RHO)
    p1, pX, p2 = model_wc.outcome_probs(P)
    opt = prode_wc.optimize(P)
    return lh, la, p1, pX, p2, opt, P


def total_dist(P):
    """Distribucion del total de goles a partir de la matriz."""
    n = P.shape[0]
    t = np.zeros(2 * n - 1)
    for h in range(n):
        for a in range(n):
            t[h + a] += P[h, a]
    return t


def sec(title):
    print("\n" + "=" * 72 + f"\n  {title}\n" + "=" * 72)


def main():
    d = json.load(open(REAL, encoding="utf-8"))
    elo = {k: float(v) for k, v in d["elo"].items()}
    hosts = set(d["hosts"])
    results = d["results"]
    for m in results:
        m["date"] = m.get("date", "2026-06-14")

    sec("1) CALIBRACION DEL TOTAL DE GOLES (con lo realmente jugado)")
    tot = [m["hs"] + m["as"] for m in results]
    print(f"  Partidos jugados: {len(results)} · goles totales promedio = {np.mean(tot):.2f} "
          f"(mediana {np.median(tot):.1f})")
    print(f"  El modelo VIEJO asumia un total fijo mu0 = 2.60 para todos los partidos.")
    mu0_cal, k_mis_cal = ratings_wc.calibrate_totals(results, elo, hosts)
    print(f"  El modelo NUEVO lo estima de los datos (ridge hacia el prior):")
    print(f"     baseline mu0 = {mu0_cal:.2f}   ·   efecto desnivel k_mis = {k_mis_cal:.3f} "
          f"(+goles por cada 100 Elo de diferencia)")
    print(f"  Ej. Germany-Curacao (desnivel ~{abs(elo['Germany']-elo['Curacao']):.0f} Elo): "
          f"total esperado VIEJO 2.60  ->  NUEVO "
          f"{ratings_wc.match_total(elo['Germany'], elo['Curacao'], 0, mu0_cal, k_mis_cal):.2f} "
          f"(real: 8).")

    sec("2) xG vs GOLES CRUDOS: la forma in-tournament deja de sobre-reaccionar")
    asof = datetime.fromisoformat("2026-06-15")
    form_goals = ratings_wc.fit_form(results, elo, asof, mu0=mu0_cal, host_codes=hosts,
                                     k_mis=k_mis_cal, xg_weight=0.0)
    form_xg = ratings_wc.fit_form(results, elo, asof, mu0=mu0_cal, host_codes=hosts,
                                  k_mis=k_mis_cal, xg_weight=ratings_wc.XG_WEIGHT)
    print("  Multiplicador de ATAQUE estimado tras la Fecha 1 (1.0 = neutral):")
    print(f"    {'equipo':16s} {'goles':>8s} {'real(gf)':>9s} {'xG':>6s}   {'atk goles':>10s} {'atk xG':>8s}")
    by_team = {}
    for m in results:
        by_team.setdefault(m["home"], []).append((m["hs"], m.get("hxg")))
        by_team.setdefault(m["away"], []).append((m["as"], m.get("axg")))
    for team in ["Netherlands", "Japan", "Germany", "Sweden", "United States"]:
        gf = sum(g for g, _ in by_team.get(team, []))
        xg = by_team.get(team, [(None, None)])[0][1]
        xg_s = f"{xg:.2f}" if xg is not None else "n/d"
        ag = form_goals.get(team, (1.0,))[0]
        ax = form_xg.get(team, (1.0,))[0]
        print(f"    {team:16s} {'':>8s} {gf:>9d} {xg_s:>6s}   {ag:>10.2f} {ax:>8.2f}")
    print("  Netherlands/Japan: con GOLES el ataque se infla (marcaron 2 cada uno); con xG")
    print("  (0.79 y 0.54) queda casi neutral -> no sobre-reacciona a un 2-2 de chiripa.")

    sec("3) BACKTEST DEL PRODE sobre la Fecha 1 real (modelo VIEJO vs NUEVO, solo-modelo)")
    print(f"  {'Partido':34s} {'real':>5s}  {'VIEJO':>11s}  {'NUEVO':>11s}")
    old_pts = new_pts = old_acc = new_acc = 0
    old_tll = new_tll = old_tmae = new_tmae = 0.0
    for m in results:
        h, a = m["home"], m["away"]
        real = (m["hs"], m["as"])
        ro = "1" if real[0] > real[1] else ("X" if real[0] == real[1] else "2")
        # VIEJO: mu0 fijo 2.6, sin desnivel
        lho, lao, p1o, pXo, p2o, opto, Po = model_pred(h, a, elo, hosts, 2.6, 0.0)
        # NUEVO: calibrado
        lhn, lan, p1n, pXn, p2n, optn, Pn = model_pred(h, a, elo, hosts, mu0_cal, k_mis_cal)
        po, pn = prode_wc.puntos(tuple(opto["rec"]), real), prode_wc.puntos(tuple(optn["rec"]), real)
        old_pts += po; new_pts += pn
        old_acc += int(max(zip([p1o, pXo, p2o], "1X2"))[1] == ro)
        new_acc += int(max(zip([p1n, pXn, p2n], "1X2"))[1] == ro)
        to, tn = total_dist(Po), total_dist(Pn)
        rt = real[0] + real[1]
        old_tll += -np.log(max(to[rt], 1e-9)); new_tll += -np.log(max(tn[rt], 1e-9))
        old_tmae += abs((lho + lao) - rt); new_tmae += abs((lhn + lan) - rt)
        print(f"  {h+' vs '+a:34.34s} {str(real[0])+'-'+str(real[1]):>5s}  "
              f"{str(opto['rec'][0])+'-'+str(opto['rec'][1]):>4s} {po:>2d}pt   "
              f"{str(optn['rec'][0])+'-'+str(optn['rec'][1]):>4s} {pn:>2d}pt")
    n = len(results)
    print(f"\n  PRODE (modelo solo, sin cuotas):  VIEJO {old_pts}/{12*n} pts  ->  "
          f"NUEVO {new_pts}/{12*n} pts")
    print(f"  Acierto ganador:                  VIEJO {old_acc}/{n}        ->  NUEVO {new_acc}/{n}")
    print(f"  Total de goles - MAE:             VIEJO {old_tmae/n:.2f}      ->  NUEVO {new_tmae/n:.2f}  (mas bajo = mejor)")
    print(f"  Total de goles - log-loss:        VIEJO {old_tll/n:.3f}     ->  NUEVO {new_tll/n:.3f} (mas bajo = mejor)")

    sec("4) PREDICCION DE LOS PARTIDOS DE HOY (modelo nuevo, datos reales, sin cuotas)")
    cfg = {"mu0": mu0_cal, "rho": RHO, "k_mis": k_mis_cal,
           "w_mkt": 0.0, "host_codes": hosts, "n_sims": 20000}
    for i, t in enumerate(d["today"]):
        spec = dict(t, elo=[elo[t["home"]], elo[t["away"]]])
        match, teams, elom, _ = predict_cli.make_match(spec, i)
        pred = predict_wc.build_prediction(match, teams, elom, elom, {}, None, cfg)
        print(predict_cli.report_text(pred, teams))
    print("\n  NOTA: esto es solo-modelo (Elo aprox., sin cuotas). El HTML oficial de la")
    print("  fecha, con cuotas reales y el draw real, sale de:  python update_wc.py --fecha 1")


if __name__ == "__main__":
    main()
