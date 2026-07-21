"""
update.py - Actualiza el perfil de Juan Sara con una sola corrida.

Encadena: ingest.py (Transfermarkt -> data/spells.json + data/matches.json)
-> stats.py (data/stats.json) -> gen_html.py (docs/entrenador-sara/index.html).
Mismo estilo "zona-a" que prediccion-zona-a/update.py: lista de pasos +
subprocess.run, aborta ante el primer paso que devuelva codigo != 0.

Re-ejecutable de forma segura: ingest.py sigue siendo cache-backed para todo
lo ya scrapeado (ver docstring de ingest.py), pero por default fuerza un
re-fetch en vivo del perfil de Sara y de la pagina de fixture del saison_id
EN CURSO de la gestion vigente (`force_refresh_current=True`, la season "en
curso" se deriva dinamicamente de la fecha de hoy - ver
parse.current_saison_id()). Asi, correr `python update.py` de nuevo en el
futuro recoge los partidos nuevos que Ferro haya jugado desde la ultima
corrida, sin re-scrapear las ~155 paginas ya cerradas/historicas.

Uso (cuando haya partidos nuevos, ej. una fecha nueva de Ferro):
    python update.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    ("ingest.py",   "Actualizando datos desde Transfermarkt (Fuentes A/B/C)"),
    ("stats.py",    "Recalculando las 7 estadisticas"),
    ("gen_html.py", "Generando la pagina HTML"),
]


def main():
    # Fuerza UTF-8 tambien en la salida DE ESTE proceso, no solo en el env
    # que se pasa a los subprocesos de abajo: en Windows, cuando stdout no
    # es una consola interactiva (ej. capturado/redirigido, como en una
    # corrida automatizada), Python usa el codepage legacy del sistema
    # (cp1252) en vez de UTF-8, y los prints con "▶/✓/✗" de este mismo
    # archivo rompen con UnicodeEncodeError. Confirmado en vivo: la primera
    # corrida real de update.py fallo exactamente asi.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for script, desc in STEPS:
        print(f"\n▶ {desc} ({script})")
        r = subprocess.run([sys.executable, os.path.join(HERE, script)], env=env)
        if r.returncode != 0:
            sys.exit(f"✗ Fallo {script} - actualizacion abortada.")
    print("\n✓ Listo. entrenador-sara/data/stats.json y "
          "docs/entrenador-sara/index.html actualizados.")
    print("  Para publicar en la web:")
    print('     git add -A && git commit -m "update entrenador-sara" && git push')


if __name__ == "__main__":
    main()
