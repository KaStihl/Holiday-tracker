"""TEMPORARY probe of hydrotour.sk – prints to the job log only, deleted after use. Iteration 7."""
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
    print(f"\n### {method} {r.url} {json.dumps(body)[:300] if body else ''} -> {r.status_code} len={len(r.text)}")
    return r


r = fetch(H + "/assets/SearchResults-Dk8V_xZG.js")
j = r.text
m = re.search(r"\bOe as\b|as Oe\b", j)
print("imports:", j[:1200])
idx = fetch(H + "/assets/index-DIcXCF-s.js").text
# the transform the search page applies before searchTerminyRaw
for name in ("ax", "aw", "av", "au"):
    mm = re.search(r"\b(\w+) as " + name + r"\b", idx)
    if mm:
        k = idx.find(f"{mm[1]}=")
        while k != -1 and idx[k - 1].isalnum():
            k = idx.find(f"{mm[1]}=", k + 1)
        print(f"EXPORT {name} = {mm[1]}:", idx[k:k + 900] if k != -1 else None)

base = {"hotely": [], "staty": [9], "oblasti": [1021], "dni": [], "datumOd": "2027-07-01", "datumDo": "2027-08-31",
        "letiska": [], "strava": [], "hviezdy": [], "ostatne": []}
tries = [
    ("raw-min-staty", "searchTerminyRaw", {"staty": [9]}),
    ("raw-side-2ad", "searchTerminyRaw", dict(base, cestujuci=[[18, 18]])),
    ("raw-side-1+2", "searchTerminyRaw", dict(base, cestujuci=[[18, 10, 12]])),
    ("raw-side-1+2-strings", "searchTerminyRaw", dict(base, staty=None, oblasti=None, cestujuci=[[18, 10, 12]])),
]
for label, fn, body in tries:
    r = fetch(f"{H}/japi/ISearchApi/{fn}", "POST", [body])
    try:
        d = r.json()
    except ValueError:
        print(label, "NOT JSON", r.text[:800])
        continue
    hs, ts = d.get("hotely") or [], d.get("terminy") or []
    print(label, "hotely", len(hs), "terminy", len(ts), "vynechane", d.get("vynechaneFiltre"),
          "dates", sorted({t.get("datumOd", "")[:7] for t in ts})[:12])
    if ts and label.startswith("raw-side-1+2"):
        print("HOTEL0:", json.dumps(hs[0], ensure_ascii=False)[:3000])
        print("TERM0:", json.dumps(ts[0], ensure_ascii=False)[:3000])
        alh = [h for h in hs if re.search("alhambra|dragon|sural", h.get("nazov", ""), re.I)]
        print("WATCHED:", [(h.get("nazov"), h.get("hotelId")) for h in alh])
        for h in alh[:2]:
            print("W-TERMS:", json.dumps([t for t in ts if t.get("hotelId") == h["hotelId"]][:3], ensure_ascii=False)[:3000])
