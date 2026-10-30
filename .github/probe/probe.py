"""TEMPORARY endpoint discovery for watched hotels (prints to the job log only; removed after use)."""
import re, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scraper"))
from common import get  # noqa
from config import CONFIG as cfg
from adapters import dertour, satur, cedok
W = re.compile(r"s[uü]ral|alhambra", re.I)

def show(label, url, **kw):
    try:
        t = get(url, retries=0, delay=1, **kw)
    except Exception as e:
        print(f"## {label} {url} -> {type(e).__name__} {str(e)[:200]}")
        return ""
    s = t if isinstance(t, str) else json.dumps(t)
    print(f"## {label} {url} {kw.get('params') or ''} -> {len(s)} bytes, hits={len(W.findall(s))}")
    return t

def ctx(t, word, n=4, w=250):
    for m in list(re.finditer(word, t))[:n]:
        print("   ..." + t[max(0, m.start()-w):m.end()+w].replace("\n", " ") + "...")

# ---------- DERTOUR ----------
K = "https://www.kartago.sk"
page = show("kartago results", K + "/vysledky-vyhladavania")
js = sorted(set(re.findall(r'src="([^"]*index[^"]*\.js)"', page)))
print("index js:", js)
for src in js[:2]:
    t = show("js", K + src if src.startswith("/") else src)
    print("  apis:", sorted(set(re.findall(r'["\'`](/api/[A-Za-z0-9_/\-]+)', t))))
    for word in (r"\bac1\b", r"fulltext|FullText|Fulltext", r"suggest|Suggest", r"hotelId|\bhid\b|\bHID\b", r"\"q\"|\bq:"):
        print("  --", word); ctx(t, word, 3, 220)
hdr = {"Accept": "application/json", "Referer": K + "/"}
q = dertour.query(cfg); q.pop("m", None)
cats = show("cats noAI", K + dertour.API, params=q, headers=hdr, as_json=True)
tr = [c for c in dertour.countries(cats, cfg) if c[0] == "TR"]
print("TR:", tr and tr[0][1:])
if tr:
    dest, cnt = tr[0][2], tr[0][3]
    for p in range(0, min(cnt, 600), 100):
        qq = dertour.query(cfg, None, dest, p); qq.pop("m", None); qq["pitg"] = 100
        d = show("TR all", K + dertour.API, params=qq, headers=hdr, as_json=True)
        for t in d.get("tours") or []:
            h = t.get("hotel") or {}
            if W.search(h.get("name") or ""):
                bc = h.get("breadcrumbs") or {}
                print("   HIT", h.get("id"), h.get("name"), bc.get("area"), bc.get("destination"), t.get("dataSource"),
                      (t.get("tour") or {}).get("price", {}).get("total"), (t.get("tour") or {}).get("date"), t.get("detailUrl")[:200])
        if len(d.get("tours") or []) < 100: break
    # does the API accept a hotel filter?
    for k in ("hid", "h", "HID", "hi", "ft", "q", "text"):
        qq = dertour.query(cfg, None, dest); qq.pop("m", None); qq[k] = "8486" if "h" in k.lower() else "sural"
        d = show("filter " + k, K + dertour.API, params=qq, headers=hdr, as_json=True)
        print("    toursCount", d.get("toursCount"), [((t.get("hotel") or {}).get("name")) for t in (d.get("tours") or [])[:3]])

# ---------- Satur ----------
S = "https://www.satur.sk"
termin = f"{cfg['date_from']:%d.%m.%Y}-{cfg['date_to']:%d.%m.%Y}"
alln = ",".join(str(n) for n in range(cfg["nights_min"], cfg["nights_max"] + 1))
for path in ("/dovolenka/turecko/side", "/dovolenka/turecko/evrenseki", "/dovolenka/turecko/side/letecky",
             "/dovolenka/turecko/turecka-riviera"):
    for n in (1, 2):
        h = show("satur", S + path, params={"termin": termin, "dlzka-pobytu": alln, **({"stranka": n} if n > 1 else {})})
        cards = satur.parse_cards(h) if h else []
        print("   cards", len(cards), [(c["hotel"], c["place"], c["country"]) for c in cards][:25])
        if n == 1 and h:
            print("   names:", sorted(set(re.findall(r'name="([a-zA-Z_\-\[\]]+)"', h)))[:60])
            print("   total:", re.findall(r"(\d+)\s*(?:ponúk|ponuky|hotelov|výsledk)", h)[:5])
        if len(cards) < 20: break
h = show("satur produkt", S + "/produkt/sueral-hotel--313849", params={"termin": termin, "dlzka-pobytu": alln})
if h:
    ctx(h, r"termin|Termín", 3, 200)
    print("   dates:", re.findall(r"\d{1,2}\.\d{1,2}\.\d{4}", h)[:20])
    print("   prices:", re.findall(r"[\d ]{3,7}\s?€", h)[:20])

# ---------- Cedok ----------
C = "https://www.cedok.sk"
for path, params in (("/vysledky-vyhladavania/", {"q": "sural"}),
                     ("/vysledky-vyhladavania/dovolenky/turecko/side/", cedok._query(cfg)),
                     ("/vysledky-vyhladavania/dovolenky/turecko/", dict(cedok._query(cfg), q="sural"))):
    h = show("cedok", C + path, params=params)
    if not h: continue
    rates, count, links = cedok.parse_page(h)
    print("   rates", len(rates), count, [((next((s for s in r.get('segments', []) if s.get('type') == 'hotel'), {}).get('content') or {}).get('title')) for r in rates][:25])
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    if nd:
        pp = json.loads(nd.group(1))["props"]["pageProps"]
        print("   pageProps keys", list(pp)[:30])
        for qq in pp.get("initialQueryState", {}).get("queries", [])[:8]:
            print("   query key", json.dumps(qq.get("queryKey"), ensure_ascii=False)[:400])
    ctx(h, r"[Ss][uü]ral", 3, 200)
