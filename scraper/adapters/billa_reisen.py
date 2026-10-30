"""BILLA Reisen (billareisen.at, ITS BILLA Reisen = DERTOUR Austria / REWE) – packages from Vienna (VIE).

Checked 2026-10-30 from GitHub runners:
- robots.txt: for '*' only /buchen/ is disallowed (a few named SEO/AI bots are blocked completely, not us);
  /Pauschalreisen/Angebote.html is allowed. No challenge (nginx, plain 200), no captcha on result pages.
- Terms (/Service/AGB.html, /Service/Impressum.html): no text-and-data-mining reservation, no scraping ban.
- Results are server-rendered HTML: /Pauschalreisen/Angebote.html lists ~60 hotels per page (ppn=0,1,… pages),
  each card with the cheapest matching term as text ("z.B. 7 Nächte, ab 24.8.2027, Doppelzimmer, Alles
  Inklusive, ab Wien"), a "p.P. ab € 553,-" per-person price, the strike price and a HolidayCheck rating.
URL parameters (from the site's own result links): pdf=<destination id> (ids from the destination filter tree,
see COUNTRIES), pdaf=VIE departure airport, psdf/pedf travel window, pnnfl/pnnfh nights, na/pna adults,
pbtf=ai All Inclusive (incl. "Alles Inklusive plus"), ps=pr cheapest first, ppn page (0-based).
Children: the list ignores every child-age parameter we tried (pnc stays 0 in the echoed psbbr), so we ask for
2 adults and show per-person price × party size, labelled "orientačne" like satur.py / cedok.py.
"""

import re
from datetime import date
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from adapters import at_common
from common import get, parse_price
from config import approx_label, party_size, period_label

NAME = "BILLA Reisen"
HOME = "https://www.billareisen.at"
PATH = "/Pauschalreisen/Angebote.html"
AIRPORT = "VIE"  # Billa also lists GRZ/LNZ/SZG/INN/BTS… departures; VIE is the one that matters here
PAGE = 60          # hotels per result page (58–60 seen)
MAX_CALLS = 45     # result pages per run (~1.6 MB each)
ADULTS = 2         # per-person price at 2 adults, see module docstring

# country code -> destination ids of the filter tree on the result page (checked 2026-10-30). A country whose
# id disappears just yields no cards (logged); the country of each card is read from its breadcrumb anyway.
COUNTRIES = {
    "HR": "3380065", "TR": "3380096", "CY": "3380099", "IT": "3380051", "GR": "3380037",
    "ES": "3380076,3380081,3380088",  # Balearen, Kanaren, Festland
    "MT": "3380071", "PT": "3380073", "ME": "3380072", "AL": "3380033", "BG": "3380034",
    "EG": "3380106", "TN": "3380114", "MA": "3380111", "KE": "3380120", "TZ": "3380120",
    "AE": "3380178", "OM": "3380177", "MV": "3380144", "MU": "3380145", "SC": "3380150",
    "LK": "3380159", "TH": "3380164", "ID": "3380155", "VN": "3380176",
    "DO": "3380125", "MX": "3380137", "CU": "3380131",
}
TERM_RE = re.compile(r"(\d+)\s*N[äa]cht\w*,\s*ab\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", re.I)


def ai_only(cfg):
    return set(cfg["boards_preferred"]) <= {"AI", "UAI"}


def query(cfg, dest=None, page=0, adults=ADULTS):
    q = {"ttid": "PF", "bdid": "ib", "pttid": "PF", "ptoj": "PF", "dpfebl": "tr,dd,da"}
    if dest:
        q["pdf"] = dest
    q.update({"pdaf": AIRPORT, "dft": "apx", "psdf": cfg["date_from"].isoformat(), "pedf": cfg["date_to"].isoformat(),
              "pnnfl": cfg["nights_min"], "pnnfh": cfg["nights_max"], "na": adults, "pna": adults, "ptf": 1})
    if ai_only(cfg):
        q["pbtf"] = "ai"
    q.update({"ps": "pr", "pdm": "pp", "idvfmb": 1})
    if page:
        q["ppn"] = page
    return q


def deeplinks(cfg):
    ai = ", AI" if ai_only(cfg) else ""
    return [{"transport": "flight",
             "label": f"Letecky z Viedne{ai}, {period_label(cfg)}, {cfg['nights_min']}–{cfg['nights_max']} nocí "
                      f"(všetky destinácie; osoby a deti si nastavte na stránke)",
             "url": f"{HOME}{PATH}?{urlencode(query(cfg))}"}]


def country_of(breadcrumb):
    return at_common.country(breadcrumb)


def board_of(text):
    return at_common.board(text)


def _abs(url):
    if not url:
        return None
    return "https:" + url if url.startswith("//") else (HOME + url if url.startswith("/") else url)


