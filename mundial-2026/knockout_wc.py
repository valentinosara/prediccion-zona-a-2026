"""knockout_wc.py - Predicción de rondas ELIMINATORIAS del Mundial 2026 para el prode.

A diferencia de la fase de grupos (predict_wc.py), en eliminación directa:
  - los cruces son INTER-grupo (el fetch de grupos los descarta): se traen por la RONDA de
    ESPN, identificada por `season.slug` (round-of-32 / round-of-16 / quarterfinals /
    semifinals / final). Si los equipos aún no están definidos, ESPN trae placeholders
    ("Round of 32 X Winner") que no resuelven a una selección -> se cuentan como pendientes;
  - el marcador es a 120' (90' + alargue): el alargue se modela como un sub-partido de 30'
    (lambda/3) condicionado a empate a los 90' -> menos empates, y se obtiene P(penales);
  - se calcula P(avanza) por equipo y el optimizador del prode incluye el BONUS +3 por
    acertar quién clasifica. El clasificado se INFIERE del marcador (si se predice empate,
    se toma al favorito por P(avanza)). Los penales se modelan como 50/50 (sin sesgo de tanda).

Reusa el MISMO motor que grupos: ratings_wc (Elo + forma xG), market_wc (de-vig 1X2/O-U/AH),
model_wc (Dixon-Coles) y prode_wc (puntaje). La forma in-tournament toma el xG real de
data_mundial/fifaphy_xg.json (bajado por scrape_fifaphy.py); corré ese script ANTES de cada
ronda para incorporar el xG de la ronda recién jugada.
"""
import json
import os
from datetime import datetime, timedelta

import numpy as np

import fetch_wc
import market_wc
import model_wc
import predict_wc
import prode_wc
import ratings_wc

HOST = fetch_wc.HOST_CODES
RHO = model_wc.RHO_DEFAULT
PEN_A = 0.5                       # penales = moneda (honesto; sin sesgo de tanda)

# slug de ESPN -> (nombre es-AR, orden, nombre de archivo HTML)
ROUNDS = {
    "round-of-32":  ("16avos", 1, "16avos.html"),
    "round-of-16":  ("octavos", 2, "octavos.html"),
    "quarterfinals": ("cuartos", 3, "cuartos.html"),
    "semifinals":   ("semifinales", 4, "semifinales.html"),
    "third-place":  ("tercer puesto", 5, "tercer_puesto.html"),
    "final":        ("final", 6, "final.html"),
}
# nombres amigables -> slug
ALIAS = {"16avos": "round-of-32", "dieciseisavos": "round-of-32", "r32": "round-of-32",
         "octavos": "round-of-16", "r16": "round-of-16",
         "cuartos": "quarterfinals", "cuartos-de-final": "quarterfinals", "qf": "quarterfinals",
         "semis": "semifinals", "semifinales": "semifinals", "sf": "semifinals",
         "tercer-puesto": "third-place", "final": "final"}


def resolve_slug(name):
    """Acepta 'octavos', 'round-of-16', 'r16'... -> slug canónico de ESPN."""
    key = (name or "").strip().lower()
    return ALIAS.get(key, key)


# ------------------------------------------------------- fixtures de la ronda --------

def fetch_round(slug, start="2026-06-28", end="2026-07-20"):
    """Barre el scoreboard por día y junta los partidos cuya `season.slug` == slug.
    Devuelve (definidos, n_pendientes_sin_equipos). 'definidos' = ambos equipos resueltos."""
    seen, defined, tbd = set(), [], 0
    d = datetime.strptime(start, "%Y-%m-%d")
    d1 = datetime.strptime(end, "%Y-%m-%d")
    while d <= d1:
        # mismo fetch resiliente que la fase de grupos (3 reintentos + backoff): un error
        # transitorio no debe descartar un día entero de partidos de la ronda.
        data, _err = fetch_wc.http_get_json(fetch_wc.ESPN_SCOREBOARD,
                                            params={"dates": d.strftime("%Y%m%d")})
        data = data or {}
        for ev in data.get("events", []):
            if (ev.get("season") or {}).get("slug") != slug:
                continue
            eid = ev.get("id")
            if eid in seen:
                continue
            seen.add(eid)
            try:
                comp = ev["competitions"][0]
                cs = comp["competitors"]
                home = next(c for c in cs if c["homeAway"] == "home")
                away = next(c for c in cs if c["homeAway"] == "away")
                hiso = fetch_wc._espn_team_iso(home.get("team", {}))
                aiso = fetch_wc._espn_team_iso(away.get("team", {}))
            except (KeyError, IndexError, StopIteration):
                continue
            if not hiso or not aiso:        # placeholder ("X Winner"): equipos sin definir
                tbd += 1
                continue
            st = comp.get("status", {}).get("type", {})
            venue = comp.get("venue", {}) or {}
            defined.append({
                "espn_id": eid, "home": hiso, "away": aiso,
                "kickoff": fetch_wc._to_art(ev.get("date")),
                "venue": venue.get("fullName", ""),
                "status": "played" if st.get("completed") else "scheduled",
                "hs": fetch_wc._safe_int(home.get("score")),
                "as": fetch_wc._safe_int(away.get("score")),
            })
        d += timedelta(days=1)
    defined.sort(key=lambda m: m["kickoff"])
    return defined, tbd


