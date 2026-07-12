"""
gen_html.py - Informe HTML autocontenido, MOBILE-FIRST, a partir de results.json.

Diseno pensado para celular (y que escala a desktop):
- App-bar fija con efecto vidrio + chips de temporadas con scroll horizontal y
  scroll-spy (IntersectionObserver).
- Cada temporada = una tarjeta tipo "feed" con podio (medallas) y el detalle de
  cada racha desplegable (filas de partido compactas, no tablas anchas).
- Modo oscuro automatico, safe-areas (notch), tap-targets grandes.
- Metodologia y JSON crudo van colapsados (<details>) para no estorbar.
- La tabla resumen de 5 columnas se muestra SOLO en pantallas anchas.
"""
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

FMT_SHORT = {
    "2010/2011": "20 equipos · 1 zona · ida y vuelta",
    "2011/2012": "20 equipos · 1 zona · ida y vuelta",
    "2012/2013": "20 equipos · 1 zona · ida y vuelta",
    "2013/2014": "22 equipos · 1 zona · ida y vuelta",
    "2014": "22 equipos · 2 zonas de 11 · transición",
    "2015": "22 equipos · 1 zona · ida y vuelta",
    "2016": "22 equipos · 1 zona · solo ida (corto)",
    "2016/2017": "23 equipos · 1 zona · ida y vuelta",
    "2017/2018": "25 equipos · 1 zona · solo ida",
    "2018/2019": "25 equipos · 1 zona · solo ida",
    "2019/2020": "32 equipos · 2 zonas de 16",
    "2021": "35 equipos · 2 zonas (17 / 18)",
    "2022": "37 equipos · 1 zona · solo ida",
    "2023": "37 equipos · 2 zonas (19 / 18)",
    "2024": "38 equipos · 2 zonas de 19 + interzonal",
    "2025": "36 equipos · 2 zonas de 18",
    "2026": "36 equipos · temporada en curso",
}

BADGE = {
    "complete": "",
    "covid": '<span class="badge badge-covid">COVID · anulada</span>',
    "ongoing": '<span class="badge badge-ongoing">en curso</span>',
}
MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def anchor(label):
    return "t" + label.replace("/", "-")


# -------- detalle de una racha (lista de partidos, formato compacto) --------
def wins_list(team):
    items = []
    for w in team["wins"]:
        loc = "L" if w["home"] else "V"
        lvc = "loc" if w["home"] else "vis"
        rd = w["round"].replace("Round ", "F")
        items.append(
            f'<li class="win">'
            f'<span class="w-rd">{esc(rd)}</span>'
            f'<span class="w-dt">{esc(w["date"])}</span>'
            f'<span class="w-lv {lvc}">{loc}</span>'
            f'<span class="w-rival">{esc(w["vs"])}</span>'
            f'<span class="w-sc">{w["gf"]}-{w["ga"]}</span>'
            f'</li>'
        )
    return f'<ul class="wins">{"".join(items)}</ul>'


def team_block(team):
    span = ""
    if team["start"]:
        span = f'<span class="span">{esc(team["start"])} → {esc(team["end"])}</span>'
    return (
        f'<details class="team">'
        f'<summary><span class="t-name">{esc(team["team"])}</span>{span}'
        f'<span class="chev" aria-hidden="true"></span></summary>'
        f'{wins_list(team)}</details>'
    )


def rank_block(rk):
    medal = MEDAL.get(rk["rank"], "")
    tie = f'<span class="tie">{len(rk["teams"])} equipos</span>' if len(rk["teams"]) > 1 else ""
    teams_html = "".join(team_block(t) for t in rk["teams"])
    return (
        f'<div class="rank rank-{rk["rank"]}">'
        f'<div class="rank-h"><span class="medal">{medal}</span>'
        f'<span class="streak-n">{rk["streak"]}</span>'
        f'<span class="streak-l">victorias al hilo</span>{tie}</div>'
        f'<div class="teams">{teams_html}</div>'
        f'</div>'
    )


