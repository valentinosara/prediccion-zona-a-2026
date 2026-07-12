"""
market_wc.py - La senal mas precisa que existe: las CUOTAS de mercado.

La evidencia academica es consistente: las cuotas de las casas (Pinnacle es la mas
"afilada") son el mejor predictor disponible de resultados de futbol (~54% de acierto,
muy dificil de superar). Aca:

  1) DE-VIG (quitar el margen / overround): de las cuotas decimales 1X2 se sacan las
     probabilidades implicitas LIMPIAS de local/empate/visita (q1,qX,q2) normalizando
     los inversos de las cuotas (metodo proporcional).
  2) SUPREMACIA y TOTAL: de la linea de Over/Under sale el total esperado mu = lh+la y
     de la linea de handicap asiatico la supremacia s = lh-la. Combinado con el de-vig
     1X2 se resuelven los lambda de mercado lh=(mu+s)/2, la=(mu-s)/2.

Resolucion numerica: se alterna biseccion en s (para igualar el 'expected score' del
modelo DC al de-vig 1X2) y en mu (para igualar P(over) del modelo a la cuota O/U
de-vigada), hasta converger. Si falta O/U, se fija mu = mu0. Si hay handicap asiatico,
su linea refuerza la supremacia (promedio).
"""
import numpy as np

import model_wc
import ratings_wc


def devig_1x2(o1, oX, o2):
    """Cuotas decimales 1X2 -> probabilidades de-vigadas (q1,qX,q2)."""
    inv = np.array([1.0 / o1, 1.0 / oX, 1.0 / o2])
    inv = inv / inv.sum()
    return float(inv[0]), float(inv[1]), float(inv[2])


def devig_two(over, under):
    """Cuotas decimales de un mercado de dos vias -> prob de-vigadas (p_over, p_under)."""
    inv = np.array([1.0 / over, 1.0 / under])
    inv = inv / inv.sum()
    return float(inv[0]), float(inv[1])


def overround(odds):
    """Margen de la casa (suma de inversos - 1). Solo informativo / control de calidad."""
    return float(sum(1.0 / o for o in odds) - 1.0)


def market_lambdas(q1, qX, q2, q_over=None, mu0=ratings_wc.MU0_DEFAULT,
                   rho=model_wc.RHO_DEFAULT, s_hint=None, line_total=2.5):
    """Resuelve (lh, la) de mercado a partir del de-vig 1X2 y (si hay) O/U.

    q1,qX,q2   probabilidades 1X2 de-vigadas (el mercado manda en el 'quien gana')
    q_over     P(total > line_total) de-vigada del O/U (None -> total fijo mu0)
    s_hint     supremacia sugerida por el handicap asiatico (None si no hay)
    """
    target = q1 + 0.5 * qX                 # 'expected score' que debe reproducir el modelo
    mu = mu0
    s = 0.0
    for _ in range(8):
        # (a) supremacia s que iguala el expected score, dado mu
        lo, hi = -(mu - 0.2), (mu - 0.2)
        for _ in range(34):
            s = 0.5 * (lo + hi)
            if ratings_wc._model_expected_score((mu + s) / 2, (mu - s) / 2, rho) < target:
                lo = s
            else:
                hi = s
        s = 0.5 * (lo + hi)
        # (b) total mu que iguala P(over), dado s
        if q_over is not None:
            lo2, hi2 = 0.6, 5.2
            for _ in range(34):
                mu = 0.5 * (lo2 + hi2)
                p_over = model_wc.total_goals_prob(
                    model_wc.dc_matrix((mu + s) / 2, (mu - s) / 2, rho), line_total)
                if p_over < q_over:
                    lo2 = mu
                else:
                    hi2 = mu
            mu = 0.5 * (lo2 + hi2)
    if s_hint is not None:                 # el handicap asiatico refuerza la supremacia
        s = 0.5 * s + 0.5 * s_hint
    return max((mu + s) / 2, 0.05), max((mu - s) / 2, 0.05), s, mu


def parse_match_odds(odds):
    """Normaliza un bloque de cuotas crudas (dict del fetch/seed) a senales utiles.

    Espera (cualquier subconjunto):
      odds["h2h"]     = [o_local, o_empate, o_visita]   (decimales)
      odds["totals"]  = {"line": 2.5, "over": o, "under": o}
      odds["spreads"] = {"line": -0.75 (linea del LOCAL), "home": o, "away": o}

    Devuelve dict con q1,qX,q2 (de-vig), q_over, s_hint, line_total, bookmaker, margen.
    """
    out = {"ok": False, "bookmaker": odds.get("bookmaker", "mercado")}
    h2h = odds.get("h2h")
    if not h2h or len(h2h) != 3:
        return out
    q1, qX, q2 = devig_1x2(*h2h)
    out.update(ok=True, q1=q1, qX=qX, q2=q2, overround_1x2=overround(h2h))

    tot = odds.get("totals")
    if tot and tot.get("over") and tot.get("under"):
        p_over, _ = devig_two(tot["over"], tot["under"])
        out["q_over"] = p_over
        out["line_total"] = float(tot.get("line", 2.5))
    else:
        out["q_over"] = None
        out["line_total"] = 2.5

    spr = odds.get("spreads")
    if spr and spr.get("line") is not None:
        # Linea del local (negativa = favorito). La supremacia ~ -linea, ajustada por el
        # sesgo de las cuotas del handicap (si la visita paga mas, el local es aun mejor).
        line = float(spr["line"])
        s_hint = -line
        if spr.get("home") and spr.get("away"):
            s_hint += 0.25 * np.log(spr["away"] / spr["home"])
        out["s_hint"] = float(s_hint)
    else:
        out["s_hint"] = None
    return out
