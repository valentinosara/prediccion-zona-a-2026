"""
predict_zonaA.py - Modelo predictivo de la Zona A 2026 (Primera Nacional).

MODELO base (Poisson de ataque/defensa con ventaja de localia):
  goles_local  ~ Poisson(lh),  log(lh) = mu + gamma + atk[local]  - def[visita]
  goles_visita ~ Poisson(la),  log(la) = mu        + atk[visita] - def[local]
  (atk_i: poder ofensivo; def_i: solidez defensiva; ambos "mas alto = mejor")
  Calidad de un equipo  c_i = atk_i + def_i.

PRIOR DE PLANTEL (lo que pediste):
  El valor de mercado del plantel (Transfermarkt) es un proxy OBJETIVO de la
  jerarquia (integra calidad, experiencia y edad). Se usa como prior sobre la
  CALIDAD c_i: se regulariza c_i hacia  scale * z_i  (z = valor de plantel
  estandarizado en log). 'scale' se estima de los propios datos (regresion de
  la calidad observada vs. el valor), asi el prior queda en la escala correcta.
  El peso 'w_prior' decide cuanto pesa el plantel frente a la forma:
    - "forma"       w=0     -> solo resultados (ciego al plantel)
    - "equilibrado" w medio -> mezcla forma + jerarquia de plantel
    - "plantel"     w alto  -> la jerarquia manda (util si hay pocas fechas)
  Con ~14 fechas, el termino de verosimilitud (252 partidos) compite con el
  prior: equipos con poca muestra se "tiran" mas hacia su plantel.

QUE NO HACE: ajustes a mano por opinion. El DT/contexto se documenta aparte
(no se inventa un coeficiente). La edad se reporta como descriptivo (el valor
de mercado ya la incorpora).

PREDICCION por partido: probabilidades 1/X/2 (grilla Poisson) + marcador mas
probable. La TABLA proyectada usa PUNTOS ESPERADOS (no el sesgo del 'modo').
Monte Carlo (20k simulaciones) para prob. de campeon / Reducido / descenso.
"""
import json
import math
import os
import numpy as np

DP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_promiedos")
MAXG, ITERS, LR, L2_LVL = 8, 7000, 0.05, 0.04
_FACT = np.array([math.factorial(k) for k in range(MAXG + 1)], float)


def load(path):
    raw = open(os.path.join(DP, path), encoding="utf-8").read()
    d = json.loads(raw)
    return json.loads(d) if isinstance(d, str) else d


def zscores(squad, team_ids):
    logv = np.array([math.log(squad[t]["value"]) for t in team_ids])
    z = (logv - logv.mean()) / logv.std()
    return {t: float(z[k]) for k, t in enumerate(team_ids)}


def calibrate(played, team_ids):
    """Calibracion base (solo forma): atk/def por maxima verosimilitud Poisson."""
    idx = {t: k for k, t in enumerate(team_ids)}
    n = len(team_ids)
    h = np.array([idx[m["home_id"]] for m in played])
    a = np.array([idx[m["away_id"]] for m in played])
    hs = np.array([m["hs"] for m in played], float)
    as_ = np.array([m["as"] for m in played], float)
    mu, gamma = 0.0, 0.2
    atk = np.zeros(n); dff = np.zeros(n)
    for _ in range(ITERS):
        lh = np.exp(mu + gamma + atk[h] - dff[a])
        la = np.exp(mu + atk[a] - dff[h])
        eh, ea = hs - lh, as_ - la
        g_mu = eh.sum() + ea.sum(); g_gamma = eh.sum()
        g_atk = np.zeros(n); g_def = np.zeros(n)
        np.add.at(g_atk, h, eh); np.add.at(g_atk, a, ea)
        np.add.at(g_def, a, -eh); np.add.at(g_def, h, -ea)
        g_atk -= L2_LVL * atk; g_def -= L2_LVL * dff
        m_ = len(played)
        mu += LR * g_mu / m_; gamma += LR * g_gamma / m_
        atk += LR * g_atk / m_; dff += LR * g_def / m_
        atk -= atk.mean(); dff -= dff.mean()
    return {"idx": idx, "mu": mu, "gamma": gamma, "atk": atk, "def": dff}


