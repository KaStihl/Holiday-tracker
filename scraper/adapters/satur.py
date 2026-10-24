"""Satur.sk – Slovak tour operator. The car + dogs track (so-psom / vlastna facets) plus flights from BTS.

Listing cards are server-rendered (article cards inside ul[data-category-target=productsListing]); each card
shows one term (the cheapest one matching the page filter) with a per-person and a 2-person price.
"""

import re
from datetime import date

from bs4 import BeautifulSoup

from common import get, norm_board, norm_country, parse_price

NAME = "Satur.sk"
HOME = "https://www.satur.sk"

# (path, transport, pets_allowed, pages). Listings take ?termin=dd.mm.yyyy-dd.mm.yyyy, ?dlzka-pobytu=<nights>
# and ?stranka=N (20 cards per page); each card shows the cheapest matching term of one hotel.
PAGES = [
    ("/dovolenka/chorvatsko/so-psom", "car", True, 3),
    ("/dovolenka/so-psom", "car", True, 3),
    ("/dovolenka/taliansko/so-psom", "car", True, 1),
    ("/first-minute/vlastna", "car", None, 2),
    ("/dovolenka/vlastna", "car", None, 2),
    ("/first-minute/letecky/z-bratislavy/all-inclusive", "flight", None, 3),
    ("/dovolenka/letecky/z-bratislavy/all-inclusive", "flight", None, 3),
    ("/dovolenka/letecky/z-bratislavy/ultra-all-inclusive", "flight", None, 2),
] + [(f"/dovolenka/{c}/letecky/z-bratislavy/all-inclusive", "flight", None, 2)
     for c in ("turecko", "grecko", "cyprus", "taliansko", "spanielsko", "chorvatsko", "malta")]

DATES_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})?\s*-\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")
AIRPORTS = {"bratislava": "BTS", "viede": "VIE", "vieden": "VIE", "kosice": "KSC", "budapest": "BUD"}


def deeplinks(cfg):
    n = f"{cfg['nights_min']}–{cfg['nights_max']} nocí"
    return [
        {"transport": "car", "label": "Chorvátsko so psom, vlastná doprava", "url": HOME + "/dovolenka/chorvatsko/so-psom"},
        {"transport": "car", "label": "Dovolenka so psom (všetky krajiny)", "url": HOME + "/dovolenka/so-psom"},
        {"transport": "car", "label": "First minute, vlastná doprava", "url": HOME + "/first-minute/vlastna"},
        {"transport": "flight", "label": f"First minute letecky z Bratislavy, AI, {n}",
         "url": HOME + "/first-minute/letecky/z-bratislavy/all-inclusive"},
        {"transport": "flight", "label": "Turecko letecky z Bratislavy, AI",
         "url": HOME + "/dovolenka/turecko/letecky/z-bratislavy/all-inclusive"},
    ]


def _text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def _price_block(card, cls):
    """(current, original, nights) from the .collapse-price-person / -group footer block."""
    box = card.select_one(f"footer .{cls}")
    if not box:
        return None, None, None
    cur = box.select_one(".fw-bold")
    orig = box.find("s")
    m = re.search(r"(\d+)\s*noc", _text(box))
    return parse_price(_text(cur)), parse_price(_text(orig)), int(m[1]) if m else None


