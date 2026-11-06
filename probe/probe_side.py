"""TEMPORARY probe #2 (deleted after use)."""
import json, os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from common import get, session, allowed, Robots, UA
from config import CONFIG as cfg
from adapters import dertour

def sec(t): print("\n=====", t, flush=True)
def tryit(fn):
    try: fn()
    except Exception as e: print("   ERROR", type(e).__name__, str(e)[:300])

def ov():
    for base, path in [("https://overpass-api.de", "/api/interpreter"), ("https://z.overpass-api.de", "/api/interpreter"),
                       ("https://lz4.overpass-api.de", "/api/interpreter"), ("https://overpass.kumi.systems", "/api/interpreter"),
                       ("https://overpass.private.coffee", "/api/interpreter"), ("https://maps.mail.ru", "/osm/tools/overpass/api/interpreter"),
                       ("https://overpass.openstreetmap.ru", "/api/interpreter")]:
        try:
            r = session().get(base + "/robots.txt", timeout=15)
            txt = r.text if r.ok else ""
            ok = Robots(txt, UA).can_fetch(base + path)
            print(f"   {base}: robots {r.status_code} allowed={ok} :: {txt[:160]!r}")
        except Exception as e:
            print(f"   {base}: {type(e).__name__} {str(e)[:100]}")
sec("overpass instances"); tryit(ov)

def dt():
    home = "https://www.kartago.sk"
    hdr = {"Accept": "application/json", "Referer": home + "/"}
    q = dertour.query(cfg); q.pop("m", None)
    cats = get(home + dertour.API, params=q, headers=hdr, as_json=True)
    tr = [x for c in cats.get("categories") or [] for x in c.get("destinations") or [] if x.get("name") == "Turecko"][0]
    q2 = dertour.query(cfg, None, tr["destinationIds"]); q2.pop("m", None); q2["pitg"] = 100
    d = get(home + dertour.API, params=q2, headers=hdr, as_json=True)
    tours = d.get("tours") or []
    side = [t for t in tours if re.search(r"side|colakli|kumkoy|evrenseki|titreyen|sorgun|kizilagac|manavgat", json.dumps(t["hotel"].get("breadcrumbs"), ensure_ascii=False), re.I)]
    print(f"   {len(tours)} tours, {len(side)} in Side area")
    for t in side[:3]:
        h = t["hotel"]
        print("   HOTEL", h["name"], "gps", h.get("gps"), "tags", h.get("tags"), "iconTags", json.dumps(h.get("iconTags"), ensure_ascii=False)[:400])
        print("     imageTags", json.dumps(h.get("imageTags"), ensure_ascii=False)[:200])
        print("     extendedAttribues", json.dumps(h.get("extendedAttribues"), ensure_ascii=False)[:1500])
        print("     descriptions", json.dumps(h.get("descriptions"), ensure_ascii=False)[:600])
        print("     rooms", [r.get("name") for r in t["tour"]["rooms"]])
    from collections import Counter
    c = Counter()
    for t in tours:
        for a in (t["hotel"].get("extendedAttribues") or []):
            c[json.dumps(a, ensure_ascii=False)[:80]] += 1
        for a in (t["hotel"].get("iconTags") or []):
            c["ICON " + json.dumps(a, ensure_ascii=False)[:80]] += 1
    for k, v in c.most_common(60): print("   ATTR", v, k)
    def walk(f, depth=0):
        if depth > 3: return
        items = f.get("items") or []
        print("   " + "  " * depth + f"FILTER id={f.get('id')} type={f.get('type')} title={f.get('title')!r} items=" + json.dumps([(i.get("title") or i.get("name"), i.get("id"), i.get("value"), i.get("count")) for i in items][:25], ensure_ascii=False)[:700])
        for c2 in (f.get("categories") or [])[:6]:
            if f.get("type") != "areas": walk(c2, depth + 1)
    for f in d.get("filters") or []: walk(f)
    for a in d.get("aggregateResultItems") or []:
        print("   AGG", a.get("categoryName"), json.dumps([(i.get("name"), i.get("values"), i.get("count")) for i in a.get("items") or []][:40], ensure_ascii=False)[:600])
    # tt=0 transport types in Turkey
    q3 = dict(q2); q3["tt"] = 0; q3.pop("to", None)
    d3 = get(home + dertour.API, params=q3, headers=hdr, as_json=True)
    print("   tt=0 Turkey transportType", Counter(t["tour"].get("transportType") for t in d3.get("tours") or []), d3.get("toursCount"))
