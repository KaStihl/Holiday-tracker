"""TEMPORARY probe of hydrotour.sk – prints to the job log only, deleted after use. Iteration 3."""
import re
import sys
from pathlib import Path

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
    for x in el.select("svg,path,img"):
        x.decompose()
    return re.sub(r"\s+", " ", str(el))[:n]


r = fetch(H + "/dovolenky/turecko/side")
soup = BeautifulSoup(r.text, "lxml")
c = soup.select_one(".card-hotel .next-terms")
print("NEXT-TERMS:", clean(c, 3000))
mods = re.findall(r'/assets/[\w-]+\.js', r.text)
print("modules:", mods)

r = fetch(H + "/dovolenky/turecko/side/royal-alhambra-palace")
t = r.text
soup = BeautifulSoup(t, "lxml")
print("title:", soup.title.get_text(strip=True) if soup.title else None)
print("term ids:", len(set(re.findall(r'#(\d{6})', t))), "classes with term:", sorted({c for el in soup.select('[class]') for c in el['class'] if 'term' in c.lower()})[:40])
for sel in (".term", ".terms", ".term-row", "table", ".hotel-terms"):
    els = soup.select(sel)
    if els:
        print(sel, len(els), "FIRST:", clean(els[0], 2500))
inl = [s.string or "" for s in soup.select("script:not([src])")]
print("inline scripts:", [len(x) for x in inl])
for x in inl:
    if '"@type"' in x[:200]:
        print("LD:", x[:1500])
grep(t, r"€", 200, 6)
grep(t, r"term[ií]n", 150, 6)

seen = set()
for m in mods:
    if any(k in m for k in ("SearchResults", "IWebKatalog", "CardHotel", "HotelDetail", "Termin", "Term", "Search")) and m not in seen:
        seen.add(m)
        r = fetch(H + m)
        j = r.text
        print("strings with / :", sorted(set(s for s in re.findall(r'["\'`]([^"\'`\s]{2,120})["\'`]', j) if "/" in s and not s.startswith("./")))[:120])
        grep(j, r"fetch\(|axios|XMLHttpRequest|\.get\(|baseURL|endpoint|\bapi\b", 150, 20)
