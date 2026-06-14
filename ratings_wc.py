"""
ratings_wc.py - Fuerza de las selecciones: Elo internacional + forma in-tournament.

Dos roles:
  1) ANCLA estructural (Elo): el rating Elo internacional (estilo World Football Elo)
     resume la fuerza de cada seleccion y se actualiza partido a partido. Es la mejor
     senal de fuerza disponible cuando hay POCOS datos del torneo (justo la Fecha 1).
  2) FORMA in-tournament: a medida que se juegan fechas, los resultados del propio
     Mundial corrigen el Elo (atk/def por equipo) con DECAIMIENTO temporal (Dixon-Coles:
     los partidos viejos pesan menos). Asi la F2 refleja lo que paso en la F1.

Elo -> goles esperados (lh, la): no se inventa una constante "a dedo". Se fija el total
mu0 (goles esperados del partido, ~2.6 en Mundial) y se resuelve la SUPREMACIA s = lh-la
por biseccion para que el win/empate/loss del modelo Dixon-Coles iguale la expectativa
Elo (We). Eso deja el "quien gana" consistente con el Elo y el total con mu0.

Campo NEUTRAL en el Mundial (sedes compartidas): la localia es ~0, salvo un bonus
modesto de Elo para los anfitriones (USA/Canada/Mexico) cuando juegan de "locales".
"""
from datetime import datetime
from math import log, exp

import model_wc

MU0_DEFAULT = 2.6          # goles totales esperados por partido (fase de grupos Mundial)
HOST_BONUS = 60.0          # bonus Elo modesto al anfitrion como local (campo neutral)
K_ELO = 40.0               # factor K (alto: Mundial es competicion de peso maximo)


def elo_expect(elo_h, elo_a, home_adv=0.0):
    """Expectativa Elo (prob. de ganar + 1/2 empate) del 'local'."""
    return 1.0 / (1.0 + 10 ** (-((elo_h + home_adv) - elo_a) / 400.0))


def _model_expected_score(lh, la, rho):
    """'Expected score' estilo Elo del modelo DC: P(local) + 1/2 P(empate)."""
    p1, pX, _ = model_wc.outcome_probs(model_wc.dc_matrix(lh, la, rho))
    return p1 + 0.5 * pX


def lambdas_from_elo(elo_h, elo_a, mu0=MU0_DEFAULT, home_adv=0.0, rho=model_wc.RHO_DEFAULT):
    """(lh, la) tal que el DC reproduce la expectativa Elo y total mu0.
    Resuelve la supremacia s por biseccion (E[score] es monotona creciente en s)."""
    We = min(max(elo_expect(elo_h, elo_a, home_adv), 0.02), 0.98)
    lo, hi = -(mu0 - 0.2), (mu0 - 0.2)
    for _ in range(40):
        s = 0.5 * (lo + hi)
        if _model_expected_score((mu0 + s) / 2, (mu0 - s) / 2, rho) < We:
            lo = s
        else:
            hi = s
    s = 0.5 * (lo + hi)
    return max((mu0 + s) / 2, 0.05), max((mu0 - s) / 2, 0.05)


def elo_update(elo_h, elo_a, gh, ga, home_adv=0.0, k=K_ELO):
    """Actualiza Elo de un partido con multiplicador por diferencia de goles
    (World Football Elo): empates por 1 -> G=1, por 2 -> 1.5, por 3+ -> (11+d)/8."""
    We = elo_expect(elo_h, elo_a, home_adv)
    W = 1.0 if gh > ga else (0.5 if gh == ga else 0.0)
    d = abs(gh - ga)
    G = 1.0 if d <= 1 else (1.5 if d == 2 else (11 + d) / 8.0)
    delta = k * G * (W - We)
    return elo_h + delta, elo_a - delta


def update_ratings(elo0, history, host_codes, host_bonus=HOST_BONUS, k=K_ELO):
    """Aplica los resultados ya jugados (cronologicos) sobre el Elo pre-torneo.
    Devuelve un Elo nuevo (no muta el de entrada)."""
    elo = dict(elo0)
    for m in sorted(history, key=lambda x: x.get("date", "")):
        ha = host_bonus if m["home"] in host_codes else 0.0
        eh, ea = elo[m["home"]], elo[m["away"]]
        elo[m["home"]], elo[m["away"]] = elo_update(eh, ea, m["hs"], m["as"], ha, k)
    return elo


def fit_form(history, elo0, asof, mu0=MU0_DEFAULT, host_codes=(), host_bonus=HOST_BONUS,
             rho=model_wc.RHO_DEFAULT, halflife_days=200):
    """Forma in-tournament: para cada equipo, multiplicadores de ataque y de 'fuga'
    defensiva = goles marcados/encajados RELATIVOS a la expectativa Elo del rival,
    ponderados por decaimiento temporal (medio peso cada `halflife_days`).

    Devuelve {code: (atk_mult, leak_mult, games)} con atk/leak ~ 1 al inicio.
    """
    acc = {}   # code -> [w_sum, w*log(scored/exp), w*log(conceded/exp), games]
    for m in history:
        ha = host_bonus if m["home"] in host_codes else 0.0
        lh, la = lambdas_from_elo(elo0[m["home"]], elo0[m["away"]], mu0, ha, rho)
        try:
            age = max((asof - datetime.fromisoformat(m["date"])).days, 0)
        except Exception:
            age = 0
        w = 0.5 ** (age / halflife_days)
        for code, scored, exp_s, conceded, exp_c in (
                (m["home"], m["hs"], lh, m["as"], la),
                (m["away"], m["as"], la, m["hs"], lh)):
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
