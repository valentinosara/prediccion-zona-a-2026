"""
gen_html.py - Pagina HTML autocontenida (lang="es") con el perfil y las 7
estadisticas de Juan Sara como head coach, a partir de data/stats.json.

Convenciones visuales tomadas de rachas-primera-nacional/gen_html.py: CSS por
variables con modo claro/oscuro automatico (prefers-color-scheme), barra
superior fija, tarjetas con sombra suave, <details>/<summary> para contenido
secundario colapsable, boton "volver arriba". Sin ninguna dependencia externa
(fuentes del sistema, sin JS/CSS/imagenes remotas) para poder abrirse
haciendo doble click al archivo, sin conexion.

Nunca se renderiza la tabla cruda de ~156 partidos (PAGE-1): todo lo que se
ve aca son agregados (por gestion, por club rival, por DT rival, etc.) o, a
lo sumo, el detalle puntual de una racha (un puñado de partidos), igual que
ya hace el sibling de rachas con el detalle de una racha de victorias.
"""
import datetime
import html
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
STATS_PATH = os.path.join(DATA, "stats.json")

MEDAL = {0: "🥇", 1: "🥈", 2: "🥉"}


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def fmt_pct(v):
    """None -> "N/A" (nunca 0% enganoso, spec MET-4): stats.json ya deja
    `None` en vez de 0 para un split sin partidos, este es el unico lugar
    que lo traduce a texto."""
    return f"{v:.1f}%" if v is not None else "N/A"


def fmt_ppp(v):
    return f"{v:.2f}" if v is not None else "—"


def data_sort(v):
    """Comparable value for the client-side table sorter's `data-sort`
    attribute: the raw number as a plain string, or the literal "N/A"
    sentinel when the underlying value is `None` (so the inline sorter
    always pushes it to the bottom, regardless of sort direction)."""
    return "N/A" if v is None else str(v)


def ddmmyyyy(iso):
    if not iso:
        return None
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def fmt_period(appointed, until):
    return f'{ddmmyyyy(appointed)} → {ddmmyyyy(until) or "presente"}'


def fmt_generated(iso_dt):
    d, t = iso_dt.split("T")
    y, m, day = d.split("-")
    hh, mm = t.split(":")[:2]
    return f"{day}/{m}/{y} {hh}:{mm}"


LV_LABEL = {"H": "L", "A": "V"}
LV_CLASS = {"H": "loc", "A": "vis"}


# ------------------------------------------------------------------
# Hero (resumen de carrera)
# ------------------------------------------------------------------
def stat_card(value, label):
    return f'<div class="stat"><span class="stat-n">{value}</span><span class="stat-l">{esc(label)}</span></div>'


def hero_block(stats, current_spell):
    career = stats["career"]
    cards = "".join([
        stat_card(career["pj"], "Partidos dirigidos"),
        stat_card(f'{career["w"]}-{career["d"]}-{career["l"]}', "V-E-D"),
        stat_card(fmt_ppp(career["ppp"]), "Puntos por partido"),
        stat_card(fmt_pct(career["effectiveness_pct"]), "Efectividad"),
    ])
    current_line = ""
    if current_spell:
        current_line = (
            f'<p class="current">Actualmente dirige a <b>{esc(current_spell["club"])}</b>, '
            f'desde el {esc(ddmmyyyy(current_spell["appointed"]))}.</p>'
        )
    return f'''
    <section class="hero">
      <div class="stats-grid">{cards}</div>
      {current_line}
    </section>'''


