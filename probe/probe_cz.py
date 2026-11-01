"""Temporary probe (deleted after use). Prints to the job log only."""
import json, re, sys, traceback
sys.path.insert(0, "scraper")
import requests
from common import get, session, allowed, _robots, UA

def p(*a):
    print(*a, flush=True)

def robots(base):
    try:
        r = session().get(base + "/robots.txt", timeout=20)
        p(f"##### ROBOTS {base}: {r.status_code} {r.headers.get('server')} {r.headers.get('content-type')}")
        p(r.text[:3000])
    except Exception as e:
        p(f"##### ROBOTS {base}: {e}")

def raw(url, n=0, show_headers=True, **kw):
    """Plain fetch (still robots-checked) printing status, headers, and optionally body head."""
    if not allowed(url):
        p(f"##### {url}: DISALLOWED by robots"); return None
    try:
        r = session().get(url, timeout=30, **kw)
    except Exception as e:
        p(f"##### {url}: {e}"); return None
    p(f"##### {url} -> {r.status_code} {r.url} len={len(r.text)} ct={r.headers.get('content-type')} server={r.headers.get('server')}")
    if show_headers:
        p("   headers:", {k: v[:120] for k, v in r.headers.items() if k.lower() in ("set-cookie", "cf-ray", "x-powered-by", "x-cache", "via", "x-datadome", "x-akamai-transformed", "server-timing", "x-frame-options")})
    if n:
        p(r.text[:n])
    return r

def ctx(text, pat, w=200, k=6, label=""):
    for m in list(re.finditer(pat, text))[:k]:
        p(f"   [{label}{pat}] ...{text[max(0, m.start()-w):m.end()+w]!r}")

def scripts(html, base):
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', html)
    out = []
    for s in srcs:
        if s.startswith("//"):
            s = "https:" + s
        elif s.startswith("/"):
            s = base + s
        elif not s.startswith("http"):
            s = base + "/" + s
        out.append(s)
    return out

def apis(text, label):
    found = sorted(set(re.findall(r'["\'`](/?(?:api|ajax|services?|search|offer|hotel)[A-Za-z0-9_\-/.]{2,80})["\'`]', text)))
    p(f"   [{label}] api-like strings ({len(found)}):", found[:120])
    hosts = sorted(set(re.findall(r'https?://[a-z0-9.\-]+\.[a-z]{2,}(?:/[A-Za-z0-9_\-/.]*)?', text)))
    p(f"   [{label}] urls ({len(hosts)}):", [h for h in hosts if not any(x in h for x in ("w3.org", "schema.org", "google", "facebook"))][:80])

def section(name, fn):
    p(f"\n================ {name} ================")
    try:
        fn()
    except Exception:
        traceback.print_exc(file=sys.stdout)

# ---------------------------------------------------------------- ECB
def ecb():
    robots("https://www.ecb.europa.eu")
    r = raw("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml", n=0)
    if r is not None:
        ctx(r.text, r"CZK", 80, 2)

# ---------------------------------------------------------------- Coral
def coral():
    for base in ("https://www.coraltravel.cz", "https://www.coraltravel.sk", "https://coraltravel.sk"):
        robots(base)
    r = raw("https://www.coraltravel.cz/", n=1500)
    if r is not None and r.ok:
        ss = scripts(r.text, "https://www.coraltravel.cz")
        p("   scripts:", ss)
        apis(r.text, "home")
        ctx(r.text, r"(?i)obchodn[ií] podm|podm[ií]nky|terms", 150, 6)
        ctx(r.text, r"__NEXT_DATA__|__NUXT__|window\.__", 150, 4)
        ctx(r.text, r"(?i)brno|ostrava|praha|bratislav|v[ií]de[nň]", 120, 8)
    raw("https://www.coraltravel.sk/", n=800)
    h = raw("https://www.coraltravel.cz/hotels/turkey/royal-alhambra-palace-side/", n=0)
    if h is not None and h.ok:
        t = h.text
        apis(t, "hotel")
        p("   scripts:", scripts(t, "https://www.coraltravel.cz"))
        ctx(t, r"__NEXT_DATA__|__NUXT__|window\.__|application/json", 200, 6)
        ctx(t, r"(?i)K[čc]|CZK|price|cena", 150, 8)
        ctx(t, r"(?i)brno|ostrava|bratislav", 120, 6)
        ctx(t, r"(?i)hotelId|hotel_id|\"id\":", 120, 6)

# ---------------------------------------------------------------- Itaka
def itaka():
    for base in ("https://www.itaka.cz", "https://www.itaka.sk", "https://itaka.sk"):
        robots(base)
    r = raw("https://www.itaka.cz/", n=1200)
    if r is not None and r.ok:
        p("   scripts:", scripts(r.text, "https://www.itaka.cz"))
        apis(r.text, "home")
        ctx(r.text, r"(?i)obchodn[ií] podm|podm[ií]nky|regulamin", 150, 6)
        ctx(r.text, r"__NEXT_DATA__|__NUXT__|window\.__", 150, 4)
        ctx(r.text, r"(?i)brno|ostrava|bratislav|v[ií]de[nň]|katovic", 120, 8)
    raw("https://www.itaka.sk/", n=800)
    h = raw("https://www.itaka.cz/dovolena/turecko/side/royal-alhambra-palace,AYTALHA.html", n=0)
    if h is not None and h.ok:
        t = h.text
        apis(t, "hotel")
        p("   scripts:", scripts(t, "https://www.itaka.cz"))
        ctx(t, r"__NEXT_DATA__|__NUXT__|window\.__|application/json", 200, 6)
        ctx(t, r"(?i)K[čc]|CZK|price|cena", 150, 8)
        ctx(t, r"(?i)brno|ostrava|bratislav|katovic|praha", 120, 8)

