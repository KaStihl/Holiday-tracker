"""TEMPORARY endpoint discovery for watched hotels (prints to the job log only; removed after use)."""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scraper"))
from common import get  # noqa
from config import CONFIG as cfg
from adapters import cedok, satur
W = re.compile(r"s[uü]ral|alhambra|elhamra|alhamra", re.I)
C = "https://www.cedok.sk"
wide = (cfg["nights_min"] + 1, cfg["nights_max"] + 1)
for slug in ("turecko",):
    for page in range(1, 7):
        h = get(f"{C}/vysledky-vyhladavania/dovolenky/{slug}/", params=cedok._query(cfg, page, days=wide))
        rates, count, links = cedok.parse_page(h)
        offs = [o for o in (cedok.to_offer(r, links, cfg) for r in rates) if o]
        print(f"cedok {slug} p{page}: {len(rates)}/{count}", [ (o["hotel"], o["price_total"]) for o in offs if W.search(o["hotel"] or "")],
              "last price", offs[-1]["price_total"] if offs else None)
        if page * 25 >= count: break
S = "https://www.satur.sk"
termin = f"{cfg['date_from']:%d.%m.%Y}-{cfg['date_to']:%d.%m.%Y}"
alln = ",".join(str(n) for n in range(cfg["nights_min"], cfg["nights_max"] + 1))
for n in range(1, 5):
    h = get(S + "/dovolenka/turecko/letecky", params={"termin": termin, "dlzka-pobytu": alln, "stranka": n})
    cards = satur.parse_cards(h)
    print("satur TR p", n, len(cards), [(c["hotel"], c["place"], c["price_person"]) for c in cards if W.search(c["hotel"])])
    print("   total:", re.findall(r"(\d+)\s*(?:ponúk|ponuky|hotelov|výsledk)", h)[:3])
for path in ("/dovolenka/turecko/side", "/dovolenka/turecko/kumkoy", "/dovolenka/turecko/nonexistent-place-xyz"):
    h = get(S + path, params={"termin": termin, "dlzka-pobytu": alln})
    cards = satur.parse_cards(h)
    print(path, len(cards), sorted({(c["place"], c["region"]) for c in cards})[:8], re.findall(r"(\d+)\s*(?:ponúk|ponuky|hotelov|výsledk)", h)[:2])
