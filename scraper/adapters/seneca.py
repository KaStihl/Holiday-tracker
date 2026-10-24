"""Seneca Tours (seneca.sk; hechter.sk redirects here) – search links only.

Same MagicWare backend as TIP travel (identical /search.json catalogue, robots.txt and products, checked
2026-10-24), so scraping it would only duplicate the tiptravel adapter's offers under another name."""

from adapters import tiptravel

NAME = "Seneca Tours (ex Hechter)"
HOME = "https://seneca.sk"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return tiptravel.deeplinks(cfg, HOME)[:2] + [
        {"transport": "flight", "label": "Turecko", "url": HOME + "/dovolenka/turecko/"},
        {"transport": "flight", "label": "Grécko a ostrovy", "url": HOME + "/dovolenka/grecko-a-ostrovy/"},
        {"transport": "flight", "label": "Chorvátsko", "url": HOME + "/dovolenka/chorvatsko/"},
    ]


def search(cfg):
    return []
