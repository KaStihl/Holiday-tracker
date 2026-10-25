"""TEMPORARY probe 5 (removed after use): print trimmed real API responses for test fixtures."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters import dertour  # noqa: E402
from common import get  # noqa: E402
from config import CONFIG  # noqa: E402

DROP_HOTEL = ("extendedAttribues", "descriptions", "tags", "iconTags", "imageTags", "gps", "minPrice")


def trim_tour(t):
    t = json.loads(json.dumps(t))
    for k in ("hotelGtm", "priceCheck", "priceFormattingModel"):
        t.pop(k, None)
    h = t["hotel"]
    h["images"] = h["images"][:1]
    for k in DROP_HOTEL:
        h.pop(k, None)
    t["tour"].pop("detailInfo", None)
    t["tour"].pop("hotelInfoDataKey", None)
    return t


home = "https://www.fischer.sk"
cats = get(home + dertour.API, params=dertour.query(CONFIG), as_json=True)
dests = cats["categories"][0]["destinations"]
small = {"settings": {"resultType": cats["settings"]["resultType"]},
         "categories": [{"id": 0, "name": None, "destinations": [
             {k: d[k] for k in ("id", "name", "destinationIds", "hotelCount", "priceFrom")} for d in dests]}]}
print("FIXTURE_CATS " + json.dumps(small, ensure_ascii=False))
tr = next(d for d in dests if d["name"] == "Turecko")
data = get(home + dertour.API, params=dertour.query(CONFIG, (7, 14), tr["destinationIds"]), as_json=True)
tours = data["tours"]
pick = [t for t in tours if t["dataSource"] == 256][:3] + [t for t in tours if t["dataSource"] != 256][:2]
out = {"settings": {"resultType": data["settings"]["resultType"]}, "toursCount": data["toursCount"],
       "tours": [trim_tour(t) for t in pick]}
print("FIXTURE_TOURS " + json.dumps(out, ensure_ascii=False))
