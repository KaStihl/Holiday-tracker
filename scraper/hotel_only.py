"""Accommodation-only ("len ubytovanie") prices for the Side tab – only from legitimate sources.

Checked 2026-11-06 from a GitHub runner (temporary probe):
- Travelpayouts / Hotellook hotel data: engine.hotellook.com answers 404 on every v2 endpoint (lookup.json,
  cache.json) even with a valid TRAVELPAYOUTS_TOKEN – the Hotellook API no longer exists. Not used.
- DERTOUR SK (Kartago/Fischer): tt=2…5 (other transport types) answer no countries, tt=0 lists only flight packages
  for Turkey -> they don't sell Turkey without the flight.
- Ruefa: pauschal.ruefa.at is packages only; hotels.ruefa.at is the generic home page (no hotel-only search found).
- Čedok: not used – the Turkey listings the tracker reads are flight packages; no hotel-only / own-transport search
  for Turkey was found (not probed further).
- BILLA Reisen: sells "Nur Hotel" (hotel only): /Hotels/Angebote.html with pttid=PH / ptoj=PH, the same server-
  rendered result cards as the packages ("Nur Hotel · z.B. 7 Nächte, ab 2.7.2027, Doppelzimmer, Alles Inklusive",
  "p.P. ab € …" for 2 adults); robots.txt only disallows /buchen/. -> USED: Turkey (pdf=3380096), All Inclusive when
  boards_preferred is AI-only, 7/10/14 nights, cheapest first, ≤ MAX_CALLS pages per refresh, at most once per
  REFRESH_HOURS (side.py caches it in site/data/side_daily.json). Children are ignored by the list (as for the packages), so
  the party price is per person at 2 adults × persons – "orientačne".
"""

import time
from urllib.parse import urlencode

MAX_CALLS = 18
REFRESH_HOURS = 20
PATH = "/Hotels/Angebote.html"
TURKEY = "3380096"
SIDE_WORDS = ("side", "kumkoy", "colakli", "evrenseki", "titreyengol", "sorgun", "kizilagac", "manavgat")


def billa_query(cfg, nights, page=0):
    from adapters import billa_reisen
    q = billa_reisen.query(cfg, TURKEY, page)
    q.update({"ttid": "PH", "pttid": "PH", "ptoj": "PH", "pnnfl": nights, "pnnfh": nights})
    q.pop("pdaf", None)
    q.pop("ptf", None)
    return q


def billa_url(cfg, nights, page=0):
    from adapters import billa_reisen
    return f"{billa_reisen.HOME}{PATH}?{urlencode(billa_query(cfg, nights, page))}"


def parse_billa(html, cfg):
    """(rows, pages): rows {hotel, place, region, pp (€ per person at 2 adults, whole stay), checkin, nights, board,
    url} of the "Nur Hotel" cards. Package cards (no "Nur Hotel") are skipped."""
    from adapters import billa_reisen
    from config import party_size
    offers, pages = billa_reisen.parse_page(html, cfg)
    n = party_size(cfg)
    rows = []
    for o in offers:
        rows.append({"hotel": o["hotel"], "place": o.get("place"), "region": o.get("region"),
                     "pp": round(o["price_total"] / n), "checkin": o["date_from"], "nights": o["nights"],
                     "board": o.get("board"), "url": o["url"], "country_code": o.get("country_code")})
    return rows, pages


def in_side(row):
    from watch import norm_name
    t = norm_name(f"{row.get('place') or ''} {row.get('region') or ''}").replace(" ", "")
    return any(w in t for w in SIDE_WORDS)


def fetch_billa(cfg, get=None, max_calls=MAX_CALLS):
    """Side-area hotel-only rows from BILLA Reisen, 7/10/14 nights, ≤ max_calls pages."""
    from flights import stays
    if get is None:
        from common import get
    rows, calls, err = [], 0, None
    for nights in stays(cfg):
        page, pages = 0, 1
        while page < pages and calls < max_calls:
            calls += 1
            try:
                html = get(billa_url(cfg, nights, page))
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:120]}"
                print(f"[hotel_only] BILLA {nights}n p{page + 1}: {err}")
                break
            got, pages = parse_billa(html, cfg)
            side = [r for r in got if in_side(r)]
            print(f"[hotel_only] BILLA Nur Hotel {nights}n p{page + 1}/{pages}: {len(got)} hotels, {len(side)} in the "
                  f"Side area" + (f", {min(r['pp'] for r in side)} €/os." if side else ""))
            rows += side
            page += 1
            # spread the page budget over the stay lengths: at most a third each, unless the others are short
            if page >= max(2, max_calls // len(stays(cfg))):
                break
    return rows, calls, err


SOURCES_INFO = [
    {"id": "hotellook", "name": "Travelpayouts / Hotellook", "status": "unavailable",
     "note": "API Hotellook už neexistuje (engine.hotellook.com odpovedá 404, overené 6. 11. 2026)"},
    {"id": "dertour", "name": "Kartago / Fischer", "status": "unavailable", "note": "Turecko predávajú len s letenkou"},
    {"id": "ruefa", "name": "Ruefa", "status": "unavailable", "note": "len zájazdy s letenkou (pauschal.ruefa.at)"},
]


def fetch(cfg, get=None):
    """{"sources": [{id, name, status, note, requests}], "rows": {source id: [rows]}} – network, no cache."""
    t0 = time.time()
    rows, calls, err = fetch_billa(cfg, get)
    status = "ok" if rows else ("error" if err else "empty")
    print(f"[hotel_only] BILLA: {len(rows)} Side-area rows, {calls} requests, {time.time() - t0:.0f} s")
    return {"sources": [{"id": "billa_reisen", "name": "BILLA Reisen (Nur Hotel)", "status": status, "requests": calls,
                         "note": "cena za os. pri 2 dospelých × počet osôb (orientačne), bez letenky"
                                 + (f"; chyba: {err}" if err else "")}] + [dict(x, requests=0) for x in SOURCES_INFO],
            "rows": {"billa_reisen": rows}}
