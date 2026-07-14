"""
clubs.py - Registro estatico de los 4 clubes donde Juan Sara fue *head coach*
("Manager" en Transfermarkt), + normalizacion de nombres de competicion.

Los 4 verein_id fueron resueltos EN VIVO a partir de los anchors /verein/{id}
del perfil (Source A, https://www.transfermarkt.us/juan-sara/profil/trainer/94335),
cruzando texto visible + atributo title + slug del href para confirmar que cada
club coincide (ver checkpoint de validacion, tarea 2.3):

  - Ferro          -> href /club-ferro-carril-oeste/.../verein/4557   title="Club Ferro Carril Oeste"
  - Estudiantes    -> href /ca-estudiantes-buenos-aires-/.../verein/14312 title="CA Estudiantes"
  - Dep. Maipu     -> href /cd-maipu-mendoza-/.../verein/19523        title="Club Deportivo Maipu"
  - Tigre          -> href /club-atletico-tigre/.../verein/11831      title="Club Atletico Tigre"

Ferro (verein_id=4557) ya estaba confirmado de antemano en el design; los otros
3 no estaban en el design y se resolvieron aqui, en esta misma corrida.
"""
import re

CLUBS = {
    "ferro": {
        "slug": "club-ferro-carril-oeste",
        "verein_id": 4557,
        "name": "Ferro",
        "full_name": "Club Ferro Carril Oeste",
    },
    "estudiantes": {
        "slug": "ca-estudiantes-buenos-aires-",
        "verein_id": 14312,
        "name": "Estudiantes",
        "full_name": "CA Estudiantes",
    },
    "maipu": {
        "slug": "cd-maipu-mendoza-",
        "verein_id": 19523,
        "name": "Dep. Maipú",
        "full_name": "Club Deportivo Maipú",
    },
    "tigre": {
        "slug": "club-atletico-tigre",
        "verein_id": 11831,
        "name": "Tigre",
        "full_name": "Club Atlético Tigre",
    },
}

# indices auxiliares
BY_VEREIN_ID = {c["verein_id"]: key for key, c in CLUBS.items()}
BY_NAME = {c["name"]: key for key, c in CLUBS.items()}


def find_by_name(name):
    """Busca un club por el nombre tal como aparece en la tabla de historial
    de Transfermarkt (columna "Club & role", ya sin el sufijo de rol).
    Devuelve la key del registro (ej. "ferro") o None si no matchea.
    """
    name = name.strip()
    if name in BY_NAME:
        return BY_NAME[name]
    # match laxo por si TM cambia levemente el texto (espacios, puntuacion)
    norm = re.sub(r"[.\s]+", "", name).lower()
    for key, c in CLUBS.items():
        if re.sub(r"[.\s]+", "", c["name"]).lower() == norm:
            return key
    return None


def find_by_verein_id(verein_id):
    return BY_VEREIN_ID.get(int(verein_id))


# -------- normalizacion de nombres de competicion (Source B: fixtures) --------
# Transfermarkt muestra el nombre de competicion tal cual (a veces con logo +
# texto corto). Este mapeo cubre las variantes conocidas de las categorias
# argentinas relevantes para los 4 clubes; cualquier variante no mapeada se
# devuelve "as-is" (stripped), nunca se descarta el partido.
_COMPETITION_MAP = {
    "primera b metropolitana": "Primera B Metropolitana",
    "torneo federal a": "Torneo Federal A",
    "primera b nacional": "Primera Nacional",
    "primera nacional": "Primera Nacional",
    "copa argentina": "Copa Argentina",
    "reducido": "Reducido (ascenso)",
    "reducido - ascenso": "Reducido (ascenso)",
    "copa de la liga profesional": "Copa de la Liga Profesional",
    "liga profesional de futbol": "Liga Profesional",
    "primera division": "Primera División",
}


def normalize_competition(raw):
    """Normaliza el label crudo de competicion de Source B a un nombre
    canonico. Si no hay mapeo conocido, devuelve el texto original (stripped),
    nunca None ni excepcion: un label desconocido no debe tirar abajo el
    parseo de un partido.
    """
    if not raw:
        return raw
    key = raw.strip().lower()
    return _COMPETITION_MAP.get(key, raw.strip())


def resolve_verein_id(html):
    """Fallback: dado el HTML de una pagina de busqueda de Transfermarkt
    (https://www.transfermarkt.us/schnellsuche/ergebnis/schnellsuche?query=...),
    devuelve (verein_id, slug) del primer club encontrado en los resultados,
    o (None, None) si no hay match. Se usa solo si algun club nuevo no esta
    ya hardcodeado en CLUBS (no invocado en esta corrida: los 4 clubes de
    Sara ya estan resueltos y confirmados arriba).
    """
    from bs4 import BeautifulSoup

    if not html:
        return None, None
    soup = BeautifulSoup(html, "lxml")
    for a in soup.select('a[href*="/verein/"]'):
        href = a.get("href", "")
        m = re.search(r"/([\w-]+)/[\w-]+/verein/(\d+)", href)
        if m:
            slug, vid = m.group(1), int(m.group(2))
            return vid, slug
    return None, None
