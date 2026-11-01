"""Itaka (itaka.cz) – Polish tour operator (owner of Čedok), Czech site. Same Next.js platform as cedok.sk: search
result pages are server-rendered and carry the rate list in <script id="__NEXT_DATA__"> (prices in CZK hellers,
per participant and in total incl. airport fees as priceWithSurcharges), 25 rates per page, so cedok.parse_page()
reads them.

Checked 2026-11-01 from GitHub runners:
- robots.txt (Cloudflare, no challenge for plain requests): only /reservation*, /booking*, /api*, /_next/static/
  are disallowed; /vysledky-vyhledavani/ and /dovolena/ (hotel pages) are allowed.
- Terms: "Podmínky používání webu" (/pravidla-a-podminky, English text taken over from itaka.pl) allow personal,
  non-commercial use and prohibit "automated systems or software to extract data from this site for commercial
  purposes (so-called screen scraping)". This tracker is a private, non-commercial family tool, which is the
  permitted use; to stay well within it the adapter makes 1 request per run while Itaka has no flight from the
  configured airports (see below) and at most MAX_REQUESTS + WATCH_REQUESTS otherwise. No text-and-data-mining
  reservation beyond that clause. If the site owner objects, set DEEPLINK_ONLY = True.
- itaka.sk: no site (its TLS certificate is not valid for itaka.sk / www.itaka.sk).
- Departures: the search form lists Polish airports (WAW, KTW, WRO, POZ, GDN, KRK, RZE, …), PRG and BER. An airport
  the site doesn't serve is silently ignored: departuresByPlane=BTS, VIE, BRQ, BUD, KSC, OSR and PRG all answered the
  same unfiltered list (Turecko, Jul–Aug 2027: 204 rates, no flight segment or Berlín), KTW the real one (154 rates,
  "Katovice (letiště)"). So search() first asks one page with the configured airports and only goes on when a rate
  really departs from one of them; today none does -> 0 offers (flights from KTW/BER would be dropped by run.py's
  departure filter anyway).
- Party: participants[0][adults]=A&participants[0][children][i]=DD.MM.YYYY is honoured by the listing (the query
  key echoes adultsNumber/childrenBirthDates and every rate lists 1 adult + 2 children with their own prices), so a
  rate priced for exactly that party is price_exact; CZK -> EUR at the ECB rate of the day (common.eur_rate), noted
  in price_note.
- Royal Alhambra Palace (Side, product AYTALHA): the hotel page /dovolena/turecko/side/royal-alhambra-palace,AYTALHA/
  embeds its bookable variants (queryKey "variants" -> groupedVariants.referenceRate, same shape as a listing
  rate); on 2026-11-01 groupedVariants was null for any party and departure = not on sale at Itaka now. watch()
  reads that page for the watched hotels listed in HOTEL_PAGES (no hotel search: the autosuggester is under /api).
"""

import json
from collections import Counter
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from adapters import cedok
from common import eur_rate, get, norm_board, norm_country, strip_accents
from config import approx_label, party_label, party_size, period_label

NAME = "Itaka"
HOME = "https://www.itaka.cz"
LIST = "/vysledky-vyhledavani/dovolena/"
CURRENCY = "CZK"
MAX_REQUESTS = 30
WATCH_REQUESTS = 3
# Departure titles ("Brno (letiště)") -> IATA. Unknown titles -> the rate is skipped (never passed off as ours).
AIRPORTS = {"bratislava": "BTS", "viden": "VIE", "brno": "BRQ", "budapest": "BUD", "kosice": "KSC", "praha": "PRG",
            "ostrava": "OSR", "pardubice": "PED", "katovice": "KTW", "berlin": "BER", "krakov": "KRK",
            "vratislav": "WRO", "varsava": "WAW", "poznan": "POZ", "gdansk": "GDN", "resov": "RZE"}
# Country slugs of the listing (/vysledky-vyhledavani/dovolena/<slug>/). Seen on the site 2026-11-01: turecko, recko,
# spanelsko, egypt, italie, albanie, madeira, dominikanska-republika, kena, maledivy, oman, spojene-arabske-emiraty,
# sri-lanka, thajsko, zanzibar; the others follow the same Czech naming (a wrong slug shows other countries' rates,
# which are discarded, see search()).
SLUGS = {"TR": "turecko", "GR": "recko", "ES": "spanelsko", "EG": "egypt", "IT": "italie", "AL": "albanie",
         "PT": "portugalsko", "HR": "chorvatsko", "CY": "kypr", "MT": "malta", "ME": "cerna-hora", "BG": "bulharsko",
         "TN": "tunisko", "MA": "maroko", "CV": "kapverdy", "TZ": "zanzibar", "KE": "kena",
         "AE": "spojene-arabske-emiraty", "OM": "oman", "JO": "jordansko", "MV": "maledivy", "MU": "mauricius",
         "SC": "seychely", "LK": "sri-lanka", "TH": "thajsko", "ID": "indonesie", "VN": "vietnam",
         "DO": "dominikanska-republika", "MX": "mexiko", "CU": "kuba"}
