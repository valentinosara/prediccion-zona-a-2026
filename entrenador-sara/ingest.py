"""
ingest.py - Ensamblador: gestiones (Source A) -> fixtures por temporada
(Source B) -> filtro por rango de fechas de la gestion -> reportes de cada
partido filtrado (Source C) -> data/spells.json + data/matches.json.

Rate-limit: se apoya enteramente en fetch.Fetcher (cache en disco + jitter
2.5-5s + backoff exponencial en cada .get() en vivo); ingest.py no agrega
ninguna espera propia.

Robustez (endurecido antes de la corrida completa de ~156 partidos):
- Cada fetch en vivo (perfil/fixture/reporte) pasa un `validator` de
  contenido a Fetcher.get(): una pagina de bot-detection/interstitial
  servida con status 200 no se acepta ni se cachea, se trata como un fetch
  fallido mas (reintenta, despues -1).
- Fixture y reporte fallidos se reintentan UNA vez mas; si siguen fallando
  quedan en un ledger de fallos que se imprime al final del resumen (nunca
  se pierden en silencio).
- Antes de escribir spells.json/matches.json: si no se resolvio ninguna
  gestion, o el total de partidos ensamblados (para las gestiones
  efectivamente procesadas) cae por debajo de MIN_COMPLETENESS_RATIO de lo
  que TM reporta (matches_tm), la corrida ABORTA sin escribir (ver run()).
- Si una gestion quedo corta de partidos Y tuvo fallos reales de fetch (no
  solo filtrado legitimo por fecha/competicion), run() sale con error no-cero
  aunque el umbral agregado anterior no se haya cruzado.
- La escritura de ambos JSON es atomica (archivo temporal + os.replace): una
  corrida interrumpida a mitad de escritura no trunca el archivo real.
- Bug de grilla "-:-" confirmado en vivo (corrida completa, Dep. Maipu vs
  Juventud Unida SL, Copa Argentina 2024-04-18, reporte 4244651): la grilla
  de Source B a veces muestra "-:-" (played=False) para un partido que SI
  se jugo y tiene reporte completo (DT rival + goleadores identificados).
  Por eso, ademas del filtro normal, los partidos con played=False pero en
  rango y con fecha pasada se intentan igual como candidatos: si su reporte
  prueba contenido real (ver `_report_has_content`), se incluyen con gf/ga
  derivados de los goleadores del reporte (ver `_score_from_scorers`), no
  de la grilla. Si el reporte tambien esta vacio o no existe, se descartan
  sin contarlos como fallo (partido genuinamente no jugado/futuro).
- Fase 7 (re-run desde update.py): por default (`force_refresh_current=True`
  en run()) se fuerza un re-fetch en vivo SOLO del perfil y de la pagina de
  fixture del saison_id en curso de la gestion vigente (`until is None`) en
  CADA corrida - ver docstrings de `fetch_spells` / `build_matches_for_spell`.
  Esto es lo que permite que una corrida futura de `update.py` recoja
  partidos nuevos de Ferro sin re-scrapear las ~155 paginas ya cacheadas de
  gestiones cerradas. `run(force_refresh_current=False)` reproduce el
  comportamiento 100% cache-backed de la corrida inicial.

Uso normal (corrida completa, 7 gestiones / ~156 partidos):
    python ingest.py

Uso para probar UNA sola gestion sin tocar los JSON finales (ver run()):
    import ingest
    ingest.run(only_spell_index=0, matches_out="data/_trial_algo.json")
"""
import datetime
import json
import os
import sys

import clubs
import parse
from fetch import Fetcher

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
SPELLS_PATH = os.path.join(DATA_DIR, "spells.json")
MATCHES_PATH = os.path.join(DATA_DIR, "matches.json")

PROFILE_URL = "https://www.transfermarkt.us/juan-sara/profil/trainer/94335"

# Chequeo de integridad de run(): si el total de partidos ensamblados (solo
# para las gestiones efectivamente procesadas) cae por debajo de esta
# fraccion de matches_tm, abortar sin escribir. Nunca pisar spells.json/
# matches.json con datos colapsados/truncados.
MIN_COMPLETENESS_RATIO = 0.90