def blend_cal(cal0, team_ids, zmap, alpha):
    """Mezcla la CALIDAD (atk+def) entre forma (cal0) y plantel (z * escala de
    la calidad observada). alpha = peso del plantel (0=solo forma, 1=solo plantel).
    Conserva el ESTILO (atk-def) que mostraron los resultados."""
    idx = cal0["idx"]
    atk0, def0 = cal0["atk"], cal0["def"]
    c0 = atk0 + def0                      # calidad observada
    d0 = atk0 - def0                      # estilo (ofensivo/defensivo)
    std_c = c0.std()
    z = np.array([zmap[t] for t in team_ids])
    tgt = std_c * z                       # plantel a la escala de la calidad
    c = (1 - alpha) * c0 + alpha * tgt
    atk = (c + d0) / 2.0
    dff = (c - d0) / 2.0
    return {"idx": idx, "mu": cal0["mu"], "gamma": cal0["gamma"], "atk": atk, "def": dff}


def quality(cal, team_ids):
    return {t: float(cal["atk"][cal["idx"][t]] + cal["def"][cal["idx"][t]]) for t in team_ids}


def predict_match(cal, home_id, away_id):
    i, j = cal["idx"][home_id], cal["idx"][away_id]
    lh = float(np.exp(cal["mu"] + cal["gamma"] + cal["atk"][i] - cal["def"][j]))
    la = float(np.exp(cal["mu"] + cal["atk"][j] - cal["def"][i]))
    gh = np.exp(-lh) * lh ** np.arange(MAXG + 1) / _FACT
    ga = np.exp(-la) * la ** np.arange(MAXG + 1) / _FACT
    P = np.outer(gh, ga)
    p1, pX, p2 = np.tril(P, -1).sum(), np.trace(P), np.triu(P, 1).sum()
    s = p1 + pX + p2
    p1, pX, p2 = p1 / s, pX / s, p2 / s
    outcome = ["1", "X", "2"][int(np.argmax([p1, pX, p2]))]
    best, bx, by = -1, 0, 0
    for x in range(MAXG + 1):
        for y in range(MAXG + 1):
            cond = (x > y) if outcome == "1" else (x == y if outcome == "X" else x < y)
            if cond and P[x, y] > best:
                best, bx, by = P[x, y], x, y
    return {"lh": round(lh, 2), "la": round(la, 2),
            "p1": round(float(p1), 3), "pX": round(float(pX), 3), "p2": round(float(p2), 3),
            "outcome": outcome, "hs": bx, "as": by}


def standings(fixture, zonaA_ids, teams, incluir):
    """Tabla de Zona A con los partidos de las jornadas en `incluir` (set de
    numeros de fecha). Jugados: puntos reales (3/1/0). No jugados: PUNTOS
    ESPERADOS (3*p1+pX, etc.) y goles esperados."""
    st = {i: dict(pts=0.0, pj=0, w=0, d=0, l=0, gf=0.0, ga=0.0, real_pj=0) for i in zonaA_ids}
    for f in fixture:
        if f["fecha"] not in incluir:
            continue
        if f["played"]:
            hs, as_ = f["hs"], f["as"]
            for tid, gf, ga in [(f["home_id"], hs, as_), (f["away_id"], as_, hs)]:
                if tid not in st:
                    continue
                r = st[tid]; r["pj"] += 1; r["real_pj"] += 1; r["gf"] += gf; r["ga"] += ga
                if gf > ga: r["pts"] += 3; r["w"] += 1
                elif gf == ga: r["pts"] += 1; r["d"] += 1
                else: r["l"] += 1
        else:
            p = f["pred"]
            if f["home_id"] in st:
                r = st[f["home_id"]]; r["pj"] += 1
                r["pts"] += 3 * p["p1"] + p["pX"]; r["gf"] += p["lh"]; r["ga"] += p["la"]
            if f["away_id"] in st:
                r = st[f["away_id"]]; r["pj"] += 1
                r["pts"] += 3 * p["p2"] + p["pX"]; r["gf"] += p["la"]; r["ga"] += p["lh"]
    rows = []
    for i in zonaA_ids:
        r = st[i]
        rows.append({"id": i, "team": teams[i]["name"], "pts": round(r["pts"], 1),
                     "pj": r["pj"], "real_pj": r["real_pj"], "w": r["w"], "d": r["d"], "l": r["l"],
                     "gf": round(r["gf"], 1), "ga": round(r["ga"], 1), "dif": round(r["gf"] - r["ga"], 1)})
    rows.sort(key=lambda r: (-r["pts"], -r["dif"], -r["gf"], r["team"]))
    for k, r in enumerate(rows, 1):
        r["pos"] = k
    return rows