# ------------------------------------------------------------------
# Gestiones (per spell) - MET-7
# ------------------------------------------------------------------
def spell_row(sp):
    ongoing = ' <span class="badge badge-ongoing">vigente</span>' if sp["until"] is None else ""
    return (
        f'<tr><td class="t-club">{esc(sp["club"])}{ongoing}</td>'
        f'<td data-sort="{esc(sp["appointed"])}">{esc(fmt_period(sp["appointed"], sp["until"]))}</td>'
        f'<td data-sort="{data_sort(sp["pj"])}">{sp["pj"]}</td>'
        f'<td class="wdl" data-sort="{data_sort(sp["w"])}">{sp["w"]}-{sp["d"]}-{sp["l"]}</td>'
        f'<td data-sort="{data_sort(sp["gf"])}">{sp["gf"]}-{sp["ga"]}</td>'
        f'<td data-sort="{data_sort(sp["ppp"])}"><b>{fmt_ppp(sp["ppp"])}</b></td>'
        f'<td data-sort="{data_sort(sp["effectiveness_pct"])}">{fmt_pct(sp["effectiveness_pct"])}</td></tr>'
    )


def gestiones_section(stats):
    rows = "".join(spell_row(sp) for sp in stats["spells"])
    return f'''
    <section class="card" id="gestiones">
      <h2 class="sec-t">Gestiones</h2>
      <p class="sec-d">Las 7 etapas de Juan Sara como head coach, en orden cronológico.</p>
      <div class="table-wrap">
        <table class="tbl sortable-table">
          <thead><tr>
            <th class="sortable" aria-sort="none">Club</th>
            <th class="sortable" aria-sort="none">Período</th>
            <th class="sortable" aria-sort="none">PJ</th>
            <th class="sortable" aria-sort="none">V-E-D</th>
            <th class="sortable" aria-sort="none">GF-GC</th>
            <th class="sortable" aria-sort="none">PPP</th>
            <th class="sortable" aria-sort="none">Efectividad</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>'''


# ------------------------------------------------------------------
# Rendimiento vs Clubes (MET-1 + parte "por club" de MET-4)
# ------------------------------------------------------------------
def vs_club_row(r):
    home, away = r["home"], r["away"]
    return (
        f'<tr><td class="t-club">{esc(r["name"])}</td>'
        f'<td data-sort="{data_sort(r["pj"])}">{r["pj"]}</td>'
        f'<td class="wdl" data-sort="{data_sort(r["w"])}">{r["w"]}-{r["d"]}-{r["l"]}</td>'
        f'<td data-sort="{data_sort(r["gf"])}">{r["gf"]}-{r["ga"]}</td>'
        f'<td data-sort="{data_sort(r["effectiveness_pct"])}">{fmt_pct(r["effectiveness_pct"])}</td>'
        f'<td data-sort="{data_sort(home["effectiveness_pct"])}">{home["pj"]} · {fmt_pct(home["effectiveness_pct"])}</td>'
        f'<td data-sort="{data_sort(away["effectiveness_pct"])}">{away["pj"]} · {fmt_pct(away["effectiveness_pct"])}</td></tr>'
    )


def vs_clubes_section(stats):
    rows = "".join(vs_club_row(r) for r in stats["vs_clubs"])
    return f'''
    <section class="card" id="vs-clubes">
      <h2 class="sec-t">Rendimiento vs clubes rivales</h2>
      <p class="sec-d">{len(stats["vs_clubs"])} clubes distintos enfrentados en {sum(r["pj"] for r in stats["vs_clubs"])} partidos.
      "Local"/"Visitante" muestran partidos jugados y % de puntos ganados desde ese lado
      contra ese rival puntual (<b>N/A</b> cuando solo se lo enfrentó de un lado).</p>
      <div class="table-wrap table-scroll">
        <table class="tbl sortable-table">
          <thead><tr>
            <th class="sortable" aria-sort="none">Club rival</th>
            <th class="sortable" aria-sort="none">PJ</th>
            <th class="sortable" aria-sort="none">V-E-D</th>
            <th class="sortable" aria-sort="none">GF-GC</th>
            <th class="sortable" aria-sort="none">Efectividad</th>
            <th class="sortable" aria-sort="none">Local (PJ · %)</th>
            <th class="sortable" aria-sort="none">Visitante (PJ · %)</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>'''


