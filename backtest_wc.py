"""
backtest_wc.py - Auto-evaluacion honesta: cuantos puntos del prode habria sacado el
modelo en los partidos YA jugados de una fecha (seccion 6 del prompt).

Es la metrica seria de "que tan confiable es esto": para cada partido jugado, se predice
con la informacion que habia ANTES de ese partido (ratings/forma calibrados solo con los
partidos previos -> sin fuga de informacion), se aplica el optimizador del prode (seccion
4) y se puntua contra el resultado real con la funcion de puntaje oficial.

Ademas reporta CALIBRACION del 1X2: Brier score, log-loss y acierto del favorito.
"""
from datetime import datetime

import numpy as np

import prode_wc
import ratings_wc


def evaluate(md_played, full_history, elo0, odds_map, teams, cfg):
    """Evalua los partidos jugados de la fecha (`md_played`). `full_history` = todos los
    resultados del torneo (para reconstruir el estado previo a cada partido)."""
    import predict_wc   # import diferido: build_prediction vive alli (se comparte el motor)

    rows = []
    total = brier = logloss = 0.0
    acc = 0
    n = 0
    for f in sorted(md_played, key=lambda x: x["kickoff"]):
        # estado ANTES de este partido: solo resultados estrictamente anteriores
        before = [m for m in full_history
                  if m["kickoff"] < f["kickoff"] and m["id"] != f["id"]]
        elo_at = ratings_wc.update_ratings(elo0, before, cfg["host_codes"])
        asof = datetime.fromisoformat(f["kickoff"])
        form_at = ratings_wc.fit_form(before, elo0, asof, host_codes=cfg["host_codes"])

        # prediccion pre-partido (mismo motor que las predicciones en vivo)
        cfg_bt = dict(cfg, n_sims=1)   # el MC no se usa aca; lo minimizamos
        pred = predict_wc.build_prediction(f, teams, elo_at, elo0, form_at,
                                           odds_map.get(f["id"]), cfg_bt)

        real = (f["home_score"], f["away_score"])
        pts = prode_wc.puntos(tuple(pred["rec"]), real)
        total += pts

        # calibracion del 1X2
        real_out = "1" if real[0] > real[1] else ("X" if real[0] == real[1] else "2")
        probs = {"1": pred["p1"], "X": pred["pX"], "2": pred["p2"]}
        brier += sum((probs[o] - (1.0 if o == real_out else 0.0)) ** 2 for o in "1X2")
        logloss += -np.log(max(probs[real_out], 1e-9))
        acc += int(max(probs, key=probs.get) == real_out)
        n += 1

        rows.append({
            "id": f["id"], "group": f["group"], "home": f["home"], "away": f["away"],
            "real": [real[0], real[1]], "rec": pred["rec"], "pts": pts,
            "p1": pred["p1"], "pX": pred["pX"], "p2": pred["p2"],
            "favorito": pred["favorito"], "acerto_ganador": (max(probs, key=probs.get) == real_out),
        })

    if not n:
        return {"n": 0, "total_pts": 0, "max_pts": 0, "avg_pts": 0.0, "rows": []}
    return {
        "n": n, "total_pts": int(total), "max_pts": 12 * n,
        "avg_pts": round(total / n, 2),
        "pct_max": round(100 * total / (12 * n), 1),
        "brier": round(brier / n, 4), "logloss": round(logloss / n, 4),
        "acc_ganador": round(acc / n, 3),
        "rows": rows,
    }


if __name__ == "__main__":
    # Ejecuta una evaluacion de la Fecha 1 ya jugada como prueba rapida.
    import fetch_wc
    import predict_wc
    b = fetch_wc.load_all()
    teams = b["teams"]
    elo0 = {iso: float(t["elo"]) for iso, t in teams.items()}
    hist = predict_wc.played_history(b["fixtures"])
    md1_played = [f for f in b["fixtures"] if f["matchday"] == 1 and f.get("status") == "played"]
    cfg = {"mu0": ratings_wc.MU0_DEFAULT, "rho": -0.10,
           "w_mkt": 0.78, "host_codes": predict_wc.HOST_CODES, "n_sims": 1}
    r = evaluate(md1_played, hist, elo0, b["odds"], teams, cfg)
    print(f"F1 jugada: {r['total_pts']}/{r['max_pts']} pts ({r['pct_max']}% del maximo), "
          f"prom {r['avg_pts']}/partido, acierto ganador {r['acc_ganador']:.0%}, "
          f"Brier {r['brier']}, logloss {r['logloss']}")
