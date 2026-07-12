"""
update.py - Actualiza la prediccion de la Zona A con una sola corrida.

Cuando se juega una fecha nueva:
    python update.py

Encadena: bajar resultados (Promiedos) -> preparar -> modelar -> generar HTML.
NO re-baja valores de plantel/escudos/backtest (no cambian fecha a fecha).
Resultado: prediccion_zonaA_2026.html actualizado.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    ("scrape_promiedos.py", "Bajando resultados de Promiedos"),
    ("prep_zonaA.py",       "Preparando fixture de Zona A"),
    ("predict_zonaA.py",    "Recalibrando modelo y prediciendo"),
    ("gen_pred_html.py",    "Generando el HTML"),
]


def main():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for script, desc in STEPS:
        print(f"\n▶ {desc} ({script})")
        r = subprocess.run([sys.executable, os.path.join(HERE, script)], env=env)
        if r.returncode != 0:
            sys.exit(f"✗ Falló {script} — actualización abortada.")
    # copiar al sitio que publica GitHub Pages (carpeta docs/)
    docs = os.path.join(HERE, "docs")
    os.makedirs(docs, exist_ok=True)
    shutil.copy(os.path.join(HERE, "prediccion_zonaA_2026.html"), os.path.join(docs, "index.html"))
    print("\n✓ Listo. HTML actualizado y copiado a docs/index.html")
    print("  Para publicar en la web:")
    print('     git add -A && git commit -m "update fecha" && git push')


if __name__ == "__main__":
    main()
