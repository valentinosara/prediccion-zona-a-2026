# PROMPT — Sistema de predicción para el prode del Mundial 2026

> Pegá todo lo que sigue (desde "ROL" hasta el final) como primer mensaje de una sesión nueva.
> Está pensado para correr en este mismo repo, reutilizando los patrones que ya existen
> (`predict_zonaA.py`, `gen_pred_html.py`, `update.py`): Poisson de ataque/defensa, Monte Carlo
> vectorizado, **puntos esperados** (no "el marcador más probable"), HTML self-contained y
> actualización de un comando. Stack: Python + numpy/scipy + requests, sin frameworks pesados.

---

## ROL

Sos un ingeniero de datos y modelador estadístico de fútbol. Tu trabajo es construir el
**mejor sistema posible para acertar resultados del prode del Mundial 2026**: primero el
**ganador** de cada partido, y después el **marcador exacto en goles** — pero optimizado para
**maximizar los puntos del prode**, no para mostrar el marcador "más probable" a secas (no es lo
mismo, ver §4). El sistema tiene que ser honesto sobre su incertidumbre (es fútbol), reproducible
con código, y servir como **referencia confiable** fecha a fecha.

Hoy es **14 de junio de 2026**. El Mundial 2026 (48 selecciones, 12 grupos de 4, sedes USA/Canadá/México)
arrancó el 11/jun. La **Fecha 1 de la fase de grupos está en curso**: varios partidos ya se jugaron y
otros faltan. Tu **entregable inmediato** es predecir **los partidos que quedan de la Fecha 1**. Después,
cuando termine la Fecha 1, el mismo sistema se reusa para la Fecha 2 y la Fecha 3 (un comando por fecha).

---

## 1. CONTEXTO Y REGLAS DEL PRODE (lo más importante de respetar)

Se predice el **marcador de cada partido** (90' de fase de grupos; sin alargue ni penales en grupos).
El puntaje por partido es **el mayor que corresponda** (NO se acumulan):

| Resultado | Puntos |
|---|---|
| ⚽ Marcador exacto (predije 2–1 y fue 2–1) | **12** |
| 📊 Ganador correcto **+ misma diferencia de goles** (predije 2–1, fue 3–2) | **8** |
| 📊 Empate correcto (predije empate y fue empate, sin importar los goles) | **8** |
| ✅ Ganador correcto sin acertar la diferencia (predije 2–1, fue 3–0) | **5** |
| 🔢 Goles exactos de **uno** de los dos equipos | **2** |
| ❌ Predicción incorrecta | **0** |

> Hay además un bonus de eliminatorias (penales, +3 a quién clasifica) y un "Podio ideal"
> pre-torneo (campeón 20 / subcampeón 10 / tercero 6). Esos quedan como **módulos opcionales**
> (§9): el podio ya está cerrado porque el torneo empezó, y la fase de grupos no tiene penales.
> El foco ahora es **maximizar puntos por partido en la fase de grupos**.

**Implicancia central:** como el prode reparte puntos por "casi acertar" (misma diferencia, ganador,
un equipo), el marcador óptimo para anotar **NO** es necesariamente el de mayor probabilidad puntual.
Hay que elegir, para cada partido, el marcador que **maximiza los puntos esperados** sobre toda la
distribución de marcadores (§4). Esto es exactamente la misma idea que ya usás en `predict_zonaA.py`
("la tabla usa **puntos esperados**, no el sesgo del modo"), pero con la **función de puntaje del
prode** en lugar de los 3/1/0 de la liga.

---

## 2. QUÉ SE USA A NIVEL PROFESIONAL (y qué vas a implementar)

Investigado y elegido por efectividad. El sistema combina tres señales y las funde en una
distribución de marcadores por partido:

**a) Cuotas de mercado (la señal MÁS precisa que existe).**
La evidencia académica es consistente: las cuotas de las casas de apuestas son el mejor predictor
disponible (~54% de acierto de resultado, muy difíciles de superar). Pinnacle es la casa más
"afilada". Vas a:
- Bajar cuotas **1X2**, **Over/Under 2.5** y **hándicap asiático** por partido.
- **Quitar el margen** (de-vig / quitar el "overround") para obtener probabilidades implícitas
  limpias de local / empate / visita.
