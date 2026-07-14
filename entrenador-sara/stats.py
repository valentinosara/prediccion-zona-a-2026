"""
stats.py - Calculo puro (stdlib) de las 7 estadisticas de gestion de Juan
Sara como head coach, a partir de data/matches.json + data/spells.json.

Modelo de puntos: SIEMPRE 3-1-0 (V-E-D), parejo para TODOS los partidos, sin
excepcion por competicion (asi lo pide la spec). Nota deliberada: en la
corrida completa (ver apply-progress) se detecto que el ppg_tm que muestra
el perfil de Transfermarkt para la gestion i=2 (Dep. Maipu, 2024-02-21 ->
2025-06-23) parece EXCLUIR el punto de un empate de Copa Argentina que nuestro
pipeline recupero via el bug de grilla "-:-" (ver ingest.py): 74/55=1.3545
coincide EXACTO con el ppg_tm=1.35 de TM si se resta ese punto, mientras que
nuestro calculo 3-1-0 uniforme da 75/55=1.3636. Esto es intencional: no
adoptamos en silencio la convencion (aparente, no confirmada como regla
general de TM) de excluir esa competicion del PPG. La diferencia de
centesimas en ESE caso puntual es esperada y ya esta documentada, no un bug
de este modulo - ver `print_sanity_gate`.

Ejes de agrupacion (no confundir):
- "vs_clubs" / "vs_coaches": rivales que Sara ENFRENTO (el otro equipo/DT en
  cada partido). MET-1, MET-2 y la mitad "por club" de MET-4.
- "spells" / "own_clubs": los 4 clubes que Sara MISMA dirigio (sus propias
  gestiones). MET-3, MET-7 y la mitad "por club" de MET-6.

Salida: data/stats.json, consumido por gen_html.py.
"""
import collections
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
MATCHES_PATH = os.path.join(DATA_DIR, "matches.json")
SPELLS_PATH = os.path.join(DATA_DIR, "spells.json")
STATS_PATH = os.path.join(DATA_DIR, "stats.json")

POINTS = {"W": 3, "D": 1, "L": 0}


# ---------------------------------------------------------------------
# Helpers basicos
# ---------------------------------------------------------------------
def _pts(result):
    return POINTS.get(result, 0)


def _pct(points, possible):
    """Puntos obtenidos / posibles, como % (1 decimal). None (NO 0%) si
    `possible` es 0 - la spec pide explicitamente "N/A" para un split sin
    partidos (MET-4), nunca un 0% enganoso ni un error de division."""
    if not possible:
        return None
    return round(points / possible * 100, 1)


def _ppp(points, played):
    """Puntos por partido (2 decimales, mismo formato que ppg_tm de TM).
    None si no se jugo ningun partido (no deberia pasar sobre datos reales
    para ninguna fila expuesta, pero evita division por cero)."""
    if not played:
        return None
    return round(points / played, 2)


def _bucket():
    return {"pj": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0}


def _add_match(bucket, m):
    bucket["pj"] += 1
    res = m["result"]
    if res == "W":
        bucket["w"] += 1
    elif res == "D":
        bucket["d"] += 1
    elif res == "L":
        bucket["l"] += 1
    bucket["gf"] += m["gf"]
    bucket["ga"] += m["ga"]
    bucket["pts"] += _pts(res)


def _finalize(bucket):
    """Agrega ppp + efectividad% al bucket ya acumulado (in-place; devuelve
    el mismo dict para poder encadenar en una sola expresion)."""
    bucket["ppp"] = _ppp(bucket["pts"], bucket["pj"])
    bucket["effectiveness_pct"] = _pct(bucket["pts"], bucket["pj"] * 3)
    return bucket


def load_data(matches_path=MATCHES_PATH, spells_path=SPELLS_PATH):
    with open(matches_path, encoding="utf-8") as f:
        matches = json.load(f)
    with open(spells_path, encoding="utf-8") as f:
        spells = json.load(f)
    return matches, spells


