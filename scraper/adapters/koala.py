"""CK Koala Tours (koala.sk; ckkoala.sk does not resolve) – TIP travel group, own React SPA by redred.sk.

robots.txt (checked 2026-10-25) disallows every search filter on koala.sk (/*?date=*, /*?destinationId=*,
*&transportationId=*, *&query=*, *&stars=*, …) plus /objednavka, /partner, /e/, /o/, /tpls/; it allows everything
else. The pages are a JS shell (search.json and /dovolenka/<x>/<hotel> return the same 6–9 KB HTML), so the
filter URLs are not needed at all: the SPA loads the WHOLE catalogue (destinations -> hotels -> terms, ~100 KB)
from one file, https://koala.redred.sk/json/encoded/tree.json, and filters it in the browser. That host has no
robots.txt (404 = no restrictions) and no terms page; we fetch the file once per run (1 request + robots.txt).

The file is key-compressed: decode_tree() re-implements the site's decode_json (index.js module 8153): every
field name from the site's dictionary is replaced by a short key; keys are generated from the de-duplicated
names sorted with Slovak collation ('ch' sorts after 'h') -> a, b, c, …
A term ("terms") is a room variant with occupancy limits (room.adultCount, room.personCount, room.childAge =
[min, max] age of a child bed) and a price per person; the party price is per-person x party size ("orientačne", like
satur.py) because child discounts are only computed in the booking form under /objednavka (robots-disallowed).
"""

import json
from datetime import date

from common import get, norm_board, norm_country
from config import approx_label, approx_note, party_size

NAME = "Koala Tours"
HOME = "https://koala.sk"
TREE_URL = "https://koala.redred.sk/json/encoded/tree.json"

# index.js module 1220 (order irrelevant, duplicates removed)
FIELDS = ["address", "branches", "email", "hours", "id", "latitude", "longitude", "name", "phoneNumber", "sellers",
          "category", "destinations", "hotels", "isActive", "level", "parentId", "url", "equipment", "photoId",
          "starCount", "terms", "type", "videoId", "adultCount", "childAge", "code", "date", "dayCount", "discount",
          "personCount", "price", "room", "roomCount", "service", "serviceId", "transportation",
          "transportationFrom", "transportationFromId", "transportationId"]
_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ$_0123456789"
CATEGORY_SEASIDE = 401  # 542 = poznávacie, 663 = púte, 10000 = exotika (other site)
TRANSPORT = {201: "flight", 202: "car"}  # 199 = bus
AIRPORTS = {"bratislav": "BTS", "viede": "VIE", "vieden": "VIE", "wien": "VIE", "kosic": "KSC", "košic": "KSC",
            "budap": "BUD"}


def _key(i):
    """index.js module 5946: 0 -> 'a', 53 -> '_', 54 -> 'ab', …"""
    base, out = 54, ""
    i += 1
    while i > 0:
        i -= 1
        out += _ALPHABET[i % base]
        i //= base
        base = 64
    return out


def _sk_sort_key(name):
    # Slovak collation for these ASCII camelCase names: case-insensitive, 'ch' is one letter between 'h' and 'i'
    return name.lower().replace("ch", "h\x7f")


def dictionary():
    names = sorted(set(FIELDS), key=_sk_sort_key)
    return {_key(i): n for i, n in enumerate(names)}


def decode_tree(obj, keys=None):
    keys = keys or dictionary()
    if isinstance(obj, list):
        return [decode_tree(x, keys) for x in obj]
    if isinstance(obj, dict):
        return {keys.get(k, k): decode_tree(v, keys) for k, v in obj.items()}
    return obj


def parse_tree(text):
    """tree.json text -> list of decoded top-level destinations."""
    raw = json.loads(text)
    return decode_tree(raw.get("encoded") or [])


def iter_hotels(dests, path=()):
    """(hotel, [destination names from top level down], top-level url) for every hotel in the tree."""
    for d in dests:
        p = path + ((d.get("name"), d.get("url")),)
        for h in d.get("hotels") or []:
            yield h, [n for n, _ in p], p[0][1]
        yield from iter_hotels(d.get("destinations") or [], p)


