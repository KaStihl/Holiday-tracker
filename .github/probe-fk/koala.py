"""TEMPORARY: Koala allowed routes. Uses common.get (robots enforced)."""
import re, sys, json
sys.path.insert(0, "scraper")
import common
from common import get, RobotsDisallowed
from adapters import tiptravel

def show(url, n=3000, params=None):
    try:
        t = get(url, params=params)
    except RobotsDisallowed:
        print("ROBOTS-DISALLOWED", url, params); return ""
    except Exception as e:
        print("ERR", url, repr(e)[:300]); return ""
    print(f"----- {url} {params} len={len(t)}"); print(t[:n]); return t

sm = get("https://koala.sk/sitemap.xml")
locs = re.findall(r"<loc>([^<]+)</loc>", sm)
hotels = [l for l in locs if re.match(r"https://koala.sk/dovolenka/[^/]+/[^/]+$", l)]
print("NLOCS", len(locs), "hotel-like", len(hotels)); print("\n".join(locs[60:360:3]))
for dfrom, dto in [("01.11.2026", "31.10.2027"), ("01.07.2027", "31.08.2027")]:
    for ap in ("2", None):
        q = {"ProductTypeIDs": "401", "DateFrom": dfrom, "DateTo": dto, "TransportationTypeID": "201",
             "Sort": "n", "Page": 1, "PageSize": 100, **({"AirportID": ap} if ap else {})}
        u = "https://koala.sk/search.json"
        from urllib.parse import urlencode
        print("ALLOWED", common.allowed(u + "?" + urlencode(q)))
        t = show(u, 1500, q)
        r = tiptravel.parse_response(t) if t else {}
        print("itemsCount", r.get("itemsCount"), "keys", list(r)[:20])
        for it in (r.get("items") or [])[:5]:
            print(json.dumps(it, ensure_ascii=False)[:800])
        dates = sorted({(it.get("dateFrom") or "")[:7] for it in r.get("items") or []})
        print("months", dates)
h = show(hotels[0] if hotels else "https://koala.sk/dovolenka/albansko/fafa-premium-resort", 800)
print("HOTEL prices", re.findall(r"[\d\s.]{3,}\s?€", h)[:20], "terms-ish", re.findall(r"\d{1,2}\.\d{1,2}\.\d{4}", h)[:20])
js = show("https://koala.sk/index.js", 0)
print("JS endpoints", sorted(set(re.findall(r'["\'](/[A-Za-z0-9_./-]*(?:\.json|\.ashx|api/[A-Za-z0-9_/-]*))', js)))[:60])
