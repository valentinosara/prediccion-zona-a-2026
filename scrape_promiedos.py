"""
scrape_promiedos.py - Baja resultados + fixture de la Zona A 2026 desde la API
de Promiedos (requests, sin navegador: la API no tiene Cloudflare-challenge).

Genera data_promiedos/prom_games.json (todas las fechas, ambas zonas).
Se corre cada vez que se juega una fecha nueva para actualizar resultados.

NOTA: el header 'x-ver' es la version de la app de Promiedos; si algun dia la
API deja de responder (devuelve {}), revisar ese valor en las requests de la web.
La asignacion de zonas (data_promiedos/tablas.json) NO cambia durante la
temporada, asi que no hace falta re-bajarla.
"""
import json
import os
import time
import requests

DP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_promiedos")
LEAGUE = "ebj"           # id de la Primera Nacional en Promiedos
STAGE = "419_46_1"       # liga_torneo_fase (zona unica de fechas; 2026)
NFECHAS = 36
HEADERS = {
    "x-ver": "1.11.7.5",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Referer": "https://www.promiedos.com.ar/",
}


def fetch_fecha(n, sess):
    url = f"https://api.promiedos.com.ar/league/games/{LEAGUE}/{STAGE}_{n}"
    r = sess.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.json().get("games", [])


def main():
    sess = requests.Session()
    games = []
    for n in range(1, NFECHAS + 1):
        try:
            gs = fetch_fecha(n, sess)
        except Exception as e:
            print(f"  F{n}: ERROR {e}")
            continue
        for g in gs:
            t = g["teams"]
            games.append({
                "fecha": n, "id": g.get("id"),
                "home": t[0]["name"], "home_id": t[0]["id"],
                "away": t[1]["name"], "away_id": t[1]["id"],
                "scores": g.get("scores") or None,
                "status": g["status"]["enum"] if g.get("status") else None,
                "status_name": g["status"]["name"] if g.get("status") else None,
                "winner": g.get("winner"),
                "start": g.get("start_time"),
            })
        time.sleep(0.15)
    out = {"count": len(games), "games": games}
    with open(os.path.join(DP, "prom_games.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    played = sum(1 for g in games if g["status"] == 3 and g["scores"])
    print(f"OK · {len(games)} partidos ({played} jugados) -> data_promiedos/prom_games.json")


if __name__ == "__main__":
    main()
