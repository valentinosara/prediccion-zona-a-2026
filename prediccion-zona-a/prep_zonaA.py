"""
prep_zonaA.py - Prepara el dataset de la Zona A 2026 desde los datos de Promiedos.

Entrada:
  data_promiedos/prom_games.json  (todas las fechas del torneo, ambas zonas)
  data_promiedos/tablas.json      (tabla oficial Zona A / Zona B -> asignacion de zona por ID)

Salida:
  data_promiedos/zonaA_data.json
    - teams:   {id: {name, zona}}   (todos los equipos, para calibrar el modelo)
    - played:  partidos jugados de TODO el torneo (para calibrar atk/def)
    - fixture: partidos de la Zona A (jugados + futuros + F36 deducida), cronologicos
"""
import json
import os
from collections import defaultdict
from itertools import combinations

DP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_promiedos")

# Arreglos de grafia para mostrar (Promiedos abrevia algunos)
PRETTY = {
    "Ciudad De Bolivar": "Ciudad de Bolívar",
    "Mitre SdE": "Mitre (SdE)",
    "Colón": "Colón (Santa Fe)",
    "Estudiantes": "Estudiantes (Caseros)",
    "Los Andes": "Los Andes",
    "Racing de Córdoba": "Racing (Córdoba)",
    "San Miguel": "San Miguel",
    "Gimnasia de Jujuy": "Gimnasia y Esgrima (Jujuy)",
}


def load(p):
    raw = open(p, encoding="utf-8").read()
    d = json.loads(raw)
    return json.loads(d) if isinstance(d, str) else d


def pretty(n):
    return PRETTY.get(n, n)


def main():
    games = load(os.path.join(DP, "prom_games.json"))["games"]
    tablas = json.load(open(os.path.join(DP, "tablas.json"), encoding="utf-8"))

    zoneA = {r["pid"]: pretty(r["name"]) for r in tablas["Zona A"]}
    zoneB = {r["pid"]: pretty(r["name"]) for r in tablas["Zona B"]}
    teams = {}
    for tid, nm in zoneA.items():
        teams[tid] = {"name": nm, "zona": "A"}
    for tid, nm in zoneB.items():
        teams[tid] = {"name": nm, "zona": "B"}

    def is_played(g):
        return g.get("status") == 3 and g.get("scores")

    # 1) partidos jugados de TODO el torneo (para calibrar el modelo)
    played_all = []
    for g in games:
        if is_played(g):
            played_all.append({
                "home_id": g["home_id"], "away_id": g["away_id"],
                "hs": g["scores"][0], "as": g["scores"][1],
            })

    # 2) fixture de la Zona A (>=1 equipo de Zona A)
    fixture = []
    intra_seen = defaultdict(int)  # (home_id,away_id) -> veces (para deducir F36)
    for g in games:
        a_home, a_away = g["home_id"] in zoneA, g["away_id"] in zoneA
        if not (a_home or a_away):
            continue  # B vs B: no es de Zona A
        rec = {
            "fecha": g["fecha"], "home_id": g["home_id"], "away_id": g["away_id"],
            "home": teams[g["home_id"]]["name"], "away": teams[g["away_id"]]["name"],
            "interzonal": not (a_home and a_away),
            "played": bool(is_played(g)),
            "hs": g["scores"][0] if is_played(g) else None,
            "as": g["scores"][1] if is_played(g) else None,
            "start": g.get("start"), "deduced": False,
        }
        fixture.append(rec)
        if a_home and a_away:
            intra_seen[(g["home_id"], g["away_id"])] += 1

    # 3) Deducir la F36 (intrazona): cruces ida/vuelta que faltan.
    ids = list(zoneA)
    missing = []
    for i, j in combinations(ids, 2):
        # cada par debe jugar 1 vez en cada cancha
        if intra_seen[(i, j)] == 0 and intra_seen[(j, i)] >= 1:
            missing.append((i, j))      # falta i de local
        elif intra_seen[(j, i)] == 0 and intra_seen[(i, j)] >= 1:
            missing.append((j, i))      # falta j de local
        elif intra_seen[(i, j)] == 0 and intra_seen[(j, i)] == 0:
            missing.append((i, j))      # no se vieron nunca (raro): asignar ida
    for (h, a) in missing:
        fixture.append({
            "fecha": 36, "home_id": h, "away_id": a,
            "home": teams[h]["name"], "away": teams[a]["name"],
            "interzonal": False, "played": False, "hs": None, "as": None,
            "start": None, "deduced": True,
        })

    # 4) Validacion: cada equipo de Zona A debe quedar con 36 partidos
    pj = defaultdict(int)
    for f in fixture:
        if f["home_id"] in zoneA:
            pj[f["home_id"]] += 1
        if f["away_id"] in zoneA:
            pj[f["away_id"]] += 1
    bad = {teams[i]["name"]: pj[i] for i in zoneA if pj[i] != 36}

    out = {
        "teams": teams,
        "zonaA_ids": list(zoneA),
        "played_all": played_all,
        "fixture": fixture,
    }
    json.dump(out, open(os.path.join(DP, "zonaA_data.json"), "w", encoding="utf-8"),
              ensure_ascii=False)

    print(f"equipos totales: {len(teams)} (A={len(zoneA)}, B={len(zoneB)})")
    print(f"jugados (todo el torneo, para calibrar): {len(played_all)}")
    print(f"fixture Zona A: {len(fixture)} partidos "
          f"(jugados={sum(f['played'] for f in fixture)}, "
          f"futuros={sum(not f['played'] for f in fixture)}, "
          f"F36 deducidos={sum(f['deduced'] for f in fixture)})")
    print(f"interzonales en fixture A: {sum(f['interzonal'] for f in fixture)}")
    print("PJ por equipo == 36 para todos:", not bad, bad if bad else "")
    if missing:
        print("F36 deducida (9 partidos):")
        for h, a in missing:
            print(f"   {teams[h]['name']} vs {teams[a]['name']}")


if __name__ == "__main__":
    main()
