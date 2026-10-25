"""Exim Tours – search link only: the Slovak Exim Tours brand is gone.

Checked 2026-10-25 from GitHub runners: every eximtours.sk URL, robots.txt included, answers 301 to the
kartago.sk home page (query dropped). Exim Tours' terms now come from Kartago Tours (DERTOUR SK), so its
offers are delivered by kartago.py; scraping it twice would only duplicate them.
"""

from adapters import dertour

NAME = "Exim Tours"
HOME = "https://www.eximtours.sk"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    d = dertour.deeplinks("https://www.kartago.sk", "/vysledky-vyhladavania", cfg)[0]
    return [dict(d, label="Exim Tours je teraz súčasť Kartago Tours – " + d["label"])]


def search(cfg):
    return []