# Watched hotels with a known Itaka page (watch() / watch_links()); matched against sledovane_hotely by watch.match.
HOTEL_PAGES = [("Royal Alhambra Palace", "/dovolena/turecko/side/royal-alhambra-palace,AYTALHA/")]


def airports(cfg):
    return cfg["departures"] + [c for c in cfg.get("departures_secondary") or [] if c not in cfg["departures"]]


def _party(cfg):
    q = {"participants[0][adults]": cfg["adults"]}
    for i, bd in enumerate(cfg["children_birthdates"]):
        y, m, d = bd.split("-")
        q[f"participants[0][children][{i}]"] = f"{d}.{m}.{y}"
    return q


def query(cfg, deps, page=1):
    q = {"departuresByPlane": ",".join(deps), "dateFrom": f"{cfg['date_from']:%d.%m.%Y}",
         "dateTo": f"{cfg['date_to']:%d.%m.%Y}", "durationMin": cfg["nights_min"] + 1,
         "durationMax": cfg["nights_max"] + 1, "order": "priceAsc", **_party(cfg)}
    if page > 1:
        q["page"] = page
    return q


def deeplinks(cfg):
    out = [{"transport": "flight",
            "label": f"Itaka.cz: dovolenka {period_label(cfg)}, {cfg['nights_min']}–{cfg['nights_max']} nocí, "
                     f"{party_label(cfg)}, odlety z {'/'.join(airports(cfg))} (ak ich cestovka ponúka)",
            "url": f"{HOME}{LIST}?{urlencode(query(cfg, airports(cfg)))}"}]
    return out


def airport(title):
    t = strip_accents(title or "").lower()
    return next((code for k, code in AIRPORTS.items() if k in t), None)


def _board(title):
    t = strip_accents(title or "").lower()
    if "ultra" in t:
        return "UAI"
    if "plna penze" in t:
        return "FB"
    return norm_board(title)


def to_offer(r, links, cfg, fx):
    """One rate -> offer dict, or None (round trips, hotel-only rates, unknown departure, missing link)."""
    if r.get("rateType") != "holidays":
        return None
    segs = r.get("segments") or []
    hotel = next((s for s in segs if s.get("type") == "hotel"), None)
    flight = next((s for s in segs if s.get("type") == "flight"), None)
    href = links.get(r.get("supplierObjectId"))
    if not hotel or not flight or not href:
        return None
    dep = airport((flight.get("departure") or {}).get("title"))
    if not dep:
        return None
    rate, fx_note = fx
    c = hotel.get("content") or {}
    geo = {g["type"]: g["title"] for g in c.get("geographicalIdentifiers") or []}
    people = r.get("participants") or []
    kids = sum(p.get("type") == "child" for p in people)
    party = party_size(cfg)
    exact = len(people) == party and kids == len(cfg["children_ages"])
    cents = r.get("priceWithSurcharges") or r.get("price")
    base = r.get("baseCatalogPriceWithSurcharges") or r.get("baseCatalogPrice") or 0
    if not cents or (r.get("currency") or CURRENCY) != CURRENCY:
        return None
    n = max(len(people), 1)
    scale = 1 if exact else party / n
    total = cents / 100 / rate * scale
    orig = base / 100 / rate * scale if base > cents else None
    promo = next((p["title"] for p in r.get("promotions") or [] if "minute" in (p.get("value") or "").lower()), None)
    stars, rating = c.get("hotelRating"), (c.get("reviews") or {}).get("customersRating")
    photos = (c.get("photos") or {}).get("gallery") or []
    days = (r.get("duration") or {}).get("days")
    czk = round(cents / 100 * scale)
    note = f"{fx_note}: " + f"{czk:,}".replace(",", " ") + " Kč"
    return {
        "hotel": c.get("title"), "url": HOME + href if href.startswith("/") else href,
        "image": photos[0] if photos else None,
        "stars": stars / 10 if stars else None, "rating": round(rating * 10 / 6, 1) if rating else None,
        "country": geo.get("country"), "country_code": norm_country(geo.get("country")),
        "region": geo.get("province"), "place": None,
        "board": _board((hotel.get("meal") or {}).get("title")), "transport": "flight", "departure": dep,
        "date_from": hotel.get("beginDate"), "date_to": hotel.get("endDate"), "nights": days - 1 if days else None,
        "price_total": round(total), "price_original": round(orig) if orig else None,
        "discount_label": promo if exact else approx_label(cfg, promo),
        "pets_allowed": None, "fx_note": note,
        **({"price_exact": True} if exact else
           {"price_note": f"orientačne: cena za osobu pri {n} osobách × {party}"}),
    }