def fixture_url(slug, verein_id, saison_id):
    return f"https://www.transfermarkt.us/{slug}/spielplandatum/verein/{verein_id}/saison_id/{saison_id}"


def report_url(report_id):
    return f"https://www.transfermarkt.us/spielbericht/index/spielbericht/{report_id}"


# ---- Validadores de contenido por tipo de pagina ----------------------
# Fix critico: nunca aceptar (ni cachear) una pagina de bot-detection o
# interstitial servida con status 200 y body largo como si fuera la pagina
# real. Cada uno chequea el marcador minimo que SIEMPRE esta presente en la
# pagina real correspondiente (confirmado contra el cache existente).
def _is_profile_page(html):
    """Fuente A: el perfil real se referencia a si mismo (canonical/og:url)
    con la URL del entrenador."""
    return "/profil/trainer/94335" in html


def _make_fixture_validator(verein_id):
    """Fuente B: al menos un link de reporte de partido, o - fallback para
    una temporada sin partidos jugados/reportados todavia - al menos una
    referencia al verein_id de ESTE club (una pagina de bot-detection no
    menciona el club en absoluto)."""
    marker = f"/verein/{verein_id}"

    def _validate(html):
        return "/spielbericht/index/spielbericht/" in html or marker in html
    return _validate


def _is_report_page(html):
    """Fuente C: la tabla de alineaciones/banco (bench-table) siempre esta
    presente en un reporte real."""
    return "bench-table" in html


def fetch_spells(fetcher, force=False):
    """Fuente A: perfil de Sara -> las 7 gestiones como head coach.

    `force=True` (usado por update.py en cada corrida, Fase 7): ignora un
    cache previo del perfil y siempre pide la version en vivo. Es la unica
    forma de detectar, en una corrida futura, un cambio de `until` en la
    gestion vigente o una gestion nueva (ej. Sara deja Ferro) - el perfil
    es una sola pagina liviana, el costo de refrescarla siempre es minimo."""
    html, cached, status = fetcher.get(PROFILE_URL, validator=_is_profile_page, force=force)
    if not html:
        raise RuntimeError(f"No se pudo obtener el perfil de Sara (status={status})")
    return parse.parse_spells(html)


def _result(gf, ga):
    if gf is None or ga is None:
        return None
    if gf > ga:
        return "W"
    if gf < ga:
        return "L"
    return "D"


def _fetch_fixture_with_retry(fetcher, slug, verein_id, saison_id, verbose, force=False):
    """Fixture de una saison_id, con un reintento extra propio de ingest.py
    (encima de los reintentos internos de Fetcher.get()) antes de darla por
    fallida de verdad.

    `force=True`: ignora el cache existente para ESTA pagina de fixture
    puntual (ver `build_matches_for_spell` - solo se usa para el saison_id
    actualmente en curso de la gestion vigente; el resto del cache, de
    temporadas ya cerradas, nunca se fuerza)."""
    validator = _make_fixture_validator(verein_id)
    url = fixture_url(slug, verein_id, saison_id)
    html, cached, status = fetcher.get(url, validator=validator, force=force)
    if html:
        return html, status
    if verbose:
        print(f"    [WARN] fixture saison_id={saison_id} fallo (status={status}); reintentando una vez...")
    html, cached, status = fetcher.get(url, validator=validator, force=force)
    if not html and verbose:
        print(f"    [ERROR] fixture saison_id={saison_id} fallo tras reintento (status={status})")
    return html, status


def _fetch_report_with_retry(fetcher, spielbericht_id, verbose):
    """Idem para el reporte de un partido puntual."""
    url = report_url(spielbericht_id)
    html, cached, status = fetcher.get(url, validator=_is_report_page)
    if html:
        return html, status
    if verbose:
        print(f"    [WARN] reporte {spielbericht_id} fallo (status={status}); reintentando una vez...")
    html, cached, status = fetcher.get(url, validator=_is_report_page)
    if not html and verbose:
        print(f"    [ERROR] reporte {spielbericht_id} fallo tras reintento (status={status})")
    return html, status


