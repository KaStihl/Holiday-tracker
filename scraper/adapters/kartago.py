"""Kartago Tours (kartago.sk) – offers from the JSON search API the results page itself calls; see dertour.py.

Exact prices for the party from nastavenia.yml. Kartago and Fischer share one inventory: this adapter
keeps every product that is not FISCHER's own (KARTAGO, DERTOUR, …), fischer.py keeps the FISCHER ones.
History: until 2026-10-25 search links only, because the HTML pages fill terms and prices client-side.
"""

from adapters import dertour

NAME = "Kartago Tours"
HOME = "https://www.kartago.sk"
PATH = "/vysledky-vyhladavania"


def deeplinks(cfg):
    return dertour.deeplinks(HOME, PATH, cfg)


def search(cfg):
    return dertour.search("kartago", HOME, cfg, fischer=False)
