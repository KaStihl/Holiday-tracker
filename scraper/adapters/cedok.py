"""Čedok (cedok.sk) – Next.js site; search result pages are server-rendered and carry the full rate list in
<script id="__NEXT_DATA__"> (prices in euro cents, per participant and in total), 25 rates per page.

Checked 2026-10-24: robots.txt only disallows /api*, /booking*, /reservation*, /_next/static/; the terms
(/obchodne-podmienky/) contain no text-and-data-mining reservation; plain requests get the page (no challenge).
Length filter: durationMin/durationMax in days (nights + 1). Children in the URL: none of ~15 participants[0][...]
variants was picked up (children=N answers 500), so we ask for 2 adults and show per-person price x party size,
labelled "orientačne" like satur.py. Each page lists the cheapest matching term per hotel.

Exact party prices (checked 2026-10-25): the hotel/term detail page /dovolena/<country>/<region>/<hotel>,<ID>/?id=…
(server-rendered React Server Components payload, robots allows /dovolena/) honours
participants[0][adults]=A&participants[0][children][i]=DD.MM.YYYY (party from nastavenia.yml) and
embeds the priced variant as "date":{"range":{start,end}} … "participants":{"adultNumber":A,"childrenNumber":C,
"childrenBirthDates":[…]},"totalPrice":N. exact_price() fetches that for a shortlist chosen by run.py and only
accepts it when the dates and the party in the payload match the offer (otherwise the offer stays approximate).
"""

import json
import re
from datetime import date
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from common import get, norm_board, norm_country
from config import approx_label, party_label, party_size, period_label

NAME = "Čedok"
HOME = "https://www.cedok.sk"

# destination slugs as used in cedok.sk URLs -> country code; a wrong slug just returns few/no rates (logged).
# Only slugs whose country is in nastavenia.yml destinations are asked.
DESTINATIONS = {"turecko": "TR", "grecko": "GR", "cyprus": "CY", "spanielsko": "ES", "kanarske-ostrovy": "ES",
                "taliansko": "IT", "malta": "MT", "chorvatsko": "HR", "egypt": "EG"}
# Long-haul / other non-European countries: one wide-length page (25 cheapest rates) each, to stay polite.
# code -> slug candidates; an unknown slug answers an empty result (0 rates), then the next one is tried.
# Confirmed 2026-10-30 (rates found): tunisko, maroko, spojene-arabske-emiraty, maldivy, mauricius, seychely,
# thajsko, indonezia, vietnam, zanzibar, dominikanska-republika, mexiko (= geographicalIdentifiers country ids).
# 0 rates for Jul–Aug from BTS/VIE (every candidate tried 2026-10-30): oman, jordansko, sri-lanka/srilanka,
# kena/kenya, kapverdske-ostrovy/kapverdy, kuba, maledivy, tanzania – kept as one cheap request each in case
# Čedok adds them.
FAR = {"TN": ("tunisko",), "MA": ("maroko",), "AE": ("spojene-arabske-emiraty",), "OM": ("oman",),
       "JO": ("jordansko",), "MV": ("maldivy",), "MU": ("mauricius",), "SC": ("seychely",),
       "LK": ("sri-lanka",), "TH": ("thajsko",), "ID": ("indonezia",), "VN": ("vietnam",),
       "TZ": ("zanzibar", "tanzania"), "KE": ("kena",), "CV": ("kapverdske-ostrovy",),
       "DO": ("dominikanska-republika",), "MX": ("mexiko",), "CU": ("kuba",)}
AIRPORTS = {"bratislava": "BTS", "vieden": "VIE", "viede": "VIE", "kosice": "KSC", "budapest": "BUD"}
# (durationMin, durationMax) in days and max pages (25 rates each) per destination. One wide 8–15 query only ever
# showed the cheapest stay, 7 nights; separate ranges give real 7, 10–11 and 14 night terms.
# Budget (checked 2026-10-30): ≤ 9 x (2+1+1) + 18 FAR + EXACT_MAX ≈ 84 requests per run.
DURATIONS = [((8, 10), 2), ((11, 12), 1), ((15, 15), 1)]
ADULTS = 2  # see module docstring
EXACT_MAX = 30  # detail pages (~1 MB each) fetched per run for exact prices of the configured party
APPROX_NOTE = re.compile(r"\s*\(cena za os\. × \d+, orientačne\)|Cena za os\. × \d+ \(orientačne\)")


