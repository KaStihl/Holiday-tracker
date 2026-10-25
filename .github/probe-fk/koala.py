"""TEMPORARY: Koala allowed routes. Uses common.get (robots enforced)."""
import re, sys
sys.path.insert(0, "scraper")
import common
from common import get, RobotsDisallowed

def show(url, n=3000):
    try:
        t = get(url)
    except RobotsDisallowed:
        print("ROBOTS-DISALLOWED", url); return ""
    except Exception as e:
        print("ERR", url, repr(e)[:300]); return ""
    print(f"----- {url} len={len(t)}"); print(t[:n]); return t

rob = show("https://koala.sk/robots.txt", 6000)
sm = [l.split(":", 1)[1].strip() for l in rob.splitlines() if l.lower().startswith("sitemap")]
print("SITEMAPS", sm)
for u in (sm or ["https://koala.sk/sitemap.xml"])[:3]:
    t = show(u, 2500)
    locs = re.findall(r"<loc>([^<]+)</loc>", t)
    print("NLOCS", len(locs))
    for l in locs[:60]: print("  ", l, common.allowed(l))
home = show("https://koala.sk/", 1500)
print("HOME script srcs", re.findall(r'src="([^"]+)"', home)[:30])
print("HOME hrefs", re.findall(r'href="([^"]+)"', home)[:60])
print("HOME json-ish", re.findall(r'["\']([^"\']*\.(?:json|php)[^"\']*)["\']', home)[:30])
for u in ["https://koala.sk/search.json", "https://koala.sk/zajazdy/", "https://koala.sk/rss", "https://koala.sk/feed"]:
    print("ALLOWED?", u, common.allowed(u))
