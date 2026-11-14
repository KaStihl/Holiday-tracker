"""TEMPORARY probe of hydrotour.sk – prints to the job log only, deleted after use. Iteration 6."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from common import allowed, session  # noqa: E402

H = "https://www.hydrotour.sk"


def fetch(url, method="GET", body=None):
    if not allowed(url):
        print(f"\n### {url}: ROBOTS DISALLOWS")
        return None
    r = session().request(method, url, json=body, timeout=40,
                          headers={"Content-Type": "application/json"} if body is not None else None)
    print(f"\n### {method} {r.url} -> {r.status_code} len={len(r.text)} ct={r.headers.get('content-type')}")
    return r


def grep(t, rx, ctx=150, n=12):
    for m in list(re.finditer(rx, t))[:n]:
        print("  ~", re.sub(r"\s+", " ", t[max(0, m.start() - ctx): m.end() + ctx]))


def shape(x, d=0, maxd=3):
    if isinstance(x, dict):
        return {k: shape(v, d + 1, maxd) if d < maxd else type(v).__name__ for k, v in list(x.items())[:60]}
    if isinstance(x, list):
        return [f"len={len(x)}", shape(x[0], d + 1, maxd)] if x else []
    return x if not isinstance(x, str) else x[:60]


idx = fetch(H + "/assets/index-DIcXCF-s.js").text
grep(idx, r"searchTerminy(Raw)?\(", 700, 6)
for mod in ("SearchResults-Dk8V_xZG", "HotelDetail-CNmdGM0T"):
    r = fetch(f"{H}/assets/{mod}.js")
    if r is not None and r.ok:
        grep(r.text, r"searchTerminy|hotelDetail\(|hotelKarta\(|\.bl\(|Fc\.", 600, 6)

r = fetch(H + "/sapi/hotel-detail/215")
if r is not None and r.ok:
    try:
        d = r.json()
        print(json.dumps(shape(d, maxd=2), ensure_ascii=False)[:5000])
        for k in ("terminy", "terms"):
            if isinstance(d, dict) and d.get(k):
                print("TERM0:", json.dumps(d[k][0], ensure_ascii=False)[:3000])
    except ValueError:
        print(r.text[:1500])

f = {"hotely": [], "staty": [9], "oblasti": [1021], "dni": [], "datumOd": "2027-07-01", "datumDo": "2027-08-31",
     "cestujuci": [[18, 10, 12]], "letiska": [], "strava": [], "hviezdy": [], "ostatne": []}
r = fetch(H + "/japi/ISearchApi/searchTerminy", "POST", [f])
if r is not None:
    try:
        d = r.json()
        print(json.dumps(shape(d, maxd=3), ensure_ascii=False)[:5000])
    except ValueError:
        print(r.text[:2000])
