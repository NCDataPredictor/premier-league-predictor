"""Props de jugador de Betano (pestaña Jugadores) → partidos/<id>.json.

Betano Colombia no ofrece Más/Menos por jugador: da escaleras "1+, 2+, 3+..." (solo el lado a favor). La captura se
hace desde el navegador de Nicolas (solo lectura) y queda en futbol/champions/cuotas/betano_props.json:
    {"eventos": {id_betano: "Local - Visitante"}, "datos": {id_betano: {jugador: {"e": equipo, "rp": [k0, c_k0, c_k0+1, ...],
     "p_k": [ks si no son consecutivos]}}}}
con rp=remates_puerta, r=remates, a=atajadas, fc=faltas_cometidas, fr=faltas_recibidas, p=pases.
En la API de Betano las faltas recibidas se llaman "<Jugador> Faltas ganadas" (typeId 1000678); también hay
"Tackles totales" (599, entradas) y "Asistencias totales" (593), que el modelo aún no proyecta.
"N+" equivale a la línea N-0,5 (Más) → [línea, cuota_más, None]: sin lado Menos. build_site_futbol las suma a
partido["props"] al simular (sin pisar un jugador que ya tenga cuota a dos lados); no se guardan en partidos/.

    python -m futbol.datos.betano_props      # resumen por partido
"""
import glob
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from futbol.datos.equipos_ucl import codigo  # noqa: E402

ARCHIVO = os.path.join(RAIZ, "futbol", "champions", "cuotas", "betano_props.json")
STATS = {"rp": "remates_puerta", "r": "remates", "a": "atajadas", "fc": "faltas_cometidas", "fr": "faltas_recibidas",
         "p": "pases"}


def lineas(jug):
    out = {}
    for ab, stat in STATS.items():
        esc = jug.get(ab)
        if not esc:
            continue
        cuotas = esc[1:]
        ks = jug.get(ab + "_k") or [esc[0] + i for i in range(len(cuotas))]
        out[stat] = [[k - 0.5, c, None] for k, c in zip(ks, cuotas) if c and c > 1]
    return out


_CACHE = {}


def props_para(local, visitante):
    """{jugador: {stat: [[línea, más, None], ...]}} de la última captura de Betano para ese partido (o {})."""
    if "cap" not in _CACHE:
        try:
            with open(ARCHIVO, encoding="utf-8") as fh:
                cap = json.load(fh)
        except OSError:
            cap = {"eventos": {}, "datos": {}}
        pares = {}
        for eid, nombre in cap["eventos"].items():
            L, V = (x.strip() for x in nombre.split(" - ", 1))
            pares[(codigo(L), codigo(V))] = eid
        _CACHE["cap"], _CACHE["pares"] = cap, pares
    eid = _CACHE["pares"].get((local, visitante))
    datos = _CACHE["cap"]["datos"].get(eid) if eid else None
    return {j: lineas(x) for j, x in (datos or {}).items()}


def main():
    n = 0
    for f in sorted(glob.glob(os.path.join(RAIZ, "futbol", "champions", "partidos", "*.json"))):
        with open(f, encoding="utf-8") as fh:
            m = json.load(fh)["match"]
        pr = props_para(m["local"], m["visitante"])
        n += bool(pr)
        print(f"{os.path.basename(f)}: {len(pr)} jugadores con escalera de Betano")
    print(f"{n} partidos con props de Betano")


if __name__ == "__main__":
    main()
