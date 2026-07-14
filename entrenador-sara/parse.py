"""
parse.py - Parseo puro (bs4 + lxml) de las 3 fuentes de Transfermarkt.

Fuente A: perfil del entrenador (ej. /juan-sara/profil/trainer/94335)
  -> parse_spells(html): las 7 gestiones como head coach ("Manager"; se
     excluyen las filas "Assistant Manager", 2015-2021).

Fuente B: fixture de un club por temporada
  (/{club-slug}/spielplandatum/verein/{vereinId}/saison_id/{year})
  -> parse_fixture(html): todos los partidos del club en esa temporada
     (no filtrados por gestion todavia; eso lo hace ingest.py).

Fuente C: reporte de un partido (/spielbericht/index/spielbericht/{id})
  -> parse_report(html, own_verein_id): ambos DTs + goleadores.

Nota sobre el minuto del gol: Transfermarkt codifica el icono de reloj de
cada evento ("sb-sprite-uhr-klein") como posicion de un sprite CSS
(background-position), sin ningun texto/tooltip/atributo accesible con el
minuto real (verificado en vivo sobre el reporte 4797931: el span solo
tiene class+style, nada mas). Sin una segunda fuente confiable para
decodificar ese sprite, `minute` queda en None en vez de inventar un valor;
no hay ningun escenario de spec que dependa del minuto exacto.

Nota sobre "gol en contra" (kind="og") - NO VALIDADO EN VIVO todavia: el
texto "penalty" SI esta confirmado contra datos reales (2 casos en el
trial: "Mateo Acosta , Penalty, 1. Goal of the Season"), pero ningun partido
visto hasta ahora (12 del trial + 7 partidos extra de Ferro fuera de la
gestion de Sara, revisados puntualmente para buscar un ejemplo) tuvo un gol
en contra. El chequeo `"own goal" in low` queda TAL CUAL estaba (no se
adivino un formato alternativo sin evidencia); ingest.py imprime un aviso
"[CHECK]" si alguna vez detecta kind="og" durante la corrida completa, para
poder confirmar a mano el texto real la primera vez que aparezca uno.
"""
import re
from datetime import date

from bs4 import BeautifulSoup

SARA_TRAINER_ID = 94335

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_source_a_date(text):
    """'Apr 14, 2026' -> '2026-04-14'."""
    m = re.match(r"([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})", text.strip())
    if not m:
        return None
    mon, day, year = m.groups()
    month = _MONTHS.get(mon[:3].title())
    if not month:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def _parse_source_b_date(text):
    """'Sat 2/14/26' -> '2026-02-14' (locale .us: weekday + M/D/YY)."""
    parts = text.strip().split(None, 1)
    if len(parts) != 2:
        return None
    _, mdy = parts
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})$", mdy.strip())
    if not m:
        return None
    mm, dd, yy = (int(x) for x in m.groups())
    year = 2000 + yy if yy < 69 else 1900 + yy
    return f"{year:04d}-{mm:02d}-{dd:02d}"


def _season_start_year(label):
    """'25/26' -> 2025."""
    m = re.match(r"(\d{2})/(\d{2})$", label.strip())
    if not m:
        return None
    return 2000 + int(m.group(1))


def _current_saison_id(today=None):
    """saison_id (anio_calendario - 1) de la temporada que contiene la
    fecha de HOY, para una gestion todavia vigente (until is None).

    Hallazgo en vivo durante la corrida completa (~156 partidos, ver
    apply-progress): la ruta spielplandatum bucketiza SIEMPRE por
    anio_calendario-1, SIN corte por mes - Primera Nacional juega feb-nov
    de un solo anio calendario. El label "XX/YY" que muestra el perfil de
    Source A (ej. "25/26") es solo una convencion de DISPLAY estilo europeo
    (ago-jul) que TM aplica de forma generica; NO refleja el saison_id real
    que esta ruta necesita. Por eso esta funcion ya no distingue meses (la
    version anterior, con corte en agosto, calculaba mal el bucket para
    fechas ago-dic - ver parse_spells).
    """
    today = today or date.today()
    return today.year - 1


