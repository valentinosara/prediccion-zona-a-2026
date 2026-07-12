"""
predict_wc.py - Orquesta la prediccion de UNA fecha del Mundial 2026.

Flujo (estilo update.py del repo, un comando por fecha):
  1) baja datos frescos (fetch_wc): fixtures + resultados ya jugados, cuotas, Elo;
  2) re-actualiza ratings/forma con los resultados ya jugados (Elo update + decaimiento);
  3) re-ancla al mercado vigente;
  4) detecta, dentro de la fecha pedida, que partidos ya se jugaron (calibran) vs cuales
     faltan (se predicen);
  5) para cada partido pendiente arma P(h,a) y aplica el optimizador del prode (seccion 4);
  6) auto-evalua los partidos de la fecha ya jugados (backtest_wc);
  7) escribe data_mundial/pred_wc.json y persiste data_mundial/state.json.

El motor probabilistico vive en model_wc/market_wc/ratings_wc/prode_wc/montecarlo_wc.
"""
import argparse
import json
import os
from datetime import datetime

import numpy as np

import fetch_wc
import market_wc
import model_wc
import montecarlo_wc
import prode_wc
import ratings_wc

DATA = fetch_wc.DATA
HOST_CODES = {"MX", "CA", "US"}


def w_market(tournament_games_per_team):
    """Peso del mercado en el blend. En la F1 (casi sin datos del torneo) el mercado
    pesa fuerte; a medida que se juegan fechas, la forma in-tournament gana algo de peso."""
    return float(np.clip(0.82 - 0.12 * tournament_games_per_team, 0.45, 0.85))


def build_prediction(match, teams, elo, elo0, form, odds_block, cfg):
    """Arma la prediccion completa de UN partido (reutilizada por el backtest).

    Devuelve un dict con P(1X2), lambdas, recomendacion del prode, top-5, heatmap,
    Monte Carlo y confianza. `elo` = ratings vigentes; `elo0` = ratings pre-torneo
    (para la forma); `form` = multiplicadores atk/def; `odds_block` = cuotas crudas o None.
    """
    home, away = match["home"], match["away"]
    mu0, rho = cfg["mu0"], cfg["rho"]
    host_adv = ratings_wc.HOST_BONUS if home in cfg["host_codes"] else 0.0

    # --- modelo de fuerza (Elo + forma in-tournament, peso de forma crece con los PJ) ---
    lh_mod, la_mod = ratings_wc.lambdas_from_elo(elo[home], elo[away], mu0, host_adv, rho,
                                                 cfg.get("k_mis", ratings_wc.K_MIS_DEFAULT))
    g_min = min(form.get(home, (0, 0, 0))[2], form.get(away, (0, 0, 0))[2])
    w_form = min(g_min / 6.0, 1.0) * 0.5
    lh_mod, la_mod = ratings_wc.apply_form(lh_mod, la_mod, home, away, form, w_form)

    # --- senal de mercado (de-vig 1X2 + O/U + handicap -> lambdas de mercado) ----------
    mk = market_wc.parse_match_odds(odds_block) if odds_block else {"ok": False}
    if mk.get("ok"):
        lh_mkt, la_mkt, _, _ = market_wc.market_lambdas(
            mk["q1"], mk["qX"], mk["q2"], mk.get("q_over"), mu0, rho,
            mk.get("s_hint"), mk.get("line_total", 2.5))
        w_mkt = cfg["w_mkt"]
        lh, la = model_wc.blend_lambdas(lh_mkt, la_mkt, lh_mod, la_mod, w_mkt)
        P = model_wc.dc_matrix(lh, la, rho)
        P = model_wc.anchor_to_market(P, mk["q1"], mk["qX"], mk["q2"])   # 1X2 lo manda el mercado
    else:
        lh_mkt = la_mkt = None
        w_mkt = 0.0
        lh, la = lh_mod, la_mod
        P = model_wc.dc_matrix(lh, la, rho)

    p1, pX, p2 = model_wc.outcome_probs(P)
    fav = ["1", "X", "2"][int(np.argmax([p1, pX, p2]))]
    opt = prode_wc.optimize(P, top=5, mode=cfg.get("jugada", "ev"))
    modo = model_wc.most_probable_score(P)
    mc = montecarlo_wc.simulate_match(P, n=cfg.get("n_sims", 50000))
    conf_label, H = montecarlo_wc.confidence(p1, pX, p2, opt["gap"])

    ganador = {"1": teams[home]["name"], "X": "Empate", "2": teams[away]["name"]}[fav]
    return {
        "id": match["id"], "group": match["group"], "matchday": match["matchday"],
        "home": home, "away": away, "kickoff": match["kickoff"], "venue": match.get("venue"),
        "p1": round(p1, 4), "pX": round(pX, 4), "p2": round(p2, 4), "favorito": fav,
        "ganador": ganador,
        "lh": round(float(lh), 2), "la": round(float(la), 2),
        "lh_mkt": None if lh_mkt is None else round(float(lh_mkt), 2),
        "la_mkt": None if la_mkt is None else round(float(la_mkt), 2),
        "lh_mod": round(float(lh_mod), 2), "la_mod": round(float(la_mod), 2),
        "w_mkt": round(w_mkt, 2), "market_used": bool(mk.get("ok")),
        "bookmaker": mk.get("bookmaker") if mk.get("ok") else None,
        "rec": opt["rec"], "ev_rec": round(opt["ev_rec"], 3), "gap": round(opt["gap"], 3),
        "modo": list(modo), "modo_prob": round(float(P[modo[0], modo[1]]), 4),
        "top": [{"score": c["score"], "prob": round(c["prob"], 4), "ev": round(c["ev"], 3)}
                for c in opt["top"]],
        "heatmap": [[round(float(P[i, j]), 4) for j in range(7)] for i in range(7)],
        "confianza": conf_label, "entropia": H, "mc": mc,
    }


