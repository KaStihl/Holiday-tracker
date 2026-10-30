"""Temporary: why are Ruefa long-haul cards dropped by run.normalise? (deleted after use)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from adapters import ruefa
from common import get
from config import CONFIG
import run
hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": ruefa.IBE + "/index.php?page=results"}
for code in ("MV", "TH"):
    data = get(ruefa.IBE + "/hub/ajax/deliver.php", method="POST", data=ruefa.form(CONFIG, ruefa.DEST_IDS[code], 7),
               headers=hdr, as_json=True)
    for o in ruefa.parse(data, CONFIG)[:4]:
        print(code, {k: o[k] for k in ("hotel", "date_from", "date_to", "nights", "departure", "price_total", "board")},
              "kept" if run.normalise(o, "ruefa", "Ruefa", CONFIG) else "DROPPED")
    import re
    v = data.get("value") or ""
    i = v.find("startDate")
    print(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", v[i - 1200:i + 900]))[:900])