- Derivar del mercado la **supremacía** `s = λ_local − λ_visita` (de la línea de hándicap) y el
  **total esperado** `μ = λ_local + λ_visita` (de la línea de Over/Under), y de ahí
  `λ_local = (μ+s)/2`, `λ_visita = (μ−s)/2`. Si hay cuotas de **marcador exacto**, usalas directo.

**b) Ratings de fuerza (ancla estructural, y fallback si falta cuota).**
- **Elo internacional** (World Football Elo, eloratings.net) como ancla principal de fuerza —
  cubre selecciones y se actualiza partido a partido.
- **Ranking FIFA** como señal secundaria.
- **Forma reciente**: goles a favor/en contra ponderados por **decaimiento temporal** (Dixon-Coles,
  los partidos viejos pesan menos) → fuerzas de ataque/defensa por selección, calibradas sobre
  históricos de partidos internacionales (amistosos + eliminatorias + Mundial 2026 a medida que se juega).
- Opcionales si son scrapeables: **Opta Power Rankings** (theanalyst.com), **valor de plantel** (Transfermarkt).

**c) Modelo de goles Dixon-Coles (el corazón del marcador exacto).**
El estándar de la industria para marcadores: Poisson bivariado con la **corrección τ de marcadores
bajos** (ρ) que arregla la subestimación de 0–0 / 1–1 / 1–0 / 0–1 del Poisson simple. Produce la
**matriz de probabilidad de marcadores** `P(h,a)` (h,a = 0..~10) por partido. **Localía ≈ neutral**
en el Mundial (campos neutrales), salvo un **bonus modesto para anfitriones** (USA/Canadá/México)
cuando juegan de "locales".

**d) Ensemble / blend.**
- Construí `P(h,a)` con Dixon-Coles a partir de los λ.
- **Anclá las marginales 1X2 de esa matriz a las del mercado de-vigado** (re-escalá/ajustá para que
  P(local)/P(empate)/P(visita) de la matriz coincidan con el mercado — el mercado manda en el "quién
  gana", el modelo aporta la **granularidad del marcador**).
- Donde haya buenos λ de mercado (supremacía+total), usá esos como centro; donde falte cuota de un
  partido, caé al modelo Elo/forma. La mezcla final es una **combinación convexa** mercado↔modelo
  (en la Fecha 1, con casi nada de datos del torneo, **el mercado pesa fuerte**; a medida que se
  juegan fechas, la forma in-tournament gana algo de peso).

**e) Monte Carlo.**
50.000 simulaciones por partido muestreando `P(h,a)` → probabilidades robustas, intervalos y nivel de
confianza. (Reusá el patrón vectorizado de `montecarlo()` en `predict_zonaA.py`.) Opcional: simular el
torneo completo para el módulo de podio (§9).

> Por qué esta combinación: el mercado da la **mejor probabilidad de resultado** (lo que pediste
> primero: el ganador), Dixon-Coles da la **mejor distribución de marcadores** (lo segundo: el goleo),
> y el ensemble + Monte Carlo lo hace **robusto y calibrado**. Es, en esencia, lo que hace el "Opta
> Supercomputer" (cuotas de mercado + power ratings + miles de simulaciones), adaptado a tu prode.

---

## 3. ANCLAJE A DATOS REALES — "SOLO FETCH AUTOMÁTICO"

El sistema **baja todo solo** cada vez que corre (decisión del usuario). Por eso necesitás fuentes
concretas, **caché local** y **fallbacks** (con fetch automático, la resiliencia es parte del pipeline,
no carga manual). Verificá y adaptá los endpoints al construir (cambian seguido).

**Fixtures, resultados y estado de la Fecha 1:**
- ESPN hidden API (sin key): `https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=YYYYMMDD` → fixtures y resultados por día. Buen primario.
- `football-data.org` (API key gratis, competición *FIFA World Cup*).
- API-Football / api-sports.io (key, tier gratis; tiene fixtures, **cuotas** y hasta predicciones).
- Fallback: Wikipedia / Wikidata (tablas de grupos 2026).

