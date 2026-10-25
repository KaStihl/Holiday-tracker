"""TEMPORARY: Koala tree.json (the SPA's catalogue file). Every fetch goes through common.get (robots enforced)."""
import re
import sys

sys.path.insert(0, "scraper")
import common  # noqa: E402
from common import RobotsDisallowed, get  # noqa: E402

try:
    print("REDRED robots.txt:", repr(get("https://koala.redred.sk/robots.txt", retries=0)[:1500]))
except Exception as e:
    print("REDRED robots.txt ERR", repr(e)[:200])
TREE = "https://koala.redred.sk/json/encoded/tree.json"
print("allowed tree", common.allowed(TREE))

js = get("https://koala.sk/index.js")
for pat in [r"decode_json", r"this\.dayCount", r"/dovolenka/\$\{", r"tree\.json", r"searchHotels\(e=\{\}"]:
    hits = [m.start() for m in re.finditer(pat, js)]
    print(f"=== /{pat}/ {len(hits)}")
    for i in hits[:3]:
        print("   >>", js[max(0, i - 700): i + 900].replace("\n", " "))

try:
    t = get(TREE, retries=0)
    print("TREE len", len(t), repr(t[:600]))
    print("TREE tail", repr(t[-300:]))
except RobotsDisallowed:
    print("TREE disallowed by robots")
except Exception as e:
    print("TREE ERR", repr(e)[:200])
