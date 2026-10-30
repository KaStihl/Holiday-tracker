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

print("\n===== RUEFA js dump")
j = fetch("https://pauschal.ruefa.at/js/min/search.min.js?id=6492")
if j is not None:
    blob("ruefa_search.min.js", j.text)
h = fetch("https://pauschal.ruefa.at/js/hotelsearch/dist/hotelsearch.min.js?id=492")
if h is not None:
    grep(h.text, r"children=|childAges|\.join\(\"[;,_-]\"\)", 12, 300, "hs")
r = fetch("https://pauschal.ruefa.at/index.php?page=results&level=1&adults=2&start=2027-07-01&until=2027-08-31&anzZimmer=1&airport=VIE&dauer=1024&destination=T%C3%BCrkei")
if r is not None:
    blob("ruefa_results.html", r.text)

print("\n===== BILLA param guesses")
B = ("https://www.billareisen.at/Pauschalreisen/Angebote.html?ttid=PF&bdid=ib&pttid=PF&ptoj=PF&dpfebl=tr%2Cdd%2Cda"
     "&pdf=3380096&pdaf=VIE&dft=apx&psdf=2027-07-01&pedf=2027-08-31&pnnfl=7&pnnfh=14&ptf=1&ps=pr&pdm=pp&idvfmb=1")
def summary(html):
    psb = re.findall(r'psbbr=([^"&]*)', html)[:1]
    copies = re.findall(r'product-desc__copy[^>]*>([^<]+)<', html)
    boards = {}
    for c in copies:
        b = c.split(",")[3].strip() if c.count(",") >= 4 else c
        boards[b] = boards.get(b, 0) + 1
    pages = re.findall(r'Seite 1 von (\d+)', html)[:1]
    prices = re.findall(r'ITS_price">\s*([\d.]+)', html)[:3]
    return f"psbbr={psb} pages={pages} n={len(copies)} boards={boards} prices={prices} first={copies[:1]}"
for extra in ["&na=2&pna=2", "&na=2&pna=2&ppn=1", "&na=2&pna=2&pbf=ai", "&na=2&pna=2&pbtf=ai", "&na=2&pna=2&pmf=ai",
              "&na=2&pna=2&pbof=ai", "&na=1&pna=1&nc=2&pnc=2&pcaf=10%2C12", "&na=1&pna=1&nc=2&pnc=2&pca0=10&pca1=12",
              "&na=1&pna=1&nc=2&pnc=2&pchaf=10%2C12", "&psbbr=pna%3D1%26pnc%3D2%26pca0%3D10%26pca1%3D12"]:
    r = fetch(B + extra)
    if r is not None:
        print("   ", extra, "->", summary(r.text))
r = fetch("https://www.billareisen.at/Pauschalreisen.html")
if r is not None:
    links = re.findall(r'href="(/Pauschalreisen/[^"?]+\.html)"[^>]*>([^<]{2,40})<', r.text)
    pdfs = re.findall(r'href="([^"]*pdf=\d+[^"]*)"', r.text)
    print("    country pages:", sorted(set(links))[:80])
    print("    pdf links:", [re.findall(r"pdf=(\d+)", p)[0] for p in pdfs][:30])
r = fetch("https://www.billareisen.at/Service/AGB.html")
if r is not None:
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", r.text, flags=re.S)))
    grep(t, r"automatisiert|scrap|data.?mining|crawl|Robot|Vervielfältig|Urheber|Nutzung der Website", 6, 250)
r = fetch("https://www.billareisen.at/Service/Impressum.html")
if r is not None:
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", r.text, flags=re.S)))
    grep(t, r"automatisiert|scrap|data.?mining|crawl|Robot|Vervielfältig|Urheber|Nutzungsbedingungen", 6, 250)
