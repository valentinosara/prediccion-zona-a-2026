"""
_build_seed.py - Genera el SEED de respaldo del Mundial 2026 (datos versionados).

Por que existe un seed: el sistema baja todo por fetch automatico, pero si la red del
entorno bloquea las fuentes en vivo (o estan caidas), el pipeline tiene que poder correr
END-TO-END igual. Este script produce un seed REALISTA e internamente consistente:

  teams.json     48 selecciones (Elo aprox World Football Elo, ranking FIFA, ISO, sede)
  fixtures.json  72 partidos de grupos (12 grupos A-L x 6); F1 de los grupos A-F ya
                 jugada (marcadores simulados con el propio modelo), el resto pendiente
  odds.json      cuotas 1X2 + O/U 2.5 + handicap asiatico por partido, derivadas de los
                 lambda "verdaderos" del modelo + margen de casa (~5-6%) + ruido de
                 mercado (para que el mercado NO sea identico al Elo y el blend tenga sentido)

Se reusa ratings_wc/model_wc para que el seed sea coherente con el motor. Reproducible
(RNG con semilla fija). NO es dato real del torneo: es un respaldo para probar el sistema
cuando no hay red. Reescribir corriendo:  python data_mundial/seed/_build_seed.py
"""
import json
import os
import sys
from datetime import datetime, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import model_wc          # noqa: E402
import ratings_wc        # noqa: E402

RNG = np.random.default_rng(2026)

# --- 48 selecciones: (nombre, ISO-2, Elo aprox) ; hosts marcados aparte ----------------
TEAMS = [
    ("Espana", "ES", 2120), ("Francia", "FR", 2095), ("Argentina", "AR", 2090),
    ("Inglaterra", "GB-ENG", 2055), ("Brasil", "BR", 2035), ("Portugal", "PT", 2015),
    ("Paises Bajos", "NL", 1990), ("Alemania", "DE", 1965), ("Belgica", "BE", 1945),
    ("Italia", "IT", 1930), ("Croacia", "HR", 1900), ("Uruguay", "UY", 1895),
    ("Colombia", "CO", 1885), ("Marruecos", "MA", 1870), ("Suiza", "CH", 1855),
    ("Japon", "JP", 1850), ("Senegal", "SN", 1840), ("Noruega", "NO", 1835),
    ("Dinamarca", "DK", 1830), ("Ecuador", "EC", 1825), ("Austria", "AT", 1820),
    ("Iran", "IR", 1815), ("Mexico", "MX", 1810), ("Serbia", "RS", 1800),
    ("Estados Unidos", "US", 1795), ("Corea del Sur", "KR", 1795), ("Ucrania", "UA", 1790),
    ("Nigeria", "NG", 1785), ("Egipto", "EG", 1780), ("Argelia", "DZ", 1775),
    ("Suecia", "SE", 1770), ("Costa de Marfil", "CI", 1765), ("Canada", "CA", 1760),
    ("Camerun", "CM", 1755), ("Tunez", "TN", 1745), ("Ghana", "GH", 1740),
    ("Peru", "PE", 1735), ("Venezuela", "VE", 1720), ("Costa Rica", "CR", 1705),
    ("Arabia Saudita", "SA", 1700), ("Uzbekistan", "UZ", 1695), ("Panama", "PA", 1695),
    ("Qatar", "QA", 1690), ("Jamaica", "JM", 1680), ("Jordania", "JO", 1670),
    ("Honduras", "HN", 1665), ("Cabo Verde", "CV", 1660), ("Nueva Zelanda", "NZ", 1505),
]

HOSTS = {"MX", "CA", "US"}

