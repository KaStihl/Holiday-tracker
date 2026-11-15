"""Temporary probe (deleted after use): DERTOUR detail app's /api/pricecheck; Čedok detail availability keys.
Job log only. Read-only requests the offer pages themselves make; no booking, no personal data."""
import collections, json, re, sys
sys.path.insert(0, "scraper")
from common import get
from adapters.cedok import rsc_payload

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
refs = sorted(set(re.findall(r'["\'`]((?:\./|/Scripts/web/|assets/)[\w./\-]+\.js)["\'`]', t)))
p("=== chunk refs:", len(refs), refs[:200])
cand = [r for r in refs if re.search(r"(?i)detail|tour|hotel|price|term|booking|order", r)] or refs
n = 0
for r in cand:
    if n >= 12:
        break
    url = F + "/Scripts/web/" + r.split("/")[-1] if not r.startswith("/") else F + r
    js = g(url) or ""
    n += 1
    hits = [m for m in re.finditer(r"PRICE_CHECK|pricecheck|priceIsCurrent|isOnline|onRequest|naVyziadanie", js)]
    p(f"=== {url} len {len(js)} hits {len(hits)}")
    for m in hits[:6]:
        p(f"   ...{js[max(0, m.start()-800):m.end()+1000]!r}")

# ---- Čedok: detail page of a watched-hotel term (party prices), any availability marker in the payload
u = ("https://www.cedok.sk/dovolena/turecko/turecka-riviera-side/hotel-dream-world-resort-and-spa,AYT2DWR/?id=CgVDZWRvaxIEVklUQxoDQ1pLIgdBWVQyRFdSKAQ6BEcyMjBCBgiA7p3jBkoGCIDjwuMGUAJiBQoDQlRTagUKA0FZVHIDCgEyegUKA0FZVIIBBQoDQlRTigEDCgEykgEGCIDuneMGmgEGCIDjwuMGogEFCgNEQkyqAQMKAUHiAQkKB1Jlc2FiZWXqAQkKB1Jlc2FiZWXyAQkKB1Jlc2FiZWU%253D&airports=BTS%2CVIE&participants%5B0%5D%5Badults%5D=1&participants%5B0%5D%5Bchildren%5D%5B0%5D=30.06.2017&participants%5B0%5D%5Bchildren%5D%5B1%5D=30.06.2015")
h = g(u) or ""
f = rsc_payload(h)
p("=== cedok detail len", len(h), "payload", len(f))
c = collections.Counter(re.findall(r'"([a-zA-Z]*(?:[Aa]vail|[Rr]equest|[Cc]apacit|[Ss]tatus|[Ss]old|[Ff]ree|[Bb]ookable|[Oo]nline|[Vv]acan|[Ss]tock)[a-zA-Z]*)"', f))
p("keys:", c.most_common(40))
for k, _ in c.most_common(8):
    for m in list(re.finditer('"' + k + '"', f))[:2]:
        p(f"   {k}: ...{f[max(0, m.start()-300):m.end()+300]!r}")
p("api refs in page:", sorted(set(re.findall(r'/api/[\w/\-]+', h)))[:30])
