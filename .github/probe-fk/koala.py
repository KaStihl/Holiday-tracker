"""TEMPORARY: Koala tree.json dictionary + a compressed copy of the file (for a trimmed test fixture).
Every fetch goes through common.get (robots enforced; koala.redred.sk/robots.txt is 404)."""
import base64
import gzip
import re
import sys

sys.path.insert(0, "scraper")
from common import get  # noqa: E402

js = get("https://koala.sk/index.js")
for mod in ("1220:", "4869:", "5946:", "4995:", "3311:"):
    i = js.find("}," + mod)
    print(f"=== module {mod} at {i}")
    if i >= 0:
        print(js[i + 2: i + 2 + 3500])
t = get("https://koala.redred.sk/json/encoded/tree.json", retries=0)
blob = base64.b64encode(gzip.compress(t.encode("utf-8"))).decode()
print("TREE b64gz len", len(blob))
for k in range(0, len(blob), 3000):
    print("B64|" + blob[k:k + 3000])
print("F nonempty count", len(re.findall(r'"F":\[\{', t)))
