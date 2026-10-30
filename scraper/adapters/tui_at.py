"""TUI Austria (tui.at) – link only: the terms forbid automated collection.

Checked 2026-10-30: robots.txt is just 'Allow: /', but /nutzungsbedingungen/ says it is expressly forbidden to
collect, compare, extract or reuse data/content of the TUI web sites (booking mask and prices included)
automatically for public or commercial purposes, 'insbesondere … durch den Einsatz von Robots, Spidern', and
also to show their data/prices on other sites through interlinks, deep links or frames. The site also runs
Akamai Bot Manager (bm_s/bm_so cookies). So no scraping and only a link to the generic package page."""

NAME = "TUI.at"
HOME = "https://www.tui.at"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "flight", "label": "Pauschalreisen z Viedne – vyhľadajte na stránke (TUI zakazuje automatický zber)", "url": "https://www.tui.at/pauschalreisen/"}]


def search(cfg):
    return []
