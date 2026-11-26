"""Parlay soñador de la Champions: una combinada larga por día de partidos, para soñar.

Pedido de Nicolas (24-nov-2026), copiando la idea de la NBA: con tantos partidos por día, una combinada con cuota
total entre CUOTA_TOTAL[0] y CUOTA_TOTAL[1], armada con las líneas más probables que tienen cuota real de la casa
(Betano), incluidas las props de jugador. El modelo nunca supone una cuota: solo entran líneas con precio publicado.

Reglas:
  - cada pata: probabilidad final (mezcla con la casa) ≥ P_MIN y cuota entre CUOTA[0] y CUOTA[1];
  - como mucho MAX_POR_PARTIDO patas por partido (una de equipo o total y otra de jugador), una por jugador y una por
    mercado (quién + estadística); las props solo de jugadores con prob. de titular ≥ MIN_TITULAR;
  - como mucho la mitad de las patas al "Menos de";
  - se eligen por la menor pérdida de probabilidad por cada punto de cuota ganado (ln p / ln cuota), hasta llegar al
    mínimo de cuota total sin pasarse del máximo.
Un soñador queda congelado cuando empieza el primer partido de su día (es el que se publicó antes de jugar).
"""
import json
import math
import os
from datetime import datetime, timezone

P_MIN = 0.60
CUOTA = (1.15, 3.0)
CUOTA_TOTAL = (50.0, 200.0)
MAX_POR_PARTIDO = 2
MAX_EQUIPO_POR_PARTIDO = 1   # la otra pata del partido queda para una prop de jugador (pedido de Nicolas)
MIN_TITULAR = 0.75           # props solo de jugadores que casi seguro arrancan (la prob. es "si juega")
MAX_PATAS = 20


def armar(lineas):
    """lineas: dicts con id, game, tipo, jugador, equipo, stat, linea, lado, cuota, p. Devuelve el soñador o None."""
    cands = [x for x in lineas if x["p"] >= P_MIN and CUOTA[0] <= x["cuota"] <= CUOTA[1]]
    cands.sort(key=lambda x: (math.log(x["p"]) / math.log(x["cuota"]), -x["p"]), reverse=True)
    patas, por_partido, por_equipo, quien, mercado = [], {}, {}, set(), set()
    q = 1.0
    for x in cands:
        if q >= CUOTA_TOTAL[0] or len(patas) >= MAX_PATAS:
            break
        mk = (x["id"], x["jugador"], x["stat"])
        if por_partido.get(x["id"], 0) >= MAX_POR_PARTIDO or mk in mercado:
            continue
        if x["tipo"] == "jugador" and x["jugador"] in quien:
            continue
        if x["tipo"] != "jugador" and por_equipo.get(x["id"], 0) >= MAX_EQUIPO_POR_PARTIDO:
            continue
        if q * x["cuota"] > CUOTA_TOTAL[1]:
            continue
        unders = sum(1 for k in patas if k["lado"] == "under") + (x["lado"] == "under")
        if unders > (len(patas) + 1) / 2:
            continue
        patas.append(x)
        q *= x["cuota"]
        por_partido[x["id"]] = por_partido.get(x["id"], 0) + 1
        mercado.add(mk)
        if x["tipo"] == "jugador":
            quien.add(x["jugador"])
        else:
            por_equipo[x["id"]] = por_equipo.get(x["id"], 0) + 1
    if q < CUOTA_TOTAL[0]:
        return None
    p = math.prod(k["p"] for k in patas)
    return {"cuota": round(q, 2), "p": round(p, 5), "ev": round(p * q - 1, 3), "n": len(patas),
            "patas": sorted(patas, key=lambda k: (k.get("hora") or "", k["game"], -k["p"]))}


def armar_jornada(outdir, lista, previos):
    """Un soñador por fecha con los partidos de index.json; respeta los ya congelados (su día ya empezó)."""
    ahora = datetime.now(timezone.utc)
    por_dia = {}
    for r in lista:
        por_dia.setdefault(r["fecha"], []).append(r)
    out = {}
    for fecha, rs in sorted(por_dia.items()):
        datos = []
        for r in rs:
            try:
                with open(os.path.join(outdir, r["id"] + ".json"), encoding="utf-8") as fh:
                    datos.append(json.load(fh))
            except OSError:
                pass
        inicios = [datetime.fromisoformat(d["match"]["utc"].replace("Z", "+00:00")) for d in datos if d["match"].get("utc")]
        empezo = bool(inicios) and min(inicios) <= ahora
        if empezo and fecha in previos:
            out[fecha] = {**previos[fecha], "congelado": True}
            continue
        if empezo:
            continue   # nunca se publicó antes de empezar: no se inventa uno a posteriori
        titular = {(t, j["nombre"]): j.get("p_titular") or 0 for d in datos for t, js in (d.get("jugadores") or {}).items() for j in js}
        lineas = [{**x, "id": d["id"], "game": d["match"]["local"] + "–" + d["match"]["visitante"],
                   "fecha": d["match"]["fecha"], "hora": d["match"].get("hora_bogota")}
                  for d in datos for x in d.get("lineas_casa") or []
                  if x["tipo"] != "jugador" or titular.get((x["equipo"], x["jugador"]), 0) >= MIN_TITULAR]
        s = armar(lineas)
        if s:
            s["armado"] = ahora.strftime("%Y-%m-%dT%H:%MZ")
            out[fecha] = s
    return out
