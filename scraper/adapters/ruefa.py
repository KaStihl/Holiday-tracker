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
  is empty and the region ids go to 'destination' (the page's own JS does suchConfig.destination =
  destinationId; space-separated ids of a country from /hub/ajax/getDestination.php?destination=<German name>;
  ids sent as destinationId are ignored -> worldwide list, a country *name* in destination -> 0 results), dauer =
  ONE stay length as a bit (2**nights: 128 = 7 nights, 1024 = 10, 16384 = 14; sums of bits are not understood,
  they fall back to 1–2 night stays), level=2 (hotel list).
"""

import re
from datetime import date, datetime
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

from adapters import at_common
from common import get, parse_price
from config import period_label

NAME = "Ruefa"
HOME = "https://www.ruefa.at"
IBE = "https://pauschal.ruefa.at"
AIRPORTS = "VIE-BTS"
AI_CODES = "AI AIP AIU AIR"
MAX_CALLS = 60
# German country names used by the destination lookup, per country code of nastavenia.yml
COUNTRY_NAMES = {
    "HR": "Kroatien", "TR": "Türkei", "CY": "Zypern", "IT": "Italien", "GR": "Griechenland", "ES": "Spanien",
    "MT": "Malta", "PT": "Portugal", "ME": "Montenegro", "AL": "Albanien", "BG": "Bulgarien", "EG": "Ägypten",
    "TN": "Tunesien", "MA": "Marokko", "CV": "Kap Verde", "TZ": "Tansania", "KE": "Kenia",
    "AE": "Vereinigte Arabische Emirate", "OM": "Oman", "JO": "Jordanien", "MV": "Malediven", "MU": "Mauritius",
    "SC": "Seychellen", "LK": "Sri Lanka", "TH": "Thailand", "ID": "Indonesien", "VN": "Vietnam",
    "DO": "Dominikanische Republik", "MX": "Mexiko", "CU": "Kuba",
}
# other names tried by the run-time lookup (the plain name found nothing on 2026-10-30)
ALT_NAMES = {"AE": ["Arabische Emirate", "Dubai"], "DO": ["Dominikanische Rep.", "Dominikanische"],
             "LK": ["Sri"], "CV": ["Kapverden", "Kapverdische Inseln", "Kap Verde Inseln"]}
# Region ids per country as getDestination.php?destination=<name> listed them on 2026-10-30. A country missing
# here (or whose ids stop matching: first page without a card of that country) is looked up at run time.
DEST_IDS = {
    "HR": "1562 1418 1326 1108 90 1635 1561 1386 1325 698 1634 1560 1327 1109 659",
    "TR": "1670 1650 1444 724 149 144 1669 1645 1309 559 148 1668 1446 960 292 147",
    "CY": "713 163 637 632",
    "IT": "436 433 85 82 79 1099 76 1047 1040 1035 1005 614 438 435 300 84 81 78 1097 1045 1039 1034 947 580 437 434 283 83 80 77 1074 1041 1036 1007 712 440",
    "GR": "42 259 38 71 35 68 1435 32 65 1401 28 62 1323 25 59 1134 56 1017 53 965 50 962 47 916 44 829 41 258 37 70 34 67 1431 31 64 1390 27 61 1322 58 1131 55 993 52 964 49 924 46 833 43 745 39 165 36 69 1711 33 66 1429 30 63 1324 26 60 1232 57 1118 54 967 51 963 48 917 45 832",
    "ES": "707 591 134 1135 131 935 128 877 125 850 740 737 734 730 720 704 290 1504 133 957 130 923 127 857 805 739 736 733 729 708 655 135 1315 132 956 129 922 126 851 741 738 735 731 726",
    "MT": "101 716 715",
    "PT": "1301 653 112 109 1428 1300 652 111 1335 725 326 110",
    "ME": "1052",
    "AL": "918",
    "BG": "1537 1534 1531 743 14 1536 1533 1530 178 1538 1535 1532 1239 15",
    "EG": "1031 1028 561 1680 1030 651 1032 1029 562",
    "TN": "1542 1539 819 153 150 1541 1507 633 152 1540 1038 154 151",
    "MA": "1286 102 1285 1519 1284",
    "TZ": "1643 643 138 1642 642 1644 1641 641",
    "OM": "108 612",
    "MV": "1153 1150 1147 1144 1141 100 1518 1348 1155 1152 1149 1146 1143 1140 1381 1157 1154 1151 1148 1145 1142 1139 1380 1156",
    "MU": "1114 746 603 104 869 699 594 1520 864 681 593",
    "TH": "1654 934 927 742 139 1506 932 926 141 1119 929 908 140",
    "MX": "1566 1563 1355 1288 1116 106 1565 1459 1349 1287 1027 1567 1564 1394 1289 1117 1026",
    "KE": "640 269 639 638",
    "JO": "1279 87 1278 1559 1277",
    "SC": "1420 116 1422 1419 1421 709",
    "ID": "1403 1087 1084 1080 995 72 1712 1552 1436 1402 1086 1083 1079 912 1648 1505 1404 1398 1085 1081 1078 910 1553 1437",
    "VN": "323",
    "CU": "1667 1128 92 1399 1127 1129 1126",
}


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
            "destination_groups": "", "excludeNbc": "1", "destination": dest_id, "destinationId": "",
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


def lookup(code):
    """(space-separated region ids of a country or None, requests made) via getDestination.php, the search form's
    own autocomplete."""
    n = 0
    for name in [COUNTRY_NAMES[code]] + ALT_NAMES.get(code, []):
        n += 1
        res = get(IBE + "/hub/ajax/getDestination.php", params={"destination": name}, as_json=True,
                  headers={"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/"})
        for x in res or []:
            ids = str(x.get("id") or "").strip()
            if x.get("country") and ids and at_common.country(re.sub(r"<[^>]+>", "", x.get("name") or "")) == code:
                return ids, n
    return None, n


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
                ids[code], n = lookup(code)
                calls += n
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
