"""Temporary diagnostics for new sources (deleted after use). Iteration 2."""
import re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
import requests
from common import UA, Robots

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "de-AT,de;q=0.9,en;q=0.7"})
ROB = {}

def robots(url):
    p = urlsplit(url); base = f"{p.scheme}://{p.netloc}"
    if base not in ROB:
        try:
            r = S.get(base + "/robots.txt", timeout=20); time.sleep(1)
            ROB[base] = Robots(r.text if r.ok else "", UA)
            print(f"  [robots {base} {r.status_code}]" + ("\n   | " + "\n   | ".join(
                l for l in r.text.splitlines() if l.strip() and not l.startswith('#'))[:3000] if r.ok else ""))
        except Exception as e:
            print(f"  [robots {base} {type(e).__name__}]"); ROB[base] = Robots("", UA)
    return ROB[base].can_fetch(url)

def fetch(url, **kw):
    ok = robots(url)
    if not ok:
        print(f"  ROBOTS-DISALLOWED {url}"); return None
    try:
        r = S.get(url, timeout=25, **kw)
    except Exception as e:
        print(f"  !! {url}: {type(e).__name__} {str(e)[:150]}"); return None
    time.sleep(1.5)
    print(f"  GET {r.status_code} {url} -> {r.url} len={len(r.text)} ct={r.headers.get('content-type')} server={r.headers.get('server')}")
    return r

def grep(text, pat, n=8, w=200, label=""):
    c = 0
    for m in re.finditer(pat, text, re.I | re.S):
        print(f"    {label}~ " + re.sub(r"\s+", " ", text[max(0, m.start() - w): m.end() + w]))
        c += 1
        if c >= n:
            break

def plain(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)))

def scripts(r, n=6, pat=r"/api/[\w/.-]+|https?://[\w.-]+/[\w/.-]*(?:api|search|graph)[\w/.-]*"):
    srcs = [urljoin(r.url, s) for s in re.findall(r'<script[^>]+src="([^"]+)"', r.text)]
    print("  scripts:", srcs[:30])
    found = set(re.findall(pat, r.text))
    for s in [s for s in srcs if urlsplit(s).netloc == urlsplit(r.url).netloc][:n]:
        j = fetch(s)
        if j is not None:
            found |= set(re.findall(pat, j.text))
    print("  endpoints:", sorted(found)[:80])

def head(r, n=1500):
    print("    BODY:", re.sub(r"\s+", " ", r.text[:n]))

print("\n===== BILLA REISEN")
r = fetch("https://www.billareisen.at/Startseite.html")
if r is not None:
    links = sorted(set(re.findall(r'href="(/[^"]*(?:[Pp]auschal|[Ss]uche|[Tt]uerkei|search|angebote)[^"]*)"', r.text)))
    print("  links:", links[:40])
    grep(r.text, r"<form[^>]*>", 5, 50, "form")
    scripts(r)
for u in ["https://www.billareisen.at/Pauschalreisen.html", "https://www.billareisen.at/Tuerkei.html"]:
    p = fetch(u)
    if p is not None:
        grep(p.text, r"(€|EUR)\s*\d|\d[\d.]*,-|preis", 5, 150, "price")

print("\n===== RUEFA")
r = fetch("https://pauschal.ruefa.at/")
if r is not None:
    head(r, 800); scripts(r)
r = fetch("https://www.ruefa.at/")
if r is not None:
    links = sorted(set(re.findall(r'href="(https?://pauschal\.ruefa\.at[^"]*)"', r.text)))
    print("  pauschal links:", links[:20])
p = fetch("https://www.ruefa.at/informationen/nutzungsbedingungen")
if p is not None:
    grep(plain(p.text), r"automatisiert|scrap|robot|data.?mining|crawl", 5, 250)

print("\n===== HOFER")
r = fetch("https://www.hofer-reisen.at/at")
if r is not None:
    links = sorted(set(re.findall(r'href="(/at/[^"]*(?:pauschal|suche|search|tuerkei|angebot)[^"]*)"', r.text, re.I)))
    print("  links:", links[:40])
    grep(r.text, r"__NEXT_DATA__|__NUXT__|window\.__\w+", 4, 120, "ssr")
    scripts(r, 3)
for u in ["https://www.hofer-reisen.at/at/service/agb", "https://www.hofer-reisen.at/at/service/nutzungsbedingungen"]:
    p = fetch(u)
    if p is not None:
        grep(plain(p.text), r"automatisiert|scrap|robot|data.?mining|crawl", 5, 250)

print("\n===== LIDL AT")
for u in ["https://www.lidl-reisen.at/nutzungsbedingungen", "https://www.lidl-reisen.at/agb-reiseanbieter"]:
    p = fetch(u)
    if p is not None:
        grep(plain(p.text), r"automatisiert|scrap|robot|data.?mining|crawl|Vervielfältig", 5, 250)
r = fetch("https://www.lidl-reisen.at/")
if r is not None:
    links = sorted(set(re.findall(r'href="(/[^"]*(?:pauschal|suche|search)[^"]*)"', r.text, re.I)))
    print("  links:", links[:30])
    grep(r.text, r"/api/graph/lidl", 3, 200, "graph")

print("\n===== AIRSTOP")
r = fetch("https://airstop.sk/")
if r is not None:
    links = sorted(set(re.findall(r'href="(/[^"]*)"', r.text)))
    print("  links:", [l for l in links if any(k in l for k in ("dovolen", "zajazd", "pobyt", "turecko", "last", "first", "balik", "package"))][:40])
    scripts(r, 6, r"/api/vue/[\w/.-]+|/api/[\w/.-]+")
p = fetch("https://airstop.sk/o-nas/obchodne-podmienky")
if p is not None:
    grep(plain(p.text), r"automat|kopírov|robot|scrap|data mining|vyťaž|databáz", 6, 250)
for u in ["https://airstop.sk/api/vue/offer-packages", "https://airstop.sk/api/vue/page?url=/dovolenka"]:
    p = fetch(u)
    if p is not None:
        head(p, 1200)

print("\n===== RESTPLATZBOERSE")
p = fetch("https://www.restplatzboerse.at/pauschalreisen")
p = fetch("https://www.restplatzboerse.at/agb")
if p is not None:
    grep(plain(p.text), r"automatisiert|scrap|robot|data.?mining|crawl", 5, 250)

print("\n===== NECKERMANN DE")
r = fetch("https://www.neckermann-reisen.de/")
if r is not None:
    grep(r.text, r"ibeAdvanced\w*BaseUrl[^,]{0,200}", 4, 20, "ibe")
    grep(r.text, r"Wien|VIE\b|Österreich", 5, 100, "vie")
p = fetch("https://www.neckermann-reisen.de/agb/")
if p is not None:
    grep(plain(p.text), r"automatisiert|scrap|robot|data.?mining|crawl", 5, 250)

print("\n===== GRUBER / URLAUBSGURU / ANEX AT")
for u in ["https://gruber-reisen.at/", "https://www.gruberreisen.at/", "https://www.gruber-touristik.at/",
          "https://www.anextour.at/", "https://www.urlaubsguru.at/pauschalreisen/"]:
    r = fetch(u)
    if r is not None:
        print("    title:", re.findall(r"<title>(.*?)</title>", r.text, re.S)[:1])
        hosts = sorted({urlsplit(h).netloc for h in re.findall(r'(?:href|src)="(https?://[^"]+)"', r.text)})
        print("    hosts:", hosts[:30])
