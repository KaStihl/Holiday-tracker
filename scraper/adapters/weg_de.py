"""weg.de (Invia group; no separate Austrian site) – link only: bot wall.

Checked 2026-10-30 from GitHub runners: robots.txt and every page answer 403 with a Cloudflare challenge page
(challenge-platform). No circumvention."""

NAME = "weg.de"
HOME = "https://www.weg.de"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "flight", "label": "Pauschalreisen (weg.de, odlety aj z Viedne) – vyhľadajte na stránke", "url": "https://www.weg.de/"}]


def search(cfg):
    return []
