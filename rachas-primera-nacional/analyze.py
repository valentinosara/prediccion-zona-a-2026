"""
analyze.py - Calculo de rachas de victorias consecutivas (Primera Nacional).

Entrada: archivos JSON por temporada (uno por "se" de worldfootball), cada uno
con la lista de partidos {round, round_id, dt, date, match_id, home, home_id,
away, away_id, score, cls}.

Salida: por temporada, el top de equipos segun su MAXIMA racha de victorias
consecutivas, calculada recorriendo los partidos de cada equipo en ORDEN
CRONOLOGICO (por data-datetime, el timestamp real del partido; round como
desempate). Una racha solo suma con victoria; empate o derrota la cortan
(la resetea a 0).
"""
import json
import re
import unicodedata
from datetime import datetime, timezone


# -------------------- carga y parseo basico --------------------
def load_season_file(path):
    """Lee el JSON guardado (puede venir doble-encodeado como string)."""
    raw = open(path, encoding="utf-8").read()
    d = json.loads(raw)
    if isinstance(d, str):
        d = json.loads(d)
    return d


def parse_score(s):
    """'2:1' -> (2,1). Devuelve None si no es un resultado numerico jugado."""
    m = re.match(r"^\s*(\d+):(\d+)\s*$", s or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def round_num(r):
    m = re.search(r"(\d+)", r or "")
    return int(m.group(1)) if m else 9999


def parse_dt(dt):
    """ISO '2022-02-11T23:00:00Z' -> datetime aware (UTC). None si falta."""
    if not dt:
        return None
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except Exception:
        return None


# -------------------- construccion de la secuencia por equipo --------------------
def build_team_games(matches, team_key="name"):
    """Devuelve dict: equipo -> lista de partidos en orden cronologico.

    Cada partido del equipo: {sk, dt, round, opp, res(W/D/L), gf, ga, home, score, match_id}
    El orden se define por (datetime real, numero de fecha) -> 'sk' (sort key).
    `team_key`='name' usa el nombre mostrado; 'id' usaria el teID estable.
    """
    games = {}
    for m in matches:
        sc = parse_score(m.get("score"))
        if not sc:
            continue  # partido no jugado / sin resultado numerico
        hg, ag = sc
        dt = m.get("dt")
        sk = (dt or "9999", round_num(m.get("round")))
        sides = [
            ("H", m.get("home"), m.get("home_id"), m.get("away"), hg, ag),
            ("A", m.get("away"), m.get("away_id"), m.get("home"), ag, hg),
        ]
        for side, team, tid, opp, gf, ga in sides:
            if not team:
                continue
            key = tid if (team_key == "id" and tid) else team
            res = "W" if gf > ga else ("D" if gf == ga else "L")
            games.setdefault(key, {"name": team, "id": tid, "g": []})
            games[key]["g"].append({
                "sk": sk, "dt": dt, "round": m.get("round"),
                "opp": opp, "res": res, "gf": gf, "ga": ga,
                "home": side == "H", "score": m.get("score"),
                "match_id": m.get("match_id"),
            })
    for k in games:
        games[k]["g"].sort(key=lambda x: x["sk"])
    return games


# -------------------- algoritmo longest-run --------------------
def longest_win_streak(team_games):
    """Maxima corrida de 'W' consecutivas. Reset en D o L.

    Devuelve (best_len, best_span) donde best_span = lista de partidos de la
    mejor racha (para poder mostrar rivales y fechas). Ante empate de longitud,
    conserva la PRIMERA ocurrencia cronologica.
    """
    best = 0
    best_run = []
    cur = []
    for g in team_games:
        if g["res"] == "W":
            cur.append(g)
            if len(cur) > best:
                best = len(cur)
                best_run = list(cur)
        else:
            cur = []
    return best, best_run


def season_ranking(matches, team_key="name"):
    """Top de equipos por racha maxima. Devuelve lista ordenada de dicts."""
    games = build_team_games(matches, team_key=team_key)
    rows = []
    for key, info in games.items():
        best, run = longest_win_streak(info["g"])
        rows.append({
            "team": info["name"],
            "team_id": info["id"],
            "streak": best,
            "played": len(info["g"]),
            "run": run,
        })
    rows.sort(key=lambda r: (-r["streak"], r["team"]))
    return rows


def fmt_run(run):
    """Resumen legible de una racha: fechas de inicio/fin y rivales batidos."""
    if not run:
        return ""
    def d(g):
        dt = parse_dt(g["dt"])
        return dt.strftime("%d/%m/%Y") if dt else (g["round"] or "?")
    inicio, fin = d(run[0]), d(run[-1])
    rivales = "; ".join(
        f"{g['round'].replace('Round','F')}: {'v' if g['home'] else '@'}{g['opp']} {g['gf']}-{g['ga']}"
        for g in run
    )
    return inicio, fin, rivales


if __name__ == "__main__":
    import sys
    d = load_season_file(sys.argv[1])
    ms = d["matches"]
    print(f"Temporada {d.get('season')} ({d.get('se')}) - {len(ms)} partidos")
    # chequeo de contaminacion de playoffs
    rounds = sorted(set(m.get("round") for m in ms), key=round_num)
    bad = [r for r in rounds if r and not re.match(r"^Round \d+$", r)]
    if bad:
        print("  AVISO etiquetas de ronda no estandar:", bad)
    ranking = season_ranking(ms)
    print("  Top 5 rachas:")
    for r in ranking[:5]:
        span = fmt_run(r["run"])
        print(f"   {r['streak']}  {r['team']}  ({span[0]} -> {span[1]})" if span else f"   {r['streak']}  {r['team']}")