# ------------------------------------------------------------------
# Historial vs Entrenadores (MET-2)
# ------------------------------------------------------------------
def vs_coach_row(r):
    return (
        f'<tr><td class="t-club">{esc(r["name"])}</td>'
        f'<td data-sort="{data_sort(r["pj"])}">{r["pj"]}</td>'
        f'<td class="wdl" data-sort="{data_sort(r["w"])}">{r["w"]}-{r["d"]}-{r["l"]}</td>'
        f'<td data-sort="{data_sort(r["ppp"])}"><b>{fmt_ppp(r["ppp"])}</b></td></tr>'
    )


def vs_entrenadores_section(stats):
    rows = "".join(vs_coach_row(r) for r in stats["vs_coaches"])
    return f'''
    <section class="card" id="vs-entrenadores">
      <h2 class="sec-t">Historial vs entrenadores rivales</h2>
      <p class="sec-d">{len(stats["vs_coaches"])} DTs rivales distintos. Ordenado por partidos jugados
      (el más enfrentado primero) y, ante empate, por puntos por partido (PPP).</p>
      <div class="table-wrap table-scroll">
        <table class="tbl sortable-table">
          <thead><tr>
            <th class="sortable" aria-sort="none">DT rival</th>
            <th class="sortable" aria-sort="none">PJ</th>
            <th class="sortable" aria-sort="none">PG-PE-PP</th>
            <th class="sortable" aria-sort="none">PPP</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>'''


# ------------------------------------------------------------------
# Efectividad y puntos local/visitante (MET-3 + MET-4 global)
# ------------------------------------------------------------------
def own_club_row(name, b):
    n_spells = len(b["spell_indices"])
    tag = f' <span class="tag">{n_spells} gestiones</span>' if n_spells > 1 else ""
    return (
        f'<tr><td class="t-club">{esc(name)}{tag}</td>'
        f'<td data-sort="{data_sort(b["pj"])}">{b["pj"]}</td>'
        f'<td class="wdl" data-sort="{data_sort(b["w"])}">{b["w"]}-{b["d"]}-{b["l"]}</td>'
        f'<td data-sort="{data_sort(b["gf"])}">{b["gf"]}-{b["ga"]}</td>'
        f'<td data-sort="{data_sort(b["ppp"])}"><b>{fmt_ppp(b["ppp"])}</b></td>'
        f'<td data-sort="{data_sort(b["effectiveness_pct"])}">{fmt_pct(b["effectiveness_pct"])}</td></tr>'
    )


def efectividad_section(stats):
    career = stats["career"]
    ha = stats["home_away_global"]
    own_rows = "".join(
        own_club_row(name, b) for name, b in
        sorted(stats["own_clubs"].items(), key=lambda kv: -kv[1]["pj"])
    )
    mini_cards = "".join([
        stat_card(fmt_pct(career["effectiveness_pct"]), "Efectividad global"),
        stat_card(f'{fmt_pct(ha["home"]["effectiveness_pct"])} ({ha["home"]["pj"]} PJ)', "Puntos como local"),
        stat_card(f'{fmt_pct(ha["away"]["effectiveness_pct"])} ({ha["away"]["pj"]} PJ)', "Puntos como visitante"),
    ])
    return f'''
    <section class="card" id="efectividad">
      <h2 class="sec-t">Efectividad y puntos local / visitante</h2>
      <p class="sec-d">Efectividad = puntos obtenidos / puntos posibles (3 por partido), con el mismo
      criterio 3-1-0 para toda la carrera, incluidas copas.</p>
      <div class="stats-grid mini">{mini_cards}</div>
      <h3 class="sub-t">Por club propio (gestiones fusionadas)</h3>
      <div class="table-wrap">
        <table class="tbl sortable-table">
          <thead><tr>
            <th class="sortable" aria-sort="none">Club</th>
            <th class="sortable" aria-sort="none">PJ</th>
            <th class="sortable" aria-sort="none">V-E-D</th>
            <th class="sortable" aria-sort="none">GF-GC</th>
            <th class="sortable" aria-sort="none">PPP</th>
            <th class="sortable" aria-sort="none">Efectividad</th>
          </tr></thead>
          <tbody>{own_rows}</tbody>
        </table>
      </div>
      <p class="note">El desglose local/visitante por cada <b>club rival</b> puntual está en la tabla
      de <a href="#vs-clubes">Rendimiento vs clubes rivales</a>.</p>
    </section>'''


