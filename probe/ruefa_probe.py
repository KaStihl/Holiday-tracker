"""Ruefa (ruefa.at, Verkehrsbüro group, Austria's largest travel agency chain) – packages of all tour operators
it sells (TUI, DERTOUR, Coral, SLR/Schauinsland, Bye bye, …) from Vienna and Bratislava, exact prices for the party.

Checked 2026-10-30 from GitHub runners:
- The package search lives on pauschal.ruefa.at; its robots.txt answers 404 (= no restrictions), www.ruefa.at's
  robots.txt is "Allow: /". No bot wall (Apache, plain 200); captcha.eu only guards the e-mail/contact forms.
- Terms (/informationen/reisebedingungen, /ueber-uns/impressum): no text-and-data-mining reservation, no
  scraping ban.
- The results page (index.php?page=results) is an empty shell; it fills itself by POSTing its search config to
  /hub/ajax/deliver.php, which answers JSON {resultCount, value: <10 hotel cards as HTML>, …}. We call that same
  endpoint with the same form fields, 10 hotels per call (page=N), cheapest first (sort=price).
- Fields: adults, children = child ages joined by "-" (e.g. "10-12"; the card links echo children=12-10 and the
  price changes, so every card is priced for exactly the configured party: data-price = "Gesamtpreis"),
  start/until travel window, airport "VIE-BTS", verpflegung "AI AIP AIU AIR" (all-inclusive codes), destinationId
  (space-separated region ids of a country from /hub/ajax/getDestination.php?destination=<German name>), dauer =
  ONE stay length as a bit (2**nights: 128 = 7 nights, 1024 = 10, 16384 = 14; sums of bits are not understood,
  they fall back to 1–2 night stays), level=2 (hotel list).
"""

import re
from datetime import date, datetime
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

import at_common
from common import get, parse_price
from config import period_label

NAME = "Ruefa"
HOME = "https://www.ruefa.at"
IBE = "https://pauschal.ruefa.at"
AIRPORTS = "VIE-BTS"
AI_CODES = "AI AIP AIU AIR"
MAX_CALLS = 55
# German country names used by the destination lookup, per country code of nastavenia.yml
COUNTRY_NAMES = {
    "HR": "Kroatien", "TR": "Türkei", "CY": "Zypern", "IT": "Italien", "GR": "Griechenland", "ES": "Spanien",
    "MT": "Malta", "PT": "Portugal", "ME": "Montenegro", "AL": "Albanien", "BG": "Bulgarien", "EG": "Ägypten",
    "TN": "Tunesien", "MA": "Marokko", "CV": "Kap Verde", "TZ": "Tansania", "KE": "Kenia",
    "AE": "Vereinigte Arabische Emirate", "OM": "Oman", "JO": "Jordanien", "MV": "Malediven", "MU": "Mauritius",
    "SC": "Seychellen", "LK": "Sri Lanka", "TH": "Thailand", "ID": "Indonesien", "VN": "Vietnam",
    "DO": "Dominikanische Republik", "MX": "Mexiko", "CU": "Kuba",
}
# Destination ids per country (from getDestination.php, 2026-10-30). A country missing here is looked up at run
# time (one extra request).
DEST_IDS = {}


def ai_only(cfg):
    return set(cfg["boards_preferred"]) <= {"AI", "UAI"}


def stays(cfg):
    """Stay lengths asked (one per request, see module docstring): 7, 10 and 14 nights clipped to the settings."""
    want = [n for n in (7, 10, 14) if cfg["nights_min"] <= n <= cfg["nights_max"]]
    return want or [cfg["nights_min"]]


def children(cfg):
    return "-".join(str(a) for a in cfg["children_ages"])


def form(cfg, dest_id, nights, page=1):
    """The POST fields the results page itself sends to deliver.php."""
    return {"adults": str(cfg["adults"]), "children": children(cfg), "start": cfg["date_from"].isoformat(),
            "until": cfg["date_to"].isoformat(), "hotelSearchtext": "", "level": "2", "page": str(page), "topGid": "",
            "destinationName": "", "airport": AIRPORTS, "recommendationrate": "", "dauer": str(2 ** nights),
            "anzZimmer": "1", "sort": "price", "airline": "", "maxPrice": "", "minPrice": "", "citycodes": "",
            "destination_groups": "", "excludeNbc": "1", "destination": "", "destinationId": dest_id,
            "verpflegung": AI_CODES if ai_only(cfg) else ""}


def deeplinks(cfg):
    q = {"page": "results", "level": "1", "adults": cfg["adults"], "start": cfg["date_from"].isoformat(),
         "until": cfg["date_to"].isoformat(), "anzZimmer": 1, "airport": AIRPORTS, "dauer": 2 ** stays(cfg)[0]}
    if cfg["children_ages"]:
        q["children"] = children(cfg)
    if ai_only(cfg):
        q["verpflegung"] = AI_CODES
    return [{"transport": "flight",
             "label": f"Letecky z Viedne/Bratislavy{', AI' if ai_only(cfg) else ''}, {period_label(cfg)}, "
                      f"{stays(cfg)[0]} nocí, všetky cestovky (dĺžku a cieľ si zmeňte na stránke)",
             "url": f"{IBE}/index.php?{urlencode(q)}"}]


def _txt(el):
    return " ".join(el.get_text(" ").split()) if el else ""


