"""Temporary probe (deleted after use): how pauschal.ruefa.at filters by hotel. Prints to the job log only."""
import json, re, sys
sys.path.insert(0, "scraper")
from bs4 import BeautifulSoup
from common import get
from config import CONFIG
from adapters import ruefa

IBE = ruefa.IBE
H = {"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/index.php?page=results"}

def p(*a):
    print(*a, flush=True)

def ac(term):
    res = get(IBE + "/hub/ajax/getDestination.php", params={"destination": term}, as_json=True, headers=H)
    p(f"=== getDestination {term!r}: {len(res or [])} entries")
    for x in res or []:
        p("   ", json.dumps(x, ensure_ascii=False)[:300])
    return res or []

hits = ac("Sural") + ac("Royal Alhambra")

# JS of the results page: how hotelSearchtext / topGid / level are used
html = get(IBE + "/index.php", params={"page": "results"})
srcs = re.findall(r'<script[^>]+src="([^"]+)"', html)
p("=== scripts:", srcs)
for s in srcs:
    if any(k in s for k in ("jquery", "bootstrap", "gtm", "google", "cookie")):
        continue
    url = s if s.startswith("http") else IBE + "/" + s.lstrip("/")
    if "ruefa" not in url:
        continue
    try:
        js = get(url)
    except Exception as e:
        p("  fail", url, e); continue
    for k in ("hotelSearchtext", "topGid", "level", "giata", "gid", "deliver.php", "getOffers", "page=hotel"):
        for m in list(re.finditer(re.escape(k), js))[:4]:
            p(f"--- {url.split('/')[-1]} [{k}] ...{js[max(0,m.start()-200):m.end()+250]!r}")
# inline scripts mentioning suchConfig
for m in list(re.finditer(r"suchConfig|hotelSearchtext|topGid", html))[:12]:
    p(f"--- inline ...{html[max(0,m.start()-200):m.end()+300]!r}")

def deliver(label, **over):
    f = ruefa.form(CONFIG, ruefa.DEST_IDS["TR"], 7, 1)
    f["dauer"] = ""
    f.update(over)
    try:
        d = get(IBE + "/hub/ajax/deliver.php", method="POST", data=f, headers=H, as_json=True)
    except Exception as e:
        p(f"=== {label}: {e}"); return None
    soup = BeautifulSoup(d.get("value") or "", "lxml")
    cards = soup.select("div.card-hotel[data-href]") or soup.select("[data-href]")
    p(f"=== {label}: keys {list(d)} resultCount {d.get('resultCount')} level {d.get('level')} cards {len(cards)} len {len(d.get('value') or '')}")
    for c in cards[:12]:
        n = " ".join((c.select_one('.hotel-name') or c).get_text(" ").split())[:60]
        p("   ", n, c.get("data-price"), c.get("data-nights"), c.get("data-startdate"), c.get("data-giataid"), c.get("data-href")[:200])
    if not cards:
        p("   value head:", (d.get("value") or "")[:1500])
    return d

gid = next((x.get("id") for x in hits if x.get("field") == "hotelname" and "alhambra" in (x.get("name") or "").lower()), None)
p("alhambra id", gid)
deliver("hotelSearchtext=Royal Alhambra", hotelSearchtext="Royal Alhambra", dauer=str(2**7))
if gid:
    deliver(f"topGid={gid} level2", topGid=str(gid), dauer=str(2**7))
    d = deliver(f"level3 gid={gid}", level="3", topGid=str(gid), gid=str(gid), dauer=str(2**7))
    if d:
        p("level3 raw head:", (d.get("value") or "")[:3000])
