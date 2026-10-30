"""CHECK24 Austria (urlaub.check24.at) – link only: robots.txt and the terms forbid it.

Checked 2026-10-30: robots.txt disallows /suche/, /offer/, /region/ (the result pages) for every agent, and the
AGB section 11 'Nutzung der Inhalte und automatisierte Zugriffe' forbids reading the site by bots, crawlers or
scraping tools and declares a text-and-data-mining reservation (§ 44b Abs. 3 UrhG / Art. 4(3) DSM directive)."""

NAME = "CHECK24.at"
HOME = "https://urlaub.check24.at"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "flight", "label": "Pauschalreisen (porovnávač) – vyhľadajte na stránke", "url": "https://urlaub.check24.at/"}]


def search(cfg):
    return []
