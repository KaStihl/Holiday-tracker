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
H = {"X-Requested-With": "XMLHttpRequest", "Referer": r.url if r is not None else R}
print("\n===== RUEFA all countries")
p = S.get(R + "/hub/ajax/getDestination.php", params={"destination": ""}, headers=H, timeout=30); time.sleep(1.5)
print("  empty:", p.status_code, len(p.text), p.text[:300])
p2 = S.get(R + "/hub/ajax/getDestination.php", params={"x": "1"}, headers=H, timeout=30); time.sleep(1.5)
print("  noparam:", p2.status_code, len(p2.text))
lst = []
for cand in (p2, p):
    try:
        lst = cand.json()
        if len(lst) > 20:
            break
    except Exception:
        pass
ids = {x["name"]: x["id"].strip() for x in lst if x.get("country")}
print("  countries:", len(ids))
blob("ruefa_destinations.json", _j.dumps(lst, ensure_ascii=False))
want = ["Türkei", "Griechenland", "Spanien", "Zypern", "Italien", "Kroatien", "Ägypten", "Malediven", "Mauritius",
        "Vereinigte Arabische Emirate", "Thailand", "Dominikanische Republik", "Mexiko", "Kuba", "Kap Verde", "Kapverden", "Tansania"]
print("  wanted:", {w: ids.get(w) for w in want})

base = {"adults": "1", "children": "10-12", "start": "2027-07-01", "until": "2027-08-31", "hotelSearchtext": "", "level": "2",
        "page": "1", "topGid": "", "destinationName": "", "airport": "VIE-BTS", "recommendationrate": "", "dauer": "1024",
        "anzZimmer": "1", "sort": "price", "airline": "", "maxPrice": "", "minPrice": "", "citycodes": "", "destination_groups": "",
        "excludeNbc": "1", "destination": "", "destinationId": "", "verpflegung": "AI AIP AIU AIR"}
def run(name, extra, save=None):
    d = dict(base, **extra)
    try:
        p = S.post(R + "/hub/ajax/deliver.php", data=d, timeout=60, headers=H); time.sleep(1.5)
        j = p.json()
        cs = cards(j.get("value") or "")
        from collections import Counter
        print(f"  [{name}] {p.status_code} {round(p.elapsed.total_seconds(),1)}s count={j.get('resultCount')} n={len(cs)} "
              f"nights={Counter(c['nights'] for c in cs)} countries={Counter((c['region'] or '').split('/')[0] for c in cs)} "
              f"prices={[c['price'] for c in cs][:4]}")
        if save:
            blob(save, p.text)
        return cs
    except Exception as e:
        print(f"  [{name}] fail {type(e).__name__} {e}")
tr = ids.get("Türkei", "")
run("TR ids AI kids", {"destinationId": tr}, save="ruefa_tr_ai_kids.json")
run("TR ids first-id", {"destinationId": tr.split()[0] if tr else ""})
run("TR destination name", {"destination": "Türkei"})
for dv in ["7", "14", "714", "7-14", "0714", "128", "4096", "1014", "-1", "16384", "2048", "512"]:
    run(f"TR dauer={dv}", {"destinationId": tr, "dauer": dv})
run("TR page2", {"destinationId": tr, "page": "2"})
cs = run("TR Sural search", {"destinationId": tr, "hotelSearchtext": "Sural", "dauer": "-1"})
cs = run("TR Alhambra search", {"destinationId": tr, "hotelSearchtext": "Alhambra", "dauer": "-1"})
