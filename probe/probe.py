"""Temporary diagnostics for new sources (deleted after use). Iteration 4."""
import base64, gzip, json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
import requests
from common import UA, Robots

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "de-AT,de;q=0.9,en;q=0.7"})
ROB = {}

def robots(url):
    p = urlsplit(url); base = f"{p.scheme}://{p.netloc}"
    if base not in ROB:
        try:
            r = S.get(base + "/robots.txt", timeout=20); time.sleep(1)
            ok = r.ok and "<html" not in r.text[:300].lower()
            ROB[base] = Robots(r.text if ok else "", UA)
        except Exception as e:
            ROB[base] = Robots("", UA)
    return ROB[base].can_fetch(url)

def fetch(url, **kw):
    if not robots(url):
        print(f"  ROBOTS-DISALLOWED {url}"); return None
    try:
        r = S.get(url, timeout=30, **kw)
    except Exception as e:
        print(f"  !! {url}: {type(e).__name__} {str(e)[:150]}"); return None
    time.sleep(1.5)
    print(f"  GET {r.status_code} {url[:400]} -> len={len(r.text)} ct={r.headers.get('content-type')}")
    return r

def grep(text, pat, n=8, w=200, label=""):
    c = 0
    for m in re.finditer(pat, text, re.I | re.S):
        print(f"    {label}~ " + re.sub(r"\s+", " ", text[max(0, m.start() - w): m.end() + w]))
        c += 1
        if c >= n:
            break
    if not c:
        print(f"    {label}~ (no match for {pat[:60]})")

def blob(name, text):
    b = base64.b64encode(gzip.compress(text.encode())).decode()
    print(f"BLOB-BEGIN {name} {len(b)}")
    for i in range(0, len(b), 4000):
        print("BLOB " + b[i:i + 4000])
    print(f"BLOB-END {name}")

def devalue(arr):
    memo = {}
    def res(i, depth=0):
        if not isinstance(i, int) or i < 0:
            return None
        if i in memo:
            return memo[i]
        v = arr[i]
        if depth > 60:
            return "..."
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in ("ShallowReactive", "Reactive", "Ref", "EmptyRef", "ShallowRef", "Set", "Date"):
                out = res(v[1], depth + 1) if len(v) > 1 and v[0] != "Date" else (v[1] if len(v) > 1 else None)
            else:
                out = [res(x, depth + 1) for x in v]
        elif isinstance(v, dict):
            out = {k: res(x, depth + 1) for k, x in v.items()}
        else:
            out = v
        memo[i] = out
        return out
    return res(0)





import json as _j, os
from urllib.parse import urlencode, parse_qsl

def cards(v, n=4):
    out = []
    for c in v.split('class="card nocity card-hotel')[1:]:
        g = lambda p: (re.search(p, c, re.S).group(1).strip() if re.search(p, c, re.S) else None)
        out.append({"href": g(r'data-href="([^"]+)"'), "price": g(r'data-price="([^"]+)"'), "nights": g(r'data-nights="([^"]+)"'),
                    "start": g(r'data-startdate="([^"]+)"'), "name": g(r'hotel-name h5">([^<]+)'), "region": g(r'region">([^<]+)'),
                    "board": g(r'class="board">.*?icontext">([^<]+)'), "dep": g(r'ab/bis\s+([^<]+)<'),
                    "pp": g(r'Preis p\. Pers\.[^\d]*([\d.]+)')})
    return out

R = "https://pauschal.ruefa.at"
r = fetch(R + "/index.php?page=results&level=1&adults=2&start=2027-07-01&until=2027-08-31&anzZimmer=1&airport=VIE&dauer=1024&destination=T%C3%BCrkei")
print("\n===== RUEFA getDestination")
h = fetch(R + "/js/hotelsearch/dist/hotelsearch.min.js?id=492")
if h is not None:
    grep(h.text, r"getDestination\.php", 4, 700, "gd")
for data in [{"term": "Türkei"}, {"q": "Türkei"}, {"search": "Türkei"}, {"destination": "Türkei"}, {"value": "Türkei"}]:
    for meth in ("post", "get"):
        try:
            p = getattr(S, meth)(R + "/hub/ajax/getDestination.php", **({"data": data} if meth == "post" else {"params": data}),
                                  timeout=30, headers={"X-Requested-With": "XMLHttpRequest"}); time.sleep(1.5)
            print("  ", meth, data, p.status_code, len(p.text), p.text[:600].replace("\n", " "))
        except Exception as e:
            print("  fail", e)

print("\n===== RUEFA deliver variants")
base = {"adults": "2", "children": "", "start": "2027-07-01", "until": "2027-08-31", "hotelSearchtext": "", "level": "2",
        "page": "1", "topGid": "", "destinationName": "", "airport": "VIE", "recommendationrate": "", "dauer": "1024",
        "anzZimmer": "1", "sort": "", "airline": "", "maxPrice": "", "minPrice": "", "citycodes": "", "destination_groups": "",
        "excludeNbc": "1", "destination": "", "destinationId": "19"}
tests = [
  ("base", {}),
  ("dauer7-14", {"dauer": str(sum(2 ** n for n in range(7, 15)))}),
  ("kids 1+2", {"adults": "1", "children": "10-12"}),
  ("kids 1+2 comma", {"adults": "1", "children": "10,12"}),
  ("AI", {"verpflegung": "AI AIP AIU AIR"}),
  ("AI+sort price", {"verpflegung": "AI AIP AIU AIR", "sort": "price"}),
  ("no destId", {"destinationId": ""}),
  ("BTS-VIE", {"airport": "VIE-BTS"}),
  ("page2", {"page": "2"}),
]
for name, extra in tests:
    d = dict(base, **extra)
    try:
        p = S.post(R + "/hub/ajax/deliver.php", data=d, timeout=60,
                   headers={"X-Requested-With": "XMLHttpRequest", "Referer": r.url if r is not None else R}); time.sleep(1.5)
        j = p.json()
        cs = cards(j.get("value") or "")
        print(f"  [{name}] {p.status_code} count={j.get('resultCount')} n={len(cs)} bc={str(j.get('breadcrumb'))[:80]} boards={j.get('boardTypes')}")
        for c in cs[:3]:
            print("     ", c)
        if name == "kids 1+2":
            blob("ruefa_kids.json", p.text)
    except Exception as e:
        print(f"  [{name}] fail {type(e).__name__} {e}")
