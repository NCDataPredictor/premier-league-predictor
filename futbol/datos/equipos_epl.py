"""Equipos de la Premier League: un código de 3 letras por equipo, igual en FotMob, Kambi, Betano, The Odds API,
football-data y la web.

Cada fuente escribe los nombres a su manera ("Man City", "Manchester City FC", "Nott'm Forest", "Brighton & Hove
Albion"), así que se compara el nombre normalizado (sin tildes, minúsculas, sin "FC"/"AFC" ni "&") contra una lista
de alias. Además de los 20 de la temporada están los que estuvieron en la Premier desde 2019-20 (histórico y
backtest) y los candidatos a ascender desde la Championship. Un equipo que no está aquí recibe las 3 primeras letras,
y si eso choca con un código de la Premier se le antepone "x" para no mezclarlos.
"""
import unicodedata

# código → (nombre para mostrar, [alias normalizados, de más a menos específico])
# Ojo con los choques: Manchester City/United, Newcastle/Nottingham, West Ham/West Brom/Wolves, Sheffield Utd/Wed.
EQUIPOS = {
    "ARS": ("Arsenal", ["arsenal"]),
    "AVL": ("Aston Villa", ["aston villa", "villa"]),
    "BOU": ("Bournemouth", ["afc bournemouth", "bournemouth"]),
    "BRE": ("Brentford", ["brentford"]),
    "BHA": ("Brighton", ["brighton and hove albion", "brighton hove albion", "brighton hove", "brighton"]),
    "BUR": ("Burnley", ["burnley"]),
    "CHE": ("Chelsea", ["chelsea"]),
    "CRY": ("Crystal Palace", ["crystal palace", "palace"]),
    "EVE": ("Everton", ["everton"]),
    "FUL": ("Fulham", ["fulham"]),
    "LEE": ("Leeds United", ["leeds united", "leeds utd", "leeds"]),
    "LIV": ("Liverpool", ["liverpool"]),
    "MCI": ("Manchester City", ["manchester city", "man city", "man. city", "mancity"]),
    "MUN": ("Manchester United", ["manchester united", "manchester utd", "man united", "man utd", "man. united", "man. utd"]),
    "NEW": ("Newcastle", ["newcastle united", "newcastle utd", "newcastle"]),
    "NFO": ("Nottingham Forest", ["nottingham forest", "nott'm forest", "nottm forest", "nott forest", "nottingham", "forest"]),
    "SUN": ("Sunderland", ["sunderland"]),
    "TOT": ("Tottenham", ["tottenham hotspur", "tottenham", "spurs"]),
    "WHU": ("West Ham", ["west ham united", "west ham utd", "west ham"]),
    "WOL": ("Wolves", ["wolverhampton wanderers", "wolverhampton", "wolves"]),
    # ascendidos 2026-27 y equipos de temporadas anteriores (histórico y backtest)
    "HUL": ("Hull City", ["hull city", "hull"]),
    "IPS": ("Ipswich", ["ipswich town", "ipswich"]),
    "COV": ("Coventry", ["coventry city", "coventry"]),
    "MID": ("Middlesbrough", ["middlesbrough", "boro"]),
    "LEI": ("Leicester", ["leicester city", "leicester"]),
    "SOU": ("Southampton", ["southampton"]),
    "LUT": ("Luton", ["luton town", "luton"]),
    "SHU": ("Sheffield United", ["sheffield united", "sheffield utd", "sheff utd"]),
    "NOR": ("Norwich", ["norwich city", "norwich"]),
    "WAT": ("Watford", ["watford"]),
    "WBA": ("West Brom", ["west bromwich albion", "west bromwich", "west brom"]),
    "MIL": ("Millwall", ["millwall"]),
    "STK": ("Stoke", ["stoke city", "stoke"]),
    "SWA": ("Swansea", ["swansea city", "swansea"]),
    "BLA": ("Blackburn", ["blackburn rovers", "blackburn"]),
    "BRC": ("Bristol City", ["bristol city"]),
    "DER": ("Derby", ["derby county", "derby"]),
    "PRE": ("Preston", ["preston north end", "preston"]),
    "QPR": ("QPR", ["queens park rangers", "qpr"]),
    "SHW": ("Sheffield Wednesday", ["sheffield wednesday", "sheff wed"]),
    "WRX": ("Wrexham", ["wrexham"]),
    "POR": ("Portsmouth", ["portsmouth"]),
    "CAR": ("Cardiff", ["cardiff city", "cardiff"]),
}
# alias que solo valen si el nombre completo es exactamente ese (para no confundir con otros clubes)
EXACTOS = {"villa", "palace", "forest", "nottingham", "spurs", "leeds", "boro", "derby", "hull", "stoke", "preston", "swansea",
           "coventry", "cardiff", "portsmouth", "wolves", "brighton", "chelsea", "liverpool", "everton", "arsenal"}
# nombres que contienen un alias pero son otro equipo
NO_SON = {"liverpool fc women", "arsenal women", "chelsea women", "manchester city women", "manchester united women",
          "tottenham hotspur women", "everton women", "aston villa women", "brighton women",
          "arsenal de sarandi", "everton de vina del mar", "liverpool montevideo", "wolfsburg"}


def _norm(s):
    s = (s or "").replace("ø", "o").replace("Ø", "O").replace("&", " and ")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace("’", "'")
    s = " ".join(w for w in s.replace(".", ". ").split() if w not in ("fc", "afc", "f.c.", "a.f.c."))
    return s.replace(" and ", " and ").strip()



def _buscar(nombre):
    n = _norm(nombre)
    if not n or n in NO_SON:
        return None
    for cod, (_, alias) in EQUIPOS.items():
        for a in alias:
            if n == a:
                return cod
    for cod, (_, alias) in EQUIPOS.items():
        for a in alias:
            if a not in EXACTOS and a in n:
                return cod
    return None


def codigo(nombre):
    """Código de 3 letras: el de la tabla si es un equipo conocido de la Premier; si no, 3 letras (con 'x' si chocaría)."""
    c = _buscar(nombre)
    if c:
        return c
    c = "".join(ch for ch in _norm(nombre).upper() if ch.isalpha())[:3] or "XXX"
    return "x" + c if c in EQUIPOS else c


def nombre(cod):
    return EQUIPOS.get(cod, (cod, []))[0]


class Nombres(dict):
    """Se comporta como el dict NOMBRES de la Serie A (nombre → código), pero reconoce cualquier alias.
    Devuelve None para equipos que no están en la tabla."""

    def __init__(self):
        super().__init__({v[0]: k for k, v in EQUIPOS.items()})

    def get(self, k, default=None):
        return _buscar(k) or default

    def __getitem__(self, k):
        c = _buscar(k)
        if c is None:
            raise KeyError(k)
        return c

    def __contains__(self, k):
        return _buscar(k) is not None
