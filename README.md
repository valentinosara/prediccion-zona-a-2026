# Primera Nacional (Argentina) — análisis y predicción

Tres proyectos independientes de fútbol argentino/mundial en un repo, cada uno
reproducible con su propio código y datos.

> ⚠️ **Aviso honesto:** las predicciones son un *escenario probable*, no un pronóstico
> cerrado. El ascenso de la B Nacional es de los torneos más impredecibles que hay
> (el modelo de Zona A explica ~14% de lo que pasa en el tramo restante). Léanse como
> un mapa de probabilidades — el número serio es la **probabilidad de campeón** del
> Monte Carlo, no la tabla final proyectada.

## Cómo está organizado

```
.
├── docs/                        # lo que publica GitHub Pages
│   ├── zona-a/                  #   predicción Zona A (interactiva)
│   ├── rachas/                  #   rachas históricas
│   └── mundial/                 #   prode del Mundial 2026 (por fecha/ronda)
│
├── prediccion-zona-a/           # predicción interactiva de la Zona A 2026
├── rachas-primera-nacional/     # análisis histórico de rachas de victorias
└── mundial-2026/                # prode del Mundial 2026
```

## Los proyectos

1. **[Predicción Zona A 2026](prediccion-zona-a/README.md)** — proyección fecha a
   fecha de cómo termina la tabla, con un modelo Poisson + Monte Carlo calibrado con
   valor de plantel (Transfermarkt) y forma (Promiedos).
   👉 **[Ver online](https://valentinosara.github.io/prediccion-zona-a-2026/zona-a/)**

2. **[Rachas históricas](rachas-primera-nacional/README.md)** — las 3 rachas más
   largas de victorias consecutivas por temporada (2010-2026).
   👉 **[Ver online](https://valentinosara.github.io/prediccion-zona-a-2026/rachas/)**

3. **[Prode del Mundial 2026](mundial-2026/README.md)** — predicción por fecha
   optimizada para **maximizar los puntos del prode** (cuotas de mercado + Dixon-Coles
   + Elo + xG real de FIFA + Monte Carlo). Fase de grupos y eliminatorias.
   👉 **[Ver Fecha 1](https://valentinosara.github.io/prediccion-zona-a-2026/mundial/fecha1.html)**

---

*Generado con código propio. Datos públicos de fútbol. Sin fines comerciales.*