def _query(cfg, page=1, adults=ADULTS, days=None):
    days = days or (cfg["nights_min"] + 1, cfg["nights_max"] + 1)
    q = {"departuresByPlane": ",".join(cfg["departures"]), "dateFrom": f"{cfg['date_from']:%d.%m.%Y}",
         "dateTo": f"{cfg['date_to']:%d.%m.%Y}", "durationMin": days[0], "durationMax": days[1],
         "order": "priceAsc", "participants[0][adults]": adults}
    if page > 1:
        q["page"] = page
    return q


def deeplinks(cfg):
    n = f"{cfg['nights_min']}–{cfg['nights_max']} nocí"
    out = []
    for slug, label in [("turecko", "Turecko"), ("grecko", "Grécko"), ("spanielsko", "Španielsko"),
                        ("cyprus", "Cyprus")]:
        q = _query(cfg, adults=cfg["adults"])
        out.append({"transport": "flight", "label": f"{label} letecky z {'/'.join(cfg['departures'])}, "
                                                    f"{period_label(cfg)}, {n}, {party_label(cfg)}",
                    "url": f"{HOME}/vysledky-vyhladavania/dovolenky/{slug}/?{urlencode(q)}"})
    out.append({"transport": "flight", "label": "All inclusive z Bratislavy (všetky destinácie)",
                "url": HOME + "/all-inclusive/?departuresByPlane=BTS%2CKSC%2CTAT"})
    return out


def _airport(title):
    t = (title or "").lower().replace("ň", "n").replace("š", "s").replace("í", "i")
    return next((code for k, code in AIRPORTS.items() if k in t), None)


def parse_page(html):
    """(rates, total count, {supplierObjectId: detail href}) from one result page."""
    soup = BeautifulSoup(html, "lxml")
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd is None or not nd.string:
        return [], 0, {}
    pp = json.loads(nd.string)["props"]["pageProps"]
    q = [q for q in pp["initialQueryState"]["queries"]
         if isinstance(q["state"].get("data"), dict) and "main" in q["state"]["data"]]
    if not q:
        return [], 0, {}
    rates = q[0]["state"]["data"]["main"]["rates"]
    links = {}
    for a in soup.select("[data-testid=offer-list-item] h3 a[href]"):
        m = re.search(r",([A-Z0-9]+)/\?", a["href"])
        if m:
            links.setdefault(m[1], a["href"])
    return rates.get("list") or [], rates.get("ratesCount") or 0, links


def to_offer(r, links, cfg, adults=ADULTS):
    """One rate -> offer dict, or None for round trips / rates without a hotel."""
    if r.get("rateType") != "holidays":
        return None
    hotel = next((s for s in r.get("segments", []) if s.get("type") == "hotel"), None)
    flight = next((s for s in r.get("segments", []) if s.get("type") == "flight"), None)
    href = links.get(r.get("supplierObjectId"))
    if not hotel or not href:
        return None
    c = hotel.get("content") or {}
    geo = {g["type"]: g["title"] for g in c.get("geographicalIdentifiers", [])}
    people = r.get("participants") or []
    kids = sum(p.get("type") == "child" for p in people)
    party = party_size(cfg)
    # priced by the site for exactly the configured party (listing pages normally price 2 adults)
    exact = len(people) == party and kids == len(cfg["children_ages"])
    total = r["price"] / 100 if exact else r["price"] / 100 / max(len(people) or adults, 1) * party
    orig = r.get("baseCatalogPrice") or 0
    orig = (orig / 100 if exact else orig / 100 / max(len(people) or adults, 1) * party) if orig > r["price"] else None
    promo = next((p["title"] for p in r.get("promotions", []) if "minute" in p.get("value", "").lower()), None)
    if exact:
        label = promo  # run.py marks it price_exact
    else:
        label = approx_label(cfg, promo or ("Zľava" if orig else None))
    stars = c.get("hotelRating")
    rating = (c.get("reviews") or {}).get("customersRating")
    photos = (c.get("photos") or {}).get("gallery") or []
    dep = _airport((flight or {}).get("departure", {}).get("title"))
    if not dep:
        dep = (parse_qs(urlsplit(href).query).get("airports", [""])[0].split(",") or [None])[0] or None
    d1, d2 = hotel["beginDate"], hotel["endDate"]
    nights = (r.get("duration") or {}).get("days")
    return {
        "hotel": c.get("title"), "url": HOME + href if href.startswith("/") else href,
        "image": photos[0] if photos else None,
        "stars": stars / 10 if stars else None, "rating": round(rating * 10 / 6, 1) if rating else None,
        "country": geo.get("country"), "country_code": norm_country(geo.get("country")),
        "region": geo.get("province"), "place": None,
        "board": norm_board((hotel.get("meal") or {}).get("title")), "transport": "flight", "departure": dep,
        "date_from": d1, "date_to": d2, "nights": nights - 1 if nights else None,
        "price_total": round(total), "price_original": round(orig) if orig else None,
        "discount_label": label, "pets_allowed": None,
        **({"price_exact": True} if exact else
           {"price_note": f"orientačne: cena za osobu pri {max(len(people) or adults, 1)} dospelých × {party}"}),
    }


