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
- Brno: airport=BRQ answers resultCount 0 (2026-11-01; "VIE-BTS-BRQ" gives the same cards as VIE-BTS), Ruefa sells
  no packages from Brno, so BRQ from departures_secondary is not asked.

Watched hotels (watch() hook, checked 2026-10-30 from GitHub runners):
- The search form's autocomplete getDestination.php?destination=<text> also lists hotels: {"field": "hotelname",
  "name": "Sural Resort<span …> Türkische Riviera, Colakli, Türkei</span>", "id": 53099}; the id is the GIATA id the
  cards carry (data-giataid="53099p") and the results page's gid parameter.
- deliver.php with gid=<ids> (space- or comma-separated) and an empty destination lists just those hotels, one card
  per hotel = its cheapest term in start..until for the dauer asked, priced for the party like any other card.
  A gid without offers answers resultCount 0 *plus* 10 unrelated fallback cards, so cards are kept only when their
  giataid is one of the asked gids. hotelSearchtext=<name> filters too, but by text; the ids are exact.
"""

import json
import random
import re
import string
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

from adapters import at_common
from common import facilities, get, parse_price, strip_accents
from config import continent, period_label

NAME = "Ruefa"
HOME = "https://www.ruefa.at"
IBE = "https://pauschal.ruefa.at"
AIRPORTS = "VIE-BTS"
AI_CODES = "AI AIP AIU AIR"
MAX_CALLS = 60
EXTRA_CALLS = 5  # per extra party (skupiny): see search_party()
_IDS = {}  # region ids per country, filled by search() (incl. run-time lookups), reused by search_party()
_WATCH_GIDS = []  # hotel ids of the watched hotels found by watch(), reused by search_party()
WATCH_CALLS = 10  # extra requests of the watch() hook: id lookups + deliver.php calls
# Hotel ids the autocomplete gave on 2026-10-30, used only when the run-time lookup fails or finds nothing
# (keys: normalised watch terms, see watch.norm_name). Sural Saray (4924) had no offer for 1+2 in Jul–Aug 2027.
WATCH_GIDS = {"sural": ["53099", "4924", "4923", "4922"], "royal alhambra": ["239871"]}
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
            **({"fac": ["fr"]} if facilities(_txt(card.select_one(".room")), ("fr",)) else {}),
            **({"gid": gid} if (gid := re.sub(r"\D", "", card.get("data-giataid") or "")) and
               at_common.country(region[0] if region else "") == "TR" else {}),
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
    """[(code, dauer nights, page)]: every configured country once at the shortest stay, then the longer stays and a
    second page for the favourites (weight >= 0.9). dauer counts travel nights including an overnight flight: for
    Maldives/Thailand/… dauer=7 gives 6 hotel nights (checked 2026-10-30), so outside Europe one night is added."""
    codes = [c for c, w in sorted(cfg["countries"].items(), key=lambda kv: -kv[1]) if c in COUNTRY_NAMES]
    fav = [c for c in codes if cfg["countries"][c] >= 0.9]
    st = stays(cfg)
    extra = {c: 0 if continent(c) == "Európa" else 1 for c in codes}
    out = [(c, st[0] + extra[c], 1) for c in codes]
    out += [(c, n + extra[c], 1) for n in st[1:] for c in fav]
    out += [(c, st[0] + extra[c], 2) for c in fav]
    return out


def search(cfg):
    if "flight" not in cfg["transports"]:
        return []
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/index.php?page=results"}
    ids, offers, calls, errors, empty = _IDS, [], 0, [], set()
    ids.clear()
    ids.update(DEST_IDS)
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


def watch_lookup(term):
    """[(gid, hotel name)] of the hotels the autocomplete lists for a watch term (only names the term matches)."""
    from watch import match, split_term
    res = get(IBE + "/hub/ajax/getDestination.php", params={"destination": split_term(term)[0]}, as_json=True,
              headers={"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/"})
    out = []
    for x in res if isinstance(res, list) else []:
        name = re.sub(r"<span.*", "", x.get("name") or "", flags=re.S)
        name = re.sub(r"<[^>]+>", "", name).strip()
        gid = str(x.get("id") or "").strip()
        if x.get("field") == "hotelname" and gid.isdigit() and match(name, [term]):
            out.append((gid, name))
    return out


def watch_windows(cfg):
    """[(start, until)]: departures in the first and in the second half of the travel window (until = latest
    return, so the first half may return later), each answered with the cheapest term per hotel."""
    a, b = cfg["date_from"], cfg["date_to"]
    mid = date.fromordinal((a.toordinal() + b.toordinal()) // 2)
    if (b - a).days < 14:
        return [(a, b)]
    return [(a, date.fromordinal(mid.toordinal() + cfg["nights_max"] + 1)),
            (date.fromordinal(mid.toordinal() + 1), b)]


def watch_form(cfg, gids, nights, start, until):
    f = form(cfg, "", nights)
    f.update({"gid": " ".join(gids), "verpflegung": "", "start": start.isoformat(), "until": until.isoformat()})
    return f


def watch_parse(data, cfg, gids):
    """Offers of the asked hotels only (a gid without offers comes back with unrelated fallback cards)."""
    if not data or not int(data.get("resultCount") or 0):
        return []
    soup = BeautifulSoup(data.get("value") or "", "lxml")
    ok = {c["data-href"].lstrip("/") for c in soup.select("div.card-hotel[data-href]")
          if re.sub(r"\D", "", c.get("data-giataid") or "") in gids}
    return [o for o in parse(data, cfg) if o["url"].split(IBE + "/", 1)[-1] in ok]


def watch(cfg, terms, hints=None):
    """run.py hook: the watched hotels' cheapest terms per stay length (7/10/14 nights) and half of the travel
    window, any board, for the configured party, looked up by hotel id (≤ WATCH_CALLS requests)."""
    from watch import norm_name
    if "flight" not in cfg["transports"] or not terms:
        return []
    calls, gids = 0, {}
    for t in terms:
        try:
            found = watch_lookup(t)
        except Exception as e:
            print(f"[ruefa] watch lookup {t!r}: {type(e).__name__} {str(e)[:120]}")
            found = []
        calls += 1
        ids = [g for g, _ in found] or WATCH_GIDS.get(norm_name(t), [])
        print(f"[ruefa] watch {t!r}: " + (", ".join(f"{n} ({g})" for g, n in found) or
                                          f"autocomplete found nothing, cached ids {ids}"))
        for g in ids:
            gids.setdefault(g, t)
    _WATCH_GIDS[:] = list(gids)
    if not gids:
        return []
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/index.php?page=results"}
    asked = list(gids)
    offers = []
    for nights in stays(cfg):
        for start, until in watch_windows(cfg):
            if calls >= WATCH_CALLS:
                print(f"[ruefa] watch: call budget {WATCH_CALLS} reached")
                return offers
            calls += 1
            try:
                data = get(IBE + "/hub/ajax/deliver.php", method="POST", headers=hdr, as_json=True,
                           data=watch_form(cfg, asked, nights, start, until))
            except Exception as e:
                print(f"[ruefa] watch {nights}n {start}: {type(e).__name__} {str(e)[:120]}")
                if "403" in str(e) or "429" in str(e):
                    break
                continue
            got = watch_parse(data, cfg, set(asked))
            print(f"[ruefa] watch {nights}n {start}..{until}: {data.get('resultCount')} results, {len(got)} watched: "
                  + ", ".join(f"{o['hotel']} {o['date_from']} {o['price_total']}" for o in got))
            offers += got
    return offers


# --- extra parties (skupiny in nastavenia.yml) -------------------------------------------------------------------
# Cards are priced for the party in the form (adults/children), so another party needs its own requests. Cheap
# pass reusing the primary run: page 1 (10 cheapest hotels, shortest stay) of the countries with primary offers,
# best preference weight first, plus one gid call for the watched hotels found by watch(); ≤ EXTRA_CALLS per party
# (2 extra parties: ≤ 10 requests on top of the ≤ 70 of search() + watch()).

def search_party(cfg, primary):
    """run.py hook for an extra party: exact prices for cfg's party."""
    from collections import Counter
    if "flight" not in cfg["transports"] or not primary:
        return []
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/index.php?page=results"}
    ids = {**DEST_IDS, **{k: v for k, v in _IDS.items() if v}}
    have = Counter(o.get("country_code") for o in primary if not o.get("watched"))
    codes = sorted((c for c in have if c in ids and c in cfg["countries"]),
                   key=lambda c: (-cfg["countries"][c], -have[c]))
    budget = EXTRA_CALLS - (1 if _WATCH_GIDS else 0)
    offers = []
    for code in codes[:budget]:
        nights = stays(cfg)[0] + (0 if continent(code) == "Európa" else 1)
        try:
            data = get(IBE + "/hub/ajax/deliver.php", method="POST", data=form(cfg, ids[code], nights), headers=hdr,
                       as_json=True)
        except Exception as e:
            print(f"[ruefa] party {code}: {type(e).__name__} {str(e)[:120]}")
            if "403" in str(e) or "429" in str(e):
                return offers
            continue
        mine = [o for o in parse(data, cfg) if o["country_code"] == code]
        print(f"[ruefa] party {cfg['adults']}+{len(cfg['children_ages'])} {code} {nights}n: "
              f"{data.get('resultCount')} results, {len(mine)} in {code}")
        offers += mine
    if _WATCH_GIDS:
        try:
            data = get(IBE + "/hub/ajax/deliver.php", method="POST", headers=hdr, as_json=True,
                       data=watch_form(cfg, _WATCH_GIDS, stays(cfg)[0], cfg["date_from"], cfg["date_to"]))
            got = watch_parse(data, cfg, set(_WATCH_GIDS))
            print(f"[ruefa] party {cfg['adults']}+{len(cfg['children_ages'])} watched: {len(got)}: "
                  + ", ".join(f"{o['hotel']} {o['price_total']}" for o in got))
            offers += got
        except Exception as e:
            print(f"[ruefa] party watch: {type(e).__name__} {str(e)[:120]}")
    return offers


