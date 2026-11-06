"""TEMPORARY probe #3 (deleted after use): BILLA Nur Hotel query variants."""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from common import get
from config import CONFIG as cfg
import hotel_only
base = hotel_only.billa_query(cfg, 7)
variants = {
    "A mine": dict(base),
    "B no ttid": {k: v for k, v in base.items() if k != "ttid"},
    "C site-like": {"bdid": "ib", "na": 2, "nc": 0, "dpfebl": "tr,dd,da", "pttid": "PH", "ptoj": "PH", "pdf": "3380096",
                    "pdcoom": "o,c,h", "pdacf": "au", "dft": "apx", "psdf": "2027-07-01", "pedf": "2027-08-31",
                    "pnnfl": 7, "pnnfh": 7, "pna": 2, "pnc": 0, "ps": "pr", "pdm": "pp", "idvfmb": 1},
}
variants["D C+ai"] = dict(variants["C site-like"], pbtf="ai")
for name, q in variants.items():
    try:
        h = get("https://www.billareisen.at/Hotels/Angebote.html", params=q)
    except Exception as e:
        print(name, "ERROR", e); continue
    cards = h.count("ITS_OBJ_product-desc__title")
    m = re.search(r"Seite 1 von (\d+)", h)
    rows, pages = hotel_only.parse_billa(h, cfg)
    side = [r for r in rows if hotel_only.in_side(r)]
    print(f"{name}: {len(h)} bytes, title-cards {cards}, pages {m[1] if m else '?'}, parsed {len(rows)}, side {len(side)}")
    i = h.find("ITS_OBJ_product-desc__copy")
    print("   copy:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h[i:i + 600]))[:220] if i > 0 else "-")
    j = h.find("ITS_price")
    print("   price:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h[j:j + 300]))[:120] if j > 0 else "-")
    for k in ("keine", "Keine Angebote", "leider"):
        x = h.find(k)
        if x > 0:
            print("   msg:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h[x - 100:x + 200]))[:200]); break
    print("   side sample:", [(r["hotel"], r["place"], r["pp"], r["checkin"], r["board"]) for r in side[:4]])
