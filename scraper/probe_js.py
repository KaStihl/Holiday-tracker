"""TEMPORARY probe (removed after use): robots.txt, terms TDM check and XHR capture on Kartago/Fischer/Exim."""
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
from adapters import eximtours, fischer, kartago  # noqa: E402
from config import CONFIG  # noqa: E402

OUT = Path(__file__).resolve().parent / "debug"
OUT.mkdir(exist_ok=True)
KW = re.compile(r"vy[tť]a[zž]|data\s*mining|dolovan|text(u|ov)?\s+a\s+d[aá]t|\bTDM\b|scrap|robot|automatiz|crawl|"
                r"stroj(ov|ne)|vytěž|ťažb|extrah|harvest", re.I)


def terms(home):
    s = common.session()
    r = s.get(home, timeout=30)
    print(f"  home {r.status_code} {len(r.text)}")
    soup = BeautifulSoup(r.text, "lxml")
    links = {}
    for a in soup.select("a[href]"):
        t = (a.get_text(" ", strip=True) + " " + a["href"]).lower()
        if re.search(r"podmien|vop|ochran|pravn|legal|cookies|terms|gdpr|autorsk", t):
            links[urljoin(home, a["href"])] = a.get_text(" ", strip=True)[:60]
    for u, t in list(links.items())[:12]:
        print(f"  link: {t!r} {u}")
    for u in list(links)[:6]:
        if not common.allowed(u):
            print(f"  robots disallows {u}")
            continue
        time.sleep(1.5)
        try:
            r = s.get(u, timeout=30)
        except Exception as e:
            print(f"  {u}: {e}")
            continue
        ct = r.headers.get("content-type", "")
        if "pdf" in ct or u.lower().endswith(".pdf"):
            try:
                import pypdf
                text = " ".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(r.content)).pages)
            except Exception as e:
                text = f"PDF? {e}"
        else:
            text = BeautifulSoup(r.text, "lxml").get_text(" ", strip=True)
        hits = [text[max(0, m.start() - 150):m.end() + 150] for m in KW.finditer(text)]
        print(f"  TERMS {r.status_code} {ct[:30]} {len(text)} chars, {len(hits)} keyword hits: {u}")
        for h in hits[:8]:
            print("     >", re.sub(r"\s+", " ", h))


def capture(page, name, url):
    seen = []

    def on_resp(resp):
        rt = resp.request.resource_type
        if rt not in ("xhr", "fetch", "document"):
            return
        ct = resp.headers.get("content-type", "")
        entry = {"url": resp.url, "status": resp.status, "type": rt, "ct": ct, "method": resp.request.method,
                 "post": (resp.request.post_data or "")[:1500]}
        if "json" in ct:
            try:
                body = resp.text()
                entry["len"] = len(body)
                entry["head"] = body[:600]
                fn = OUT / f"{name}_{len(seen):02d}.json"
                fn.write_text(body[:3_000_000])
                entry["file"] = fn.name
            except Exception as e:
                entry["err"] = str(e)
        seen.append(entry)

    page.on("response", on_resp)
    print(f"  robots allows page: {common.allowed(url)}")
    t0 = time.time()
    try:
        r = page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"  goto {r.status if r else None} -> {page.url}")
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            print("  networkidle timeout")
        for _ in range(3):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1500)
    except Exception as e:
        print(f"  goto error {e}")
    print(f"  title {page.title()!r} in {time.time() - t0:.0f}s")
    html = page.content()
    (OUT / f"{name}_page.html").write_text(html)
    txt = page.inner_text("body")[:3000]
    print("  BODY:", re.sub(r"\s+", " ", txt)[:1500])
    page.remove_listener("response", on_resp)
    for e in seen:
        if e["type"] == "document" and "json" not in e["ct"]:
            print(f"  DOC {e['status']} {e['url'][:200]}")
            continue
        print(f"  XHR {e['method']} {e['status']} {e['ct'][:25]} len={e.get('len')} {e['url'][:300]}")
        if e["post"]:
            print(f"      POST: {e['post'][:800]}")
        if e.get("head"):
            print(f"      HEAD: {e['head'][:400]}")
        if e.get("url"):
            print(f"      robots allows xhr: {common.allowed(e['url'])}")
    (OUT / f"{name}_index.json").write_text(json.dumps(seen, indent=1))


def main():
    from playwright.sync_api import sync_playwright
    sites = [("kartago", kartago), ("fischer", fischer), ("exim", eximtours)]
    for name, mod in sites:
        print(f"===== {name} {mod.HOME}")
        r = common.session().get(mod.HOME + "/robots.txt", timeout=30)
        print(f"  robots.txt {r.status_code}:\n" + "\n".join("    " + l for l in r.text.splitlines()[:60]))
        terms(mod.HOME)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(user_agent=common.UA, locale="sk-SK")
        page = ctx.new_page()
        for name, mod in sites:
            url = mod.deeplinks(CONFIG)[0]["url"]
            print(f"===== {name} browser {url}")
            capture(page, name, url)
            time.sleep(2)
        b.close()


if __name__ == "__main__":
    main()