# --- hotel attributes for the Side tab (side.py) -------------------------------------------------------------------
# The results page filters by hotel attributes (checked 2026-11-06 from a runner): checkboxes globalTypebox /
# zimmerbox whose codes the page sends to deliver.php as globalType=<codes> / zimmer=<codes> (search.min.js lists
# both among the search parameters). Asked together with gid=<the hotels' GIATA ids>, the answer lists only the asked
# hotels that have the attribute (and an offer for the party/term). A baseline call without the filter shows which
# hotels answer at all; if a filter returns every baseline hotel it was evidently ignored and is discarded.
ATTR_FILTERS = {"aq": ("globalType", "GT03-WASL"), "fr": ("zimmer", "ST04-FA"), "pl": ("globalType", "GT03-DIBE#ST03-DIRE")}
ATTR_CALLS = 16
ATTR_PAGE = 10  # cards per deliver.php answer


def side_attributes(cfg, gids, max_calls=ATTR_CALLS):
    """{gid: [codes]} for the given GIATA ids (Side hotels Ruefa sells), ≤ max_calls requests; codes as in
    common.facilities (aq water slide, fr family room, pl directly on the beach)."""
    gids = [g for g in dict.fromkeys(str(g) for g in gids if str(g).isdigit())]
    if not gids:
        return {}
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/index.php?page=results"}
    calls, found = 0, {}

    def ask(field=None, code=None):
        nonlocal calls
        got = set()
        for i in range(0, len(gids), ATTR_PAGE):
            if calls >= max_calls:
                return got, False
            chunk = gids[i:i + ATTR_PAGE]
            f = watch_form(cfg, chunk, stays(cfg)[0], cfg["date_from"], cfg["date_to"])
            if field:
                f[field] = code
            calls += 1
            try:
                data = get(IBE + "/hub/ajax/deliver.php", method="POST", headers=hdr, as_json=True, data=f)
            except Exception as e:
                print(f"[ruefa] side attributes {code or 'baseline'}: {type(e).__name__} {str(e)[:120]}")
                return got, False
            if int((data or {}).get("resultCount") or 0):
                soup = BeautifulSoup(data.get("value") or "", "lxml")
                got |= {re.sub(r"\D", "", c.get("data-giataid") or "") for c in soup.select("div.card-hotel")} & set(chunk)
        return got, True

    base, ok = ask()
    print(f"[ruefa] side attributes: {len(gids)} hotels asked, {len(base)} answer without a filter")
    if not ok or not base:
        return {}
    for fac, (field, code) in ATTR_FILTERS.items():
        got, ok = ask(field, code)
        if not ok:
            break
        if got and got >= base and len(base) > 2:
            print(f"[ruefa] side attributes {code}: all {len(got)} hotels -> filter ignored, discarded")
            continue
        print(f"[ruefa] side attributes {code} ({fac}): {len(got)} of {len(base)} hotels")
        for g in got:
            found.setdefault(g, []).append(fac)
    return {g: sorted(v) for g, v in found.items()}