def season_card(s):
    srcs = []
    for i, u in enumerate(s["src"]):
        txt = (f"zona {i+1}" if len(s["src"]) > 1 else "ver en worldfootball.net")
        srcs.append(f'<a href="{esc(u)}" target="_blank" rel="noopener">{txt}</a>')
    pj = (f'{s["played_matches"]}/{s["total_matches"]} partidos'
          if s["played_matches"] != s["total_matches"]
          else f'{s["total_matches"]} partidos')
    return (
        f'<section class="card" id="{anchor(s["label"])}">'
        f'<div class="card-top">'
        f'<h2 class="yr">{esc(s["label"])}</h2>{BADGE[s["status"]]}'
        f'</div>'
        f'<p class="fmt">{esc(FMT_SHORT.get(s["label"], ""))}</p>'
        f'<div class="ranks">{"".join(rank_block(rk) for rk in s["ranks"])}</div>'
        f'<p class="src">{pj} · {" · ".join(srcs)}</p>'
        f'</section>'
    )


def chip(s):
    return f'<a class="chip" href="#{anchor(s["label"])}" data-t="{anchor(s["label"])}">{esc(s["label"])}</a>'


def summary_row(s):
    cells = ["—", "—", "—"]
    for rk in s["ranks"]:
        if rk["rank"] <= 3:
            t = rk["teams"]
            cells[rk["rank"] - 1] = (f'<b>{rk["streak"]}</b> · {esc(t[0]["team"])}'
                                     if len(t) == 1 else f'<b>{rk["streak"]}</b> · {len(t)} equipos')
    return (f'<tr><td class="s-yr"><a href="#{anchor(s["label"])}">{esc(s["label"])}</a> {BADGE[s["status"]]}</td>'
            f'<td class="s-fmt">{esc(FMT_SHORT.get(s["label"], ""))}</td>'
            f'<td>{cells[0]}</td><td>{cells[1]}</td><td>{cells[2]}</td></tr>')


