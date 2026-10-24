"""SOREA (sorea.sk) – search links only.

Not a sea-holiday operator: it is a chain of Slovak hotels (Tatry, Nízke Tatry, Ľubovňa, Bratislava), so it
has nothing for the flight or Croatia/Italy-by-car tracks. Its /pravne-informacie/ also says the site's
materials may only be used with SOREA's prior written consent (checked 2026-10-24), so it is not scraped."""

NAME = "SOREA"
HOME = "https://www.sorea.sk"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "car", "label": "Hotely SOREA na Slovensku (vlastná doprava, nie pri mori)", "url": HOME + "/"}]


def search(cfg):
    return []
