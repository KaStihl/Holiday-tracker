"""HOFER REISEN (hofer-reisen.at, ALDI Süd Austria; Peakwork backend) – link only: its search API is disallowed.

Checked 2026-10-30 from GitHub runners: robots.txt disallows /api/ (and member area, checkout); the search
results are loaded client-side from that /api/. The server-rendered destination pages only carry 10–20 teaser
products ('z.B. 2 Erwachsene … 1 Nacht') and ignore every search parameter we tried (s_dr/s_du/s_px/s_ap and the
p_* variants returned the byte-identical page), so they can't be turned into offers for our dates and party.
Terms (/at/service/reisebedingungen, /impressum) have no scraping clause; there is simply no allowed data path."""

NAME = "HOFER REISEN"
HOME = "https://www.hofer-reisen.at"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "flight", "label": "Pauschalreisen z Viedne (Hofer) – vyhľadajte na stránke", "url": "https://www.hofer-reisen.at/at/destination"}]


def search(cfg):
    return []