**Cuotas (la señal clave):**
- The Odds API — `the-odds-api.com`, key gratis (500 req/mes), deporte `soccer_fifa_world_cup`, mercados `h2h` (1X2), `totals` (O/U) y `spreads` (hándicap), de varias casas. Preferí **Pinnacle** si está.
- API-Football odds endpoint como alternativa.
- Fallback: scrape de OddsPortal / oddschecker.

**Fuerza:**
- Elo internacional: `eloratings.net` (parseá la tabla de ratings actuales por selección).
- Ranking FIFA: `inside.fifa.com/fifa-world-ranking` o un CSV espejo.
- Opcional: Opta Power Rankings (theanalyst.com), Transfermarkt (valor de plantel).

**Resiliencia obligatoria:**
- Guardá cada fetch exitoso en `data_mundial/cache/` (JSON con timestamp). Si una fuente falla en una
  corrida, usá el último caché y **avisalo en el HTML** ("dato del mercado al HH:MM, fuente X").
- Implementá reintentos con backoff y *rate limiting* respetuoso.
- **Requisito de entorno:** este sistema necesita salida de red hacia esos dominios. Si la política de
  red del entorno los bloquea, documentá en el README la whitelist necesaria; mientras tanto, el
  sistema corre en **modo degradado** con el último caché (o, en última instancia, un `seed` de datos
  mínimos versionado en el repo para poder probar el pipeline end-to-end).

---

## 4. EL OPTIMIZADOR DEL PRODE (núcleo — implementalo con exactitud)

Dada la matriz `P(h,a)` de un partido, para **cada predicción candidata** `(ph,pa)` con `ph,pa ∈ 0..6`,
calculá el **valor esperado de puntos**:

```
E[pts | predigo (ph,pa)] = Σ_{ah,aa} P(ah,aa) · puntos((ph,pa),(ah,aa))
```

y recomendá el `(ph,pa)` que **maximiza** ese valor. La función de puntaje (exacta, de §1):

```python
import numpy as np

def puntos(pred, real):
    ph, pa = pred; ah, aa = real
    if ph == ah and pa == aa:            # marcador exacto
        return 12
    pred_dir = np.sign(ph - pa); real_dir = np.sign(ah - aa)
    same_dir  = (pred_dir == real_dir)
    same_diff = ((ph - pa) == (ah - aa))
    # 8: empate correcto (ambos empate) o ganador correcto + misma diferencia
    if same_dir and (real_dir == 0 or same_diff):
        return 8
    # 5: ganador correcto sin la diferencia (real es decisivo y acerté el lado)
    if same_dir:
        return 5
    # 2: goles exactos de exactamente uno de los dos equipos
    if (ph == ah) ^ (pa == aa):
        return 2
    return 0
```

Implementación eficiente: precomputá una vez la matriz de puntos `Pts[ph,pa,ah,aa]` (7×7×11×11) y hacé
`E[pts](ph,pa) = Σ Pts[ph,pa] ⊙ P` con numpy → elegís el argmax. Reportá por partido:

1. **Ganador más probable** (lo que el usuario pidió primero): de las marginales 1X2 de `P` (ancladas al
   mercado) → P(local)/P(empate)/P(visita) y el lado favorito.
2. **Marcador recomendado para el prode** (el argmax de puntos esperados) — **resaltado**, es la jugada.
3. **Marcador más probable** (el modo de `P`) — mostralo aparte, porque suele diferir del óptimo del prode.
4. **Top-5 marcadores candidatos** ordenados por puntos esperados (con su probabilidad y su E[pts]).
5. **Confianza**: entropía del 1X2 y/o brecha de E[pts] entre la 1ª y la 2ª opción (cuán "clara" es la jugada).

> Detalle típico: en partidos parejos el óptimo del prode suele ser un marcador bajo y "central"
> (1–0, 1–1, 2–1) porque cubre muchos escenarios de 8/5/2 puntos; en partidos muy desnivelados se
> estira (2–0, 3–0). Que lo decida el cálculo, no la mano.

