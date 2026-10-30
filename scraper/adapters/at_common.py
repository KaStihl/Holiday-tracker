"""Helpers shared by the Austrian (German-language) adapters billa_reisen.py and ruefa.py: country, board and
airport names as they appear on the cards. Not an adapter itself (not listed in adapters/__init__.py)."""

from common import norm_board, norm_country, strip_accents

# German country names (accent-free, lower case) -> ISO code
GERMAN = {
    "turkei": "TR", "griechenland": "GR", "spanien": "ES", "zypern": "CY", "italien": "IT", "kroatien": "HR",
    "malta": "MT", "portugal": "PT", "montenegro": "ME", "albanien": "AL", "bulgarien": "BG", "agypten": "EG",
    "tunesien": "TN", "marokko": "MA", "kenia": "KE", "tansania": "TZ", "vereinigte arabische emirate": "AE",
    "oman": "OM", "jordanien": "JO", "malediven": "MV", "mauritius": "MU", "seychellen": "SC", "sri lanka": "LK",
    "thailand": "TH", "indonesien": "ID", "vietnam": "VN", "dominikanische republik": "DO", "mexiko": "MX",
    "kuba": "CU", "kap verde": "CV", "kapverden": "CV", "kapverdische inseln": "CV",
}
AIRPORTS = {"wien": "VIE", "bratislava": "BTS", "budapest": "BUD", "graz": "GRZ", "linz": "LNZ", "salzburg": "SZG",
            "innsbruck": "INN", "klagenfurt": "KLU", "munchen": "MUC", "kosice": "KSC"}


def country(name):
    """'Türkei' (or the first part of 'Türkei • Riviera' / 'Türkei/Riviera/Side') -> 'TR', else None."""
    if not name:
        return None
    first = strip_accents(name.replace("•", "/").split("/")[0]).strip().lower()
    return GERMAN.get(first) or norm_country(first)


def board(text):
    t = strip_accents(text or "").lower()
    if "ultra" in t:
        return "UAI"
    if "inklusive" in t or "inclusive" in t:
        return "AI"
    if "vollpension" in t:
        return "FB"
    if "halbpension" in t:
        return "HB"
    if "fruhstuck" in t:
        return "BB"
    if "ohne verpflegung" in t or "nur ubernachtung" in t or "selbstverpflegung" in t:
        return "RO"
    return norm_board(text)


def airport(text):
    """IATA code of the first known city name in 'ab Wien' / 'ab/bis Wien'."""
    t = strip_accents(text or "").lower()
    return next((code for k, code in AIRPORTS.items() if k in t), None)
