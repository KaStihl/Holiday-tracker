"""Temporary diagnostics for new sources (deleted after use). Iteration 3."""
import json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
import requests
from common import UA, Robots

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "de-AT,de;q=0.9,en;q=0.7"})
ROB = {}

def robots(url, show=True):
    p = urlsplit(url); base = f"{p.scheme}://{p.netloc}"
    if base not in ROB:
        try:
            r = S.get(base + "/robots.txt", timeout=20); time.sleep(1)
            ok = r.ok and "<html" not in r.text[:300].lower()
            ROB[base] = Robots(r.text if ok else "", UA)
            print(f"  [robots {base} {r.status_code} html={not ok}]" + ("\n   | " + "\n   | ".join(
                l for l in r.text.splitlines() if l.strip() and not l.startswith('#'))[:2500] if ok and show else ""))
        except Exception as e:
            print(f"  [robots {base} {type(e).__name__}]"); ROB[base] = Robots("", UA)
    return ROB[base].can_fetch(url)

def fetch(url, show=True, **kw):
    if not robots(url, show):
        print(f"  ROBOTS-DISALLOWED {url}"); return None
    try:
        r = S.get(url, timeout=30, **kw)
    except Exception as e:
        print(f"  !! {url}: {type(e).__name__} {str(e)[:150]}"); return None
    time.sleep(1.5)
    print(f"  GET {r.status_code} {url[:300]} -> {r.url[:120]} len={len(r.text)} ct={r.headers.get('content-type')}")
    return r

def grep(text, pat, n=8, w=200, label=""):
    c = 0
    for m in re.finditer(pat, text, re.I | re.S):
        print(f"    {label}~ " + re.sub(r"\s+", " ", text[max(0, m.start() - w): m.end() + w]))
        c += 1
        if c >= n:
            break
    if not c:
        print(f"    {label}~ (no match for {pat[:60]})")

def plain(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)))

print("\n===== BILLA REISEN")
r = fetch("https://www.billareisen.at/Pauschalreisen/Europa-Mittelmeer/Tuerkei.html")
if r is not None:
    m = re.search(r'<form[^>]*id="ITS_thumbbarpanel".*?</form>', r.text, re.S)
    if m:
        print("    inputs:", sorted(set(re.findall(r'name="([^"]+)"', m.group(0))))[:80])
        grep(m.group(0), r"(Kind|Alter|child)", 6, 150, "kids")
    links = sorted(set(re.findall(r'href="(/Pauschalreisen/[^"]*\?[^"]*)"', r.text)))
    print("    search links:", [l.replace("&amp;", "&") for l in links[:6]])
u = ("https://www.billareisen.at/Pauschalreisen/Angebote.html?bdid=ib&toid=iba&ptid=BPS&na=1&nc=2&dpfebl=dd%2Cda"
     "&psdf=2027-07-01&pedf=2027-08-31&pnnfl=7&pnnfh=14&pna=1&pnc=2&ptf=1&ps=pr&pdm=pp&idvfmb=1")
r = fetch(u)
if r is not None:
    t = plain(r.text)
    grep(t, r"Angebote? gefunden|Treffer|Ergebnisse", 3, 150, "count")
    grep(r.text, r"ITS_price", 4, 600, "price")
    grep(r.text, r"data-[\w-]*(?:hotel|offer|price)[\w-]*=\"[^\"]{0,80}\"", 8, 50, "data")
    print("    ajax urls:", sorted(set(re.findall(r'["\'](/[\w/.-]*(?:ajax|Ajax|json|api)[\w/.-]*)', r.text)))[:30])

print("\n===== RUEFA")
r = fetch("https://pauschal.ruefa.at/js/searchParams.js?id=492")
if r is not None:
    print(r.text[:6700])
u = ("https://pauschal.ruefa.at/index.php?page=results&level=1&adults=1&children=10,12&start=2027-07-01&until=2027-08-31"
     "&anzZimmer=1&airport=VIE,BTS&dauer=7-14&verpflegung=AI+AIP+AIU+AIR&destination=T%C3%BCrkei")
