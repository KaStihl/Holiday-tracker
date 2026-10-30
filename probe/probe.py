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



sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CONFIG
import ruefa_probe as RU
R = "https://pauschal.ruefa.at"
H = {"X-Requested-With": "XMLHttpRequest", "Referer": R + "/"}
print("\n===== RUEFA hotel lookups")
for q in ["Sural", "Alhambra", "Royal Alhambra", "Sural Saray"]:
    p = S.get(R + "/hub/ajax/getDestination.php", params={"destination": q}, headers=H, timeout=30); time.sleep(1.5)
    try:
        print("  ", q, [(x.get("name"), x.get("id"), x.get("field")) for x in p.json()][:15])
    except Exception as e:
        print("  ", q, p.status_code, p.text[:300])
print("\n===== RUEFA adapter test")
t0 = time.time()
try:
    offs = RU.search(CONFIG)
    from collections import Counter
    print("  RUEFA", len(offs), "offers in", round(time.time() - t0), "s;", Counter(o["country_code"] for o in offs).most_common(),
          Counter(o["board"] for o in offs), Counter(o["departure"] for o in offs), Counter(o["nights"] for o in offs))
    for o in offs:
        if any(k in o["hotel"].lower() for k in ("sural", "alhambra")):
            print("  HIT", o["hotel"], o["date_from"], o["nights"], o["price_total"], o["url"][:150])
except Exception:
    import traceback; traceback.print_exc()
