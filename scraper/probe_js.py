"""TEMPORARY probe 4 (removed after use): sort/paging params, children ages, brands."""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

S = common.session()
TR = "63260|63288|63448|64152|64153|64154|64157|211801|211814|212113"


def brief(t):
    tour, h = t["tour"], t["hotel"]
    room = tour["rooms"][0]
    return (h["name"], h["breadcrumbs"].get("country"), tour["date"], tour["nightsCount"], room["meal"],
            [a["price"] for a in room["adults"]], [(c["age"], c["price"]) for c in room["children"]],
            tour["price"]["total"], tour["price"].get("discount"), t["hotelGtm"]["brand"], t["dataSource"],
            tour["flight"]["departure"]["segments"][0]["airport"]["fromIATA"], tour.get("isFirstMinute"),
            t["hotelGtm"].get("dimension7"))


def call(home, extra, label):
    q = {"tt": 1, "to": "483|3789", "d": TR, "dd": "2027-07-01", "rd": "2027-08-31", "nn": "7|8|9|10|11|12|13|14",
         "ac1": 1, "kc1": 2, "ka1": "10|12", "m": 5, "sc": "residential"}
    q.update(extra)
    time.sleep(1.5)
    r = S.get(home + "/api/searchapi/getsearchresult", params=q, timeout=60)
    print(f"== {label} {r.status_code} {len(r.text)} {r.url}")
    try:
        d = r.json()
    except ValueError:
        print(r.text[:500])
        return None
    tours = d.get("tours") or []
    print(f"   toursCount={d.get('toursCount')} got={len(tours)} resultType={d['settings']['resultType']}")
    for t in tours[:4]:
        print("   ", brief(t))
    if tours:
        print("    prices:", [t["tour"]["price"]["total"] for t in tours])
        print("    nights:", [t["tour"]["nightsCount"] for t in tours])
    return d


def main():
    js = S.get("https://www.fischer.sk/Scripts/web/index.CD3GWOsj.js", timeout=60).text
    for key in ("paginationPerPage", "sortBy", "orderBy", "sortType", "sorting"):
        for m in list(re.finditer(key, js))[:3]:
            print(f"JS[{key}]:", js[max(0, m.start() - 700):m.end() + 700].replace("\n", " "))
    for home in ("https://www.fischer.sk", "https://www.kartago.sk"):
        d = call(home, {}, home + " base")
        if d and d.get("tours"):
            t = d["tours"][0]
            print("   detailUrl:", t["detailUrl"])
            print("   filter:", t["filter"])
            print("   tags:", json.dumps(t["tour"].get("tags"), ensure_ascii=False)[:600])
            print("   hoteltags:", json.dumps(t["hotel"].get("tags"), ensure_ascii=False)[:600])
            print("   priceDetail:", json.dumps(t["tour"]["rooms"][0]["priceDetail"], ensure_ascii=False)[:600])
            print("   discount:", json.dumps(t["tour"]["rooms"][0].get("discount"), ensure_ascii=False))
            print("   gtm keys:", list(d.get("gtmData", {}).keys()))
            print("   other keys:", [k for k in d.keys()])
            print("   sortings:", json.dumps({k: v for k, v in d.items() if "sort" in k.lower() or "order" in k.lower()},
                                          ensure_ascii=False)[:1500])
    call("https://www.fischer.sk", {"pitg": 50}, "pitg50")
    call("https://www.fischer.sk", {"pitg": 20, "pstg": 20}, "skip20")
    for s in ({"ob": "price"}, {"so": 1}, {"s": "PriceAsc"}, {"sort": "price"}, {"o": "pa"}):
        call("https://www.fischer.sk", s, f"sort {s}")


if __name__ == "__main__":
    main()
