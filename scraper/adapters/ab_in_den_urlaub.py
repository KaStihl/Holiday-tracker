"""ab-in-den-urlaub.at (Invia group) – link only: bot wall.

Checked 2026-10-30 from GitHub runners: every URL, robots.txt included, answers 403 from CloudFront to our
honest user agent, so nothing can be read without circumventing the block (which we don't)."""

NAME = "ab-in-den-urlaub.at"
HOME = "https://www.ab-in-den-urlaub.at"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "flight", "label": "Pauschalreisen (Invia/Unister) – vyhľadajte na stránke", "url": "https://www.ab-in-den-urlaub.at/"}]


def search(cfg):
    return []