def _report_has_content(report):
    """True si el reporte YA PARSEADO prueba que el partido se jugo de
    verdad (no es un stub/placeholder): DT rival identificado, O al menos
    un goleador. Un 0:0 real SI tiene DT rival identificado aunque no haya
    goleadores - por eso no alcanza con mirar solo `scorers` (un stub
    vacio no tiene ninguna de las dos cosas)."""
    return report["opponent_coach"] is not None or bool(report["scorers"])


def _score_from_scorers(scorers):
    """gf/ga derivados de la lista de goleadores YA resuelta por
    parse_report (team="sara"|"opp" - ya cubre en-contra y penales con el
    mismo criterio que usaria la grilla: el gol cuenta para el equipo
    BENEFICIADO). Fallback usado SOLO cuando la grilla muestra "-:-" pero
    el reporte prueba que el partido si se jugo (ver `_report_has_content`,
    bug de grilla documentado en el docstring del modulo)."""
    gf = sum(1 for s in scorers if s["team"] == "sara")
    ga = sum(1 for s in scorers if s["team"] == "opp")
    return gf, ga


def build_matches_for_spell(spell, spell_index, club_info, fetcher, verbose=True,
                             force_current=False):
    """Arma los registros de partido de UNA gestion (spell):

    0. `force_current=True` (Fase 7, solo cuando `spell["until"] is None` -
       la gestion vigente): fuerza un re-fetch en vivo de la pagina de
       fixture del saison_id ACTUALMENTE en curso (`parse.current_saison_id()`),
       ignorando su cache. Las demas saison_ids de la MISMA gestion (si
       hubiera, ej. una gestion vigente que ya lleva mas de un anio
       calendario) y todas las gestiones ya cerradas nunca se fuerzan: un
       partido ya jugado y reporteado no cambia retroactivamente, forzar
       ese cache seria trabajo en vano. Esto es lo que permite que
       update.py sea "re-runnable" de verdad (recoge partidos nuevos de
       Ferro) sin re-scrapear las ~155 paginas historicas ya cacheadas.
    1. Fixture de CADA saison_id que toca la gestion (Source B).
    2. Union por spielbericht_id (una gestion de 2 temporadas puede repetir
       partidos si TM lista el mismo id en ambas paginas; el dict dedup por
       id evita contarlos dos veces).
    3. Filtro a los partidos JUGADOS dentro de [appointed, until] (ING-1):
       el fixture de un club tambien lista partidos de OTROS DTs, por eso
       hace falta este filtro incluso teniendo ya el saison_id correcto.
       Ademas: los partidos con played=False (segun la grilla) pero en
       rango y con fecha <= hoy se agregan como CANDIDATOS "-:-" (ver bug
       documentado en el docstring del modulo) - se les intenta el reporte
       igual, y solo se confirman como jugados si el reporte prueba
       contenido real.
    4. Fetch del reporte de cada partido filtrado y de cada candidato
       "-:-" (Source C) -> DT rival + goleadores (+ gf/ga derivados para
       los candidatos "-:-" confirmados).

    Devuelve (matches, failed_saison_ids, failed_report_ids,
    recovered_dashdash_ids): los primeros dos ledgers de fallos nunca se
    pierden en silencio (run() los junta en el resumen final y decide si
    la corrida debe salir con error); `recovered_dashdash_ids` son los
    spielbericht_id que la grilla marcaba como no jugados pero se
    confirmaron y agregaron via el reporte (informativo - cuenta el
    impacto real del bug de grilla, no afecta pass/fail de la corrida).
    """
    current_saison = parse.current_saison_id()
    seen_ids = {}
    failed_saison_ids = []
    for saison_id in spell["saison_ids"]:
        force = force_current and saison_id == current_saison
        html, status = _fetch_fixture_with_retry(
            fetcher, club_info["slug"], club_info["verein_id"], saison_id, verbose,
            force=force)
        if not html:
            failed_saison_ids.append(saison_id)
            continue
        for m in parse.parse_fixture(html):
            seen_ids[m["spielbericht_id"]] = m

    appointed = spell["appointed"]
    until = spell["until"]
    # Fail CLOSED, no abierto: un fallo real de parseo de fecha en Source A
    # no debe convertirse silenciosamente en un rango sin limite.
    # `appointed` nunca es legitimamente None (toda gestion tiene fecha de
    # alta). `until` SI es legitimamente None cuando la gestion sigue
    # vigente - pero en ese caso `until_saison` tambien da None (misma rama
    # en parse_spells); si `until` es None y `until_saison` NO lo es, fue un
    # fallo de parseo de la fecha de baja, no una gestion vigente.
    if appointed is None:
        raise RuntimeError(
            f"[{spell['club']}] appointed=None: fallo de parseo de la fecha de "
            f"alta (Source A). No es un caso legitimo (toda gestion tiene "
            f"fecha de alta); abortando en vez de correr con un rango de "
            f"fechas sin limite inferior.")
    if until is None and spell.get("until_saison") is not None:
        raise RuntimeError(
            f"[{spell['club']}] until=None pero until_saison={spell['until_saison']}: "
            f"fallo de parseo de la fecha de baja (Source A), no una gestion "
            f"vigente (esa viene con until_saison=None tambien). Abortando en "
            f"vez de correr con un rango de fechas sin limite superior.")

    def in_range(date):
        if date is None:
            return False
        if appointed and date < appointed:
            return False
        if until and date > until:
            return False
        return True

    today_iso = datetime.date.today().isoformat()
    filtered = [m for m in seen_ids.values() if m["played"] and in_range(m["match_date"])]
    # Candidatos al bug de grilla "-:-": played=False pero en rango y con
    # fecha ya pasada (una fecha futura dentro de una gestion en curso
    # legitimamente no tiene reporte todavia - no vale la pena gastar un
    # fetch en eso).
    dashdash_candidates = [
        m for m in seen_ids.values()
        if not m["played"] and in_range(m["match_date"]) and m["match_date"] <= today_iso
    ]
    filtered.sort(key=lambda m: m["match_date"])
    dashdash_candidates.sort(key=lambda m: m["match_date"])

    matches = []
    failed_report_ids = []
    recovered_dashdash_ids = []

    def _append_match(m, gf, ga, report):
        matches.append({
            "i": spell_index,
            "club": spell["club"],
            "date": m["match_date"],
            "competition": clubs.normalize_competition(m["competition"]),
            "home_away": m["home_away"],
            "opponent": m["opponent"],
            "opponent_verein_id": m["opponent_verein_id"],
            "opponent_coach": report["opponent_coach"],
            "opponent_coach_id": report["opponent_coach_id"],
            "gf": gf,
            "ga": ga,
            "result": _result(gf, ga),
            "spielbericht_id": m["spielbericht_id"],
            "scorers": report["scorers"],
        })

    for m in filtered:
        rep_html, status = _fetch_report_with_retry(fetcher, m["spielbericht_id"], verbose)
        if not rep_html:
            failed_report_ids.append(m["spielbericht_id"])
            continue
        report = parse.parse_report(rep_html, own_verein_id=club_info["verein_id"])
        if verbose and any(s["kind"] == "og" for s in report["scorers"]):
            print(f"    [CHECK] posible gol en contra en reporte {m['spielbericht_id']} "
                  f"- el patron 'og' de parse.py no esta validado en vivo todavia, "
                  f"verificar a mano: {report_url(m['spielbericht_id'])}")
        _append_match(m, m["gf"], m["ga"], report)

    for m in dashdash_candidates:
        # No cuenta como fallo de fetch si el reporte no existe (404) o
        # sigue sin poder obtenerse: un partido futuro/no jugado de verdad
        # simplemente no tiene reporte. Solo es informativo.
        rep_html, status = _fetch_report_with_retry(fetcher, m["spielbericht_id"], verbose)
        if not rep_html:
            continue
        report = parse.parse_report(rep_html, own_verein_id=club_info["verein_id"])
        if not _report_has_content(report):
            continue  # reporte vacio/stub: confirma que NO se jugo, se descarta
        gf, ga = _score_from_scorers(report["scorers"])
        if verbose:
            print(f"    [RECOVERED] {m['spielbericht_id']} ({m['match_date']}, "
                  f"vs {m['opponent']}): grilla decia '-:-' pero el reporte prueba "
                  f"que SI se jugo (DT rival={report['opponent_coach']!r}, "
                  f"marcador derivado de goleadores {gf}:{ga}); incluido.")
        if verbose and any(s["kind"] == "og" for s in report["scorers"]):
            print(f"    [CHECK] posible gol en contra en reporte {m['spielbericht_id']} "
                  f"- el patron 'og' de parse.py no esta validado en vivo todavia, "
                  f"verificar a mano: {report_url(m['spielbericht_id'])}")
        recovered_dashdash_ids.append(m["spielbericht_id"])
        _append_match(m, gf, ga, report)

    matches.sort(key=lambda mm: mm["date"])
    return matches, failed_saison_ids, failed_report_ids, recovered_dashdash_ids


