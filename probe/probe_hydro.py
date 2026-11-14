"""TEMPORARY probe of hydrotour.sk – prints to the job log only, deleted after use. Iteration 5."""
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
    for m in list(re.finditer(rx, t))[:n]:
        print("  ~", re.sub(r"\s+", " ", t[max(0, m.start() - ctx): m.end() + ctx]))


idx = fetch(H + "/assets/index-DIcXCF-s.js").text
grep(idx, r"fetch\(", 400, 10)
grep(idx, r"Vv=\(e,t\)=>", 50, 1)
m = idx.find("Vv=(e,t)=>")
print("VV:", idx[m:m + 2500])
grep(idx, r"location\.hash|createWebHistory|createWebHashHistory|router\.(push|replace)", 200, 8)
grep(idx, r"\bbh as\b|as bh\b", 300, 3)
grep(idx, r"hdtSearch|vyhladaj|searchTerm|terminy\b", 200, 10)

r = fetch(H + "/dovolenky/turecko/side")
s = BeautifulSoup(r.text, "lxml")
for sc in s.select("script:not([src])"):
    x = sc.string or ""
    print("INLINE", len(x), sc.attrs, x[:300].replace("\n", " "))
