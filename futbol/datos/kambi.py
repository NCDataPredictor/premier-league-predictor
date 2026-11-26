"""Cuotas de Kambi (motor de Unibet, 888 y otras casas) para la Champions: fuente accesible sin el PC.

Betano solo se puede leer desde el PC de Nicolas. Kambi publica sus cuotas en un JSON público (sin clave) con casi
los mismos mercados de equipo: goles, córners, tarjetas, remates, remates a puerta, faltas y fueras de lugar, total y
por equipo. Se guarda en el mismo formato que el extracto de Betano (futbol/datos/betano.py), así build_site_futbol
lo usa igual:

    python -m futbol.datos.kambi                    # todos los partidos de futbol/champions/partidos/ que no empezaron
    python -m futbol.datos.kambi --forzar           # reemplaza también extractos de Betano (por defecto se respetan)

Salida: futbol/champions/cuotas/<id>.json con "casa": "Kambi (Unibet)". Si ya hay un extracto de Betano de ese
partido se deja (es la casa de Nicolas) salvo --forzar.
"""
import argparse
import glob
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from futbol.datos.betano import NOMBRES  # noqa: E402

BASE = "https://eu-offering-api.kambicdn.com/offering/v2018/ub"
Q = "lang=en_GB&market=ES"
# Rushbet y BetPlay (Colombia) usan Kambi: si el catálogo de Unibet no trae la Champions, se prueban estos.
OFERTAS = [("https://eu-offering-api.kambicdn.com/offering/v2018/ub", "lang=en_GB&market=ES", "Kambi (Unibet)"),
           ("https://eu-offering-api.kambicdn.com/offering/v2018/rsico", "lang=en_GB&market=CO", "Kambi (Rushbet)"),
           ("https://eu-offering-api.kambicdn.com/offering/v2018/betplay", "lang=en_GB&market=CO", "Kambi (BetPlay)"),
           ("https://us1-offering-api.kambicdn.com/offering/v2018/rsico", "lang=en_GB&market=CO", "Kambi (Rushbet)")]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
LIGAS = {"champions": "football/champions_league"}
CASA = "Kambi (Unibet)"

# Nombres en inglés de Kambi que no están en betano.NOMBRES
NOMBRES_K = NOMBRES   # Nombres() de equipos_ucl ya reconoce los nombres en inglés de Kambi

# Mercado (inglés de Kambi, sin el sufijo "(Settled using Opta data)") → nombre de mercado del extracto (como Betano)
MERCADOS = {"Total Goals": "Goles totales Más/Menos", "Total Corners": "Tiros de esquina Menos/Más",
            "Total Cards": "Tarjetas Totales Más/Menos", "Total Shots on Target": "Tiros al Arco",
            "Total Shots": "Remates totales", "Total Fouls conceded": "Total de Faltas Cometidas",
            "Total Offsides": "Total de Fueras de lugar"}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _ruta_champions():
    """Busca en el árbol de grupos de Kambi la ruta de la Champions de la UEFA (por si cambia el nombre).
    Hay otras "Champions League" (Golfo, AFC, CONCACAF, femenina, juvenil): se toma la de nombre exacto o con UEFA."""
    g = _get(f"{BASE}/group.json?{Q}")
    pila = [(g.get("group") or g, [])]
    cands = []
    while pila:
        n, ruta = pila.pop()
        r = ruta + ([n["termKey"]] if n.get("termKey") else [])
        nom = (n.get("englishName") or n.get("name") or "").lower().strip()
        if r and r[0] == "football" and "champions league" in nom:
            otra = any(x in nom for x in ("gulf", "afc", "asian", "concacaf", "caf", "women", "youth", "u19", "arab", "ofc"))
            if not otra:
                cands.append((0 if nom in ("champions league", "uefa champions league") else 1, len(r), "/".join(r), nom))
        for h in n.get("groups") or []:
            pila.append((h, r))
    cands.sort()
    print("Candidatas Kambi:", cands[:5])
    return cands[0][2] if cands else None


def eventos(liga="champions"):
    """Partidos de la liga en el primer catálogo de Kambi que responda (Unibet, Rushbet, BetPlay)."""
    global BASE, Q, CASA
    d, err = None, None
    for base, q, casa in OFERTAS:
        BASE, Q, CASA = base, q, casa
        try:
            d = _get(f"{BASE}/listView/{LIGAS[liga]}/all/matches.json?{Q}&useCombined=true")
        except Exception as e:  # noqa: BLE001
            err = e
            try:
                ruta = _ruta_champions()
                d = _get(f"{BASE}/listView/{ruta}/all/matches.json?{Q}&useCombined=true") if ruta else None
            except Exception as e2:  # noqa: BLE001
                err, d = e2, None
        n = len((d or {}).get("events", []))
        print(f"{casa} ({base.split('/')[2]}, {q}): {n} partidos" + ("" if d else f" · {err}"))
        if n:
            break
    if not d:
        raise RuntimeError(f"Ningún catálogo de Kambi respondió: {err}")
    out = []
    for e in d.get("events", []):
        ev = e["event"]
        L, V = NOMBRES_K.get(ev.get("homeName")), NOMBRES_K.get(ev.get("awayName"))
        out.append({"id": ev["id"], "local": L, "visitante": V, "nombre": ev.get("name"), "inicio": ev.get("start"),
                    "home": ev.get("homeName"), "away": ev.get("awayName")})
    return out