def parse_page(html, cfg):
    """(offers, page count) from one result page."""
    soup = BeautifulSoup(html, "lxml")
    m = re.search(r"Seite 1 von (\d+)", html)
    pages = int(m[1]) if m else 1
    party = party_size(cfg)
    offers = []
    for card in soup.select("div.ITS_OBJ_product"):
        a = card.select_one("h3.ITS_OBJ_product-desc__title a[href]")
        price = card.select_one(".ITS_OBJ_product-desc__cta .ITS_price")
        copy = card.select_one(".ITS_OBJ_product-desc__copy")
        if not (a and price and copy):
            continue
        text = " ".join(copy.get_text(" ").split())
        tm = TERM_RE.search(text)
        pp = parse_price(price.get_text())
        if not tm or not pp:
            continue
        nights, d, mth, y = (int(x) for x in tm.groups())
        try:
            start = date(y, mth, d)
        except ValueError:
            continue
        parts = [p.strip() for p in text.split(",")]
        board = board_of(parts[3] if len(parts) > 3 else text)
        dep = at_common.airport(text.rsplit(", ab ", 1)[-1]) if ", ab " in text else None
        crumb = card.select_one(".ITS_OBJ_product-desc__text > div")
        crumb = " ".join(crumb.get_text(" ").split()) if crumb else ""
        geo = [x.strip() for x in crumb.split("•")]
        stars = card.select_one('[itemprop="starRating"] meta[itemprop="ratingValue"]')
        hc = card.select_one(".ITS_OBJ-holidaycheck__sun--rating-value")
        strike = card.select_one(".ITS_OBJ_txt-price--strikethrough .ITS_OBJ_txt-price__value")
        orig_pp = parse_price(strike.get_text()) if strike else None
        callout = card.select_one(".ITS_OBJ_txt-callout--percent .ITS_OBJ_txt-callout__text")
        img = card.select_one(".ITS_OBJ_product-photo img[src]")
        rating = None
        if hc:
            try:
                rating = round(float(hc.get_text().strip().replace(",", ".")) * 10 / 6, 1)
            except ValueError:
                pass
        pct = re.sub(r"[^\d]", "", callout.get_text()) if callout else ""
        promo = f"Zľava {pct} %" if pct else None
        offers.append({
            "hotel": " ".join(a.get_text(" ").split()), "url": _abs(a["href"]), "image": _abs(img["src"]) if img else None,
            "stars": float(stars["content"]) if stars and stars.get("content") else None, "rating": rating,
            "country": geo[0] if geo else None, "country_code": country_of(crumb) if crumb else None,
            "region": geo[1] if len(geo) > 1 else None, "place": geo[2] if len(geo) > 2 else None,
            "board": board, "transport": "flight", "departure": dep,
            "date_from": start.isoformat(), "date_to": date.fromordinal(start.toordinal() + nights).isoformat(),
            "nights": nights, "price_total": pp * party,
            "price_original": orig_pp * party if orig_pp and orig_pp > pp else None,
            "discount_label": approx_label(cfg, promo), "pets_allowed": None,
            "price_note": f"orientačne: cena za osobu pri {ADULTS} dospelých × {party}",
        })
    return offers, pages


def plan(cfg):
    """[(code, dest ids, page)]: page 0 of every configured country (by weight), then page 1 of the favourites."""
    todo, seen = [], set()
    for code, w in sorted(cfg["countries"].items(), key=lambda kv: -kv[1]):
        dest = COUNTRIES.get(code)
        if dest and dest not in seen:
            seen.add(dest)
            todo.append((code, dest, w))
    first = [(c, d, 0) for c, d, w in todo]
    second = [(c, d, 1) for c, d, w in todo if w >= 0.9]
    return first + second


def search(cfg):
    if "flight" not in cfg["transports"]:
        return []
    offers, calls, errors = [], 0, []
    pages_of = {}
    for code, dest, page in plan(cfg):
        if calls >= MAX_CALLS:
            print(f"[billa_reisen] call budget {MAX_CALLS} reached")
            break
        if page and pages_of.get(dest, 1) <= page:
            continue
        calls += 1
        try:
            html = get(HOME + PATH, params=query(cfg, dest, page))
        except Exception as e:
            print(f"[billa_reisen] {code} p{page + 1}: {type(e).__name__} {str(e)[:120]}")
            errors.append(f"{type(e).__name__}: {str(e)[:120]}")
            if "403" in str(e) or "429" in str(e):
                raise
            continue
        got, pages = parse_page(html, cfg)
        pages_of[dest] = pages
        prices = sorted(o["price_total"] for o in got)
        print(f"[billa_reisen] {code} p{page + 1}/{pages}: {len(got)} offers, countries "
              f"{sorted({o['country_code'] or '?' for o in got})}, price {prices[0] if prices else '-'}–"
              f"{prices[-1] if prices else '-'}")
        offers += got
    print(f"[billa_reisen] {calls} requests, {len(offers)} offers")
    if errors and not offers:
        raise RuntimeError(f"all {len(errors)} BILLA Reisen requests failed, first: {errors[0]}")
    return offers
