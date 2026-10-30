"""GRUBER-reisen (gruberreisen.at; www.gruber-reisen.at doesn't resolve) – link only: bot wall.

Checked 2026-10-30 from GitHub runners: the WordPress site is open (robots.txt only blocks MJ12bot and a plugin),
but the package booking engine buchung.gruberreisen.at answers with an Imperva/Incapsula challenge
('Request unsuccessful. Incapsula incident ID'). No circumvention."""

NAME = "GRUBER-reisen"
HOME = "https://www.gruberreisen.at"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "flight", "label": "Pauschalreisen (Gruber, Graz) – vyhľadajte na stránke", "url": "https://www.gruberreisen.at/"}]


def search(cfg):
    return []
