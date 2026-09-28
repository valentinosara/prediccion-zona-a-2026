"""gen_html_ko.py - HTML self-contained y publicable de una ronda eliminatoria, a partir
del dict que devuelve knockout_wc.predict_round. Escribe ../docs/mundial/<out_name> (un
archivo por ronda: octavos.html, cuartos.html, ...).
"""
import os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "..", "docs", "mundial")

# Track record del algoritmo en fase de grupos (backtest honesto sin fuga; ver groups_perf).
PERF_GRUPOS = {"pct": 41.6, "win": 67, "fechas": [(1, 26.4), (2, 44.1), (3, 54.2)]}

MESES = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
CONF = {"alta": ("#16a34a", "Alta"), "media": ("#d97706", "Media"), "baja": ("#dc2626", "Baja")}


def _flag(iso):
    return f"https://flagcdn.com/w40/{iso.lower()}.png"


def _when(ko):
    try:
        dt = datetime.fromisoformat(ko)
        return f"{DIAS[dt.weekday()]} {dt.day} {MESES[dt.month]} · {dt.hour:02d}:{dt.minute:02d}h"
    except (ValueError, TypeError):
        return ""


def _card(p):
    cc, cl = CONF[p["conf"]]
    ah, aw = p["adv_home"] * 100, p["adv_away"] * 100
    rec = f'{p["rec"][0]} <span class="dash">–</span> {p["rec"][1]}'
    book = f'cuotas {p["book"]}' if p["book"] else "modelo Elo (sin cuotas)"
    return f"""
    <article class="card">
      <div class="teams">
        <div class="team"><img src="{_flag(p['home'])}" alt=""><span>{p['home_name']}</span></div>
        <div class="vs">vs</div>
        <div class="team right"><span>{p['away_name']}</span><img src="{_flag(p['away'])}" alt=""></div>
      </div>
      <div class="when">{_when(p['kickoff'])}</div>
      <div class="advbar" title="Probabilidad de avanzar a la próxima ronda">
        <div class="adv-home" style="width:{ah:.1f}%">{ah:.0f}%</div>
        <div class="adv-away" style="width:{aw:.1f}%">{aw:.0f}%</div>
      </div>
      <div class="advlbl"><span>avanza {p['home_name']}</span><span>avanza {p['away_name']}</span></div>
      <div class="rec">
        <div class="rec-score">{rec}</div>
        <div class="rec-tag">marcador a cargar</div>
      </div>
      <div class="chips">
        <span class="chip clasif">🏅 Clasifica: <b>{p['clasif_name']}</b></span>
        <span class="chip">🥅 Penales: <b>{p['ppen']*100:.0f}%</b></span>
        <span class="chip">📈 EV: <b>{p['ev']:.1f}</b></span>
        <span class="chip conf" style="--c:{cc}">{cl}</span>
      </div>
      <div class="src">{book}</div>
    </article>"""