def _page(cfg, path, deps, page, fx):
    rates, count, links = cedok.parse_page(get(HOME + path, params=query(cfg, deps, page)))
    return rates, count, [o for o in (to_offer(r, links, cfg, fx) for r in rates) if o]


def _departures(rates):
    return Counter((next((s for s in r.get("segments") or [] if s.get("type") == "flight"), {}).get("departure")
                    or {}).get("title") or "bez letu" for r in rates)


def search(cfg):
    if "flight" not in cfg["transports"]:
        return []
    deps = airports(cfg)
    fx = eur_rate(CURRENCY)
    rates, count, got = _page(cfg, LIST, deps, 1, fx)
    served = sorted({o["departure"] for o in got if o["departure"] in deps})
    if not served:
        print(f"[itaka] no flight from {','.join(deps)} (the site ignores airports it doesn't serve): "
              f"{count} rates, departures on page 1: {dict(_departures(rates))} -> 0 offers")
        return []
    print(f"[itaka] flights from {served}: {count} rates")
    offers, calls = [o for o in got if o["departure"] in served], 1
    todo = [(c, SLUGS[c]) for c, w in sorted(cfg["countries"].items(), key=lambda kv: -kv[1]) if c in SLUGS]
    pages = [(c, s, 1) for c, s in todo] + [(c, s, 2) for c, s in todo if cfg["countries"][c] >= 0.9]
    empty = set()
    for code, slug, page in pages:
        if calls >= MAX_REQUESTS:
            print(f"[itaka] request budget {MAX_REQUESTS} reached")
            break
        if code in empty:
            continue
        calls += 1
        try:
            rates, count, got = _page(cfg, f"{LIST}{slug}/", served, page, fx)
        except Exception as e:
            print(f"[itaka] {slug} p{page}: {type(e).__name__} {str(e)[:120]}")
            if "403" in str(e) or "429" in str(e):
                raise
            continue
        mine = [o for o in got if o["country_code"] == code and o["departure"] in served]
        print(f"[itaka] {slug} p{page}: {len(rates)}/{count} rates, {len(mine)} offers "
              f"({sum(bool(o.get('price_exact')) for o in mine)} exact), departures {dict(_departures(rates))}")
        offers += mine
        if not mine or page * 25 >= count:
            empty.add(code)
    return offers


# --- watched hotels (sledovane_hotely) ---------------------------------------------------------------------------

def hotel_pages(terms):
    from watch import match
    return [(name, path, match(name, terms)) for name, path in HOTEL_PAGES if match(name, terms)]


def parse_variants(html):
    """groupedVariants of a hotel page's __NEXT_DATA__ (None when the hotel has nothing on sale)."""
    soup = BeautifulSoup(html, "lxml")
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd is None or not nd.string:
        return None
    for q in json.loads(nd.string)["props"]["pageProps"].get("initialQueryState", {}).get("queries", []):
        if (q.get("queryKey") or [None])[0] == "variants":
            return (q.get("state") or {}).get("data", {}).get("groupedVariants")
    return None


def watch(cfg, terms, hints=None):
    """run.py hook: the reference (cheapest default) variant of each watched hotel with a known Itaka page."""
    if "flight" not in cfg["transports"]:
        return []
    fx, offers = None, []
    for name, path, term in hotel_pages(terms)[:WATCH_REQUESTS]:
        q = {**_party(cfg), "departuresByPlane": ",".join(airports(cfg))}
        try:
            gv = parse_variants(get(HOME + path, params=q))
        except Exception as e:
            print(f"[itaka] watch {name}: {type(e).__name__} {str(e)[:120]}")
            continue
        if not gv or not gv.get("referenceRate"):
            print(f"[itaka] watch {name}: nothing on sale (no variants)")
            continue
        fx = fx or eur_rate(CURRENCY)
        ref = gv["referenceRate"]
        seen = sorted({(d.get("departure") or {}).get("id") or "?" for d in gv.get("departureCode") or []})
        o = to_offer(ref, {ref.get("supplierObjectId"): f"{path}?{urlencode(q)}"}, cfg, fx)
        print(f"[itaka] watch {name}: departures offered {seen}, reference variant -> "
              + (f"{o['departure']} {o['date_from']} {o['nights']}n {o['price_total']} €" if o else "not usable"))
        if o:
            offers.append(o)
    return offers


def watch_links(cfg, term, hints):
    return [{"label": f"{name} na itaka.cz", "url": f"{HOME}{path}?{urlencode(_party(cfg))}"}
            for name, path, _ in hotel_pages([term])]
