"""TEMPORARY probe 2 (removed after use): search API shape, child-age params, terms PDFs."""
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

OUT = Path(__file__).resolve().parent / "debug"
OUT.mkdir(exist_ok=True)
KW = re.compile(r"vy[tť]a[zž]|data\s*mining|dolovan|text(u|ov)?\s+a\s+d[aá]t|\bTDM\b|scrap|robot|automatiz|crawl|"
                r"stroj(ov|ne)|vytěž|ťažb|extrah|harvest|kopírova|rozmnož", re.I)
S = common.session()


def show(label, text, n=6000):
    print(f"--- {label} ({len(text)} chars)")
    print(text[:n])


def text_of(r):
    ct = r.headers.get("content-type", "")
    if "pdf" in ct or r.url.lower().endswith(".pdf"):
        import pypdf
        return " ".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(r.content)).pages)
    return BeautifulSoup(r.text, "lxml").get_text(" ", strip=True)


def terms(home, paths):
    for p in paths:
        u = urljoin(home, p)
        time.sleep(1.5)
        r = S.get(u, timeout=60)
        soup = BeautifulSoup(r.text, "lxml") if "html" in r.headers.get("content-type", "") else None
        t = text_of(r)
        print(f"TERMS {r.status_code} {u} -> {r.url} {len(t)} chars")
        print("   TEXT:", re.sub(r"\s+", " ", t)[:1200])
        for m in list(KW.finditer(t))[:10]:
            print("     KW>", re.sub(r"\s+", " ", t[max(0, m.start() - 200):m.end() + 200]))
        if soup:
            for a in soup.select("main a[href], .content a[href], article a[href], a[href$='.pdf']"):
                h = a["href"]
                if re.search(r"\.pdf|podmien|pravn|legal", h, re.I):
                    print(f"   LINK {a.get_text(' ', strip=True)[:60]!r} {urljoin(u, h)}")


def api(home, q):
    url = home + "/api/searchapi/getsearchresult"
    print(f"robots {url}: {common.allowed(url)}")
    time.sleep(1.5)
    r = S.get(url, params=q, timeout=60, headers={"Accept": "application/json"})
    print(f"API {r.status_code} {r.url} {r.headers.get('content-type')}")
    return r


def main():
    terms("https://www.kartago.sk", ["/uzitocne-informacie/vseobecne-podmienky", "/uzitocne-informacie/podmienky-pouzivania",
                                     "/o-nas"])
    terms("https://www.fischer.sk", ["/podmienky/podmienky-pre-cestujucich", "/podmienky", "/podmienky/podmienky-pouzivania"])
    r = S.get("https://www.eximtours.sk/", timeout=30, allow_redirects=False)
    print("EXIM home", r.status_code, r.headers.get("location"))
    r = S.get("https://www.eximtours.sk/robots.txt", timeout=30, allow_redirects=False)
    print("EXIM robots", r.status_code, r.headers.get("location"))

    base = {"tt": 1, "to": "483|3789", "dd": "2027-07-01", "rd": "2027-08-31", "nn": "7|8|9|10|11|12|13|14",
            "ac1": 1, "ic1": 2, "m": 5, "sc": "residential"}
    for home in ("https://www.kartago.sk", "https://www.fischer.sk"):
        r = api(home, base)
        show(home + " categories", r.text, 14000)
        (OUT / (home.split(".")[1] + "_cat.json")).write_text(r.text)

    # children-age / param names in the JS bundles
    html = S.get("https://www.fischer.sk/vysledky-vyhledavani", timeout=30).text
    srcs = [urljoin("https://www.fischer.sk/", s) for s in re.findall(r'<script[^>]+src="([^"]+)"', html)]
    print("SCRIPTS", srcs)
    pat = re.compile(r'.{0,250}(?:\bic1\b|\bka1\b|"ac1"|ac1:|childAge|kidsAge|childrenAge|birthDate|\bage\d?\b).{0,250}')
    hits = 0
    for s in srcs:
        if "fischer.sk" not in s:
            continue
        time.sleep(1.5)
        try:
            js = S.get(s, timeout=60).text
        except Exception as e:
            print(s, e)
            continue
        for m in pat.finditer(js):
            print(f"JS {s.rsplit('/', 1)[-1][:40]}: {m[0]}")
            hits += 1
            if hits > 40:
                return


if __name__ == "__main__":
    main()
