"""Temporary probe (deleted after use): Ruefa multi-gid filter and the hotel page's term calendar. Job log only."""
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
    cards = BeautifulSoup(d.get("value") or "", "lxml").select("div.card-hotel[data-href]")
    p(f"=== {label}: resultCount {d.get('resultCount')} gids {str(d.get('gids'))[:200]} cards {len(cards)}")
    for c in cards[:12]:
        n = " ".join((c.select_one('.hotel-name') or c).get_text(" ").split())[:40]
        p("   ", n, c.get("data-price"), c.get("data-nights"), c.get("data-startdate"), c.get("data-giataid"))
    return cards

deliver("gid space-separated", gid="4922 4923 4924 53099")
deliver("gid comma", gid="4922,4923,4924,53099")
deliver("gid=4924 Saray 7n", gid="4924")
cards = deliver("gid=53099 Resort 7n Aug", gid="53099", start="2027-08-01")

href = "index.php?page=hotel&start=2027-07-01&until=2027-08-31&adults=1&children=12-10&anzZimmer=1&abflughafen=VIE%20BTS&gid=53099&dauer=128"
html = get(IBE + "/" + href)
m = re.search(r"var conf\s*=\s*(\{.*?\});", html, re.S) or re.search(r"conf\s*=\s*(\{.{0,3000}?\});", html, re.S)
p("=== conf:", m.group(0)[:3000] if m else None)
for m2 in list(re.finditer(r"conf\.[a-zA-Z]+\s*=", html))[:40]:
    p("  ", html[m2.start():m2.start()+120].split("\n")[0])
if m:
    try:
        conf = json.loads(m.group(1))
    except Exception as e:
        p("conf not json", e); conf = None
    if conf:
        hh = {"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/" + href}
        for ep, data in (("ajax_kalender.php", {"conf": json.dumps(conf), "date": "", "debug": ""}),
                         ("additionalOffersHotelpage.php", {"conf": json.dumps(conf), "price": "", "data": "", "debug": ""})):
            try:
                t = get(IBE + "/hub/ajax/" + ep, method="POST", data=data, headers=hh)
            except Exception as e:
                p(f"=== {ep}: {e}"); continue
            p(f"=== {ep}: len {len(t)}")
            s = BeautifulSoup(t, "lxml")
            p("  text:", " ".join(s.get_text(" ").split())[:2500])
            for el in s.select("[data-offer],[data-preis],[data-date],[data-price]")[:15]:
                p("   el", el.name, {k: v for k, v in el.attrs.items() if k.startswith("data")})
            p("  raw head:", t[:2500])