def build_html(results):
    today = "26/05/2026"
    og = next((s for s in results if s["status"] == "ongoing"), None)
    og_played = og["played_matches"] if og else 0
    og_total = og["total_matches"] if og else 0
    chips = "".join(chip(s) for s in results)
    cards = "\n".join(season_card(s) for s in results)
    rows = "\n".join(summary_row(s) for s in results)
    data_json = html.escape(json.dumps(results, ensure_ascii=False, indent=2))

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0a6b3b" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0c1411" media="(prefers-color-scheme: dark)">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:image/svg+xml,&lt;svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'&gt;&lt;text y='.9em' font-size='90'&gt;⚽&lt;/text&gt;&lt;/svg&gt;">
<title>Rachas · Primera Nacional</title>
<style>
  :root {{
    --accent:#0a6b3b; --accent-ink:#fff;
    --ink:#15202b; --muted:#667586; --line:#e6ebf0;
    --bg:#eef1f5; --card:#fff; --chip:#dfe7ee; --chip-on:#0a6b3b;
    --covid:#b4232b; --covid-bg:#fde8e8; --ong:#8a5a00; --ong-bg:#fff2d4;
    --loc:#0a6b3b; --vis:#8794a3; --shadow:0 1px 3px rgba(20,40,30,.08),0 6px 18px rgba(20,40,30,.05);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --accent:#23c277; --accent-ink:#06130d;
      --ink:#e8eef2; --muted:#92a0ad; --line:#243038;
      --bg:#0c1411; --card:#121c19; --chip:#1c2a25; --chip-on:#23c277;
      --covid:#ff8a8a; --covid-bg:#3a1717; --ong:#ffcf6b; --ong-bg:#322611;
      --loc:#23c277; --vis:#8794a3; --shadow:0 1px 2px rgba(0,0,0,.4);
    }}
  }}
  * {{ box-sizing:border-box; -webkit-tap-highlight-color:transparent; }}
  html {{ scroll-behavior:smooth; -webkit-text-size-adjust:100%; }}
  body {{
    margin:0; background:var(--bg); color:var(--ink); overflow-x:hidden;
    font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    padding-bottom:env(safe-area-inset-bottom);
  }}
  a {{ color:var(--accent); }}

  /* ---------- app-bar fija (efecto vidrio) ---------- */
  .bar {{
    position:sticky; top:0; z-index:30;
    background:color-mix(in srgb, var(--card) 82%, transparent);
    -webkit-backdrop-filter:saturate(1.6) blur(12px); backdrop-filter:saturate(1.6) blur(12px);
    border-bottom:1px solid var(--line);
    padding:calc(env(safe-area-inset-top) + 10px) 16px 0;
  }}
  .bar h1 {{ font-size:1.06rem; margin:0; letter-spacing:.2px; }}
  .bar .def {{ font-size:.78rem; color:var(--muted); margin:2px 0 9px; }}
  .years {{
    display:flex; gap:7px; overflow-x:auto; padding-bottom:10px;
    scrollbar-width:none; -ms-overflow-style:none; scroll-snap-type:x proximity;
  }}
  .years::-webkit-scrollbar {{ display:none; }}
  .chip {{
    flex:0 0 auto; scroll-snap-align:start; text-decoration:none;
    background:var(--chip); color:var(--ink); font-size:.8rem; font-weight:600;
    padding:7px 12px; border-radius:999px; white-space:nowrap; transition:.15s;
  }}
  .chip.on {{ background:var(--chip-on); color:var(--accent-ink); }}

  .wrap {{ padding:14px; }}
  @media (min-width:780px) {{ .wrap {{ max-width:1060px; margin:0 auto; padding:20px; }} }}

  .lead {{ color:var(--muted); font-size:.86rem; margin:2px 2px 14px; }}

  /* ---------- tarjeta de temporada ---------- */
  .card {{
    background:var(--card); border:1px solid var(--line); border-radius:18px;
    padding:15px 15px 11px; margin:0 0 13px; box-shadow:var(--shadow);
    scroll-margin-top:118px;
  }}
  .card-top {{ display:flex; align-items:center; gap:9px; }}
  .card .yr {{ font-size:1.5rem; margin:0; font-weight:800; letter-spacing:-.5px; }}
  .card .fmt {{ color:var(--muted); font-size:.82rem; margin:1px 0 12px; }}
  .badge {{ font-size:.66rem; font-weight:800; padding:3px 8px; border-radius:999px;
            text-transform:uppercase; letter-spacing:.4px; }}
  .badge-covid {{ background:var(--covid-bg); color:var(--covid); }}
  .badge-ongoing {{ background:var(--ong-bg); color:var(--ong); }}

  .ranks {{ display:grid; gap:9px; }}
  @media (min-width:680px) {{ .ranks {{ grid-template-columns:repeat(3,1fr); align-items:start; }} }}
  .rank {{ background:var(--bg); border:1px solid var(--line); border-radius:13px; padding:10px 12px; }}
  .rank-h {{ display:flex; align-items:baseline; gap:7px; flex-wrap:wrap; }}
  .medal {{ font-size:1.05rem; }}
  .streak-n {{ font-size:1.5rem; font-weight:800; line-height:1; }}
  .streak-l {{ color:var(--muted); font-size:.76rem; }}
  .tie {{ margin-left:auto; font-size:.7rem; font-weight:700; color:var(--muted);
          background:var(--chip); padding:2px 8px; border-radius:999px; }}
  .teams {{ margin-top:7px; }}

  details.team {{ border-top:1px solid var(--line); }}
  details.team:first-child {{ border-top:none; }}
  details.team > summary {{
    list-style:none; cursor:pointer; display:flex; align-items:center; gap:8px;
    padding:9px 2px; min-height:40px;
  }}
  details.team > summary::-webkit-details-marker {{ display:none; }}
  .t-name {{ font-weight:700; font-size:.95rem; }}
  .span {{ color:var(--muted); font-size:.74rem; margin-left:2px; }}
  .chev {{ margin-left:auto; width:8px; height:8px; border-right:2px solid var(--muted);
           border-bottom:2px solid var(--muted); transform:rotate(45deg); transition:.2s; flex:0 0 auto; }}
  details.team[open] .chev {{ transform:rotate(225deg); }}

  /* ---------- filas de partido (sin tablas anchas) ---------- */
  ul.wins {{ list-style:none; margin:2px 0 10px; padding:0;
             border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  li.win {{ display:flex; align-items:center; gap:8px; padding:8px 10px; font-size:.84rem;
            border-top:1px solid var(--line); }}
  li.win:first-child {{ border-top:none; }}
  li.win:nth-child(odd) {{ background:color-mix(in srgb,var(--card) 100%, var(--bg) 45%); }}
  .w-rd {{ flex:0 0 auto; font-weight:700; color:var(--muted); width:34px; font-size:.76rem; }}
  .w-dt {{ flex:0 0 auto; color:var(--muted); font-variant-numeric:tabular-nums; font-size:.78rem; }}
  .w-lv {{ flex:0 0 auto; width:18px; height:18px; line-height:18px; text-align:center;
           border-radius:5px; font-size:.66rem; font-weight:800; color:#fff; }}
  .w-lv.loc {{ background:var(--loc); }}
  .w-lv.vis {{ background:var(--vis); }}
  .w-rival {{ flex:1 1 auto; min-width:0; }}
  .w-sc {{ flex:0 0 auto; font-weight:800; font-variant-numeric:tabular-nums; }}

  .src {{ color:var(--muted); font-size:.76rem; margin:11px 2px 2px; }}

  /* ---------- bloques info ---------- */
  h2.sec {{ font-size:1.1rem; margin:26px 2px 10px; }}
  .info {{ background:var(--card); border:1px solid var(--line); border-radius:16px;
           padding:6px 0; margin:0 0 13px; box-shadow:var(--shadow); }}
  .info > summary {{ list-style:none; cursor:pointer; padding:13px 16px; font-weight:700;
                     display:flex; align-items:center; gap:8px; min-height:48px; }}
  .info > summary::-webkit-details-marker {{ display:none; }}
  .info > summary .chev {{ }}
  .info .body {{ padding:0 16px 14px; font-size:.88rem; }}
  .info .body ul,.info .body ol {{ padding-left:20px; margin:6px 0; }}
  .info .body li {{ margin:5px 0; }}
  .warn {{ border-left:4px solid var(--covid); }}

  pre.data {{ background:#0d1714; color:#bfe6cf; padding:13px; border-radius:12px;
              overflow:auto; max-height:50vh; font-size:.7rem; line-height:1.45;
              font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}

  /* ---------- tabla resumen: SOLO desktop ---------- */
  .summary {{ display:none; }}
  @media (min-width:920px) {{
    .summary {{ display:table; width:100%; border-collapse:collapse; background:var(--card);
                border:1px solid var(--line); border-radius:14px; overflow:hidden; font-size:.9rem;
                box-shadow:var(--shadow); margin-bottom:10px; }}
    .summary th,.summary td {{ padding:10px 12px; border-bottom:1px solid var(--line);
                               text-align:left; vertical-align:top; }}
    .summary thead th {{ background:var(--accent); color:var(--accent-ink); }}
    .summary .s-yr a {{ font-weight:700; text-decoration:none; white-space:nowrap; }}
    .summary .s-fmt {{ color:var(--muted); }}
  }}

  footer {{ color:var(--muted); font-size:.78rem; margin:24px 2px 8px; }}

  /* feedback tactil / hover solo en mouse */
  .chip:active,.card a:active {{ opacity:.6; }}
  @media (hover:hover) {{
    .chip:hover {{ filter:brightness(.97); }}
    details.team > summary:hover .t-name {{ color:var(--accent); }}
  }}

  /* boton volver arriba */
  .fab {{ position:fixed; right:14px; bottom:calc(14px + env(safe-area-inset-bottom));
          width:46px; height:46px; border-radius:50%; background:var(--accent); color:var(--accent-ink);
          display:flex; align-items:center; justify-content:center; text-decoration:none;
          box-shadow:0 6px 18px rgba(0,0,0,.25); font-size:1.2rem; z-index:25;
          opacity:0; pointer-events:none; transition:opacity .2s; }}
  .fab.show {{ opacity:1; pointer-events:auto; }}
</style>
</head>
<body id="top">
  <header class="bar">
    <h1>Rachas · Primera Nacional 🇦🇷</h1>
    <p class="def">Victorias consecutivas por temporada · empate o derrota cortan la racha</p>
    <nav class="years">{chips}</nav>
  </header>

  <main class="wrap">
    <p class="lead">Las <b>3 rachas más largas</b> de victorias al hilo en cada temporada de la
    Primera Nacional / B Nacional (segunda división de Argentina), 2010/11 → 2026.
    Tocá un equipo para ver los partidos de su racha. Datos al {today}.</p>

    <table class="summary">
      <thead><tr><th>Temporada</th><th>Formato</th><th>1ª racha</th><th>2ª racha</th><th>3ª racha</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>

    {cards}

    <h2 class="sec">Temporadas especiales</h2>
    <details class="info warn" open>
      <summary>⚠️ Incompletas / con asterisco<span class="chev"></span></summary>
      <div class="body">
        <ul>
          <li><b>2019/2020 — anulada por COVID-19.</b> La racha se calcula solo sobre los
          <b>partidos efectivamente jugados</b> antes de la suspensión (último: 17/03/2020;
          se jugaron 334 de 480). La AFA anuló la temporada (sin campeón ni descensos
          deportivos): los números valen como “racha dentro de lo jugado”, pero no se completó.</li>
          <li><b>2026 — en curso.</b> Datos <b>parciales</b> al {today} ({og_played} de {og_total} partidos,
          última fecha jugada: 24/05/2026); las rachas pueden cambiar.</li>
          <li><b>El resto (2010/11 → 2025):</b> 100% de los partidos de fase regular con
          resultado, en orden cronológico. Sin estimaciones ni datos inventados.</li>
        </ul>
      </div>
    </details>

    <h2 class="sec">Cómo se midió</h2>
    <details class="info">
      <summary>ℹ️ Definición de racha, fuente y método<span class="chev"></span></summary>
      <div class="body">
        <ul>
          <li>Solo <b>victorias consecutivas</b>; un empate o una derrota resetean el contador a 0.</li>
          <li>Orden <b>cronológico real</b> de cada equipo (timestamp del partido); la jornada
          solo desempata. Así se ubican bien los partidos postergados.</li>
          <li>Solo <b>fase regular</b> (todos contra todos / interzonales). Se excluyen Reducido,
          finales por el ascenso, promociones, desempates y playoffs.</li>
          <li>Ranking por <b>longitud de racha</b> (1º/2º/3º); si hay empate, se listan todos.</li>
        </ul>
        <p><b>Fuente:</b> <a href="https://www.worldfootball.net/competition/co1787/argentina-primera-nacional/" target="_blank" rel="noopener">worldfootball.net</a>
        — calendario partido-a-partido con fecha y jornada, una sola fuente para todas las
        temporadas (identidad de cada club por ID estable). Validación externa del caso extremo:
        Rosario Central 2012/13 = 12 victorias (coincide la fecha del 12º triunfo, 11/03/2013 vs Nueva Chicago).</p>
      </div>
    </details>

    <h2 class="sec">Datos estructurados</h2>
    <details class="info">
      <summary>{{ }} JSON completo (con detalle partido-a-partido)<span class="chev"></span></summary>
      <div class="body"><pre class="data">{data_json}</pre></div>
    </details>

    <footer>Fuente: worldfootball.net · Generado automáticamente el {today}.
    Cada temporada es verificable con su enlace.</footer>
  </main>

  <a href="#top" class="fab" id="fab" aria-label="Volver arriba">↑</a>

<script>
  // scroll-spy: resalta el chip de la temporada visible
  const chips = [...document.querySelectorAll('.chip')];
  const byId = Object.fromEntries(chips.map(c => [c.dataset.t, c]));
  const bar = document.querySelector('.years');
  const obs = new IntersectionObserver((entries) => {{
    entries.forEach(e => {{
      if (e.isIntersecting) {{
        chips.forEach(c => c.classList.remove('on'));
        const c = byId[e.target.id];
        if (c) {{ c.classList.add('on');
          c.scrollIntoView({{inline:'center', block:'nearest', behavior:'smooth'}}); }}
      }}
    }});
  }}, {{ rootMargin: '-45% 0px -50% 0px' }});
  document.querySelectorAll('section.card').forEach(s => obs.observe(s));

  // FAB volver-arriba
  const fab = document.getElementById('fab');
  addEventListener('scroll', () => fab.classList.toggle('show', scrollY > 700), {{passive:true}});
</script>
</body>
</html>
"""


def main():
    results = json.load(open(os.path.join(DATA, "results.json"), encoding="utf-8"))
    out = build_html(results)
    path = os.path.join(HERE, "rachas_primera_nacional.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print("HTML escrito en", path, "·", len(out), "bytes")


if __name__ == "__main__":
    main()