def montecarlo(fixture, zonaA_ids, cal, n_sims=20000, seed=7):
    rng = np.random.default_rng(seed)
    aidx = {t: k for k, t in enumerate(zonaA_ids)}
    nA = len(zonaA_ids)
    base_pts, base_dif = np.zeros(nA), np.zeros(nA)
    fut = []
    for f in fixture:
        hk, ak = aidx.get(f["home_id"], -1), aidx.get(f["away_id"], -1)
        if f["played"]:
            hs, as_ = f["hs"], f["as"]
            if hk >= 0: base_pts[hk] += 3 if hs > as_ else (1 if hs == as_ else 0); base_dif[hk] += hs - as_
            if ak >= 0: base_pts[ak] += 3 if as_ > hs else (1 if as_ == hs else 0); base_dif[ak] += as_ - hs
        else:
            i, j = cal["idx"][f["home_id"]], cal["idx"][f["away_id"]]
            lh = float(np.exp(cal["mu"] + cal["gamma"] + cal["atk"][i] - cal["def"][j]))
            la = float(np.exp(cal["mu"] + cal["atk"][j] - cal["def"][i]))
            fut.append((hk, ak, lh, la))
    pts = np.tile(base_pts, (n_sims, 1)).astype(float)
    dif = np.tile(base_dif, (n_sims, 1)).astype(float)
    for hk, ak, lh, la in fut:
        hs = rng.poisson(lh, n_sims); as_ = rng.poisson(la, n_sims)
        hw, dr, aw = hs > as_, hs == as_, as_ > hs
        if hk >= 0: pts[:, hk] += np.where(hw, 3, np.where(dr, 1, 0)); dif[:, hk] += hs - as_
        if ak >= 0: pts[:, ak] += np.where(aw, 3, np.where(dr, 1, 0)); dif[:, ak] += as_ - hs
    score = pts + dif * 1e-4
    order = np.argsort(-score, axis=1)
    ranks = np.empty_like(order)
    ranks[np.arange(n_sims)[:, None], order] = np.arange(1, nA + 1)[None, :]
    res = {}
    for t, k in aidx.items():
        rk = ranks[:, k]
        res[t] = {"p_champ": round(float((rk == 1).mean()), 4),
                  "p_top8": round(float((rk <= 8).mean()), 4),
                  "p_last": round(float((rk == nA).mean()), 4),
                  "pos_avg": round(float(rk.mean()), 2),
                  "pts_avg": round(float(pts[:, k].mean()), 1),
                  "pts_p10": round(float(np.percentile(pts[:, k], 10)), 1),
                  "pts_p90": round(float(np.percentile(pts[:, k], 90)), 1)}
    return res


def run_variant(data, cal, alpha, label):
    import copy
    fixture = copy.deepcopy(data["fixture"])
    for f in fixture:
        if not f["played"]:
            f["pred"] = predict_match(cal, f["home_id"], f["away_id"])
    teams = data["teams"]; zonaA_ids = data["zonaA_ids"]
    from collections import defaultdict
    from datetime import datetime as _dt
    byf = defaultdict(list)
    for f in fixture:
        byf[f["fecha"]].append(f)
    is_real = {N: all(g["played"] for g in byf[N]) for N in byf}

    def fmin(N):  # fecha real de disputa de la jornada (la postergada va a su nueva fecha)
        ps = []
        for g in byf[N]:
            try:
                ps.append(_dt.strptime(g["start"], "%d-%m-%Y %H:%M"))
            except Exception:
                pass
        return min(ps) if ps else _dt.max
    chron = sorted(byf.keys(), key=fmin)   # ORDEN CRONOLOGICO real (F4 reprogramada en su lugar)

    snaps = []
    for k in range(1, len(chron) + 1):
        added = chron[k - 1]
        snaps.append({"paso": k, "fecha": added, "is_real": bool(is_real.get(added, False)),
                      "rows": standings(fixture, zonaA_ids, teams, set(chron[:k]))})
    mc = montecarlo(fixture, zonaA_ids, cal)
    for r in snaps[-1]["rows"]:
        r["mc"] = mc[r["id"]]
    return {"label": label, "alpha": alpha, "gamma": round(cal["gamma"], 3),
            "fixture": fixture, "standings_by_fecha": snaps, "montecarlo": mc}