# --- 12 grupos A-L (orden = pot 1..4: cabeza de serie / bombo 2 / 3 / 4) ----------------
GROUPS = {
    "A": ["MX", "HR", "EC", "SA"],
    "B": ["CA", "IT", "KR", "QA"],
    "C": ["ES", "UY", "NG", "CR"],
    "D": ["US", "CO", "EG", "PA"],
    "E": ["FR", "MA", "CI", "JM"],
    "F": ["AR", "CH", "DZ", "NZ"],
    "G": ["BR", "JP", "CM", "UZ"],
    "H": ["PT", "SN", "TN", "JO"],
    "I": ["GB-ENG", "DK", "GH", "VE"],
    "J": ["NL", "AT", "NO", "PE"],
    "K": ["BE", "RS", "SE", "CV"],
    "L": ["DE", "IR", "UA", "HN"],
}

# Orden de partidos de un grupo de 4 (cubre los 6 cruces; cada equipo juega a cada uno una vez)
ROUND_PAIRS = {1: [(0, 1), (2, 3)], 2: [(0, 2), (1, 3)], 3: [(0, 3), (1, 2)]}

# Una jornada (matchday) por bloque de 2 grupos por dia. La F1 de A-F (Jun 11-13) ya se jugo.
MD1_DAYS = {"A": "2026-06-11", "B": "2026-06-11", "C": "2026-06-12", "D": "2026-06-12",
            "E": "2026-06-13", "F": "2026-06-13", "G": "2026-06-14", "H": "2026-06-14",
            "I": "2026-06-15", "J": "2026-06-15", "K": "2026-06-16", "L": "2026-06-16"}
MD2_DAYS = {g: (datetime.fromisoformat(d) + timedelta(days=6)).date().isoformat()
            for g, d in MD1_DAYS.items()}
MD3_DAYS = {g: (datetime.fromisoformat(d) + timedelta(days=12)).date().isoformat()
            for g, d in MD1_DAYS.items()}
DAYS = {1: MD1_DAYS, 2: MD2_DAYS, 3: MD3_DAYS}
KICK_TIMES = ["16:00", "19:00", "22:00", "13:00"]   # se reparten por grupo
VENUES = {"MX": "Estadio Azteca, Ciudad de Mexico", "CA": "BMO Field, Toronto",
          "US": "MetLife Stadium, Nueva Jersey"}
NEUTRAL_VENUES = ["SoFi Stadium, Los Angeles", "AT&T Stadium, Dallas",
                  "Mercedes-Benz Stadium, Atlanta", "Lumen Field, Seattle",
                  "Hard Rock Stadium, Miami", "Arrowhead Stadium, Kansas City",
                  "Levi's Stadium, San Francisco", "Gillette Stadium, Boston",
                  "Lincoln Financial Field, Filadelfia", "NRG Stadium, Houston"]


def flag(iso2):
    """ISO-3166 alpha-2 -> emoji bandera (con casos especiales de Reino Unido)."""
    special = {"GB-ENG": "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"}
    if iso2 in special:
        return special[iso2]
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2.upper())


def build_teams():
    elo = {iso: e for _, iso, e in TEAMS}
    rank = {iso: i + 1 for i, (_, iso, _) in enumerate(sorted(TEAMS, key=lambda t: -t[2]))}
    grp_of = {iso: g for g, members in GROUPS.items() for iso in members}
    out = {}
    for name, iso, e in TEAMS:
        out[iso] = {"name": name, "iso2": iso, "flag": flag(iso), "elo": e,
                    "fifa_rank": rank[iso], "group": grp_of.get(iso),
                    "host": iso in HOSTS}
    return out


def _sample_score(lh, la):
    """Muestrea un marcador de la matriz Dixon-Coles (con su semilla global)."""
    P = model_wc.dc_matrix(lh, la).ravel()
    idx = RNG.choice(P.size, p=P / P.sum())
    h, a = divmod(int(idx), model_wc.MAXG + 1)
    return h, a


