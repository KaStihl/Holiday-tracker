"""TEMPORARY probe of hydrotour.sk – prints to the job log only, deleted after use. Iteration 2."""
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from bs4 import BeautifulSoup  # noqa: E402
from common import allowed, session  # noqa: E402

H = "https://www.hydrotour.sk"


def fetch(url, **kw):
    if not allowed(url):
        print(f"\n### {url}: ROBOTS DISALLOWS")
        return None
    r = session().get(url, timeout=30, **kw)
    print(f"\n### {r.url} -> {r.status_code} len={len(r.text)} ct={r.headers.get('content-type')}")
    return r


def grep(t, rx, ctx=150, n=12):
    for m in list(re.finditer(rx, t, re.I))[:n]:
        print("  ~", re.sub(r"\s+", " ", t[max(0, m.start() - ctx): m.end() + ctx]))


def clean(el, n=2500):
    for x in el.select("svg,path"):
        x.decompose()
    return re.sub(r"\s+", " ", str(el))[:n]


r = fetch(H + "/vseobecne-podmienky")
soup = BeautifulSoup(r.text, "lxml")
body = soup.get_text(" ", strip=True)
grep(body, r"autorsk|obsah (webov|stránk)|internetov\w+ stránk|webov\w+ stránk|databáz|kopír|rozmnož", 200, 10)

r = fetch(H + "/dovolenky/turecko/side")
t = r.text
soup = BeautifulSoup(t, "lxml")
cards = soup.select(".card-hotel")
print("cards:", len(cards))
for c in cards[:2]:
    print("CARD:", clean(c, 3500))
inl = [s.string or "" for s in soup.select("script:not([src])")]
print("inline scripts:", [len(x) for x in inl])
for x in inl:
    if len(x) > 2000:
        print("INLINE START:", x[:1500].replace("\n", " "))
        grep(x, r"price|cena|termin|alhambra", 200, 8)
grep(t, r"alhambra", 200, 5)
grep(t, r"str[aá]nk|page=|dal[sš]ie|zobrazi[tť] viac|load", 120, 8)
print("pager/links:", sorted({a['href'] for a in soup.select('a[href]') if '?' in a['href'] or '#' in a['href']})[:60])

js = re.search(r'/assets/index-[\w-]+\.js', t)
if js:
    r = fetch(H + js[0])
    j = r.text
    print("api paths:", sorted(set(re.findall(r'["\'`](/api/[\w/${}.:-]*)', j)))[:120])
    print("other abs paths:", sorted(set(re.findall(r'["\'`](/(?:dovolenky|hotel|vyhlad|search|termin)[\w/${}.:-]*)', j)))[:60])
    grep(j, r"/api/", 120, 25)
    grep(j, r"cestujuci|vekDeti|deti|children|dospel|adults", 100, 15)

r = fetch(H + "/sitemap.xml")
if r is not None:
    print(r.text[:1500])
    grep(r.text, r"alhambra|royal|sural|dragon", 120, 10)