sec("dertour attrs"); tryit(dt)

def ru():
    h = get("https://pauschal.ruefa.at/index.php?page=results&level=2&adults=2&children=10-12")
    for name in ("globalTypebox", "zimmerbox"):
        vals = re.findall(r'name="%s"[^>]*data-filtername="([^"]+)"[^>]*value="([^"]+)"' % name, h)
        print("   ", name, sorted(set(vals))[:80])
    for m in list(re.finditer(r"globalType|zimmer(?!box)", h))[:0]: pass
    js = re.findall(r'<script[^>]+src="([^"]+)"', h)
    print("   scripts", js[:15])
    for m in re.finditer(r".{120}globalTypebox.{200}", h.replace("\n", " ")):
        if "input" not in m.group(0): print("   ..", m.group(0)[:320])
    for u in js:
        if "pauschal" in u or u.startswith("/") or "ruefa" in u:
            u2 = u if u.startswith("http") else "https://pauschal.ruefa.at/" + u.lstrip("/")
            try:
                t = get(u2)
            except Exception as e:
                print("   js fail", u2, e); continue
            for m in list(re.finditer(r".{150}(globalType|zimmerbox|suchConfig\.zimmer|suchConfig\.global).{200}", t.replace("\n", " ")))[:6]:
                print("   JS", u2[-40:], "..", m.group(0)[:360])
    r = session().get("https://hotels.ruefa.at/robots.txt", timeout=15)
    print("   hotels.ruefa.at robots", r.status_code, r.text[:300].replace("\n", " | "))
    t = get("https://hotels.ruefa.at/")
    print("   hotels.ruefa.at home", len(t), re.findall(r"<title>([^<]*)", t)[:1])
    for m in list(re.finditer(r".{100}(Nur Hotel|deliver|ajax|index\.php\?page=|api/).{150}", t.replace("\n", " ")))[:8]:
        print("   ..", m.group(0)[:260])
sec("ruefa"); tryit(ru)

def bi():
    w = get("https://www.billareisen.at/Hotels.html")
    print("   Hotels.html", len(w))
    for m in list(re.finditer(r".{200}Nur Hotel.{200}", w.replace("\n", " ")))[:3]:
        print("   ..", m.group(0)[:420])
    for m in list(re.finditer(r'href="(/[^"]*(Hotel|Angebote)[^"]*ttid=[^"]*)"', w))[:6]:
        print("   link", m.group(1)[:300])
    print("   ttid values", sorted(set(re.findall(r"ttid=([A-Za-z]+)", w)))[:20], sorted(set(re.findall(r'(?:name|value)="(ttid|PF|NH|HO|H)"', w)))[:10])
sec("billa hotel-only"); tryit(bi)

def tp():
    tok = os.environ.get("TRAVELPAYOUTS_TOKEN") or ""
    print("   token present:", "yes" if tok else "no")
    hdr = {"X-Access-Token": tok}
    for o, d, m in [("VIE", "AYT", "2027-07"), ("AYT", "VIE", "2027-07"), ("VIE", "AYT", "2027-08"), ("BTS", "AYT", "2027-07"), ("AYT", "BTS", "2027-07"), ("BRQ", "AYT", "2027-07")]:
        r = session().get("https://api.travelpayouts.com/aviasales/v3/prices_for_dates", params={"origin": o, "destination": d, "departure_at": m, "one_way": "true", "sorting": "price", "unique": "false", "limit": 1000, "currency": "eur"}, headers=hdr, timeout=30)
        j = r.json(); data = j.get("data") or []
        days = sorted({x["departure_at"][:10] for x in data})
        print(f"   one-way {o}->{d} {m}: HTTP {r.status_code} {len(data)} rows, {len(days)} days, min {min([x['price'] for x in data], default=None)}; first {json.dumps(data[0], ensure_ascii=False)[:200] if data else ''}")
sec("travelpayouts one-way"); tryit(tp)