def _ymd(n):
    s = str(n)
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def deeplinks(cfg):
    return [
        {"transport": "flight", "label": "Koala Tours – pobytové zájazdy pri mori", "url": HOME + "/more"},
        {"transport": "flight", "label": "Koala Tours – Turecko", "url": HOME + "/dovolenka/turecko"},
        {"transport": "flight", "label": "Koala Tours – Grécko a ostrovy", "url": HOME + "/dovolenka/grecko-a-ostrovy"},
    ]


def fits(term, cfg):
    """Can this room variant take the configured party at all? Mirrors the site's own filters."""
    room = term.get("room") or {}
    party = party_size(cfg)
    adults, persons = room.get("adultCount") or 0, room.get("personCount") or 0
    if persons and persons < party:
        return False
    if adults and adults < cfg["adults"]:
        return False
    return True


def to_offer(hotel, names, top_url, term, cfg):
    if hotel.get("category") != CATEGORY_SEASIDE or hotel.get("type") == "bez ubytovania":
        return None
    transport = TRANSPORT.get(term.get("transportationId"))
    if not transport or not term.get("price") or not term.get("date"):
        return None
    if not fits(term, cfg):
        return None
    party = party_size(cfg)
    d1, d2 = _ymd(term["date"][0]), _ymd(term["date"][1])
    pp = int(term["price"])
    # The site shows "Cena za osobu" = price and, next to it, "zľava N%" (only when N < 50). Whether price is
    # before or after that discount is not stated, so no original price is derived from it.
    disc = term.get("discount") or 0
    disc = disc if 0 < disc < 50 else None
    frm = str(term.get("transportationFrom") or "").lower()
    dep = next((c for k, c in AIRPORTS.items() if k in frm), None) if transport == "flight" else None
    country = names[0] if names else None
    photo = hotel.get("photoId")
    return {
        "hotel": hotel.get("name"),
        "url": f"{HOME}/dovolenka/{top_url}/{hotel.get('url')}",
        "image": f"{HOME}/FileHandler.ashx?FileID={photo}&FormatID=19" if photo else None,
        "stars": hotel.get("starCount") or None, "rating": None,
        "country": country, "country_code": norm_country(country) or norm_country(" ".join(names)),
        "region": names[1] if len(names) > 1 else None, "place": names[-1] if len(names) > 2 else None,
        "board": norm_board(term.get("service")), "transport": transport, "departure": dep,
        "date_from": d1.isoformat(), "date_to": d2.isoformat(),
        "nights": (term.get("dayCount") or ((d2 - d1).days + 1)) - 1,
        "price_total": pp * party, "price_original": None, "discount_pct": disc,
        "discount_label": approx_label(cfg, f"Zľava {disc} %" if disc else None),
        "price_note": approx_note(cfg, basis=None),
        "pets_allowed": None,
    }


def offers_from_tree(dests, cfg):
    out = []
    for hotel, names, top in iter_hotels(dests):
        for term in hotel.get("terms") or []:
            o = to_offer(hotel, names, top, term, cfg)
            if o:
                out.append(o)
    return out


def search(cfg):
    dests = parse_tree(get(TREE_URL))
    hotels = list(iter_hotels(dests))
    terms = [t for h, _, _ in hotels for t in h.get("terms") or []]
    offers = offers_from_tree(dests, cfg)
    summer = [o for o in offers if cfg["date_from"].isoformat() <= o["date_from"] <= cfg["date_to"].isoformat()]
    span = sorted(str(t["date"][0]) for t in terms if t.get("date"))
    print(f"[koala] tree.json: {len(hotels)} hotels, {len(terms)} terms ({span[0] if span else '-'}…"
          f"{span[-1] if span else '-'}), {len(offers)} seaside offers, {len(summer)} in Jul–Aug {cfg['date_from'].year}")
    return offers