# ---------------------------------------------------------------------
# MET-7 (general info) + MET-3 "per spell": una fila por gestion, y el
# total de toda la carrera.
# ---------------------------------------------------------------------
def build_spells_info(matches, spells):
    """Una fila por gestion (7), en orden CRONOLOGICO por fecha de alta:
    club, appointed, until (None = vigente), PJ/V-E-D/GF-GC/PPP/efectividad%.
    Satisface MET-7 (info general por gestion) y el "ALSO keep per-spell"
    explicito de MET-3 (la efectividad% de cada fila es exactamente
    ppp/3*100, ya calculada aqui - no hace falta una estructura aparte)."""
    by_spell = collections.defaultdict(_bucket)
    for m in matches:
        _add_match(by_spell[m["i"]], m)

    rows = []
    for sp in spells:
        row = {
            "i": sp["i"],
            "club": sp["club"],
            "appointed": sp["appointed"],
            "until": sp["until"],
            **_finalize(by_spell[sp["i"]]),
            "matches_tm": sp["matches_tm"],
            "ppg_tm": sp["ppg_tm"],
        }
        rows.append(row)
    rows.sort(key=lambda r: r["appointed"])
    return rows


def build_career_totals(matches):
    """MET-7: "+ un total de todas las gestiones" (carrera completa)."""
    b = _bucket()
    for m in matches:
        _add_match(b, m)
    return _finalize(b)


# ---------------------------------------------------------------------
# MET-3 (primario): efectividad por CLUB PROPIO de Sara, fusionando sus
# gestiones en el mismo club (Ferro x2, Estudiantes x2, Dep. Maipu x2,
# Tigre x1) en una sola fila por club.
# ---------------------------------------------------------------------
def build_own_clubs(matches, spells):
    spell_indices = collections.defaultdict(list)
    for sp in spells:
        spell_indices[sp["club"]].append(sp["i"])

    by_club = collections.defaultdict(_bucket)
    for m in matches:
        _add_match(by_club[m["club"]], m)

    out = {}
    for club, bucket in by_club.items():
        out[club] = {
            **_finalize(bucket),
            "spell_indices": sorted(spell_indices.get(club, [])),
        }
    return out


# ---------------------------------------------------------------------
# MET-1 + pieza "per club" de MET-4: rendimiento vs cada CLUB RIVAL
# enfrentado (no el propio de Sara), con split local/visitante.
# ---------------------------------------------------------------------
def build_vs_clubs(matches):
    """Se agrupa por `opponent_verein_id` (id estable), NO por el string
    `opponent`: mismo criterio de identidad que ya usa el resto del
    pipeline (BY_VEREIN_ID en clubs.py, SARA_TRAINER_ID en parse.py), para
    no fragmentar el mismo club rival en dos filas si TM alguna vez varia
    acentos/espacios del nombre entre paginas distintas. `opponent_verein_id`
    esta presente en el 100% de los 156 partidos (verificado), asi que esto
    no deja ningun partido sin agrupar."""
    by_id = collections.defaultdict(lambda: {
        "total": _bucket(), "home": _bucket(), "away": _bucket(),
        "names": collections.Counter(),
    })
    for m in matches:
        entry = by_id[m["opponent_verein_id"]]
        _add_match(entry["total"], m)
        _add_match(entry["home"] if m["home_away"] == "H" else entry["away"], m)
        entry["names"][m["opponent"]] += 1

    rows = []
    for vid, entry in by_id.items():
        name = entry["names"].most_common(1)[0][0]
        rows.append({
            "verein_id": vid,
            "name": name,
            **_finalize(entry["total"]),
            # home/away: cada uno lleva su propio ppp + effectiveness_pct
            # (este ultimo ES el "% de puntos como local/visitante" de
            # MET-4 para este club rival puntual; None cuando ese lado
            # tiene 0 partidos - MET-4 pide "N/A", nunca 0%, ver `_pct`).
            "home": _finalize(entry["home"]),
            "away": _finalize(entry["away"]),
        })
    rows.sort(key=lambda r: (-r["pj"], r["name"]))
    return rows


