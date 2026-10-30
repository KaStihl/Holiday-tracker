"""Fischer (fischer.sk) – offers from the JSON search API the results page itself calls; see dertour.py.

Exact prices for the party from nastavenia.yml. Only FISCHER's own products (dataSource 256,
ATCOM_Fischer); the rest of the shared DERTOUR inventory comes through kartago.py.
History: until 2026-10-25 search links only, because the HTML pages fill terms and prices client-side.
"""

from adapters import dertour

NAME = "Fischer"
HOME = "https://www.fischer.sk"
PATH = "/vysledky-vyhledavani"


def deeplinks(cfg):
    return dertour.deeplinks(HOME, PATH, cfg)


def search(cfg):
    return dertour.search("fischer", HOME, cfg, fischer=True)
