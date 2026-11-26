"""Los 36 equipos de la fase liga de la Champions 2026-27: un código de 3 letras por equipo, igual en FotMob, Kambi,
Betano, The Odds API y la web.

Cada fuente escribe los nombres a su manera ("FC Bayern Munchen", "Bayern München", "Bayern Munich"), así que se
compara el nombre normalizado (sin tildes, minúsculas) contra una lista de alias. Los rivales de otras competiciones
(liga local, copas) que no están aquí reciben las 3 primeras letras, y si eso choca con un código de la Champions
se les antepone "x" para no mezclarlos (p. ej. Bayer Leverkusen → "xBAY", no "BAY" del Bayern).
"""
import unicodedata

# código → (nombre para mostrar, [alias normalizados, de más a menos específico])
EQUIPOS = {
    "ARS": ("Arsenal", ["arsenal"]),
    "BVB": ("Borussia Dortmund", ["borussia dortmund", "dortmund"]),
    "BOD": ("Bodø/Glimt", ["bodo/glimt", "bodo glimt", "bodoglimt", "fk bodo"]),
    "LAS": ("LASK", ["linzer ask", "lask"]),
    "COM": ("Como", ["como 1907", "como"]),
    "AEK": ("AEK Atenas", ["aek athens", "aek atenas", "aek"]),
    "FEY": ("Feyenoord", ["feyenoord"]),
    "POR": ("Porto", ["fc porto", "porto"]),
    "GAL": ("Galatasaray", ["galatasaray"]),
    "AVL": ("Aston Villa", ["aston villa"]),
    "MCI": ("Manchester City", ["manchester city", "man city", "man. city"]),
    "MUN": ("Manchester United", ["manchester united", "man united", "man utd", "man. united"]),
    "NAP": ("Napoli", ["ssc napoli", "napoli"]),
    "RBL": ("RB Leipzig", ["rb leipzig", "leipzig"]),
    "LEN": ("Lens", ["rc lens", "lens"]),
    "RMA": ("Real Madrid", ["real madrid"]),
    "PSV": ("PSV", ["psv eindhoven", "psv"]),
    "SLO": ("Slovan Bratislava", ["slovan bratislava", "slovan"]),
    "BET": ("Real Betis", ["real betis", "betis"]),
    "SAB": ("Sabah", ["fc sabah", "sabah fk", "sabah"]),
    "BAR": ("Barcelona", ["fc barcelona", "barcelona"]),
    "SLA": ("Slavia Praga", ["slavia praha", "slavia prague", "slavia praga", "slavia"]),
    "VIL": ("Villarreal", ["villarreal"]),
    "ATM": ("Atlético de Madrid", ["atletico madrid", "atletico de madrid", "atl. madrid", "atletico"]),
    "VIK": ("Viking", ["viking fk", "viking"]),
    "BRU": ("Club Brugge", ["club brugge", "club bruges", "brugge kv"]),
    "LIV": ("Liverpool", ["liverpool"]),
    "INT": ("Inter", ["inter de milan", "inter milan", "internazionale", "inter"]),
    "VFB": ("Stuttgart", ["vfb stuttgart", "stuttgart"]),
    "LIL": ("Lille", ["lille osc", "lille"]),
    "BAY": ("Bayern Múnich", ["bayern munchen", "bayern munich", "bayern"]),
    "PSG": ("PSG", ["paris saint-germain", "paris saint germain", "paris sg", "psg"]),
    "ROM": ("Roma", ["as roma", "roma"]),
    "SHA": ("Shakhtar", ["shakhtar donetsk", "shakhtar"]),
    "FEN": ("Fenerbahçe", ["fenerbahce"]),
    "SCP": ("Sporting CP", ["sporting cp", "sporting lisbon", "sporting clube de portugal", "sporting"]),
}
# alias que solo valen si el nombre completo es exactamente ese (para no confundir "Inter Miami", "Cercle Brugge"...)
EXACTOS = {"inter", "porto", "roma", "como", "lens", "lille", "sporting", "atletico", "bayern", "slavia", "slovan", "aek",
           "viking", "sabah", "barcelona", "napoli", "psv", "psg", "betis", "leipzig", "stuttgart", "dortmund", "shakhtar"}
# nombres que contienen un alias pero son otro equipo
NO_SON = {"bayer leverkusen", "atletico mineiro", "atletico nacional", "sporting braga", "sporting gijon", "cercle brugge",
          "inter miami", "barcelona sc", "real madrid castilla", "barcelona atletic", "porto b", "atletico madrid b"}


def _norm(s):
    s = (s or "").replace("ø", "o").replace("Ø", "O")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


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
    """Código de 3 letras: el de la Champions si es uno de los 36; si no, 3 letras (con 'x' si chocaría)."""
    c = _buscar(nombre)
    if c:
        return c
    c = "".join(ch for ch in _norm(nombre).upper() if ch.isalpha())[:3] or "XXX"
    return "x" + c if c in EQUIPOS else c


def nombre(cod):
    return EQUIPOS.get(cod, (cod, []))[0]


class Nombres(dict):
    """Se comporta como el dict NOMBRES de la Serie A (nombre → código), pero reconoce cualquier alias.
    Devuelve None para equipos que no son de la Champions."""

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
