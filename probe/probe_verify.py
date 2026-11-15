"""Temporary probe (deleted after use): Ruefa session needs for the price check; DERTOUR /api/pricecheck usage.
Job log only. Read-only requests the offer pages themselves make; no booking, no personal data."""
import json, random, re, string, sys
sys.path.insert(0, "scraper")
import requests
from bs4 import BeautifulSoup
import common
from common import get

IBE = "https://pauschal.ruefa.at"

def p(*a):
    print(*a, flush=True)

def g(url, **kw):
    try:
        return get(url, **kw)
    except Exception as e:
        p(f"!! {url[:150]}: {type(e).__name__} {str(e)[:200]}")
        return None

def fresh():
    common._local.session = None

href = ("index.php?page=hotel&start=2027-07-01&until=2027-07-08&adults=1&cabinClass=economy&ankunftshafen=AYT"
        "&children=12-10&anzZimmer=1&abflughafen=VIE%20BTS&reisetag=2027-07-01&rq=1&rva=VFVJRA==&bu=AYT41041"
        "&gid=239871&pos=5")
conf = {"start": "2027-07-01", "until": "2027-07-08", "adults": "1", "children": "12-10", "destinationName": "",
        "destinationId": "", "airline": "", "dauer": "128", "abflughafen": "VIE BTS", "ankunftshafen": "AYT",
        "preis": "", "stars": "", "bewertung": "", "name": "", "veranstalter": "VFVJRA==", "reisetag": "2027-07-01",
        "verpflegung": "", "room": "", "rq": "1", "gid": "239871", "hotelOnly": "", "nonStop": "", "stops": "",
        "transfer": "", "baggageincluded": "", "sort": "price", "depApt": "", "dstApt": "", "rfId": "", "offset": "",
        "dstOutMax": "", "dstOutMin": "", "depOutMax": "", "depOutMin": "", "cabinClass": "economy"}
H = {"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/" + href, "Origin": IBE}

def additional(c):
    t = g(IBE + "/hub/ajax/additionalOffersHotelpage.php", method="POST", headers=H,
          data={"conf": json.dumps(c), "price": "", "data": "", "debug": ""}) or ""
    s = BeautifulSoup(t, "lxml")
    out = []
    for o in s.select(".hotel-offer[data-offer]"):
        b = o.select_one(".additionalButton[data-price]")
        out.append((float(b["data-price"]) if b else 9e9, o["data-offer"], o.get("data-rva")))
    p(f"   additional len {len(t)} offers {len(out)} boards {sorted({x[1].split('*')[8] for x in out})}")
    return sorted(out)

def check(x, label):
    r = g(IBE + "/hub/ajax/checkPrice.php", method="POST", headers=H,
          data={"conf": json.dumps(dict(conf, veranstalter=x[2])), "data": x[1],
                "bid": "".join(random.choice(string.ascii_letters + string.digits) for _ in range(10)),
                "recheck": "0", "isHotelPriceCheck": "1", "url": IBE + "/" + href, "alternative": "", "debug": ""}) or ""
    p(f"=== {label}: {x[0]} {x[1][-45:]} -> {re.sub(r'<preisText>.*</preisText>', '', r, flags=re.S)[:300]!r}")

fresh()
p("=== S1: fresh session, no hotel page")
offs = additional(conf)
its = [x for x in offs if x[1].endswith("*ITS") and "ST04-SU" in x[1]]
if its:
    check(its[0], "S1 ITS suite")
p("cookies S1:", list(common.session().cookies.keys()))
fresh()
p("=== S2: hotel page, AI filter")
g(IBE + "/" + href)
offs = additional(dict(conf, verpflegung="AI AIP AIU AIR"))
its = [x for x in offs if x[1].endswith("*ITS") and "ST04-SU" in x[1]]
if its:
    check(its[0], "S2 ITS suite")

# ---- DERTOUR: how the detail page uses /api/pricecheck and the tour's priceIsCurrent/isOnline flags
t = g("https://www.fischer.sk/Scripts/web/index.CD3GWOsj.js") or ""
for pat in (r"PRICE_CHECK(?!=)", r"priceIsCurrent", r"\.isOnline\b", r"HOTEL_API(?!=)", r"TOUR_SEARCH(?!=)"):
    ms = [m for m in re.finditer(pat, t)]
    p(f"=== fischer {pat}: {len(ms)} hits")
    for m in ms[:6]:
        p(f"   ...{t[max(0, m.start()-900):m.end()+1200]!r}")
