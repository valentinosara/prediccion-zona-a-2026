"""
predict_cli.py - Predecir un partido (o varios) AL TOQUE cargando las cuotas a mano.

Pensado para cuando no hay fetch automatico (red bloqueada) pero queres la jugada del
prode YA: leés las cuotas de cualquier casa (1X2, y si podés Over/Under 2.5 y handicap
asiatico) y este script te devuelve, con el MISMO motor (de-vig + Dixon-Coles + puntos
esperados + Monte Carlo):

  - P(local)/P(empate)/P(visita) de-vigadas y el favorito,
  - los goles esperados λ por equipo,
  - el MARCADOR RECOMENDADO para el prode (maximiza los puntos esperados),
  - el marcador mas probable (aparte) y el top-5 por puntos esperados,
  - el nivel de confianza.

Un partido (rapido):
  python predict_cli.py --home "Brasil" --away "Japon" --h2h 1.50 4.10 6.90 \
                        --ou 2.5 1.83 1.97 --ah -1.25 1.93 1.93 --book Pinnacle --kickoff 14:00

Varios partidos + HTML (docs/mundial_hoy.html):
  python predict_cli.py --file hoy.json --html
  # hoy.json: {"titulo":"Mundial 2026 — Hoy", "matches":[
  #   {"home":"Brasil","away":"Japon","h2h":[1.50,4.10,6.90],
  #    "ou":[2.5,1.83,1.97],"ah":[-1.25,1.93,1.93],"book":"Pinnacle","kickoff":"14:00",
  #    "group":"G","hflag":"BR","aflag":"JP"} ]}

Si no pasás cuotas, cae al modelo de fuerza Elo (--elo H A; por defecto 1800/1800).
"""
import argparse
import json
import os
from datetime import datetime

import model_wc
import predict_wc
import ratings_wc


def flag(iso2):
    """ISO-3166 alpha-2 -> emoji bandera (con caso especial Inglaterra)."""
    if not iso2:
        return ""
    iso2 = iso2.upper()
    if iso2 in ("GB-ENG", "ENG"):
        return "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"
    if len(iso2) != 2:
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2)


def _kickoff_iso(s):
    """'14:00' -> hoy a esa hora (ISO); ISO completo se respeta; vacio -> ahora."""
    if not s:
        return datetime.now().isoformat(timespec="minutes")
    if "T" in s or len(s) > 8:
        return s
    try:
        hh, mm = s.split(":")
        return datetime.now().replace(hour=int(hh), minute=int(mm), second=0,
                                      microsecond=0).isoformat(timespec="minutes")
    except Exception:
        return s


def make_match(spec, idx=0):
    """Normaliza un partido (dict del --file o de los args) a (match, teams, elo, odds_block)."""
    home, away = spec["home"], spec["away"]
    hk = f"H{idx}_" + "".join(c for c in home if c.isalnum())[:12] or f"H{idx}"
    ak = f"A{idx}_" + "".join(c for c in away if c.isalnum())[:12] or f"A{idx}"
    elo = spec.get("elo") or [1800.0, 1800.0]
    teams = {
        hk: {"name": home, "iso2": spec.get("hflag", ""), "flag": flag(spec.get("hflag", "")),
             "elo": float(elo[0]), "fifa_rank": None, "group": spec.get("group", "—"), "host": False},
        ak: {"name": away, "iso2": spec.get("aflag", ""), "flag": flag(spec.get("aflag", "")),
             "elo": float(elo[1]), "fifa_rank": None, "group": spec.get("group", "—"), "host": False},
    }
    match = {"id": spec.get("id", f"MANUAL-{idx+1:02d}"), "group": spec.get("group", "—"),
             "matchday": 0, "home": hk, "away": ak,
             "kickoff": _kickoff_iso(spec.get("kickoff", "")), "venue": spec.get("venue", "")}
    odds_block = None
    if spec.get("h2h"):
        odds_block = {"bookmaker": spec.get("book", "mercado"), "h2h": list(spec["h2h"])}
        if spec.get("ou"):
            ln, ov, un = spec["ou"]
            odds_block["totals"] = {"line": float(ln), "over": float(ov), "under": float(un)}
        if spec.get("ah"):
            ln, hh, aa = spec["ah"]
            odds_block["spreads"] = {"line": float(ln), "home": float(hh), "away": float(aa)}
    return match, teams, {hk: float(elo[0]), ak: float(elo[1])}, odds_block


def predict_one(spec, idx, cfg):
    match, teams, elo, odds_block = make_match(spec, idx)
    pred = predict_wc.build_prediction(match, teams, elo, elo, {}, odds_block, cfg)
    return pred, teams


def report_text(pred, teams):
    h, a = teams[pred["home"]], teams[pred["away"]]
    W = 60
    L = []
    L.append("═" * W)
    title = f"  ⚽ {h['flag']} {h['name']}  vs  {a['flag']} {a['name']}"
    when = pred["kickoff"].replace("T", " ")
    L.append(title)
    grp = f"Grupo {pred['group']}" if pred["group"] not in (None, "—") else ""
    L.append(f"     {grp}  ·  {when}".rstrip())
    L.append("═" * W)
    src = "mercado " + (pred["bookmaker"] or "") if pred["market_used"] else "modelo Elo (sin cuotas)"
    L.append(f"  {src} (de-vigado):  "
             f"Local {pred['p1']*100:4.1f}%   Empate {pred['pX']*100:4.1f}%   "
             f"Visita {pred['p2']*100:4.1f}%")
    L.append(f"  λ esperados (goles):  {h['name']} {pred['lh']:.2f}  –  {pred['la']:.2f} {a['name']}")
    L.append(f"  Favorito (quien gana): {pred['ganador']}")
    L.append("-" * W)
    L.append(f"  ★ MARCADOR RECOMENDADO (prode):  {pred['rec'][0]}–{pred['rec'][1]}"
             f"      [{pred['ev_rec']:.2f} pts esperados]")
    L.append(f"    Marcador mas probable:         {pred['modo'][0]}–{pred['modo'][1]}"
             f"      ({pred['modo_prob']*100:.1f}%)")
    L.append("-" * W)
    L.append("  Top-5 por puntos esperados:")
    for c in pred["top"]:
        star = "  ★" if c["score"] == pred["rec"] else ""
        L.append(f"      {c['score'][0]}–{c['score'][1]}    prob {c['prob']*100:5.1f}%"
                 f"    E[pts] {c['ev']:.2f}{star}")
    L.append("-" * W)
    L.append(f"  Confianza: {pred['confianza'].upper()}"
             f"   (entropia 1X2 {pred['entropia']}, brecha E[pts] {pred['gap']:.2f},"
             f" {pred['mc']['n']:,} sims)")
    L.append("═" * W)
    return "\n".join(L)


