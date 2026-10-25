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


def rsc(html):
    """Concatenated React Server Components flight payload (self.__next_f.push([1,"..."]))."""
    out = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html):
        try:
            out.append(json.loads(m[1]))
        except ValueError:
            pass
    return "".join(out)


def cedok_report(tag, html):
    soup = BeautifulSoup(html, "lxml")
    flight = rsc(html)
    print(f"--- cedok {tag}: {len(html)} bytes, rsc {len(flight)} chars")
    seen = set()
    for m in re.finditer(r'"participants":\{[^{}]*\}', flight):
        if m[0] in seen:
            continue
        seen.add(m[0])
        print("  PARTICIPANTS", m[0], "| after:", flight[m.end():m.end() + 700])
    keys = set()
    for a in soup.find_all(href=True):
        for k, v in parse_qsl(urlsplit(a["href"]).query):
            if "particip" in k:
                keys.add((k, v))
    print("  HREF participant keys", sorted(keys)[:20])
    for m in list(re.finditer(r"childrenBirthDates|birthDate|childAge|childrenAges", flight))[:8]:
        print("  CTX", flight[max(0, m.start() - 200):m.end() + 200].replace("\n", " "))
    for m in list(re.finditer(r'"(error|notFound|digest)"', flight))[:3]:
        print("  ERR", flight[max(0, m.start() - 100):m.end() + 200])


def cedok():
    print("=================== CEDOK")
    o = next(o for o in OFFERS if o["source"] == "cedok" and o["board"] in ("AI", "UAI"))
    url = o["url"]
    print(f"OFFER {o['hotel']} {o['date_from']} {o['nights']}n price_total(x3)={o['price_total']}")
    A = "participants[0][adults]"
    P = "participants[0]"
    variants = {
        "cbd_iso_idx": {f"{P}[childrenBirthDates][0]": "2017-01-15", f"{P}[childrenBirthDates][1]": "2015-01-15"},
        "cbd_sk_idx": {f"{P}[childrenBirthDates][0]": "15.01.2017", f"{P}[childrenBirthDates][1]": "15.01.2015"},
        "cbd_iso_csv": {f"{P}[childrenBirthDates]": "2017-01-15,2015-01-15"},
        "cbd_sk_csv": {f"{P}[childrenBirthDates]": "15.01.2017,15.01.2015"},
        "children_csv": {f"{P}[children]": "2017-01-15,2015-01-15"},
        "children_idx_sk": {f"{P}[children][0]": "15.01.2017", f"{P}[children][1]": "15.01.2015"},
        "childrenAges": {f"{P}[childrenAges]": "10,12"},
        "childrenN_cbd": {f"{P}[childrenNumber]": "2", f"{P}[childrenBirthDates][0]": "2017-01-15",
                          f"{P}[childrenBirthDates][1]": "2015-01-15"},
    }
    for tag, extra in variants.items():
        u = with_params(url, drop=(A,), **{A: 1}, **extra)
        try:
            cedok_report(tag, get(u))
        except Exception as e:
            print(f"--- cedok {tag}: {type(e).__name__} {str(e)[:200]}")


def satur_report(tag, html):
    soup = BeautifulSoup(html, "lxml")
    m = re.search(r'"children_age":"[^"]*","passengers":"[^"]*","adults":\d+,"children":\d+', html)
    print(f"--- satur {tag}: {len(html)} bytes; dataLayer: {m[0] if m else None}")
    for el in soup.select("[class*=term], [class*=Term], [data-price], [class*=price]")[:12]:
        print("  EL", el.name, el.get("class"), _t(el)[:200])
    for a in soup.select("ul[data-category-target=productsListing] article")[:4]:
        print("  CARD", _t(a.select_one("h2"))[:60], "|", _t(a.select_one("footer"))[:200])


def _t(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def satur():
    print("=================== SATUR")
    o = next(o for o in OFFERS if o["source"] == "satur" and o["board"] in ("AI", "UAI") and o["transport"] == "flight")
    print(f"OFFER {o['hotel']} {o['url']} {o['date_from']} {o['date_to']} {o['nights']}n x3={o['price_total']}")
    d1 = "{2}.{1}.{0}".format(*o["date_from"].split("-"))
    d2 = "{2}.{1}.{0}".format(*o["date_to"].split("-"))
    base = o["url"].split("?")[0]
    for tag, u in [
        ("form_get", f"{base}?" + urlencode({"date": f"{d1} - {d2}", "passengers": "18,10,12", "numberOfRooms": 1,
                                             "length": o["nights"], "food": 3, "transport": 3})),
        ("form_get_ajaxless", f"{base}?" + urlencode({"termin": f"{d1}-{d2}", "osoby": "18,10,12"})),
    ]:
        try:
            satur_report(tag, get(u))
        except Exception as e:
            print(f"--- satur {tag}: {type(e).__name__} {str(e)[:200]}")
    lst = "https://www.satur.sk/dovolenka/letecky/z-bratislavy/all-inclusive"
    q = {"termin": "01.07.2027-31.08.2027", "dlzka-pobytu": 7}
    for tag, extra in [("list_plain", {}), ("list_passengers", {"passengers": "18,10,12"}),
                       ("list_osoby", {"dospeli": 1, "deti": "10,12"})]:
        try:
            satur_report(tag, get(lst, params={**q, **extra}))
        except Exception as e:
            print(f"--- satur {tag}: {type(e).__name__} {str(e)[:200]}")


def tip():
    print("=================== TIP")
    html = get("https://tiptravel.sk/dovolenka/lanzarote/barcelo-playa-blanca/")
    soup = BeautifulSoup(html, "lxml")
    for s in soup.find_all("select")[:20]:
        print("  SELECT", s.get("name"), s.get("id"), s.get("class"), [o.get("value") for o in s.find_all("option")][:15])
    for m in list(re.finditer(r"\d[\d\s]{2,6}\s*€", soup.get_text(" ")))[:10]:
        print("  PRICE", repr(soup.get_text(" ")[max(0, m.start() - 100):m.end()]))
    for m in list(re.finditer(r"(search\.json|termin|terms?\.json|\.json\?)[^\"']{0,200}", html))[:10]:
        print("  JSONREF", m[0][:250])


if __name__ == "__main__":
    for fn in (cedok, satur, tip):
        try:
            fn()
        except Exception as e:
            print(f"{fn.__name__} failed: {type(e).__name__} {e}")
