"""
show_wc.py - Muestra por consola las recomendaciones del prode YA calculadas por el
pipeline (lee data_mundial/pred_wc.json que dejan update_wc.py / predict_wc.py). Asi la
consola coincide EXACTO con lo que sale en el HTML: mismo de-vig, mismo Dixon-Coles,
mismo optimizador de puntos esperados, mismas cuotas reales.

  python show_wc.py                 # los pendientes de HOY (fecha real ART)
  python show_wc.py --dia 2026-06-14
  python show_wc.py --match Curazao  # filtra por nombre
  python show_wc.py --all            # todos los pendientes de la fecha cargada
"""
import argparse
import json
import os
from datetime import datetime

import predict_wc
from predict_cli import report_text


def main():
    ap = argparse.ArgumentParser(description="Recomendaciones del prode por consola (lee pred_wc.json).")
    ap.add_argument("--dia", default=None, help="YYYY-MM-DD en hora de Argentina. Por defecto: hoy.")
    ap.add_argument("--all", action="store_true", help="mostrar todos los pendientes, sin filtrar por dia")
    ap.add_argument("--match", default=None, help="filtra por subcadena del nombre de un equipo")
    args = ap.parse_args()

    path = os.path.join(predict_wc.DATA, "pred_wc.json")
    if not os.path.exists(path):
        ap.error("No encuentro data_mundial/pred_wc.json. Corré primero: python update_wc.py --fecha N")
    d = json.load(open(path, encoding="utf-8"))
    teams = d["teams"]
    preds = d["pendientes"]
    meta = d["meta"]
    prov = meta.get("provenance", {})

    sel = preds
    if not args.all:
        dia = args.dia or datetime.now().strftime("%Y-%m-%d")
        sel = [p for p in preds if (p.get("kickoff") or "")[:10] == dia]
        scope = f"dia {dia}"
    else:
        scope = f"Fecha {meta.get('fecha')}"
    if args.match:
        m = args.match.lower()
        sel = [p for p in sel if m in teams.get(p["home"], {}).get("name", "").lower()
               or m in teams.get(p["away"], {}).get("name", "").lower()]

    # Procedencia + aviso honesto de incertidumbre
    def ptag(k):
        s = prov.get(k, {})
        return f"{k}={s.get('source', '?')}"
    print()
    print(f"  PRODE MUNDIAL 2026 — {scope}  ({len(sel)} partidos pendientes)")
    print(f"  Datos: {ptag('fixtures')}, {ptag('odds')}, {ptag('teams')}  ·  generado {meta.get('generado', '')}")
    degraded = [k for k in ("fixtures", "odds", "teams") if prov.get(k, {}).get("source") not in ("live", "manual")]
    if degraded:
        print(f"  ⚠ MODO DEGRADADO en: {', '.join(degraded)} (cache/seed; puede estar desactualizado).")
    print("  ⚠ Incertidumbre: el mercado manda en el 1X2; el marcador es el que MAXIMIZA los")
    print("    puntos esperados del prode (no el mas probable). Es la jugada de mayor valor, no")
    print("    una certeza: en un partido puntual cualquier resultado puede salir.")
    print()

    if not sel:
        print("  (no hay partidos pendientes que coincidan con el filtro)")
        return

    for p in sorted(sel, key=lambda x: x.get("kickoff", "")):
        print(report_text(p, teams))
        print()
    total = sum(p["ev_rec"] for p in sel)
    print(f"  Puntos esperados totales del prode: {total:.1f} en {len(sel)} partidos.")
    print()


if __name__ == "__main__":
    main()