def extracto(ev):
    """Extracto en el formato de betano.py a partir de las ofertas del evento."""
    d = _get(f"{BASE}/betoffer/event/{ev['id']}.json?{Q}&includeParticipants=true")
    mk, props = {}, {}
    for b in d.get("betOffers", []):
        crit = (b.get("criterion") or {}).get("englishLabel", "")
        tipo = (b.get("betOfferType") or {}).get("englishName", "")
        oc = b.get("outcomes") or []
        if any(o.get("status") not in (None, "OPEN") for o in oc):
            continue
        if crit == "Full Time" and tipo == "Match" and len(oc) == 3:
            orden = {"OT_ONE": 0, "OT_CROSS": 1, "OT_TWO": 2}
            v = [None] * 3
            for o in oc:
                if o.get("type") in orden:
                    v[orden[o["type"]]] = o["odds"] / 1000
            if all(v):
                mk["Resultado del partido"] = v
            continue
        if crit == "Both Teams To Score" and tipo == "Yes/No":
            s = {o.get("type"): o["odds"] / 1000 for o in oc}
            if s.get("OT_YES") and s.get("OT_NO"):
                mk["Ambos equipos anotan"] = [s["OT_YES"], s["OT_NO"]]
            continue
        if tipo != "Over/Under":
            continue
        # props de jugador: la línea viene con el nombre del jugador (participant)
        if any(o.get("participant") for o in oc):
            cl = crit.lower()
            stat = ("remates_puerta" if "on target" in cl else "atajadas" if "save" in cl
                    else "remates" if "shot" in cl else None)
            if stat and "half" not in cl:
                jug = next(o.get("participant") for o in oc if o.get("participant"))
                lado = {}
                for o in oc:
                    if o.get("line") is not None and o.get("type") in ("OT_OVER", "OT_UNDER"):
                        lado.setdefault(o["line"] / 1000, {})[o["type"]] = o["odds"] / 1000
                for ln, d2 in lado.items():
                    if "OT_OVER" in d2 and "OT_UNDER" in d2:
                        props.setdefault(jug, {}).setdefault(stat, []).append([ln, d2["OT_OVER"], d2["OT_UNDER"]])
            continue
        base = crit.replace(" (Settled using Opta data)", "").strip()
        if any(x in base for x in ("Half", "Interval", "0:00")):
            continue
        quien, nombre = None, None
        for k in sorted(MERCADOS, key=len, reverse=True):   # "Total Shots on Target" antes que "Total Shots"
            if base == k:
                quien, nombre = "TOTAL", MERCADOS[k]
                break
            eq = next((base[len(k + s):].strip() for s in (" by ", " By ", " - ") if base.startswith(k + s)), None)
            if eq is not None:
                if eq in (ev["home"], ev["away"]):
                    quien, nombre = eq, MERCADOS[k]
                break
        if not nombre:
            continue
        if quien != "TOTAL":
            quien = {ev["home"]: _betano_nombre(ev["local"]), ev["away"]: _betano_nombre(ev["visitante"])}[quien]
        clave = f"{quien}|{nombre}"
        for o in oc:
            if o.get("line") is None:
                continue
            linea = str(o["line"] / 1000)
            par = mk.setdefault(clave, {}).setdefault(linea, [None, None])
            if o.get("type") == "OT_OVER":
                par[0] = o["odds"] / 1000
            elif o.get("type") == "OT_UNDER":
                par[1] = o["odds"] / 1000
    return {"capturado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "casa": CASA, "evento": ev["nombre"],
            "kambi_id": ev["id"], "mercados": mk, "props": props}


def _betano_nombre(cod):
    """Nombre que betano.cuotas_equipo reconoce para ese código (el primero de NOMBRES que lo mapea)."""
    return next(n for n, c in NOMBRES.items() if c == cod)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("liga", nargs="?", default="champions")
    ap.add_argument("--forzar", action="store_true")
    a = ap.parse_args()
    evs = eventos(a.liga)
    print(f"Kambi: {len(evs)} partidos de {a.liga}")
    sin = [e["nombre"] for e in evs if not (e["local"] and e["visitante"])]
    if sin:
        print("Equipos sin código (añadir a NOMBRES_K):", sin)
    ahora = datetime.now(timezone.utc)
    outdir = os.path.join(RAIZ, "futbol", a.liga, "cuotas")
    os.makedirs(outdir, exist_ok=True)
    for f in sorted(glob.glob(os.path.join(RAIZ, "futbol", a.liga, "partidos", "*.json"))):
        with open(f, encoding="utf-8") as fh:
            p = json.load(fh)
        m = p["match"]
        pid = p.get("id") or f'{m["fecha"]}-{m["local"]}-{m["visitante"]}'
        utc = m.get("utc")
        if utc and datetime.fromisoformat(utc.replace("Z", "+00:00")) <= ahora:
            continue   # ya empezó: lo publicado queda congelado
        ev = next((e for e in evs if e["local"] == m["local"] and e["visitante"] == m["visitante"]), None)
        if not ev:
            print(f"{pid}: Kambi no lo ofrece todavía")
            continue
        destino = os.path.join(outdir, pid + ".json")
        x = extracto(ev)
        if x.get("props"):
            p["props"] = {**(p.get("props") or {}), **x["props"]}
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(p, fh, ensure_ascii=False, indent=1)
        hay_betano = False
        if os.path.exists(destino) and not a.forzar:
            with open(destino, encoding="utf-8") as fh:
                hay_betano = (json.load(fh).get("casa") or "").startswith("Betano")
        if not hay_betano:
            with open(destino, "w", encoding="utf-8") as fh:
                json.dump(x, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"{pid}: {len(x['mercados'])} mercados de equipo{' (se respetan los de Betano)' if hay_betano else ''} · "
              f"props de {len(x.get('props') or {})} jugadores")

if __name__ == "__main__":
    main()