---

## 5. ACTUALIZACIÓN FECHA A FECHA

- **Estado persistente** en `data_mundial/state.json`: ratings Elo actualizados hasta el último partido
  jugado, historial de partidos del torneo, y las predicciones emitidas (para auto-evaluación).
- Comando único, estilo `update.py` del repo:
  ```bash
  python update_wc.py --fecha 1     # genera docs/mundial_fecha1.html (partidos pendientes de la F1)
  python update_wc.py --fecha 2     # cuando termine la F1: re-fetch + re-fit + predice la F2
  python update_wc.py --fecha 3
  ```
  Cada corrida: (1) baja datos frescos incluyendo **resultados ya jugados**, (2) **re-actualiza los
  ratings/forma con esos resultados** (Elo update + decaimiento temporal — así la F2 refleja lo que
  pasó en la F1), (3) re-anclar al mercado vigente, (4) predice los **partidos pendientes** de la fecha
  pedida, (5) regenera el HTML.
- Detectá automáticamente, dentro de la fecha pedida, **qué partidos ya se jugaron** (no se predicen,
  se usan para calibrar) vs **cuáles faltan** (se predicen).

---

## 6. VALIDACIÓN Y HONESTIDAD (lo que lo hace "confiable")

- **Auto-evaluación / backtest** (estilo `backtest.py`): con los partidos de la Fecha 1 **ya jugados**,
  calculá **cuántos puntos del prode habría sacado el modelo** (aplicando §4 a cada uno) y mostralo. Es
  la métrica honesta de "qué tan confiable es esto".
- **Calibración**: Brier score y log-loss del 1X2 contra resultados reales; reliability diagram contra
  el mercado. Si el modelo está sistemáticamente sesgado, recalibrá (p. ej. Platt/isotónica).
- **Aviso honesto** en el HTML (como ya hacés en el README de la Zona A): esto es un **mapa de
  probabilidades**, no una certeza; el fútbol es alta varianza; el número serio es la probabilidad, no
  el marcador puntual. Mostrá el nivel de confianza por partido y por fecha.

---

## 7. SALIDA: HTML SELF-CONTAINED Y PULIDO (front simple, back pesado)

Un único archivo HTML por fecha (`docs/mundial_fecha1.html`, etc.), **autocontenido** (CSS y JS embebidos,
sin servidor, **descargable y abrible offline**), responsive, en **español**, con diseño moderno y limpio
(seguí el estilo y la calidad de `gen_pred_html.py`). Contenido:

**Encabezado:** título, fecha de generación, "datos al HH:MM", fuentes usadas, nivel de confianza global
de la fecha, y el aviso honesto.

**Tabla resumen de la fecha:** todos los partidos pendientes, con la **predicción recomendada** y los
**puntos esperados** de cada una; total de puntos esperados de la fecha.

**Tarjeta por partido:**
- Equipos (con banderas/escudos si los conseguís), grupo, día y hora de cierre (1 min antes del inicio).
- Barra de **P(local) / P(empate) / P(visita)** y el favorito.
- **λ esperados** por selección (goles).
- **Marcador recomendado para el prode** (resaltado) + puntos esperados.
- **Marcador más probable** (aparte) y **ganador más probable**.
- **Top-5 alternativas** (marcador · probabilidad · puntos esperados).
- **Heatmap** de la matriz `P(h,a)` (SVG inline o canvas; sin dependencias externas).
- Etiqueta de **confianza** (alta/media/baja) y, si aplica, "dato de mercado cacheado".

**Pie:** metodología en criollo (2–3 párrafos: cuotas + Dixon-Coles + puntos esperados + Monte Carlo),
limitaciones, y resultado de la auto-evaluación de la Fecha 1 ya jugada.

> Mantené el front simple pero **el back y la analítica deben ser de primer nivel**: el HTML es solo el
> visor de un motor probabilístico serio.

---

## 8. STACK Y ESTRUCTURA (consistente con el repo)

