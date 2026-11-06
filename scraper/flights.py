"""Flights to Antalya (AYT) for the Side tab: Travelpayouts Data API (Aviasales cache), token in env TRAVELPAYOUTS_TOKEN
(GitHub Actions secret). Same API family as the user's flight_tracker/flight_deal_watcher.py.

Endpoint: GET https://api.travelpayouts.com/aviasales/v3/prices_for_dates (documented at
https://support.travelpayouts.com/hc/en-us/articles/203956163): origin, destination, departure_at and return_at
(YYYY-MM or YYYY-MM-DD), one_way=false (round trips), sorting=price, unique=false, limit ≤ 1000, currency=eur; the token
goes in the X-Access-Token header (never in the URL, so it can't leak into logs).
Answer: {"success": true, "data": [{origin, destination, price, airline, flight_number, departure_at, return_at,
transfers, return_transfers, duration, link}], "currency": "eur"}.
Prices are CACHED (what Aviasales users searched in the last days) and per ONE adult passenger: the page multiplies
by the party size (children 10/12 pay a full fare on most carriers) and labels it "orientačne".
The 2027 round-trip cache is thin (2026-11-06: VIE 4 round trips in July, BTS/BRQ none), so per origin we also ask
one-way fares (one_way=true) there and back per month and combine the cheapest of day d with day d + 7/10/14
("2× jednosmerná"). Per origin ≤ 4 round-trip + 2 + 3 one-way requests -> ≤ 27 requests per run (3 origins).
A missing token never fails the run: the tab then shows how to add it.
"""

import os
from datetime import date

API = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
DEST = "AYT"
ORIGINS = ("VIE", "BTS", "BRQ")
STAYS = (7, 10, 14)
KEEP = 8  # cheapest flights kept per origin and stay length


def token():
    return (os.environ.get("TRAVELPAYOUTS_TOKEN") or "").strip()


def months(cfg, extra_days=0):
    """['YYYY-MM', …] from date_from to date_to (+ extra_days, for returns)."""
    from datetime import timedelta
    out = []
    y, m = cfg["date_from"].year, cfg["date_from"].month
    end = cfg["date_to"] + timedelta(days=extra_days)
    while (y, m) <= (end.year, end.month):
        out.append(f"{y}-{m:02d}")
        y, m = y + (m == 12), m % 12 + 1
    return out


def rt_months(cfg):
    """[(departure month, return month)] for the round-trip queries: same month and the next one."""
    ms = months(cfg, cfg["nights_max"])
    return [(a, b) for i, a in enumerate(ms[:len(months(cfg))]) for b in ms[i:i + 2]]


def origins(cfg):
    return [o for o in ORIGINS if o in cfg["departures"] + cfg.get("departures_secondary", [])]


def stays(cfg):
    return [n for n in STAYS if cfg["nights_min"] <= n <= cfg["nights_max"]] or [cfg["nights_min"]]


def _rows(payload):
    if not isinstance(payload, dict) or not payload.get("success"):
        return []
    out = []
    for x in payload.get("data") or []:
        try:
            out.append((x, date.fromisoformat(str(x["departure_at"])[:10]), int(round(float(x["price"])))))
        except (KeyError, TypeError, ValueError):
            continue
    return [r for r in out if r[2] > 0]


def parse(payload, cfg, origin):
    """Round trips of one answer -> [{o, dep, ret, n, p, al, tr, k: 'rt'}] departing in the window, nights_min..max."""
    out = []
    for x, d1, price in _rows(payload):
        try:
            d2 = date.fromisoformat(str(x["return_at"])[:10])
        except (KeyError, TypeError, ValueError):
            continue
        n = (d2 - d1).days
        if not (cfg["date_from"] <= d1 <= cfg["date_to"]) or not (cfg["nights_min"] <= n <= cfg["nights_max"]):
            continue
        out.append({"o": x.get("origin_airport") or x.get("origin") or origin, "dep": d1.isoformat(),
                    "ret": d2.isoformat(), "n": n, "p": price, "al": x.get("airline") or None,
                    "tr": (x.get("transfers") or 0) + (x.get("return_transfers") or 0), "k": "rt"})
    return out


def cheapest_by_day(payload):
    """{date: (price, airline, transfers)} – the cheapest one-way fare of every day in a one_way=true answer."""
    out = {}
    for x, d1, price in _rows(payload):
        if d1 not in out or price < out[d1][0]:
            out[d1] = (price, x.get("airline") or None, x.get("transfers") or 0)
    return out


def combine(origin, out_days, back_days, cfg):
    """Two one-way fares (there on day d, back on day d + n, n in stays) -> combos {…, k: 'ow'}."""
    from datetime import timedelta
    res = []
    for d1, (p1, a1, t1) in out_days.items():
        if not cfg["date_from"] <= d1 <= cfg["date_to"]:
            continue
        for n in stays(cfg):
            d2 = d1 + timedelta(days=n)
            if d2 in back_days:
                p2, a2, t2 = back_days[d2]
                al = a1 if a1 == a2 else "/".join(x for x in (a1, a2) if x) or None
                res.append({"o": origin, "dep": d1.isoformat(), "ret": d2.isoformat(), "n": n, "p": p1 + p2, "al": al,
                            "tr": t1 + t2, "k": "ow"})
    return res


