"""
gen_html_wc.py - Informe HTML self-contained de la prediccion del prode (una fecha).

Lee data_mundial/pred_wc.json y escribe docs/mundial_fechaN.html: un unico archivo
autocontenido (CSS+JS embebidos, sin servidor, abrible offline), responsive, en espanol,
con el estilo y la calidad de gen_pred_html.py. El front es simple; la inteligencia esta
en el back (model_wc/market_wc/ratings_wc/prode_wc).

Contenido (seccion 7 del prompt): encabezado con procedencia y aviso honesto; tabla
resumen de la fecha con recomendaciones y puntos esperados totales; una tarjeta por
partido (P(1X2), lambdas, marcador recomendado para el prode resaltado, marcador mas
probable y ganador aparte, top-5, heatmap SVG, confianza); pie con metodologia y la
auto-evaluacion de la fecha ya jugada.
"""
import argparse
import html
import json
import os
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data_mundial")
DOCS = os.path.join(HERE, "docs")

DIAS = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
CONF_CLASS = {"alta": "c-alta", "media": "c-media", "baja": "c-baja"}
SRC_LABEL = {"live": "en vivo", "cache": "cache", "seed": "respaldo (seed)",
             "manual": "cargado a mano", "model": "modelo Elo (sin cuotas)"}

