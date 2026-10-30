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

print("\n===== BILLA JS")
for u in ["https://www.billareisen.at/docroot/backend/js/search.js?2026-10-02-1",
          "https://www.billareisen.at/docroot/backend/js/ajax_update_central.js?2026-10-02-1",
          "https://www.billareisen.at/docroot/backend/js/ajax.js?2026-10-02-1"]:
    r = fetch(u)
    if r is not None:
        print(r.text[:1600])
r = fetch("https://www.billareisen.at/docroot/assets/js/ITS_callbacks.js?2026-10-02-1")
if r is not None:
    grep(r.text, r"childage|pnc|pcaf|pchaf|ages", 10, 250, "js")
r = fetch("https://script.billareisen.at/api.v1.js")
if r is not None:
    grep(r.text, r"childage|pnc|pca|ages|Angebote\.html", 10, 250, "api")

print("\n===== BILLA SEARCH with ages guesses")
base = ("https://www.billareisen.at/Pauschalreisen/Angebote.html?ttid=PF&bdid=ib&pttid=PF&ptoj=PF&dpfebl=tr%2Cdd%2Cda"
        "&pdf=3380096&pdaf=VIE&dft=apx&psdf=2027-07-01&pedf=2027-08-31&pnnfl=7&pnnfh=14&na=1&nc=2&pna=1&pnc=2&ptf=1&ps=pr&pdm=pp&idvfmb=1")
for extra in ["&pcaf=10%2C12", "&pca=10%2C12&ca=10%2C12"]:
    r = fetch(base + extra)
    if r is not None:
        grep(r.text, r"psbbr=[^\"&]*(?:&amp;)?", 2, 20, "psbbr")
        grep(r.text, r"ITS_price\">[^<]*", 2, 0, "price")
        grep(r.text, r"(\d+)\s*(?:Angebote|Hotels|Ergebnisse|Reisen) gefunden|ITS_MOD_result[\w-]*count[^<]*<[^<]*", 2, 100, "count")
r = fetch(base + "&pcaf=10%2C12")
if r is not None:
    blob("billa_tuerkei.html", r.text)
    m = re.search(r'href="(/Reisen/[^"]+)"', r.text)
    if m:
        d = fetch(urljoin(r.url, m.group(1).replace("&amp;", "&")))
        if d is not None:
            grep(d.text, r"ITS_price|Gesamtpreis|Reisepreis", 5, 300, "detail")
            grep(d.text, r"Abflug|Wien|VIE", 3, 150, "dep")

print("\n===== HOFER")
r = fetch("https://www.hofer-reisen.at/at/destination/asien/tuerkei/antalya")
if r is not None:
    hrefs = sorted(set(h.replace("&amp;", "&") for h in re.findall(r'href="(/at/[^"]+)"', r.text)))
    print("    hrefs:", [h for h in hrefs if "reiseangebote" not in h][:60])
    prods = [h for h in hrefs if "reiseangebote" in h]
    print("    product hrefs:", len(prods), prods[:3])
    grep(r.text, r"suche|search[A-Z]\w*Url|/at/s/", 6, 150, "search")
    blob("hofer_antalya.html", r.text)

print("\n===== AIRSTOP")
r = fetch("https://airstop.sk/dovolenka/turecko")
if r is not None:
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    data = devalue(json.loads(m.group(1)))
    op = data["data"].get("offer-packages")
    s = json.dumps(op, ensure_ascii=False)
    print("    offer-packages type", type(op).__name__, "len", len(op) if hasattr(op, "__len__") else "-", s[:3000])
    print("    data keys:", {k: (type(v).__name__, len(json.dumps(v, ensure_ascii=False))) for k, v in data["data"].items()})
    st = data.get("state") or {}
    print("    state keys:", list(st)[:40])
    pin = data.get("pinia") or {}
    print("    pinia:", {k: list(v)[:30] if isinstance(v, dict) else type(v).__name__ for k, v in pin.items()})
r = fetch("https://airstop.sk/_nuxt/ffoz2nQQ.js")
if r is not None:
    grep(r.text, r"offer-packages|offerPackages", 8, 300, "js")

print("\n===== RUEFA JS")
for u in ["https://pauschal.ruefa.at/js/min/search.min.js?id=6492", "https://pauschal.ruefa.at/js/min/basic.min.js?id=492",
          "https://pauschal.ruefa.at/js/hotelsearch/dist/hotelsearch.min.js?id=492"]:
    r = fetch(u)
    if r is not None:
        grep(r.text, r"index\.php\?|ajax\.php|\.php\?|page=|xhr|fetch\(|\$\.(?:get|post|ajax)", 12, 160, "js")

print("\n===== NECKERMANN pauschal")
r = fetch("https://pauschal.neckermann-reisen.de/")
if r is not None:
    print(r.text[:960])
