"""Satur.sk – Slovak tour operator. The car + dogs track (so-psom / vlastna facets) plus flights from BTS.

Listing cards are server-rendered (article cards inside ul[data-category-target=productsListing]); each card
shows one term (the cheapest one matching the page filter) with a per-person and a 2-person price.
"""

import re
from datetime import date

from bs4 import BeautifulSoup

from common import diag, get, norm_board, norm_country, parse_price
from config import party_size

NAME = "Satur.sk"
HOME = "https://www.satur.sk"

# (path, transport, pets_allowed, pages). Listings take ?termin=dd.mm.yyyy-dd.mm.yyyy, ?dlzka-pobytu=<nights>
# (or a list: 10,11) and ?stranka=N (20 cards per page); each card shows the cheapest matching term of one hotel.
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
PAGE_COUNTRY = {"turecko": "TR", "grecko": "GR", "cyprus": "CY", "taliansko": "IT", "spanielsko": "ES",
                "chorvatsko": "HR", "malta": "MT"}

# Long-haul / non-European countries: one listing page per country (any departure airport and board, every
# allowed length in one ?dlzka-pobytu list), departures outside nastavenia.yml are dropped by run.py.
# Asked only for countries listed in nastavenia.yml destinations. A slug Satur doesn't use answers 404 (logged).
FAR = {"EG": "egypt", "TN": "tunisko", "MA": "maroko", "AE": "spojene-arabske-emiraty", "OM": "oman",
       "JO": "jordansko", "MV": "maldivy", "MU": "mauricius", "SC": "seychely", "LK": "sri-lanka", "TH": "thajsko",
       "ID": "indonezia", "VN": "vietnam", "TZ": "tanzania", "KE": "kena", "CV": "kapverdske-ostrovy",
       "DO": "dominikanska-republika", "MX": "mexiko", "CU": "kuba"}

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
    booking form, so the real price for the configured party can differ either way.
    Checked 2026-10-25: neither listings nor /produkt/ pages take the party server-side (?passengers=1|3|18,10,12,
    ?date=…&passengers=… from the product form, ?dospeli=…: still "2 dospelí", group price = 2 x per person; dospeli
    is the adults-only club facet). Exact party prices come only from /ajax, which robots.txt disallows -> stays
    approximate (no exact_price hook)."""
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
        "discount_label": (f"Zľava (cena za os. × {party}, orientačne)" if orig
                           else f"Cena za os. × {party} (orientačne)"),
        "price_note": f"orientačne: cena za osobu pri 2 dospelých × {party}",
        "pets_allowed": (pets or c.get("pets") or None) if car else None,
    }


# ?dlzka-pobytu (nights; a comma list works, ranges like 10-11 are ignored) -> {transport: max pages per PAGES
# entry, None = all}. Checked 2026-10-24 for Jul–Aug: car stays are Saturday to Saturday (no 10–11 night terms)
# and most 10–14 night flight terms cost more than price_cap, so those get one page. ~55 requests per run,
# plus one per long-haul country in FAR (~19) -> ≤ ~75.
STAYS = [(7, {"car": None, "flight": None}), ("10,11", {"flight": 1}), (14, {"car": 2, "flight": 1})]


def pages_for(cfg):
    """PAGES narrowed to nastavenia.yml: transports, dogs, destination countries."""
    out = []
    for path, transport, pets, pages in PAGES:
        if transport not in cfg["transports"] or (pets and not cfg["dogs"]):
            continue
        slug = path.split("/")[2] if path.startswith("/dovolenka/") else None
        if slug in PAGE_COUNTRY and PAGE_COUNTRY[slug] not in cfg["countries"]:
            continue
        out.append((path, transport, pets, pages))
    return out


def far_pages(cfg):
    if "flight" not in cfg["transports"]:
        return []
    return [(code, f"/dovolenka/{slug}/letecky") for code, slug in FAR.items() if code in cfg["countries"]]


def search(cfg):
    party = party_size(cfg)
    termin = f"{cfg['date_from']:%d.%m.%Y}-{cfg['date_to']:%d.%m.%Y}"
    offers, errors = [], []  # duplicates across pages are fine: run.py keeps the cheapest per offer id
    for stay, budget in STAYS:
        wanted = {int(x) for x in str(stay).split(",")}
        for path, transport, pets, pages in pages_for(cfg):
            if transport not in budget:
                continue
            for n in range(1, min(pages, budget[transport] or pages) + 1):
                params = {"termin": termin, "dlzka-pobytu": stay, **({"stranka": n} if n > 1 else {})}
                try:
                    cards = parse_cards(get(HOME + path, params=params))
                except Exception as e:
                    print(f"[satur] {path} {stay}n p{n}: {type(e).__name__} {str(e)[:120]}")
                    errors.append(f"{type(e).__name__}: {str(e)[:120]}")
                    break
                got = [o for o in (to_offer(c, transport, pets, party) for c in cards) if o]
                nights = sorted({o["nights"] for o in got})
                print(f"[satur] {path} {stay}n p{n}: {len(cards)} cards, {len(got)} offers, nights={nights}")
                offers += got  # real terms either way; run.py drops lengths outside the criteria
                # no term of the asked length: the site fell back to other lengths, more pages won't help
                if len(cards) < 20 or not wanted & set(nights):
                    break
    all_nights = ",".join(str(n) for n in range(cfg["nights_min"], cfg["nights_max"] + 1))
    for code, path in far_pages(cfg):
        try:
            html = get(HOME + path, params={"termin": termin, "dlzka-pobytu": all_nights})
            cards = parse_cards(html)
            art = BeautifulSoup(html, "lxml").select_one("ul[data-category-target=productsListing] article")
            if art:
                diag(f"satur-{code}", re.sub(r"\s+", " ", str(art)))
        except Exception as e:
            print(f"[satur] {path}: {type(e).__name__} {str(e)[:120]}")
            errors.append(f"{type(e).__name__}: {str(e)[:120]}")
            continue
        got = [o for o in (to_offer(c, "flight", None, party) for c in cards) if o]
        print(f"[satur] {code} {path}: {len(cards)} cards, {len(got)} offers, nights={sorted({o['nights'] for o in got})}, "
              f"deps={sorted({o['departure'] or '?' for o in got})}, "
              f"prices={sorted(o['price_total'] for o in got)[:3]}")
        offers += got
    if errors and not offers:
        raise RuntimeError(f"all {len(errors)} satur.sk listing requests failed, first: {errors[0]}")
    return offers