CSS = """
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
:root{
  --accent:#0a6b3b;--accent2:#13a05a;--ink:#10212e;--muted:#6a7b88;--line:#e7ecf1;
  --bg:#eef2f6;--card:#fff;--soft:#f4f7fa;--chip:#e3eaf0;
  --blue:#1f7ad1;--gold:#e0a400;--red:#d23b43;--orange:#d97a16;
  --shadow:0 1px 2px rgba(16,40,30,.06),0 8px 24px rgba(16,40,30,.07);
}
@media (prefers-color-scheme:dark){:root{
  --accent:#1fbf6f;--accent2:#15a05c;--ink:#e9eff4;--muted:#8da0ad;--line:#22303c;
  --bg:#0b1220;--card:#121c28;--soft:#0f1925;--chip:#1b2836;
  --blue:#5aa9ee;--gold:#e9b730;--red:#ff6b72;--orange:#e9963c;
  --shadow:0 1px 2px rgba(0,0,0,.5);
}}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);overflow-x:hidden;
  font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  padding-bottom:env(safe-area-inset-bottom)}
.bar{position:sticky;top:0;z-index:40;background:linear-gradient(180deg,var(--accent),var(--accent2));
  color:#fff;padding:calc(env(safe-area-inset-top) + 12px) 16px 12px;box-shadow:0 2px 10px rgba(0,0,0,.15)}
.bar h1{font-size:1.12rem;margin:0;font-weight:800;letter-spacing:.2px}
.bar .sub{font-size:.74rem;margin:3px 0 0;opacity:.93}
.wrap{padding:13px}
@media(min-width:980px){.wrap{max-width:1180px;margin:0 auto;padding:18px}}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;margin:0 0 13px;box-shadow:var(--shadow)}
.lbl{font-size:.64rem;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);font-weight:800;margin:0 0 8px}
.note{font-size:.82rem;color:var(--muted);margin:.4rem 0}
.banner{border-left:4px solid var(--orange);background:var(--soft);padding:9px 12px;border-radius:10px;font-size:.8rem;margin:0 0 12px}
.prov{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.pill{font-size:.66rem;font-weight:700;padding:3px 9px;border-radius:999px;background:var(--chip);color:var(--ink)}
.pill.live{background:#d7f0e1;color:#0a6b3b}.pill.seed{background:#fbe7cf;color:#9a5a12}.pill.cache{background:#e6edf6;color:#345}
@media (prefers-color-scheme:dark){.pill.live{background:#13361f;color:#7fe0a6}.pill.seed{background:#3a2a12;color:#e9b76a}.pill.cache{background:#1a2940;color:#a8c4ea}}

table.sum{width:100%;border-collapse:collapse;font-size:.84rem}
table.sum th{font-size:.6rem;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);text-align:left;padding:6px 7px;border-bottom:2px solid var(--line)}
table.sum td{padding:8px 7px;border-bottom:1px solid var(--line);vertical-align:middle}
table.sum td.r,table.sum th.r{text-align:right;font-variant-numeric:tabular-nums}
.rec-score{font-weight:800;background:var(--soft);border:1px solid var(--line);border-radius:7px;padding:2px 8px;white-space:nowrap}
.tot{font-weight:800}
.fav{font-weight:700}
.cn{display:inline-block;font-size:.62rem;font-weight:800;padding:2px 8px;border-radius:999px}
.c-alta{background:#d7f0e1;color:#0a6b3b}.c-media{background:#fbf1d4;color:#9a7a12}.c-baja{background:#fbe0e2;color:#b22}
@media (prefers-color-scheme:dark){.c-alta{background:#13361f;color:#7fe0a6}.c-media{background:#332a10;color:#e9c96a}.c-baja{background:#3a1416;color:#ff8e94}}

.grid{display:grid;gap:13px;grid-template-columns:1fr}
@media(min-width:980px){.grid{grid-template-columns:1fr 1fr}}
.match h3{margin:0;font-size:1.02rem;font-weight:800;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.flag{font-size:1.15rem;line-height:1}
.vs{color:var(--muted);font-weight:700}
.meta-row{font-size:.74rem;color:var(--muted);margin:5px 0 11px}
.gtag{display:inline-block;font-size:.62rem;font-weight:800;background:var(--chip);color:var(--ink);border-radius:6px;padding:1px 7px;margin-right:6px}

.barx{display:flex;height:24px;border-radius:8px;overflow:hidden;border:1px solid var(--line);font-size:.66rem;font-weight:800;color:#fff}
.barx i{display:flex;align-items:center;justify-content:center;min-width:0;white-space:nowrap}
.b1{background:var(--accent)}.bX{background:var(--muted)}.b2{background:var(--blue)}
.barleg{display:flex;justify-content:space-between;font-size:.66rem;color:var(--muted);margin:5px 1px 0;font-weight:700}

.plays{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:13px 0}
.play{border:1px solid var(--line);border-radius:12px;padding:10px;background:var(--soft)}
.play.hi{border:2px solid var(--accent);background:linear-gradient(180deg,rgba(19,160,90,.10),transparent)}
.play .k{font-size:.6rem;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:800}
.play .v{font-size:1.5rem;font-weight:800;margin-top:2px;line-height:1}
.play .x{font-size:.72rem;color:var(--muted);margin-top:2px}
.lam{font-size:.78rem;color:var(--muted);margin:2px 0 0}

.cols{display:grid;grid-template-columns:1.05fr .95fr;gap:12px;align-items:start;margin-top:6px}
@media(max-width:520px){.cols{grid-template-columns:1fr}}
table.top{width:100%;border-collapse:collapse;font-size:.78rem}
table.top th{font-size:.58rem;text-transform:uppercase;color:var(--muted);text-align:left;padding:4px 5px;font-weight:800}
table.top td{padding:4px 5px;border-top:1px solid var(--line);font-variant-numeric:tabular-nums}
table.top td.r{text-align:right}
table.top tr.best td{font-weight:800;background:var(--soft)}
.hmwrap{text-align:center}
.hmcap{font-size:.62rem;color:var(--muted);margin-top:3px}

.foot{font-size:.82rem;color:var(--muted)}
.foot h2{color:var(--ink);font-size:1rem;margin:0 0 6px}
.foot p{margin:.5rem 0}
.bt-grid{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.bt{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:7px 11px}
.bt b{display:block;font-size:1.1rem;color:var(--ink)}
.bt span{font-size:.66rem}
"""


def esc(s):
    return html.escape(str(s))


def fmt_kick(iso):
    """ISO -> 'Dom 14/06 · 16:00 (cierre 15:59)'."""
    try:
        dt = datetime.fromisoformat(iso)
    except Exception:
        return iso
    cierre = (dt - timedelta(minutes=1)).strftime("%H:%M")
    return f"{DIAS[dt.weekday()]} {dt.strftime('%d/%m')} · {dt.strftime('%H:%M')} (cierre {cierre})"


