"""TEMPORARY probe of hydrotour.sk / hydrotour.cz – prints to the job log only, deleted after use."""
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from bs4 import BeautifulSoup  # noqa: E402
from common import allowed, session  # noqa: E402

BLOCK = re.compile(r"cf-chl|challenge-platform|Just a moment|Pardon Our Interruption|captcha|reese84|_Incapsula|datadome|perimeterx", re.I)


def fetch(url, n=0, grep=None, ctx=160, show_robots=False, **kw):
    try:
        ok = allowed(url)
    except Exception as e:
        ok = f"robots-error {e}"
    if ok is not True:
        print(f"\n### {url}: ROBOTS DISALLOWS ({ok})")
        return None
    try:
        r = session().get(url, timeout=30, **kw)
    except Exception as e:
        print(f"\n### {url}: {type(e).__name__} {str(e)[:200]}")
        return None
    t = r.text
    soup = BeautifulSoup(t, "lxml") if "<" in t[:2000] else None
    title = soup.title.get_text(strip=True)[:120] if soup and soup.title else None
    hdr = {k: v[:120] for k, v in r.headers.items() if k.lower() in ("server", "content-type", "x-powered-by", "cf-ray", "x-cache", "via", "x-robots-tag")}
    print(f"\n### {url} -> {r.status_code} {r.url} len={len(t)} title={title!r} hdr={hdr} cookies={list(r.cookies.keys())} "
          f"block={bool(BLOCK.search(t[:20000]))}")
    if show_robots or n < 0:
        print(t[:3000])
    if n and soup:
        host = urlsplit(r.url).netloc
        links = []
        for a in soup.select("a[href]"):
            h = urljoin(r.url, a["href"])
            if urlsplit(h).netloc.endswith(host.replace("www.", "")) and h not in links:
                links.append(h)
        print(f"links ({len(links)}):", " | ".join(x.replace("https://" + host, "") for x in links[:n]))
        print("scripts:", [s.get("src") for s in soup.select("script[src]")][:30])
        inl = " ".join(s.string or "" for s in soup.select("script:not([src])"))
        print("inline script len", len(inl), "markers:", sorted(set(re.findall(r"__NEXT_DATA__|__NUXT__|window\.__[A-Z_]+|/api/[\w/.-]+|ajax[\w/.-]*|graphql|\.json\b", t)))[:40])
        for f in soup.select("form"):
            print("form", f.get("action"), f.get("method"), [i.get("name") for i in f.select("input,select")][:30])
    if grep:
        for m in list(re.finditer(grep, t, re.I))[:12]:
            s = t[max(0, m.start() - ctx): m.end() + ctx]
            print("  ~", re.sub(r"\s+", " ", s))
    return r


TERMS = r"scrap|robot|automati|vyt[eě]ž|vytaz|data.?mining|dolov|vytěžov|text.{0,6}dat|TDM|extrakc|kopírov|kopirov|strojov"

for base in ("https://www.hydrotour.sk", "https://hydrotour.sk", "https://www.hydrotour.cz", "https://hydrotour.cz"):
    fetch(base + "/robots.txt", -1)
for base in ("https://www.hydrotour.sk", "https://www.hydrotour.cz"):
    r = fetch(base + "/", 200, grep=r"alhambra|letisk|odlet|bratislav|ko[sš]ic|brno|vied|api")
    if r is None:
        continue
    soup = BeautifulSoup(r.text, "lxml")
    terms = []
    for a in soup.select("a[href]"):
        if re.search(r"podmien|podmín|vop|obchod|pravidl|ochrana|gdpr|pouzi|použí|terms|cookies", a.get("href", "") + " " + a.get_text(), re.I):
            h = urljoin(r.url, a["href"])
            if h not in terms:
                terms.append(h)
    print("terms candidates:", terms)
    for h in terms[:5]:
        fetch(h, 0, grep=TERMS, ctx=300)
