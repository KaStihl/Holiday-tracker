"""TIP travel (tiptravel.sk) – MagicWare/CeSYS site whose listing pages are filled client-side from
/search.json (a JS snippet wrapping a JSON object `var response = {...}`). seneca.py reuses this module.

Checked 2026-10-24: robots.txt disallows /objednavka, /tpls/, /partner, /e/, /o/ … but not /search.json; no
terms / text-and-data-mining page is linked from the site. exotika.tiptravel.sk timed out from GitHub runners.
Prices are per person for the default occupancy (2 adults; the endpoint ignored AdultsCount/ChildrenAges),
so the party price is per-person x 3, labelled "orientačne" like satur.py.
On 2026-10-24 TIP had no Jul–Aug 2027 terms yet (site still on "LETO 2026"), so expect 'empty' for a while.
"""

import json
import re

from common import get, norm_board, norm_country, parse_price

NAME = "TIP travel"
HOME = "https://tiptravel.sk"

AIRPORTS = {"BTS": "2", "VIE": "89"}  # AirportID select values (3 = Košice)
STATIONS = {"BA": "BTS", "VI": "VIE", "VIE": "VIE", "KE": "KSC", "BTS": "BTS"}
PAGE_SIZE = 100
MAX_PAGES = 3


def deeplinks(cfg, home=HOME):
    return [
        {"transport": "flight", "label": "Letecky z Bratislavy, pobytové zájazdy",
         "url": f"{home}/zajazdy/?TransportationTypeID=201&AirportID=2"},
        {"transport": "flight", "label": "Letecky z Viedne, pobytové zájazdy",
         "url": f"{home}/zajazdy/?TransportationTypeID=201&AirportID=89"},
        {"transport": "flight", "label": "Cyprus", "url": f"{home}/dovolenka/cyprus/"},
    ]


def parse_response(text):
    """The JSON object inside search.json's JS wrapper -> dict (items, itemsCount)."""
    i = text.find("var response = ")
    if i < 0:
        return {"items": [], "itemsCount": 0}
    obj, _ = json.JSONDecoder().raw_decode(text[i + len("var response = "):])
    return obj


def to_offer(it, home, party, dep=None):
    if it.get("transportationType") != "airplane" or it.get("productType") != "pobytove":
        return None
    pp, orig = parse_price(it.get("price")), parse_price(it.get("price1"))
    days = int(it.get("days") or 0)
    if not pp or not days:
        return None
    img = it.get("imageUrl") or ""
    akcia = orig and orig > pp
    return {
        "hotel": it.get("accommodationName"), "url": it.get("url"),
        "image": home + img if img.startswith("/") else img or None,
        "stars": None, "rating": None,  # 'rating' (1–5) is not documented as stars or reviews, so left out
        "country": it.get("destinationName"), "country_code": norm_country(it.get("destinationName")),
        "region": it.get("destinationName"), "place": it.get("subdestinationName"),
        "board": norm_board(it.get("servicesPlan")), "transport": "flight",
        "departure": STATIONS.get((it.get("departureStation") or "").upper(), dep),
        "date_from": it.get("dateFrom"), "date_to": it.get("dateTo"), "nights": days - 1,
        "price_total": pp * party, "price_original": orig * party if akcia else None,
        "discount_label": "Zľava (cena za os. × 3, orientačne)" if akcia else "Cena za os. × 3 (orientačne)",
        "pets_allowed": None,
    }


def search_site(cfg, home, tag):
    party = cfg["adults"] + len(cfg["children_ages"])
    offers, errors = [], []
    for code in cfg["departures"]:
        if code not in AIRPORTS:
            continue
        for page in range(1, MAX_PAGES + 1):
            q = {"ProductTypeIDs": "401", "DateFrom": f"{cfg['date_from']:%d.%m.%Y}",
                 "DateTo": f"{cfg['date_to']:%d.%m.%Y}", "TransportationTypeID": "201",
                 "AirportID": AIRPORTS[code], "Sort": "n", "Page": page, "PageSize": PAGE_SIZE}
            try:
                resp = parse_response(get(home + "/search.json", params=q))
            except Exception as e:
                print(f"[{tag}] {code} p{page}: {type(e).__name__} {str(e)[:120]}")
                errors.append(f"{type(e).__name__}: {str(e)[:120]}")
                break
            items = resp.get("items") or []
            got = [o for o in (to_offer(it, home, party, code) for it in items) if o]
            print(f"[{tag}] {code} p{page}: {len(items)}/{resp.get('itemsCount')} items, {len(got)} offers")
            offers += got
            if page * PAGE_SIZE >= int(resp.get("itemsCount") or 0):
                break
    if errors and not offers:
        raise RuntimeError(f"all {len(errors)} {home} requests failed, first: {errors[0]}")
    return offers


def search(cfg):
    return search_site(cfg, HOME, "tiptravel")
