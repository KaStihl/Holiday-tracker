"""Lidl Reisen Austria (lidl-reisen.at, Traffics-based) – link only.

Checked 2026-10-30: robots.txt gives every generic user agent 'Allow: /' AND 'Disallow: /' (only Googlebot and
Bingbot get real rules). Under RFC 9309 the tie would go to Allow, but the evident intent is to keep generic
crawlers out, so we stay out. Results come from a GraphQL API on another host (search-api-mvp2prod.lidl-reisen.de)
that rejects requests without a site-specific 'application-domain' header; the AGB contain no scraping clause.
Lidl Reisen AT mostly resells the same tour operators that Ruefa and BILLA Reisen already cover."""

NAME = "Lidl Reisen"
HOME = "https://www.lidl-reisen.at"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "flight", "label": "Pauschalreisen (Lidl Reisen AT) – vyhľadajte na stránke", "url": "https://www.lidl-reisen.at/pauschalreisen"}]


def search(cfg):
    return []
