"""Urlaubsguru (urlaubsguru.at) – link only: a deal blog, not a tour operator.

Checked 2026-10-30: robots.txt disallows /search/ and /reise-schnaeppchen/; deals are editorial articles and the
package search runs on a separate partner booking engine (buchen.urlaubsguru.at, GraphQL on holidayguru.de).
Deals are hand-picked snapshots, not a searchable inventory for our dates/party, so a link is the useful part."""

NAME = "Urlaubsguru.at"
HOME = "https://www.urlaubsguru.at"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "flight", "label": "Deals a Pauschalreisen – vyhľadajte na stránke", "url": "https://www.urlaubsguru.at/pauschalreisen/"}]


def search(cfg):
    return []
