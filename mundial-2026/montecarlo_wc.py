"""
montecarlo_wc.py - Simulaciones Monte Carlo por partido.

Se muestrean N marcadores de la matriz P(h,a) (50.000 por defecto) para obtener
probabilidades robustas, la distribucion de goles y una medida de confianza. La matriz
ya da las probabilidades EXACTAS; el Monte Carlo confirma su robustez y habilita
intervalos y, opcionalmente, simular el torneo completo (modulo de podio, seccion 9).

Patron vectorizado (sin loops por simulacion), al estilo de montecarlo() en
predict_zonaA.py.
"""
import numpy as np


def simulate_match(P, n=50000, seed=7):
    """Muestrea n marcadores de P y devuelve probabilidades e intervalos empiricos."""
    flat = P.ravel().astype(float)
    flat = flat / flat.sum()
    rng = np.random.default_rng(seed)
    idx = rng.choice(flat.size, size=n, p=flat)
    h, a = np.divmod(idx, P.shape[1])
    return {
        "p1": float(np.mean(h > a)),
        "pX": float(np.mean(h == a)),
        "p2": float(np.mean(h < a)),
        "gh_mean": float(h.mean()),
        "ga_mean": float(a.mean()),
        "gh_p90": int(np.percentile(h, 90)),
        "ga_p90": int(np.percentile(a, 90)),
        "n": n,
    }


def confidence(p1, pX, p2, gap):
    """Nivel de confianza de la jugada, sobre todo por la CLARIDAD del 'quien gana'
    (entropia normalizada del 1X2). La brecha de puntos esperados entre la 1a y la 2a
    opcion del prode (gap) solo degrada 'alta'->'media' cuando el marcador en si es muy
    ambiguo. Devuelve (label, entropia 0..1)."""
    ps = np.array([p1, pX, p2])
    ps = ps[ps > 0]
    H = float(-(ps * np.log(ps)).sum() / np.log(3))      # 0 (favorito claro) .. 1 (parejo)
    # La claridad de la JUGADA la define sobre todo cuan marcado es el favorito (entropia).
    # La brecha de E[pts] (gap) entre marcadores suele ser chica y no degrada el favorito;
    # solo se usa para no marcar "alta" cuando ademas el marcador es practicamente un empate
    # tecnico de candidatos (gap casi nulo).
    if H < 0.83 and gap >= 0.05:
        label = "alta"
    elif H > 0.95:
        label = "baja"
    else:
        label = "media"
    return label, round(H, 3)
