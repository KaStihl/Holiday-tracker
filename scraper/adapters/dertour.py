"""Shared code for the DERTOUR SK brand sites (kartago.sk, fischer.sk; eximtours.sk now redirects to kartago.sk).

The results pages are a JavaScript app; the data comes from the JSON endpoint the page itself calls,
/api/searchapi/getsearchresult (robots.txt of both sites allows /api/; fischer.sk only disallows /CMS*,
/WebServices/). Plain requests get the same JSON the browser gets, so no headless browser is needed.
Checked 2026-10-25 from GitHub runners (no challenge, 200 + JSON; the page's invisible reCAPTCHA only guards
forms). Terms: the brands' "Podmienky pre cestujúcich" (DERTOUR SK VOP PDFs, 01.10.2026) and the privacy pages
contain no text-and-data-mining reservation or scraping ban.

Query parameters (from the app's URL mapping in /Scripts/web/index.*.js):
  tt=1 flight, to=483|3789 BTS|VIE airport ids (see AIRPORT_IDS), dd/rd date range, nn=7|8|…|14 allowed nights, m=5 All Inclusive
  (incl. Ultra), ac1 adults, kc1 children, ka1=<ages joined by |> children ages (without ka1 the children count
  as infants!), d=<destination ids> (without it the API returns only per-country "categories"), pitg page size,
  pstg skip. All party values come from nastavenia.yml.
With ac1/kc1/ka1 every tour is priced for exactly that party: rooms[0].adults/children carry the ages
and per-person prices and tour.price.total is the sum -> price_exact. Each tour is one hotel with its cheapest
matching term.
Destination ids are not hard-coded: the categories call lists every country on sale for the criteria with its
destinationIds (2026-10-25 fixture: also SAE, Omán, Maldivy, Srí Lanka, Thajsko, Mexiko, Dominikánska republika,
Kapverdy, Tanzánia), and countries() keeps those listed in nastavenia.yml.
Brno (BRQ, departures_secondary): the API has no airport list, but tours asked without 'to' carry every
departure's fromId/fromIATA (2026-11-01, Turecko/Grécko/…: TAT 3437, KSC 1837, PRG 4312, BTS 483, BUD 489, BRQ 4305,
VIE 3789, PED 4308, …). Brno gets its own pass (to=4305: one categories call + page 1 per country, right after the
first round), so a cheaper Brno term never replaces the BTS/VIE one of the same hotel; the 40-call cap trims the
tail (second pages / 10–14 pass of the big countries) instead. First run (2026-11-01): Brno flies to Turecko,
Taliansko, Grécko, Španielsko, Bulharsko, Egypt, Tunisko (+ Čierna Hora/Albánsko listed, 0 tours) and all ~155 tours
were KARTAGO products – Fischer's pass stops after SEC_MISSES pages without an own-brand tour.
Kartago and Fischer search one shared inventory (both sites list ATCOM_Kartago and ATCOM_Fischer
products at the same prices), so each adapter keeps only its own brand's products to avoid duplicates.
"""

import math
import re
from urllib.parse import urlencode

from common import facilities, get, norm_board, norm_country
from config import approx_label, party_label, party_size, period_label

API = "/api/searchapi/getsearchresult"
AIRPORT_IDS = {"BTS": 483, "VIE": 3789, "BRQ": 4305, "BUD": 489, "KSC": 1837}  # fromId in the flight segments
AIRPORTS = "483|3789"  # BTS | VIE: fallback when no airport of 'departures' is known here
# departures_secondary airports searched in a pass of their own (approved 2026-11-01: Brno). BUD/KSC ids are known,
# add them here to search them too.
SECONDARY_ASKED = ("BRQ",)
SEC_MISSES = 2  # secondary pass stops after this many pages with only the other brand's tours (and none of ours)
PAGE = 50              # tours per API call (~1 MB JSON)
MAX_CALLS = 40         # tour pages per source and run (+1 categories call)
# (nights, max pages per country) – the 7–14 pass returns the cheapest stay (practically always 7 nights),
# a second 10–14 pass gives the longer stays. Calls are made in rounds (every country's first page, then
# second pages, then the 10–14 pass), so with ~20 countries the cap trims the extra pages of the big
# European countries, never a whole long-haul country.
PASSES = [((7, 14), 2), ((10, 14), 1)]
FISCHER_SOURCE = 256   # tour "dataSource" of FISCHER products (brand ATCOM_Fischer)


