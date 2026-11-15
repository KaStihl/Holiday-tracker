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
sess_html = g(IBE + "/" + href) or ""
p("cookies after hotel page:", list(__import__("common").session().cookies.keys()))
sb = g(IBE + "/hub/ajax/sidebar.php", method="POST", headers=H,
       data={"conf": json.dumps(conf), "data": "", "loadAlternatives": "1", "debug": ""}) or ""
try:
    sj = json.loads(sb)
    p("sidebar keys", list(sj), "furtherDetails", {k: str(v)[:200] for k, v in (sj.get("furtherDetails") or {}).items()})
    p("sidebar internal/hotelDetails:", str(sj.get("hotelDetails"))[:1500])
except Exception as e:
    p("sidebar not json", e, sb[:1500])
t = g(IBE + "/hub/ajax/additionalOffersHotelpage.php", method="POST", headers=H,
      data={"conf": json.dumps(conf), "price": "", "data": "", "debug": ""}) or ""
p("=== additional len", len(t))
s = BeautifulSoup(t, "lxml")
for f in s.select(".flightColumn"):
    f.decompose()
conts = s.select(".additionalOfferContainer")
p("containers", len(conts))
ho = s.select_one(".hotel-offer")
p("--- one offer html:", str(ho)[:6000])
offers = []
for c in conts:
    room = " ".join((c.select_one("b.detailHl") or c).get_text(" ").split())[:80]
    h5 = " ".join((c.select_one("h5") or c).get_text(" ").split())[:80]
    for o in c.select(".hotel-offer"):
        pr = " ".join((o.select_one(".priceInfo") or o).get_text(" ").split())[:100]
        offers.append((float(c.get("data-price") or 0), pr, o.get("data-offer"), o.get("data-rva"), h5, room,
                       " ".join((o.select_one(".roomBoardColumn") or o).get_text(" ").split())[:60], o.get("class")))
p("offers", len(offers))
for x in offers[:60]:
    p("  ", x)
def bid():
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
def num(x):
    m = re.search(r"(\d[\d.]*)", x or "")
    return float(m[1].replace(".", "")) if m else 9e9
srt = sorted(offers, key=lambda x: num(x[1]))
for x in [o for o in srt if "AYT41041" in (o[2] or "")][:2] + srt[:7]:
    c2 = dict(conf, veranstalter=x[3])
    r = g(IBE + "/hub/ajax/checkPrice.php", method="POST", headers=H,
          data={"conf": json.dumps(c2), "data": x[2], "bid": bid(), "recheck": "0", "isHotelPriceCheck": "1",
                "url": IBE + "/" + href, "alternative": "", "debug": ""}) or ""
    p(f"=== checkPrice {x[1]} | {x[4]} | {x[5]} | {x[6]} | {x[2][-40:]} -> {re.sub(r'<preisText>.*</preisText>', '', r)[:600]!r}")

# ---- Fischer app bundle: which API the detail page calls for price/availability
for js in ("/Scripts/web/index.BUniwKnw.js", "/Scripts/web/index.CD3GWOsj.js"):
    t = g("https://www.fischer.sk" + js, "f") or ""
    apis = sorted(set(re.findall(r'["\'`](/api/[\w/\-{}$]+)', t)))
    imports = sorted(set(re.findall(r'["\'](\./[\w.\-]+\.js|/Scripts/web/[\w.\-]+\.js)', t)))
    p(f"=== {js} len {len(t)} apis: {apis}\n imports: {imports[:80]}")
    for m in list(re.finditer(r"/api/pricecheck|priceIsCurrent|/api/hotelapi|/api/toursearch", t))[:20]:
        p(f"   ...{t[max(0, m.start()-700):m.end()+900]!r}")
p("requests: ruefa", N["r"], "fischer", N["f"])