Python + `numpy` + `scipy` + `requests` (+ `beautifulsoup4`/`lxml` si scrapeás). Sin frameworks pesados.
Reutilizá lo que ya funciona del repo: la calibración Poisson MLE de `predict_zonaA.py`, el Monte Carlo
vectorizado, y el generador HTML de `gen_pred_html.py`.

```
.
├── fetch_wc.py         # fetch + caché: fixtures/resultados, cuotas, Elo, ranking FIFA (con fallbacks)
├── ratings_wc.py       # Elo + forma ponderada por tiempo → fuerzas atk/def por selección
├── market_wc.py        # de-vig de cuotas → P(1X2), supremacía s, total μ, λ de mercado
├── model_wc.py         # Dixon-Coles + blend mercado↔modelo → matriz P(h,a) por partido
├── prode_wc.py         # función puntos() + optimizador de puntos esperados (§4)
├── montecarlo_wc.py    # simulaciones por partido (+ torneo opcional, §9)
├── predict_wc.py       # orquesta una fecha → data_mundial/pred_wc.json
├── gen_html_wc.py      # arma docs/mundial_fechaN.html (self-contained)
├── backtest_wc.py      # auto-evaluación: puntos del prode en partidos ya jugados (§6)
├── update_wc.py        # ⭐ un comando: --fecha N → fetch + fit + predict + html
└── data_mundial/       # caché, state.json (ratings/historial), salidas json
```

Entregá `requirements.txt` y actualizá el `README.md` con: cómo correrlo, fuentes, whitelist de red
necesaria, y limitaciones honestas. **No hardcodees fechas ni resultados**: todo sale del fetch/estado.

---

## 9. MÓDULOS OPCIONALES (si sobra tiempo, no son el foco ahora)

- **Podio ideal** (campeón 20 / sub 10 / 3º 6): simulá el torneo completo (bracket de 48 → 32 → ...) con
  Monte Carlo para dar probabilidades de campeón/finalista/podio. Nota: la predicción del podio ya está
  **cerrada** (el torneo empezó); sirve como referencia y para futuras ediciones.
- **Bonus de eliminatorias** (+3 a quién clasifica por penales): relevante recién en octavos.

---

## 10. ENTREGABLE INMEDIATO Y CRITERIOS DE ACEPTACIÓN

**Entregá ahora:** `python update_wc.py --fecha 1` corriendo end-to-end y generando
`docs/mundial_fecha1.html` con las predicciones de **los partidos que faltan de la Fecha 1**. Debe cumplir:

- [ ] Baja datos reales por fetch automático (con caché/fallback) y **detecta** qué partidos de la F1 ya
      se jugaron vs cuáles faltan.
- [ ] Por cada partido pendiente: P(1X2) anclada al mercado, λ por equipo, **marcador recomendado para el
      prode** (máx puntos esperados) resaltado, marcador más probable y ganador más probable aparte,
      top-5 alternativas con puntos esperados, heatmap y confianza.
- [ ] Tabla resumen de la fecha con recomendaciones y puntos esperados totales.
- [ ] **Auto-evaluación**: cuántos puntos del prode habría sacado el modelo en los partidos de la F1 ya
      jugados (con la función de §1).
- [ ] HTML self-contained, responsive, en español, pulido, descargable, con metodología y aviso honesto.
- [ ] Código limpio y comentado, consistente con el repo; `README` y `requirements.txt` actualizados;
      `update_wc.py` reutilizable tal cual para `--fecha 2` y `--fecha 3`.
- [ ] Commit y push a la rama de trabajo.

**Antes de codear:** confirmá brevemente el plan (fuentes elegidas + arquitectura del modelo), después
implementá. Si una fuente de datos no responde, dejá el pipeline funcionando con caché/seed y documentá
qué whitelist de red hace falta — no bloquees el entregable por una API caída.

---

### Recordatorio de filosofía (la del repo)

Sin ajustes "a mano" por opinión. Los pesos salen de los datos/calibración, no del dedo. Se reporta la
**incertidumbre** de frente. El número serio es la **probabilidad** y el **valor esperado de puntos**, no
el marcador puntual. El HTML es lindo pero simple; **la inteligencia está en el back**.
