"""TEMPORARY probe (deleted after use): what the Side-hotels feature can use. Prints only short snippets."""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
import requests
from common import get, session, allowed
from config import CONFIG as cfg
from adapters import dertour

def snip(text, pats, width=90, maxn=25):
    n = 0
    for p in pats:
        for m in re.finditer(p, text, re.I):
            s = text[max(0, m.start() - width): m.end() + width].replace("\n", " ")
            print("   ..", s)
            n += 1
            if n >= maxn:
                return

def sec(t):
    print("\n=====", t, flush=True)

def tryit(fn):
    try:
        fn()
    except Exception as e:
        print("   ERROR", type(e).__name__, str(e)[:300])

# 1 overpass robots + tiny query
def ov():
    r = session().get("https://overpass-api.de/robots.txt", timeout=20)
    print("   robots", r.status_code, r.text[:400].replace("\n", " | "))
    print("   allowed /api/interpreter:", allowed("https://overpass-api.de/api/interpreter"))
    r = session().get("https://overpass-api.de/api/status", timeout=20)
    print("   status", r.status_code, r.text[:300].replace("\n", " | "))
sec("overpass"); tryit(ov)

# 2 DERTOUR transport types + JS bundle filters
def dt():
    home = "https://www.kartago.sk"
    hdr = {"Accept": "application/json", "Referer": home + "/"}
    for tt in (0, 2, 3, 4, 5):
        q = dertour.query(cfg); q["tt"] = tt; q.pop("to", None); q.pop("m", None)
        try:
            d = get(home + dertour.API, params=q, headers=hdr, as_json=True)
            cats = [(x.get("name"), x.get("hotelCount")) for c in d.get("categories") or [] for x in c.get("destinations") or []]
            print(f"   tt={tt}: {cats[:12]}")
        except Exception as e:
            print(f"   tt={tt}: {type(e).__name__} {str(e)[:150]}")
    html = get(home + "/vysledky-vyhladavania")
    js = re.findall(r'src="([^"]*index[^"]*\.js[^"]*)"', html) + re.findall(r'src="(/Scripts/[^"]+\.js)"', html)
    print("   scripts:", js[:8])
    for u in js[:3]:
        u = u if u.startswith("http") else home + u
        t = get(u)
        print("   JS", u, len(t))
        snip(t, [r"aquapark", r"tobog", r"facilit", r"detsk", r"miniklub|miniclub|kids", r"beach|plaz|pláž", r"rodinn|family", r'"/api/[a-z/]+'], 70, 40)
    # tour JSON of Side destination: every key seen
    q = dertour.query(cfg); q.pop("m", None)
    cats = get(home + dertour.API, params=q, headers=hdr, as_json=True)
    tr = [x for c in cats.get("categories") or [] for x in c.get("destinations") or [] if x.get("name") == "Turecko"]
    if tr:
        q2 = dertour.query(cfg, None, tr[0]["destinationIds"]); q2.pop("m", None); q2["pitg"] = 5
        d = get(home + dertour.API, params=q2, headers=hdr, as_json=True)
        print("   top keys", list(d.keys()))
        for k, v in d.items():
            if k not in ("tours",):
                print("   ", k, json.dumps(v, ensure_ascii=False)[:600])
        t = (d.get("tours") or [{}])[0]
        print("   hotel keys", list((t.get("hotel") or {}).keys()), "tour keys", list((t.get("tour") or {}).keys()))
        print("   tags", [x.get("tour", {}).get("tags") for x in d.get("tours") or []], [x.get("hotel", {}).get("badgeId") for x in d.get("tours") or []])
sec("dertour"); tryit(dt)

# 3 Ruefa: filters and hotel-only IBE
def ru():
    h = get("https://pauschal.ruefa.at/index.php?page=results&level=2&adults=2&children=10-12")
    print("   results page", len(h))
    snip(h, [r"Kinderclub|Kinderbetreuung|Miniclub", r"Rutsche|Aquapark|Wasserpark", r"Familienzimmer", r"Strandlage|Strandnah|direkt am Strand", r"name=\"[a-zA-Z_]*(attr|facil|ausst|merkmal|kategorie)[a-zA-Z_]*\"", r"nur.?hotel|hotelonly|reiseart|Eigenanreise"], 80, 40)
    w = get("https://www.ruefa.at/")
    hrefs = sorted(set(re.findall(r'href="(https?://[^"]+)"', w)))
    print("   ruefa.at hosts:", sorted({re.sub(r"(https?://[^/]+).*", r"\1", x) for x in hrefs})[:40])
    snip(w, [r"nur.?hotel", r"Eigenanreise", r"hotel\.ruefa"], 80, 10)
sec("ruefa"); tryit(ru)

# 4 BILLA: hotel-only + globaltypes
def bi():
    w = get("https://www.billareisen.at/")
    snip(w, [r'href="[^"]*(Hotel|Nur)[^"]*"'], 40, 15)
    snip(w, [r"Nur Hotel|Eigenanreise"], 80, 6)
sec("billa"); tryit(bi)