def write_html(preds_teams, cfg, titulo):
    """Arma data_mundial/pred_wc.json (formato gen_html) y genera docs/mundial_hoy.html."""
    import gen_html_wc
    teams = {}
    preds = []
    for pred, tms in preds_teams:
        teams.update(tms)
        preds.append(pred)
    conf = {"alta": 0, "media": 0, "baja": 0}
    for p in preds:
        conf[p["confianza"]] += 1
    now = datetime.now().isoformat(timespec="seconds")
    manual_prov = {"source": "manual", "fetched_at": now, "detail": "cuotas cargadas a mano"}
    data = {
        "meta": {"fecha": 0, "titulo": titulo, "out_name": "mundial_hoy.html",
                 "generado": now, "datos_al": now, "n_pendientes": len(preds), "n_jugados": 0,
                 "ev_total": round(sum(p["ev_rec"] for p in preds), 1), "w_mkt": cfg["w_mkt"],
                 "mu0": cfg["mu0"], "rho": cfg["rho"], "tournament_games_per_team": 0,
                 "confianza_global": conf, "n_sims": cfg["n_sims"],
                 "provenance": {"teams": manual_prov, "fixtures": manual_prov, "odds": manual_prov}},
        "teams": teams, "elo_now": {k: v["elo"] for k, v in teams.items()},
        "pendientes": preds, "backtest": {"n": 0, "total_pts": 0, "max_pts": 0, "avg_pts": 0.0, "rows": []},
    }
    os.makedirs(predict_wc.DATA, exist_ok=True)
    json.dump(data, open(os.path.join(predict_wc.DATA, "pred_wc.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return gen_html_wc.build()


def main():
    ap = argparse.ArgumentParser(
        description="Prediccion del prode cargando las cuotas a mano (sin fetch).")
    ap.add_argument("--home"); ap.add_argument("--away")
    ap.add_argument("--h2h", nargs=3, type=float, metavar=("LOCAL", "EMPATE", "VISITA"),
                    help="cuotas decimales 1X2")
    ap.add_argument("--ou", nargs=3, type=float, metavar=("LINEA", "OVER", "UNDER"),
                    help="Over/Under (ej: 2.5 1.83 1.97)")
    ap.add_argument("--ah", nargs=3, type=float, metavar=("LINEA", "LOCAL", "VISITA"),
                    help="handicap asiatico (linea del LOCAL, negativa=favorito)")
    ap.add_argument("--book", default="mercado"); ap.add_argument("--group", default="—")
    ap.add_argument("--kickoff", default=""); ap.add_argument("--venue", default="")
    ap.add_argument("--hflag", default=""); ap.add_argument("--aflag", default="")
    ap.add_argument("--elo", nargs=2, type=float, metavar=("LOCAL", "VISITA"))
    ap.add_argument("--wmkt", type=float, default=0.85, help="peso del mercado en el blend")
    ap.add_argument("--sims", type=int, default=50000)
    ap.add_argument("--file", help="JSON con varios partidos")
    ap.add_argument("--html", action="store_true", help="genera docs/mundial_hoy.html")
    args = ap.parse_args()

    cfg = {"mu0": ratings_wc.MU0_DEFAULT, "rho": model_wc.RHO_DEFAULT,
           "w_mkt": args.wmkt, "host_codes": set(), "n_sims": args.sims}

    if args.file:
        spec = json.load(open(args.file, encoding="utf-8"))
        matches = spec["matches"] if isinstance(spec, dict) else spec
        titulo = spec.get("titulo", "Hoy") if isinstance(spec, dict) else "Hoy"
    elif args.home and args.away:
        matches = [{"home": args.home, "away": args.away, "h2h": args.h2h, "ou": args.ou,
                    "ah": args.ah, "book": args.book, "group": args.group,
                    "kickoff": args.kickoff, "venue": args.venue, "hflag": args.hflag,
                    "aflag": args.aflag, "elo": args.elo}]
        titulo = "Hoy"
    else:
        ap.error("pasá --home y --away (con --h2h), o --file con varios partidos.")

    preds_teams = [predict_one(m, i, cfg) for i, m in enumerate(matches)]
    for pred, teams in preds_teams:
        print(report_text(pred, teams))
        print()
    total = sum(p["ev_rec"] for p, _ in preds_teams)
    if len(preds_teams) > 1:
        print(f"  Puntos esperados totales: {total:.1f} en {len(preds_teams)} partidos\n")

    if args.html:
        path = write_html(preds_teams, cfg, titulo)
        print(f"  HTML generado: {os.path.relpath(path, os.path.dirname(os.path.abspath(__file__)))}")


if __name__ == "__main__":
    main()
