"""TEMPORARY probe (removed after the occupancy investigation): what do detail pages accept for 1 adult + 2 kids?
Prints compact findings to the job log; DOVOLENKA_DUMP=1 keeps full bodies in scraper/debug/ (uploaded as artifact).
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from common import get  # noqa: E402

KEYS = re.compile(r"particip|child|kid|birth|age\b|ages|adult|dosp|diet|deti|vek|osob|person|pax|occup|room|izb", re.I)
OFFERS = json.loads((Path(__file__).resolve().parents[1] / "site/data/offers.json").read_text())["offers"]


def walk(o, path="", out=None, depth=0):
    out = [] if out is None else out
    if depth > 14 or len(out) > 80:
        return out
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{path}.{k}"
            if KEYS.search(k):
                out.append((p, json.dumps(v, ensure_ascii=False)[:300]))
            walk(v, p, out, depth + 1)
    elif isinstance(o, list):
        for i, v in enumerate(o[:3]):
            walk(v, f"{path}[{i}]", out, depth + 1)
    return out


def html_report(tag, html):
    soup = BeautifulSoup(html, "lxml")
    print(f"--- {tag}: {len(html)} bytes, title={soup.title.string if soup.title else None!r}")
    for f in soup.find_all("form")[:12]:
        ins = [(i.get("name"), i.get("value"), i.get("type")) for i in f.find_all(["input", "select"]) if i.get("name")]
        print(f"  FORM action={f.get('action')!r} method={f.get('method')!r} inputs={ins[:40]}")
    for el in soup.find_all(True):
        attrs = {k: v for k, v in el.attrs.items() if isinstance(k, str) and KEYS.search(k)}
        if attrs:
            print(f"  ATTR <{el.name}> {json.dumps(attrs, ensure_ascii=False)[:400]}")
    hrefs = {a["href"] for a in soup.find_all(href=True) if KEYS.search(a["href"])}
    for h in sorted(hrefs)[:25]:
        print(f"  HREF {h[:300]}")
    for s in soup.find_all("script"):
        t = s.string or ""
        if s.get("id") == "__NEXT_DATA__":
            continue
        for m in list(re.finditer(r"(particip|children|childAge|birth|adults?|dospel|deti|vek)", t, re.I))[:6]:
            print(f"  SCRIPT[{s.get('src') or s.get('type') or ''}] …{t[max(0, m.start() - 150):m.end() + 200]!r}")
    return soup


def with_params(url, drop=(), **add):
    p = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k not in drop]
    return urlunsplit(p._replace(query=urlencode(q + list(add.items()))))


def cedok():
    print("=================== CEDOK")
    cands = [o for o in OFFERS if o["source"] == "cedok" and o["board"] in ("AI", "UAI")][:2]
    for o in cands:
        url = o["url"]
        print(f"OFFER {o['hotel']} {o['date_from']} {o['nights']}n price_total(x3)={o['price_total']}")
        variants = [("orig", url),
                    ("adults1", with_params(url, drop=("participants[0][adults]",), **{"participants[0][adults]": 1}))]
        if o is cands[0]:
            variants += [
                ("childrenBirthDates", with_params(url, drop=("participants[0][adults]",), **{
                    "participants[0][adults]": 1, "participants[0][childrenBirthDates][0]": "2017-01-15",
                    "participants[0][childrenBirthDates][1]": "2015-01-15"})),
                ("children_birthDate", with_params(url, drop=("participants[0][adults]",), **{
                    "participants[0][adults]": 1, "participants[0][children][0][birthDate]": "2017-01-15",
                    "participants[0][children][1][birthDate]": "2015-01-15"})),
            ]
        for tag, u in variants:
            try:
                html = get(u)
            except Exception as e:
                print(f"--- {tag}: {type(e).__name__} {str(e)[:200]}")
                continue
            soup = html_report(f"cedok {tag}", html)
            nd = soup.find("script", id="__NEXT_DATA__")
            if not nd:
                print("  no __NEXT_DATA__")
                continue
            d = json.loads(nd.string)
            print("  NEXT page", d.get("page"), "query", json.dumps(d.get("query"), ensure_ascii=False)[:600])
            pp = d.get("props", {}).get("pageProps", {})
            print("  pageProps keys", list(pp)[:30])
            for q in (pp.get("initialQueryState") or {}).get("queries", [])[:20]:
                print("  QUERY", json.dumps(q.get("queryKey"), ensure_ascii=False)[:700])
            for p, v in walk(pp)[:60]:
                print(f"  KEY {p} = {v}")
            prices = re.findall(r'"price":(\d+)', nd.string)[:10]
            print("  first prices", prices)


def satur():
    print("=================== SATUR")
    o = next(o for o in OFFERS if o["source"] == "satur" and o["board"] in ("AI", "UAI") and o["transport"] == "flight")
    print(f"OFFER {o['hotel']} {o['url']} {o['date_from']} {o['nights']}n x3={o['price_total']}")
    for tag, u in [("orig", o["url"]),
                   ("dospeli", with_params(o["url"], dospeli=1, deti=2, vek="10,12"))]:
        try:
            html = get(u)
        except Exception as e:
            print(f"--- {tag}: {type(e).__name__} {str(e)[:200]}")
            continue
        soup = html_report(f"satur {tag}", html)
        for m in list(re.finditer(r"\d[\d\s]{2,6}\s*€", soup.get_text(" ")))[:15]:
            print("  PRICE", repr(soup.get_text(" ")[max(0, m.start() - 80):m.end()]))


def tip():
    print("=================== TIP")
    for tag, u in [("detail", "https://tiptravel.sk/dovolenka/lanzarote/barcelo-playa-blanca/"),
                   ("detail_occ", "https://tiptravel.sk/dovolenka/lanzarote/barcelo-playa-blanca/?AdultsCount=1&ChildrenCount=2&ChildrenAges=10,12")]:
        try:
            html = get(u)
        except Exception as e:
            print(f"--- {tag}: {type(e).__name__} {str(e)[:200]}")
            continue
        html_report(f"tip {tag}", html)


if __name__ == "__main__":
    for fn in (cedok, satur, tip):
        try:
            fn()
        except Exception as e:
            print(f"{fn.__name__} failed: {type(e).__name__} {e}")