def main():
    data = load("zonaA_data.json")
    squad = load("squad_value.json")
    colors = load("colors.json")
    escudos = load("escudos.json")
    teams = data["teams"]
    for tid in teams:
        teams[tid]["color"] = colors.get(tid, {}).get("color", "#888")
        teams[tid]["txt"] = colors.get(tid, {}).get("txt", "#fff")
        teams[tid]["badge"] = escudos.get(tid, "")
    team_ids = list(teams.keys())
    zmap = zscores(squad, team_ids)

    # 1) calibracion base (solo forma) y asociacion plantel<->rendimiento
    cal0 = calibrate(data["played_all"], team_ids)
    z = np.array([zmap[t] for t in team_ids])
    c = np.array([quality(cal0, team_ids)[t] for t in team_ids])
    r2 = float(np.corrcoef(c, z)[0, 1] ** 2)
    print(f"Asociacion plantel<->rendimiento (14 fechas): R2={r2:.2f} "
          f"(el plantel explica {100*r2:.0f}% de la calidad observada hasta ahora)")

    # peso del plantel CALIBRADO por el backtest historico (no elegido a dedo)
    bt = load("backtest.json")
    a_cal = bt["alpha"]
    ALPHAS = {"forma": 0.0, "calibrado": a_cal, "plantel": 0.60}
    LABELS = {"forma": "Solo forma (ignora el plantel)",
              "calibrado": f"Calibrado por la historia · {int(round((1-a_cal)*100))}% forma / {int(round(a_cal*100))}% plantel",
              "plantel": "Plantel alto (60%) · sensibilidad"}
    variants = {k: run_variant(data, blend_cal(cal0, team_ids, zmap, a), a, LABELS[k])
                for k, a in ALPHAS.items()}

    # fechas dinamicas (para no hardcodear): ultima jornada jugada y dia de hoy
    from datetime import datetime as _dt2
    def _pf(s):
        try:
            return _dt2.strptime(s, "%d-%m-%Y %H:%M")
        except Exception:
            return None
    pdates = [d for d in (_pf(f.get("start")) for f in data["fixture"] if f["played"]) if d]
    datos_al = max(pdates).strftime("%d/%m/%Y") if pdates else "—"
    from collections import Counter as _Counter
    _tot = _Counter(f["fecha"] for f in data["fixture"])
    _pla = _Counter(f["fecha"] for f in data["fixture"] if f["played"])
    fechas_reales = sum(1 for n in _tot if _pla[n] == _tot[n])  # jornadas completas jugadas

    out = {
        "meta": {"generado": _dt2.now().strftime("%d/%m/%Y"), "datos_al": datos_al,
                 "fechas_jugadas": fechas_reales,
                 "calibrado_con": len(data["played_all"]), "n_sims": 20000,
                 "prior_r2": round(r2, 2), "default_variant": "calibrado",
                 "backtest": bt},
        "teams": {i: teams[i] for i in data["zonaA_ids"]},
        "squad": {i: {"value": squad[i]["value"], "age": squad[i]["age"], "z": round(zmap[i], 2)}
                  for i in data["zonaA_ids"]},
        "variants": variants,
    }
    json.dump(out, open(os.path.join(DP, "pred_results.json"), "w", encoding="utf-8"), ensure_ascii=False)

    # comparacion de la tabla final entre variantes
    print(f"\nTabla FINAL (modelo CALIBRADO, alpha={a_cal}) + comparacion:")
    print(f"  {'Equipo':24s} {'Forma':>6} {'CALIB':>7} {'Plantel':>8}   (€plantel)")
    eq = {r["id"]: r["pos"] for r in variants["calibrado"]["standings_by_fecha"][-1]["rows"]}
    pl = {r["id"]: r["pos"] for r in variants["plantel"]["standings_by_fecha"][-1]["rows"]}
    cal_rows = variants["calibrado"]["standings_by_fecha"][-1]["rows"]
    forma_pos = {r["id"]: r["pos"] for r in variants["forma"]["standings_by_fecha"][-1]["rows"]}
    for r in cal_rows:
        i = r["id"]; m = r["mc"]
        print(f"  {r['team']:24s} {forma_pos[i]:>5}º {r['pos']:>6}º {pl[i]:>7}º   "
              f"€{squad[i]['value']/1e6:.1f}m  camp {100*m['p_champ']:.0f}%")


if __name__ == "__main__":
    main()
