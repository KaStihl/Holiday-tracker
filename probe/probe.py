"""Temporary diagnostics for new sources (deleted after use)."""
import re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
import requests
from common import UA, Robots

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "de-AT,de;q=0.9,en;q=0.7"})
MARK = ["_abck", "akamai", "cf-chl", "cloudflare", "captcha", "Access Denied", "datadome", "perimeterx",
        "px-captcha", "incapsula", "Pardon Our Interruption", "challenge-platform", "sec-if-cpt", "kasada"]
TDM = re.compile(r"(text.{0,3}und.{0,3}data.{0,3}mining|data.{0,3}mining|TDM|§\s*42h|scrap|crawl|automatisiert\w*|robots?\b|Spider|maschinell\w*|vytežovan\w*|automatizovan\w*)", re.I)
TERMS = re.compile(r"(agb|nutzungsbedingung|impressum|rechtlich|datenschutz|terms|podmienk|pravne|legal|disclaimer)", re.I)

def fetch(url, **kw):
    try:
        r = S.get(url, timeout=25, **kw)
    except Exception as e:
        print(f"  !! {url}: {type(e).__name__} {str(e)[:150]}")
        return None
    time.sleep(1.5)
    return r

def show(r, label):
    t = r.text
    hits = [m for m in MARK if m.lower() in t.lower() or m.lower() in str(r.headers).lower()]
    print(f"  {label} {r.status_code} {r.url} len={len(t)} server={r.headers.get('server')} "
          f"cookies={list(r.cookies.keys())[:8]} markers={hits}")

def site(home, extra=()):
    print(f"\n===== {home}")
    r = fetch(home + "/robots.txt")
    rb = None
    if r is not None:
        print(f"  robots {r.status_code} len={len(r.text)}")
        if r.ok:
            lines = [l for l in r.text.splitlines() if l.strip() and not l.startswith("#")]
            print("   | " + "\n   | ".join(lines[:70]))
            rb = Robots(r.text, UA)
    h = fetch(home + "/")
    if h is None:
        return
    show(h, "home")
    hosts = sorted({urlsplit(s).netloc for s in re.findall(r'src="(https?://[^"]+)"', h.text)})
    print("  script hosts:", hosts[:25])
    kw = sorted(set(m.lower() for m in re.findall(r"(traffics|peakwork|bistro|travelport|ibe\w*|giata|tt-?ibe|nezasa|"
                                                      r"travelsandbox|vtours|tourOnline|xmlwebservice|graphql|/api/[\w/-]+)", h.text, re.I)))
    print("  keywords:", kw[:40])
    links = []
    for href, txt in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', h.text, re.S):
        if TERMS.search(href) or TERMS.search(re.sub("<[^>]+>", "", txt)):
            u = urljoin(h.url, href)
            if u not in links and u.startswith("http"):
                links.append(u)
    print("  legal links:", links[:12])
    for u in list(links[:4]) + list(extra):
        if rb and not rb.can_fetch(u):
            print(f"  (robots disallows {u})")
            continue
        p = fetch(u)
        if p is None:
            continue
        show(p, "legal")
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", p.text, flags=re.S)))
        seen = 0
        for m in TDM.finditer(txt):
            if seen >= 6:
                break
            seen += 1
            print("    TDM?", txt[max(0, m.start() - 160): m.end() + 200])
    for u in extra_urls.get(home, []):
        allowed = rb.can_fetch(u) if rb else True
        print(f"  extra robots_allowed={allowed} {u}")
        if allowed:
            p = fetch(u)
            if p is not None:
                show(p, "extra")
                print("    ", re.sub(r"\s+", " ", p.text[:600]))

extra_urls = {}
SITES = ["https://www.tui.at", "https://www.neckermann-reisen.at", "https://www.neckermann-reisen.de",
         "https://www.thomascook.com", "https://www.ruefa.at", "https://www.gruber-reisen.at",
         "https://www.billareisen.at", "https://www.hofer-reisen.at", "https://www.lidl-reisen.at",
         "https://www.ab-in-den-urlaub.at", "https://www.weg.de", "https://www.holidaycheck.at",
         "https://urlaub.check24.at", "https://www.check24.at", "https://www.urlaubsguru.at",
         "https://www.airstop.sk", "https://www.restplatzboerse.at", "https://www.dertour.at"]
for s in SITES:
    site(s)
