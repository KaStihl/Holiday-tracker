"""Exim Tours – dates and prices are rendered by JavaScript, so only search links for a human."""

from urllib.parse import urlencode

NAME = "Exim Tours"
HOME = "https://www.eximtours.sk"
DEEPLINK_ONLY = True

AIRPORTS = "483|3789"  # Bratislava + Vienna ids of the Fischer/Kartago/Exim platform (seen on fischer.sk)


def deeplinks(cfg):
    nights = "|".join(str(n) for n in range(cfg["nights_min"], cfg["nights_max"] + 1))
    q = {"tt": 1, "to": AIRPORTS, "dd": cfg["date_from"].isoformat(), "rd": cfg["date_to"].isoformat(),
         "nn": nights, "ac1": cfg["adults"], "kc1": len(cfg["children_ages"]), "m": 5}
    label = f"Letecky z Bratislavy/Viedne, AI, júl–aug, {cfg['nights_min']}–{cfg['nights_max']} nocí, 1+2"
    return [{"transport": "flight", "label": label + " (vek detí doplniť)",
             "url": f"{HOME}/vysledky-vyhledavani?{urlencode(q)}"}]


def search(cfg):
    return []
