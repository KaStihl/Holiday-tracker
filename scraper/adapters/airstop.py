"""Airstop (airstop.sk) – link only: robots.txt disallows its search.

Checked 2026-10-30 from GitHub runners: robots.txt disallows /vyhladavanie (search) and /api, allowing only a
few CMS endpoints (/api/vue/page, /agency, /offer-packages = inspiration tiles, articles, faq, blog). Hotel and
destination pages are server-rendered (Nuxt) but carry only names and an undated 'od … €' teaser; the terms are
loaded client-side from the disallowed /api. The obchodné podmienky have no scraping clause. Airstop's hotel
catalogue does list Sural Saray and Royal Alhambra Palace (Çolaklı/Side) – check them on the site."""

NAME = "Airstop"
HOME = "https://airstop.sk"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "flight", "label": "All inclusive (Airstop, nemecké CK) – vyhľadajte na stránke", "url": "https://airstop.sk/inspiracia/all-inclusive"}]


def search(cfg):
    return []