def parse_cards(html):
    """Raw card data from a listing page (no criteria applied)."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for art in soup.select("ul[data-category-target=productsListing] article"):
        a = art.select_one("h2 a[href]")
        if not a:
            continue
        tags = [_text(t) for t in art.select("ul.list-unstyled li .tag, ul.list-unstyled li .btn-tag")]
        stars_el = art.select_one("h2 .rating[aria-label]")
        stars = re.search(r"([\d.]+)", stars_el["aria-label"]) if stars_el else None
        rating = next((float(t) for t in tags if re.fullmatch(r"\d(\.\d)?", t)), None)  # 0–5 scale
        dates = next((DATES_RE.search(t) for t in tags if DATES_RE.search(t)), None)
        transport = next((t for t in tags if re.search(r"doprava|let\b|letecky|Priamy", t, re.I)), "")
        board = next((t for t in tags if norm_board(t)), None)
        pp, pp_orig, nights = _price_block(art, "collapse-price-person")
        pg, pg_orig, _ = _price_block(art, "collapse-price-group")
        loc = [x.strip() for x in _text(art.select_one("header p")).split("·")]
        img = art.select_one("img[src]")
        perks = " ".join([_text(art)] + [b.get("title", "") for b in art.select("[title]")]).lower()
        out.append({
            "hotel": _text(a), "url": HOME + a["href"] if a["href"].startswith("/") else a["href"],
            "stars": float(stars[1]) if stars else None, "rating": round(rating * 2, 1) if rating else None,
            "country": loc[0] if loc else None, "region": loc[1] if len(loc) > 2 else None,
            "place": loc[-1] if len(loc) > 1 else None, "dates": dates.group(0) if dates else None,
            "transport_text": transport, "board": board, "nights": nights,
            "price_person": pp, "price_person_original": pp_orig, "price_group": pg, "price_group_original": pg_orig,
            "image": img["src"] if img else None, "pets": "so psom" in perks,
        })
    return out


def _dates(s):
    m = DATES_RE.search(s or "")
    if not m:
        return None, None
    d2 = date(int(m[6]), int(m[5]), int(m[4]))
    d1 = date(int(m[3] or m[6]), int(m[2]), int(m[1]))
    if d1 > d2:  # "28.12. - 4.1.2027" crosses the year
        d1 = date(d1.year - 1, d1.month, d1.day)
    return d1, d2


def to_offer(c, transport, pets, party):
    """Card -> offer dict. Satur shows per-person prices (for 2 adults sharing a room); the party price is
    approximated as per-person x party size – child discounts or a single-adult surcharge only show in the
    booking form, so the real price for 1 adult + 2 kids can differ either way."""
    d1, d2 = _dates(c["dates"])
    if not (d1 and c["price_person"]):
        return None
    tt = (c["transport_text"] or "").lower()
    car = "individu" in tt or "vlastn" in tt or (transport == "car" and "let" not in tt)
    dep = next((code for k, code in AIRPORTS.items() if k in tt.replace("í", "i").replace("š", "s")), None)
    if not dep and not car:  # some cards omit the flight tag; their link still says ?odlet=BTS
        m = re.search(r"[?&]odlet=([A-Z]{3})", c["url"])
        dep = m[1] if m else None
    orig = c["price_person_original"]
    return {
        "hotel": c["hotel"], "url": c["url"], "image": c["image"], "stars": c["stars"], "rating": c["rating"],
        "country": c["country"], "country_code": norm_country(c["country"]), "region": c["region"],
        "place": c["place"], "board": norm_board(c["board"]), "transport": "car" if car else "flight",
        "departure": None if car else dep, "date_from": d1.isoformat(), "date_to": d2.isoformat(),
        "nights": c["nights"] or (d2 - d1).days,
        "price_total": c["price_person"] * party,
        "price_original": orig * party if orig else None,
        "discount_label": "Zľava (cena za os. × 3, orientačne)" if orig else "Cena za os. × 3 (orientačne)",
        "pets_allowed": (pets or c.get("pets") or None) if car else None,
    }


def search(cfg):
    party = cfg["adults"] + len(cfg["children_ages"])
    termin = f"{cfg['date_from']:%d.%m.%Y}-{cfg['date_to']:%d.%m.%Y}"
    offers, errors = [], []  # duplicates across pages are fine: run.py keeps the cheapest per offer id
    # dlzka-pobytu=7: 7-night stays (the cheapest in our 7–14 range); longer ones are left to the deeplinks
    for path, transport, pets, pages in PAGES:
        for n in range(1, pages + 1):
            params = {"termin": termin, "dlzka-pobytu": cfg["nights_min"], **({"stranka": n} if n > 1 else {})}
            try:
                cards = parse_cards(get(HOME + path, params=params))
            except Exception as e:
                print(f"[satur] {path} p{n}: {type(e).__name__} {str(e)[:120]}")
                errors.append(f"{type(e).__name__}: {str(e)[:120]}")
                break
            got = [o for o in (to_offer(c, transport, pets, party) for c in cards) if o]
            print(f"[satur] {path} p{n}: {len(cards)} cards, {len(got)} offers, first={cards[:1]}")
            offers += got
            if len(cards) < 20:
                break
    if errors and not offers:
        raise RuntimeError(f"all {len(errors)} satur.sk listing requests failed, first: {errors[0]}")
    return offers
