"""Temporary probe (deleted after use): DERTOUR detail app's /api/pricecheck usage. Job log only."""
import re, sys
sys.path.insert(0, "scraper")
from common import get

def p(*a):
    print(*a, flush=True)

def g(url, **kw):
    try:
        return get(url, **kw)
    except Exception as e:
        p(f"!! {url[:150]}: {type(e).__name__} {str(e)[:200]}")
        return None

F = "https://www.fischer.sk"
t = g(F + "/Scripts/web/index.CD3GWOsj.js") or ""
refs = sorted(set(re.findall(r'["\'`]\./assets/([\w.\-]+\.js)["\'`]', t)))
want = [r for r in refs if re.match(r"App(HotelDetail|NdPriceList|HotelTourCards|TourList|TourDetail|Term|Price|Order)", r)]
p("=== candidates:", want, "| all App*Detail/Price/Term:", [r for r in refs if re.search(r"Detail|Price|Term|Book|Order|Occup", r)])
seen = set()
for r in want[:8]:
    js = g(F + "/Scripts/web/assets/" + r) or ""
    deps = sorted(set(re.findall(r'["\'`]\./([\w.\-]+\.js)["\'`]', js)))
    hits = list(re.finditer(r"PRICE_CHECK|pricecheck|priceIsCurrent|isOnline|onRequest", js))
    p(f"=== {r} len {len(js)} hits {len(hits)} deps {deps[:40]}")
    for m in hits[:8]:
        p(f"   ...{js[max(0, m.start()-600):m.end()+900]!r}")
    for d in deps:
        if d in seen or not re.search(r"(?i)price|term|detail|tour|check", d):
            continue
        seen.add(d)
        if len(seen) > 8:
            break
        js2 = g(F + "/Scripts/web/assets/" + d) or ""
        h2 = list(re.finditer(r"PRICE_CHECK|pricecheck|priceIsCurrent|isOnline", js2))
        p(f"  === dep {d} len {len(js2)} hits {len(h2)}")
        for m in h2[:8]:
            p(f"     ...{js2[max(0, m.start()-600):m.end()+900]!r}")