# ------------------------------------------------- estado del motor (con xG real) ----

def engine_state(asof=None):
    """Reconstruye el estado del motor desde TODO lo jugado con xG real pegado
    (data_mundial/fifaphy_xg.json): Elo actualizado, forma in-tournament y cfg
    (mu0/k_mis/w_mkt). Mismo cálculo que predict_wc.run, pero la forma usa el xG real."""
    seed_teams = json.load(open(os.path.join(fetch_wc.SEED, "teams.json"),
                                encoding="utf-8"))["teams"]
    teams = {iso: dict(t) for iso, t in seed_teams.items()}
    elo0 = {iso: float(t["elo"]) for iso, t in teams.items()}
    elo_live, _ = fetch_wc._fetch_elo()
    for iso, e in (elo_live or {}).items():
        if iso in elo0:
            elo0[iso] = float(e)
            teams[iso]["elo"] = int(e)

    history = []
    xg_path = os.path.join(fetch_wc.DATA, "fifaphy_xg.json")
    if os.path.exists(xg_path):
        for m in json.load(open(xg_path, encoding="utf-8")).get("matches", []):
            if m.get("home_score") is None or m.get("away_score") is None:
                continue
            history.append({"id": m.get("ifes"), "home": m["home"], "away": m["away"],
                            "hs": m["home_score"], "as": m["away_score"],
                            "hxg": m.get("home_xg"), "axg": m.get("away_xg"),
                            "date": m["date"], "kickoff": m["date"] + "T12:00:00"})
    history.sort(key=lambda m: m["date"])

    asof = asof or datetime.now()
    elo_now = ratings_wc.update_ratings(dict(elo0), history, HOST)
    mu0, k_mis = ratings_wc.calibrate_totals(history, elo0, HOST)
    form = ratings_wc.fit_form(history, elo0, asof, mu0=mu0, host_codes=HOST, k_mis=k_mis)
    tg = (2 * len(history)) / max(len(teams), 1)
    cfg = {"mu0": mu0, "rho": RHO, "k_mis": k_mis, "w_mkt": predict_wc.w_market(tg),
           "host_codes": HOST}
    return teams, elo0, elo_now, form, cfg, len(history)


# --------------------------------------------- probabilidades 90' -> 120' + prode ----

def matrix_90(home, away, elo_now, form, cfg, odds_block):
    """Matriz DC de marcadores a 90' anclada al mercado (núcleo de build_prediction)."""
    host_adv = ratings_wc.HOST_BONUS if home in HOST else 0.0
    lh, la = ratings_wc.lambdas_from_elo(elo_now[home], elo_now[away], cfg["mu0"],
                                         host_adv, RHO, cfg["k_mis"])
    g_min = min(form.get(home, (0, 0, 0))[2], form.get(away, (0, 0, 0))[2])
    w_form = min(g_min / 6.0, 1.0) * 0.5
    lh, la = ratings_wc.apply_form(lh, la, home, away, form, w_form)
    mk = market_wc.parse_match_odds(odds_block) if odds_block else {"ok": False}
    if mk.get("ok"):
        lh_mkt, la_mkt, _, _ = market_wc.market_lambdas(
            mk["q1"], mk["qX"], mk["q2"], mk.get("q_over"), cfg["mu0"], RHO,
            mk.get("s_hint"), mk.get("line_total", 2.5))
        lh, la = model_wc.blend_lambdas(lh_mkt, la_mkt, lh, la, cfg["w_mkt"])
        P = model_wc.anchor_to_market(model_wc.dc_matrix(lh, la, RHO),
                                      mk["q1"], mk["qX"], mk["q2"])
        book = mk.get("bookmaker") or "mercado"
    else:
        P = model_wc.dc_matrix(lh, la, RHO)
        book = None
    return P, float(lh), float(la), book


