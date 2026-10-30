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


import json as _j
from urllib.parse import urlencode, parse_qsl

print("\n===== HOFER terms")
for u in ["https://www.hofer-reisen.at/at/service/reisebedingungen", "https://www.hofer-reisen.at/at/service/impressum"]:
    r = fetch(u)
    if r is not None:
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", r.text, flags=re.S)))
        grep(t, r"automatisiert|scrap|data.?mining|crawl|Robot|Vervielfältig|Urheber", 6, 250)

print("\n===== HOFER search variants")
def cards(html, n=4):
    out = []
    for m in re.finditer(r'data-testid="ProductCard"(.*?)Zum Angebot', html, re.S):
        c = m.group(1)
        name = re.search(r'product-card__headline"[^>]*>([^<]+)', c)
        price = re.search(r'price-value">([^<]+)', c)
        opts = re.findall(r'booking-options[^"]*">(.*?)</div>', c, re.S)
        href = re.search(r'href="([^"]+)"$', c.strip()) or re.search(r'href="(/at/hotels/[^"]+)"', c)
        out.append((name and name.group(1), price and price.group(1), [re.sub("<[^>]+>", "", o) for o in opts],
                    (href.group(1).replace("&amp;", "&").replace("&quot;", '"')[:600] if href else None)))
    print("    cards:", len(out))
    for o in out[:n]:
        print("     ", o)
PX = '[{"id":"0","ad":1,"ch":[10,12],"ti":[]}]'
variants = {
  "s_mn7mx14": {"s_dr": "270701,270831", "s_du": '{"ty":"night","mn":7,"mx":14}', "s_px": PX, "s_ap": "VIE"},
  "s_mn7": {"s_dr": "270701,270831", "s_du": '{"ty":"night","mn":7}', "s_px": PX, "s_ap": "VIE", "s_si": "PACKAGE"},
  "p_": {"p_dr": "270701,270831", "p_du": '{"ty":"night","mn":7}', "p_px": PX, "p_ap": "VIE", "p_si": "PACKAGE"},
}
for k, q in variants.items():
    r = fetch("https://www.hofer-reisen.at/at/destination/asien/tuerkei?" + urlencode(q))
    if r is not None:
        print("   variant", k); cards(r.text)
        if k == "s_mn7":
            blob("hofer_tuerkei_party.html", r.text)

print("\n===== RUEFA deliver")
u = ("https://pauschal.ruefa.at/index.php?page=results&level=1&adults=1&children=10,12&start=2027-07-01&until=2027-08-31"
     "&anzZimmer=1&airport=VIE&dauer=1024&destination=T%C3%BCrkei")
r = fetch(u)
if r is not None:
    grep(r.text, r"suchConfig\s*=", 3, 1500, "cfg")
    grep(r.text, r"name=\"dauer\"|dauer", 4, 300, "dauer")
j = fetch("https://pauschal.ruefa.at/js/min/search.min.js?id=6492")
if j is not None:
    grep(j.text, r"dauer", 8, 200, "jsdauer")
    grep(j.text, r"suchConfig\.\w+=|suchConfig=", 6, 300, "jscfg")
data = dict(parse_qsl(urlsplit(u).query)); data.update({"page": 1, "level": 1})
try:
    p = S.post("https://pauschal.ruefa.at/hub/ajax/deliver.php", data=data, timeout=40,
               headers={"X-Requested-With": "XMLHttpRequest", "Referer": u}); time.sleep(1.5)
    print("  POST deliver", p.status_code, len(p.text), p.headers.get("content-type"))
    print("    ", p.text[:3000])
    try:
        d = p.json(); print("    keys:", list(d)[:40] if isinstance(d, dict) else type(d))
        blob("ruefa_deliver.json", p.text)
    except Exception as e:
        print("    not json", e)
except Exception as e:
    print("  POST failed", e)

print("\n===== BILLA global js")
r = fetch("https://www.billareisen.at/docroot/assets/js/ITS_global.min.js?2026-10-02-1")
if r is not None:
    grep(r.text, r"childage|tmp_num_children|psbbr|\bpnc\b|pcba|ptba", 12, 250, "g")

print("\n===== AIRSTOP hotel page")
r = fetch("https://airstop.sk/dovolenka/turecko")
if r is not None:
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    data = devalue(_j.loads(m.group(1)))
    big = data["data"].get("5zdtk1gWXn")
    print("    5zd keys:", {k: (type(v).__name__, len(_j.dumps(v, ensure_ascii=False))) for k, v in big.items()} if isinstance(big, dict) else type(big))
    print("    5zd sample:", _j.dumps(big, ensure_ascii=False)[:2500])
    hl = [h for h in re.findall(r'href="(/dovolenka/turecko/[^"]+)"', r.text) if h.count("/") >= 5]
    print("    hotel links:", len(hl), hl[:5])
    sur = [h for h in hl if "sural" in h or "alhambra" in h]
    print("    sural/alhambra links:", sur)
    if hl:
        h = fetch("https://airstop.sk" + (sur[0] if sur else hl[0]))
        if h is not None:
            m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', h.text, re.S)
            d2 = devalue(_j.loads(m.group(1)))
            ts = (d2.get("pinia") or {}).get("tourStore")
            print("    tourStore:", _j.dumps(ts, ensure_ascii=False)[:2000])
            print("    data keys:", {k: len(_j.dumps(v, ensure_ascii=False)) for k, v in d2["data"].items()})
            grep(h.text, r"€", 4, 150, "eur")

print("\n===== RESTPLATZBOERSE")
r = fetch("https://www.restplatzboerse.at/pauschalreisen")
if r is not None:
    print("    scripts:", re.findall(r'<script[^>]+src="([^"]+)"', r.text)[:15])
    print("    hosts:", sorted({urlsplit(h).netloc for h in re.findall(r'(?:href|src|action)="(https?://[^"]+)"', r.text)})[:25])
    print("    forms:", re.findall(r'<form[^>]*>', r.text)[:5])
