# Prode del Mundial 2026

Sistema (módulos `*_wc`) que predice **el prode del Mundial 2026** fecha a fecha con
Dixon-Coles + cuotas de mercado (de-vig) + Elo + xG real de FIFA + Monte Carlo. Fase de
grupos y eliminatorias.

👉 **[Ver Fecha 1](https://valentinosara.github.io/prediccion-zona-a-2026/mundial/fecha1.html)**

El prode reparte puntos por "casi acertar" (marcador exacto 12, ganador+diferencia u
empate 8, ganador 5, un equipo 2), así que el objetivo no es el marcador *más probable*
sino el que **maximiza los puntos esperados**.

## En criollo

1. **El mercado manda en el "quién gana".** Se bajan las cuotas (1X2, Over/Under,
   hándicap), se les quita el margen (*de-vig*) y quedan las probabilidades limpias.
   Es el mejor predictor que existe (~54% de acierto, muy difícil de superar).
2. **Dixon-Coles da la granularidad del marcador.** Un Poisson bivariado con corrección
   de marcadores bajos arma la matriz `P(h,a)` de cada partido, centrada en los goles
   esperados `λ` (mezcla convexa mercado↔Elo; el mercado pesa fuerte en la Fecha 1). Las
   marginales 1X2 de la matriz se anclan al mercado.
3. **El optimizador del prode elige la jugada.** Para cada partido se calcula `E[pts]` de
   cada marcador candidato sobre **toda** la distribución y se recomienda el máximo — por
   eso suele diferir del marcador más probable.
4. **Monte Carlo** (50.000 simulaciones por partido) confirma probabilidades y confianza.
   La fuerza base es **Elo internacional** (bonus modesto a los anfitriones); la **forma
   in-tournament** (Dixon-Coles con decaimiento temporal) gana peso fecha a fecha.

Sin ajustes a mano por opinión: los pesos salen de los datos/calibración. Se reporta la
**auto-evaluación honesta**: cuántos puntos del prode habría sacado el modelo en los
partidos de la fecha ya jugados (prediciéndolos con la info previa, sin fuga de datos).

## Cómo correrlo (un comando por fecha)

```bash
pip install -r ../requirements.txt
python update_wc.py --fecha 1     # genera ../docs/mundial/fecha1.html (pendientes de la F1)
python update_wc.py --fecha 2     # cuando termine la F1: re-fetch + re-fit + predice la F2
python update_wc.py --fecha 3
```

Cada corrida baja datos frescos (incluyendo resultados ya jugados), re-actualiza
ratings/forma, re-ancla al mercado vigente, **detecta** qué partidos de la fecha ya se
jugaron (calibran) vs cuáles faltan (se predicen), y regenera un HTML self-contained
(abrible offline) con tabla resumen, una tarjeta por partido (P(1X2), λ, marcador
recomendado resaltado, marcador más probable y ganador aparte, top-5, heatmap, confianza)
y la auto-evaluación de la fecha.

### Eliminatorias

```bash
python scrape_fifaphy.py            # 1) bajá el xG de la ronda recién jugada
python update_ko.py --ronda octavos # 2) predecí la siguiente ronda + generá el HTML
```

Genera `../docs/mundial/<ronda>.html` (16avos.html, octavos.html, cuartos.html,
semifinales.html, tercer_puesto.html, final.html).

## Predecir un partido YA, cargando las cuotas a mano (sin fetch)

Si la red está bloqueada (o querés la jugada al toque), no hace falta esperar al fetch:
leés las cuotas de cualquier casa y `predict_cli.py` te da la recomendación con el mismo
motor (de-vig → Dixon-Coles → puntos esperados → Monte Carlo).

```bash
# Un partido (1X2; opcional Over/Under 2.5 y hándicap asiático):
python predict_cli.py --home "Brasil" --away "Japón" \
    --h2h 1.50 4.10 6.90 --ou 2.5 1.83 1.97 --ah -1.25 1.93 1.93 \
    --book Pinnacle --kickoff 14:00 --hflag BR --aflag JP

# Varios partidos del día + página HTML (../docs/mundial/hoy.html):
python predict_cli.py --file hoy.json --html
```

Devuelve P(1X2) de-vigada, los λ por equipo, el **marcador recomendado para el prode**
(máx. puntos esperados), el más probable aparte, el top-5 y la confianza. Es la vía más
robusta cuando no hay salida de red: el mercado es la señal dominante y vos se la das.

## Fuentes y whitelist de red

El sistema **baja todo solo** por fetch automático, con **caché** local y **fallback**:

| Señal | Fuente primaria (sin key) | Fallbacks |
|---|---|---|
| Fixtures / resultados / estado | ESPN scoreboard (`site.api.espn.com`) | caché · seed |
| Grupos A–L (draw real) | ESPN standings (`site.api.espn.com`) | tabla anclada en `fetch_wc.py` |
| Cuotas (1X2/O-U/AH) | ESPN core API (`sports.core.api.espn.com`) | The Odds API (`ODDS_API_KEY`) · caché · seed |
| Fuerza (Elo) | eloratings.net (`World.tsv` + `en.teams.tsv`) | caché · seed |

Los parsers están **validados contra los esquemas reales del Mundial 2026**: los moneyline
americanos de ESPN se convierten a decimal y se de-vigan; los horarios de ESPN (UTC) se
guardan en **hora de Argentina (ART, UTC-3)**; el cruce de nombres entre fuentes (ESPN usa
inglés, eloratings su propio código) se resuelve por código FIFA-3 + alias normalizados.

Este sistema **baja todo solo**. Si la política de red bloquea un dominio (o está caído),
esa señal corre en **modo degradado** con el último caché o con el **seed versionado**
(`data_mundial/seed/`, que ya contiene **datos reales**) y el HTML lo avisa arriba.
Whitelist mínima a habilitar:

```
site.api.espn.com
sports.core.api.espn.com
www.eloratings.net
api.the-odds-api.com   (opcional, solo si usás ODDS_API_KEY)
```

> Las cuotas primarias salen de ESPN **sin API key**. Para forzar Pinnacle vía The Odds
> API (opcional): `export ODDS_API_KEY=tu_key`. El seed real se regenera con
> `python fetch_wc.py --build-seed` (baja equipos, grupos, fixtures, resultados y cuotas).

## Archivos del sistema (`*_wc`)

```
fetch_wc.py        fetch + caché + fallback (fixtures/resultados, cuotas, Elo)
ratings_wc.py      Elo + forma ponderada por tiempo → λ por selección
market_wc.py       de-vig de cuotas → P(1X2), supremacía s, total μ, λ de mercado
model_wc.py        Dixon-Coles + blend mercado↔modelo → matriz P(h,a)
prode_wc.py        función puntos() + optimizador de puntos esperados
montecarlo_wc.py   simulaciones por partido + nivel de confianza
predict_wc.py      orquesta una fecha → data_mundial/pred_wc.json + state.json
gen_html_wc.py      arma ../docs/mundial/fechaN.html (self-contained)
backtest_wc.py     auto-evaluación: puntos del prode en partidos ya jugados
predict_cli.py     predecir cargando las cuotas a mano (sin fetch) → texto / HTML
show_wc.py         muestra por consola las jugadas ya calculadas (lee pred_wc.json)
scrape_fifaphy.py  baja el xG REAL de la API de FIFA (Playwright→requests) y lo pega al seed
analyze_fifaphy.py valida el efecto del xG real sobre la forma (goles vs xG)
analyze_real.py    analiza la Fecha 1 real (xG/calibración) — modelo viejo vs nuevo
update_wc.py       ⭐ un comando: --fecha N → fetch + fit + predict + html
knockout_wc.py     predicción de rondas eliminatorias (inter-grupo, 120', penales)
gen_html_ko.py     arma ../docs/mundial/<ronda>.html (self-contained)
update_ko.py       ⭐ un comando: --ronda X → fetch + fit + predict + html (eliminatorias)
data_mundial/      seed/ (datos reales), real/ (Fecha 1 + xG para el análisis), cache/, ...
```

> Consola rápida del día: `python show_wc.py` (o `--dia YYYY-MM-DD`, `--match <equipo>`,
> `--all`). Muestra la jugada recomendada, el de-vig del mercado, el top-5 por puntos
> esperados y la confianza — idéntico a lo que sale en el HTML, con su procedencia.

## Mejoras del modelo con datos reales (xG y calibración del total)

Tras la Fecha 1 **real** del Mundial 2026 se ajustaron tres cosas — guiadas por los datos,
no a dedo (`analyze_real.py` compara modelo viejo vs nuevo sobre los partidos jugados):

1. **Fuerza desde xG, no desde goles crudos.** El rendimiento que actualiza atk/def de cada
   selección se mide con **expected goals (xG)**, mucho menos ruidoso que el marcador. Caso
   real: *Países Bajos 2-2 Japón* terminó 2-2 pero el xG fue **0.79–0.54**; con goles crudos
   el ataque de Japón saltaba a ×1.6, con xG queda ×1.0 (lo correcto). El xG también templa
   la magnitud del update de Elo. (`ratings_wc`, peso `XG_WEIGHT`; campos `home_xg`/`away_xg`.)
2. **Total de goles calibrado de lo jugado.** En vez de un total fijo 2.6, el baseline `mu0`
   se estima de los partidos disputados (la Fecha 1 promedió ~3.5 goles). (`calibrate_totals`,
   ridge hacia el prior: con pocos partidos manda el prior, se afina solo fecha a fecha.)
3. **Potencial de goleada en cruces desnivelados.** El total esperado sube —de forma
   *saturada*— con la diferencia de Elo: el modelo viejo no podía predecir un *Alemania 7-1
   Curaçao* (xG real ~3.9); ahora a esos cruces les asigna un total mayor. (`match_total`.)

Efecto en el backtest del prode sobre la Fecha 1 real (solo-modelo, sin cuotas): de
**32 → 40 / 120** puntos y mejor calibración del total (log-loss 2.22 → 2.04).

> **xG real automatizado:** `python scrape_fifaphy.py` baja el xG oficial de FIFA (la fuente
> detrás de [fifaphy](https://fifaphy.vercel.app/), sin API key) y lo pega como
> `home_xg`/`away_xg` sobre los fixtures jugados del seed. Detalle de la fuente, la API y la
> utilidad de cada métrica en [`REPORTE_FIFAPHY.md`](REPORTE_FIFAPHY.md). Otras fuentes de xG
> válidas: Opta/TheAnalyst, Sofascore, FBref. (Sin xG, el modelo cae a goles crudos sin romperse.)

## Limitaciones

- El Mundial tiene **muestras chicas y mucha varianza**: la Fecha 1 se apoya casi toda
  en el mercado. El número serio es la probabilidad y el `E[pts]`, no el marcador puntual.
- Los esquemas de los endpoints en vivo **pueden cambiar**; por eso el fetch es resiliente
  y cae a caché/seed sin romperse (y el HTML avisa la procedencia de cada dato).
- El **seed** versionado contiene **datos reales** del Mundial 2026 (48 selecciones, 12
  grupos A–L, 72 fixtures con horario ART, resultados ya jugados y cuotas), bajados de
  ESPN + eloratings. Es el anclaje para correr sin red; con red, el fetch lo refresca.