r = fetch(u)
if r is not None:
    t = plain(r.text)
    grep(t, r"€|EUR", 6, 200, "price")
    print("    ajax/api:", sorted(set(re.findall(r'["\']((?:https?://[\w.-]+)?/[\w/.-]*(?:ajax|json|api|xhr)[\w/.?=&-]*)', r.text)))[:30])
r = fetch("https://www.ruefa.at/informationen/reisebedingungen", show=False)
if r is not None:
    grep(plain(r.text), r"automatisiert\w* (?:Abfrage|Zugriff|Auslesen)|scrap|data.?mining|crawl|Robot", 4, 250)
r = fetch("https://www.ruefa.at/ueber-uns/impressum", show=False)
if r is not None:
    grep(plain(r.text), r"Nutzung|Urheber|automatisiert|scrap|data.?mining|Vervielf", 4, 250)

print("\n===== HOFER")
r = fetch("https://www.hofer-reisen.at/at/destination/asien/tuerkei/antalya")
if r is not None:
    grep(r.text, r"p\.P\.|€\s*\d|\d+\s*€", 5, 200, "price")
    grep(r.text, r'self\.__next_f\.push', 2, 300, "rsc")
    print("    api refs:", sorted(set(re.findall(r'(/api/[\w/.-]+)', r.text)))[:30])
    grep(r.text, r'(?:Nutzungsbedingungen|AGB)[^<]{0,40}</a>', 3, 300, "terms")

print("\n===== LIDL")
for u in ["https://search-api-mvp2prod.lidl-reisen.de/graphql", "https://www.lidl-reisen.at/pauschalreisen"]:
    r = fetch(u)
    if r is not None:
        print("    ", r.text[:300].replace("\n", " "))
r = fetch("https://www.lidl-reisen.at/agb-reiseanbieter", show=False)
if r is not None:
    grep(plain(r.text), r"automatisiert|scrap|data.?mining|crawl|Robot|Nutzung der Website", 4, 250)

print("\n===== AIRSTOP")
r = fetch("https://airstop.sk/dovolenka/turecko")
if r is not None:
    grep(r.text, r"€|EUR", 5, 200, "price")
    grep(r.text, r'__NUXT_DATA__|__NUXT__', 2, 400, "nuxt")
    print("    api refs:", sorted(set(re.findall(r'(/api/[\w/.-]+)', r.text)))[:30])
    print("    links:", sorted(set(re.findall(r'href="(/[^"]*)"', r.text)))[:60])
r = fetch("https://airstop.sk/o-nas/obchodne-podmienky", show=False)
if r is not None:
    grep(plain(r.text), r"automat|robot|kopírov|rozmnož|databáz|obsah stránky|duševn", 6, 250)

print("\n===== GRUBER")
r = fetch("https://www.gruberreisen.at/robots.txt")
if r is not None:
    print(r.text[:1500])
r = fetch("https://buchung.gruberreisen.at/")
if r is not None:
    print("    title:", re.findall(r"<title>(.*?)</title>", r.text, re.S)[:1])
    print("    hosts:", sorted({urlsplit(h).netloc for h in re.findall(r'(?:href|src)="(https?://[^"]+)"', r.text)})[:20])
    print("    ", re.sub(r"\s+", " ", r.text[:1500]))

print("\n===== RESTPLATZBOERSE")
r = S.get("https://www.restplatzboerse.at/robots.txt", timeout=20); print(r.text[-1500:])
print("\n===== URLAUBSGURU / NECKERMANN")
for u in ["https://buchen.urlaubsguru.at/", "https://www.urlaubsguru.at/agb/", "https://www.urlaubsguru.at/nutzungsbedingungen/",
          "https://pauschal.neckermann-reisen.de/"]:
    r = fetch(u)
    if r is not None:
        grep(plain(r.text), r"automatisiert|scrap|data.?mining|crawl|Robot|Wien|\bVIE\b", 5, 200)