def played_history(fixtures):
    """Resultados ya jugados (cronologicos) con fecha para Elo update + forma."""
    hist = []
    for f in fixtures:
        if f.get("status") == "played" and f.get("home_score") is not None:
            hist.append({"id": f["id"], "home": f["home"], "away": f["away"],
                         "hs": f["home_score"], "as": f["away_score"],
                         "hxg": f.get("home_xg"), "axg": f.get("away_xg"),
                         "date": f["kickoff"][:10], "kickoff": f["kickoff"]})
    hist.sort(key=lambda m: m["kickoff"])
    return hist


def run(fecha, n_sims=50000, jugada="ev"):
    bundle = fetch_wc.load_all()
    teams, fixtures, odds = bundle["teams"], bundle["fixtures"], bundle["odds"]
    elo0 = {iso: float(t["elo"]) for iso, t in teams.items()}

    history = played_history(fixtures)
    elo_now = ratings_wc.update_ratings(elo0, history, HOST_CODES)
    asof = datetime.now()
    # Calibracion del total de goles (baseline + efecto desnivel) con lo ya jugado:
    mu0_cal, k_mis_cal = ratings_wc.calibrate_totals(history, elo0, HOST_CODES)
    form = ratings_wc.fit_form(history, elo0, asof, mu0=mu0_cal, host_codes=HOST_CODES,
                               k_mis=k_mis_cal)
    tg_per_team = (2 * len(history)) / max(len(teams), 1)   # PJ promedio del torneo

    cfg = {"mu0": mu0_cal, "rho": model_wc.RHO_DEFAULT, "k_mis": k_mis_cal,
           "w_mkt": w_market(tg_per_team), "host_codes": HOST_CODES, "n_sims": n_sims,
           "jugada": jugada}

    md = [f for f in fixtures if f["matchday"] == fecha]
    pendientes_fx = sorted((f for f in md if f.get("status") != "played"),
                           key=lambda f: f["kickoff"])
    jugados_fx = [f for f in md if f.get("status") == "played"]

    # --- predicciones de los partidos PENDIENTES de la fecha ---------------------------
    preds = [build_prediction(f, teams, elo_now, elo0, form, odds.get(f["id"]), cfg)
             for f in pendientes_fx]
    ev_total = round(sum(p["ev_rec"] for p in preds), 1)

    # --- auto-evaluacion sobre los partidos de la fecha YA jugados ---------------------
    import backtest_wc
    bt = backtest_wc.evaluate(jugados_fx, history, elo0, odds, teams, cfg)

    datos_al = max((m["kickoff"] for m in history), default=None)
    conf_counts = {"alta": 0, "media": 0, "baja": 0}
    for p in preds:
        conf_counts[p["confianza"]] += 1

    out = {
        "meta": {
            "fecha": fecha, "generado": asof.isoformat(timespec="seconds"),
            "datos_al": datos_al, "n_pendientes": len(preds), "n_jugados": len(jugados_fx),
            "ev_total": ev_total, "w_mkt": cfg["w_mkt"], "mu0": round(cfg["mu0"], 2),
            "k_mis": round(cfg["k_mis"], 3), "rho": cfg["rho"],
            "tournament_games_per_team": round(tg_per_team, 2),
            "confianza_global": conf_counts, "provenance": bundle["provenance"],
            "n_sims": n_sims, "jugada": jugada,
        },
        "teams": {iso: {k: t[k] for k in ("name", "iso2", "flag", "elo", "fifa_rank",
                                          "group", "host")}
                  for iso, t in teams.items()},
        "elo_now": {iso: round(elo_now[iso], 1) for iso in teams},
        "pendientes": preds,
        "backtest": bt,
    }
    os.makedirs(DATA, exist_ok=True)
    json.dump(out, open(os.path.join(DATA, "pred_wc.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # --- estado persistente: ratings al ultimo partido + historial + predicciones ------
    state = {"updated": asof.isoformat(timespec="seconds"), "fecha": fecha,
             "elo": {iso: round(elo_now[iso], 1) for iso in teams},
             "history": history,
             "emitted": [{"id": p["id"], "rec": p["rec"], "ev_rec": p["ev_rec"],
                          "p1": p["p1"], "pX": p["pX"], "p2": p["p2"]} for p in preds]}
    json.dump(state, open(os.path.join(DATA, "state.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return out


def main():
    ap = argparse.ArgumentParser(description="Prediccion del prode del Mundial 2026 por fecha")
    ap.add_argument("--fecha", type=int, required=True, help="numero de fecha (1, 2 o 3)")
    ap.add_argument("--sims", type=int, default=50000, help="simulaciones Monte Carlo por partido")
    args = ap.parse_args()
    out = run(args.fecha, n_sims=args.sims)
    m = out["meta"]
    src = m["provenance"]
    print(f"Fecha {args.fecha}: {m['n_pendientes']} pendientes, {m['n_jugados']} jugados "
          f"(datos {src['fixtures']['source']}/{src['odds']['source']}).")
    print(f"  Puntos esperados totales de la fecha: {m['ev_total']}  "
          f"(confianza {m['confianza_global']})")
    bt = out["backtest"]
    if bt["n"]:
        print(f"  Auto-evaluacion (F{args.fecha} ya jugada): {bt['total_pts']}/{bt['max_pts']} "
              f"pts del prode en {bt['n']} partidos  (prom {bt['avg_pts']}/partido)")


if __name__ == "__main__":
    main()