# ---------------------------------------------------------------- DERTOUR Brno id
def dertour():
    for home, path in (("https://www.kartago.sk", "/vysledky-vyhladavania"), ("https://www.fischer.sk", "/vysledky-vyhledavani")):
        r = raw(home + path, n=0)
        if r is None or not r.ok:
            continue
        ctx(r.text, r"(?i)brno|483|3789", 150, 8, label=home)
        for s in scripts(r.text, home):
            if not any(x in s for x in ("index", "app", "main", "search", "web")) or not s.startswith(home):
                continue
            try:
                js = get(s)
            except Exception as e:
                p("  js fail", s, e); continue
            p(f"   js {s} len={len(js)}")
            ctx(js, r"(?i)brno|3789|airport", 150, 8, label="js ")
            apis(js, "js")

# ---------------------------------------------------------------- Čedok BRQ
def cedok():
    from config import CONFIG
    from adapters import cedok as c
    for deps in ("BRQ", "BTS,VIE,BRQ", "BTS,VIE"):
        q = c._query(CONFIG, days=(8, 15))
        q["departuresByPlane"] = deps
        html = get(c.HOME + "/vysledky-vyhladavania/dovolenky/turecko/", params=q)
        rates, count, links = c.parse_page(html)
        offs = [o for o in (c.to_offer(r, links, CONFIG) for r in rates) if o]
        p(f"   cedok {deps}: {len(rates)}/{count} rates, deps {sorted({o['departure'] or '?' for o in offs})}")
        for r in rates[:3]:
            f = next((s for s in r.get('segments', []) if s.get('type') == 'flight'), {})
            p("      flight dep title:", (f.get("departure") or {}).get("title"))

# ---------------------------------------------------------------- Ruefa BRQ
def ruefa():
    from config import CONFIG
    from adapters import ruefa as rf
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": rf.IBE + "/index.php?page=results"}
    for ap in ("BRQ", "VIE-BTS-BRQ"):
        f = rf.form(CONFIG, rf.DEST_IDS["TR"], 7, 1)
        f["airport"] = ap
        d = get(rf.IBE + "/hub/ajax/deliver.php", method="POST", data=f, headers=hdr, as_json=True)
        offs = rf.parse(d, CONFIG)
        p(f"   ruefa {ap}: resultCount {d.get('resultCount')}, {len(offs)} cards, deps {sorted({o['departure'] or '?' for o in offs})}")
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(d.get("value") or "", "lxml")
        for c in soup.select("div.card-hotel")[:3]:
            p("      ", " ".join(c.select_one(".startDate").get_text(" ").split()) if c.select_one(".startDate") else "?", c.get("data-href", "")[:160])


from config import CONFIG
from adapters import cedok as C

IT = "https://www.itaka.cz"

def nd_queries(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd is None or not nd.string:
        return None
    return json.loads(nd.string)

def shape(o, depth=0, maxd=3):
    if depth > maxd: return "…"
    if isinstance(o, dict): return {k: shape(v, depth+1, maxd) for k, v in list(o.items())[:25]}
    if isinstance(o, list): return [shape(o[0], depth+1, maxd), f"len={len(o)}"] if o else []
    return o if not isinstance(o, str) else o[:60]

from collections import Counter

def C_query(deps, days=(8, 15), adults=2, kids=()):
    q = {"departuresByPlane": deps, "dateFrom": "01.07.2027", "dateTo": "31.08.2027",
         "durationMin": days[0], "durationMax": days[1], "order": "priceAsc", "participants[0][adults]": adults}
    for i, k in enumerate(kids):
        q[f"participants[0][children][{i}]"] = k
    return q

def summarize(html, label):
    d = nd_queries(html)
    rates, count, links = C.parse_page(html)
    qk = None
    if d:
        for qq in d["props"]["pageProps"].get("initialQueryState", {}).get("queries", []):
            if qq.get("queryKey", [None])[0] == "rates":
                qk = qq["queryKey"]
    types = Counter(r.get("rateType") for r in rates)
    deps = Counter((next((s for s in r.get('segments', []) if s.get('type') == 'flight'), {}).get("departure") or {}).get("title") for r in rates)
    p(f"   {label}: {len(rates)}/{count} types={dict(types)} deps={dict(deps)}")
    if qk: p("      qk:", json.dumps(qk, ensure_ascii=False)[:600])
    for r in rates[:4]:
        h = next((s for s in r.get('segments', []) if s.get('type') == 'hotel'), {})
        c = h.get("content") or {}
        p("      ", c.get("title"), r.get("price"), r.get("currency"), r.get("rateType"), h.get("beginDate"), h.get("endDate"), (r.get("duration") or {}).get("days"),
          [(x.get("type"), x.get("price")) for x in r.get("participants") or []], {g["type"]: g["title"] for g in c.get("geographicalIdentifiers", [])}, (h.get("meal") or {}).get("title"))
    return rates, links


def itaka5():
    from adapters import itaka
    p("fx:", __import__("common").eur_rate("CZK"))
    offs = itaka.search(CONFIG)
    p("itaka search offers:", len(offs))
    w = itaka.watch(CONFIG, CONFIG["watched"], {})
    p("itaka watch:", w)
    # which departures Itaka offers for Royal Alhambra (any airport), for the report
    html = get(itaka.HOME + itaka.HOTEL_PAGES[0][1], params=itaka._party(CONFIG))
    gv = itaka.parse_variants(html)
    p("AYTALHA groupedVariants (no airport filter):", json.dumps(gv, ensure_ascii=False)[:1500] if gv else gv)

section("ITAKA5", itaka5)