def matrix_120(P90, lh, la):
    """Marcador FINAL tras el alargue: un empate a 90' juega un sub-partido de 30' (lambda/3);
    si el alargue no rompe el empate -> penales (queda en la diagonal)."""
    N = P90.shape[0]
    # alargue (30'): Poisson independiente (rho=0). El rho de Dixon-Coles está calibrado para
    # 90' (~2.7 goles totales); a escala de 30' (~0.7) no hay calibración, así que no se corrige.
    P_et = model_wc.dc_matrix(lh / 3.0, la / 3.0, 0.0)
    P120 = np.zeros_like(P90)
    for h in range(N):
        for a in range(N):
            p = P90[h, a]
            if p <= 0:
                continue
            if h != a:
                P120[h, a] += p                      # decidido en los 90'
            else:
                for gh in range(N):
                    row = p * P_et[gh]
                    for ga in range(N):
                        if row[ga] > 0:
                            P120[min(h + gh, N - 1), min(a + ga, N - 1)] += row[ga]
    return P120


def outcome_120(P120):
    """(P(gana local a 120'), P(empate=van a penales), P(gana visita a 120'))."""
    return (float(np.tril(P120, -1).sum()), float(np.trace(P120)),
            float(np.triu(P120, 1).sum()))


def optimize_120(P120, p_pen, fav, pmax=6):
    """Marcador del prode que maximiza E[pts] a 120' INCLUYENDO el +3 por clasificación
    (clasificado inferido del marcador; si es empate, se elige al favorito `fav`)."""
    N = P120.shape[0]
    best = None
    for ph in range(pmax + 1):
        for pa in range(pmax + 1):
            ev = 0.0
            for ah in range(N):
                Prow = P120[ah]
                for aa in range(N):
                    if Prow[aa] > 0:
                        ev += Prow[aa] * prode_wc.puntos((ph, pa), (ah, aa))
            mine = "A" if ph > pa else ("B" if ph < pa else fav)
            ev += 3.0 * p_pen * (PEN_A if mine == "A" else 1 - PEN_A)
            if best is None or ev > best["ev"]:
                best = {"rec": (ph, pa), "ev": ev, "clasif": mine}
    return best


# ----------------------------------------------------------- orquestación -----------

def predict_round(round_name, start=None, end=None, pmax=6):
    """Predice una ronda eliminatoria. Devuelve un dict con la ronda, las predicciones de
    los partidos con equipos definidos y cuántos cruces siguen pendientes (`tbd`)."""
    slug = resolve_slug(round_name)
    if slug not in ROUNDS:
        raise ValueError(f"Ronda desconocida: {round_name!r}. Opciones: {list(ALIAS)}")
    name, _order, out_name = ROUNDS[slug]

    teams, elo0, elo_now, form, cfg, n_hist = engine_state()
    fixtures, tbd = fetch_round(slug, start or "2026-06-28", end or "2026-07-20")

    preds = []
    for r in fixtures:
        if r["status"] == "played":
            continue                                  # ya jugado: no se predice
        home, away = r["home"], r["away"]
        odds_block = fetch_wc._espn_core_odds(r["espn_id"])
        P90, lh, la, book = matrix_90(home, away, elo_now, form, cfg, odds_block)
        P120 = matrix_120(P90, lh, la)
        p1, ppen, p2 = outcome_120(P120)
        adv_home = p1 + ppen * PEN_A
        adv_away = p2 + ppen * (1 - PEN_A)
        fav = "A" if adv_home >= adv_away else "B"
        opt = optimize_120(P120, ppen, fav, pmax)
        clasif = home if opt["clasif"] == "A" else away
        adv_fav = max(adv_home, adv_away)
        conf = "alta" if adv_fav >= 0.75 else ("media" if adv_fav >= 0.62 else "baja")
        preds.append({
            "espn_id": r["espn_id"], "home": home, "away": away,
            "home_name": teams[home]["name"], "away_name": teams[away]["name"],
            "kickoff": r["kickoff"], "venue": r["venue"],
            "p1_120": round(p1, 4), "ppen": round(ppen, 4), "p2_120": round(p2, 4),
            "adv_home": round(adv_home, 4), "adv_away": round(adv_away, 4),
            "rec": list(opt["rec"]), "ev": round(opt["ev"], 3),
            "clasif": clasif, "clasif_name": teams[clasif]["name"],
            "lh": round(lh, 2), "la": round(la, 2), "book": book, "conf": conf,
        })
    preds.sort(key=lambda p: p["kickoff"])
    return {"round": name, "slug": slug, "out_name": out_name, "teams": teams,
            "preds": preds, "tbd": tbd, "n_hist": n_hist, "w_mkt": cfg["w_mkt"],
            "generado": datetime.now().isoformat(timespec="seconds")}
