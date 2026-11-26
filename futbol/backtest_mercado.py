"""Backtest del modelo de goles frente a la casa con varias temporadas de football-data (Premier).

    python -m futbol.backtest_mercado correr --temporadas 2024-25 2025-26 --sims 2000     # simula y guarda filas
    python -m futbol.backtest_mercado evaluar                                             # métricas y picks

Para cada partido jugado (desde la jornada `--desde`) el modelo predice con SOLO lo que se sabía antes del partido
(temporada en curso + anterior, como en la web) y se guarda, por variante de la fuerza de equipo:

  dc         fuerza.py (Dixon-Coles con decaimiento) → contexto → simulación minuto a minuto  (futbol-0.1, Serie A)
  mercado    λ local/visitante que reproducen el 1X2 y el más/menos 2,5 de la casa (Pinnacle de apertura) → misma
             simulación (lo que hace la Champions con `fuerza_mercado`)
  …_pois     lo mismo pero con Poisson + ρ de Dixon-Coles directo de los λ (sin la simulación), para ver cuánto
             mueve la simulación el 1X2 y los goles

football-data no trae jugadores: cada equipo lleva 11 jugadores sintéticos que se reparten sus remates, faltas y
tarjetas (los goles del equipo no dependen del reparto). Pases y fueras de lugar no vienen: se rellenan con la
media de la liga y no se evalúan.

`evaluar` mide, por variante y mezcla con la casa (MKT_W): log loss y Brier del 1X2 y del más/menos 2,5, % de
acierto del favorito, empates y locales simulados frente a reales, calibración por rango, y los picks con las
reglas de la web (p ≥ MIN_P, EV ≥ VALUE_EV) tomados a la cuota de apertura de bet365 (margen parecido al de Betano
CO): número, % de acierto, unidades y ROI, más el CLV frente al cierre de Pinnacle.
Salida: futbol/premier/backtest/filas*.json y resumen*.json (los de futbol-0.1 y futbol-0.2 quedan guardados).
"""
import argparse
import glob
import json
import math
import os
import sys
import time

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from comun import mercado as MK  # noqa: E402
from futbol.modelo import base, contexto, fuerza, fuerza_mercado, jugadores, simular  # noqa: E402
from futbol.modelo import params as P  # noqa: E402

DIR = os.path.join(RAIZ, "futbol", "premier", "backtest")
FD = os.path.join(DIR, "footballdata")
# 11 jugadores sintéticos: (posición, peso de remates, peso de faltas cometidas, peso de faltas recibidas, pases)
XI = [("POR", 0.0, 0.2, 0.3, 0.6), ("LD", 0.5, 1.0, 0.9, 1.0), ("DFC", 0.5, 1.0, 0.6, 1.2), ("DFC", 0.5, 1.0, 0.6, 1.2),
      ("LI", 0.5, 1.0, 0.9, 1.0), ("MC", 0.9, 1.2, 1.1, 1.3), ("MC", 0.9, 1.2, 1.1, 1.3), ("MCO", 1.5, 0.9, 1.3, 1.1),
      ("EI", 1.8, 0.8, 1.4, 0.9), ("ED", 1.8, 0.8, 1.4, 0.9), ("DC", 2.6, 0.9, 1.3, 0.6)]
LADO = {"LD": "der", "ED": "der", "LI": "izq", "EI": "izq"}
RELLENO = {"pases": 460, "offsides": 2}   # no vienen en football-data: media aproximada de la Premier


def _reparto(total, pesos):
    """Reparte un entero según pesos (mayor resto) para que la suma cuadre."""
    s = sum(pesos)
    if not total or s <= 0:
        return [0] * len(pesos)
    x = [total * w / s for w in pesos]
    b = [int(v) for v in x]
    for i in sorted(range(len(x)), key=lambda i: -(x[i] - b[i]))[: total - sum(b)]:
        b[i] += 1
    return b


