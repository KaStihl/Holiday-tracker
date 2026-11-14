"""TEMPORARY probe of hydrotour.sk – prints to the job log only, deleted after use. Iteration 4."""
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


print(fetch(H + "/assets/IWebKatalog-D2wfQnmo.js").text)
print(fetch(H + "/assets/searchResultsUtils-CPkTUGK9.js").text[:6000])
j = fetch(H + "/assets/SearchResults-Dk8V_xZG.js").text
print(j[:14700])
idx = fetch(H + "/assets/index-DIcXCF-s.js").text
grep(idx, r"katalog|baseURL|https?://[\w.-]+hydrotour[\w./-]*|/api|\.hydrotour", 200, 30)
grep(idx, r"query\.\w+|URLSearchParams|terminOd|datumOd|odlet|letiska|cestujuci|deti|vek", 120, 30)


def cards(url):
    r = fetch(url)
    if r is None:
        return
    s = BeautifulSoup(r.text, "lxml")
    cs = s.select(".card-hotel")
    names = [c.select_one(".hotel-name a").get_text(" ", strip=True)[:30] for c in cs if c.select_one(".hotel-name a")]
    terms = [t.get_text(" ", strip=True)[:40] for t in s.select(".next-term-timespan")][:6]
    print("cards", len(cs), names[:8], "terms", terms, "pager", [a.get('href') for a in s.select('a[href*="strana"], a[href*="page"], .pagination a')][:8])


cards(H + "/dovolenky?staty=9&oblasti=1021")
cards(H + "/dovolenky/turecko")
cards(H + "/dovolenky/turecko?strana=2")
cards(H + "/vyhladavanie")
