"""TEMPORARY probe of hydrotour.sk – prints to the job log only, deleted after use. Iteration 8."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from common import allowed, session  # noqa: E402

H = "https://www.hydrotour.sk"
U = H + "/japi/ISearchApi/searchTerminyRaw"


def post(label, body):
    assert allowed(U)
    r = session().post(U, json=[body], timeout=60, headers={"Content-Type": "application/json"})
    try:
        d = r.json()
    except ValueError:
        print(f"\n## {label} {r.status_code} NOT JSON {r.text[:600]}")
        return None
    hs = d.get("hotely") or []
    ts = d.get("terminy") or []
    nested = [t for h in hs for t in (h.get("terminy") or [])]
    allt = ts or nested
    print(f"\n## {label} {json.dumps(body)[:260]} -> {r.status_code} len={len(r.text)} hotely={len(hs)} terminy={len(ts)} "
          f"nested={len(nested)} vynechane={d.get('vynechaneFiltre')} keys={list(d)}")
    if allt:
        print("   months", sorted(Counter(str(t.get('datumOd'))[:7] for t in allt).items())[:20],
              "dni", sorted(Counter(t.get('dni') for t in allt).items())[:12])
    return d


def trim(x, n=200):
    if isinstance(x, dict):
        return {k: trim(v, n) for k, v in x.items() if k not in ("popis", "obrazky", "vybavenie", "popisy", "vylety")}
    if isinstance(x, list):
        return [trim(v, n) for v in x[:4]]
    if isinstance(x, str):
        return x[:n]
    return x


d = post("staty9-pocet10", {"staty": [9], "terminyPocet": 10})
if d and d.get("hotely"):
    h0 = d["hotely"][0]
    print("HOTEL0 keys:", list(h0))
    print("HOTEL0:", json.dumps(trim(h0), ensure_ascii=False)[:4500])
    if d.get("terminy"):
        print("TERM0:", json.dumps(trim(d["terminy"][0]), ensure_ascii=False)[:3500])
for lab, extra in [
    ("dates-iso", {"datumOd": "2027-07-01", "datumDo": "2027-08-31"}),
    ("dates-T", {"datumOd": "2027-07-01T00:00:00", "datumDo": "2027-08-31T00:00:00"}),
    ("dateOd-only", {"datumOd": "2027-07-01"}),
    ("cest-1+2", {"cestujuci": [[18, 10, 12]]}),
    ("cest-2", {"cestujuci": [[18, 18]]}),
    ("dni8", {"dni": [8]}),
]:
    post(lab, dict({"staty": [9], "oblasti": [1021], "terminyPocet": 3}, **extra))
d = post("side-jul-aug-1+2-pocet50", {"oblasti": [1021], "datumOd": "2027-07-01", "datumDo": "2027-08-31",
                                       "cestujuci": [[18, 10, 12]], "terminyPocet": 50})
if d:
    hs = d.get("hotely") or []
    print("names:", [(h.get("nazov"), h.get("hotelId"), len(h.get("terminy") or [])) for h in hs][:40])
    for h in hs:
        if re.search("alhambra|dragon|sural", h.get("nazov") or "", re.I):
            print("WATCHED:", json.dumps(trim(h), ensure_ascii=False)[:3500])
    if d.get("terminy"):
        print("TERM0-1+2:", json.dumps(trim(d["terminy"][0]), ensure_ascii=False)[:3500])
        print("TERM1-1+2:", json.dumps(trim(d["terminy"][1]), ensure_ascii=False)[:2000])
post("all-jul-aug-1+2-pocet3", {"datumOd": "2027-07-01", "datumDo": "2027-08-31", "cestujuci": [[18, 10, 12]],
                                "terminyPocet": 3})
post("hotel215", {"hotely": [215], "terminyPocet": 50})
