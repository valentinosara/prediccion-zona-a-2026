# Rachas históricas — Primera Nacional

Análisis histórico de rachas de victorias consecutivas en la Primera Nacional
(2da división del fútbol argentino), 2010-2026: las 3 rachas más largas por temporada.

👉 **[Ver online](https://valentinosara.github.io/prediccion-zona-a-2026/rachas/)**

## Archivos

```
scrape_playwright.py   # baja resultados de worldfootball (vía navegador, por Cloudflare)
analyze.py             # algoritmo de rachas (longest run de victorias)
teams.py               # normalización de nombres de equipos
build.py               # pipeline → data/results.json
gen_html.py            # arma rachas_primera_nacional.html (y lo copia a ../docs/rachas/)
fetch.py               # fetcher con caché (worldfootball)
data/                  # resultados crudos (worldfootball) por temporada
```

> **Nota cross-project:** `data/` de esta carpeta es **reusada** por
> `../prediccion-zona-a/backtest.py` para calibrar el peso forma↔plantel del modelo de
> Zona A (2021-2025). No la muevas ni la renombres sin actualizar esa referencia.

`gen_html.py` ahora, además de escribir el HTML local, copia el resultado a
`../docs/rachas/index.html` (el sitio que publica GitHub Pages).

## Requisitos

```bash
pip install playwright && playwright install chromium
```

## Fuente

- **worldfootball.net** — resultados históricos partido a partido, 2010-2026.
