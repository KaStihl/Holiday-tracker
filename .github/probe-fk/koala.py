"""TEMPORARY: find Koala SPA data endpoints in index.js / constants.js. Uses common.get (robots enforced)."""
import re, sys
sys.path.insert(0, "scraper")
import common
from common import get

for name in ("constants.js", "index.js"):
    js = get("https://koala.sk/" + name)
    print(f"===== {name} len={len(js)}")
    pats = [r"fetch\(", r"axios", r"XMLHttpRequest", r"/api/", r"graphql", r"\.json", r"\.ashx", r"search", r"baseUrl|apiUrl|API_URL|endpoint",
            r"https?://[a-z0-9.-]+"]
    for p in pats:
        hits = [m.start() for m in re.finditer(p, js)]
        print(f"--- /{p}/ hits={len(hits)}")
        seen = set()
        for i in hits[:400]:
            ctx = js[max(0, i - 90): i + 110].replace("\n", " ")
            key = ctx[60:150]
            if key in seen: continue
            seen.add(key)
            if len(seen) > 12: break
            print("   ", ctx)
    urls = sorted(set(re.findall(r"https?://[a-z0-9.-]+[^\s\"'`)]{0,80}", js)))
    print("ABS URLS", urls[:80])
    strs = sorted(set(re.findall(r"[\"'`](/[A-Za-z][A-Za-z0-9_./{}$-]{2,80})[\"'`?]", js)))
    print("PATH STRINGS", len(strs)); print("\n".join(strs[:300]))
