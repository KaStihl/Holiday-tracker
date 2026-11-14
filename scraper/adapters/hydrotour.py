"""Hydrotour (hydrotour.sk) – Slovak tour operator (Bratislava), flights from Bratislava, Košice and Poprad.

Checked 2026-11-14 from GitHub runners:
- hydrotour.cz is not a separate shop: www.hydrotour.cz and hydrotour.cz redirect to https://www.hydrotour.sk/ (even
  /robots.txt), so this one adapter covers both.
- robots.txt: User-agent * disallows /letove-casy, /api, /app/dotaznik, /oblubene, /unsubscribe, /objednavka-*,
  /objednavka/uprava-rezervacie*, /s/, /p/, /admin/camt2gpc, /pobocka/, /predajca/ (SemrushBot: everything). The
  site's own search JSON lives under /japi/ (POST /japi/ISearchApi/searchTerminyRaw, what the /dovolenky search page
  calls) and /sapi/ (GET hotel data) – neither is disallowed (/api is a different path prefix). This adapter only
  uses /japi/ISearchApi/searchTerminyRaw and one home page (/), never /api, /s/, /p/ or the booking pages.
- Terms: Všeobecné podmienky (/vseobecne-podmienky), Všeobecné podmienky zliav, Zmluvné podmienky pre darčekové
  poukazy, Ochrana osobných údajov and Cookies contain no clause on scraping, robots, automated access or a
  text-and-data-mining reservation (searched for scrap/robot/automat/vyťaž/dolov/data mining/kopír/databáz).
- No bot protection: plain requests get 200 with content, no challenge script, no cookies needed.
- Results: the listing pages (/dovolenky/<country>[/<region>]) are prerendered HTML with each hotel's 3 nearest
  terms (May/June), not filterable server-side; the search page loads its data with searchTerminyRaw, JSON
  {hotely: [hotel], terminy: [term]}. The request takes the search form's filter: datumOd/datumDo (YYYY-MM-DD,
  departure from datumOd on), dni (trip length in DAYS = nights + 1), cestujuci ([[18, 18]] = 2 adults; children as
  their age, [[18, 10, 12]] = 1 adult + 2 children – honoured: fewer hotels fit that room), staty/oblasti (ids),
  hotely (hotel ids) and terminyPocet. The answer holds at most 3 terms per hotel – the earliest from datumOd (asking
  terminyPocet 50 still gave 3) – so search() asks with datumOd stepping a week at a time through the period
  (WINDOWS requests, the whole catalogue in each, ~160 hotels / 0.7 MB) and run.py drops the duplicates.
- Prices: cenaTotal is the price per ADULT incl. airport fees and fuel ("s popl. / dosp. os." on the cards; cenaZlava
  without them, cenaKatalog the catalogue price without them) for the asked room occupancy. The children's prices
  only show in the booking flow (/objednavka*, disallowed), so the party total is approximated as per-adult price ×
  party size (children usually cost less -> the real total is lower) and is never price_exact. Prices are in EUR.
- Departures: each term lists its airports (odlety: letisko1 = airport id of the hotel's letiska list: 1 Bratislava
  BTS, 2 Košice KSC, 4 Poprad TAT), each with its own term id; no Vienna, Brno or Budapest. One offer per term and
  airport (same price); run.py keeps BTS and KSC (Poprad is not in nastavenia.yml).
- Royal Alhambra Palace: in the catalogue (hotel id 215, /dovolenky/turecko/side/royal-alhambra-palace), but with no
  term on sale (hotel-detail terminy [], searchTerminyRaw hotely=[215] empty, JSON-LD "SoldOut"); its sister hotels
  Royal Dragon (217) and Royal Taj Mahal (216) have July 2027 terms from BTS/KSC/TAT.
"""

import json
import re
from datetime import timedelta
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from common import get, norm_board, norm_country
from config import approx_label, party_label, party_size, period_label
from watch import match

NAME = "Hydrotour"
HOME = "https://www.hydrotour.sk"
SEARCH = HOME + "/japi/ISearchApi/searchTerminyRaw"
WINDOWS = 9  # weekly datumOd steps through Jul–Aug; per party
TERMS_PER_HOTEL = 3  # what the site answers per hotel and request anyway
# Board texts in order of "less included" first: a hotel with several boards gets its cheapest one, which is the
# one its "od" (from) price is for.
BOARD_ORDER = ["RO", "BB", "HB", "FB", "AI", "UAI"]
# Hotel pages of watched hotels known to be in the Hydrotour catalogue (watch_links when watch() found nothing).
HOTEL_PAGES = [("Royal Alhambra Palace", "/dovolenky/turecko/side/royal-alhambra-palace"),
               ("Royal Dragon", "/dovolenky/turecko/side/royal-dragon")]
