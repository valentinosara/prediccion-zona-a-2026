"""
ratings_wc.py - Fuerza de las selecciones: Elo internacional + forma (xG) in-tournament.

Tres roles:
  1) ANCLA estructural (Elo): el rating Elo internacional resume la fuerza de cada
     seleccion. Es la mejor senal cuando hay POCOS datos del torneo (la Fecha 1).
  2) FORMA in-tournament con xG: a medida que se juegan fechas, los resultados del propio
     Mundial corrigen atk/def por equipo, con DECAIMIENTO temporal (Dixon-Coles). Clave:
     se mide el rendimiento con xG (expected goals), NO con goles crudos. El xG es mucho
     menos ruidoso por partido: ej. Netherlands 2-2 Japan termino 2-2 pero el xG fue
     0.79-0.54 (los dos definieron de chiripa). Con goles crudos el modelo sobre-reacciona
     y le sube el ataque a los dos; con xG casi no se mueve, que es lo correcto.
  3) CALIBRACION del total de goles a partir de lo jugado (no a dedo): el baseline mu0 y
     cuanto sube el total en partidos MUY desnivelados (potencial de goleada vs. minnows,
     ej. Germany 7-1 Curacao) se estiman de los partidos ya disputados.

Elo -> goles esperados (lh, la): se fija el total esperado del partido mu (= mu0 + un
termino de desnivel) y se resuelve la SUPREMACIA s = lh-la por biseccion para que el
win/empate/loss del modelo Dixon-Coles iguale la expectativa Elo (We).

Campo NEUTRAL en el Mundial: la localia es ~0, salvo un bonus modesto de Elo para los
anfitriones (USA/Canada/Mexico) cuando juegan de "locales".
"""
from datetime import datetime
from math import log, exp

import numpy as np

import model_wc

MU0_DEFAULT = 2.7          # baseline de goles totales por partido (prior; se recalibra)
K_MIS_DEFAULT = 0.12       # +goles esperados por cada 100 Elo de desnivel (potencial goleada)
HOST_BONUS = 60.0          # bonus Elo modesto al anfitrion como local (campo neutral)
K_ELO = 40.0               # factor K (alto: Mundial es competicion de peso maximo)
XG_WEIGHT = 0.6            # peso del xG vs goles crudos al medir rendimiento (0=solo goles)


def elo_expect(elo_h, elo_a, home_adv=0.0):
    """Expectativa Elo (prob. de ganar + 1/2 empate) del 'local'."""
    return 1.0 / (1.0 + 10 ** (-((elo_h + home_adv) - elo_a) / 400.0))


def _eff(goals, xg, w=XG_WEIGHT):
    """Rendimiento efectivo: mezcla goles y xG (si hay xG). El xG es menos ruidoso."""
    if xg is None:
        return float(goals)
    return (1.0 - w) * float(goals) + w * float(xg)


def _model_expected_score(lh, la, rho):
    """'Expected score' estilo Elo del modelo DC: P(local) + 1/2 P(empate)."""
    p1, pX, _ = model_wc.outcome_probs(model_wc.dc_matrix(lh, la, rho))
    return p1 + 0.5 * pX


GAP_SAT = 300.0   # el efecto del desnivel sobre el total SATURA pasados ~300 Elo de brecha


def match_total(elo_h, elo_a, home_adv=0.0, mu0=MU0_DEFAULT, k_mis=K_MIS_DEFAULT):
    """Total de goles esperado del partido: baseline mu0 + termino de DESNIVEL (saturado).
    Mas desnivel -> mas goles esperados (un favorito aplastante suele golear a un minnow),
    pero el efecto satura: de 500 a 700 Elo de brecha el total casi no cambia."""
    dr = min(abs((elo_h + home_adv) - elo_a), GAP_SAT)
    return float(min(max(mu0 + k_mis * (dr / 100.0), 1.6), 4.4))


def lambdas_from_elo(elo_h, elo_a, mu0=MU0_DEFAULT, home_adv=0.0,
                     rho=model_wc.RHO_DEFAULT, k_mis=K_MIS_DEFAULT):
    """(lh, la) tal que el DC reproduce la expectativa Elo y el total mu del partido.
    Resuelve la supremacia s por biseccion (E[score] es monotona creciente en s)."""
    We = min(max(elo_expect(elo_h, elo_a, home_adv), 0.02), 0.98)
    mu = match_total(elo_h, elo_a, home_adv, mu0, k_mis)
    lo, hi = -(mu - 0.2), (mu - 0.2)
    for _ in range(40):
        s = 0.5 * (lo + hi)
        if _model_expected_score((mu + s) / 2, (mu - s) / 2, rho) < We:
            lo = s
        else:
            hi = s
    s = 0.5 * (lo + hi)
    return max((mu + s) / 2, 0.05), max((mu - s) / 2, 0.05)


