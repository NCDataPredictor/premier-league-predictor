# NCDataPredictor · Premier League

Web de la Premier League de NCData Predictor: `docs/premier/` (una sola página HTML + CSS + JS, sin build). El sitio
central (`NCDataPredictor/serieA-predictor`, `scripts/pages_build.sh`) clona este repo en cada build y la publica en
**https://ncdatapredictor.pages.dev/premier/**. La guía de construcción es [`futbol/PREMIER.md`](futbol/PREMIER.md) y el
contexto del proyecto (NBA, lecciones, plan de fútbol) está en [`futbol/CONTEXTO.md`](futbol/CONTEXTO.md).

Base de código: la de la Champions (soñadora, props de The Odds API y de Betano, recuento, apertura de picks, deploy
hook), con la fuerza de equipo de la Serie A (Dixon-Coles con el histórico propio de la liga) y lo propio de la
Champions quitado (peso por competición, columna `ucl`, anclaje de remates al mercado, `equipos_ucl`).

## Flujo

```
futbol/datos/fotmob.py historico | proximos   → futbol/premier/historico/*.json, futbol/premier/partidos/*.json
futbol/datos/kambi.py                         → futbol/premier/cuotas/<id>.json  (Betano desde el PC se respeta)
futbol/datos/oddsapi.py | oddsapi_props.py    → futbol/premier/consenso/*.json, props en partidos/<id>.json
python -m futbol.build_site_futbol premier [FECHA] [--sims N] [--solo-futuros]
                                              → docs/premier/data/index.json, <id>.json, resultados.json, equipos.json
python -m futbol.recuento premier             → docs/premier/data/recuento.json (Rendimiento)
```

Acciones (`.github/workflows/`): `jornada.yml` cada 3 h y ~55 min antes de cada franja de partidos, `recuento.yml` a las
22:30 de Bogotá, `avisos.yml` (tag `premier`) y `ncdata.yml` (deploy hook). Secretos de la organización:
`CF_DEPLOY_HOOK_NCDATA`, `ONESIGNAL_REST_API_KEY`, `ODDS_API_KEY`.

## El modelo (`futbol/modelo/`, versión `futbol-0.2`)

Mismo motor que la Serie A (`futbol-0.1`): contexto por estadística, jugadores, simulación Monte Carlo minuto a minuto
(20.000 sims, semilla fija) y mercados. La Premier cambia dos cosas, las dos medidas con backtest:

1. **Goles anclados al mercado** (`build_site_futbol.lambda_mercado`, `params.PESO_FUERZA_PROPIA = 0,15`). Cuando hay
   1X2 de la casa, los goles esperados de cada equipo son los que reproducen el 1X2 y el más/menos 2,5 sin margen
   (Pinnacle del consenso de The Odds API > consenso de casas > Kambi/Betano), mezclados con un 15% de la fuerza
   propia (media geométrica). Sin cuota se usa `fuerza.py` sola, como en la Serie A. Córners, tarjetas, remates,
   faltas y jugadores siguen saliendo del modelo.
2. **Ajuste de amarillas** (`params.AJUSTE_AMARILLAS = 1,2`). La simulación perdía ~12% de las amarillas que esperaba
   el contexto (el amonestado se cuida, tope de probabilidad por falta, expulsados): ahora la media simulada coincide.

### Backtest (`python -m futbol.backtest_mercado`)

700 partidos de la Premier 2024-25 y 2025-26 (desde la jornada 4), cada uno predicho solo con lo que se sabía antes
(temporada en curso + anterior). Datos de football-data (`futbol/datos/footballdata.py`, temporadas 2019-20 a
2026-27 en `futbol/premier/backtest/footballdata/`) con cuotas de apertura y cierre. No traen xG ni jugadores: la
fuerza propia usa goles (en la web usa 0,6·xG + 0,4·goles de FotMob) y cada equipo lleva 11 jugadores sintéticos.

| | futbol-0.1 (Serie A) | **futbol-0.2 (Premier)** | bet365 apertura | Pinnacle apertura* |
|---|---|---|---|---|
| 1X2 · log loss (menos es mejor) | 1,0037 | **0,9938** | 1,0005 | 0,9833 |
| 1X2 · acierto del favorito | 49,6% | **51,1%** | 51,1% | 53,0% |
| Más de 2,5 goles · log loss | 0,6994 | **0,6837** | 0,6793 | 0,6757 |
| Más de 2,5 goles · acierto | 52,6% | **53,9%** | 55,7% | 56,6% |
| Amarillas · media simulada / real | 3,43 / 3,89 | **3,95 / 3,89** | | |
| Amarillas · reales fuera del p10 / p90 | 8,1% / 15,4% | **11,3% / 10,3%** (objetivo ~10%) | | |
| Amarillas · log loss líneas 3,5 / 4,5 / 5,5 | 0,724 / 0,702 / 0,566 | **0,694 / 0,671 / 0,530** | | |

\* Pinnacle solo en 530 partidos (football-data no lo trae en 2025-26).

Lo que **no** entró (probado y sin mejora): quitarle a los goles la sobredispersión de los remates
(`GAMMA_GOLES = 0`: el 1X2 empata y el favorito acierta menos) y quitar el efecto del marcador en los goles
(`ESTADO_GOLES = 0` o 0,5: empeora el 1X2 porque subestima los empates). El peso de la fuerza propia se eligió con Poisson
sobre los mismos partidos: 0 → 0,9984, **0,15 → 0,9978**, 0,30 → 0,9979, 0,50 → 0,9990, 1 → 1,0067.

Lo que el backtest dice de los picks: en 1X2 y más/menos 2,5 **ni el modelo viejo ni el nuevo le ganan a la casa**
(con la mezcla de la web, `MKT_W = 0,20`, casi no sale ningún pick y con más peso al modelo se pierde), así que esos
mercados se siguen mostrando sin recomendarse. El valor está, como en la Serie A, en líneas de equipo (córners,
tarjetas, remates, faltas) y de jugador, que football-data no trae con cuota: se medirán con los picks "en seco".

Pendiente: las faltas quedan ~4% por debajo de lo real (20,8 frente a 21,8; 11% por encima del p90). En la Serie A, con
jugadores reales, salían por encima: se revisa con el histórico de FotMob antes de tocarlas.

## Datos de ejemplo

`python futbol/premier/ejemplo/generar.py` crea una liga **sintética** para probar la web de punta a punta sin datos
reales (`"ejemplo": true`, franja amarilla en la web). No se sube a git.

## Antes de publicar picks con dinero

1. Primera corrida de `jornada.yml`: confirmar el ID 47 de FotMob, la ruta de Kambi y que salen los 20 equipos
   (`futbol/premier/nube/estado.json`, `docs/premier/data/equipos.json`).
2. `python -m futbol.backtest premier --desde 4` con el histórico de FotMob (xG y jugadores reales).
3. Unas semanas de picks "en seco" y revisión con Nicolas.
4. Logo oficial de la liga (§9.4 de PREMIER.md): el de `docs/premier/logos/premier.png` es un balón genérico provisional.