# --- exact price for the configured party from the detail page -------------------------------------------------

def occupancy_url(url, cfg):
    """The offer's detail URL re-asked for the configured party (birth dates as DD.MM.YYYY, the site's format)."""
    parts = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.startswith("participants[")]
    q.append(("participants[0][adults]", str(cfg["adults"])))
    for i, bd in enumerate(cfg["children_birthdates"]):
        y, m, d = bd.split("-")
        q.append((f"participants[0][children][{i}]", f"{d}.{m}.{y}"))
    return urlunsplit(parts._replace(query=urlencode(q)))


def rsc_payload(html):
    """Concatenated React Server Components payload: every self.__next_f.push([1,"…"]) string, decoded."""
    out = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html):
        try:
            out.append(json.loads(m[1]))
        except ValueError:
            pass
    return "".join(out)


_PARTY_RE = re.compile(r'"participants":(\{[^{}]*\}),"totalPrice":(\d+(?:\.\d+)?)')
_RANGE_RE = re.compile(r'"range":\{"start":"(\d{4}-\d\d-\d\d)","end":"(\d{4}-\d\d-\d\d)"\}')


def parse_detail(html):
    """Priced variants on a detail page: [{start, end, adults, children, birthdates, total}]."""
    flight = rsc_payload(html)
    out, seen = [], set()
    for m in _PARTY_RE.finditer(flight):
        rng = list(_RANGE_RE.finditer(flight, max(0, m.start() - 2000), m.start()))
        try:
            p = json.loads(m[1])
        except ValueError:
            continue
        v = {"start": rng[-1][1] if rng else None, "end": rng[-1][2] if rng else None,
             "adults": p.get("adultNumber"), "children": p.get("childrenNumber"),
             "birthdates": p.get("childrenBirthDates") or [], "total": float(m[2])}
        key = tuple((k, str(x)) for k, x in v.items())
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def _age(born, on):
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def pick_exact(variants, offer, cfg):
    """Total for the offer's own term and exactly the configured party, else None (never a guess)."""
    d1 = date.fromisoformat(offer["date_from"])
    for v in variants:
        if (v["start"], v["end"]) != (offer["date_from"], offer["date_to"]):
            continue
        if v["adults"] != cfg["adults"] or v["children"] != len(cfg["children_ages"]):
            continue
        try:
            ages = sorted(_age(date.fromisoformat(b[:10]), d1) for b in v["birthdates"])
        except ValueError:
            continue
        if ages == sorted(cfg["children_ages"]) and v["total"] > 0:
            return round(v["total"])
    return None


def exact_price(offer, cfg):
    """run.py hook: {'price_total': …} for the configured party, or None when the page doesn't confirm it."""
    url = occupancy_url(offer["url"], cfg)
    variants = parse_detail(get(url))
    total = pick_exact(variants, offer, cfg)
    if total is None:
        print(f"[cedok] exact {offer['hotel']} {offer['date_from']}: no matching variant in {variants[:3]}")
        return None
    return {"price_total": total, "price_original": None, "url": url,
            "discount_label": APPROX_NOTE.sub("", offer.get("discount_label") or "").strip() or None}


