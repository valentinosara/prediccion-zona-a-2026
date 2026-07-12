"""
update_wc.py - Un solo comando para predecir una fecha del Mundial 2026.

    python update_wc.py --fecha 1     # genera docs/mundial_fecha1.html (pendientes de la F1)
    python update_wc.py --fecha 2     # cuando termine la F1: re-fetch + re-fit + predice la F2
    python update_wc.py --fecha 3

Encadena (estilo update.py del repo): predecir (fetch + re-fit ratings/forma con los
resultados ya jugados + anclar al mercado + optimizar el prode) -> generar el HTML
self-contained. Reusable tal cual para las fechas 2 y 3.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description="Actualiza la prediccion del prode (una fecha)")
    ap.add_argument("--fecha", type=int, required=True, help="numero de fecha (1, 2 o 3)")
    ap.add_argument("--sims", type=int, default=50000, help="simulaciones Monte Carlo por partido")
    ap.add_argument("--jugada", choices=["ev", "probable"], default="ev",
                    help="ev = marcador de maximo valor esperado (gana mas a la larga; default); "
                         "probable = marcador mas probable (mas realista, rinde un poco menos)")
    args = ap.parse_args()

    sys.path.insert(0, HERE)
    import predict_wc
    import gen_html_wc

    modo_txt = "MAX valor esperado" if args.jugada == "ev" else "marcador MAS PROBABLE"
    print(f"\n▶ Prediciendo la Fecha {args.fecha} (fetch + re-fit + anclaje a mercado + "
          f"jugada: {modo_txt})")
    out = predict_wc.run(args.fecha, n_sims=args.sims, jugada=args.jugada)
    m = out["meta"]; src = m["provenance"]
    print(f"   {m['n_pendientes']} partidos pendientes · {m['n_jugados']} ya jugados · "
          f"datos: fixtures={src['fixtures']['source']}, cuotas={src['odds']['source']}")
    print(f"   Puntos esperados totales de la fecha: {m['ev_total']}  "
          f"(confianza {m['confianza_global']})")
    bt = out["backtest"]
    if bt["n"]:
        print(f"   Auto-evaluacion (F{args.fecha} ya jugada): {bt['total_pts']}/{bt['max_pts']} "
              f"pts del prode ({bt['pct_max']}% del maximo) en {bt['n']} partidos")

    print(f"\n▶ Generando el HTML self-contained")
    path = gen_html_wc.build(args.fecha)
    print(f"   {os.path.relpath(path, HERE)}  ({os.path.getsize(path)//1024} KB)")

    print(f"\n✓ Listo. Abri docs/mundial_fecha{args.fecha}.html (offline, self-contained).")
    print("  Para publicar:  git add -A && git commit -m \"prode fecha "
          f"{args.fecha}\" && git push")


if __name__ == "__main__":
    main()
