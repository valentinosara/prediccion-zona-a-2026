"""
backtest.py - ¿Cuánto pesa REALMENTE el valor de plantel? (calibracion historica)

Pregunta 1 (la del usuario): en 2021-2025, ¿a los planteles mas caros les fue
mejor?  -> correlacion entre valor de plantel (estandarizado por temporada) y
rendimiento (puntos por partido, PPP, de toda la temporada).

Pregunta 2 (la que define el peso): a la altura actual del torneo (~40% jugado),
¿el valor de plantel agrega poder predictivo POR ENCIMA de la forma ya mostrada?
-> regresion out-of-sample:  ppp_resto ~ ppp_parcial + valor_z  (estandarizados).
El peso del plantel para 2026 sale de aca, no de una eleccion a dedo.

Fuentes: Transfermarkt (valor por temporada) + worldfootball (resultados).
"""
import glob
import json
import os
import re
import unicodedata
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DP = os.path.join(HERE, "data_promiedos")
WF = os.path.join(HERE, "data")
CUT = 0.40  # fraccion jugada al momento de "predecir" (≈ 14/36 actual)

SEASONS = {
    "2021": ["wf_se38348_2021-grupo-a.json", "wf_se38347_2021-grupo-b.json"],
    "2022": ["wf_se42905_2022.json"],
    "2023": ["wf_se49762_2023-grupo-a.json", "wf_se49761_2023-grupo-b.json"],
    "2024": ["wf_se62387_2024.json"],
    "2025": ["wf_se85625_2025.json"],
}


def loadj(p):
    raw = open(p, encoding="utf-8").read()
    d = json.loads(raw)
    return json.loads(d) if isinstance(d, str) else d


def val_eur(s):
    s = s.replace("€", "").strip()
    if s.endswith("m"): return float(s[:-1]) * 1e6
    if s.endswith("k"): return float(s[:-1]) * 1e3
    return float(s or 0)


def norm(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\b(ca|cd|cs|club|atletico|deportivo|asociacion|amsd|de|del|y|esgrima|antonio|tomba|ac|fc|sad)\b", " ", n)
    n = re.sub(r"[^a-z ]", " ", n)
    return set(w for w in n.split() if len(w) > 2)


def match(wf_names, tm):
    """Devuelve {wf_name: value_eur} cruzando por tokens."""
    tmn = [(t["team"], norm(t["team"]), val_eur(t["value"])) for t in tm]
    out = {}
    for wn in wf_names:
        k = norm(wn); best, bs, bv = None, 0, 0
        for tn, tnk, tv in tmn:
            sc = len(k & tnk) / max(1, len(k | tnk))
            if sc > bs: bs, best, bv = sc, tn, tv
        if bs >= 0.34:
            out[wn] = bv
    return out


def team_ppp(matches):
    """Por equipo: PPP parcial (primer CUT) y PPP resto, en orden cronologico."""
    games = {}
    for m in matches:
        sc = re.match(r"^(\d+):(\d+)$", (m.get("score") or "").strip())
        if not sc:
            continue
        hs, as_ = int(sc.group(1)), int(sc.group(2))
        dt = m.get("dt") or ""
        for tid, gf, ga in [(m["home"], hs, as_), (m["away"], as_, hs)]:
            games.setdefault(tid, []).append((dt, 3 if gf > ga else (1 if gf == ga else 0)))
    res = {}
    for t, gl in games.items():
        gl.sort()
        n = len(gl); k = max(1, int(round(n * CUT)))
        first = [p for _, p in gl[:k]]
        rest = [p for _, p in gl[k:]]
        if not rest:
            continue
        res[t] = {"ppp_parcial": sum(first) / len(first), "ppp_resto": sum(rest) / len(rest),
                  "ppp_total": sum(p for _, p in gl) / n, "n": n}
    return res


def main():
    rows = []  # pooled: (season, team, value_z, ppp_parcial, ppp_resto, ppp_total)
    print(f"Corte 'parcial' = primeros {int(CUT*100)}% de fechas (≈ la situacion actual 14/36)\n")
    print("Correlacion VALOR de plantel <-> rendimiento (PPP total), por temporada:")
    for season, files in SEASONS.items():
        matches = []
        for f in files:
            matches += loadj(os.path.join(WF, f))["matches"]
        ppp = team_ppp(matches)
        tm = loadj(os.path.join(DP, f"tm_{season}.json"))["teams"]
        vmap = match(list(ppp.keys()), tm)
        common = [t for t in ppp if t in vmap]
        logv = np.array([np.log(vmap[t]) for t in common])
        vz = (logv - logv.mean()) / logv.std()
        tot = np.array([ppp[t]["ppp_total"] for t in common])
        r = float(np.corrcoef(vz, tot)[0, 1])
        print(f"  {season}: {len(common):2d} equipos cruzados · corr(valor, PPP)= {r:+.2f}")
        for k, t in enumerate(common):
            rows.append((season, t, float(vz[k]), ppp[t]["ppp_parcial"], ppp[t]["ppp_resto"], ppp[t]["ppp_total"]))

    # pooled
    vz = np.array([r[2] for r in rows])
    pp = np.array([r[3] for r in rows])
    rest = np.array([r[4] for r in rows])
    tot = np.array([r[5] for r in rows])
    n = len(rows)
    print(f"\nPooled: {n} observaciones equipo-temporada")
    print(f"  corr(valor, PPP_total)        = {np.corrcoef(vz, tot)[0,1]:+.2f}   "
          f"(R2={np.corrcoef(vz, tot)[0,1]**2:.2f})")
    print(f"  corr(forma_parcial, PPP_resto)= {np.corrcoef(pp, rest)[0,1]:+.2f}")
    print(f"  corr(valor, PPP_resto)        = {np.corrcoef(vz, rest)[0,1]:+.2f}")

    # regresion estandarizada: ppp_resto ~ ppp_parcial + valor_z
    def z(x): return (x - x.mean()) / x.std()
    X = np.column_stack([z(pp), vz, np.ones(n)])
    y = z(rest)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    b_form, b_val = float(beta[0]), float(beta[1])
    yhat = X @ beta
    r2 = 1 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    print(f"\nRegresion (estandarizada)  ppp_resto ~ forma_parcial + valor:")
    print(f"  beta forma_parcial = {b_form:+.3f}")
    print(f"  beta valor_plantel = {b_val:+.3f}")
    print(f"  R2 del modelo conjunto = {r2:.2f}")
    # peso del plantel calibrado (clip a >=0)
    bf, bv = max(b_form, 0), max(b_val, 0)
    alpha = bv / (bf + bv) if (bf + bv) > 0 else 0.0
    print(f"\n=> PESO del plantel calibrado:  alpha = {alpha:.2f}  "
          f"(forma {1-alpha:.0%} / plantel {alpha:.0%})")
    json.dump({"alpha": round(alpha, 3), "beta_form": round(b_form, 3),
               "beta_value": round(b_val, 3), "r2": round(float(r2), 3),
               "n": n, "cut": CUT,
               "corr_value_total": round(float(np.corrcoef(vz, tot)[0, 1]), 3)},
              open(os.path.join(DP, "backtest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
