"""football-data.co.uk (Premier, archivo E0.csv por temporada) → formato normalizado + cuotas, SOLO para backtest.

football-data trae, por partido: goles, remates, a puerta, córners, faltas, amarillas, rojas, árbitro y las cuotas
1X2 y de más/menos 2,5 goles de varias casas, de apertura (viernes) y de cierre. No trae jugadores, eventos por
minuto, pases ni fueras de lugar, así que NO reemplaza a FotMob para la web: sirve para medir el modelo de goles y
de estadísticas de equipo frente a la casa en varias temporadas (futbol/backtest_mercado.py).

    python -m futbol.datos.footballdata ruta/E0_2425.csv ruta/E0_2526.csv ...

El nombre del archivo debe terminar en _AABB.csv (2425 = 2024-25). Escribe futbol/premier/backtest/footballdata/<temporada>.json.
Desde la nube de Claude football-data.co.uk está bloqueado; los CSV se bajaron de copias públicas en GitHub
(misma estructura). Desde el PC: https://www.football-data.co.uk/mmz4281/2526/E0.csv
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from futbol.datos.equipos_epl import codigo  # noqa: E402

SALIDA = os.path.join(RAIZ, "futbol", "premier", "backtest", "footballdata")
# casas: prefijo de columna (apertura, cierre)
CASAS_1X2 = {"pinnacle": ("PS", "PSC"), "b365": ("B365", "B365C"), "media": ("Avg", "AvgC"), "max": ("Max", "MaxC")}
CASAS_OU = {"pinnacle": ("P", "PC"), "b365": ("B365", "B365C"), "media": ("Avg", "AvgC"), "max": ("Max", "MaxC")}


def _f(x):
    try:
        v = float(x)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _i(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def _fecha(s):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(s)


def convertir(ruta):
    m = re.search(r"(\d{2})(\d{2})\.csv$", ruta)
    temporada = f"20{m.group(1)}-{m.group(2)}"
    filas = [r for r in csv.DictReader(open(ruta, encoding="utf-8-sig")) if r.get("HomeTeam")]
    filas.sort(key=lambda r: (_fecha(r["Date"]), r.get("Time") or ""))
    jugados = defaultdict(int)
    out = []
    for r in filas:
        L, V = codigo(r["HomeTeam"]), codigo(r["AwayTeam"])
        fecha = _fecha(r["Date"])
        jugados[L] += 1
        jugados[V] += 1
        eq = {}
        for t, h in ((L, "H"), (V, "A")):
            e = {"goles": _i(r[f"FT{h}G"]), "remates": _i(r.get(f"{h}S")), "remates_puerta": _i(r.get(f"{h}ST")),
                 "corners": _i(r.get(f"{h}C")), "faltas": _i(r.get(f"{h}F")), "amarillas": _i(r.get(f"{h}Y")),
                 "rojas": _i(r.get(f"{h}R"))}
            xg = r.get(f"{h}xG")
            if xg not in (None, ""):
                e["xg"] = float(xg)
            eq[t] = {k: v for k, v in e.items() if v is not None}
        cuotas = {}
        for casa, (a, c) in CASAS_1X2.items():
            for nom, pre in (("", a), ("_cierre", c)):
                v = [_f(r.get(pre + x)) for x in "HDA"]
                if all(v):
                    cuotas[f"1x2_{casa}{nom}"] = v
        for casa, (a, c) in CASAS_OU.items():
            for nom, pre in (("", a), ("_cierre", c)):
                v = [_f(r.get(pre + ">2.5")), _f(r.get(pre + "<2.5"))]
                if all(v):
                    cuotas[f"ou25_{casa}{nom}"] = v
        out.append({"id": f"{fecha}-{L}-{V}", "fuente": "football-data", "liga": "premier", "temporada": temporada,
                    "jornada": max(jugados[L], jugados[V]), "fecha": fecha, "competicion": "liga", "local": L, "visitante": V,
                    "arbitro": (r.get("Referee") or "").strip() or None,
                    "medio_tiempo": [_i(r.get("HTHG")), _i(r.get("HTAG"))],
                    "equipos": eq, "cuotas": cuotas})
    return temporada, out


def main():
    os.makedirs(SALIDA, exist_ok=True)
    for ruta in sys.argv[1:]:
        temporada, ps = convertir(ruta)
        with open(os.path.join(SALIDA, temporada + ".json"), "w", encoding="utf-8") as fh:
            json.dump(ps, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"{temporada}: {len(ps)} partidos, {len({p['local'] for p in ps})} equipos")


if __name__ == "__main__":
    main()
