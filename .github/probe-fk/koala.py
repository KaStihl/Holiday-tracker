"""TEMPORARY: decode Koala tree.json with the adapter, print terms + a trimmed encoded fixture.
Every fetch goes through common.get (robots enforced)."""
import collections
import json
import re
import sys

sys.path.insert(0, "scraper")
from adapters import koala  # noqa: E402
from common import get  # noqa: E402
from config import CONFIG  # noqa: E402

text = get(koala.TREE_URL, retries=0)
raw = json.loads(text)
print("meta", {k: raw[k] for k in raw if k != "encoded"})
dests = koala.decode_tree(raw["encoded"])
hotels = list(koala.iter_hotels(dests))
print("hotels", len(hotels), "categories", collections.Counter(h.get("category") for h, _, _ in hotels))
seen_keys = collections.Counter()
for h, names, top in hotels:
    for t in h.get("terms") or []:
        seen_keys.update(t.keys())
        print("TERM", top, "/", h.get("url"), names, json.dumps(t, ensure_ascii=False))
print("term keys", seen_keys)
offers = koala.offers_from_tree(dests, CONFIG)
print("offers", len(offers))
for o in offers[:10]:
    print("OFFER", json.dumps(o, ensure_ascii=False))


def trim(enc_dests):
    """keep destinations that (transitively) contain hotels with terms; hotels w/o terms dropped except 1"""
    out = []
    for d in enc_dests:
        sub = trim(d.get("h") or [])
        hs = [dict(h, F=h["F"][:3]) for h in d.get("l") or [] if h.get("F")]
        if sub or hs:
            out.append(dict(d, h=sub, l=hs))
    return out


fx = {"createdAt": raw.get("createdAt"), "encoded": trim(raw["encoded"])}
# plus one destination without terms (shape of an off-season entry)
fx["encoded"].append(dict(raw["encoded"][0], h=[], l=(raw["encoded"][0].get("l") or [])[:1]))
s = json.dumps(fx, ensure_ascii=False, separators=(",", ":"))
print("FIXTURE len", len(s))
print("FIXTURE|" + s)

js = get("https://koala.sk/index.js")
for pat in [r"za osobu", r"osob", r"\.price\b", r"transportationFrom\b"]:
    hits = [m.start() for m in re.finditer(pat, js)]
    print(f"=== /{pat}/ {len(hits)}")
    for i in hits[:5]:
        print("   >>", js[max(0, i - 300): i + 300].replace("\n", " "))