def fmt_dt(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso or "—"


def bar_1x2(p):
    """Barra apilada P(local)/P(empate)/P(visita) con porcentajes dentro."""
    p1, pX, p2 = p["p1"], p["pX"], p["p2"]
    seg = lambda cls, v: (f'<i class="{cls}" style="width:{v*100:.1f}%">'
                          f'{v*100:.0f}%</i>' if v > 0.06 else
                          f'<i class="{cls}" style="width:{v*100:.1f}%"></i>')
    return (f'<div class="barx">{seg("b1",p1)}{seg("bX",pX)}{seg("b2",p2)}</div>')


def heatmap_svg(P, rec, modo, hname, aname):
    """Heatmap SVG inline 7x7 de P(h,a). Resalta la celda recomendada (borde verde) y
    la mas probable (borde dorado). Sin dependencias externas."""
    n = 7
    cell, pad, top, left = 26, 2, 18, 22
    W = left + n * cell + 8
    H = top + n * cell + 18
    mx = max(max(row) for row in P) or 1.0
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:340px" '
           f'role="img" aria-label="Matriz de probabilidad de marcadores">']
    out.append(f'<text x="{left+n*cell/2}" y="11" text-anchor="middle" '
               f'font-size="9" fill="currentColor" opacity=".6">goles {esc(aname)} →</text>')
    out.append(f'<text x="9" y="{top+n*cell/2}" text-anchor="middle" font-size="9" '
               f'fill="currentColor" opacity=".6" transform="rotate(-90 9 {top+n*cell/2})">'
               f'goles {esc(hname)} →</text>')
    for h in range(n):
        out.append(f'<text x="{left-5}" y="{top+h*cell+cell/2+3}" text-anchor="end" '
                   f'font-size="9" fill="currentColor" opacity=".55">{h}</text>')
        out.append(f'<text x="{left+h*cell+cell/2}" y="{top-4}" text-anchor="middle" '
                   f'font-size="9" fill="currentColor" opacity=".55">{h}</text>')
        for a in range(n):
            v = P[h][a]
            inten = (v / mx) ** 0.6
            fill = f'rgba(19,160,90,{0.06 + 0.84*inten:.3f})'
            x, y = left + a * cell, top + h * cell
            stroke, sw = "rgba(0,0,0,.08)", 0.5
            if [h, a] == list(rec):
                stroke, sw = "var(--accent)", 2.2
            elif [h, a] == list(modo):
                stroke, sw = "var(--gold)", 2.0
            out.append(f'<rect x="{x}" y="{y}" width="{cell-pad}" height="{cell-pad}" '
                       f'rx="3" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
            if v >= 0.05:
                out.append(f'<text x="{x+(cell-pad)/2}" y="{y+(cell-pad)/2+3}" '
                           f'text-anchor="middle" font-size="7.5" fill="var(--ink)" '
                           f'opacity=".8">{v*100:.0f}</text>')
    out.append('</svg>')
    return "".join(out)


def match_card(p, teams):
    h, a = teams[p["home"]], teams[p["away"]]
    rec = p["rec"]; modo = p["modo"]
    conf_cls = CONF_CLASS.get(p["confianza"], "c-media")
    fav_txt = {"1": h["name"], "X": "Empate", "2": a["name"]}[p["favorito"]]

    top_rows = []
    for c in p["top"]:
        best = (c["score"] == rec)
        cls = ' class="best"' if best else ""
        mark = " ⭐" if best else ""
        top_rows.append(
            f'<tr{cls}><td>{c["score"][0]}–{c["score"][1]}{mark}</td>'
            f'<td class="r">{c["prob"]*100:.1f}%</td>'
            f'<td class="r">{c["ev"]:.2f}</td></tr>')

    lam_mkt = ("" if p["lh_mkt"] is None else
               f' · mercado {p["lh_mkt"]:.2f}–{p["la_mkt"]:.2f}')
    market_tag = (f'mercado {int(p["w_mkt"]*100)}% ({esc(p["bookmaker"])})'
                  if p["market_used"] else "sin cuota: solo Elo/forma")

    return f"""
<section class="card match">
  <h3><span class="flag">{h['flag']}</span>{esc(h['name'])}
      <span class="vs">vs</span>
      <span class="flag">{a['flag']}</span>{esc(a['name'])}</h3>
  <div class="meta-row"><span class="gtag">Grupo {p['group']}</span>{esc(fmt_kick(p['kickoff']))}
      &nbsp;·&nbsp;{esc(p.get('venue') or '')}</div>

  {bar_1x2(p)}
  <div class="barleg"><span>Local {p['p1']*100:.0f}%</span>
      <span>Empate {p['pX']*100:.0f}%</span><span>Visita {p['p2']*100:.0f}%</span></div>
  <div class="lam">λ esperados (goles): <b>{esc(h['name'])} {p['lh']:.2f}</b> – <b>{p['la']:.2f} {esc(a['name'])}</b>
      &nbsp;·&nbsp;{market_tag}{lam_mkt}</div>

  <div class="plays">
    <div class="play hi">
      <div class="k">★ Recomendado para el prode</div>
      <div class="v">{rec[0]}–{rec[1]}</div>
      <div class="x">{p['ev_rec']:.2f} pts esperados · maximiza el puntaje</div>
    </div>
    <div class="play">
      <div class="k">Marcador mas probable</div>
      <div class="v">{modo[0]}–{modo[1]}</div>
      <div class="x">{p['modo_prob']*100:.1f}% · ganador: {esc(fav_txt)}</div>
    </div>
  </div>

  <div class="cols">
    <div>
      <div class="lbl">Top-5 marcadores por puntos esperados</div>
      <table class="top"><tr><th>Marcador</th><th class="r">Prob.</th><th class="r">E[pts]</th></tr>
        {''.join(top_rows)}</table>
    </div>
    <div class="hmwrap">
      <div class="lbl">Mapa de calor P(h,a)</div>
      {heatmap_svg(p['heatmap'], rec, modo, h['name'], a['name'])}
      <div class="hmcap">borde verde = recomendado · borde dorado = mas probable</div>
    </div>
  </div>

  <div class="note" style="margin-top:10px">
    Confianza <span class="cn {conf_cls}">{p['confianza'].upper()}</span>
    &nbsp;(entropia 1X2 {p['entropia']}, brecha E[pts] 1ª–2ª {p['gap']:.2f}) ·
    Monte Carlo {p['mc']['n']:,} sims
  </div>
</section>"""


def summary_table(preds, teams, ev_total):
    rows = []
    for p in preds:
        h, a = teams[p["home"]], teams[p["away"]]
        fav_p = max(p["p1"], p["pX"], p["p2"])
        fav_txt = {"1": h["name"], "X": "Empate", "2": a["name"]}[p["favorito"]]
        rows.append(
            f'<tr><td>{h["flag"]} {esc(h["name"])} <span class="vs">vs</span> '
            f'{a["flag"]} {esc(a["name"])}<br><span class="note" style="font-size:.7rem">'
            f'Grupo {p["group"]} · {esc(fmt_kick(p["kickoff"]).split("·")[0].strip())}</span></td>'
            f'<td><span class="rec-score">{p["rec"][0]}–{p["rec"][1]}</span></td>'
            f'<td class="fav">{esc(fav_txt)} <span class="note">{fav_p*100:.0f}%</span></td>'
            f'<td class="r">{p["ev_rec"]:.2f}</td>'
            f'<td><span class="cn {CONF_CLASS.get(p["confianza"],"c-media")}">'
            f'{p["confianza"].upper()}</span></td></tr>')
    return f"""
<table class="sum">
  <tr><th>Partido</th><th>Reco.</th><th>Favorito</th><th class="r">E[pts]</th><th>Conf.</th></tr>
  {''.join(rows)}
  <tr><td class="tot">Total de la fecha ({len(preds)} partidos)</td><td></td><td></td>
      <td class="r tot">{ev_total:.1f}</td><td></td></tr>
</table>"""


def backtest_block(bt, teams):
    if not bt.get("n"):
        return '<p class="note">Todavia no hay partidos jugados de esta fecha para auto-evaluar.</p>'
    rows = []
    for r in bt["rows"]:
        h, a = teams[r["home"]], teams[r["away"]]
        ok = "✅" if r["acerto_ganador"] else "❌"
        rows.append(
            f'<tr><td>{h["flag"]} {esc(h["name"])} {r["real"][0]}–{r["real"][1]} '
            f'{esc(a["name"])} {a["flag"]}</td>'
            f'<td><span class="rec-score">{r["rec"][0]}–{r["rec"][1]}</span></td>'
            f'<td class="r">{ok} {r["pts"]}</td></tr>')
    return f"""
<div class="bt-grid">
  <div class="bt"><b>{bt['total_pts']}/{bt['max_pts']}</b><span>puntos del prode ({bt['pct_max']}% del maximo)</span></div>
  <div class="bt"><b>{bt['avg_pts']}</b><span>promedio por partido</span></div>
  <div class="bt"><b>{bt['acc_ganador']*100:.0f}%</b><span>acierto del ganador</span></div>
  <div class="bt"><b>{bt['brier']}</b><span>Brier score 1X2</span></div>
  <div class="bt"><b>{bt['logloss']}</b><span>log-loss 1X2</span></div>
</div>
<table class="top"><tr><th>Resultado real</th><th>Predijo</th><th class="r">Puntos</th></tr>
  {''.join(rows)}</table>"""


def provenance_block(prov):
    pills = []
    degraded = manual = model = False
    for k, label in [("fixtures", "fixtures/resultados"), ("odds", "cuotas"),
                     ("teams", "Elo/fuerza")]:
        s = prov[k]["source"]
        if s == "manual":
            manual = True
        elif s == "model":
            model = True
        elif s != "live":
            degraded = True
        pills.append(f'<span class="pill {s}">{label}: {SRC_LABEL.get(s, s)} '
                     f'· {esc(fmt_dt(prov[k].get("fetched_at")))}</span>')
    banner = ""
    if model:
        banner = ('<div class="banner">📐 <b>Predicción solo-modelo:</b> sin cuotas en '
                  'vivo en este entorno, las probabilidades salen del modelo de fuerza '
                  '(Elo + forma con xG + Dixon-Coles). Es menos afilado que con mercado: '
                  'corriendo local con cuotas reales, el mercado ancla el "quién gana".</div>')
    elif manual:
        banner = ('<div class="banner">✍️ <b>Cuotas cargadas a mano:</b> las '
                  'probabilidades 1X2 y los λ salen de las cuotas reales que ingresaste '
                  '(de-vigadas). El motor del prode es el mismo; solo cambia el origen de '
                  'los datos de entrada.</div>')
    elif degraded:
        banner = ('<div class="banner">⚠️ <b>Modo degradado:</b> la red del entorno '
                  'bloquea las fuentes en vivo, asi que se usa el ultimo cache o el seed '
                  'de respaldo versionado. El motor es el mismo; solo cambian los datos de '
                  'entrada. Whitelist de red necesaria: ver README.</div>')
    return banner, f'<div class="prov">{"".join(pills)}</div>'


def build(fecha=None):
    d = json.load(open(os.path.join(DATA, "pred_wc.json"), encoding="utf-8"))
    if fecha is not None and d["meta"]["fecha"] != fecha:
        raise SystemExit(f"pred_wc.json es de la fecha {d['meta']['fecha']}, no {fecha}. "
                         f"Corré primero: python predict_wc.py --fecha {fecha}")
    m = d["meta"]; teams = d["teams"]; preds = d["pendientes"]
    # Etiqueta y archivo de salida: por defecto "Fecha N"; el modo manual (predict_cli)
    # puede pasar un titulo/nombre propio via meta (p.ej. "Hoy" -> mundial_hoy.html).
    fecha = d["meta"]["fecha"]
    label = m.get("titulo") or f"Fecha {fecha}"
    out_name = m.get("out_name") or f"mundial_fecha{fecha}.html"
    cg = m["confianza_global"]
    banner, prov_html = provenance_block(m["provenance"])
    cards = "".join(match_card(p, teams) for p in preds)

    body = f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0a6b3b" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0b1220" media="(prefers-color-scheme: dark)">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:image/svg+xml,&lt;svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'&gt;&lt;text y='.9em' font-size='90'&gt;⚽&lt;/text&gt;&lt;/svg&gt;">
<title>Prode Mundial 2026 · {label}</title>
<style>{CSS}</style></head>
<body>
<div class="bar">
  <h1>⚽ Prode Mundial 2026 · {label}</h1>
  <div class="sub">Predicciones optimizadas para MAXIMIZAR puntos del prode ·
     generado {esc(fmt_dt(m['generado']))} · datos al {esc(fmt_dt(m['datos_al']))}</div>
</div>
<div class="wrap">

  {banner}

  <section class="card">
    <p class="lbl">Resumen de la fecha</p>
    <p class="note" style="margin-top:-2px">
      {len(preds)} partidos pendientes · {m['n_jugados']} ya jugados (se usan para calibrar) ·
      <b>{m['ev_total']:.1f} puntos esperados</b> en total ·
      confianza: <span class="cn c-alta">{cg['alta']} alta</span>
      <span class="cn c-media">{cg['media']} media</span>
      <span class="cn c-baja">{cg['baja']} baja</span>
    </p>
    {prov_html}
    <div style="margin-top:12px">{summary_table(preds, teams, m['ev_total'])}</div>
    <p class="note" style="margin-top:11px">
      <b>Aviso honesto:</b> esto es un <b>mapa de probabilidades</b>, no una certeza. El
      futbol es de alta varianza: el numero serio es la <b>probabilidad</b> y el <b>valor
      esperado de puntos</b>, no el marcador puntual. El "marcador recomendado" es el que
      maximiza los puntos esperados del prode sobre TODA la distribucion de resultados —
      por eso suele diferir del marcador mas probable.
    </p>
  </section>

  <p class="lbl" style="margin:4px 2px 8px">Partido por partido</p>
  <div class="grid">{cards}</div>

  <section class="card foot">
    <h2>Auto-evaluacion · {label} (partidos ya jugados)</h2>
    <p>Cuantos puntos del prode habria sacado este mismo modelo en los partidos de la
       fecha que ya se jugaron, prediciendo cada uno con la informacion disponible
       <i>antes</i> de jugarse (sin fuga de informacion) y puntuando con la tabla oficial.</p>
    {backtest_block(d['backtest'], teams)}

    <h2 style="margin-top:16px">Metodologia (en criollo)</h2>
    <p><b>1) El mercado manda en el "quien gana".</b> Las cuotas de las casas (de-vigadas,
       sin el margen) son el mejor predictor que existe. De ellas salen las probabilidades
       1X2 limpias, la supremacia (handicap) y el total de goles (Over/Under).</p>
    <p><b>2) Dixon-Coles da la granularidad del marcador.</b> Un Poisson bivariado con la
       correccion de marcadores bajos arma la matriz P(h,a) de cada partido, centrada en los
       goles esperados λ (mezcla convexa mercado↔Elo; el mercado pesa {int(m['w_mkt']*100)}% en
       esta fecha). Las marginales 1X2 de la matriz se anclan al mercado.</p>
    <p><b>3) El optimizador del prode elige la jugada.</b> Como el prode da puntos por "casi
       acertar", el marcador que mas puntos espera NO es el mas probable: para cada partido se
       calcula E[pts] de cada candidato sobre toda la distribucion y se elige el maximo.</p>
    <p><b>4) Monte Carlo</b> ({m['n_sims']:,} simulaciones por partido) confirma la robustez de
       las probabilidades y la confianza. La fuerza base es Elo internacional con bonus modesto
       a los anfitriones; la forma in-tournament gana peso fecha a fecha.</p>
    <p style="margin-top:10px"><b>Limitaciones.</b> Sin ajustes a mano por opinion: los pesos
       salen de los datos/calibracion. El Mundial tiene muestras chicas y mucha varianza; la
       Fecha 1 se apoya casi toda en el mercado. Si una fuente en vivo no responde, el sistema
       corre con cache/seed y lo avisa arriba. Reusable tal cual para la Fecha 2 y la Fecha 3
       (<code>python update_wc.py --fecha N</code>).</p>
  </section>

  <p class="note" style="text-align:center;margin:18px 0 8px">
     Generado por el motor de prediccion del repo · {esc(fmt_dt(m['generado']))}</p>
</div>
</body></html>"""

    os.makedirs(DOCS, exist_ok=True)
    out_path = os.path.join(DOCS, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(body)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="HTML self-contained del prode (una fecha)")
    ap.add_argument("--fecha", type=int, required=True)
    args = ap.parse_args()
    path = build(args.fecha)
    print(f"HTML generado: {os.path.relpath(path, HERE)}  ({os.path.getsize(path)//1024} KB)")


if __name__ == "__main__":
    main()
