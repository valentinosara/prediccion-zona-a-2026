"""
prode_wc.py - El OPTIMIZADOR del prode (nucleo, seccion 4 del prompt).

El prode reparte puntos por "casi acertar" (misma diferencia, ganador, un equipo), asi
que el marcador optimo para PUNTUAR no es necesariamente el mas probable. Para cada
partido, dada la matriz P(h,a), se elige la prediccion (ph,pa) que MAXIMIZA los puntos
esperados sobre toda la distribucion de marcadores:

    E[pts | predigo (ph,pa)] = sum_{ah,aa} P(ah,aa) * puntos((ph,pa),(ah,aa))

Implementacion eficiente: se precomputa una vez el tensor Pts[ph,pa,ah,aa] (7x7x11x11)
y E[pts] = tensordot(Pts, P) con numpy -> argmax.

La tabla de puntaje (exacta, seccion 1 del prompt):
  12  marcador exacto
   8  empate correcto, o ganador correcto + misma diferencia de goles
   5  ganador correcto sin acertar la diferencia
   2  goles exactos de exactamente UNO de los dos equipos
   0  incorrecto  (se toma SIEMPRE el mayor que corresponda, no se acumulan)
"""
import numpy as np

PMAX = 6                # marcadores candidatos a predecir: 0..6 por equipo
RMAX = 10               # marcadores reales considerados: 0..10 (= MAXG del modelo)


def puntos(pred, real):
    """Puntos del prode de predecir `pred`=(ph,pa) si el resultado real es `real`=(ah,aa)."""
    ph, pa = pred
    ah, aa = real
    if ph == ah and pa == aa:                       # marcador exacto
        return 12
    pred_dir = np.sign(ph - pa)
    real_dir = np.sign(ah - aa)
    same_dir = (pred_dir == real_dir)
    same_diff = ((ph - pa) == (ah - aa))
    # 8: empate correcto (ambos empate) o ganador correcto + misma diferencia
    if same_dir and (real_dir == 0 or same_diff):
        return 8
    # 5: ganador correcto sin la diferencia (real decisivo y acerte el lado)
    if same_dir:
        return 5
    # 2: goles exactos de exactamente uno de los dos equipos
    if (ph == ah) ^ (pa == aa):
        return 2
    return 0


def _build_pts_tensor():
    """Pts[ph,pa,ah,aa] precomputado una sola vez."""
    Pts = np.zeros((PMAX + 1, PMAX + 1, RMAX + 1, RMAX + 1))
    for ph in range(PMAX + 1):
        for pa in range(PMAX + 1):
            for ah in range(RMAX + 1):
                for aa in range(RMAX + 1):
                    Pts[ph, pa, ah, aa] = puntos((ph, pa), (ah, aa))
    return Pts


PTS = _build_pts_tensor()


def expected_points(P):
    """Matriz E[pts] 7x7: puntos esperados de cada prediccion candidata (ph,pa)."""
    return np.tensordot(PTS, P[:RMAX + 1, :RMAX + 1], axes=([2, 3], [0, 1]))


def optimize(P, top=5):
    """Devuelve la jugada del prode para la matriz P.

    {
      rec: (ph,pa),         marcador recomendado (max puntos esperados)  -> la jugada
      ev_rec: float,        puntos esperados de la recomendacion
      gap: float,           brecha de E[pts] entre la 1a y la 2a opcion (cuan clara es)
      top: [ {score,(h,a) prob, ev}, ... top-N por puntos esperados ],
    }
    """
    E = expected_points(P)
    order = np.argsort(E, axis=None)[::-1]
    best = np.unravel_index(int(order[0]), E.shape)
    second_ev = float(E.flat[int(order[1])])
    cands = []
    for idx in order[:top]:
        ph, pa = np.unravel_index(int(idx), E.shape)
        prob = float(P[ph, pa]) if (ph <= RMAX and pa <= RMAX) else 0.0
        cands.append({"score": [int(ph), int(pa)], "prob": prob, "ev": float(E[ph, pa])})
    return {
        "rec": [int(best[0]), int(best[1])],
        "ev_rec": float(E[best]),
        "gap": float(E[best] - second_ev),
        "top": cands,
    }