def _con_jugadores(p):
    L, V = p["local"], p["visitante"]
    js = {}
    for t, r in ((L, V), (V, L)):
        e = p["equipos"][t]
        for k, v in RELLENO.items():
            e.setdefault(k, v)
        rem = _reparto(e.get("remates", 0), [x[1] for x in XI])
        pue = _reparto(e.get("remates_puerta", 0), [x[1] for x in XI])
        pue = [min(a, b) for a, b in zip(pue, rem)]
        fc = _reparto(e.get("faltas", 0), [x[2] for x in XI])
        fr = _reparto(p["equipos"][r].get("faltas", 0), [x[3] for x in XI])
        pa = _reparto(int(e["pases"] * 0.84), [x[4] for x in XI])
        am = _reparto(e.get("amarillas", 0), [x[2] for x in XI])
        js[t] = [{"id": f"{t}-{i + 1}", "nombre": f"{t} {i + 1}", "pos": x[0], "lado": LADO.get(x[0], "centro"),
                  "titular": True, "min_entra": 0, "min_sale": 90, "jugo": True, "remates": rem[i], "remates_puerta": pue[i],
                  "faltas_cometidas": fc[i], "faltas_recibidas": fr[i], "pases": pa[i], "amarillas": min(1, am[i])}
                 for i, x in enumerate(XI)]
    p["jugadores"] = js
    return p