def build_fixtures(teams):
    elo = {k: v["elo"] for k, v in teams.items()}
    fixtures = []
    mid = 0
    nv = 0
    for g, members in GROUPS.items():
        for md in (1, 2, 3):
            day = DAYS[md][g]
            for slot, (i, j) in enumerate(ROUND_PAIRS[md]):
                home, away = members[i], members[j]
                mid += 1
                kt = KICK_TIMES[(ord(g) + slot) % len(KICK_TIMES)]
                kickoff = f"{day}T{kt}:00"
                host_adv = ratings_wc.HOST_BONUS if home in HOSTS else 0.0
                lh, la = ratings_wc.lambdas_from_elo(elo[home], elo[away], home_adv=host_adv)
                venue = VENUES.get(home) if home in HOSTS else NEUTRAL_VENUES[nv % len(NEUTRAL_VENUES)]
                if home not in HOSTS:
                    nv += 1
                f = {"id": f"WC2026-{mid:03d}", "group": g, "matchday": md,
                     "home": home, "away": away, "kickoff": kickoff, "venue": venue,
                     "status": "scheduled", "home_score": None, "away_score": None}
                # La F1 de los grupos A-F (Jun 11-13) ya se jugo: marcador simulado.
                if md == 1 and day <= "2026-06-13":
                    hs, as_ = _sample_score(lh, la)
                    f.update(status="played", home_score=hs, away_score=as_)
                fixtures.append(f)
    return fixtures


def build_odds(teams, fixtures):
    """Cuotas por partido a partir de los lambda 'verdaderos' + ruido de mercado + margen."""
    elo = {k: v["elo"] for k, v in teams.items()}
    odds = {}
    books = ["Pinnacle", "Bet365", "William Hill"]
    for f in fixtures:
        home, away = f["home"], f["away"]
        host_adv = ratings_wc.HOST_BONUS if home in HOSTS else 0.0
        lh0, la0 = ratings_wc.lambdas_from_elo(elo[home], elo[away], home_adv=host_adv)
        # ruido de mercado: el mercado no es el Elo puro (lesiones, momentum, etc.)
        s = (lh0 - la0) + RNG.normal(0, 0.18)
        mu = (lh0 + la0) * float(np.exp(RNG.normal(0, 0.06)))
        lh, la = max((mu + s) / 2, 0.05), max((mu - s) / 2, 0.05)
        P = model_wc.dc_matrix(lh, la)
        p1, pX, p2 = model_wc.outcome_probs(P)
        p_over = model_wc.total_goals_prob(P, 2.5)

        def quote(p, margin):
            return round(1.0 / (p * (1.0 + margin)), 2)

        m = 0.05 + 0.015 * RNG.random()        # overround ~5-6.5%
        h2h = [quote(p1, m), quote(pX, m), quote(p2, m)]
        totals = {"line": 2.5, "over": quote(p_over, m), "under": quote(1 - p_over, m)}
        line = round((la - lh) * 4) / 4.0       # linea AH del LOCAL (negativa = favorito)
        spreads = {"line": line, "home": round(1.93 + RNG.normal(0, 0.04), 2),
                   "away": round(1.93 + RNG.normal(0, 0.04), 2)}
        odds[f["id"]] = {"bookmaker": str(RNG.choice(books)), "h2h": h2h,
                         "totals": totals, "spreads": spreads}
    return odds


def main():
    teams = build_teams()
    fixtures = build_fixtures(teams)
    odds = build_odds(teams, fixtures)
    meta = {"_note": "SEED de respaldo (no es dato real del torneo). Generado por "
                     "_build_seed.py para correr el pipeline sin red.",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "n_teams": len(teams), "n_fixtures": len(fixtures)}
    for name, obj in [("teams.json", {"meta": meta, "teams": teams}),
                      ("fixtures.json", {"meta": meta, "fixtures": fixtures}),
                      ("odds.json", {"meta": meta, "odds": odds})]:
        json.dump(obj, open(os.path.join(HERE, name), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    played = sum(1 for f in fixtures if f["status"] == "played")
    print(f"Seed generado: {len(teams)} equipos, {len(fixtures)} partidos "
          f"({played} ya jugados), cuotas para {len(odds)} partidos.")


if __name__ == "__main__":
    main()
