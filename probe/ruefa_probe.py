"""Temporary probe (deleted after use): run ruefa.watch() for real and print trimmed answers for test fixtures."""
import json, sys
sys.path.insert(0, "scraper")
from bs4 import BeautifulSoup
import common
from config import CONFIG
from adapters import ruefa

orig = common.get
seen = []

def spy(url, **kw):
    r = orig(url, **kw)
    seen.append((url, kw.get("params"), kw.get("data"), r))
    return r

ruefa.get = spy
offers = ruefa.watch(CONFIG, ["Sural", "Royal Alhambra"], {})
print("=== offers", len(offers))
for o in offers:
    print("   ", json.dumps(o, ensure_ascii=False))
for url, params, data, r in seen:
    if "getDestination" in url:
        print("=== FIXTURE autocomplete", params, json.dumps(r, ensure_ascii=False))
# one deliver answer (Sural + Alhambra ids, 7 nights, 1st window), trimmed: keep only the card divs
url, params, data, r = next(x for x in seen if "deliver" in x[0])
soup = BeautifulSoup(r.get("value") or "", "lxml")
cards = soup.select("div.card-hotel[data-href]")
print("=== FIXTURE deliver form", json.dumps(data, ensure_ascii=False))
print("=== FIXTURE deliver", json.dumps({"resultCount": r.get("resultCount"), "level": r.get("level"), "gids": r.get("gids"),
      "value": "".join(str(c) for c in cards)}, ensure_ascii=False))