def primary_to(cfg):
    ids = [str(AIRPORT_IDS[c]) for c in cfg["departures"] if c in AIRPORT_IDS]
    return "|".join(ids) or AIRPORTS


def secondary_to(cfg):
    """'to' of the extra pass (Brno), or None."""
    ids = [str(AIRPORT_IDS[c]) for c in cfg.get("departures_secondary") or []
           if c in SECONDARY_ASKED and c in AIRPORT_IDS and c not in cfg["departures"]]
    return "|".join(ids) or None


def query(cfg, nights=None, dest=None, skip=0, to=None):
    lo, hi = nights or (cfg["nights_min"], cfg["nights_max"])
    lo, hi = max(lo, cfg["nights_min"]), min(hi, cfg["nights_max"])
    if lo > hi:
        lo, hi = cfg["nights_min"], cfg["nights_max"]
    q = {"tt": 1, "to": to or primary_to(cfg), "dd": cfg["date_from"].isoformat(), "rd": cfg["date_to"].isoformat(),
         "nn": "|".join(str(n) for n in range(lo, hi + 1)),
         "ac1": cfg["adults"], "kc1": len(cfg["children_ages"])}
    if cfg["children_ages"]:
        q["ka1"] = "|".join(str(a) for a in cfg["children_ages"])
    if set(cfg["boards_preferred"]) <= {"AI", "UAI"}:
        q["m"] = 5  # All Inclusive incl. Ultra; other preferred boards -> no meal filter
    if dest:
        q["d"] = dest
        q["pitg"] = PAGE
        if skip:
            q["pstg"] = skip
    return q


def deeplinks(home, path, cfg):
    label = (f"Letecky z Bratislavy/Viedne{', AI' if 'm' in query(cfg) else ''}, {period_label(cfg)}, "
             f"{cfg['nights_min']}–{cfg['nights_max']} nocí, {party_label(cfg)}")
    out = [{"transport": "flight", "label": label, "url": f"{home}{path}?{urlencode(query(cfg))}"}]
    sec = secondary_to(cfg)
    if sec == str(AIRPORT_IDS["BRQ"]):
        out.append({"transport": "flight", "label": label.replace("z Bratislavy/Viedne", "z Brna"),
                    "url": f"{home}{path}?{urlencode(query(cfg, to=sec))}"})
    return out


def countries(data, cfg):
    """[(code, name, destination ids, hotel count)] of the preferred countries from a categories response."""
    out = []
    for cat in data.get("categories") or []:
        for d in cat.get("destinations") or []:
            code = norm_country(d.get("name"))
            if code in cfg["countries"] and d.get("destinationIds"):
                out.append((code, d["name"], d["destinationIds"], d.get("hotelCount") or 0))
    return sorted(out, key=lambda c: (-cfg["countries"][c[0]], -c[3]))


def _board(meal):
    m = (meal or "").lower()
    if "ultra" in m and "all" in m:
        return "UAI"
    return norm_board(meal)