# --- offer verification (run.py verify hook) -----------------------------------------------------------------------
# The cards' data-price is a cached "from" price (the cheapest the tour operators' feeds listed). What Ruefa itself
# does when an offer is opened (checked 2026-11-15 from a runner; js/min/ajaxLoadDetails.min.js):
# 1. The hotel page (index.php?page=hotel&…) builds a `conf` object from its URL parameters (start, until, adults,
#    children, dauer, abflughafen, ankunftshafen, veranstalter = rva, reisetag, rq, gid, cabinClass, …) and POSTs it
#    to /hub/ajax/additionalOffersHotelpage.php (conf=JSON, price, data, debug). The answer is HTML (~3.7 MB for
#    Royal Alhambra Palace, 1+2, 7 nights): one .additionalOfferContainer per room type with .hotel-offer rows
#    (data-offer = "dep*ret*…*outFlight*retFlight*roomCode***boardCode*roomTypes****1*bu*TOC", data-rva = tour
#    operator, b.detailHl = the operator's room name, .board/.transfer, .additionalButton[data-price] = listed total).
# 2. justCheckPrice() – run automatically for the first row and for every row whose "Verfügbarkeit prüfen" button
#    is clicked – POSTs conf (veranstalter = the row's rva) + data = data-offer + a random bid + isHotelPriceCheck=1 to
#    /hub/ajax/checkPrice.php. The answer is tags: <preis>N</preis> (live total for the party, 0 = not bookable),
#    <pPPreis>, <originalPrice>, <preisText>, optionally <error>. The page shows "JETZT BUCHEN" when error is empty
#    and preis > 0, else "Angebot nicht verfügbar". An <error> mentioning "Lücke"/"Leerzeitraum" is re-asked once
#    with recheck=1. Nothing is booked: the booking page (index.php?page=book&bid=…) is only opened on a click.
# The PHP session cookie the first request sets is needed (without it every check answered preis 0); the hotel page
# itself is not. So one offer costs 1 list request + 1 check per room/flight option tried, cheapest first.
# First result (2026-11-15, Royal Alhambra Palace, 1 adult + kids 10/12, 1.–8. 7. 2027, from VIE): listed 3 596 €
# (TUI, Double Superior) -> preis 0; TUI lateral sea view 3 706 € -> 0; TUI from BTS 3 707 € -> 0; ITS "Alhambra
# Suite", AI ohne Transfer, listed 3 725 € -> bookable at 3 692 €.
VERIFY_CALLS = 25   # requests per run for verification (list + checks)
VERIFY_CHECKS = 4   # checkPrice calls per offer at most (cheapest options first)
_AI_BOARD_CODES = ("GT06-AI", "GT06-UAI", "GT06-AIP", "GT06-AIU", "GT06-AIR")