def parse(data, cfg):
    """Offers from one deliver.php JSON answer."""
    soup = BeautifulSoup((data or {}).get("value") or "", "lxml")
    ages = sorted(cfg["children_ages"])
    out = []
    for card in soup.select("div.card-hotel[data-href]"):
        href = card["data-href"]
        q = parse_qs(urlsplit(href).query)
        try:
            total = float(card.get("data-price"))
            nights = int(card.get("data-nights"))
            start = datetime.fromisoformat(card.get("data-startdate")).date()
        except (TypeError, ValueError):
            continue
        name_el = card.select_one(".hotel-name")
        if name_el:
            for s in name_el.select(".sternbox"):
                s.decompose()
        name = _txt(name_el)
        if not name:
            continue
        kids = sorted(int(x) for x in (q.get("children") or [""])[0].split("-") if x.isdigit())
        if (q.get("adults") or [""])[0] != str(cfg["adults"]) or kids != ages:
            continue  # priced for another party (never seen): no per-person split we could trust
        region = _txt(card.select_one(".region")).split("/")
        strike = card.select_one(".discountPrice .linethrough")
        orig = parse_price(_txt(strike)) if strike else None
        try:
            rating = round(float(card.get("data-rating")) * 10 / 6, 1)
        except (TypeError, ValueError):
            rating = None
        try:
            stars = float(card.get("data-stars")) or None
        except (TypeError, ValueError):
            stars = None
        dep = at_common.airport(_txt(card.select_one(".startDate")).split("ab/bis")[-1]) or \
            {"VIE": "VIE", "BTS": "BTS"}.get((q.get("abflughafen") or [""])[0])
        out.append({
            "hotel": name, "url": f"{IBE}/{href.lstrip('/')}", "image": None, "stars": stars, "rating": rating,
            "country": region[0] if region else None, "country_code": at_common.country(region[0]) if region else None,
            "region": region[1] if len(region) > 1 else None, "place": region[2] if len(region) > 2 else None,
            "board": at_common.board(_txt(card.select_one(".board"))), "transport": "flight", "departure": dep,
            "date_from": start.isoformat(), "date_to": date.fromordinal(start.toordinal() + nights).isoformat(),
            "nights": nights, "price_total": round(total),
            "price_original": orig if orig and orig > total else None,
            "discount_label": None, "pets_allowed": None, "price_exact": True,
        })
    return out


def lookup(name):
    """Space-separated destination ids of a country, or None."""
    res = get(IBE + "/hub/ajax/getDestination.php", params={"destination": name}, as_json=True,
              headers={"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/"})
    for x in res or []:
        if x.get("country") and x.get("name") == name and str(x.get("id") or "").strip():
            return str(x["id"]).strip()
    return None


def plan(cfg):
    """[(code, nights, page)]: every configured country once at the shortest stay, then the longer stays and a
    second page for the favourites (weight >= 0.9)."""
    codes = [c for c, w in sorted(cfg["countries"].items(), key=lambda kv: -kv[1]) if c in COUNTRY_NAMES]
    fav = [c for c in codes if cfg["countries"][c] >= 0.9]
    st = stays(cfg)
    out = [(c, st[0], 1) for c in codes]
    out += [(c, n, 1) for n in st[1:] for c in fav]
    out += [(c, st[0], 2) for c in fav]
    return out


def search(cfg):
    if "flight" not in cfg["transports"]:
        return []
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/index.php?page=results"}
    ids, offers, calls, errors, empty = dict(DEST_IDS), [], 0, [], set()
    for code, nights, page in plan(cfg):
        if calls >= MAX_CALLS:
            print(f"[ruefa] call budget {MAX_CALLS} reached")
            break
        if code in empty:
            continue
        try:
            if code not in ids:
                calls += 1
                ids[code] = lookup(COUNTRY_NAMES[code])
                if not ids[code]:
                    print(f"[ruefa] {code}: no destination id for {COUNTRY_NAMES[code]}")
                    empty.add(code)
                    continue
            calls += 1
            data = get(IBE + "/hub/ajax/deliver.php", method="POST", data=form(cfg, ids[code], nights, page),
                       headers=hdr, as_json=True)
        except Exception as e:
            print(f"[ruefa] {code} {nights}n p{page}: {type(e).__name__} {str(e)[:120]}")
            errors.append(f"{type(e).__name__}: {str(e)[:120]}")
            if "403" in str(e) or "429" in str(e):
                raise
            continue
        got = parse(data, cfg)
        mine = [o for o in got if o["country_code"] == code]
        prices = sorted(o["price_total"] for o in mine)
        print(f"[ruefa] {code} {nights}n p{page}: {data.get('resultCount')} results, {len(got)} cards, {len(mine)} in "
              f"{code} ({sum(bool(o.get('price_exact')) for o in mine)} exact), price "
              f"{prices[0] if prices else '-'}–{prices[-1] if prices else '-'}")
        if not mine and page == 1:
            empty.add(code)  # the country isn't sold for these criteria (or its ids changed): don't ask again
        offers += mine  # cards of neighbouring countries leak into a country's list; they come with their own query
    print(f"[ruefa] {calls} requests, {len(offers)} offers; ids: {ids}")
    if errors and not offers:
        raise RuntimeError(f"all {len(errors)} Ruefa requests failed, first: {errors[0]}")
    return offers