def to_offer(t, home, cfg):
    """One API tour -> offer dict (None when essential fields are missing)."""
    tour, h = t.get("tour") or {}, t.get("hotel") or {}
    rooms = tour.get("rooms") or []
    price = (tour.get("price") or {}).get("total")
    if not (h.get("name") and t.get("detailUrl") and rooms and price and (tour.get("date") or {}).get("from")):
        return None
    room = rooms[0]
    adults, kids = room.get("adults") or [], room.get("children") or []
    exact = (len(rooms) == 1 and len(adults) == cfg["adults"]
             and sorted(c.get("age") for c in kids) == sorted(cfg["children_ages"]))
    party = party_size(cfg)
    if not exact:  # never seen, but don't pass another party's price off as ours
        pp = (tour.get("price") or {}).get("adultPrice") or (adults[0].get("price") if adults else None)
        if not pp:
            return None
        price = pp * party
    disc = (tour.get("price") or {}).get("discount") or 0
    orig = price + disc if exact and disc > 0 else None
    fm = "First minute" if tour.get("isFirstMinute") else None
    seg = (((tour.get("flight") or {}).get("departure") or {}).get("segments") or [{}])[0]
    bc = h.get("breadcrumbs") or {}
    imgs = h.get("images") or []
    score = (h.get("trustYou") or {}).get("score")
    return {
        "hotel": h["name"].strip(), "url": home + t["detailUrl"],
        "image": imgs[0].get("previewImagePath") if imgs else None,
        "stars": h.get("starsCount") or None, "rating": round(score * 2, 1) if score else None,
        "country": bc.get("country"), "country_code": norm_country(bc.get("country")) or h.get("countryId"),
        "region": bc.get("destination"), "place": bc.get("area"),
        "board": _board(room.get("meal")), "transport": "flight",
        "departure": (seg.get("airport") or {}).get("fromIATA"),
        "date_from": tour["date"]["from"], "date_to": tour["date"].get("to"), "nights": tour.get("nightsCount"),
        "price_total": round(price), "price_original": round(orig) if orig else None,
        "discount_label": fm if exact else approx_label(cfg, fm),
        "pets_allowed": None,
        **({"price_exact": True} if exact else {"price_note": f"orientačne: cena za dospelého × {party}"}),
        **hotel_facts(h, room),
    }


BEACH_RE = re.compile(r"vzdialenos\w*\s+k\s+pl[aá][žz]i\s+(\d+)\s*m", re.I)


def hotel_facts(h, room):
    """Hotel attributes the API exposes (checked 2026-11-06 from a runner): hotel.tags ('Vzdialenosť k pláži 0 m',
    'Aquapark v hotelu', …), hotel.descriptions[].name ('Aquapark s tobogánmi', 'Detský klub s … animátorom',
    'Priamo pri piesočnatej pláži', …), hotel.gps {latitude, longitude}; the room name tells a family room.
    -> {"fac": [...codes], "beach_m": int, "gps": [lat, lon]} (only keys that are known). Used by the Side tab."""
    text = " · ".join([str(t) for t in h.get("tags") or []] +
                      [str(d.get("name") or "") for d in h.get("descriptions") or [] if isinstance(d, dict)])
    fac = set(facilities(text, ("aq", "kc", "pl"))) | set(facilities(room.get("name"), ("fr",)))
    out = {}
    m = BEACH_RE.search(text)
    if m:
        out["beach_m"] = int(m[1])
        if int(m[1]) <= 50:
            fac.add("pl")
    if fac:
        out["fac"] = sorted(fac)
    g = h.get("gps") or {}
    try:
        lat, lon = float(g["latitude"]), float(g["longitude"])
        if lat and lon and (h.get("countryId") == "TR" or "turec" in str((h.get("breadcrumbs") or {}).get("country", "")).lower()):
            out["gps"] = [round(lat, 5), round(lon, 5)]  # Turkey only (the Side tab), keeps offers.json small
    except (KeyError, TypeError, ValueError):
        pass
    return out


def _mine(t, fischer):
    return (t.get("dataSource") == FISCHER_SOURCE) == fischer


def plan(todo, cfg, extra=()):
    """Call order [(nights, country tuple, page, to)]: round 1 = page 1 of every country in the first pass, then page 1
    of every country of the secondary-airport pass (extra, Brno), then the remaining pages of the first pass, then the
    other passes; within a round by preference weight. A pass whose nights collapse to an already asked range
    (e.g. nights_max < 10) is skipped."""
    rounds, seen = [], set()
    for nights, max_pages in PASSES:
        nn = query(cfg, nights)["nn"]
        if nn in seen:
            continue
        seen.add(nn)
        for page in range(max_pages):
            rounds.append([(nights, c, page, None) for c in todo if page < (math.ceil(c[3] / PAGE) or 1)])
            if len(rounds) == 1 and extra:
                rounds.append([(nights, c, 0, secondary_to(cfg)) for c in extra])
    return [x for r in rounds for x in r]