def verify_conf(offer):
    """The hotel page's conf object, from the offer URL (same keys the page script sets)."""
    q = {k: v[0] for k, v in parse_qs(urlsplit(offer["url"]).query).items()}
    nights = int(offer.get("nights") or 7)
    return {"start": q.get("start", offer["date_from"]), "until": q.get("until", offer.get("date_to") or ""),
            "adults": q.get("adults", ""), "children": q.get("children", ""), "destinationName": "",
            "destinationId": "", "airline": "", "dauer": str(2 ** nights), "abflughafen": q.get("abflughafen", "VIE BTS"),
            "ankunftshafen": q.get("ankunftshafen", ""), "preis": "", "stars": "", "bewertung": "", "name": "",
            "veranstalter": q.get("rva", ""), "reisetag": q.get("reisetag", offer["date_from"]), "verpflegung": "",
            "room": "", "rq": q.get("rq", "1"), "gid": q.get("gid", ""), "hotelOnly": "", "nonStop": "", "stops": "",
            "transfer": "", "baggageincluded": "", "sort": "price", "depApt": "", "dstApt": "", "rfId": "",
            "offset": "", "dstOutMax": "", "dstOutMin": "", "depOutMax": "", "depOutMin": "",
            "cabinClass": q.get("cabinClass", "economy")}


