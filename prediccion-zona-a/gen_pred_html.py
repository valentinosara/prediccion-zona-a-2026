"""
gen_pred_html.py - Informe HTML interactivo de la PREDICCION de la Zona A 2026.
Lee data_promiedos/pred_results.json. Mobile-first + 2 columnas en PC.
- Eje = ORDEN CRONOLOGICO real de disputa (la F4 postergada va en su lugar).
- Tabla en CSS grid (header y filas comparten grilla -> alineados) + escudos.
- En pantalla ancha: tabla y partidos de la fecha, lado a lado (como Promiedos).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DP = os.path.join(HERE, "data_promiedos")

TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0a6b3b" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0b1220" media="(prefers-color-scheme: dark)">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:image/svg+xml,&lt;svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'&gt;&lt;text y='.9em' font-size='90'&gt;🔮&lt;/text&gt;&lt;/svg&gt;">
<title>Predicción · Zona A 2026</title>
<style>
  :root{
    --accent:#0a6b3b;--accent2:#13a05a;--ink:#10212e;--muted:#6a7b88;--line:#e7ecf1;
    --bg:#eef2f6;--card:#fff;--soft:#f4f7fa;--chip:#e3eaf0;
    --gold:#e0a400;--blue:#1f7ad1;--orange:#d97a16;--red:#d23b43;
    --blue-bg:#e7f1fb;--gold-bg:#fbf1d4;
    --shadow:0 1px 2px rgba(16,40,30,.06),0 8px 24px rgba(16,40,30,.07);
  }
  @media (prefers-color-scheme:dark){:root{
    --accent:#1fbf6f;--accent2:#15a05c;--ink:#e9eff4;--muted:#8da0ad;--line:#22303c;
    --bg:#0b1220;--card:#121c28;--soft:#0f1925;--chip:#1b2836;
    --gold:#e9b730;--blue:#5aa9ee;--orange:#e9963c;--red:#ff6b72;
    --blue-bg:#13283a;--gold-bg:#2c2410;
    --shadow:0 1px 2px rgba(0,0,0,.5);
  }}
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--bg);color:var(--ink);overflow-x:hidden;
    font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    padding-bottom:env(safe-area-inset-bottom)}
  a{color:var(--accent)}
  .bar{position:sticky;top:0;z-index:40;background:linear-gradient(180deg,var(--accent),var(--accent2));
    color:#fff;padding:calc(env(safe-area-inset-top) + 11px) 16px 11px;box-shadow:0 2px 10px rgba(0,0,0,.15)}
  .bar h1{font-size:1.06rem;margin:0;font-weight:800;letter-spacing:.2px}
  .bar .def{font-size:.74rem;margin:2px 0 0;opacity:.92}
  .wrap{padding:13px}
  @media(min-width:980px){.wrap{max-width:1140px;margin:0 auto;padding:18px}}
  .lead{color:var(--muted);font-size:.84rem;margin:0 2px 12px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:13px;margin:0 0 12px;box-shadow:var(--shadow)}
  .lbl{font-size:.66rem;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);font-weight:800;margin:0 0 7px}

  .seg{display:flex;gap:5px;background:var(--soft);border:1px solid var(--line);border-radius:13px;padding:4px}
  .seg button{flex:1;border:0;background:transparent;color:var(--ink);font-weight:800;font-size:.76rem;padding:9px 4px;border-radius:10px;cursor:pointer;line-height:1.15}
  .seg button.on{background:var(--accent);color:#fff;box-shadow:0 2px 8px rgba(10,107,59,.3)}
  .seg small{display:block;font-weight:600;font-size:.6rem;opacity:.8;margin-top:2px}

  .nav{display:flex;align-items:center;gap:9px;margin-top:11px}
  .nav button.arrow{width:44px;height:44px;flex:0 0 auto;border-radius:50%;border:1px solid var(--line);background:var(--soft);color:var(--ink);font-size:1.3rem;font-weight:700;cursor:pointer;line-height:1}
  .nav button.arrow:active{transform:scale(.92)}
  .nav .play{margin-left:auto;background:var(--accent);color:#fff;border-color:transparent}
  .fnow{flex:1;text-align:center}.fnow b{font-size:1.1rem}
  .ftag{display:inline-block;font-size:.64rem;font-weight:800;padding:2px 8px;border-radius:999px;margin-top:2px}
  .t-real{background:var(--blue-bg);color:var(--blue)}
  .t-proj{background:var(--gold-bg);color:var(--gold)}

  .strip{display:flex;gap:6px;overflow-x:auto;margin-top:11px;padding:2px 0 6px;scrollbar-width:none;scroll-snap-type:x proximity}
  .strip::-webkit-scrollbar{display:none}
  .fc{flex:0 0 auto;scroll-snap-align:center;min-width:38px;height:42px;border-radius:11px;border:1px solid var(--line);background:var(--soft);cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;font-weight:800;font-size:.82rem;color:var(--ink);position:relative}
  .fc .d{width:5px;height:5px;border-radius:50%;margin-top:2px}
  .fc .d.r{background:var(--blue)}.fc .d.p{background:var(--gold)}
  .fc.on{background:var(--accent);color:#fff;border-color:transparent;transform:scale(1.06)}
  .fc.on .d{background:#fff}
  .fc.resched{border-color:var(--orange);box-shadow:0 0 0 1px var(--orange) inset}
  .fc .rs{position:absolute;top:-2px;right:-2px;font-size:.5rem;background:var(--orange);color:#fff;border-radius:50%;width:11px;height:11px;line-height:11px}

  /* 2 columnas en PC */
  .split{display:grid;gap:12px;grid-template-columns:1fr}
  @media(min-width:980px){.split{grid-template-columns:1.35fr 1fr;align-items:start}
    .split .games-card{position:sticky;top:84px}}

  .gr{display:grid;grid-template-columns:26px 24px 1fr 56px 28px 46px;align-items:center;gap:0}
  .thead{border-left:4px solid transparent;padding:0 6px 8px}
  .thead .c{font-size:.6rem;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);font-weight:800}
  .row{border-left:4px solid var(--tc,transparent);padding:8px 6px;border-top:1px solid var(--line);background:var(--card)}
  .row:first-of-type{border-top:none}
  .row:nth-child(even){background:var(--soft)}
  .c{min-width:0}.c.r{text-align:right;font-variant-numeric:tabular-nums}
  .c.pos{display:flex}
  .badge{width:23px;height:23px;border-radius:7px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.76rem;background:var(--chip);color:var(--ink)}
  .row.d-gold .badge{background:var(--gold);color:#1a1300}
  .row.d-blue .badge{background:var(--blue);color:#fff}
  .row.d-orange .badge{background:var(--orange);color:#fff}
  .row.d-red .badge{background:var(--red);color:#fff}
  .esc{display:flex;align-items:center;justify-content:center}
  .esc img{width:20px;height:20px;object-fit:contain;display:block}
  .tm{font-weight:700;font-size:.88rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-left:4px}
  .mv{font-size:.64rem;font-weight:800;margin-left:5px}
  .up{color:#1aa251}.dn{color:var(--red)}.eq{color:var(--muted);opacity:.45}
  .pts{font-weight:800;font-size:.98rem}.sub{color:var(--muted);font-size:.82rem}
  .leg{display:flex;flex-wrap:wrap;gap:9px 14px;font-size:.7rem;color:var(--muted);margin-top:11px;padding-top:10px;border-top:1px solid var(--line)}
  .leg span{display:inline-flex;align-items:center;gap:5px}
  .dot{width:11px;height:11px;border-radius:4px}

  .game{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center;padding:9px 2px;border-top:1px solid var(--line);font-size:.84rem}
  .game:first-child{border-top:none}
  .gh{text-align:right;font-weight:600}.ga{font-weight:600}
  .gsc{font-weight:800;background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:3px 9px;white-space:nowrap;text-align:center}
  .gsc.proj{color:var(--muted)}
  .gbar{grid-column:1/-1;display:flex;height:6px;border-radius:4px;overflow:hidden;border:1px solid var(--line);margin-top:-2px}
  .gbar i{display:block}.b1{background:var(--accent)}.bX{background:var(--muted);opacity:.5}.b2{background:var(--blue)}
  .gpm{grid-column:1/-1;font-size:.64rem;color:var(--muted);text-align:center}
  .izz{font-size:.58rem;color:var(--orange);font-weight:800;text-transform:uppercase}

  .mcrow{display:grid;grid-template-columns:1fr 64px 56px 48px;align-items:center;gap:6px;padding:6px 2px;border-top:1px solid var(--line);font-size:.8rem}
  .mcrow.head{font-size:.6rem;text-transform:uppercase;color:var(--muted);font-weight:800;border-top:none}
  .mcrow .r{text-align:right;font-variant-numeric:tabular-nums}
  .mcbar{height:7px;border-radius:4px;background:var(--gold);display:inline-block;vertical-align:middle;margin-right:5px}

  details.info{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:0 0 12px;box-shadow:var(--shadow)}
  details.info>summary{cursor:pointer;padding:12px 14px;font-weight:800;list-style:none;font-size:.9rem}
  details.info>summary::-webkit-details-marker{display:none}
  details.info .body{padding:0 14px 13px;font-size:.85rem;color:var(--ink)}
  details.info .body li{margin:5px 0}
  .warn{border-left:4px solid var(--orange)}
  .sqrow{display:grid;grid-template-columns:1fr 70px 48px;gap:6px;padding:4px 2px;border-top:1px solid var(--line);font-size:.8rem}
  .sqrow.head{color:var(--muted);font-size:.62rem;text-transform:uppercase;font-weight:800;border-top:none}
  .sqrow .r{text-align:right;font-variant-numeric:tabular-nums}
  .bt{font-size:.84rem;line-height:1.5}
  footer{color:var(--muted);font-size:.74rem;margin:16px 2px 8px}
</style>
</head>
<body id="top">
<header class="bar">
  <h1>🔮 Predicción · Zona A · Primera Nacional 2026</h1>
  <p class="def">Proyección por modelo, no certeza · el ascenso de la B Nacional es muy impredecible</p>
</header>
<main class="wrap">
  <p class="lead">Tabla <b>real al <span id="asof">—</span></b> y cómo la proyecta el modelo hasta el final.
  Elegí cuánto pesa el <b>plantel</b> y movete por las fechas en <b>orden cronológico</b> real
  (las postergadas aparecen en su lugar).</p>

  <div class="card">
    <p class="lbl">¿Cuánto pesa el plantel? (valor de mercado vs forma)</p>
    <div class="seg" id="seg">
      <button data-v="forma">Solo forma<small>ignora plantel</small></button>
      <button data-v="calibrado" class="on">Calibrado<small>68/32 · historia</small></button>
      <button data-v="plantel">Plantel alto<small>60% · sensib.</small></button>
    </div>
    <div class="nav">
      <button class="arrow" id="prev" aria-label="fecha anterior">‹</button>
      <div class="fnow"><b id="fnum">Fecha 15</b><br><span class="ftag" id="ftag"></span></div>
      <button class="arrow" id="next" aria-label="fecha siguiente">›</button>
      <button class="arrow play" id="play" aria-label="animar">▶</button>
    </div>
    <div class="strip" id="strip"></div>
  </div>

  <div class="split">
    <div class="card">
      <div class="gr thead"><span class="c">#</span><span class="c"></span><span class="c">Equipo</span>
        <span class="c r">Pts</span><span class="c r">PJ</span><span class="c r">DG</span></div>
      <div id="tbody"></div>
      <div class="leg">
        <span><i class="dot" style="background:var(--gold)"></i>1º Final</span>
        <span><i class="dot" style="background:var(--blue)"></i>2º-8º Reducido</span>
        <span><i class="dot" style="background:var(--orange)"></i>17º promoción</span>
        <span><i class="dot" style="background:var(--red)"></i>18º desciende</span>
      </div>
      <p class="gpm" id="ptsnote" style="margin-top:9px"></p>
    </div>

    <div class="card games-card">
      <p class="lbl" id="gtitle">Partidos</p>
      <div id="games"></div>
    </div>
  </div>

  <div class="card">
    <p class="lbl">¿Por qué el plantel pesa 32%? · backtest 2021-2025</p>
    <div class="bt" id="btbody"></div>
  </div>

  <div class="card">
    <p class="lbl">Proyección final · probabilidades (20.000 simulaciones)</p>
    <div class="mcrow head"><span>Equipo</span><span class="r">Campeón</span><span class="r">Reducido</span><span class="r">Desc.</span></div>
    <div id="mcbody"></div>
  </div>

  <details class="info"><summary>👥 Plantel (valor / edad) y contexto de DTs</summary>
  <div class="body">
    <div class="sqrow head"><span>Equipo</span><span class="r">Valor</span><span class="r">Edad</span></div>
    <div id="sqbody"></div>
    <p style="margin-top:10px"><b>Contexto (se documenta, no se mete como número):</b></p>
    <ul>
      <li><b>“La trituradora”:</b> ~22 DTs dejaron su cargo en la Primera Nacional 2026 tras 13-14 fechas → torneo muy volátil.</li>
      <li><b>Colón</b> y <b>Godoy Cruz</b> vienen de Primera: planteles más caros (€6,4m y €9,5m).</li>
      <li><b>Ciudad de Bolívar:</b> la sorpresa — arriba con uno de los planteles más baratos (€1,8m).</li>
      <li><b>Morón</b> mantuvo a Walter Otta. <b>Defensores de Belgrano</b> cambió de DT (salió Nardozza).</li>
    </ul>
  </div></details>

  <details class="info warn"><summary>📐 Cómo se hizo + límites</summary>
  <div class="body">
    <ul>
      <li><b>Datos:</b> Promiedos (resultados + fixture). Las fechas siguen el <b>orden cronológico real</b>: la Fecha 4 fue suspendida y reprogramada al 20/06, por eso aparece tarde. La Fecha 36 (sin fixture aún) se dedujo de los cruces faltantes.</li>
      <li><b>Modelo:</b> Poisson ataque/defensa + localía. Tabla con <b>puntos esperados</b>; probabilidades por <b>Monte Carlo</b>.</li>
      <li><b>Peso del plantel (32%) calibrado por backtest</b> 2021-2025, no a dedo. En estas 14 fechas el plantel explica solo <b id="r2"></b> de la calidad.</li>
      <li><b>Límite honesto:</b> escenario probable, no certeza (R²≈0,14 para predecir el resto).</li>
    </ul>
  </div></details>

  <footer>Fuentes: Promiedos · Transfermarkt · Doble Amarilla/El Gráfico. Modelo propio. Generado el <span id="genat">—</span>.</footer>
</main>

<script id="data" type="application/json">__DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('data').textContent);
let V='calibrado', F=14, timer=null;  // F = PASO en orden cronologico (1..36). 14 = presente
const NSTEPS=DATA.variants.calibrado.standings_by_fecha.length;
const r2el=document.getElementById('r2'); if(r2el) r2el.textContent=Math.round(DATA.meta.prior_r2*100)+'%';
{const a=document.getElementById('asof'); if(a) a.textContent=DATA.meta.datos_al||DATA.meta.generado;
 const ga=document.getElementById('genat'); if(ga) ga.textContent=DATA.meta.generado;}
function destClass(p){return p===1?'d-gold':(p>=2&&p<=8?'d-blue':(p===17?'d-orange':(p===18?'d-red':'')));}
function fmtVal(v){return v>=1e6?'€'+(v/1e6).toFixed(2)+'m':'€'+Math.round(v/1e3)+'k';}
function snapOf(step){return DATA.variants[V].standings_by_fecha[step-1];}

function buildStrip(){
  const s=document.getElementById('strip'); s.innerHTML=''; let prevF=0;
  for(let k=1;k<=NSTEPS;k++){
    const snap=snapOf(k);
    const resched = snap.fecha < prevF;       // jornada que rompe el orden = reprogramada
    prevF = snap.fecha;
    const el=document.createElement('div'); el.className='fc'+(k===F?' on':'')+(resched?' resched':'');
    el.innerHTML=`${snap.fecha}<span class="d ${snap.is_real?'r':'p'}"></span>`+(resched?'<span class="rs">↺</span>':'');
    if(resched) el.title='Fecha '+snap.fecha+' (postergada, se juega el 20/06)';
    el.onclick=()=>setF(k);
    s.appendChild(el);
  }
}
function syncStrip(){[...document.querySelectorAll('#strip .fc')].forEach((el,i)=>{
  const on=(i+1)===F; el.classList.toggle('on',on);
  if(on) el.scrollIntoView({inline:'center',block:'nearest',behavior:'smooth'});});}

function render(animate){
  const snap=snapOf(F), prev=F>1?snapOf(F-1):null;
  const prevPos={}; if(prev) prev.rows.forEach(r=>prevPos[r.id]=r.pos);
  document.getElementById('fnum').textContent='Fecha '+snap.fecha;
  const tag=document.getElementById('ftag');
  tag.textContent=snap.is_real?'jugada (real)':'proyectada';
  tag.className='ftag '+(snap.is_real?'t-real':'t-proj');

  const tb=document.getElementById('tbody');
  const old={}; tb.querySelectorAll('.row').forEach(r=>old[r.dataset.id]=r.getBoundingClientRect().top);
  tb.innerHTML='';
  snap.rows.forEach(r=>{
    const t=DATA.teams[r.id];
    const row=document.createElement('div'); row.className='row gr '+destClass(r.pos);
    row.dataset.id=r.id; row.style.setProperty('--tc',t.color);
    let mv='<span class="mv eq">·</span>';
    if(prev){const d=prevPos[r.id]-r.pos; mv=d>0?`<span class="mv up">▲${d}</span>`:(d<0?`<span class="mv dn">▼${-d}</span>`:'<span class="mv eq">·</span>');}
    const pts=Number.isInteger(r.pts)?r.pts:r.pts.toFixed(1);
    row.innerHTML=`<span class="c pos"><span class="badge">${r.pos}</span></span>
      <span class="c esc">${t.badge?`<img src="${t.badge}" alt="">`:''}</span>
      <span class="c"><span class="tm">${t.name}</span>${mv}</span>
      <span class="c r pts">${pts}</span><span class="c r sub">${r.pj}</span>
      <span class="c r sub">${r.dif>0?'+':''}${r.dif}</span>`;
    tb.appendChild(row);
  });
  if(animate){tb.querySelectorAll('.row').forEach(row=>{
    const o=old[row.dataset.id]; if(o==null)return; const dy=o-row.getBoundingClientRect().top; if(!dy)return;
    row.style.transition='none'; row.style.transform=`translateY(${dy}px)`;
    requestAnimationFrame(()=>{row.style.transition='transform .5s cubic-bezier(.2,.7,.2,1)';row.style.transform='';});});}
  const realCount=DATA.variants[V].standings_by_fecha.filter(x=>x.is_real).length;
  document.getElementById('ptsnote').textContent = F<=realCount
    ? 'Puntos reales (coincide con la tabla oficial).'
    : 'Pts y DG = reales + esperados del modelo (promedio).';

  const gt=document.getElementById('gtitle'), gv=document.getElementById('games');
  gt.textContent=(snap.is_real?'Resultados · Fecha ':'Pronóstico · Fecha ')+snap.fecha;
  const gs=DATA.variants[V].fixture.filter(x=>x.fecha===snap.fecha);
  gv.innerHTML=gs.map(g=>{
    const p=g.pred, played=g.played;
    const sc=played?`${g.hs}-${g.as}`:`${p.hs}-${p.as}`;
    const iz=g.interzonal?'<span class="izz">interz.</span> ':'';
    let extra='';
    if(!played){extra=`<div class="gbar"><i class="b1" style="width:${p.p1*100}%"></i><i class="bX" style="width:${p.pX*100}%"></i><i class="b2" style="width:${p.p2*100}%"></i></div>
      <div class="gpm">L ${Math.round(p.p1*100)}% · E ${Math.round(p.pX*100)}% · V ${Math.round(p.p2*100)}%</div>`;}
    return `<div class="game"><span class="gh">${iz}${g.home}</span><span class="gsc ${played?'':'proj'}">${sc}</span><span class="ga">${g.away}</span>${extra}</div>`;
  }).join('');
}

function renderStatic(){
  const b=DATA.meta.backtest;
  document.getElementById('btbody').innerHTML=
    `En 5 temporadas previas (${b.n} casos), a los planteles más caros les fue <b>algo</b> mejor:
     correlación <b>+${b.corr_value_total}</b> (~${Math.round(b.corr_value_total**2*100)}%). A mitad de torneo la
     forma pesa más que el plantel (β forma <b>${b.beta_form}</b> vs plantel <b>${b.beta_value}</b>).
     De ahí el peso: <b>forma ${Math.round((1-b.alpha)*100)}% / plantel ${Math.round(b.alpha*100)}%</b> — no a dedo.`;
  const mc=snapOf(NSTEPS).rows;
  document.getElementById('mcbody').innerHTML=mc.map(r=>{const m=r.mc;
    return `<div class="mcrow"><span>${DATA.teams[r.id].name}</span>
      <span class="r"><span class="mcbar" style="width:${Math.max(1,m.p_champ*55)}px"></span>${Math.round(m.p_champ*100)}%</span>
      <span class="r">${Math.round(m.p_top8*100)}%</span>
      <span class="r">${m.p_last>=0.1?Math.round(m.p_last*100):(m.p_last*100).toFixed(1)}%</span></div>`;}).join('');
  const sq=Object.entries(DATA.squad).map(([id,s])=>({n:DATA.teams[id].name,...s})).sort((a,b)=>b.value-a.value);
  document.getElementById('sqbody').innerHTML=sq.map(s=>`<div class="sqrow"><span>${s.n}</span><span class="r">${fmtVal(s.value)}</span><span class="r">${s.age}</span></div>`).join('');
}

function setF(f){F=Math.max(1,Math.min(NSTEPS,f));render(true);syncStrip();}
document.getElementById('prev').onclick=()=>setF(F-1);
document.getElementById('next').onclick=()=>setF(F+1);
document.getElementById('seg').addEventListener('click',e=>{const b=e.target.closest('button'); if(!b)return;
  document.querySelectorAll('#seg button').forEach(x=>x.classList.remove('on')); b.classList.add('on');
  V=b.dataset.v; buildStrip(); render(true); renderStatic();});
document.getElementById('play').onclick=function(){
  if(timer){clearInterval(timer);timer=null;this.textContent='▶';return;}
  if(F>=NSTEPS)F=1; this.textContent='⏸';
  timer=setInterval(()=>{if(F>=NSTEPS){clearInterval(timer);timer=null;document.getElementById('play').textContent='▶';return;}setF(F+1);},850);};
buildStrip(); render(false); renderStatic(); syncStrip();
</script>
</body>
</html>
"""


def main():
    data = json.load(open(os.path.join(DP, "pred_results.json"), encoding="utf-8"))
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    path = os.path.join(HERE, "prediccion_zonaA_2026.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML escrito en", path, "·", len(html), "bytes")


if __name__ == "__main__":
    main()
