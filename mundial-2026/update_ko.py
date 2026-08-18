"""update_ko.py - Un comando para predecir una ronda ELIMINATORIA del Mundial 2026.

    python scrape_fifaphy.py            # 1) bajá el xG de la ronda recién jugada
    python update_ko.py --ronda octavos # 2) predecí la siguiente ronda + generá el HTML

Rondas válidas: 16avos · octavos · cuartos · semis · final · tercer-puesto
(o los slugs de ESPN: round-of-32, round-of-16, quarterfinals, semifinals, final).

Si los cruces de la ronda todavía no están definidos (la ronda previa no terminó), ESPN
trae los equipos como placeholders y el comando lo avisa sin generar nada a medias.
Encadena (estilo update_wc.py): predecir (fetch de la ronda + re-fit de ratings/forma con
xG + anclaje a mercado + alargue/penales + optimizador del prode) -> HTML self-contained.
"""
import argparse
import os

import gen_html_ko
import knockout_wc

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description="Predice una ronda eliminatoria del Mundial 2026")
    ap.add_argument("--ronda", required=True,
                    help="16avos | octavos | cuartos | semis | final | tercer-puesto")
    ap.add_argument("--desde", default=None, help="fecha inicio del barrido (YYYY-MM-DD)")
    ap.add_argument("--hasta", default=None, help="fecha fin del barrido (YYYY-MM-DD)")
    args = ap.parse_args()

    print(f"\n▶ Prediciendo {args.ronda} (fetch de la ronda + re-fit con xG + mercado + "
          f"alargue/penales + optimizador del prode)")
    pred = knockout_wc.predict_round(args.ronda, start=args.desde, end=args.hasta)

    if not pred["preds"]:
        if pred["tbd"]:
            print(f"   ⏳ Los cruces de {pred['round']} todavía NO están definidos "
                  f"({pred['tbd']} partidos con equipos por confirmar).")
            print("   Esperá a que termine la ronda previa y volvé a correr este comando.")
        else:
            print(f"   No se encontraron partidos de {pred['round']} en el rango de fechas.")
        return

    ev_total = sum(p["ev"] for p in pred["preds"])
    print(f"   {len(pred['preds'])} partidos · datos de {pred['n_hist']} jugados · "
          f"w_mkt={pred['w_mkt']:.2f}")
    print(f"   EV total estimado: {ev_total:.1f} pts (prom {ev_total/len(pred['preds']):.2f}/partido)")
    if pred["tbd"]:
        print(f"   (faltan definir {pred['tbd']} cruces de esta ronda)")

    print()
    for p in pred["preds"]:
        rec = f"{p['rec'][0]}-{p['rec'][1]}"
        adv = f"{max(p['adv_home'], p['adv_away']) * 100:.0f}%"
        print(f"   {p['home_name']:>16s} {rec:^5s} {p['away_name']:<16s}  "
              f"-> clasifica {p['clasif_name']:<14s} ({adv})   EV {p['ev']:.1f}  [{p['conf']}]")

    print("\n▶ Generando el HTML self-contained")
    path = gen_html_ko.build(pred)
    print(f"   {os.path.relpath(path, HERE)}  ({os.path.getsize(path)//1024} KB)")
    print(f"\n✓ Listo. Abrí docs/mundial/{pred['out_name']} (offline salvo las banderas).")
    print(f"  Para publicar:  git add -A && git commit -m \"prode {pred['round']}\" && git push")


if __name__ == "__main__":
    main()
