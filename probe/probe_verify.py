"""Temporary probe (deleted after use): how Ruefa / DERTOUR / Čedok verify an offer's availability. Job log only.
Read-only GETs/POSTs that the offer pages themselves make; no booking, no personal data."""
import json, re, sys
sys.path.insert(0, "scraper")
from bs4 import BeautifulSoup
from common import get

IBE = "https://pauschal.ruefa.at"
N = {"req": 0}

def p(*a):
    print(*a, flush=True)

def g(url, **kw):
    N["req"] += 1
    try:
        return get(url, **kw)
    except Exception as e:
        p(f"!! {url[:150]}: {type(e).__name__} {str(e)[:200]}")
        return None

def ctx(text, pat, w=300, k=12):
    for m in list(re.finditer(pat, text, re.I))[:k]:
        p(f"   ...{text[max(0, m.start()-w):m.end()+w]!r}")

# ---------------- Ruefa ----------------
href = ("index.php?page=hotel&start=2027-07-01&until=2027-07-08&adults=1&cabinClass=economy&ankunftshafen=AYT"
        "&children=12-10&anzZimmer=1&abflughafen=VIE%20BTS&reisetag=2027-07-01&rq=1&rva=VFVJRA==&bu=AYT41041"
        "&gid=239871&pos=5")
html = g(IBE + "/" + href) or ""
p("=== RUEFA hotel page len", len(html))
scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
p("scripts:", scripts)
m = re.search(r"var conf\s*=\s*(\{.*?\});\s*\n", html, re.S) or re.search(r"conf\s*=\s*(\{.*?\});", html, re.S)
conf = None
if m:
    p("conf raw:", m.group(1)[:4000])
    try:
        conf = json.loads(m.group(1))
    except Exception as e:
        p("conf not json:", e)
p("ajax endpoints in page:", sorted(set(re.findall(r"[\w/\-.]*ajax/[\w\-]+\.php", html))))
p("php endpoints in page:", sorted(set(re.findall(r"[\w/\-]+\.php", html)))[:80])
ctx(html, r"additionalOffers|vakanz|verfueg|verfüg|availability|checkOffer|offerDetail|booking", 250, 15)
js_eps = {}
for s in scripts:
    if not s.startswith("/") or s.startswith("//"):
        continue
    js = g(IBE + s) or ""
    eps = sorted(set(re.findall(r"[\w/\-.]*\.php[\w?=&]*", js)))
    p(f"=== JS {s} len {len(js)} endpoints: {eps[:60]}")
    for e in eps:
        js_eps.setdefault(e, s)
    ctx(js, r"additionalOffers|vakanz|verfueg|verfüg|availab|check[A-Z]\w*|offerDetail|bookingStep|buchung", 250, 25)
p("=== all js endpoints:", sorted(js_eps))
if conf:
    hh = {"X-Requested-With": "XMLHttpRequest", "Referer": IBE + "/" + href}
    t = g(IBE + "/hub/ajax/additionalOffersHotelpage.php", method="POST",
          data={"conf": json.dumps(conf), "price": "", "data": "", "debug": ""}, headers=hh)
    if t:
        p("=== additionalOffersHotelpage len", len(t))
        p("raw head:", t[:6000])
        s = BeautifulSoup(t, "lxml")
        p("text:", " ".join(s.get_text(" ").split())[:5000])
        for el in s.select("[data-offer],[data-preis],[data-price],[data-href],[data-bu],[data-angebot]")[:40]:
            p("  el", el.name, {k: v[:200] for k, v in el.attrs.items() if k.startswith("data") or k in ("href", "class")})
        links = sorted(set(re.findall(r'(?:href|data-href)="([^"]+)"', t)))
        p("links:", links[:40])

# ---------------- Fischer / Kartago (DERTOUR) ----------------
furl = ("https://www.fischer.sk/turecko/turecka-riviera/side-kumkoy/side-colakli/royal-alhambra-palace?DS=256"
        "&GIATA=239871&D=63260%7C63288%7C63448%7C64152%7C64153%7C64154%7C64157%7C211801%7C211814%7C212113"
        "&HID=469&MT=5&DI=AU&RCS=SU01&NN=7&MNN=7%7C8%7C9%7C10%7C11%7C12%7C13%7C14")
rob = g("https://www.fischer.sk/robots.txt")
p("=== fischer robots:", rob)
fh = g(furl) or ""
p("=== FISCHER detail len", len(fh))
fs = re.findall(r'<script[^>]+src="([^"]+)"', fh)
p("scripts:", fs)
for s in fs:
    if "/Scripts/" in s and s.startswith("/"):
        js = g("https://www.fischer.sk" + s) or ""
        apis = sorted(set(re.findall(r'["\'`](/api/[\w/\-]+)', js)))
        p(f"=== JS {s} len {len(js)} apis: {apis}")
        ctx(js, r"availab|dostupn|checkPrice|checkTour|getTourDetail|offerCheck|onRequest|na vy\\u017eiadanie|freeCapacity", 200, 15)