def search(tag, home, cfg, fischer):
    """All countries from nastavenia.yml on sale, two night passes, own brand only. ≤ 1 + MAX_CALLS API calls."""
    hdr = {"Accept": "application/json", "Referer": home + "/"}
    if "flight" not in cfg["transports"]:
        return []
    cats = get(home + API, params=query(cfg), headers=hdr, as_json=True)
    todo = countries(cats, cfg)
    print(f"[{tag}] {len(todo)} countries: " + ", ".join(f"{c[1]} {c[3]}" for c in todo))
    missing = sorted(set(cfg["countries"]) - {c[0] for c in todo})
    if missing:
        print(f"[{tag}] not on sale for these criteria: {', '.join(missing)}")
    extra, calls = [], 0
    sec = secondary_to(cfg)
    if sec:  # countries flown to from the secondary airport (Brno): one categories call
        calls += 1
        try:
            extra = countries(get(home + API, params=query(cfg, to=sec), headers=hdr, as_json=True), cfg)
            print(f"[{tag}] to={sec}: {len(extra)} countries: " + ", ".join(f"{c[1]} {c[3]}" for c in extra))
        except Exception as e:
            print(f"[{tag}] to={sec} categories: {type(e).__name__} {str(e)[:120]}")
            if "403" in str(e) or "429" in str(e):
                raise
    offers, errors, other = [], [], 0
    done = set()  # (nights, code, to): pass finished (last page reached or failed)
    foreign = set()  # countries whose first page had no own-brand product: the other brand sells them, skip
    sec_own, sec_misses = 0, 0  # secondary pass: own-brand offers / pages with only the other brand's tours
    for nights, (code, name, dest, count), page, to in plan(todo, cfg, extra):
        if calls >= MAX_CALLS:
            print(f"[{tag}] call budget {MAX_CALLS} reached")
            break
        if (nights, code, to) in done or code in foreign:
            continue
        if to and not sec_own and sec_misses >= SEC_MISSES:
            continue  # 2026-11-01: every Brno product was KARTAGO's, Fischer pages had none – don't spend its budget
        calls += 1
        try:
            data = get(home + API, params=query(cfg, nights, dest, page * PAGE, to), headers=hdr, as_json=True)
        except Exception as e:
            print(f"[{tag}] {name} {nights} p{page + 1}{' to=' + to if to else ''}: {type(e).__name__} {str(e)[:120]}")
            errors.append(f"{type(e).__name__}: {str(e)[:120]}")
            if "403" in str(e) or "429" in str(e):  # blocked / rate limited: stop, don't push on
                raise
            done.add((nights, code, to))
            continue
        tours = data.get("tours") or []
        own = [t for t in tours if _mine(t, fischer)]
        other += len(tours) - len(own)
        got = [o for o in (to_offer(t, home, cfg) for t in own) if o]
        exact = sum(bool(o.get("price_exact")) for o in got)
        prices = sorted(o["price_total"] for o in got)
        print(f"[{tag}] {name} {nights[0]}-{nights[1]}n p{page + 1}{' to=' + to if to else ''}: {len(tours)}/{data.get('toursCount')} tours, "
              f"{len(got)} own-brand offers ({exact} exact), nights={sorted({o['nights'] for o in got})}, "
              f"price {prices[0] if prices else '-'}–{prices[-1] if prices else '-'}"
              + (f", departures={sorted({o['departure'] or '?' for o in got})}" if to else ""))
        offers += got
        if not own and tours and not page and not to:
            foreign.add(code)
        if to:
            sec_own += len(own)
            sec_misses += bool(tours and not own)
        if len(tours) < PAGE or (page + 1) * PAGE >= (data.get("toursCount") or 0):
            done.add((nights, code, to))
    print(f"[{tag}] {calls + 1} API calls, {len(offers)} offers, {other} other-brand tours skipped"
          + (f", other brand only: {', '.join(sorted(foreign))}" if foreign else ""))
    if errors and not offers:
        raise RuntimeError(f"all {len(errors)} {tag} API requests failed, first: {errors[0]}")
    return offers


# --- watched hotels (sledovane_hotely) ---------------------------------------------------------------------------
# The search API has no hotel-name filter (checked 2026-10-30: hid/h/HID/hi/ft/q/text are ignored, no fulltext
# endpoint under /api/), but a whole country fits in a few pages of 100 tours (Turecko without the AI filter:
# 315 hotels = 4 calls). watch() reads the categories (1 call) and then every page of the countries where a watched
# hotel was seen (this run or the previous one, any agency), any board, ≤ WATCH_CALLS calls, and keeps the own-brand
# tours whose hotel matches. Kartago and Fischer each read the shared inventory for their own brand.
WATCH_CALLS = 10
WATCH_PAGE = 100


