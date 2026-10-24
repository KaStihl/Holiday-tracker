"""Blue Style – Czech departures only (PRG/BRQ/OSR/PED), so only a search link for a human."""

from urllib.parse import urlencode

NAME = "Blue Style"
HOME = "https://www.blue-style.cz"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    q = {"dateFrom": cfg["date_from"].isoformat(), "dateTo": cfg["date_to"].isoformat(), "priceType": "total"}
    return [{"transport": "flight", "label": "Letecky z Brna/Prahy, júl–aug (len české letiská)",
             "url": f"{HOME}/vyhledavani/?{urlencode(q)}"}]


def search(cfg):
    return []