# ------------------------------------------------------------------
# Goleadores (MET-5)
# ------------------------------------------------------------------
def scorer_row(idx, r):
    medal = MEDAL.get(idx, "")
    return (
        f'<tr><td class="medal-cell">{medal}</td>'
        f'<td>{esc(r["player"])}</td>'
        f'<td data-sort="{data_sort(r["goals"])}"><b>{r["goals"]}</b></td></tr>'
    )


def spell_scorers_block(row, spells_by_i):
    sp = spells_by_i.get(row["i"])
    club = sp["club"] if sp else row["club"]
    period = fmt_period(sp["appointed"], sp["until"]) if sp else ""
    items = "".join(
        f'<li><span class="sc-player">{esc(s["player"])}</span><span class="sc-goals">{s["goals"]}</span></li>'
        for s in row["scorers"]
    )
    if not items:
        items = '<li class="sc-empty">Sin goleadores identificados en esta gestión.</li>'
    return (
        f'<details class="team">'
        f'<summary><span class="t-name">{esc(club)}</span>'
        f'<span class="span">{esc(period)}</span>'
        f'<span class="chev" aria-hidden="true"></span></summary>'
        f'<ul class="scorers">{items}</ul>'
        f'</details>'
    )


def goleadores_section(stats):
    spells_by_i = {sp["i"]: sp for sp in stats["spells"]}
    agg_rows = "".join(scorer_row(i, r) for i, r in enumerate(stats["scorers"]["aggregate"]))
    per_spell_blocks = "".join(
        spell_scorers_block(row, spells_by_i)
        for row in sorted(stats["scorers"]["per_spell"], key=lambda r: spells_by_i[r["i"]]["appointed"])
    )
    return f'''
    <section class="card" id="goleadores">
      <h2 class="sec-t">Goleadores</h2>
      <p class="sec-d">Sólo goles del equipo de Sara; los penales suman igual que un gol de juego,
      los goles en contra del rival NO se acreditan a ningún jugador propio.</p>
      <h3 class="sub-t">Histórico (todas las gestiones)</h3>
      <div class="table-wrap table-scroll">
        <table class="tbl sortable-table">
          <thead><tr>
            <th></th>
            <th class="sortable" aria-sort="none">Jugador</th>
            <th class="sortable" aria-sort="none">Goles</th>
          </tr></thead>
          <tbody>{agg_rows}</tbody>
        </table>
      </div>
      <h3 class="sub-t">Por gestión</h3>
      <div class="teams">{per_spell_blocks}</div>
    </section>'''


# ------------------------------------------------------------------
# Mejores rachas (MET-6)
# ------------------------------------------------------------------
def streak_matches_list(matches):
    if not matches:
        return '<p class="muted">Sin registros.</p>'
    items = []
    for m in matches:
        lv = LV_CLASS.get(m["home_away"], "vis")
        lv_label = LV_LABEL.get(m["home_away"], "?")
        items.append(
            f'<li class="win">'
            f'<span class="w-dt">{esc(ddmmyyyy(m["date"]))}</span>'
            f'<span class="w-lv {lv}">{lv_label}</span>'
            f'<span class="w-club">{esc(m["club"])}</span>'
            f'<span class="w-rival">vs {esc(m["opponent"])}</span>'
            f'<span class="w-sc">{m["gf"]}-{m["ga"]}</span>'
            f'</li>'
        )
    return f'<ul class="wins">{"".join(items)}</ul>'


def streak_pair_block(summary):
    win, loss = summary["best_win"], summary["best_loss"]
    return f'''
      <div class="streak-pair">
        <div class="streak-box win-box">
          <div class="streak-h"><span class="streak-n">{win["len"]}</span><span class="streak-l">victorias seguidas</span></div>
          {streak_matches_list(win["matches"])}
        </div>
        <div class="streak-box loss-box">
          <div class="streak-h"><span class="streak-n">{loss["len"]}</span><span class="streak-l">derrotas seguidas</span></div>
          {streak_matches_list(loss["matches"])}
        </div>
      </div>'''