def parse_options(html):
    """Bookable-candidate rows of additionalOffersHotelpage.php: [{price, data, rva, toc, room, board, transfer,
    dep, start, end, board_code, group}] sorted by listed price."""
    soup = BeautifulSoup(html or "", "lxml")
    out = []
    for c in soup.select(".additionalOfferContainer"):
        h5 = c.select_one("h5")
        if h5:
            for s in h5.select("span"):
                s.decompose()
        kind = _txt(h5)
        for o in c.select(".hotel-offer[data-offer]"):
            btn = o.select_one(".additionalButton[data-price]")
            try:
                price = float(btn["data-price"]) if btn else float(o.get("data-price"))
            except (TypeError, ValueError):
                continue
            f = o["data-offer"].split("*")
            if len(f) < 9 or price <= 0:
                continue
            room = _txt(o.select_one("b.detailHl")) or kind
            out.append({"price": round(price), "data": o["data-offer"], "rva": o.get("data-rva") or "",
                        "toc": o.get("data-rvaname") or "", "room": room, "kind": kind,
                        "board": _txt(o.select_one(".board")), "transfer": _txt(o.select_one(".transfer")),
                        "dep": f[3][:3], "start": f[0][:10], "end": f[1][:10], "board_code": f[8],
                        "group": (o.get("data-rva"), f[3], f[4], f[5])})
    return sorted(out, key=lambda x: x["price"])


def candidates(options, offer, cfg):
    """Rows comparable to the offer: same term, an asked departure airport, an AI board when the offer is AI/UAI;
    one row per (operator, flights, room) – its cheapest – in price order."""
    deps = set(cfg["departures"]) | set(cfg.get("departures_secondary") or [])
    ai = offer.get("board") in ("AI", "UAI")
    seen, out = set(), []
    for x in options:
        if x["start"] != offer["date_from"] or (offer.get("date_to") and x["end"] != offer["date_to"]):
            continue
        if x["dep"] not in deps or (ai and x["board_code"] not in _AI_BOARD_CODES):
            continue
        if x["group"] in seen:
            continue
        seen.add(x["group"])
        out.append(x)
    return out


def _tag(name, text):
    m = re.search(rf"<{name}>(.*?)</{name}>", text or "", re.S)
    return m.group(1).strip() if m else ""


