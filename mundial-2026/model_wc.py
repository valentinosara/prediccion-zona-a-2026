"""
model_wc.py - Corazon del marcador: Dixon-Coles bivariado + blend mercado<->modelo.

Produce, por partido, la MATRIZ de probabilidad de marcadores P(h,a) con h,a = 0..10.

Por que Dixon-Coles y no Poisson simple: el Poisson independiente subestima los
marcadores bajos (0-0, 1-0, 0-1, 1-1) que en futbol estan correlacionados. DC agrega
una correccion tau(rho) que SOLO toca esas cuatro celdas y arregla ese sesgo. Es el
estandar de la industria para marcadores exactos.

El "centro" de la distribucion son los goles esperados lh (local) y la (visita). De
donde salen esos lambda lo deciden ratings_wc (Elo+forma) y market_wc (cuotas); aca
solo se arma la matriz, se mezclan los lambda (combinacion convexa) y se ANCLAN las
marginales 1X2 de la matriz al mercado de-vigado (el mercado manda en el "quien gana",
el modelo aporta la granularidad del marcador).

Convencion de rho (parametrizacion original Dixon-Coles 1997): rho < 0 sube 0-0 y 1-1
y baja 1-0 y 0-1; un valor tipico es ~ -0.10. No se elige a dedo en produccion: se
puede calibrar por verosimilitud sobre historicos (ver ratings_wc / backtest_wc).
"""
import numpy as np
from math import lgamma

MAXG = 10                                   # marcadores 0..10 por equipo (cubre >99.99%)
_K = np.arange(MAXG + 1)
_LOGFACT = np.array([lgamma(k + 1) for k in _K])

# Mascaras de resultado sobre la matriz 11x11 (local gana / empate / visita gana)
_IH = np.tril(np.ones((MAXG + 1, MAXG + 1), bool), -1)   # h > a
_IX = np.eye(MAXG + 1, dtype=bool)                       # h == a
_IA = np.triu(np.ones((MAXG + 1, MAXG + 1), bool), 1)    # h < a

RHO_DEFAULT = -0.10


def poisson_pmf(lam):
    """Vector PMF Poisson(lam) para 0..MAXG, estable en log."""
    lam = max(float(lam), 1e-6)
    return np.exp(_K * np.log(lam) - lam - _LOGFACT)


def dc_tau(lh, la, rho):
    """Matriz de correccion Dixon-Coles (1 fuera de los marcadores bajos)."""
    t = np.ones((MAXG + 1, MAXG + 1))
    t[0, 0] = 1.0 - lh * la * rho
    t[0, 1] = 1.0 + lh * rho
    t[1, 0] = 1.0 + la * rho
    t[1, 1] = 1.0 - rho
    return t


def dc_matrix(lh, la, rho=RHO_DEFAULT):
    """Matriz P(h,a) 11x11 Dixon-Coles, normalizada a suma 1."""
    P = np.outer(poisson_pmf(lh), poisson_pmf(la)) * dc_tau(lh, la, rho)
    P = np.clip(P, 0.0, None)               # tau puede ser <0 con rho extremo; lo evitamos
    s = P.sum()
    return P / s if s > 0 else P


def outcome_probs(P):
    """(p1, pX, p2) = prob. de local / empate / visita a partir de la matriz."""
    p1 = float(P[_IH].sum()); pX = float(P[_IX].sum()); p2 = float(P[_IA].sum())
    s = p1 + pX + p2
    return (p1 / s, pX / s, p2 / s) if s > 0 else (p1, pX, p2)


def blend_lambdas(lh_mkt, la_mkt, lh_mod, la_mod, w_mkt):
    """Combinacion convexa mercado<->modelo de los goles esperados.
    w_mkt = peso del mercado (1 = solo cuotas, 0 = solo Elo/forma)."""
    return (w_mkt * lh_mkt + (1 - w_mkt) * lh_mod,
            w_mkt * la_mkt + (1 - w_mkt) * la_mod)


def anchor_to_market(P, q1, qX, q2):
    """Re-escala P para que sus marginales 1X2 coincidan EXACTO con el mercado
    de-vigado (q1,qX,q2). Conserva la forma del marcador dentro de cada resultado;
    solo redistribuye masa entre local/empate/visita. Renormaliza al final."""
    p1, pX, p2 = outcome_probs(P)
    Q = P.copy()
    if p1 > 0:
        Q[_IH] *= q1 / p1
    if pX > 0:
        Q[_IX] *= qX / pX
    if p2 > 0:
        Q[_IA] *= q2 / p2
    s = Q.sum()
    return Q / s if s > 0 else Q


def total_goals_prob(P, line=2.5):
    """P(goles totales > line) a partir de la matriz (para chequear O/U)."""
    h = _K[:, None]; a = _K[None, :]
    return float(P[(h + a) > line].sum())


def most_probable_score(P):
    """Modo de la matriz: el marcador mas probable (h,a)."""
    h, a = np.unravel_index(int(np.argmax(P)), P.shape)
    return int(h), int(a)