def build(pred, perf=PERF_GRUPOS):
    """Genera el HTML de la ronda y lo escribe en ../docs/mundial/<out_name>. Devuelve la ruta."""
    preds = pred["preds"]
    cards = "\n".join(_card(p) for p in preds)
    ev_total = sum(p["ev"] for p in preds)
    gen = datetime.fromisoformat(pred["generado"]).strftime("%d/%m/%Y %H:%M")
    perf_f = " · ".join(f"F{n} {v:.0f}%" for n, v in perf["fechas"])
    titulo = f"Mundial 2026 · {pred['round'].title()}"
    pending = ""
    if pred.get("tbd"):
        pending = (f'  <div class="pending">⏳ <b>{pred["tbd"]} cruce(s)</b> de {pred["round"]} '
                   f'todavía sin definir — se completan cuando terminen los 16avos que faltan. '
                   f'Por ahora hay <b>{len(preds)}</b> partido(s) confirmado(s); volvé a correr el '
                   f'comando a medida que se jueguen.</div>\n')

    html = f"""<!DOCTYPE html>
<html lang="es-AR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo} — Pronóstico del Prode</title>
<style>
  :root {{ --bg:#0b1020; --card:#151b30; --line:#26304d; --txt:#e8ecf6; --mut:#9aa6c4;
          --home:#3b82f6; --away:#ef4444; --acc:#22d3ee; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt);
         font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:0 18px 60px; }}
  header {{ background:linear-gradient(135deg,#1d4ed8,#7c3aed 60%,#db2777); padding:38px 18px 30px; text-align:center; }}
  header h1 {{ margin:0; font-size:30px; letter-spacing:.3px; }}
  header p {{ margin:8px 0 0; color:#e7e9ff; opacity:.92; font-size:15px; }}
  .perf {{ display:inline-flex; gap:18px; flex-wrap:wrap; justify-content:center; margin-top:16px;
          background:rgba(255,255,255,.12); padding:10px 16px; border-radius:12px; font-size:13px; }}
  .perf b {{ font-size:16px; }}
  section.note {{ background:var(--card); border:1px solid var(--line); border-radius:14px;
               padding:16px 18px; margin:22px 0; font-size:14px; color:var(--mut); line-height:1.55; }}
  section.note b {{ color:var(--txt); }}
  .scoring {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; margin-top:12px; }}
  .scoring div {{ background:#0e1428; border:1px solid var(--line); border-radius:9px; padding:8px 10px; font-size:13px; }}
  .scoring .pt {{ color:var(--acc); font-weight:700; }}
  .pending {{ background:#3a2a12; border:1px solid #6b4e1e; color:#f0d9a8; border-radius:12px;
             padding:12px 16px; margin:0 0 18px; font-size:13.5px; line-height:1.5; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:16px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:16px; box-shadow:0 6px 20px rgba(0,0,0,.25); }}
  .teams {{ display:flex; align-items:center; justify-content:space-between; gap:8px; }}
  .team {{ display:flex; align-items:center; gap:8px; font-weight:600; font-size:15px; flex:1; }}
  .team.right {{ justify-content:flex-end; text-align:right; }}
  .team img {{ width:26px; height:auto; border-radius:3px; box-shadow:0 0 0 1px var(--line); }}
  .vs {{ color:var(--mut); font-size:12px; padding:0 4px; }}
  .when {{ color:var(--mut); font-size:12.5px; margin:8px 0 12px; text-align:center; }}
  .advbar {{ display:flex; height:26px; border-radius:7px; overflow:hidden; font-size:12px; font-weight:700; }}
  .adv-home {{ background:var(--home); color:#fff; display:flex; align-items:center; padding-left:8px; min-width:34px; }}
  .adv-away {{ background:var(--away); color:#fff; display:flex; align-items:center; justify-content:flex-end; padding-right:8px; min-width:34px; }}
  .advlbl {{ display:flex; justify-content:space-between; color:var(--mut); font-size:11px; margin-top:4px; }}
  .rec {{ text-align:center; margin:14px 0 12px; }}
  .rec-score {{ font-size:40px; font-weight:800; letter-spacing:2px; line-height:1; }}
  .rec-score .dash {{ color:var(--mut); }}
  .rec-tag {{ text-transform:uppercase; font-size:10.5px; letter-spacing:1.5px; color:var(--acc); margin-top:6px; }}
  .chips {{ display:flex; flex-wrap:wrap; gap:6px; justify-content:center; }}
  .chip {{ background:#0e1428; border:1px solid var(--line); border-radius:20px; padding:5px 11px; font-size:12px; }}
  .chip b {{ color:var(--txt); }}
  .chip.conf {{ background:var(--c); border-color:var(--c); color:#fff; font-weight:700; }}
  .src {{ text-align:center; color:var(--mut); font-size:11px; margin-top:10px; }}
  footer {{ color:var(--mut); font-size:12.5px; line-height:1.6; margin-top:30px; border-top:1px solid var(--line); padding-top:18px; }}
  footer b {{ color:var(--txt); }}
</style>
</head>
<body>
<header>
  <h1>⚽ {titulo}</h1>
  <p>Pronóstico del prode — marcador de máximo valor esperado + clasificado sugerido</p>
  <div class="perf">
    <span>Performance en grupos: <b>{perf['pct']:.0f}%</b> del máximo</span>
    <span>Acierto de ganador: <b>{perf['win']}%</b></span>
    <span>Progresión: {perf_f}</span>
  </div>
</header>
<div class="wrap">

  <section class="note">
    <b>Cómo se calcula.</b> Para cada partido se parte de las cuotas reales del mercado (de-vigadas),
    se mezclan con un modelo de fuerza (Elo internacional + forma del torneo medida por <b>xG</b>,
    no por goles crudos) y se arma la matriz de marcadores con corrección <b>Dixon-Coles</b>.
    Como es eliminatoria, se extiende al <b>alargue (120')</b> y se calcula la probabilidad de
    <b>penales</b>. El marcador sugerido es el que <b>maximiza los puntos esperados</b> del prode,
    incluyendo el bonus de clasificación.
    <div class="scoring">
      <div><span class="pt">12</span> · marcador exacto</div>
      <div><span class="pt">8</span> · ganador + diferencia, o empate</div>
      <div><span class="pt">5</span> · ganador correcto</div>
      <div><span class="pt">2</span> · goles exactos de un equipo</div>
      <div><span class="pt">+3</span> · acertar quién clasifica (si hay penales)</div>
    </div>
  </section>

{pending}
  <div class="grid">
{cards}
  </div>

  <footer>
    <p><b>EV total estimado de la ronda:</b> {ev_total:.1f} puntos en {len(preds)} partidos
       (promedio {ev_total/max(len(preds),1):.2f} por partido).</p>
    <p><b>Supuestos y datos.</b> El marcador es a 120' (90' + alargue); los penales no cuentan
       para el marcador y se modelan como 50/50 para el bonus de clasificación. La forma usa
       <b>xG real de FIFA</b> de los partidos cerrados (vía fifaphy). El alargue se modela como
       un sub-partido de 30' (un tercio del ritmo de gol de 90'). Cuotas vía ESPN; Elo de
       eloratings.net. Generado el {gen} (hora de Argentina).</p>
    <p>El "clasificado" se infiere del marcador: si predecís un ganador, ese avanza; si predecís
       empate, conviene marcar al equipo con mayor probabilidad de avanzar (ya indicado arriba).</p>
  </footer>
</div>
</body>
</html>"""

    os.makedirs(DOCS, exist_ok=True)
    out = os.path.join(DOCS, pred["out_name"])
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return out