def best(flights):
    """Cheapest KEEP per (origin, nights), plus the cheapest of every departure day (for the date picker), deduped."""
    by, day = {}, {}
    for f in sorted(flights, key=lambda f: (f["p"], f["dep"])):
        by.setdefault((f["o"], f["n"]), []).append(f)
        day.setdefault((f["o"], f["n"], f["dep"]), f)
    keep = {id(f): f for v in by.values() for f in v[:KEEP]}
    keep.update({id(f): f for f in day.values()})
    return sorted(keep.values(), key=lambda f: (f["o"], f["n"], f["dep"], f["p"]))


def fetch(cfg, get=None):
    """{"status": ok|empty|no_token|error, "flights": [...], "requests": n, "error": str|None}. Per origin: round trips
    (rt_months) + one-way fares there (months) and back (months incl. the return month) -> ≤ 9 requests per origin."""
    tok = token()
    print(f"[flights] token present: {'yes' if tok else 'no'}")
    if not tok:
        return {"status": "no_token", "flights": [], "requests": 0, "error": None}
    if get is None:
        from common import get
    hdr = {"X-Access-Token": tok, "Accept-Encoding": "gzip"}
    flights, n, errors = [], 0, []

    def ask(q, what):
        nonlocal n
        n += 1
        q = dict(q, destination=q["destination"], direct="false", sorting="price", unique="false", limit=1000,
                 page=1, currency="eur")  # token only in the header, never in a URL (logs)
        try:
            return get(API, params=q, headers=hdr, as_json=True, retries=1, delay=0.5)
        except Exception as e:
            msg = f"{type(e).__name__}: {str(e).replace(tok, '***')[:160]}"
            print(f"[flights] {what}: {msg}")
            errors.append(msg)
            if "401" in msg or "403" in msg:
                raise PermissionError(msg) from None
            return None

    try:
        for origin in origins(cfg):
            rt = []
            for dep_m, ret_m in rt_months(cfg):
                payload = ask({"origin": origin, "destination": DEST, "departure_at": dep_m, "return_at": ret_m,
                               "one_way": "false"}, f"{origin} {dep_m}/{ret_m}")
                rt += parse(payload, cfg, origin)
            there, back = {}, {}
            for m in months(cfg):
                there.update(cheapest_by_day(ask({"origin": origin, "destination": DEST, "departure_at": m,
                                                  "one_way": "true"}, f"{origin}->{DEST} {m}")))
            for m in months(cfg, cfg["nights_max"]):
                back.update(cheapest_by_day(ask({"origin": DEST, "destination": origin, "departure_at": m,
                                                 "one_way": "true"}, f"{DEST}->{origin} {m}")))
            ow = combine(origin, there, back, cfg)
            print(f"[flights] {origin}<->{DEST}: {len(rt)} cached round trips ({cfg['nights_min']}–{cfg['nights_max']} "
                  f"nights), one-way fares on {len(there)} days there / {len(back)} back -> {len(ow)} combinations "
                  f"of {'/'.join(map(str, stays(cfg)))} nights"
                  + (f"; from {min(f['p'] for f in rt + ow)} €/os." if rt + ow else ""))
            flights += rt + ow
    except PermissionError as e:
        return {"status": "error", "flights": [], "requests": n, "error": str(e)}
    flights = best(flights)
    status = "ok" if flights else ("error" if errors and len(errors) == n else "empty")
    return {"status": status, "flights": flights, "requests": n, "error": errors[0] if errors else None}


def aviasales_party(adults, ages):
    """(adults, children, infants) in airline terms: 12+ = adult, 2–11 child, 0–1 infant."""
    a = adults + sum(1 for x in ages if x >= 12)
    c = sum(1 for x in ages if 2 <= x < 12)
    i = sum(1 for x in ages if x < 2)
    return a, c, i


def aviasales_link(origin, dest, dep, ret, adults=1, ages=()):
    """https://www.aviasales.com/search/{ORIGIN}{DDMM}{DEST}{DDMM}{adults}{children}{infants} (the URL scheme
    flight_deal_watcher.build_aviasales_link() uses; children/infants digits only when there are any)."""
    d1, d2 = date.fromisoformat(dep[:10]), date.fromisoformat(ret[:10]) if ret else None
    a, c, i = aviasales_party(adults, list(ages))
    pax = f"{a}" + (f"{c}" if c or i else "") + (f"{i}" if i else "")
    return f"https://www.aviasales.com/search/{origin}{d1:%d%m}{dest}{d2:%d%m}{pax}" if d2 else \
        f"https://www.aviasales.com/search/{origin}{d1:%d%m}{dest}{pax}"