def current_saison_id(today=None):
    """Wrapper publico de `_current_saison_id` (Fase 7 / update.py): la
    gestion en curso (until is None) necesita saber cual es el saison_id
    "vivo" de HOY para poder forzar un re-fetch selectivo de esa unica
    pagina de fixture en cada corrida de update.py, sin tocar el resto del
    cache (ver ingest.py: `build_matches_for_spell(..., force_current=)`)."""
    return _current_saison_id(today)


def _saison_id_for_date(iso_date):
    """saison_id real (anio_calendario_del_partido - 1) para una fecha ISO
    'YYYY-MM-DD' ya parseada. Ver docstring de `_current_saison_id` y la
    nota en `parse_spells`: NO usar el label 'XX/YY' de Source A para esto,
    difiere del saison_id real cuando la fecha cae jul-dic."""
    return int(iso_date[:4]) - 1


def parse_spells(html):
    """Devuelve las 7 gestiones de Sara como head coach ("Manager"), desde
    la tabla de historial de carrera del perfil (Source A). Filas
    "Assistant Manager" (2015-2021) y filas informativas de una sola celda
    ("Assistant Manager of: ...") se ignoran por completo.

    Cada item: {club, appointed, until (None si sigue en el cargo),
                until_saison (None SOLO si sigue en el cargo; expuesto para
                que ingest.py distinga eso de un fallo real de parseo de la
                fecha de baja, donde `until` tambien da None pero
                `until_saison` no), saison_ids: [...], matches_tm, ppg_tm}
    """
    soup = BeautifulSoup(html, "lxml")
    tables = soup.select("table.items")
    if not tables:
        return []
    rows = tables[0].select("tbody > tr")

    spells = []
    for tr in rows:
        tds = tr.find_all("td", recursive=False)
        if len(tds) != 6:
            continue  # filas informativas tipo "Assistant Manager of: ..."

        role_cell = tds[1].get_text(" ", strip=True)
        if role_cell.endswith(" Assistant Manager"):
            continue  # gestion como asistente: excluida de todo (ING-1)
        if not role_cell.endswith(" Manager"):
            continue  # fila inesperada: no romper el parseo, solo saltear
        club_name = role_cell[: -len(" Manager")].strip()

        appointed_raw = tds[2].get_text(" ", strip=True)
        until_raw = tds[3].get_text(" ", strip=True)
        matches_raw = tds[4].get_text(strip=True)
        ppg_raw = tds[5].get_text(strip=True)

        m_app = re.match(r"(\d{2}/\d{2})\s*\(([^)]+)\)", appointed_raw)
        if not m_app:
            continue
        _appointed_season_label, appointed_date_text = m_app.groups()
        appointed = _parse_source_a_date(appointed_date_text)
        # Nota: el label "XX/YY" de Source A (_appointed_season_label) ya
        # NO se usa para saison_ids (ver mas abajo) - solo servia como
        # display; el saison_id real se deriva de la fecha ISO ya parseada.

        if until_raw.strip() == "-":
            until = None
            until_saison = None
        else:
            m_until = re.match(r"(\d{2}/\d{2})\s*\(([^)]+)\)", until_raw)
            if not m_until:
                continue
            until_season_label, until_date_text = m_until.groups()
            until = _parse_source_a_date(until_date_text)
            until_saison = _season_start_year(until_season_label)

        # saison_ids: derivado de las fechas ISO YA PARSEADAS
        # (appointed/until), NO del label "XX/YY" de Source A.
        #
        # Hallazgo en vivo (corrida completa, ~156 partidos - ver
        # apply-progress): el label "XX/YY" es una convencion de DISPLAY
        # estilo europeo (ago-jul) que TM aplica de forma generica en esta
        # tabla; el saison_id REAL que espera la ruta spielplandatum para
        # un partido jugado en el anio calendario Y es SIEMPRE Y-1, sin
        # excepcion por mes (confirmado fetcheando saison_id=2022/2024/2025
        # para Ferro y Estudiantes: la ventana real siempre cae dentro de
        # feb-nov del anio calendario "saison_id+1", nunca se corre).
        # Cuando appointed/until caen en jul-dic, el label (Y/Y+1) y el
        # saison_id real (Y-1) DIFIEREN: Estudiantes con
        # appointed_raw="25/26 (Jul 1, 2025)" necesitaba saison_id=2024
        # (no 2025, que el label sugeriria) para ver los partidos de
        # jul-dic 2025 - confirmado en vivo (6/25 partidos ingresados antes
        # del fix, gap exacto en esa ventana). Por eso `until_saison` (que
        # SI sigue viniendo del label, ver arriba) ya NO se usa para esta
        # cuenta - solo para el chequeo fail-closed de ingest.py.
        if appointed is None:
            saison_ids = []
        else:
            start_id = _saison_id_for_date(appointed)
            end_id = (_saison_id_for_date(until) if until is not None
                      else _current_saison_id())
            if end_id < start_id:
                end_id = start_id
            saison_ids = list(range(start_id, end_id + 1))

        matches_tm = int(matches_raw) if matches_raw not in ("", "-") else 0
        try:
            ppg_tm = float(ppg_raw)
        except ValueError:
            ppg_tm = None

        spells.append({
            "club": club_name,
            "appointed": appointed,
            "until": until,
            "until_saison": until_saison,
            "saison_ids": saison_ids,
            "matches_tm": matches_tm,
            "ppg_tm": ppg_tm,
        })

    return spells


