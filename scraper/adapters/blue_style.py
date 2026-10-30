"""Blue Style – Czech departures only (PRG/BRQ/OSR/PED), so only a search link for a human."""

from urllib.parse import urlencode

from config import period_label

NAME = "Blue Style"
HOME = "https://www.blue-style.cz"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    q = {"dateFrom": cfg["date_from"].isoformat(), "dateTo": cfg["date_to"].isoformat(), "priceType": "total"}
    return [{"transport": "flight", "label": f"Letecky z Brna/Prahy, {period_label(cfg)} (len české letiská)",
             "url": f"{HOME}/vyhledavani/?{urlencode(q)}"}]


def search(cfg):
    return []