def parse_check(text):
    """checkPrice.php answer -> ('available'|'on_request'|'unavailable'|'retry', price or None)."""
    err = _tag("error", text)
    try:
        price = int(float(_tag("preis", text) or 0))
    except ValueError:
        price = 0
    low = strip_accents(err).lower()
    if "lucke" in low or "leerzeitraum" in low:
        return "retry", None
    if not err and price > 0:
        return "available", price
    if "anfrage" in low:
        return "on_request", price or None
    return "unavailable", None


def _room_text(x):
    bits = [x["room"] + (f" ({x['kind']})" if x["kind"] and x["kind"].lower() not in x["room"].lower() else ""),
            " ".join(b for b in (x["board"], x["transfer"]) if b), x["toc"]]
    return ", ".join(b for b in bits if b)[:160]


def verify_one(offer, cfg, budget):
    """(result dict or None, requests made) for one offer, ≤ budget requests."""
    conf = verify_conf(offer)
    if not conf["gid"] or budget < 2:
        return None, 0
    referer = offer["url"]
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": referer, "Origin": IBE}
    html = get(IBE + "/hub/ajax/additionalOffersHotelpage.php", method="POST", headers=hdr, timeout=60,
               data={"conf": json.dumps(conf), "price": "", "data": "", "debug": ""})
    calls = 1
    opts = parse_options(html)
    todo = candidates(opts, offer, cfg)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    res = {"status": "unavailable", "price": None, "room": None, "checked_at": now, "options": len(todo),
           "checked": 0, "listed": todo[0]["price"] if todo else None}
    if not todo:
        print(f"[ruefa] verify {offer['hotel']} {offer['date_from']}: {len(opts)} rows, none comparable -> unavailable")
        return res, calls
    on_request = None
    for x in todo[:VERIFY_CHECKS]:
        if calls >= budget:
            break
        status, price = "retry", None
        for recheck in ("0", "1"):
            if calls >= budget:
                break
            text = get(IBE + "/hub/ajax/checkPrice.php", method="POST", headers=hdr,
                       data={"conf": json.dumps(dict(conf, veranstalter=x["rva"])), "data": x["data"],
                             "bid": "".join(random.choice(string.ascii_letters + string.digits) for _ in range(10)),
                             "recheck": recheck, "isHotelPriceCheck": "1", "url": referer, "alternative": "",
                             "debug": ""})
            calls += 1
            status, price = parse_check(text)
            if status != "retry":
                break
        res["checked"] += 1
        print(f"[ruefa] verify {offer['hotel']} {offer['date_from']}: {x['toc']} {x['room']} {x['dep']} "
              f"listed {x['price']} -> {status} {price or ''}")
        if status == "available":
            res.update(status="available", price=price, room=_room_text(x))
            return res, calls
        if status == "on_request" and not on_request:
            on_request = (x, price)
    if on_request:
        x, price = on_request
        res.update(status="on_request", price=price or x["price"], room=_room_text(x))
    elif res["checked"] < len(todo):
        res["partial"] = True  # only the cheapest options were tried; a dearer one may still be bookable
    return res, calls


def verify(cfg, offers):
    """run.py hook: {offer id: {status, price, room, checked_at, …}} for the given offers (most important first),
    ≤ VERIFY_CALLS requests in total. Offers left out (budget, errors) are simply not in the answer."""
    out, calls = {}, 0
    for o in offers:
        if VERIFY_CALLS - calls < 2:
            print(f"[ruefa] verify: request budget {VERIFY_CALLS} reached")
            break
        if not o.get("url", "").startswith(IBE + "/") or "page=hotel" not in o["url"]:
            continue
        try:
            res, n = verify_one(o, cfg, VERIFY_CALLS - calls)
        except Exception as e:
            print(f"[ruefa] verify {o['hotel']}: {type(e).__name__} {str(e)[:120]}")
            calls += 1
            if "403" in str(e) or "429" in str(e):
                break
            continue
        calls += n
        if res:
            out[o["id"]] = res
    print(f"[ruefa] verify: {len(out)} offers checked with {calls} requests")
    return out