_found = {}  # watched hotel pages found by watch() this run: {path: name}


def cestujuci(cfg):
    return [[18] * cfg["adults"] + [int(a) for a in cfg["children_ages"]]]


def body(cfg, start):
    """searchTerminyRaw filter: departures from `start` to date_to (datumDo a trip length later, in case it bounds the
    return), every allowed trip length, the configured party."""
    end = cfg["date_to"] + timedelta(days=cfg["nights_max"] + 1)
    return {"datumOd": start.isoformat(), "datumDo": end.isoformat(),
            "dni": list(range(cfg["nights_min"] + 1, cfg["nights_max"] + 2)), "cestujuci": cestujuci(cfg),
            "terminyPocet": TERMS_PER_HOTEL}


def windows(cfg):
    """datumOd of each request: date_from, then a week later each, at most WINDOWS, not after date_to."""
    out, d = [], cfg["date_from"]
    while d <= cfg["date_to"] and len(out) < WINDOWS:
        out.append(d)
        d += timedelta(days=7)
    return out


def _board(strava):
    codes = [c for c in (norm_board(s.get("text")) for s in strava or []) if c]
    return min(codes, key=BOARD_ORDER.index) if codes else None


def to_offers(data, cfg):
    """searchTerminyRaw answer -> offer dicts (one per term and departure airport). Countries not in nastavenia.yml,
    round trips and terms without a known airport are skipped."""
    hotels = {h["hotelId"]: h for h in data.get("hotely") or []}
    n = party_size(cfg)
    out = []
    for t in data.get("terminy") or []:
        h = hotels.get(t.get("hotelId"))
        if not h or h.get("poznavaci") or not h.get("pageUrl"):
            continue
        country = (h.get("stat") or {}).get("nadpis")
        cc = norm_country(country)
        if cc not in cfg["countries"]:
            continue
        per = t.get("cenaTotal") or t.get("cenaZlava")
        if not per or t.get("idTypDopravaTam", 40) != 40:  # 40 = flight
            continue
        fees = (t.get("cenaTotal") or 0) - (t.get("cenaZlava") or 0) if t.get("cenaTotal") else 0
        orig = (t["cenaKatalog"] + fees) if t.get("cenaKatalog") else None
        airports = {a["id"]: a.get("kod") for a in h.get("letiska") or []}
        promo = "First minute" if t.get("firstMinute") else "Last minute" if t.get("lastMinute") else None
        if promo and t.get("zlavaPercenta"):
            promo += f" −{t['zlavaPercenta']} %"
        region = (h.get("oblast") or {}).get("nadpis")
        for od in t.get("odlety") or [{"terminId": t["id"], "letisko1": None}]:
            dep = airports.get(od.get("letisko1"))
            if not dep:
                continue
            out.append({
                "hotel": h.get("nazov"), "url": f"{HOME}{h['pageUrl']}#{od.get('terminId') or t['id']}",
                "image": h.get("obrazokUrl"), "stars": h.get("hviezdy") or None, "rating": None,
                "country": country, "country_code": cc, "region": region, "place": region,
                "board": _board(h.get("strava")), "transport": "flight", "departure": dep,
                "date_from": str(t.get("datumOd"))[:10], "date_to": str(t.get("datumDo"))[:10],
                "nights": t.get("noci") or (t.get("dni") or 0) - 1,
                "price_total": round(per * n), "price_original": round(orig * n) if orig and orig > per else None,
                "discount_label": approx_label(cfg, promo),
                "price_note": f"orientačne: cena za dospelého s poplatkami × {n}",
                "pets_allowed": None,
            })
    return out


