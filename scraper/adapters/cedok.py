"""Čedok (cedok.sk) – Next.js site; search result pages are server-rendered and carry the full rate list in
<script id="__NEXT_DATA__"> (prices in euro cents, per participant and in total), 25 rates per page.

Checked 2026-10-24: robots.txt only disallows /api*, /booking*, /reservation*, /_next/static/; the terms
(/obchodne-podmienky/) contain no text-and-data-mining reservation; plain requests get the page (no challenge).
Length filter: durationMin/durationMax in days (nights + 1). Children in the URL: none of ~15 participants[0][...]
variants was picked up (children=N answers 500), so we ask for 2 adults and show per-person price x 3, labelled
"orientačne" like satur.py. Each page lists the cheapest matching term per hotel.
"""

import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

from common import get, norm_board, norm_country

NAME = "Čedok"
HOME = "https://www.cedok.sk"

# destination slugs as used in cedok.sk URLs; a wrong slug just returns few/no rates (logged)
DESTINATIONS = ["turecko", "grecko", "cyprus", "spanielsko", "kanarske-ostrovy", "taliansko", "malta",
                "chorvatsko", "egypt"]
AIRPORTS = {"bratislava": "BTS", "vieden": "VIE", "viede": "VIE", "kosice": "KSC", "budapest": "BUD"}
PAGES = 3  # max pages (25 rates each) per destination
ADULTS = 2  # see module docstring


def _query(cfg, page=1, adults=ADULTS):
    q = {"departuresByPlane": ",".join(cfg["departures"]), "dateFrom": f"{cfg['date_from']:%d.%m.%Y}",
         "dateTo": f"{cfg['date_to']:%d.%m.%Y}", "durationMin": cfg["nights_min"] + 1,
         "durationMax": cfg["nights_max"] + 1, "order": "priceAsc", "participants[0][adults]": adults}
    if page > 1:
        q["page"] = page
    return q


def deeplinks(cfg):
    n = f"{cfg['nights_min']}–{cfg['nights_max']} nocí"
    out = []
    for slug, label in [("turecko", "Turecko"), ("grecko", "Grécko"), ("spanielsko", "Španielsko"),
                        ("cyprus", "Cyprus")]:
        q = _query(cfg, adults=cfg["adults"])
        out.append({"transport": "flight", "label": f"{label} letecky z Bratislavy / Viedne, júl–aug, {n}",
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


def to_offer(r, links, party, adults=ADULTS):
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
    exact = len(people) == party and kids == party - 1  # 1 adult + 2 children priced by the site
    total = r["price"] / 100 if exact else r["price"] / 100 / max(len(people) or adults, 1) * party
    orig = r.get("baseCatalogPrice") or 0
    orig = (orig / 100 if exact else orig / 100 / max(len(people) or adults, 1) * party) if orig > r["price"] else None
    promo = next((p["title"] for p in r.get("promotions", []) if "minute" in p.get("value", "").lower()), None)
    if exact:
        label = promo
    else:
        label = f"{promo} (cena za os. × 3, orientačne)" if promo or orig else "Cena za os. × 3 (orientačne)"
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
    }


def search(cfg):
    party = cfg["adults"] + len(cfg["children_ages"])
    offers, errors = [], []
    for slug in DESTINATIONS:
        for page in range(1, PAGES + 1):
            try:
                html = get(f"{HOME}/vysledky-vyhladavania/dovolenky/{slug}/", params=_query(cfg, page))
            except Exception as e:
                print(f"[cedok] {slug} p{page}: {type(e).__name__} {str(e)[:120]}")
                errors.append(f"{type(e).__name__}: {str(e)[:120]}")
                break
            rates, count, links = parse_page(html)
            got = [o for o in (to_offer(r, links, party) for r in rates) if o]
            print(f"[cedok] {slug} p{page}: {len(rates)}/{count} rates, {len(got)} offers")
            offers += got
            if page * 25 >= count or not rates:
                break
    if errors and not offers:
        raise RuntimeError(f"all {len(errors)} cedok.sk requests failed, first: {errors[0]}")
    return offers