# ---------------------------------------------------------------------
# MET-4 (global): TODOS los partidos separados en local/visitante, sin
# filtrar por club rival.
# ---------------------------------------------------------------------
def build_home_away_global(matches):
    home, away = _bucket(), _bucket()
    for m in matches:
        _add_match(home if m["home_away"] == "H" else away, m)
    return {"home": _finalize(home), "away": _finalize(away)}


# ---------------------------------------------------------------------
# MET-2: historial vs cada DT rival.
# ---------------------------------------------------------------------
def _coach_match_brief(matches_sorted):
    """Detalle partido a partido para la fila expandible de un DT rival
    (gen_html.py): una entrada por enfrentamiento, ya en orden cronologico,
    con exactamente los campos que la tabla necesita. Deliberadamente
    SEPARADO de `_run_brief` (usado por las rachas, MET-6): consumidor
    distinto, forma garantizada distinta; reusar `_run_brief` aca
    arriesgaria cambiar sin necesidad la forma ya verificada de streaks en
    stats.json."""
    return [{
        "date": m["date"], "club": m["club"], "opponent": m["opponent"],
        "home_away": m["home_away"], "result": m["result"],
        "gf": m["gf"], "ga": m["ga"], "competition": m["competition"],
    } for m in matches_sorted]


def build_vs_coaches(matches):
    """PG-PE-PP/PPG por DT rival, agrupado por `opponent_coach_id` (mismo
    criterio de identidad estable que build_vs_clubs). Los partidos con DT
    rival no identificado en la fuente (1 de 156 en la corrida completa:
    Ferro vs Dep. Madryn, 2023-03-17, ver apply-progress) quedan FUERA de
    esta lista - no hay ningun DT concreto al que atribuirselos - pero
    siguen contando normalmente en vs_clubs / general / streaks. Por eso el
    total de PJ sumado aca puede dar 155, no 156; es esperado, no un bug.
    (Mismo criterio aplica al nuevo campo `matches`: 155 filas de detalle
    en total, NO 156 - el unico partido sin DT rival identificado tampoco
    tiene fila de detalle en ningun lado, por la misma razon.)

    Orden explicitamente pedido: por partidos jugados (desc, "mas
    enfrentado" primero), PPP como desempate (desc). Cada fila incluye
    ademas `matches`: el detalle partido a partido contra ese DT rival, en
    orden cronologico (filas expandibles en gen_html.py). Los campos
    agregados (pj/w/d/l/gf/ga/pts/ppp/effectiveness_pct) quedan sin tocar."""
    by_id = collections.defaultdict(lambda: {
        "b": _bucket(), "names": collections.Counter(), "matches": [],
    })
    for m in matches:
        if m["opponent_coach_id"] is None:
            continue
        entry = by_id[m["opponent_coach_id"]]
        _add_match(entry["b"], m)
        entry["names"][m["opponent_coach"]] += 1
        entry["matches"].append(m)

    rows = []
    for cid, entry in by_id.items():
        name = entry["names"].most_common(1)[0][0]
        rows.append({
            "coach_id": cid, "name": name, **_finalize(entry["b"]),
            "matches": _coach_match_brief(_sorted_chrono(entry["matches"])),
        })
    rows.sort(key=lambda r: (-r["pj"], -(r["ppp"] or 0), r["name"]))
    return rows


# ---------------------------------------------------------------------
# MET-5: goleadores.
# ---------------------------------------------------------------------
def _scorer_counts(matches):
    """Counter jugador->goles: solo goles DE SARA (team=="sara"), excluye
    en-contra (kind=="og", ING-2) e INCLUYE penales (kind=="pen" cuenta
    igual que cualquier gol, ING-3). Los goles sin goleador identificable
    (player is None, ING-2) se excluyen de esta lista: la suma de esta
    lista puede entonces ser MENOR al GF real del equipo en esos partidos -
    eso es esperado (la fuente no siempre identifica al goleador), nunca se
    inventa un nombre para completar la cuenta."""
    c = collections.Counter()
    for m in matches:
        for s in m["scorers"]:
            if s["team"] != "sara" or s["kind"] == "og" or not s["player"]:
                continue
            c[s["player"]] += 1
    return c


