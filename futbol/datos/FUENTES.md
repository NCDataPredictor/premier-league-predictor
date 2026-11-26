# Fuentes de datos de fútbol (probadas el 22-nov-2026)

Desde la nube (Claude) todas las webs de fútbol dan 403 del proxy. Desde el PC de Nicolas
(`C:\Users\Usuario 1\Documents\NCDataPredictor`):

| Fuente | Estado | Para qué |
|---|---|---|
| **FotMob** `/api/data/leagues?id=55[&season=2025%2F2026]`, `/api/data/matchDetails?matchId=` | ✅ Principal (`fotmob.py`) | Estadísticas de equipo total y por tiempo (posesión, remates, a puerta, córners, fueras de lugar, amarillas, rojas, faltas, pases, xG), por jugador (minutos, remates, a puerta, faltas cometidas/recibidas, pases precisos), árbitro con promedios (ojo: a veces de la Serie B), eventos con minuto, shotmap (x 0-105, y 0-68, situación, xG), bajas con regreso previsto. La ruta vieja `/api/...` da 404. |
| **365Scores** `webws.365scores.com/web/...` (competitions=17) | ✅ Respaldo (pendiente) | Casi lo mismo; además riesgo de sanción por amarillas. Valores como texto ("49%", "49/52 (94%)"). |
| **ESPN** scoreboard / summary | ✅ (pendiente) | El *commentary* trae córners, fueras de lugar y faltas **con minuto** (FotMob y 365Scores solo por tiempo): mejora la distribución por tramos de esas tres estadísticas. |
| **Fantacalcio** probabili formazioni (HTML) | ✅ (pendiente) | XI probable con % de titularidad, dudas, sancionados, apercibidos. Nombres abreviados: hay que cruzarlos con FotMob. |
| **Transfermarkt** lesionados (HTML) | ✅ | Lesiones. |
| **Open-Meteo** | ✅ | Clima (el de FotMob puede ser el del momento de la consulta). |
| Sofascore | ❌ 403 (protección antibots; no se evade) | |
| football-data.co.uk | ❌ bloqueado por la operadora (Coljuegos) | Sería la base de cuotas de cierre para el backtest: probar con otra red. |
| Understat | ❌ en mantenimiento | |
| FBref | ❌ 403 de Cloudflare | |
| ClubElo | ❌ caído ese día | |

Pendiente de verificar con datos reales: qué lado es y=0 en el shotmap de FotMob (`INVERTIR_Y` en `fotmob.py`;
se comprueba con los remates de un extremo izquierdo conocido) y cómo marca FotMob una alineación probable.

## Premier League (26-nov-2026)

| Fuente | Nube de Claude | Notas |
|---|---|---|
| FotMob `leagues?id=47` | ❌ 403 del proxy | ID 47 sin verificar: la primera corrida de `jornada.yml` en Actions lo confirma (ver `futbol/premier/nube/estado.json`). |
| Kambi `football/england/premier_league` | ❌ 403 | Si la ruta no existe, `kambi._ruta_liga()` la busca en el árbol de grupos. |
| The Odds API `soccer_epl` | sin probar (clave en Actions) | Props con casas `uk`. |
| Fantasy Premier League `bootstrap-static` | ❌ 403 | Pendiente: estado de lesión y % de jugar (`chance_of_playing_next_round`). |
| football-data.co.uk `E0.csv` | ❌ 403 | Las temporadas 2019-20 a 2025-26 (con cuotas de apertura y cierre) se bajaron de copias públicas en GitHub para el backtest (`futbol/datos/footballdata.py`). |
