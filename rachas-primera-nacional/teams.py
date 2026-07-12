"""
teams.py - Normalizacion de nombres de equipos.

Uso una sola fuente (worldfootball) con teID estable, asi que internamente la
identidad del equipo ya es consistente. Esta capa solo arregla la GRAFIA para
mostrar nombres argentinos canonicos (worldfootball germaniza/abrevia algunos).
"""

# raw (worldfootball) -> canonico (es-AR)
CANON = {
    "Belgrano de Córdoba": "Belgrano (Córdoba)",
    "Mitre de SdE": "Mitre (Santiago del Estero)",
    "Tristan Suárez": "Tristán Suárez",
    "Gimnasia de Jujuy": "Gimnasia y Esgrima (Jujuy)",
    "Gimnasia y Tiro de Salta": "Gimnasia y Tiro (Salta)",
    "Güemes de SdE": "Güemes (Santiago del Estero)",
    "Gueemes de SdE": "Güemes (Santiago del Estero)",
    "Estudiantes de Caseros": "Estudiantes (Caseros)",
    "Estudiantes de Río Cuarto": "Estudiantes (Río Cuarto)",
    "Estudiantes de San Luis": "Estudiantes (San Luis)",
    "Deportivo Morón": "Deportivo Morón",
    "Atlético de Rafaela": "Atlético de Rafaela",
    "Atletico Rafaela": "Atlético de Rafaela",
    "Instituto Córdoba": "Instituto (Córdoba)",
    "Instituto de Córdoba": "Instituto (Córdoba)",
    "San Martín de Tucumán": "San Martín (Tucumán)",
    "San Martín de San Juan": "San Martín (San Juan)",
    "Independiente Rivadavia": "Independiente Rivadavia (Mendoza)",
    "Defensores de Belgrano": "Defensores de Belgrano (VR)",
    "Racing de Córdoba": "Racing (Córdoba)",
    "Ciudad de Bolívar": "Ciudad de Bolívar",
    "Club Ciudad de Bolívar": "Ciudad de Bolívar",
    "Colón de Santa Fe": "Colón (Santa Fe)",
    "Patronato de Paraná": "Patronato (Paraná)",
    "Gimnasia de Mendoza": "Gimnasia y Esgrima (Mendoza)",
    "Alvarado de Mar del Plata": "Alvarado (Mar del Plata)",
    "Brown de Adrogué": "Brown (Adrogué)",
    "Brown de Puerto Madryn": "Brown (Puerto Madryn)",
    "Sol de América": "Sol de América (Formosa)",
    "Atlético Tucumán": "Atlético Tucumán",
    "Crucero del Norte": "Crucero del Norte",
}


def canon(name, team_id=None):
    if not name:
        return name
    return CANON.get(name, name)
