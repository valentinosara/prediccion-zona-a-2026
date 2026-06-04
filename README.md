# Primera Nacional (Argentina) — análisis y predicción

Dos cosas en un repo, ambas reproducibles con código y datos:

1. **Predicción interactiva de la Zona A 2026** — proyección fecha a fecha de cómo
   termina la tabla, con un modelo estadístico calibrado.
   👉 **[Ver online](https://valentinosara.github.io/prediccion-zona-a-2026/)**
2. **Rachas históricas** — las 3 rachas más largas de victorias consecutivas por
   temporada (2010-2026).
   👉 **[Ver online](https://valentinosara.github.io/prediccion-zona-a-2026/rachas.html)**

> ⚠️ **Aviso honesto:** la predicción es un *escenario probable*, no un pronóstico
> cerrado. El ascenso de la B Nacional es de los torneos más impredecibles que hay
> (el modelo explica ~14% de lo que pasa en el tramo restante). Léela como un mapa
> de probabilidades — el número serio es la **probabilidad de campeón** del Monte
> Carlo, no la tabla final proyectada.

---

## La predicción, en criollo

- Se parte de los **resultados reales** ya jugados (Promiedos).
- Un modelo **Poisson de ataque/defensa + localía** estima cada partido que falta.
- La tabla proyectada usa **puntos esperados** (no "el resultado más probable", que
  infla los triunfos locales). Las probabilidades de campeón / Reducido / descenso
  salen de **20.000 simulaciones Monte Carlo** de la temporada completa.
- **Cuánto pesa el plantel:** el valor de mercado (Transfermarkt) se mezcla con la
  forma. El peso **no fue elegido a dedo**: surge de un *backtest* 2021-2025
  (`backtest.py`) que mide cuánto suma el valor de plantel **por encima** de la forma
  ya mostrada, a esta misma altura del torneo. Resultado: **forma ~68% / plantel ~32%**.
  El sitio permite mover ese peso (solo forma / calibrado / plantel alto) para ver la
  sensibilidad.

## Cómo está organizado

```
.
├── docs/                     # lo que publica GitHub Pages
│   ├── index.html            #   predicción Zona A (interactiva)
│   └── rachas.html           #   rachas históricas
├── data/                     # resultados crudos (worldfootball) por temporada
├── data_promiedos/           # fixture/tabla (Promiedos), valores y escudos, salidas del modelo
│
│  # --- Predicción Zona A 2026 ---
├── scrape_promiedos.py       # baja resultados+fixture de la API de Promiedos
├── prep_zonaA.py             # arma el fixture de Zona A (incluye deducir la fecha sin publicar)
├── backtest.py               # calibra el peso forma↔plantel con 2021-2025
├── predict_zonaA.py          # modelo Poisson + Monte Carlo → pred_results.json
├── gen_pred_html.py          # arma docs/index.html
├── update.py                 # ⭐ corre todo lo anterior de una sola vez
│
│  # --- Rachas históricas ---
├── scrape_playwright.py      # baja resultados de worldfootball (vía navegador, por Cloudflare)
├── analyze.py                # algoritmo de rachas (longest run de victorias)
├── teams.py                  # normalización de nombres de equipos
├── build.py                  # pipeline → results.json
├── gen_html.py               # arma docs/rachas.html
└── fetch.py                  # fetcher con caché (worldfootball)
```

## Actualizar después de una fecha

La API de Promiedos responde sin bloqueos, así que la predicción se actualiza con
**un comando**:

```bash
python update.py
git add -A && git commit -m "update fecha" && git push
```

`update.py` baja los resultados nuevos, recalibra, regenera el HTML y lo copia a
`docs/index.html`. Al hacer `push`, **GitHub Pages re-deploya solo** (~1 min) y el
link no cambia.

> Nota: `scrape_promiedos.py` usa un header de versión de la app de Promiedos
> (`x-ver`). Si algún día la API deja de responder, hay que actualizar ese valor
> (es una línea).

## Requisitos

```bash
pip install requests numpy beautifulsoup4 lxml
# El pipeline de rachas (worldfootball) además usa Playwright por el Cloudflare:
#   pip install playwright && playwright install chromium
```

## Fuentes

- **Promiedos** — resultados y fixture de la Primera Nacional 2026.
- **Transfermarkt** — valor de mercado y edad de los planteles (2021-2026).
- **worldfootball.net** — resultados históricos partido a partido (rachas).
- Contexto (DTs, entrevistas): Doble Amarilla, El Gráfico, Infobae.

## Limitaciones (para no engañar a nadie)

- El modelo ve **forma y jerarquía de plantel**, no lesiones puntuales, clima,
  arbitrajes ni el contexto fino de cada partido.
- Con ~15 fechas la señal todavía es ruidosa: una sola jornada puede mover bastante
  la tabla final proyectada. Eso es del torneo, no un bug.
- El valor de plantel de Transfermarkt en esta categoría es aproximado (mercado poco
  líquido), pero captura bien la **jerarquía relativa**, que es lo que aporta.

---

*Generado con código propio. Datos públicos de fútbol. Sin fines comerciales.*
