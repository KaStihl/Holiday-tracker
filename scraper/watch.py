"""Watched hotels ("sledovane_hotely" in nastavenia.yml): name normalisation and matching.

A watch term matches an offer when the normalised hotel name contains the normalised term at a word start:
accents and case are ignored and filler words (hotel, resort, spa, &, …) are dropped on both sides, so
"Sural Resort" matches "Hotel Süral Hotel" and "Sural Saray", and "alhambra" matches "Alhambra Beach Hotel".
Matching offers get offer["watched"] = <term as written in nastavenia.yml> and are kept even above price_cap
(up to WATCH_CAP_FACTOR × price_cap), flagged over_cap, so the user always sees what the watched hotel costs.
"""

import re
import unicodedata

WATCH_CAP_FACTOR = 2
STOPWORDS = {"hotel", "hotels", "hotely", "otel", "hoteli", "resort", "resorts", "spa", "and", "the", "a", "&"}
_EXTRA = str.maketrans({"ı": "i", "ß": "ss", "ø": "o", "æ": "ae", "đ": "d", "ł": "l", "œ": "oe"})


def norm_name(s):
    """'Hotel Süral Resort & Spa' -> 'sural'; 'Sural Saray' -> 'sural saray'."""
    t = unicodedata.normalize("NFKD", str(s or "").lower().translate(_EXTRA))
    t = "".join(c for c in t if not unicodedata.combining(c))
    words = re.findall(r"[a-z0-9]+", t.replace("&", " & "))
    return " ".join(w for w in words if w not in STOPWORDS)


def split_term(term):
    """'Long Beach Resort @TR' -> ('Long Beach Resort', 'TR'); a term without '@XX' has no country limit."""
    m = re.fullmatch(r"(.*?)\s*@\s*([A-Za-z]{2})", str(term or "").strip())
    return (m.group(1), m.group(2).upper()) if m else (str(term or "").strip(), None)


def match(hotel, terms, country=None):
    """The first watch term (as written) whose normalised form occurs in the hotel name at a word start.
    A term limited to a country ('… @TR') only matches when `country` is that code; callers that don't know
    the country (adapters' watch lookups) pass None and get name-only matching – run.py re-checks with it."""
    name = " " + norm_name(hotel)
    for term in terms or ():
        base, cc = split_term(term)
        n = norm_name(base)
        if n and (" " + n) in name and not (cc and country is not None and country != cc):
            return term
    return None


def keep_limit(cfg):
    """Highest price a watched offer may have and still be kept."""
    return cfg["price_cap"] * WATCH_CAP_FACTOR
