"""TEMPORARY endpoint discovery for watched hotels (prints to the job log only; removed after use)."""
import re, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scraper"))
from common import get, allowed, _robots  # noqa

def show(label, url, **kw):
    try:
        t = get(url, retries=0, delay=1, **kw)
    except Exception as e:
        print(f"## {label} {url} -> {type(e).__name__} {str(e)[:200]}")
        return ""
    print(f"## {label} {url} -> {len(t)} bytes, sural={t.lower().count('sural')} alhambra={t.lower().count('alhambra')}")
    return t

def ctx(t, word, n=4, w=250):
    for m in list(re.finditer(word, t, re.I))[:n]:
        print("   ..." + t[max(0, m.start()-w):m.end()+w].replace("\n", " ") + "...")

# ---------- DERTOUR / kartago ----------
K = "https://www.kartago.sk"
home = show("kartago home", K + "/")
js = sorted(set(re.findall(r'src="(/Scripts/[^"]+\.js)"', home)))
print("kartago scripts:", js)
for src in js:
    t = show("kartago js", K + src)
    apis = sorted(set(re.findall(r'["\'](/api/[A-Za-z0-9_/\-]+)', t)))
    print("  apis:", apis)
    for word in ("fulltext", "Fulltext", "suggest", "autocomplete", "HID", "hotelId"):
        if word in t:
            print("  --", word); ctx(t, re.escape(word), 3, 200)
for p in ("/api/searchapi/fulltext?text=sural", "/api/fulltext?text=sural", "/api/searchapi/suggest?text=sural",
          "/api/search/fulltext?query=sural", "/api/fulltextapi/search?text=sural"):
    t = show("kartago guess", K + p, headers={"Accept": "application/json"})
    if t: print("   ", t[:600])

# ---------- Satur ----------
S = "https://www.satur.sk"
h = show("satur home", S + "/")
for f in re.findall(r"<form[^>]*>", h)[:8]: print("  form:", f[:300])
for i in re.findall(r"<input[^>]*>", h)[:15]: print("  input:", i[:200])
for word in ("vyhladav", "hladat", "search", "fulltext", "autocomplete", "suggest"):
    print("  --", word); ctx(h, word, 2, 150)
for p in ("/vyhladavanie?q=sural", "/hladat?q=sural", "/search?q=sural", "/vyhladavanie?fulltext=sural",
          "/dovolenka/turecko/side", "/dovolenka?q=sural"):
    t = show("satur guess", S + p)
    print("   produkt links:", sorted(set(re.findall(r'href="(/produkt/[^"?]*(?:sural|sueral|alhambra)[^"]*)"', t, re.I)))[:10])
rb = show("satur robots", S + "/robots.txt")
print([l for l in rb.splitlines() if "itemap" in l])

# ---------- Cedok ----------
C = "https://www.cedok.sk"
rb = show("cedok robots", C + "/robots.txt"); print(rb[:1500])
h = show("cedok home", C + "/")
for word in ("fulltext", "searchQuery", "suggest", "autocomplete", "vyhladavanie"):
    print("  --", word); ctx(h, word, 2, 150)
for p in ("/vysledky-vyhladavania/?q=sural", "/vyhladavanie/?q=sural", "/vysledky-vyhladavania/dovolenky/turecko/?query=sural",
          "/hledani/?q=sural"):
    t = show("cedok guess", C + p)
    print("   dovolena links:", sorted(set(re.findall(r'href="(/dovolena/[^"]*(?:sural|alhambra)[^"]*)"', t, re.I)))[:10])
