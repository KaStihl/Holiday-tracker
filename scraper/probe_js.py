"""TEMPORARY probe 3 (removed after use): hotel-level API, paging/age params from JS, rendered terms."""
import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bs4 import BeautifulSoup  # noqa: E402

import common  # noqa: E402

KW = re.compile(r"vy[tť]a[zž]|data\s*mining|dolovan|text(u|ov)?\s+a\s+d[aá]t|\bTDM\b|scrap|robot|automati|crawl|"
                r"strojov|vytěž|ťažb|extrah|harvest|kopírova|rozmnož|autorsk", re.I)
S = common.session()
TR = "63260|63288|63448|64152|64153|64154|64157|211801|211814|212113"


def summarize(o, depth=0, maxd=4):
    """keys + types tree, lists show first element."""
    pad = "  " * depth
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (dict, list)) and depth < maxd:
                print(f"{pad}{k}: {type(v).__name__}{'[' + str(len(v)) + ']' if isinstance(v, list) else ''}")
                summarize(v, depth + 1, maxd)
            else:
                print(f"{pad}{k}: {json.dumps(v, ensure_ascii=False)[:160]}")
    elif isinstance(o, list) and o:
        summarize(o[0], depth, maxd)


def pdf_text(u):
    import pypdf
    r = S.get(u, timeout=60)
    return " ".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(r.content)).pages)


def kw(label, t):
    hits = list(KW.finditer(t))
    print(f"KW {label}: {len(t)} chars, {len(hits)} hits")
    for m in hits[:12]:
        print("   >", re.sub(r"\s+", " ", t[max(0, m.start() - 220):m.end() + 220]))


def main():
    from playwright.sync_api import sync_playwright
    q = {"tt": 1, "to": "483|3789", "d": TR, "dd": "2027-07-01", "rd": "2027-08-31", "nn": "7|8|9|10|11|12|13|14",
         "ac1": 1, "ic1": 2, "m": 5, "sc": "residential"}
    r = S.get("https://www.fischer.sk/api/searchapi/getsearchresult", params=q, timeout=60)
    print("API", r.status_code, len(r.text), r.url)
    try:
        d = r.json()
        summarize(d)
        print("RAW", r.text[:6000])
    except ValueError:
        print(r.text[:2000])
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(user_agent=common.UA, locale="sk-SK")
        page = ctx.new_page()
        for u in ["https://www.fischer.sk/podmienky/podmienky-pre-cestujucich", "https://www.kartago.sk/uzitocne-informacie/vseobecne-podmienky",
                  "https://www.fischer.sk/podmienky"]:
            print("ROBOTS", u, common.allowed(u))
            page.goto(u, wait_until="networkidle", timeout=60000)
            t = page.inner_text("body")
            kw(u, t)
            print("   TEXT:", re.sub(r"\s+", " ", t)[2000:5000])
            links = page.eval_on_selector_all("a[href]", "els => els.map(e => [e.innerText.trim().slice(0,70), e.href])")
            for txt, h in links:
                if re.search(r"\.pdf|podmien|pravn|legal|pouziv|vop", h + txt, re.I):
                    print(f"   LINK {txt!r} {h}")
            for txt, h in links:
                if h.lower().endswith(".pdf") or "getmedia" in h:
                    if re.search(r"podmien|vop|zmluv", h + txt, re.I):
                        try:
                            kw(h, pdf_text(h))
                        except Exception as e:
                            print("   pdf err", h, e)
                        time.sleep(1.5)
            time.sleep(1.5)
        xhrs, scripts = [], []
        page.on("request", lambda rq: xhrs.append(rq.url) if "getsearchresult" in rq.url else (
            scripts.append(rq.url) if rq.resource_type == "script" else None))
        url = "https://www.fischer.sk/vysledky-vyhledavani?" + "&".join(f"{k}={v}" for k, v in q.items())
        page.goto(url, wait_until="networkidle", timeout=60000)
        for _ in range(4):
            page.mouse.wheel(0, 6000)
            page.wait_for_timeout(2000)
        print("BODY", re.sub(r"\s+", " ", page.inner_text("body"))[:3000])
        print("XHRS", xhrs)
        btns = page.eval_on_selector_all("button, a", "els => els.map(e => e.innerText.trim()).filter(t => /viac|ďalš|načítať|zobraziť/i.test(t)).slice(0,20)")
        print("BUTTONS", btns)
        # child ages UI
        html = page.content()
        for m in list(re.finditer(r".{0,200}(vek|Vek dieťaťa|age).{0,200}", html))[:8]:
            print("AGEHTML", m[0])
        print("SCRIPTS", [s for s in scripts if "fischer" in s])
        pat = re.compile(r'.{0,200}(?:\bic1\b|\bia1\b|\bka1\b|\bca1\b|childAge|kidsAge|childrenAge|birthDate|kidsAges|ages).{0,200}')
        n = 0
        for s in scripts:
            if "fischer.sk" not in s:
                continue
            js = S.get(s, timeout=60).text
            for m in pat.finditer(js):
                print(f"JS {s.rsplit('/', 1)[-1][:50]}: {m[0]}")
                n += 1
                if n > 50:
                    break
            if n > 50:
                break
        b.close()


if __name__ == "__main__":
    main()
