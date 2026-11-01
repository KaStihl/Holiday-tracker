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

def itaka2():
    home = get(IT + "/")
    m = re.search(r'departureCities\\":\{\\"airports\\":(\[.*?\])', home)
    if m:
        p("   airports:", m[1].replace('\\"', '"')[:3000])
    links = sorted(set(re.findall(r'href="(/[^"]*(?:vysledky|departuresByPlane|dovolena/)[^"]*)"', home)))
    p("   links:", links[:60])
    for path in ("/terms", "/pravidla-a-podminky", "/regulamin/", "/dohoda"):
        try:
            t = get(IT + path)
        except Exception as e:
            p(f"   {path}: {e}"); continue
        txt = re.sub(r"<[^>]+>", " ", t)
        p(f"   {path}: len {len(t)}")
        ctx(txt, r"(?i)vytěž|vytez|výhrad|robot|automati|crawl|scrap|data mining|tdm|strojov|kopírov|stahov", 220, 10)

def itaka_results():
    for path in ("/vysledky-vyhledavani/dovolena/turecko/", "/vysledky-vyhledavani/dovolena/"):
        q = {"departuresByPlane": "BTS,VIE,BRQ,PRG,OSR,KTW", "dateFrom": "01.07.2027", "dateTo": "31.08.2027",
             "durationMin": 8, "durationMax": 15, "order": "priceAsc", "participants[0][adults]": 2}
        try:
            html = get(IT + path, params=q)
        except Exception as e:
            p(f"   {path}: {e}"); continue
        d = nd_queries(html)
        p(f"   {path}: len {len(html)} nextdata={d is not None}")
        if d:
            pp = d["props"]["pageProps"]
            p("   pageProps keys:", list(pp))
            for qq in pp.get("initialQueryState", {}).get("queries", []):
                p("    query key:", json.dumps(qq.get("queryKey"))[:300])
            rates, count, links = C.parse_page(html)
            p(f"   rates {len(rates)}/{count}, links {len(links)}")
            if rates:
                p("   rate0:", json.dumps(shape(rates[0], maxd=4), ensure_ascii=False)[:5000])
                for r in rates[:25]:
                    f = next((s for s in r.get('segments', []) if s.get('type') == 'flight'), {})
                    h = next((s for s in r.get('segments', []) if s.get('type') == 'hotel'), {})
                    p("     ", (h.get("content") or {}).get("title"), r.get("price"), r.get("currency"), (f.get("departure") or {}).get("title"), h.get("beginDate"), (r.get("duration") or {}).get("days"), len(r.get("participants") or []))
                p("   links sample:", list(links.items())[:3])
            ctx(html, r"(?i)K[čc]\b|CZK", 100, 3)
            break

def itaka_hotel():
    q = {"departuresByPlane": "BTS,VIE,BRQ", "dateFrom": "01.07.2027", "dateTo": "31.08.2027",
         "durationMin": 8, "durationMax": 15, "participants[0][adults]": 1,
         "participants[0][children][0]": "01.07.2017", "participants[0][children][1]": "01.07.2015"}
    html = get(IT + "/dovolena/turecko/side/royal-alhambra-palace,AYTALHA/", params=q)
    d = nd_queries(html)
    p(f"   hotel len {len(html)} nextdata={d is not None}")
    v = C.parse_detail(html)
    p("   rsc variants:", v[:5])
    if d:
        pp = d["props"]["pageProps"]
        p("   pageProps keys:", list(pp))
        for qq in pp.get("initialQueryState", {}).get("queries", []):
            p("    query key:", json.dumps(qq.get("queryKey"))[:400])
            p("    data shape:", json.dumps(shape(qq.get("state", {}).get("data"), maxd=5), ensure_ascii=False)[:3000])
    ctx(html, r'"totalPrice"|"adultNumber"|childrenBirthDates', 300, 4)
    ctx(html, r"(?i)brno|bratislav|v[ií]de[nň]", 150, 6)

def coral2():
    for u in ("https://www.coraltravel.cz/sitemap.xml", "https://coraltravel.cz/", "https://www.coraltravel.cz/obchodni-podminky/"):
        r = raw(u, n=0)
        if r is not None:
            p("    title:", re.findall(r"<title>([^<]*)", r.text)[:2], "imperva/reese:", "reese84" in r.text or "Pardon Our Interruption" in r.text)

def dertour2():
    home = "https://www.kartago.sk"
    html = get(home + "/vysledky-vyhladavania")
    ss = re.findall(r'<script[^>]+src="([^"]+)"', html)
    p("   scripts:", ss)
    for s in ss:
        if not ("Scripts" in s or "/scripts/" in s.lower()):
            continue
        url = s if s.startswith("http") else home + ("" if s.startswith("/") else "/") + s
        try:
            js = get(url)
        except Exception as e:
            p("  js fail", url, e); continue
        p(f"   js {url} len={len(js)}")
        ctx(js, r"(?i)brno|fromId|airportId|departureAirport|/api/[a-z]+/[a-z]+", 160, 15, label="js ")
    ctx(html, r"(?i)letisk|airport|odlet", 160, 10)

section("ITAKA2", itaka2)
section("ITAKA RESULTS", itaka_results)
section("ITAKA HOTEL", itaka_hotel)
section("CORAL2", coral2)
section("DERTOUR2", dertour2)