def parse_fixture(html):
    """Devuelve todos los partidos de un club en una temporada (Source B,
    ruta spielplandatum). No filtra por gestion: eso lo hace ingest.py con
    el rango [appointed, until] de cada spell.

    Fila de encabezado de competicion (una sola celda, sin link de reporte)
    actualiza `competition` para las filas siguientes, asi soporta paginas
    que mezclen mas de una competicion en la misma tabla.

    Cada item: {match_date, competition, home_away: "H"|"A", opponent,
                opponent_verein_id, gf, ga, played: bool, spielbericht_id}
    """
    soup = BeautifulSoup(html, "lxml")
    matches = []
    current_competition = None

    for table in soup.find_all("table"):
        rows = table.select("tbody > tr")
        # heuristica: en la tabla de fixture real, CADA fila tiene a lo sumo
        # UN link de reporte (una fila = un partido; la fila de encabezado de
        # competicion no tiene ninguno). Descarta otros widgets de la misma
        # pagina (ej. grillas resumen con varios links por fila).
        link_counts = [len(tr.select('a[href*="/spielbericht/"]')) for tr in rows]
        if not link_counts or max(link_counts) > 1 or sum(1 for c in link_counts if c == 1) == 0:
            continue

        for tr in rows:
            tds = tr.find_all("td", recursive=False)
            if len(tds) < 9:
                # fila de encabezado de competicion (1 celda, colspan)
                header_text = tr.get_text(strip=True)
                if header_text:
                    current_competition = header_text
                continue

            report_a = tds[9].find("a", href=re.compile(r"/spielbericht/"))
            if not report_a:
                continue
            m_id = re.search(r"/spielbericht/(\d+)", report_a.get("href", ""))
            if not m_id:
                continue
            spielbericht_id = int(m_id.group(1))

            match_date = _parse_source_b_date(tds[1].get_text(strip=True))
            home_away = tds[3].get_text(strip=True)  # "H" o "A"

            opp_a = tds[6].find("a")
            opponent = opp_a.get_text(strip=True) if opp_a else None
            opponent_verein_id = None
            if opp_a:
                m_vid = re.search(r"/verein/(\d+)", opp_a.get("href", ""))
                if m_vid:
                    opponent_verein_id = int(m_vid.group(1))

            result_text = report_a.get_text(strip=True)  # "2:1" o "-:-"
            played = ":" in result_text and "-" not in result_text
            gf_home = ga_away = None
            if played:
                parts = result_text.split(":")
                if len(parts) == 2 and all(p.strip().lstrip("-").isdigit() for p in parts):
                    gf_home, ga_away = int(parts[0]), int(parts[1])
                else:
                    played = False

            matches.append({
                "match_date": match_date,
                "competition": current_competition,
                "home_away": home_away,
                "opponent": opponent,
                "opponent_verein_id": opponent_verein_id,
                # gf/ga desde la perspectiva DEL CLUB de este fixture (no siempre
                # "home"): TM siempre imprime "home:away"; reorientamos aqui.
                "gf": (gf_home if home_away == "H" else ga_away) if played else None,
                "ga": (ga_away if home_away == "H" else gf_home) if played else None,
                "played": played,
                "spielbericht_id": spielbericht_id,
            })

    return matches


