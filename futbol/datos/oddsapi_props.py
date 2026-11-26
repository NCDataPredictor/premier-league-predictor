"""Cuotas de jugador (props) desde The Odds API, para cuando no hay extracto de Betano con líneas de jugador.

El modelo ya proyecta remates, remates a puerta y atajadas de cada jugador; para que un prop sea pick hace falta
una cuota real a los dos lados (Más/Menos). Betano solo se lee desde el PC; esto funciona desde GitHub Actions.

    python -m futbol.datos.oddsapi_props            # partidos de futbol/champions/partidos/ que no empezaron

Costo: cada partido cuesta (mercados × regiones) créditos del plan de 500/mes compartido con la Serie A
(aquí hasta 3 mercados × 1 región = 3 por partido, ~54 por jornada de 18; un 422 no cobra). Por eso se consulta como mucho una vez cada MIN_HORAS.
Escribe en cada partidos/<id>.json: "props": {"Jugador": {"remates_puerta": [[línea, más, menos], ...], ...}},
con la mediana de las casas que dan los dos lados de esa línea. Nunca inventa una cuota.
"""
import glob
import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from futbol.datos.equipos_ucl import codigo  # noqa: E402

BASE = "https://api.the-odds-api.com/v4/sports/soccer_uefa_champs_league"
REGIONES = "eu"
# mercado de The Odds API → estadística del modelo
MERCADOS = {"player_shots_on_target": "remates_puerta", "player_shots": "remates", "player_goalkeeper_saves": "atajadas"}
MIN_HORAS = 5
ESTADO = os.path.join(RAIZ, "futbol", "champions", "nube", "props_estado.json")   # fuera de consenso/: ese glob solo lee fotos


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ncdata-predictor"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")), r.headers.get("x-requests-remaining")


def lineas(evento):
    """{jugador: {stat: [[línea, más, menos]]}} con la mediana de las casas que dan ambos lados."""
    tmp = {}
    for bk in evento.get("bookmakers", []):
        for m in bk.get("markets", []):
            stat = MERCADOS.get(m["key"])
            if not stat:
                continue
            lados = {}
            for o in m.get("outcomes", []):
                jug, pt = o.get("description"), o.get("point")
                if not jug or pt is None or o.get("name") not in ("Over", "Under"):
                    continue
                lados.setdefault((jug, pt), {})[o["name"]] = o["price"]
            for (jug, pt), d in lados.items():
                if "Over" in d and "Under" in d:
                    tmp.setdefault(jug, {}).setdefault(stat, {}).setdefault(pt, []).append((d["Over"], d["Under"]))
    out = {}
    for jug, porstat in tmp.items():
        for stat, porlinea in porstat.items():
            out.setdefault(jug, {})[stat] = [[pt, round(statistics.median(x[0] for x in v), 3), round(statistics.median(x[1] for x in v), 3)]
                                             for pt, v in sorted(porlinea.items())]
    return out


def main():
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        print("Sin ODDS_API_KEY: no se consultan props.")
        return
    ahora = datetime.now(timezone.utc)
    try:
        with open(ESTADO, encoding="utf-8") as fh:
            est = json.load(fh)
        ult = datetime.fromisoformat(est["ultima"])
        if est.get("partidos_con_props") == 0 and not os.environ.get("PROPS_FORZAR"):
            # 24-nov-2026: las casas "eu" no dan remates de jugador en la Champions y cada consulta cobra igual.
            print("La última consulta no trajo ningún prop: no se gasta más (PROPS_FORZAR=1 para reintentar).")
            return
        if ahora - ult < timedelta(hours=MIN_HORAS) and not os.environ.get("PROPS_FORZAR"):
            print(f"Props consultados a las {ult:%H:%M} UTC: todavía no toca (ahorro de créditos).")
            return
    except (OSError, KeyError, ValueError):
        pass
    eventos, rest = _get(f"{BASE}/events?apiKey={key}")   # gratis
    print(f"{len(eventos)} eventos en The Odds API · créditos restantes {rest}")
    por_par = {(codigo(e["home_team"]), codigo(e["away_team"])): e for e in eventos}
    n_ok = 0
    no_hay = set()
    for f in sorted(glob.glob(os.path.join(RAIZ, "futbol", "champions", "partidos", "*.json"))):
        with open(f, encoding="utf-8") as fh:
            p = json.load(fh)
        m = p["match"]
        if datetime.fromisoformat(m["utc"].replace("Z", "+00:00")) <= ahora:
            continue
        e = por_par.get((m["local"], m["visitante"]))
        if not e:
            print(f"{p['id']}: no está en The Odds API")
            continue
        # un mercado por consulta: si la API no ofrece uno para la Champions (422, no cobra), los demás siguen
        d = {"bookmakers": []}
        for mk in MERCADOS:
            if mk in no_hay:
                continue
            try:
                dm, rest = _get(f"{BASE}/events/{e['id']}/odds?apiKey={key}&regions={REGIONES}&markets={mk}&oddsFormat=decimal")
                d["bookmakers"] += dm.get("bookmakers", [])
            except urllib.error.HTTPError as ex:
                cuerpo = ex.read().decode("utf-8", "replace")[:200]
                print(f"{p['id']} {mk}: HTTP {ex.code} {cuerpo}")
                if ex.code == 422:
                    no_hay.add(mk)   # mercado no disponible en este deporte: no se vuelve a pedir
            except Exception as ex:  # noqa: BLE001
                print(f"{p['id']} {mk}: {ex}")
        pr = lineas(d)
        if pr:
            p["props"] = {**pr, **(p.get("props") or {})}   # si Kambi ya trajo ese jugador, gana Kambi
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(p, fh, ensure_ascii=False, indent=1)
            n_ok += 1
        print(f"{p['id']}: {len(pr)} jugadores con línea · créditos restantes {rest}")
    os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
    with open(ESTADO, "w", encoding="utf-8") as fh:
        json.dump({"ultima": ahora.isoformat(), "partidos_con_props": n_ok, "creditos_restantes": rest, "mercados_sin_oferta": sorted(no_hay)}, fh)


if __name__ == "__main__":
    main()