def calibrate_totals(history, elo0, host_codes=(), host_bonus=HOST_BONUS,
                     prior_mu=MU0_DEFAULT, prior_k=K_MIS_DEFAULT, strength=12.0):
    """Estima (mu0, k_mis) del total de goles a partir de los partidos jugados, por
    regresion ridge hacia el prior (regularizada: con pocos partidos manda el prior).
    Modelo:  goles_totales ~ mu0 + k_mis * (|desnivel_Elo| / 100).
    No es a dedo: el baseline y el efecto de desnivel salen de lo que de verdad paso."""
    rows = []
    for m in history:
        if "hs" not in m or "as" not in m:
            continue
        ha = host_bonus if m["home"] in host_codes else 0.0
        x = min(abs((elo0[m["home"]] + ha) - elo0[m["away"]]), GAP_SAT) / 100.0
        rows.append((x, m["hs"] + m["as"]))
    if len(rows) < 3:
        return float(prior_mu), float(prior_k)
    X = np.array([[1.0, x] for x, _ in rows])
    y = np.array([t for _, t in rows], float)
    prior = np.array([prior_mu, prior_k])
    A = X.T @ X + strength * np.eye(2)
    b = X.T @ y + strength * prior
    mu0, k = np.linalg.solve(A, b)
    return float(min(max(mu0, 2.2), 3.4)), float(min(max(k, 0.0), 0.4))


def elo_update(elo_h, elo_a, gh, ga, home_adv=0.0, k=K_ELO, hxg=None, axg=None,
               xg_weight=XG_WEIGHT):
    """Actualiza Elo de un partido. El RESULTADO (gano/empato/perdio) es real y manda en W;
    el xG TEMPLA la magnitud del cambio (el multiplicador por 'dominancia'): si ganaste 7-1
    pero el xG fue 3.9, te subis menos que si lo hubieras merecido del todo."""
    We = elo_expect(elo_h, elo_a, home_adv)
    W = 1.0 if gh > ga else (0.5 if gh == ga else 0.0)
    d_goals = abs(gh - ga)
    d = d_goals if hxg is None else _eff(d_goals, abs(hxg - axg), xg_weight)
    G = 1.0 if d <= 1 else (1.5 if d < 2 else (11 + d) / 8.0)
    delta = k * G * (W - We)
    return elo_h + delta, elo_a - delta


def update_ratings(elo0, history, host_codes, host_bonus=HOST_BONUS, k=K_ELO):
    """Aplica los resultados ya jugados (cronologicos) sobre el Elo pre-torneo.
    Usa xG para templar la magnitud cuando esta disponible. No muta el Elo de entrada."""
    elo = dict(elo0)
    for m in sorted(history, key=lambda x: x.get("date", "")):
        ha = host_bonus if m["home"] in host_codes else 0.0
        elo[m["home"]], elo[m["away"]] = elo_update(
            elo[m["home"]], elo[m["away"]], m["hs"], m["as"], ha, k,
            m.get("hxg"), m.get("axg"))
    return elo


def fit_form(history, elo0, asof, mu0=MU0_DEFAULT, host_codes=(), host_bonus=HOST_BONUS,
             rho=model_wc.RHO_DEFAULT, halflife_days=200, k_mis=K_MIS_DEFAULT,
             xg_weight=XG_WEIGHT):
    """Forma in-tournament con xG: para cada equipo, multiplicadores de ataque y de 'fuga'
    defensiva = rendimiento (xG mezclado con goles) RELATIVO a la expectativa Elo del rival,
    ponderado por decaimiento temporal. atk/leak ~ 1 al inicio.

    Usar xG en vez de goles crudos es lo que evita la sobre-reaccion a marcadores de chiripa
    (ej. el 2-2 de Netherlands-Japan con 0.79-0.54 de xG casi no mueve los ataques)."""
    acc = {}   # code -> [w_sum, w*log(scored_eff/exp), w*log(conceded_eff/exp), games]
    for m in history:
        ha = host_bonus if m["home"] in host_codes else 0.0
        lh, la = lambdas_from_elo(elo0[m["home"]], elo0[m["away"]], mu0, ha, rho, k_mis)
        try:
            age = max((asof - datetime.fromisoformat(m["date"])).days, 0)
        except Exception:
            age = 0
        w = 0.5 ** (age / halflife_days)
        sc_h = _eff(m["hs"], m.get("hxg"), xg_weight)
        sc_a = _eff(m["as"], m.get("axg"), xg_weight)
        for code, scored, exp_s, conceded, exp_c in (
                (m["home"], sc_h, lh, sc_a, la),
                (m["away"], sc_a, la, sc_h, lh)):
            d = acc.setdefault(code, [0.0, 0.0, 0.0, 0])
            d[0] += w
            d[1] += w * log((scored + 0.3) / (exp_s + 0.3))
            d[2] += w * log((conceded + 0.3) / (exp_c + 0.3))
            d[3] += 1
    out = {}
    for code, d in acc.items():
        atk = exp(d[1] / d[0]) if d[0] > 0 else 1.0
        leak = exp(d[2] / d[0]) if d[0] > 0 else 1.0
        out[code] = (min(max(atk, 0.6), 1.6), min(max(leak, 0.6), 1.6), d[3])
    return out


def apply_form(lh, la, home, away, form, w_form):
    """Nudge modesto de los lambda Elo con la forma. w_form crece con los partidos
    jugados (en la Fecha 1 es ~0; la forma manda recien con varias fechas)."""
    ah, lk_h, _ = form.get(home, (1.0, 1.0, 0))
    aa, lk_a, _ = form.get(away, (1.0, 1.0, 0))
    fh = (ah * lk_a) ** w_form          # ataque local x fuga defensiva visita
    fa = (aa * lk_h) ** w_form
    return lh * fh, la * fa