def parse_report(html, own_verein_id):
    """Devuelve DTs + goleadores de un reporte de partido (Source C).

    - Sara siempre se identifica por su id de entrenador fijo (94335); el
      otro link de entrenador es el DT rival (design: "Sara's side = trainer
      link id 94335; the OTHER trainer link = opponent_coach").
    - Cada gol: {player, minute, team: "sara"|"opp", kind: "goal"|"pen"|"og"}.
      `team` se resuelve comparando el verein_id del escudo del evento
      (`sb-aktion-wappen`) contra `own_verein_id` (el club de Sara en este
      partido) — esto tambien cubre en-contra: el escudo mostrado es el del
      equipo BENEFICIADO, que es lo que corresponde para gf/ga.
    - `kind` se resuelve por texto: "own goal" -> "og", "penalty" -> "pen",
      si no matchea ninguno -> "goal" (gol de juego normal).
    - `minute` queda en None (ver docstring del modulo).
    """
    soup = BeautifulSoup(html, "lxml")

    # ambos DTs viven en su propia fila "Manager:" del bench-table de cada
    # equipo. Buscar en TODA la pagina (sin este scope) trae ruido: se
    # confirmo en vivo (reporte 4797870, Racing Cba) un tercer link
    # /profil/trainer/ fuera de cualquier bench-table__tr, de un DT anterior
    # mencionado en otra seccion, que pisaba al DT correcto.
    opponent_coach = None
    opponent_coach_id = None
    for tr in soup.select("tr.bench-table__tr"):
        label_td = tr.find("td")
        if not label_td or "manager" not in label_td.get_text(strip=True).lower():
            continue
        a = tr.select_one('a[href*="/profil/trainer/"]')
        if not a:
            continue
        m = re.search(r"/profil/trainer/(\d+)", a.get("href", ""))
        if not m:
            continue
        tid = int(m.group(1))
        if tid == SARA_TRAINER_ID:
            continue
        name = a.get_text(strip=True) or a.get("title")
        if not name:
            # ultimo fallback: derivar del slug del href (ej. "pablo-motta")
            slug = a.get("href", "").strip("/").split("/")[0]
            name = slug.replace("-", " ").title() or None
        opponent_coach = name
        opponent_coach_id = tid

    scorers = []
    for li in soup.select("div#sb-tore li"):
        action = li.select_one("div.sb-aktion-aktion")
        action_text = action.get_text(" ", strip=True) if action else ""

        # el link de la foto solo envuelve un <img> (el nombre vive en su
        # title/alt); el link de texto real esta en sb-aktion-aktion.
        player = None
        action_a = action.find("a") if action else None
        if action_a:
            player = action_a.get_text(strip=True) or action_a.get("title") or None
        if not player:
            img = li.select_one("div.sb-aktion-spielerbild img")
            if img:
                player = img.get("title") or img.get("alt") or None
        if not player:
            player = None  # gol sin goleador identificable (ING-2): no falla el parseo

        crest_a = li.select_one("div.sb-aktion-wappen a")
        crest_verein_id = None
        if crest_a:
            m_vid = re.search(r"/verein/(\d+)", crest_a.get("href", ""))
            if m_vid:
                crest_verein_id = int(m_vid.group(1))
        team = "sara" if crest_verein_id == own_verein_id else "opp"

        low = action_text.lower()
        # "penalty" confirmado en vivo (ver docstring del modulo). "own goal"
        # NO confirmado en vivo todavia - se busco un ejemplo real sin
        # encontrar uno; se deja el patron original en vez de adivinar un
        # formato alternativo. ingest.py avisa con "[CHECK]" la primera vez
        # que esto matchee en la corrida completa, para confirmar a mano.
        if "own goal" in low:
            kind = "og"
        elif "penalty" in low:
            kind = "pen"
        else:
            kind = "goal"

        scorers.append({
            "player": player,
            "minute": None,
            "team": team,
            "kind": kind,
        })

    return {
        "sara_coach_id": SARA_TRAINER_ID,
        "opponent_coach": opponent_coach,
        "opponent_coach_id": opponent_coach_id,
        "scorers": scorers,
    }