def cargar():
    ps = []
    for f in sorted(glob.glob(os.path.join(FD, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            ps.extend(json.load(fh))
    return [_con_jugadores(p) for p in ps]


def _anterior(t):
    a = int(t[:4]) - 1
    return f"{a}-{str(a + 1)[2:]}"


def _pois(l1, l2, rho=fuerza_mercado.RHO):
    m = fuerza_mercado._matriz(l1, l2, rho)
    i, j = np.indices(m.shape)
    return [float(m[i > j].sum()), float(m[i == j].sum()), float(m[i < j].sum())], float(m[(i + j) > 2.5].sum()), \
        float(m[(i > 0) & (j > 0)].sum())


def _sim(p, db, goles_fn, sims, sufijo):
    L, V = p["local"], p["visitante"]
    partido = {"id": "bt-" + p["id"] + sufijo, "match": {"fecha": p["fecha"], "local": L, "visitante": V, "neutral": False},
               "contexto": {"arbitro": p.get("arbitro")}, "bajas": {},
               "alineaciones": {"estado": "oficial", **{t: {"titulares": [f"{t}-{i + 1}" for i in range(11)], "banco": []} for t in (L, V)}}}
    ctx = contexto.armar(db, goles_fn, partido)
    prep = {t: jugadores.preparar_equipo(db, partido, t) for t in (L, V)}
    eqs = {}
    for t in (L, V):
        mult, _ = jugadores.ajustes_bajas(prep[t], ctx["esperado"][t])
        eqs[t] = simular.Equipo(prep[t], ctx["esperado"][t], ctx["perfiles"][t], ctx["cruce"][t], mult, ctx["arbitro"], bool(ctx["derbi"]))
    sim = simular.simular(partido["id"], eqs[L], eqs[V], N=sims)
    gl, gv = sim["goles"]
    tl, tv = sim["team"]
    out = {"1x2": [float((gl > gv).mean()), float((gl == gv).mean()), float((gl < gv).mean())],
           "o25": float(((gl + gv) > 2.5).mean()), "btts": float(((gl > 0) & (gv > 0)).mean()),
           "goles": [float(gl.mean()), float(gv.mean())], "esp_goles": [ctx["esperado"][L]["goles"], ctx["esperado"][V]["goles"]]}
    for s in ("corners", "amarillas", "remates", "remates_puerta", "faltas"):
        out[s] = [float(tl[s].mean()), float(tv[s].mean())]
        x = tl[s] + tv[s]
        out[s + "_p"] = [float(np.percentile(x, 10)), float(np.percentile(x, 90))]
        out[s + "_lineas"] = {li: float((x > li).mean()) for li in LINEAS_TOT.get(s, [])}
    return out


LINEAS_TOT = {"corners": [8.5, 9.5, 10.5, 11.5], "amarillas": [2.5, 3.5, 4.5, 5.5], "remates": [22.5, 24.5, 26.5],
              "remates_puerta": [7.5, 8.5, 9.5], "faltas": [18.5, 20.5, 22.5]}


def correr(temporadas, desde, sims, limite=None, variantes=("dc", "mercado"), trozo=None):
    todos = cargar()
    obj = [p for p in todos if p["temporada"] in temporadas and (p.get("jornada") or 0) >= desde]
    obj.sort(key=lambda p: p["fecha"])
    if limite:
        obj = obj[:limite]
    if trozo:   # "i/n": solo los partidos i, i+n, i+2n... (para correr en paralelo)
        i, n_ = (int(x) for x in trozo.split("/"))
        obj = obj[i::n_]
    filas = []
    t0 = time.time()
    for n, p in enumerate(obj, 1):
        temp, ant = p["temporada"], _anterior(p["temporada"])
        hist = [x for x in todos if x["temporada"] in (temp, ant)]
        db = base.construir(hist, temp, hasta=p["fecha"], temporada_ant=ant)
        eq_act = {t for x in db["partidos"] if x["temporada"] == temp for t in (x["local"], x["visitante"])}
        eq_ant = {t for x in db["partidos"] if x["temporada"] == ant for t in (x["local"], x["visitante"])}
        fz = fuerza.ajustar(db["partidos"], p["fecha"], ascendidos=(eq_act - eq_ant) if eq_ant else set(), temporada=temp)
        L, V = p["local"], p["visitante"]
        c = p["cuotas"]
        fila = {"id": p["id"], "temporada": temp, "jornada": p["jornada"], "real": [p["equipos"][L]["goles"], p["equipos"][V]["goles"]],
                "real_stats": {s: p["equipos"][L].get(s, 0) + p["equipos"][V].get(s, 0) for s in LINEAS_TOT},
                "cuotas": c, "fuerza": {"mu": fz["mu"], "localia": fz["localia"], "rho": fz["rho"]}}
        ldc = fuerza.esperados(fz, L, V)
        if "dc" in variantes:
            fila["dc"] = _sim(p, db, lambda a, b, ne: fuerza.esperados(fz, a, b, ne), sims, "")
        x12, ou = c.get("1x2_pinnacle") or c.get("1x2_media"), c.get("ou25_pinnacle") or c.get("ou25_media")
        lm = fuerza_mercado.lambdas(x12, 2.5, ou) if x12 else None
        if lm and P.PESO_FUERZA_PROPIA:   # λ del mercado con un poco de la fuerza propia (media geométrica)
            a = P.PESO_FUERZA_PROPIA
            lm = (lm[0] ** (1 - a) * ldc[0] ** a, lm[1] ** (1 - a) * ldc[1] ** a)
        fila["lambda_dc"], fila["lambda_mercado"] = list(ldc), list(lm) if lm else None
        if lm and "mercado" in variantes:
            fila["mercado"] = _sim(p, db, lambda a, b, ne: tuple(lm) if (a, b) == (L, V) else fuerza.esperados(fz, a, b, ne), sims, "")
        for nom, lam in (("dc_pois", ldc), ("mercado_pois", lm)):
            if lam:
                pr, o25, bt = _pois(*lam, rho=fz["rho"] if nom == "dc_pois" else fuerza_mercado.RHO)
                fila[nom] = {"1x2": pr, "o25": o25, "btts": bt}
        filas.append(fila)
        if n % 25 == 0:
            print(f"  {n}/{len(obj)}  ({time.time() - t0:.0f} s)", flush=True)
    return filas


# ------------------------------------------------------------------------------------------------ evaluar
def _ll3(p, k):
    return -math.log(max(1e-9, p[k]))


def _k(real):
    a, b = real
    return 0 if a > b else (1 if a == b else 2)


def _sin_margen(c):
    return MK.sin_margen(c) if c else None


def _metricas_1x2(filas, f_p):
    xs = [(f_p(f), _k(f["real"])) for f in filas]
    xs = [(p, k) for p, k in xs if p]
    n = len(xs)
    if not n:
        return None
    return {"n": n, "log_loss": round(sum(_ll3(p, k) for p, k in xs) / n, 4),
            "brier": round(sum(sum((p[i] - (i == k)) ** 2 for i in range(3)) for p, k in xs) / n, 4),
            "acierto_favorito": round(sum(max(range(3), key=lambda i: p[i]) == k for p, k in xs) / n, 4),
            "local_media": round(sum(p[0] for p, _ in xs) / n, 3), "empate_media": round(sum(p[1] for p, _ in xs) / n, 3),
            "local_real": round(sum(k == 0 for _, k in xs) / n, 3), "empate_real": round(sum(k == 1 for _, k in xs) / n, 3)}


def _metricas_bin(pares):
    pares = [(p, y) for p, y in pares if p is not None]
    n = len(pares)
    if not n:
        return None
    ll = -sum(y * math.log(max(1e-9, p)) + (1 - y) * math.log(max(1e-9, 1 - p)) for p, y in pares) / n
    return {"n": n, "log_loss": round(ll, 4), "acierto": round(sum((p >= 0.5) == bool(y) for p, y in pares) / n, 4),
            "p_media": round(sum(p for p, _ in pares) / n, 3), "real": round(sum(y for _, y in pares) / n, 3)}


def _picks(filas, f_p1x2, f_po, w, casa="b365", min_p=None, min_ev=None, clv_ref="pinnacle_cierre"):
    """Picks con las reglas de la web en 1X2 y más/menos 2,5: p = (1-w)·casa sin margen + w·modelo."""
    min_p = P.MIN_P if min_p is None else min_p
    min_ev = P.VALUE_EV if min_ev is None else min_ev
    res = []
    for f in filas:
        c = f["cuotas"]
        k = _k(f["real"])
        tot = sum(f["real"])
        p1 = f_p1x2(f)
        c1 = c.get(f"1x2_{casa}")
        if p1 and c1:
            pc = MK.sin_margen(c1)
            cc = c.get(f"1x2_{clv_ref}")
            for i in range(3):
                p = MK.mezclar(p1[i], pc[i], w)
                e = MK.ev(p, c1[i])
                if p >= min_p and e >= min_ev:
                    res.append({"m": "1x2", "p": p, "cuota": c1[i], "gana": i == k,
                                "clv": (c1[i] / cc[i] - 1) if cc else None})
        po = f_po(f)
        co = c.get(f"ou25_{casa}")
        if po is not None and co:
            pc = MK.sin_margen(co)
            cc = c.get(f"ou25_{clv_ref}")
            for i, (pm, gana) in enumerate(((po, tot > 2.5), (1 - po, tot < 2.5))):
                p = MK.mezclar(pm, pc[i], w)
                e = MK.ev(p, co[i])
                if p >= min_p and e >= min_ev:
                    res.append({"m": "ou25", "p": p, "cuota": co[i], "gana": gana, "clv": (co[i] / cc[i] - 1) if cc else None})
    n = len(res)
    if not n:
        return {"n": 0}
    u = sum((x["cuota"] - 1) if x["gana"] else -1 for x in res)
    clv = [x["clv"] for x in res if x["clv"] is not None]
    return {"n": n, "acierto": round(sum(x["gana"] for x in res) / n, 4), "p_media": round(sum(x["p"] for x in res) / n, 3),
            "cuota_media": round(sum(x["cuota"] for x in res) / n, 2), "unidades": round(u, 2), "roi": round(u / n, 4),
            "clv_medio": round(sum(clv) / len(clv), 4) if clv else None,
            "por_mercado": {m: sum(1 for x in res if x["m"] == m) for m in ("1x2", "ou25")}}


def _fuentes(filas):
    """Probabilidades 1X2 y más 2,5 de cada fuente."""
    nv = lambda c: MK.sin_margen(c) if c else None  # noqa: E731
    F = {
        "casa_pinnacle": (lambda f: nv(f["cuotas"].get("1x2_pinnacle")), lambda f: (nv(f["cuotas"].get("ou25_pinnacle")) or [None])[0]),
        "casa_pinnacle_cierre": (lambda f: nv(f["cuotas"].get("1x2_pinnacle_cierre")), lambda f: (nv(f["cuotas"].get("ou25_pinnacle_cierre")) or [None])[0]),
        "casa_b365": (lambda f: nv(f["cuotas"].get("1x2_b365")), lambda f: (nv(f["cuotas"].get("ou25_b365")) or [None])[0]),
    }
    for v in ("dc", "mercado", "dc_pois", "mercado_pois", "dc_cal"):
        if any(v in f for f in filas):
            F[v] = ((lambda v: lambda f: (f.get(v) or {}).get("1x2"))(v), (lambda v: lambda f: (f.get(v) or {}).get("o25"))(v))
    return F


def evaluar(filas):
    F = _fuentes(filas)
    out = {"partidos": len(filas), "temporadas": sorted({f["temporada"] for f in filas}), "1x2": {}, "mas25": {}, "picks": {}}
    for nom, (f1, fo) in F.items():
        out["1x2"][nom] = _metricas_1x2(filas, f1)
        out["mas25"][nom] = _metricas_bin([(fo(f), sum(f["real"]) > 2.5) for f in filas])
    # mezcla con la casa (la web): p = (1-w)·bet365 sin margen + w·modelo
    for nom in [k for k in F if not k.startswith("casa")]:
        f1, fo = F[nom]
        out["picks"][nom] = {}
        for w in (0.1, 0.2, 0.3, 0.5, 1.0):
            out["picks"][nom][f"w{w}"] = _picks(filas, f1, fo, w)
        # log loss de la mezcla con Pinnacle de apertura (¿el modelo le añade información a la casa?)
        out.setdefault("mezcla_ll", {})[nom] = {}
        for w in (0.0, 0.1, 0.2, 0.3, 0.5):
            def mix(f, w=w):
                pc, pm = F["casa_pinnacle"][0](f), f1(f)
                return [(1 - w) * a + w * b for a, b in zip(pc, pm)] if pc and pm else None
            out["mezcla_ll"][nom][f"w{w}"] = _metricas_1x2(filas, mix)["log_loss"]
    # calibración y p10-p90 de estadísticas de equipo (variante dc)
    st = {}
    for s, lineas in LINEAS_TOT.items():
        xs = [f for f in filas if "dc" in f and f["dc"].get(s + "_p")]
        if not xs:
            continue
        bajo = sum(f["real_stats"][s] < f["dc"][s + "_p"][0] for f in xs) / len(xs)
        sobre = sum(f["real_stats"][s] > f["dc"][s + "_p"][1] for f in xs) / len(xs)
        st[s] = {"media_sim": round(sum(sum(f["dc"][s]) for f in xs) / len(xs), 2),
                 "media_real": round(sum(f["real_stats"][s] for f in xs) / len(xs), 2),
                 "bajo_p10": round(bajo, 3), "sobre_p90": round(sobre, 3),
                 "lineas": {str(li): _metricas_bin([(f["dc"][s + "_lineas"].get(str(li), f["dc"][s + "_lineas"].get(li)), f["real_stats"][s] > li) for f in xs])
                            for li in lineas}}
    out["estadisticas_dc"] = st
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("correr")
    c.add_argument("--temporadas", nargs="+", default=["2024-25", "2025-26"])
    c.add_argument("--desde", type=int, default=4)
    c.add_argument("--sims", type=int, default=2000)
    c.add_argument("--limite", type=int)
    c.add_argument("--salida", default="filas.json")
    c.add_argument("--trozo", help="i/n: corre solo una parte (en paralelo) y luego se juntan con 'juntar'")
    c.add_argument("--variantes", nargs="+", default=["dc", "mercado"])
    c.add_argument("--fijar", nargs="*", default=[], help="PARAM=valor para probar parámetros (p. ej. GAMMA_GOLES=0)")
    j = sub.add_parser("juntar")
    j.add_argument("archivos", nargs="+")
    j.add_argument("--salida", default="filas.json")
    e = sub.add_parser("evaluar")
    e.add_argument("--filas", default="filas.json")
    a = ap.parse_args()
    if a.cmd == "correr":
        for kv in a.fijar:
            k, v = kv.split("=")
            setattr(P, k, float(v))
            print(f"{k} = {v}")
        filas = correr(a.temporadas, a.desde, a.sims, a.limite, tuple(a.variantes), a.trozo)
        with open(os.path.join(DIR, a.salida), "w", encoding="utf-8") as fh:
            json.dump(filas, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"{len(filas)} partidos → {a.salida}")
    elif a.cmd == "juntar":
        filas = []
        for f in a.archivos:
            with open(os.path.join(DIR, f), encoding="utf-8") as fh:
                filas.extend(json.load(fh))
        filas.sort(key=lambda f: f["id"])
        with open(os.path.join(DIR, a.salida), "w", encoding="utf-8") as fh:
            json.dump(filas, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"{len(filas)} partidos → {a.salida}")
    else:
        with open(os.path.join(DIR, a.filas), encoding="utf-8") as fh:
            filas = json.load(fh)
        res = evaluar(filas)
        with open(os.path.join(DIR, a.filas.replace("filas", "resumen")), "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
        print(json.dumps({k: res[k] for k in ("partidos", "1x2", "mas25", "mezcla_ll")}, ensure_ascii=False, indent=1))
        print(json.dumps(res["picks"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
