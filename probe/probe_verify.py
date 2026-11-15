"""Temporary probe (deleted after use): how Ruefa / DERTOUR / Čedok verify an offer's availability. Job log only.
Read-only GETs/POSTs that the offer pages themselves make; no booking, no personal data."""
import json, re, sys
sys.path.insert(0, "scraper")
from bs4 import BeautifulSoup
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

def chunks(label, text, n=3000):
    for i in range(0, len(text), n):
        p(f"[{label} {i}] {text[i:i+n]!r}")

js = g(IBE + "/js/min/ajaxLoadDetails.min.js?id=494") or ""
chunks("ajaxLoadDetails", js)
href = ("index.php?page=hotel&start=2027-07-01&until=2027-07-08&adults=1&cabinClass=economy&ankunftshafen=AYT"
        "&children=12-10&anzZimmer=1&abflughafen=VIE%20BTS&reisetag=2027-07-01&rq=1&rva=VFVJRA==&bu=AYT41041"
        "&gid=239871&pos=5")
html = g(IBE + "/" + href) or ""
soup = BeautifulSoup(html, "lxml")
for i, s in enumerate(soup.find_all("script")):
    if s.get("src"):
        continue
    t = s.string or ""
    if len(t.strip()) > 20 and "gtag" not in t[:200]:
        chunks(f"inline{i}", t[:12000])
# checkPrice / sidebar markup on the page
for sel in ("#checkPrice", "#sidebar", "#kalender", ".additionalOfferContainer", ".hotel-offer"):
    for el in soup.select(sel)[:2]:
        p(f"=== {sel}:", str(el)[:2500])

fh = g("https://www.fischer.sk/turecko/turecka-riviera/side-kumkoy/side-colakli/royal-alhambra-palace?DS=256"
       "&GIATA=239871&D=63260%7C63288%7C63448%7C64152%7C64153%7C64154%7C64157%7C211801%7C211814%7C212113"
       "&HID=469&MT=5&DI=AU&RCS=SU01&NN=7&MNN=7%7C8%7C9%7C10%7C11%7C12%7C13%7C14") or ""
p("=== fischer script tags:", re.findall(r"<script[^>]*>", fh)[:40])
p("=== fischer /api/ strings:", sorted(set(re.findall(r"/api/[\w/\-]+", fh))))
p("=== fischer .js:", sorted(set(re.findall(r"[\w/\-.]+\.js(?:\?[\w=.\-]*)?", fh)))[:60])