def _ranked_scorer_list(counts):
    return sorted(
        ({"player": p, "goals": g} for p, g in counts.items()),
        key=lambda r: (-r["goals"], r["player"]),
    )


def build_scorers(matches, spells):
    """Lista por gestion (per_spell) + UNA lista agregada de toda la
    carrera (aggregate). Un jugador que suma goles en dos gestiones del
    MISMO club (ej. Ferro i=0 y Ferro i=5) o incluso en CLUBES distintos se
    fusiona en una sola fila en `aggregate` (se agrupa por nombre de
    texto, no hay id de jugador estable en la fuente - ver parse.py: esto
    es exactamente lo que pide el escenario MET-5 de "mismo jugador en dos
    gestiones del mismo club"). Limitacion conocida y documentada: dos
    jugadores reales distintos que compartieran EXACTAMENTE el mismo
    string de nombre (caso extremo, no observado en los 156 partidos) se
    fusionarian en una sola fila - limitacion de la fuente (sin player id),
    no de este calculo."""
    by_spell = collections.defaultdict(list)
    for m in matches:
        by_spell[m["i"]].append(m)

    per_spell = []
    for sp in spells:
        counts = _scorer_counts(by_spell.get(sp["i"], []))
        per_spell.append({
            "i": sp["i"],
            "club": sp["club"],
            "scorers": _ranked_scorer_list(counts),
        })
    per_spell.sort(key=lambda r: r["i"])

    aggregate = _ranked_scorer_list(_scorer_counts(matches))
    return {"per_spell": per_spell, "aggregate": aggregate}


# ---------------------------------------------------------------------
# MET-6: rachas.
# ---------------------------------------------------------------------
def _sorted_chrono(matches):
    """Orden cronologico estable: fecha ISO (ya ordenable como string) y,
    ante un empate de fecha (caso raro, dos partidos el mismo dia), el
    spielbericht_id como desempate secundario - no cambia el resultado en
    la practica, solo hace el orden deterministico."""
    return sorted(matches, key=lambda m: (m["date"], m["spielbericht_id"]))


def _longest_streak(matches_sorted, want_result):
    """Racha mas larga de `want_result` ("W" o "L"); CUALQUIER otro
    resultado (incluido el empate) la corta a 0, MET-6. Ante un empate de
    longitud, conserva la PRIMERA ocurrencia cronologica (mismo criterio
    que rachas-primera-nacional/analyze.py::longest_win_streak)."""
    best_len, best_run, cur = 0, [], []
    for m in matches_sorted:
        if m["result"] == want_result:
            cur.append(m)
            if len(cur) > best_len:
                best_len, best_run = len(cur), list(cur)
        else:
            cur = []
    return best_len, best_run


def _run_brief(run):
    return [{
        "date": m["date"], "club": m["club"], "opponent": m["opponent"],
        "home_away": m["home_away"], "gf": m["gf"], "ga": m["ga"],
        "competition": m["competition"],
    } for m in run]


def _streak_summary(matches_sorted):
    win_len, win_run = _longest_streak(matches_sorted, "W")
    loss_len, loss_run = _longest_streak(matches_sorted, "L")
    return {
        "best_win": {"len": win_len, "matches": _run_brief(win_run)},
        "best_loss": {"len": loss_len, "matches": _run_brief(loss_run)},
    }


