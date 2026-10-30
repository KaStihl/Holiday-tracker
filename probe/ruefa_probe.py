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

def deliver(label, **over):
    f = ruefa.form(CONFIG, "", 7, 1)
    f["verpflegung"] = ""
    f.update(over)
    try:
        d = get(IBE + "/hub/ajax/deliver.php", method="POST", data=f, headers=H, as_json=True)
    except Exception as e:
        p(f"=== {label}: {e}"); return None
    soup = BeautifulSoup(d.get("value") or "", "lxml")
    cards = soup.select("div.card-hotel[data-href]")
    p(f"=== {label}: resultCount {d.get('resultCount')} level {d.get('level')} firstGid {d.get('firstGid')} gids {str(d.get('gids'))[:200]} cards {len(cards)}")
    for c in cards[:12]:
        n = " ".join((c.select_one('.hotel-name') or c).get_text(" ").split())[:60]
        p("   ", n, c.get("data-price"), c.get("data-nights"), c.get("data-startdate"), c.get("data-giataid"),
          " ".join((c.select_one('.board') or c).get_text(" ").split())[:40], c.get("data-href"))
    return cards

deliver("gid=239871 any board 7n", gid="239871")
cards = deliver("hotelSearchtext=Sural any board 10n", hotelSearchtext="Sural", dauer=str(2**10))
deliver("hotelSearchtext=Royal Alhambra 14n July", hotelSearchtext="Royal Alhambra", dauer=str(2**14), until="2027-07-31")

if cards:
    href = cards[0]["data-href"]
    html = get(IBE + "/" + href)
    p("=== hotel page len", len(html))
    p("scripts:", re.findall(r'<script[^>]+src="([^"]+)"', html))
    for m in list(re.finditer(r"ajax/[a-zA-Z_]+\.php|\.ajax\(|fetch\(", html))[:15]:
        p(f"--- ...{html[max(0,m.start()-400):m.end()+400]!r}")
    for s in re.findall(r'<script[^>]+src="(/js/[^"]+)"', html):
        if "search.min" in s or "basic.min" in s or "history" in s or "hotelsearch" in s or "searchParams" in s:
            continue
        js = get(IBE + s)
        for m in list(re.finditer(r"ajax/[a-zA-Z_]+\.php", js))[:10]:
            p(f"--- {s} ...{js[max(0,m.start()-300):m.end()+500]!r}")
