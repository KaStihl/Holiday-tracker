"""Kartago Tours – search links only (needs JavaScript).

Checked 2026-10-24 from GitHub runners: robots.txt allows everything and the terms carry no TDM reservation,
but /vysledky-vyhladavania, /first-minute/* and hotel pages fill terms and prices client-side (DER Touristik
JS app). Country pages (/turecko, 14 MB) only hold a hidden SEO teaser – one term per hotel, mostly Prague
departures in Oct–Jan – and ignore all query parameters, so there is nothing for Jul–Aug 2027 to parse.
"""

from urllib.parse import urlencode

NAME = "Kartago Tours"
HOME = "https://www.kartago.sk"
DEEPLINK_ONLY = True

# TO= airport ids, read off kartago.sk/fischer.sk links on 2026-10-24 (483 next to "Bratislava", 3789 "Viedeň")
AIRPORTS = {"BTS": ("483", "z Bratislavy"), "VIE": ("3789", "z Viedne")}


def deeplinks(cfg):
    out = []
    for code, (to, label) in AIRPORTS.items():
        q = {"DS": 0, "TT": 1, "TO": to, "DD": cfg["date_from"].isoformat(), "RD": cfg["date_to"].isoformat(),
             "NN": cfg["nights_min"], "MNN": cfg["nights_min"], "NNM": cfg["nights_max"], "MT": 5,
             "AC1": cfg["adults"], "KC1": len(cfg["children_ages"]), "IC1": 0, "PF": 0, "PT": cfg["price_cap"]}
        out.append({"transport": "flight",
                    "label": f"Letecky {label}, AI, júl–aug, {cfg['nights_min']}–{cfg['nights_max']} nocí, 1+2",
                    "url": f"{HOME}/vysledky-vyhladavania?{urlencode(q)}"})
    return out


def search(cfg):
    return []
