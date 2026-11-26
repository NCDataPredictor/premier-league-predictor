"""Fuerza de equipo desde el mercado (Champions, TRASPASO §6.2).

En la Champions cada equipo lleva pocos partidos y casi nunca contra rivales comunes, así que el Dixon-Coles de
fuerza.py no da números creíbles. Aquí se sacan los goles esperados (λ local, λ visitante) que reproducen la cuota
1X2 sin margen y la de total de goles (línea 2,5 o la más cercana) con Poisson independiente + ρ de Dixon-Coles.
El simulador usa esos λ; el modelo aporta lo suyo en córners, tarjetas, remates, faltas y props de jugador.
"""
import math

import numpy as np

RHO = -0.05     # corrección de Dixon-Coles para 0-0/1-1 (valor típico; no se re-estima aquí)
MAXG = 11


def _sin_margen(c):
    inv = [1 / x for x in c]
    s = sum(inv)
    return [x / s for x in inv]


def _matriz(l1, l2, rho=RHO):
    i = np.arange(MAXG)
    p1 = np.exp(-l1) * l1 ** i / np.array([math.factorial(k) for k in i])
    p2 = np.exp(-l2) * l2 ** i / np.array([math.factorial(k) for k in i])
    m = np.outer(p1, p2)
    m[0, 0] *= 1 - l1 * l2 * rho
    m[0, 1] *= 1 + l1 * rho
    m[1, 0] *= 1 + l2 * rho
    m[1, 1] *= 1 - rho
    return m / m.sum()


def _probs(l1, l2, linea):
    m = _matriz(l1, l2)
    i, j = np.indices(m.shape)
    return m[i > j].sum(), m[i == j].sum(), m[i < j].sum(), m[(i + j) > linea].sum()


def lambdas(cuota_1x2, linea_goles=None, cuota_over_under=None):
    """(λ local, λ visitante) que mejor reproducen el 1X2 sin margen y, si hay, el over/under de goles."""
    p1, px, p2 = _sin_margen(cuota_1x2)
    po = _sin_margen(cuota_over_under)[0] if cuota_over_under else None
    linea = linea_goles if linea_goles is not None else 2.5
    mejor, err_min = (1.4, 1.1), 1e9
    # búsqueda en malla gruesa y luego fina alrededor del mejor punto (rápido y sin dependencias)
    def err(l1, l2):
        q1, qx, q2, qo = _probs(l1, l2, linea)
        e = (q1 - p1) ** 2 + (q2 - p2) ** 2 + 0.5 * (qx - px) ** 2
        return e + ((qo - po) ** 2 if po is not None else 0)
    rejas = [(np.arange(0.1, 5.0, 0.05), np.arange(0.1, 5.0, 0.05))]
    for _ in range(2):
        for l1 in rejas[-1][0]:
            for l2 in rejas[-1][1]:
                e = err(l1, l2)
                if e < err_min:
                    err_min, mejor = e, (float(l1), float(l2))
        rejas.append((np.arange(max(0.05, mejor[0] - 0.06), mejor[0] + 0.06, 0.005),
                      np.arange(max(0.05, mejor[1] - 0.06), mejor[1] + 0.06, 0.005)))
    return round(mejor[0], 3), round(mejor[1], 3)


def desde_extracto(extracto):
    """λ desde un extracto de cuotas (Betano o Kambi). None si no hay 1X2."""
    mk = (extracto or {}).get("mercados") or {}
    x12 = mk.get("Resultado del partido")
    if not x12 or len(x12) != 3 or not all(x12):
        return None
    goles = mk.get("TOTAL|Goles totales Más/Menos") or {}
    linea, ou = None, None
    lineas = sorted((float(k), v) for k, v in goles.items() if v and len(v) == 2 and all(v))
    if lineas:
        linea, ou = min(lineas, key=lambda kv: abs(kv[0] - 2.5))
    return lambdas(x12, linea, ou)
