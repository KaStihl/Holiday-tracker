"""Invia.sk – aggregator of ~100 tour operators. Search links only.

Not scraped, on purpose:
  * invia.sk publishes an express rights-holder reservation (www.invia.sk/vytazovanie-textov-a-dat/,
    Art. 4(3) of EU directive 2019/790) forbidding downloading/storing its content with crawlers, bots or
    web scraping without prior written consent;
  * robots.txt disallows every search filter (nl_*, d_start_from, d_end_to, sort, page=) and the
    /direct/tour_hotel/ term-picker JSON (which answers 403 to non-browser clients anyway);
  * the allowed landing pages only show one term per hotel for 2 adults (checked 2026-10-24: 1 of 90 cards
    fell into Jul–Aug 2027).
So the page gets ready-made filtered searches for a human to click.
"""

from urllib.parse import urlencode

NAME = "Invia.sk"
HOME = "https://www.invia.sk"
DEEPLINK_ONLY = True

AIRPORTS = {"BTS": "3_5", "VIE": "3_6"}  # invia.sk nl_transportation_id
MEALS = ["5", "11"]  # 5 = All Inclusive, 11 = Ultra All Inclusive


def _fmt(d):
    return d.strftime("%d.%m.%Y")


def deeplinks(cfg):
    base = {
        "d_start_from": _fmt(cfg["date_from"]), "d_end_to": _fmt(cfg["date_to"]),
        "nl_length_from": cfg["nights_min"] + 1, "nl_length_to": cfg["nights_max"] + 1,  # invia counts days
        "nl_occupancy_adults": cfg["adults"], "nl_occupancy_children": len(cfg["children_ages"]),
        "sort": "c_price", "sort_order": "asc",
    }
    ages = [("nl_ages_children[]", a) for a in cfg["children_ages"]]
    meals = [("nl_meal_id[]", m) for m in MEALS]
    n = f"{cfg['nights_min']}–{cfg['nights_max']} nocí"
    out = []
    for code, label in (("BTS", "z Bratislavy"), ("VIE", "z Viedne")):
        q = urlencode(list(base.items()) + [("nl_transportation_id[]", AIRPORTS[code])] + meals + ages)
        out.append({"transport": "flight", "label": f"Letecky {label}, AI/UAI, júl–aug, {n}, 1+2",
                    "url": f"{HOME}/dovolenka/?{q}"})
    out.append({"transport": "car", "label": "Vlastná doprava (psy overiť v detaile hotela)",
                "url": f"{HOME}/dovolenka/vlastna-doprava/"})
    return out


def search(cfg):
    return []
