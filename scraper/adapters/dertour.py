"""Shared code for the DERTOUR SK brand sites (kartago.sk, fischer.sk; eximtours.sk now redirects to kartago.sk).

The results pages are a JavaScript app; the data comes from the JSON endpoint the page itself calls,
/api/searchapi/getsearchresult (robots.txt of both sites allows /api/; fischer.sk only disallows /CMS*,
/WebServices/). Plain requests get the same JSON the browser gets, so no headless browser is needed.
Checked 2026-10-25 from GitHub runners (no challenge, 200 + JSON; the page's invisible reCAPTCHA only guards
forms). Terms: the brands' "Podmienky pre cestujúcich" (DERTOUR SK VOP PDFs, 01.10.2026) and the privacy pages
contain no text-and-data-mining reservation or scraping ban.

Query parameters (from the app's URL mapping in /Scripts/web/index.*.js):
  tt=1 flight, to=483|3789 BTS|VIE airport ids, dd/rd date range, nn=7|8|…|14 allowed nights, m=5 All Inclusive
  (incl. Ultra), ac1 adults, kc1 children, ka1=<ages joined by |> children ages (without ka1 the children count
  as infants!), d=<destination ids> (without it the API returns only per-country "categories"), pitg page size,
  pstg skip. All party values come from nastavenia.yml.
With ac1/kc1/ka1 every tour is priced for exactly that party: rooms[0].adults/children carry the ages
and per-person prices and tour.price.total is the sum -> price_exact. Each tour is one hotel with its cheapest
matching term.
Destination ids are not hard-coded: the categories call lists every country on sale for the criteria with its
destinationIds (2026-10-25 fixture: also SAE, Omán, Maldivy, Srí Lanka, Thajsko, Mexiko, Dominikánska republika,
Kapverdy, Tanzánia), and countries() keeps those listed in nastavenia.yml.
Kartago and Fischer search one shared inventory (both sites list ATCOM_Kartago and ATCOM_Fischer
products at the same prices), so each adapter keeps only its own brand's products to avoid duplicates.
"""

import math
from urllib.parse import urlencode

from common import get, norm_board, norm_country
from config import approx_label, party_label, party_size, period_label

API = "/api/searchapi/getsearchresult"
AIRPORTS = "483|3789"  # BTS | VIE (fromId in the flight segments)
PAGE = 50              # tours per API call (~1 MB JSON)
MAX_CALLS = 40         # tour pages per source and run (+1 categories call)
# (nights, max pages per country) – the 7–14 pass returns the cheapest stay (practically always 7 nights),
# a second 10–14 pass gives the longer stays. Calls are made in rounds (every country's first page, then
# second pages, then the 10–14 pass), so with ~20 countries the cap trims the extra pages of the big
# European countries, never a whole long-haul country.
PASSES = [((7, 14), 2), ((10, 14), 1)]
FISCHER_SOURCE = 256   # tour "dataSource" of FISCHER products (brand ATCOM_Fischer)


def query(cfg, nights=None, dest=None, skip=0):
    lo, hi = nights or (cfg["nights_min"], cfg["nights_max"])
    lo, hi = max(lo, cfg["nights_min"]), min(hi, cfg["nights_max"])
    if lo > hi:
        lo, hi = cfg["nights_min"], cfg["nights_max"]
    q = {"tt": 1, "to": AIRPORTS, "dd": cfg["date_from"].isoformat(), "rd": cfg["date_to"].isoformat(),
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
    return [{"transport": "flight", "label": label, "url": f"{home}{path}?{urlencode(query(cfg))}"}]


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
    }


def _mine(t, fischer):
    return (t.get("dataSource") == FISCHER_SOURCE) == fischer


def plan(todo, cfg):
    """Call order [(nights, country tuple, page)]: round 1 = page 1 of every country in the first pass, then the
    remaining pages of that pass, then the other passes; within a round by preference weight. A pass whose
    nights collapse to an already asked range (e.g. nights_max < 10) is skipped."""
    rounds, seen = [], set()
    for nights, max_pages in PASSES:
        nn = query(cfg, nights)["nn"]
        if nn in seen:
            continue
        seen.add(nn)
        for page in range(max_pages):
            rounds.append([(nights, c, page) for c in todo if page < (math.ceil(c[3] / PAGE) or 1)])
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
    offers, calls, errors, other = [], 0, [], 0
    done = set()  # (nights, code): pass finished (last page reached or failed)
    foreign = set()  # countries whose first page had no own-brand product: the other brand sells them, skip
    for nights, (code, name, dest, count), page in plan(todo, cfg):
        if calls >= MAX_CALLS:
            print(f"[{tag}] call budget {MAX_CALLS} reached")
            break
        if (nights, code) in done or code in foreign:
            continue
        calls += 1
        try:
            data = get(home + API, params=query(cfg, nights, dest, page * PAGE), headers=hdr, as_json=True)
        except Exception as e:
            print(f"[{tag}] {name} {nights} p{page + 1}: {type(e).__name__} {str(e)[:120]}")
            errors.append(f"{type(e).__name__}: {str(e)[:120]}")
            if "403" in str(e) or "429" in str(e):  # blocked / rate limited: stop, don't push on
                raise
            done.add((nights, code))
            continue
        tours = data.get("tours") or []
        own = [t for t in tours if _mine(t, fischer)]
        other += len(tours) - len(own)
        got = [o for o in (to_offer(t, home, cfg) for t in own) if o]
        exact = sum(bool(o.get("price_exact")) for o in got)
        prices = sorted(o["price_total"] for o in got)
        print(f"[{tag}] {name} {nights[0]}-{nights[1]}n p{page + 1}: {len(tours)}/{data.get('toursCount')} tours, "
              f"{len(got)} own-brand offers ({exact} exact), nights={sorted({o['nights'] for o in got})}, "
              f"price {prices[0] if prices else '-'}–{prices[-1] if prices else '-'}")
        offers += got
        if not own and tours and not page:
            foreign.add(code)
        if len(tours) < PAGE or (page + 1) * PAGE >= (data.get("toursCount") or 0):
            done.add((nights, code))
    print(f"[{tag}] {calls + 1} API calls, {len(offers)} offers, {other} other-brand tours skipped"
          + (f", other brand only: {', '.join(sorted(foreign))}" if foreign else ""))
    if errors and not offers:
        raise RuntimeError(f"all {len(errors)} {tag} API requests failed, first: {errors[0]}")
    return offers