def club_streak_block(club, summary):
    win, loss = summary["best_win"]["len"], summary["best_loss"]["len"]
    return (
        f'<details class="team">'
        f'<summary><span class="t-name">{esc(club)}</span>'
        f'<span class="span">{win}V seguidas máx. · {loss}D seguidas máx.</span>'
        f'<span class="chev" aria-hidden="true"></span></summary>'
        f'{streak_pair_block(summary)}'
        f'</details>'
    )


def rachas_section(stats):
    streaks = stats["streaks"]
    global_block = streak_pair_block(streaks["global"])
    club_blocks = "".join(
        club_streak_block(club, summary)
        for club, summary in sorted(streaks["per_club"].items(),
                                     key=lambda kv: -(kv[1]["best_win"]["len"] + kv[1]["best_loss"]["len"]))
    )
    return f'''
    <section class="card" id="rachas">
      <h2 class="sec-t">Mejores rachas</h2>
      <p class="sec-d">Sólo victorias (o derrotas) <b>consecutivas</b>; un empate corta ambas rachas.
      "Global" recorre toda la carrera en un único orden cronológico (puede cruzar un cambio de club
      si las fechas quedan pegadas). "Por club" fusiona las gestiones de un mismo club propio en una
      sola secuencia cronológica.</p>
      <h3 class="sub-t">Global (toda la carrera)</h3>
      {global_block}
      <h3 class="sub-t">Por club propio</h3>
      <div class="teams">{club_blocks}</div>
    </section>'''


# ------------------------------------------------------------------
# Pagina completa
# ------------------------------------------------------------------
def build_html(stats):
    current_spell = next((sp for sp in stats["spells"] if sp["until"] is None), None)
    generated = fmt_generated(stats["generated_at"])

    hero = hero_block(stats, current_spell)
    gestiones = gestiones_section(stats)
    vs_clubes = vs_clubes_section(stats)
    vs_entrenadores = vs_entrenadores_section(stats)
    efectividad = efectividad_section(stats)
    goleadores = goleadores_section(stats)
    rachas = rachas_section(stats)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#1a5fb4" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0c1116" media="(prefers-color-scheme: dark)">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:image/svg+xml,&lt;svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'&gt;&lt;text y='.9em' font-size='90'&gt;📋&lt;/text&gt;&lt;/svg&gt;">
