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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("\n===== BILLA adapter test")
from config import CONFIG
import billa_reisen as B
t0 = time.time()
try:
    offs = B.search(CONFIG)
    from collections import Counter
    print("  BILLA", len(offs), "offers in", round(time.time() - t0), "s;", Counter(o["country_code"] for o in offs).most_common(),
          Counter(o["board"] for o in offs), Counter(o["departure"] for o in offs))
    for o in offs:
        if any(k in o["hotel"].lower() for k in ("sural", "alhambra")):
            print("  HIT", o["hotel"], o["date_from"], o["nights"], o["price_total"], o["url"][:120])
except Exception as e:
    import traceback; traceback.print_exc()
html = S.get(B.HOME + B.PATH, params=B.query(CONFIG, "3380096"), timeout=40).text; time.sleep(1.5)
blob("billa_tr.html", html)
html = S.get(B.HOME + B.PATH, params=B.query(CONFIG, B.COUNTRIES["ES"]), timeout=40).text; time.sleep(1.5)
o, p = B.parse_page(html, CONFIG)
print("  ES multi-id:", len(o), p, sorted({x["region"] for x in o})[:10])

print("\n===== RUEFA deliver 2")
h = fetch("https://pauschal.ruefa.at/js/hotelsearch/dist/hotelsearch.min.js?id=492")
if h is not None:
    print("   endpoints:", sorted(set(re.findall(r"/hub/ajax/\w+\.php", h.text))))
    grep(h.text, r"dauer[\"']?\s*[:=]\s*\[|value:\s*\"?(?:128|1024|4096)\"?", 6, 400, "dauer")
r = fetch("https://pauschal.ruefa.at/index.php?page=results&level=1&adults=2&start=2027-07-01&until=2027-08-31&anzZimmer=1&airport=VIE&dauer=1024&destination=T%C3%BCrkei")
base = {"adults": "2", "children": "", "start": "2027-07-01", "until": "2027-08-31", "hotelSearchtext": "", "level": "1",
        "page": "1", "topGid": "", "destinationName": "Türkei", "airport": "VIE", "recommendationrate": "70", "dauer": "1024",
        "anzZimmer": "1", "sort": "", "airline": "", "maxPrice": "", "minPrice": "", "citycodes": "", "destination_groups": "",
        "excludeNbc": "1", "destination": "Türkei"}
for extra in [{}, {"level": "2"}, {"level": "2", "destination": "", "destinationId": "19"}]:
    d = dict(base, **extra)
    try:
        p = S.post("https://pauschal.ruefa.at/hub/ajax/deliver.php", data=d, timeout=60,
                   headers={"X-Requested-With": "XMLHttpRequest", "Referer": r.url if r is not None else ""}); time.sleep(1.5)
        print("  POST", extra, p.status_code, len(p.text), p.text[:200].replace("\n", " "))
        try:
            j = p.json(); print("    keys:", list(j)[:30], "resultCount", j.get("resultCount"), "level", j.get("level"))
            v = j.get("value") or ""
            print("    value:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", v))[:1500])
            if extra.get("level") == "2":
                blob("ruefa_deliver_l2.json", p.text)
        except Exception as e:
            print("    not json", e)
    except Exception as e:
        print("  POST failed", e)