def plan(cfg):
    """[(slug candidates, (durationMin, durationMax), max pages)] for the countries in nastavenia.yml."""
    if "flight" not in cfg["transports"]:
        return []
    out = [((slug,), days, pages) for days, pages in DURATIONS
           for slug, code in DESTINATIONS.items() if code in cfg["countries"]]
    wide = (cfg["nights_min"] + 1, cfg["nights_max"] + 1)
    return out + [(slugs, wide, 1) for code, slugs in FAR.items() if code in cfg["countries"]]


def _search_slug(cfg, slug, days, pages, far, offers, errors):
    """Pages of one destination slug into offers; False when the site had no rate at all for it."""
    for page in range(1, pages + 1):
        try:
            html = get(f"{HOME}/vysledky-vyhladavania/dovolenky/{slug}/", params=_query(cfg, page, days=days))
        except Exception as e:
            print(f"[cedok] {slug} {days} p{page}: {type(e).__name__} {str(e)[:120]}")
            errors.append(f"{type(e).__name__}: {str(e)[:120]}")
            return True
        rates, count, links = parse_page(html)
        got = [o for o in (to_offer(r, links, cfg) for r in rates) if o]
        nights = sorted({o["nights"] for o in got})
        print(f"[cedok] {slug} {days} p{page}: {len(rates)}/{count} rates, {len(got)} offers, nights={nights}"
              + (f", countries={sorted({o['country_code'] or '?' for o in got})}, "
                 f"prices={sorted(o['price_total'] for o in got)[:3]}" if far else ""))
        offers += got
        if page == 1 and not rates:
            return False
        if page * 25 >= count or not rates:
            break
    return True


def search(cfg):
    offers, errors = [], []
    far = {s for slugs in FAR.values() for s in slugs}
    for slugs, days, pages in plan(cfg):
        for slug in slugs:
            if _search_slug(cfg, slug, days, pages, slug in far, offers, errors):
                break
    if errors and not offers:
        raise RuntimeError(f"all {len(errors)} cedok.sk requests failed, first: {errors[0]}")
    return offers


# --- watched hotels (sledovane_hotely) ---------------------------------------------------------------------------
# The results page has no hotel-name filter (checked 2026-10-30: ?q=sural is ignored, the autosuggester calls /api,
# which robots.txt disallows; region slugs like /dovolenky/turecko/side/ answer 404). A country's whole offer is
# small, though (Turecko, 7–14 nights from BTS/VIE in Jul–Aug: 104 hotels = 5 pages of 25, cheapest first), so
# watch() pages through the countries where a watched hotel was seen (this run or the previous one, any agency)
# beyond the pages search() reads, ≤ WATCH_REQUESTS pages per run, and keeps the matching hotels at any price/board.
WATCH_REQUESTS = 10
COUNTRY_SLUG = {**{c: s for s, c in reversed(list(DESTINATIONS.items()))}, **{c: s[0] for c, s in FAR.items()}}


def watch(cfg, terms, hints):
    """run.py hook: offers of the watched hotels from the full listing of the countries they were seen in."""
    from watch import match
    if "flight" not in cfg["transports"]:
        return []
    codes = []
    for t in terms:
        for h in hints.get(t, []):
            if h.get("country_code") in COUNTRY_SLUG and h["country_code"] not in codes:
                codes.append(h["country_code"])
    wide = (cfg["nights_min"] + 1, cfg["nights_max"] + 1)
    offers, calls = [], 0
    for code in codes:
        slug = COUNTRY_SLUG[code]
        for page in range(1, WATCH_REQUESTS + 1):
            if calls >= WATCH_REQUESTS:
                print(f"[cedok] watch: request budget {WATCH_REQUESTS} reached")
                return offers
            calls += 1
            try:
                html = get(f"{HOME}/vysledky-vyhladavania/dovolenky/{slug}/", params=_query(cfg, page, days=wide))
            except Exception as e:
                print(f"[cedok] watch {slug} p{page}: {type(e).__name__} {str(e)[:120]}")
                break
            rates, count, links = parse_page(html)
            got = [o for o in (to_offer(r, links, cfg) for r in rates) if o and match(o["hotel"], terms)]
            print(f"[cedok] watch {slug} p{page}: {len(rates)}/{count} rates, {len(got)} watched: "
                  + ", ".join(f"{o['hotel']} {o['price_total']}" for o in got))
            offers += got
            if page * 25 >= count or not rates:
                break
    return offers