def watch(tag, home, cfg, fischer, terms, hints):
    from watch import match
    if "flight" not in cfg["transports"]:
        return []
    codes = []
    for t in terms:
        for h in hints.get(t, []):
            if h.get("country_code") in cfg["countries"] and h["country_code"] not in codes:
                codes.append(h["country_code"])
    if not codes:
        return []
    hdr = {"Accept": "application/json", "Referer": home + "/"}
    to = "|".join(x for x in (primary_to(cfg), secondary_to(cfg)) if x)  # any asked airport, Brno included
    q = query(cfg, to=to)
    q.pop("m", None)
    cats = get(home + API, params=q, headers=hdr, as_json=True)
    calls, offers = 1, []
    todo = [c for c in countries(cats, cfg) if c[0] in codes]
    for code, name, dest, count in todo:
        for page in range(math.ceil(count / WATCH_PAGE) or 1):
            if calls >= WATCH_CALLS:
                print(f"[{tag}] watch: call budget {WATCH_CALLS} reached")
                return offers
            calls += 1
            q = query(cfg, None, dest, page * WATCH_PAGE, to)
            q.pop("m", None)
            q["pitg"] = WATCH_PAGE
            try:
                data = get(home + API, params=q, headers=hdr, as_json=True)
            except Exception as e:
                print(f"[{tag}] watch {name} p{page + 1}: {type(e).__name__} {str(e)[:120]}")
                break
            tours = data.get("tours") or []
            hits = [t for t in tours if _mine(t, fischer) and match((t.get("hotel") or {}).get("name"), terms)]
            got = [o for o in (to_offer(t, home, cfg) for t in hits) if o]
            print(f"[{tag}] watch {name} p{page + 1}: {len(tours)}/{data.get('toursCount')} tours, {len(got)} watched: "
                  + ", ".join(f"{o['hotel']} {o['price_total']}" for o in got))
            offers += got
            if len(tours) < WATCH_PAGE:
                break
    return offers


# --- extra parties (skupiny in nastavenia.yml) -------------------------------------------------------------------
# Prices depend on the party (ac1/kc1/ka1), so another party needs its own requests. To stay cheap it reuses what the
# primary pass found: one categories call (destination ids for this party) and page 1 (50 cheapest tours, 7–14
# nights, BTS/VIE) of the countries where this brand had primary offers, best preference weight first,
# ≤ EXTRA_CALLS requests per party (2 extra parties: ≤ 16 calls on top of the ≤ 52 of search() + watch()).
EXTRA_CALLS = 8


def extra_plan(cats, cfg, primary):
    """[(code, name, destination ids, count)] for a party pass: countries this brand sold in the primary pass."""
    from collections import Counter
    have = Counter(o.get("country_code") for o in primary)
    todo = [c for c in countries(cats, cfg) if have[c[0]]]
    return sorted(todo, key=lambda c: (-cfg["countries"][c[0]], -have[c[0]]))[:EXTRA_CALLS - 1]


def search_party(tag, home, cfg, fischer, primary):
    """run.py hook for an extra party: exact prices for cfg's party, ≤ EXTRA_CALLS API calls."""
    if "flight" not in cfg["transports"] or not primary:
        return []
    hdr = {"Accept": "application/json", "Referer": home + "/"}
    cats = get(home + API, params=query(cfg), headers=hdr, as_json=True)
    offers = []
    for code, name, dest, count in extra_plan(cats, cfg, primary):
        try:
            data = get(home + API, params=query(cfg, PASSES[0][0], dest), headers=hdr, as_json=True)
        except Exception as e:
            print(f"[{tag}] party {party_label(cfg)} {name}: {type(e).__name__} {str(e)[:120]}")
            if "403" in str(e) or "429" in str(e):
                break
            continue
        got = [o for o in (to_offer(t, home, cfg) for t in data.get("tours") or [] if _mine(t, fischer)) if o]
        print(f"[{tag}] party {party_label(cfg)} {name}: {len(data.get('tours') or [])} tours, {len(got)} own-brand "
              f"offers ({sum(bool(o.get('price_exact')) for o in got)} exact)")
        offers += got
    return offers