<title>Juan Sara · Entrenador</title>
<style>
  :root {{
    --accent:#1a5fb4; --accent-ink:#fff;
    --ink:#15202b; --muted:#667586; --line:#e6ebf0;
    --bg:#eef1f5; --card:#fff; --chip:#dfe7ee;
    --win:#0a6b3b; --win-bg:#e7f5ec; --loss:#b4232b; --loss-bg:#fde8e8;
    --loc:#1a5fb4; --vis:#8794a3; --shadow:0 1px 3px rgba(20,30,40,.08),0 6px 18px rgba(20,30,40,.05);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --accent:#6fb1ff; --accent-ink:#06130d;
      --ink:#e8eef2; --muted:#92a0ad; --line:#243038;
      --bg:#0c1116; --card:#131a21; --chip:#1c2732;
      --win:#23c277; --win-bg:#132a1f; --loss:#ff8a8a; --loss-bg:#3a1717;
      --loc:#6fb1ff; --vis:#8794a3; --shadow:0 1px 2px rgba(0,0,0,.4);
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

  .bar {{
    position:sticky; top:0; z-index:30;
    background:color-mix(in srgb, var(--card) 82%, transparent);
    -webkit-backdrop-filter:saturate(1.6) blur(12px); backdrop-filter:saturate(1.6) blur(12px);
    border-bottom:1px solid var(--line);
    padding:calc(env(safe-area-inset-top) + 10px) 16px 0;
  }}
  .bar h1 {{ font-size:1.1rem; margin:0; letter-spacing:.2px; }}
  .bar .def {{ font-size:.78rem; color:var(--muted); margin:2px 0 9px; }}
  .nav {{
    display:flex; gap:7px; overflow-x:auto; padding-bottom:10px;
    scrollbar-width:none; -ms-overflow-style:none; scroll-snap-type:x proximity;
  }}
  .nav::-webkit-scrollbar {{ display:none; }}
  .chip {{
    flex:0 0 auto; scroll-snap-align:start; text-decoration:none;
    background:var(--chip); color:var(--ink); font-size:.8rem; font-weight:600;
    padding:7px 12px; border-radius:999px; white-space:nowrap;
  }}

  .wrap {{ padding:14px; }}
  @media (min-width:780px) {{ .wrap {{ max-width:1080px; margin:0 auto; padding:20px; }} }}

  .card {{
    background:var(--card); border:1px solid var(--line); border-radius:18px;
    padding:16px 16px 14px; margin:0 0 14px; box-shadow:var(--shadow);
    scroll-margin-top:112px;
  }}
  .sec-t {{ font-size:1.2rem; margin:0 0 4px; font-weight:800; }}
  .sub-t {{ font-size:1rem; margin:18px 0 8px; font-weight:700; }}
  .sec-d {{ color:var(--muted); font-size:.84rem; margin:0 0 12px; }}
  .note {{ color:var(--muted); font-size:.8rem; margin:10px 2px 0; }}

  .hero {{
    background:var(--card); border:1px solid var(--line); border-radius:18px;
    padding:18px 16px; margin:0 0 14px; box-shadow:var(--shadow);
  }}
  .stats-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }}
  @media (min-width:560px) {{ .stats-grid {{ grid-template-columns:repeat(4,1fr); }} }}
  .stats-grid.mini {{ grid-template-columns:repeat(1,1fr); }}
  @media (min-width:560px) {{ .stats-grid.mini {{ grid-template-columns:repeat(3,1fr); }} }}
  .stat {{
    background:var(--bg); border:1px solid var(--line); border-radius:13px;
    padding:12px 10px; text-align:center;
  }}
  .stat-n {{ display:block; font-size:1.55rem; font-weight:800; line-height:1.15; }}
  .stat-l {{ display:block; color:var(--muted); font-size:.72rem; margin-top:3px; }}
  .current {{ color:var(--muted); font-size:.86rem; margin:12px 2px 0; }}

  .badge {{ font-size:.62rem; font-weight:800; padding:2px 7px; border-radius:999px;
            text-transform:uppercase; letter-spacing:.3px; vertical-align:middle; }}
  .badge-ongoing {{ background:var(--win-bg); color:var(--win); }}
  .tag {{ font-size:.66rem; font-weight:700; color:var(--muted);
          background:var(--chip); padding:2px 7px; border-radius:999px; margin-left:4px; }}

  .table-wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:13px; }}
  .table-scroll {{ max-height:440px; overflow-y:auto; }}
  table.tbl {{ width:100%; border-collapse:collapse; font-size:.86rem; white-space:nowrap; }}
  table.tbl th, table.tbl td {{ padding:9px 11px; border-bottom:1px solid var(--line); text-align:left; }}
  table.tbl thead th {{ background:var(--accent); color:var(--accent-ink); position:sticky; top:0; z-index:1; }}
  table.tbl tbody tr:last-child td {{ border-bottom:none; }}
  table.tbl .t-club {{ font-weight:700; }}
  table.tbl .wdl {{ font-variant-numeric:tabular-nums; }}
  table.tbl .medal-cell {{ text-align:center; width:1.6em; }}

  th.sortable {{ cursor:pointer; user-select:none; -webkit-user-select:none; }}
  th.sortable:hover {{ filter:brightness(1.12); }}
  th.sortable::after {{ content:"⇅"; display:inline-block; margin-left:6px; font-size:.7em; opacity:.55; }}
  th.sortable[aria-sort="ascending"]::after {{ content:"▲"; opacity:1; }}
  th.sortable[aria-sort="descending"]::after {{ content:"▼"; opacity:1; }}

  .teams {{ margin-top:2px; }}
  details.team {{ border-top:1px solid var(--line); }}
  details.team:first-child {{ border-top:none; }}
  details.team > summary {{
    list-style:none; cursor:pointer; display:flex; align-items:center; gap:8px;
    padding:10px 2px; min-height:40px;
  }}
  details.team > summary::-webkit-details-marker {{ display:none; }}
  .t-name {{ font-weight:700; font-size:.95rem; }}
  .span {{ color:var(--muted); font-size:.74rem; margin-left:2px; }}
  .chev {{ margin-left:auto; width:8px; height:8px; border-right:2px solid var(--muted);
           border-bottom:2px solid var(--muted); transform:rotate(45deg); transition:.2s; flex:0 0 auto; }}
  details.team[open] .chev {{ transform:rotate(225deg); }}

  ul.scorers {{ list-style:none; margin:2px 0 12px; padding:0;
                border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  ul.scorers li {{ display:flex; justify-content:space-between; gap:8px; padding:8px 12px;
                   font-size:.86rem; border-top:1px solid var(--line); }}
  ul.scorers li:first-child {{ border-top:none; }}
  ul.scorers li:nth-child(odd) {{ background:color-mix(in srgb,var(--card) 100%, var(--bg) 45%); }}
  .sc-goals {{ font-weight:800; font-variant-numeric:tabular-nums; }}
  .sc-empty {{ color:var(--muted); font-style:italic; }}

  .streak-pair {{ display:grid; gap:10px; margin:8px 0 12px; }}
  @media (min-width:680px) {{ .streak-pair {{ grid-template-columns:1fr 1fr; }} }}
  .streak-box {{ border:1px solid var(--line); border-radius:13px; padding:11px 12px; }}
  .win-box {{ background:var(--win-bg); }}
  .loss-box {{ background:var(--loss-bg); }}
  .streak-h {{ display:flex; align-items:baseline; gap:8px; margin-bottom:6px; }}
  .streak-n {{ font-size:1.6rem; font-weight:800; line-height:1; }}
  .win-box .streak-n {{ color:var(--win); }}
  .loss-box .streak-n {{ color:var(--loss); }}
  .streak-l {{ color:var(--muted); font-size:.78rem; }}
  .muted {{ color:var(--muted); font-size:.84rem; margin:4px 0; }}

  ul.wins {{ list-style:none; margin:0; padding:0; border:1px solid var(--line);
             border-radius:10px; overflow:hidden; background:var(--card); }}
  li.win {{ display:flex; align-items:center; gap:8px; padding:7px 10px; font-size:.8rem;
            border-top:1px solid var(--line); }}
  li.win:first-child {{ border-top:none; }}
  .w-dt {{ flex:0 0 auto; color:var(--muted); font-variant-numeric:tabular-nums; font-size:.74rem; }}
  .w-lv {{ flex:0 0 auto; width:18px; height:18px; line-height:18px; text-align:center;
           border-radius:5px; font-size:.64rem; font-weight:800; color:#fff; }}
  .w-lv.loc {{ background:var(--loc); }}
  .w-lv.vis {{ background:var(--vis); }}
  .w-club {{ flex:0 0 auto; font-weight:700; }}
  .w-rival {{ flex:1 1 auto; min-width:0; color:var(--muted); }}
  .w-sc {{ flex:0 0 auto; font-weight:800; font-variant-numeric:tabular-nums; }}

  footer {{ color:var(--muted); font-size:.78rem; margin:22px 2px 8px; line-height:1.5; }}

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
    <h1>Juan Manuel Sara — Entrenador</h1>
    <p class="def">Estadísticas de sus 7 gestiones como head coach (Primera Nacional / copas argentinas)</p>
    <nav class="nav">
      <a class="chip" href="#gestiones">Gestiones</a>
      <a class="chip" href="#vs-clubes">vs Clubes</a>
      <a class="chip" href="#vs-entrenadores">vs Entrenadores</a>
      <a class="chip" href="#efectividad">Efectividad</a>
      <a class="chip" href="#goleadores">Goleadores</a>
      <a class="chip" href="#rachas">Rachas</a>
    </nav>
  </header>

  <main class="wrap">
    {hero}
    {gestiones}
    {vs_clubes}
    {vs_entrenadores}
    {efectividad}
    {goleadores}
    {rachas}

    <footer>Fuente: Transfermarkt · Generado automáticamente el {generated}.
    Sistema de puntos uniforme <b>3-1-0</b> (victoria-empate-derrota) para todos los partidos,
    incluidas copas y torneos reducidos — por eso la efectividad/PPP calculados acá pueden diferir
    en centésimas del PPG que muestra el perfil de Transfermarkt en alguna gestión puntual.</footer>
  </main>

  <a href="#top" class="fab" id="fab" aria-label="Volver arriba">↑</a>

<script>
  const fab = document.getElementById('fab');
  addEventListener('scroll', () => fab.classList.toggle('show', scrollY > 700), {{passive:true}});
</script>
<script>
(function () {{
  var NA = "@@NA@@";
  function cellValue(td) {{
    var raw = td.getAttribute('data-sort');
    var v = raw !== null ? raw.trim() : td.textContent.trim();
    if (v === '' || v.toUpperCase() === 'N/A') return NA;
    return v;
  }}
  function isNumeric(v) {{
    if (v === NA) return false;
    var n = Number(v);
    return isFinite(n);
  }}
  function columnIsNumeric(tbody, idx) {{
    for (var i = 0; i < tbody.rows.length; i++) {{
      var td = tbody.rows[i].cells[idx];
      if (!td) continue;
      var v = cellValue(td);
      if (v === NA) continue;
      if (!isNumeric(v)) return false;
    }}
    return true;
  }}
  function compareValues(a, b, numeric, asc) {{
    var aNA = a === NA, bNA = b === NA;
    if (aNA && bNA) return 0;
    if (aNA) return 1;
    if (bNA) return -1;
    var cmp = numeric ? (Number(a) - Number(b)) : a.localeCompare(b, 'es', {{sensitivity: 'base'}});
    return asc ? cmp : -cmp;
  }}
  function sortTable(table, th) {{
    var headerRow = th.parentNode;
    var idx = Array.prototype.indexOf.call(headerRow.children, th);
    var tbody = table.tBodies[0];
    if (idx < 0 || !tbody) return;
    var asc = th.getAttribute('aria-sort') !== 'ascending';
    Array.prototype.forEach.call(headerRow.querySelectorAll('th.sortable'), function (h) {{
      h.setAttribute('aria-sort', h === th ? (asc ? 'ascending' : 'descending') : 'none');
    }});
    var numeric = columnIsNumeric(tbody, idx);
    var rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function (r1, r2) {{
      return compareValues(cellValue(r1.cells[idx]), cellValue(r2.cells[idx]), numeric, asc);
    }});
    rows.forEach(function (r) {{ tbody.appendChild(r); }});
  }}
  document.addEventListener('click', function (e) {{
    var th = e.target.closest('th.sortable');
    if (!th) return;
    var table = th.closest('table.sortable-table');
    if (!table) return;
    sortTable(table, th);
  }});
}})();
</script>
</body>
</html>
"""


def main():
    with open(STATS_PATH, encoding="utf-8") as f:
        stats = json.load(f)
    out = build_html(stats)
    local_path = os.path.join(HERE, "entrenador_sara.html")
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(out)
    print("HTML escrito en", local_path, "-", len(out), "bytes")
    docs = os.path.join(HERE, "..", "docs", "entrenador-sara")
    os.makedirs(docs, exist_ok=True)
    shutil.copy(local_path, os.path.join(docs, "index.html"))
    print("Copiado a", os.path.join(docs, "index.html"))


if __name__ == "__main__":
    main()