def _write_json_atomic(path, data):
    """Escribe JSON de forma atomica (archivo temporal + os.replace) para
    que una corrida interrumpida a mitad de escritura no trunque el archivo
    real existente."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def run(only_spell_index=None, matches_out=None, spells_out=None, verbose=True,
        force_refresh_current=True):
    """Corre el pipeline completo de ingesta.

    - `only_spell_index`: si se pasa, solo se scrapean partidos de ESA
      gestion (por indice, 0-based, en el orden que devuelve parse_spells).
      `spells_records` igual se arma para las 7, es informacion ya cacheada
      del profile y no pega requests extra.
    - `matches_out` / `spells_out`: paths de salida; si son None no se
      escribe ese archivo (util para una corrida de prueba que solo quiere
      el JSON de partidos, sin tocar data/spells.json final).
    - `force_refresh_current` (default True, Fase 7 / update.py): fuerza un
      re-fetch en vivo SOLO del perfil (Source A) y de la pagina de fixture
      del saison_id en curso de la gestion vigente (`until is None`) - ver
      docstring de `build_matches_for_spell`. El resto del cache (~155
      reportes de partido ya jugados + fixtures de temporadas cerradas)
      nunca se toca. Poner en False reproduce el comportamiento
      100% cache-backed usado en la corrida inicial completa.

    Chequeo de integridad: si parse_spells no devuelve ninguna gestion, o el
    total de partidos ensamblados (solo para las gestiones efectivamente
    procesadas, respetando only_spell_index) cae por debajo de
    MIN_COMPLETENESS_RATIO de lo que TM reporta (matches_tm), la corrida
    ABORTA (sys.exit) SIN escribir ningun JSON. Ademas, si alguna gestion
    quedo corta de partidos Y tuvo fallos reales de fetch, la corrida sale
    con error no-cero al final aunque los archivos SI se hayan escrito.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    fetcher = Fetcher()
    spells = fetch_spells(fetcher, force=force_refresh_current)

    if not spells:
        sys.exit("[ABORT] ingest.run(): parse_spells() no devolvio ninguna gestion "
                  "- el perfil de Sara puede haber cambiado de estructura. "
                  "No se escribe spells.json/matches.json.")

    spells_records = []
    all_matches = []
    expected_total = 0
    all_failed_saison_ids = []
    all_failed_report_ids = []
    all_recovered_dashdash_ids = []
    run_incomplete = False

    for i, spell in enumerate(spells):
        club_key = clubs.find_by_name(spell["club"])
        if not club_key:
            if verbose:
                print(f"[WARN] club desconocido en registry: {spell['club']!r}; salteando gestion i={i}")
            continue
        club_info = clubs.CLUBS[club_key]
        spells_records.append({
            "i": i,
            "club": spell["club"],
            "slug": club_info["slug"],
            "verein_id": club_info["verein_id"],
            "appointed": spell["appointed"],
            "until": spell["until"],
            "saison_ids": spell["saison_ids"],
            "matches_tm": spell["matches_tm"],
            "ppg_tm": spell["ppg_tm"],
        })

        if only_spell_index is not None and i != only_spell_index:
            continue

        expected_total += spell["matches_tm"]
        if verbose:
            print(f"[{i}] {spell['club']} ({spell['appointed']} -> {spell['until'] or 'presente'}): "
                  f"buscando partidos...")
        matches, failed_saisons, failed_reports, recovered = build_matches_for_spell(
            spell, i, club_info, fetcher, verbose=verbose,
            force_current=(force_refresh_current and spell["until"] is None))
        if verbose:
            print(f"    {len(matches)} partidos ingresados (TM dice matches_tm={spell['matches_tm']})")
            if recovered:
                print(f"    de esos, {len(recovered)} recuperados del bug de grilla "
                      f"'-:-' (reporte real encontrado): {recovered}")
        all_matches.extend(matches)
        all_failed_saison_ids.extend(failed_saisons)
        all_failed_report_ids.extend(failed_reports)
        all_recovered_dashdash_ids.extend(recovered)

        # Distingue "filtrado legitimo por fecha/competicion" (nunca es
        # error) de "fetch realmente fallido": solo marca la corrida como
        # incompleta si AMBAS cosas pasaron juntas en esta gestion.
        had_fetch_failures = bool(failed_saisons or failed_reports)
        if had_fetch_failures and len(matches) < spell["matches_tm"]:
            run_incomplete = True

    if expected_total > 0:
        ratio = len(all_matches) / expected_total
        if ratio < MIN_COMPLETENESS_RATIO:
            sys.exit(
                f"[ABORT] ingest.run(): se ensamblaron {len(all_matches)} partidos "
                f"pero TM reporta matches_tm={expected_total} para las gestiones "
                f"procesadas ({ratio:.0%}, umbral {MIN_COMPLETENESS_RATIO:.0%}). "
                f"No se escribe spells.json/matches.json - los datos parecen "
                f"truncados/incompletos.")

    if spells_out:
        _write_json_atomic(spells_out, spells_records)
        if verbose:
            print("spells escrito en", spells_out)

    if matches_out:
        _write_json_atomic(matches_out, all_matches)
        if verbose:
            print("matches escrito en", matches_out, "-", len(all_matches), "partidos")

    if verbose:
        total_failed = len(all_failed_report_ids) + len(all_failed_saison_ids)
        attempted = len(all_matches) + len(all_failed_report_ids)
        print(f"\nResumen ingest: {len(all_matches)}/{attempted} reportes ok"
              + (f" ({expected_total} esperados segun matches_tm)" if expected_total else "")
              + f", {total_failed} fallos de fetch tras reintento.")
        if all_failed_report_ids:
            print(f"  reportes fallidos: {all_failed_report_ids}")
        if all_failed_saison_ids:
            print(f"  fixtures fallidos (saison_id): {all_failed_saison_ids}")
        print(f"  recuperados del bug de grilla '-:-' (total): {len(all_recovered_dashdash_ids)}"
              + (f" -> {all_recovered_dashdash_ids}" if all_recovered_dashdash_ids else ""))

    if run_incomplete:
        sys.exit(
            "[ABORT] ingest.run(): una o mas gestiones quedaron con MENOS partidos "
            "de los que TM reporta (matches_tm) Y hubo fallos reales de fetch (no "
            "solo filtrado legitimo por fecha/competicion) - ver [ERROR]/resumen "
            "arriba. Los archivos SI se escribieron (el umbral agregado del "
            f"{MIN_COMPLETENESS_RATIO:.0%} no se cruzo), pero el resultado debe "
            "considerarse incompleto.")

    return spells_records, all_matches


if __name__ == "__main__":
    run(matches_out=MATCHES_PATH, spells_out=SPELLS_PATH)