def build_streaks(matches):
    """MET-6.

    - `global`: TODA la carrera en una sola secuencia cronologica, SIN
      cortar en un cambio de club/gestion - asi lo pide la spec
      explicitamente ("globally (all spells, chronological)"). En teoria
      una racha global puede entonces empezar en un club y seguir en otro
      si las fechas quedan pegadas entre el fin de una gestion y el inicio
      de la siguiente; queda transparente en el detalle de "matches" de
      cada racha (incluye el campo `club` de cada partido).

    - `per_club`: fusiona las gestiones de un MISMO club propio de Sara
      (ej. Ferro i=0 + i=5) en una sola secuencia cronologica "puenteada"
      entre ambas. ESTO ES UNA DECISION DE PRODUCTO CUESTIONABLE, dejada
      asi a pedido explicito del usuario: puede encadenar una racha que
      cruza el hueco de tiempo entre dos gestiones separadas en ese club
      (ej. Ferro tuvo una gestion 2022-10-24 -> 2023-04-03 y otra recien
      desde 2026-04-14: casi 3 anios sin dirigir ahi en el medio). Una
      alternativa igual de razonable seria cortar la racha en cada limite
      de gestion (per-spell en vez de per-club). Si se prefiere ese
      comportamiento: iterar por `i` (spell index) en vez de por `club`
      en el loop de abajo.
    """
    global_summary = _streak_summary(_sorted_chrono(matches))

    by_club = collections.defaultdict(list)
    for m in matches:
        by_club[m["club"]].append(m)
    per_club = {
        club: _streak_summary(_sorted_chrono(ms))
        for club, ms in by_club.items()
    }

    return {"global": global_summary, "per_club": per_club}


# ---------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------
def compute_all(matches, spells):
    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "career": build_career_totals(matches),
        "spells": build_spells_info(matches, spells),
        "own_clubs": build_own_clubs(matches, spells),
        "vs_clubs": build_vs_clubs(matches),
        "vs_coaches": build_vs_coaches(matches),
        "home_away_global": build_home_away_global(matches),
        "scorers": build_scorers(matches, spells),
        "streaks": build_streaks(matches),
    }


def print_sanity_gate(spells_info):
    """Chequeo de consistencia (task 5.8): compara PJ/PPP calculados contra
    los valores que el perfil de Transfermarkt reporta (spells.json,
    matches_tm/ppg_tm) - mismo espiritu que build.py en
    rachas-primera-nacional. Un mismatch de PJ (no solo de PPP) SI es señal
    de un problema real de ingesta; una diferencia de centesimas en PPP
    para la gestion i=2 (Dep. Maipu) es ESPERADA (ver docstring del modulo)."""
    print("\nSanity gate stats.py (PJ/PPP calculado vs perfil TM):")
    for row in spells_info:
        pj_ok = "OK" if row["pj"] == row["matches_tm"] else "MISMATCH"
        line = (f"  i={row['i']} {row['club']:<14} PJ {row['pj']:>3}/{row['matches_tm']:>3} "
                f"[{pj_ok}]  PPP {row['ppp']:.4f} vs ppg_tm {row['ppg_tm']:.2f}")
        if row["ppp"] is not None and row["ppg_tm"] is not None:
            diff = abs(row["ppp"] - row["ppg_tm"])
            if diff >= 0.005:
                line += f"  (diff {diff:.4f})"
        print(line)


def _write_json_atomic(path, data):
    """Escritura atomica (archivo temporal + os.replace), mismo patron que
    ingest.py: una corrida interrumpida a mitad de escritura no trunca el
    archivo real existente."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def run(matches_path=MATCHES_PATH, spells_path=SPELLS_PATH, out_path=STATS_PATH,
        verbose=True):
    matches, spells = load_data(matches_path, spells_path)
    stats = compute_all(matches, spells)
    if verbose:
        print(f"stats.py: {len(matches)} partidos, {len(spells)} gestiones cargadas.")
        print_sanity_gate(stats["spells"])
    if out_path:
        _write_json_atomic(out_path, stats)
        if verbose:
            print(f"\nstats escrito en {out_path}")
    return stats


if __name__ == "__main__":
    run()
