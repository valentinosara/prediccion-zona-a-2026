"""
scrape_playwright.py - Scraper reproducible de los calendarios de la Primera
Nacional (worldfootball.net), partido a partido, con fecha y jornada.

==================  COMO REPRODUCIR TODO  ==================
1) pip install playwright beautifulsoup4 requests
   playwright install chromium
2) python scrape_playwright.py      # baja y cachea data/wf_<se>_<slug>.json
3) python build.py                  # calcula rachas -> data/results.json
4) python gen_html.py               # arma rachas_primera_nacional.html
============================================================

POR QUE PLAYWRIGHT Y NO requests:
worldfootball.net esta detras de Cloudflare con un desafio JavaScript
("Just a moment..."). Un GET plano devuelve 403; hace falta un navegador real
que ejecute JS para pasar el challenge. Por eso usamos Chromium via Playwright.
NOTA: en modo headless Cloudflare a veces NO deja pasar; si recibis paginas de
challenge, corre con headless=False (ver abajo) o reintenta. Cada pagina se
cachea a disco: el challenge se "gana" una sola vez por temporada.

La extraccion (funcion JS EXTRACT_JS) recorre el contenedor .module-gameplan:
- .round-head  -> jornada ("Round N")
- .match-date  -> fecha mostrada (dd.mm.yyyy)
- .match       -> partido: data-datetime (timestamp real, para ordenar
                  cronologicamente), data-match_id, equipos (con teID estable),
                  y el resultado.
"""
import json
import os
import time

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA, exist_ok=True)

BASE = "https://www.worldfootball.net/competition/co1787/argentina-primera-nacional"

# (se-id, slug-en-la-url, nombre-de-archivo-de-salida) -- SOLO fase regular.
# Las temporadas con 2 zonas tienen 2 entradas (worldfootball las separa por
# "se", salvo 2014/2025 que vienen en un unico "se" con las zonas intercaladas).
SEASONS = [
    ("se6101",   "2010-2011",          "wf_se6101_2010-2011.json"),
    ("se7241",   "2011-2012",          "wf_se7241_2011-2012.json"),
    ("se9362",   "2012-2013",          "wf_se9362_2012-2013.json"),
    ("se12992",  "2013-2014",          "wf_se12992_2013-2014.json"),
    ("se15670",  "2014",               "wf_se15670_2014.json"),
    ("se17039",  "2015",               "wf_se17039_2015.json"),
    ("se20122",  "2016",               "wf_se20122_2016.json"),
    ("se21929",  "2016-2017",          "wf_se21929_2016-2017.json"),
    ("se24611",  "2017-2018",          "wf_se24611_2017-2018.json"),
    ("se29215",  "2018-2019",          "wf_se29215_2018-2019.json"),
    ("se32639",  "2019-2020-zona-a",   "wf_se32639_2019-2020-zona-a.json"),
    ("se32638",  "2019-2020-zona-b",   "wf_se32638_2019-2020-zona-b.json"),
    ("se38348",  "2021-grupo-a",       "wf_se38348_2021-grupo-a.json"),
    ("se38347",  "2021-grupo-b",       "wf_se38347_2021-grupo-b.json"),
    ("se42905",  "2022",               "wf_se42905_2022.json"),
    ("se49762",  "2023-grupo-a",       "wf_se49762_2023-grupo-a.json"),
    ("se49761",  "2023-grupo-b",       "wf_se49761_2023-grupo-b.json"),
    ("se62387",  "2024",               "wf_se62387_2024.json"),
    ("se85625",  "2025",               "wf_se85625_2025.json"),
    ("se112408", "2026",               "wf_se112408_2026.json"),
]

# Funcion ejecutada DENTRO de la pagina (devuelve JSON con todos los partidos).
EXTRACT_JS = r"""
() => {
  const root = document.querySelector('.module-gameplan');
  if(!root) return JSON.stringify({error:'no gameplan'});
  let curRound=null, curDate=null; const matches=[];
  root.querySelectorAll('.round-head, .match-date, .match').forEach(n=>{
    if(n.classList.contains('round-head')){ curRound=n.textContent.trim(); }
    else if(n.classList.contains('match-date')){ curDate=n.textContent.trim(); }
    else if(n.classList.contains('match')){
      const ha=n.querySelector('.team-name-home a'),
            aa=n.querySelector('.team-name-away a'),
            res=n.querySelector('.match-result a');
      const idof=a=>{ if(!a) return null;
        const m=a.getAttribute('href').match(/\/teams\/(te\d+)\//); return m?m[1]:null; };
      matches.push({round:curRound, round_id:n.getAttribute('data-round_id'),
        dt:n.getAttribute('data-datetime'), date:curDate,
        match_id:n.getAttribute('data-match_id'),
        home:ha?ha.textContent.trim():null, home_id:idof(ha),
        away:aa?aa.textContent.trim():null, away_id:idof(aa),
        score:res?res.textContent.trim():null, cls:n.className});
    }
  });
  return JSON.stringify({count:matches.length, matches});
}
"""


def main(headless=True):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            locale="es-AR",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()
        for se, slug, fn in SEASONS:
            out = os.path.join(DATA, fn)
            if os.path.exists(out):
                print("cache hit:", fn)
                continue
            url = f"{BASE}/{se}/{slug}/all-matches/"
            print("fetch:", url)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # margen para que Cloudflare resuelva y se pinte el calendario
            page.wait_for_timeout(4000)
            payload = page.evaluate(EXTRACT_JS)
            data = json.loads(payload)
            if data.get("error"):
                print("  !! sin calendario (posible challenge Cloudflare):", data)
                continue
            with open(out, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            print(f"  ok: {data['count']} partidos -> {fn}")
            time.sleep(2.5)  # cortesia
        browser.close()


if __name__ == "__main__":
    import sys
    main(headless="--headed" not in sys.argv)