# 5 Cedok: transport facets
def ce():
    h = get("https://www.cedok.sk/dovolenka/turecko/?dateFrom=01.07.2027&dateTo=31.08.2027&durationMin=8&durationMax=8&participants[0][adults]=2")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    print("   next data", bool(m))
    if m:
        t = m.group(1)
        snip(t, [r'"transport[A-Za-z]*"', r"vlastn", r"OWN_TRANSPORT|ownTransport|individual"], 80, 20)
sec("cedok"); tryit(ce)

# 6 Hotellook + Travelpayouts (token from env; never printed)
def hl():
    import os
    tok = os.environ.get("TRAVELPAYOUTS_TOKEN") or ""
    print("   token present:", "yes" if tok else "no")
    hdr = {"X-Access-Token": tok} if tok else {}
    tests = [
        ("hotellook lookup", "https://engine.hotellook.com/api/v2/lookup.json", {"query": "Side", "lang": "en", "lookFor": "both", "limit": 3}),
        ("hotellook cache", "https://engine.hotellook.com/api/v2/cache.json", {"location": "Side", "checkIn": "2027-07-10", "checkOut": "2027-07-17", "currency": "eur", "limit": 5, "adults": 2, "children": "10,12"}),
        ("hotellook cache near", "https://engine.hotellook.com/api/v2/cache.json", {"location": "Antalya", "checkIn": "2027-01-10", "checkOut": "2027-01-17", "currency": "eur", "limit": 3}),
        ("tp v3 VIE jul/jul", "https://api.travelpayouts.com/aviasales/v3/prices_for_dates", {"origin": "VIE", "destination": "AYT", "departure_at": "2027-07", "return_at": "2027-07", "currency": "eur", "limit": 1000, "one_way": "false", "sorting": "price", "unique": "false"}),
        ("tp v3 BTS jul/jul", "https://api.travelpayouts.com/aviasales/v3/prices_for_dates", {"origin": "BTS", "destination": "AYT", "departure_at": "2027-07", "return_at": "2027-07", "currency": "eur", "limit": 1000, "one_way": "false"}),
        ("tp v3 BRQ aug/aug", "https://api.travelpayouts.com/aviasales/v3/prices_for_dates", {"origin": "BRQ", "destination": "AYT", "departure_at": "2027-08", "return_at": "2027-08", "currency": "eur", "limit": 1000, "one_way": "false"}),
        ("tp v3 VIE no dates", "https://api.travelpayouts.com/aviasales/v3/prices_for_dates", {"origin": "VIE", "destination": "AYT", "currency": "eur", "limit": 30, "one_way": "false"}),
        ("tp v1 cheap VIE 2027-07", "https://api.travelpayouts.com/v1/prices/cheap", {"origin": "VIE", "destination": "AYT", "depart_date": "2027-07", "return_date": "2027-07", "currency": "eur"}),
        ("tp v2 month-matrix VIE 2027-07", "https://api.travelpayouts.com/v2/prices/month-matrix", {"origin": "VIE", "destination": "AYT", "month": "2027-07-01", "currency": "eur", "show_to_affiliates": "true"}),
    ]
    for name, u, q in tests:
        try:
            r = session().get(u, params=dict(q, token=tok) if tok else q, headers=hdr, timeout=30)
            body = r.text
            info = ""
            try:
                j = r.json()
                d = j.get("data") if isinstance(j, dict) else j
                if isinstance(d, list):
                    info = f"list {len(d)}; first: " + json.dumps(d[0], ensure_ascii=False)[:400] if d else "list 0"
                    if d and isinstance(d[0], dict) and "departure_at" in d[0]:
                        from datetime import date
                        nn = [(date.fromisoformat(x["return_at"][:10]) - date.fromisoformat(x["departure_at"][:10])).days for x in d if x.get("return_at")]
                        info += f" | nights dist {sorted(set(nn))[:30]} min price {min(x['price'] for x in d)}"
                elif isinstance(d, dict):
                    info = f"dict keys {list(d)[:10]}; " + json.dumps(d, ensure_ascii=False)[:400]
                else:
                    info = json.dumps(j, ensure_ascii=False)[:400]
            except ValueError:
                info = body[:300].replace("\n", " ")
            if tok:
                info = info.replace(tok, "***")
            print(f"   {name}: HTTP {r.status_code} {info}")
        except Exception as e:
            print(f"   {name}: {type(e).__name__} {str(e)[:200].replace(tok or '@@', '***')}")
sec("hotellook/travelpayouts"); tryit(hl)

# 7 overpass real query via side module (if present)
def osm():
    import side_hotels
    t0 = time.time()
    raw = side_hotels.fetch_overpass(side_hotels.side_cfg(cfg))
    print(f"   elements {len(raw.get('elements', []))} in {time.time()-t0:.0f}s")
    hotels = side_hotels.process_osm(raw, side_hotels.side_cfg(cfg))
    side_hotels.print_summary(hotels, side_hotels.side_cfg(cfg))
sec("overpass query"); tryit(osm)
