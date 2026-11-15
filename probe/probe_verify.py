"""Temporary probe (deleted after use): how Ruefa / DERTOUR verify an offer's availability. Job log only.
Read-only requests the offer pages themselves make (offer list + the automatic price check); no booking."""
import json, random, re, string, sys
sys.path.insert(0, "scraper")
from bs4 import BeautifulSoup
from common import get

IBE = "https://pauschal.ruefa.at"
N = {"r": 0, "f": 0}

def p(*a):
    print(*a, flush=True)

def g(url, k="r", **kw):
    N[k] += 1
    try:
        return get(url, **kw)
    except Exception as e:
        p(f"!! {url[:150]}: {type(e).__name__} {str(e)[:200]}")
        return None

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
t = g(IBE + "/hub/ajax/additionalOffersHotelpage.php", method="POST", headers=H,
      data={"conf": json.dumps(conf), "price": "", "data": "", "debug": ""}) or ""
p("=== additional len", len(t))
s = BeautifulSoup(t, "lxml")
conts = s.select(".additionalOfferContainer")
p("containers", len(conts))
for i, c in enumerate(conts[:3]):
    p(f"--- container {i} html:", str(c)[:5000])
offers = []
for c in conts:
    room = " ".join((c.select_one("b.detailHl") or c).get_text(" ").split())[:80]
    for o in c.select(".hotel-offer"):
        offers.append((float(o.get("data-price") or 0), o.get("data-offer"), o.get("data-rva"), room,
                       " ".join((o.select_one(".roomBoardColumn") or o).get_text(" ").split())[:120],
                       {k: v[:80] for k, v in o.attrs.items() if k.startswith("data")}))
p("offers", len(offers))
for x in sorted(offers)[:40]:
    p("  ", x)
p("other hotel-offer outside containers:", len(s.select(".hotel-offer")))
p("text head:", " ".join(s.get_text(" ").split())[:3000])

def bid():
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(10))

for price, data, rva, room, board, attrs in sorted(offers)[:7]:
    c2 = dict(conf, veranstalter=rva)
    r = g(IBE + "/hub/ajax/checkPrice.php", method="POST", headers=H,
          data={"conf": json.dumps(c2), "data": data, "bid": bid(), "recheck": "0", "isHotelPriceCheck": "1",
                "url": IBE + "/" + href, "alternative": "", "debug": ""}) or ""
    p(f"=== checkPrice {price} {room} | {board[:60]} -> len {len(r)}: {r[:1500]!r}")

# ---- Fischer app bundle: which API the detail page calls for price/availability
for js in ("/Scripts/web/index.BUniwKnw.js", "/Scripts/web/index.CD3GWOsj.js"):
    t = g("https://www.fischer.sk" + js, "f") or ""
    apis = sorted(set(re.findall(r'["\'`](/api/[\w/\-{}$]+)', t)))
    imports = sorted(set(re.findall(r'["\'](\./[\w.\-]+\.js|/Scripts/web/[\w.\-]+\.js)', t)))
    p(f"=== {js} len {len(t)} apis: {apis}\n imports: {imports[:80]}")
    for m in list(re.finditer(r"priceIsCurrent|isOnline|checkPrice|actualPrice|available|onRequest|getTourDetail|termsHash", t))[:30]:
        p(f"   ...{t[max(0, m.start()-250):m.end()+250]!r}")
p("requests: ruefa", N["r"], "fischer", N["f"])