def _windows_search(cfg, tag):
    offers, errors = [], []
    for start in windows(cfg):
        try:
            data = get(SEARCH, method="POST", json_body=[body(cfg, start)], as_json=True, timeout=60,
                       headers={"Content-Type": "application/json"})
        except Exception as e:
            print(f"[hydrotour] {tag} from {start}: {type(e).__name__} {str(e)[:120]}")
            errors.append(e)
            if "403" in str(e) or "429" in str(e):
                break
            continue
        got = to_offers(data or {}, cfg)
        deps = sorted({o["departure"] for o in got})
        print(f"[hydrotour] {tag} from {start}: {len(data.get('hotely') or [])} hotels, "
              f"{len(data.get('terminy') or [])} terms -> {len(got)} offers, departures {deps}")
        offers += got
    if errors and not offers:
        raise RuntimeError(f"all hydrotour.sk search requests failed, first: {type(errors[0]).__name__}: "
                           f"{str(errors[0])[:150]}")
    return offers


def search(cfg):
    if "flight" not in cfg["transports"]:
        return []
    return _windows_search(cfg, party_label(cfg))


def search_party(cfg, primary):
    """run.py hook for an extra party: the same weekly requests with that party's room occupancy (per-adult prices
    and which hotels have a room for it differ by party); still per-adult price × party size."""
    if "flight" not in cfg["transports"] or not primary:
        return []
    return _windows_search(cfg, party_label(cfg))


# --- watched hotels (sledovane_hotely) ---------------------------------------------------------------------------
# Every page embeds the site's route list (<script id="sapi_routes">: path, type HotelDetail, hotel id). watch() reads
# it from the home page (1 request), matches the watched names against the hotel names in the paths and asks
# searchTerminyRaw for just those hotel ids over the whole period (1 request), so a watched hotel the weekly listing
# requests missed still shows up, and the log says when a watched hotel is in the catalogue but not on sale.

def parse_routes(html):
    """[(path, hotel id, name from the path)] of the HotelDetail routes of a page."""
    soup = BeautifulSoup(html, "lxml")
    s = soup.find("script", id="sapi_routes")
    if s is None or not s.string:
        return []
    out = []
    for r in json.loads(s.string):
        if r.get("type") == "HotelDetail" and r.get("id") and r.get("path"):
            name = r["path"].rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
            out.append((r["path"], int(r["id"]), name))
    return out


def watched_routes(routes, terms):
    return [(p, i, n) for p, i, n in routes if match(n, terms)]


def watch(cfg, terms, hints=None):
    if "flight" not in cfg["transports"]:
        return []
    hits = watched_routes(parse_routes(get(HOME + "/")), terms)
    print(f"[hydrotour] watch: in the catalogue: {[(p.rsplit('/', 1)[-1], i) for p, i, _ in hits] or 'none'}")
    if not hits:
        return []
    _found.update({p: n for p, _, n in hits})
    q = dict(body(cfg, cfg["date_from"]), hotely=[i for _, i, _ in hits])
    data = get(SEARCH, method="POST", json_body=[q], as_json=True, timeout=60,
               headers={"Content-Type": "application/json"})
    got = to_offers(data or {}, cfg)
    on_sale = {h.get("hotelId") for h in data.get("hotely") or []}
    for p, i, _ in hits:
        mine = [o for o in got if o["url"].startswith(HOME + p + "#")]
        print(f"[hydrotour] watch {p.rsplit('/', 1)[-1]} ({i}): "
              + (", ".join(f"{o['departure']} {o['date_from']} {o['nights']}n {o['board']} {o['price_total']} €"
                           for o in mine) if mine else
                 "on sale but no term in the period" if i in on_sale else "no term on sale"))
    return got


def watch_links(cfg, term, hints):
    pages = [(n, p) for p, n in _found.items()] or [(n, p) for n, p in HOTEL_PAGES]
    return [{"label": f"{name.title() if name.islower() else name} na hydrotour.sk", "url": HOME + path}
            for name, path in pages if match(name, [term])]


def deeplinks(cfg):
    q = {"datumOd": cfg["date_from"].isoformat(), "datumDo": cfg["date_to"].isoformat(),
         "cestujuci": ",".join(["dospely"] * cfg["adults"] + [f"dieta-{a}" for a in cfg["children_ages"]])}
    return [{"transport": "flight",
             "label": f"Hydrotour: dovolenky {period_label(cfg)}, {party_label(cfg)}, odlety z Bratislavy/Košíc",
             "url": f"{HOME}/dovolenky?{urlencode(q)}"},
            {"transport": "flight", "label": "Hydrotour: Turecko – Side", "url": HOME + "/dovolenky/turecko/side"}]
