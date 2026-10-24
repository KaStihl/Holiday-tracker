"""TEMPORARY: probe which length filters satur/cedok accept (DOVOLENKA_DUMP=1 keeps the responses)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters import cedok, satur  # noqa: E402
from common import get  # noqa: E402
from config import CONFIG  # noqa: E402

T = "01.07.2027-31.08.2027"
for v in [None, "10-11", "10,11", "7-14", "11"]:
    p = {"termin": T, **({"dlzka-pobytu": v} if v else {})}
    try:
        cards = satur.parse_cards(get(satur.HOME + "/dovolenka/turecko/letecky/z-bratislavy/all-inclusive", params=p))
        print("[probe satur]", v, len(cards), sorted({(c["nights"], c["dates"]) for c in cards})[:25])
    except Exception as e:
        print("[probe satur]", v, e)
for days in [(11, 11), (8, 15)]:
    rates, count, links = cedok.parse_page(get(cedok.HOME + "/vysledky-vyhladavania/dovolenky/turecko/",
                                               params=cedok._query(CONFIG, days=days)))
    print("[probe cedok]", days, count, sorted((r.get("duration") or {}).get("days") or 0 for r in rates))
