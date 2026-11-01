"""Coral Travel (coraltravel.cz) – search links only.

Checked 2026-11-01 from GitHub runners: robots.txt is served and allows everything ("User-agent: * / Allow: /"),
but every other URL – the home page, the hotel pages (e.g. /hotels/turkey/royal-alhambra-palace-side/), the
sitemap.xml and the terms page – answers 200 with Imperva's "Pardon Our Interruption" bot wall (reese84 JavaScript
challenge, meta robots noindex) instead of content. Getting past it would mean running/solving that challenge, which
this project doesn't do (no captcha or bot-wall circumvention), so there is no data to read and the terms could not
be read either. coraltravel.sk does not exist (no DNS record). Coral's packages from Vienna are partly covered by
Ruefa (ruefa.py lists Coral among its tour operators).
"""

from watch import match

NAME = "Coral Travel"
HOME = "https://www.coraltravel.cz"
DEEPLINK_ONLY = True
REASON = "Imperva bot wall (JavaScript challenge) on every page; coraltravel.sk does not exist"
# Watched hotels with a known Coral Travel page (shown under ⭐ Sledované hotely via watch_links()).
HOTEL_PAGES = [("Royal Alhambra Palace", "/hotels/turkey/royal-alhambra-palace-side/")]


def deeplinks(cfg):
    out = [{"transport": "flight", "label": "Coral Travel CZ – vyhľadávanie zájazdov (len odkaz, stránka blokuje roboty)",
            "url": HOME + "/"}]
    return out


def search(cfg):
    return []


def watch_links(cfg, term, hints):
    return [{"label": f"{name} na coraltravel.cz", "url": HOME + path}
            for name, path in HOTEL_PAGES if match(name, [term])]
