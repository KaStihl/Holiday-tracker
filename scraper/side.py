"""Build site/data/side.json for the tab "🏨 Side – hotely pri pláži" (run after run.py, before build_html.py):

    python scraper/side.py

1. OSM hotels near the beach (side_hotels.py; Overpass at most once a week, cached in site/data/side_hotels.json).
2. Agency offers of the Side area from site/data/offers.json (every party), matched to the OSM hotels by name;
   their facility flags (offer["fac"]: Satur/BILLA card icons, DERTOUR/Ruefa room names), boards and exact
   one-room prices give the family criteria with their source.
3. Flights VIE/BTS/BRQ -> AYT from the Travelpayouts cache (flights.py, needs TRAVELPAYOUTS_TOKEN).
4. Accommodation-only prices where a legitimate source has them (hotel_only.py: BILLA Reisen "Nur Hotel") and
   Ruefa's attribute filters (water slide / family room / direct beach) – both at most once a day, cached in
   site/data/side_daily.json – otherwise the page says "cena len ubytovania nedostupná".
The page computes the own package (flights × persons + hotel + 2 × transfer_eur) next to the agency package.
Nothing here may fail the run: every network part degrades to "unavailable" and the previous data stays.
"""

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import flights as flights_mod  # noqa: E402
import hotel_only  # noqa: E402
import side_hotels as sh  # noqa: E402
from common import expand_offers  # noqa: E402
from config import CONFIG, party_size  # noqa: E402
from watch import norm_name  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
CACHE = DATA / "side_hotels.json"
OUT = DATA / "side.json"
OFFERS = DATA / "offers.json"
DAILY = DATA / "side_daily.json"
DAILY_HOURS = 20
GPS_MATCH_M = 150  # an agency hotel without a name match goes to the OSM hotel within this distance of its GPS

# words that don't tell two hotels apart (on top of watch.STOPWORDS)
GENERIC = {"beach", "side", "club", "deluxe", "de", "luxe", "family", "suites", "suite", "premium", "collection",
           "all", "inclusive", "boutique", "by", "kumkoy", "colakli", "evrenseki", "titreyengol", "sorgun", "kizilagac",
           "manavgat", "turkey", "antalya", "ultra", "plus", "adults", "only", "kids", "concept", "otel", "s", "luxury",
           "lux", "wellness", "spa", "hotels", "resort", "resorts", "and", "&", "village", "holiday", "beachfront"}
OFFERS_PER_PARTY = 12   # agency offers kept per hotel and party (cheapest per source/nights/date)
EXACT_ROOM_SOURCES = ("kartago", "fischer", "ruefa")  # exact price = one room for exactly that party


def core(name):
    return frozenset(w for w in norm_name(name).split() if w not in GENERIC)


def name_score(a, b):
    """1.0 when both names have the same core words (accents, case and GENERIC words ignored), else 0. No partial
    matches: "Side Royal Palace" must not become "Royal Alhambra Palace", nor "Sural Saray" "Süral Resort"."""
    ca, cb = core(a), core(b)
    return 1.0 if ca and ca == cb else 0.0


def offer_area(o, keys):
    """Area key of an agency offer in the Side area (from place, then region), else None."""
    if (o.get("country_code") or "TR") != "TR":
        return None
    for field in ("place", "region"):
        words = norm_name(o.get(field) or "").split()
        for w in words:
            if w in keys:
                return w
        joined = "".join(words)
        for k in keys:
            if k in joined:
                return k
    return None


def side_offers(offers, scfg):
    keys = list(sh.AREAS)  # every known area: an offer of an unconfigured area must not match a configured hotel
    out = []
    for o in offers:
        a = offer_area(o, keys)
        if a:
            out.append(dict(o, _area=a))
    return out


def match_offers(hotels, offers, max_area_km=3.0):
    """{hotel index: [offers]} plus the unmatched offers. An offer goes to the best-scoring hotel name; ties prefer a
    hotel of the offer's own area, then the closer one to that area."""
    by_name = {}
    for o in offers:
        by_name.setdefault(o["hotel"], []).append(o)
    got, rest = {}, []
    for name, os_ in by_name.items():
        area = os_[0]["_area"]
        best = None
        for i, h in enumerate(hotels):
            s = name_score(name, h["name"])
            if not s:
                continue
            key = (s, h["area"] == area, -h.get("dist_m", 0))
            if best is None or key > best[0]:
                best = (key, i)
        if not best:  # DERTOUR offers carry the hotel's GPS: the nearest OSM hotel within GPS_MATCH_M
            g = next((o["gps"] for o in os_ if o.get("gps")), None)
            if g:
                for i, h in enumerate(hotels):
                    d = gps_dist(g, (h["lat"], h["lon"]))
                    if d <= GPS_MATCH_M and (best is None or d < best[0][0]):
                        best = ((d,), i)
        if best:
            got.setdefault(best[1], []).extend(os_)
        else:
            rest.extend(os_)
    return got, rest


def gps_dist(a, b):
    ax, ay = sh.xy(*a)
    bx, by = sh.xy(*b)
    return math.hypot(ax - bx, ay - by)


def compact_offer(o):
    return [o["source"], o["price_total"], o.get("board"), o["date_from"], o["nights"], o.get("departure"),
            1 if o.get("price_exact") else 0, o["url"]]


def summarize(hotel, offers, src_name, parties, ruefa_attr=None):
    """Family-criteria evidence (with sources) and the cheapest offers per party for one hotel."""
    fac, fit, ai, names, beach = {}, {}, set(), set(), {}
    for o in offers:
        names.add(o["hotel"])
        sn = src_name.get(o["source"], o["source"])
        for f in o.get("fac") or ():
            fac.setdefault(f, set()).add(sn)
        for f in (ruefa_attr or {}).get(o.get("gid") or "", ()):
            fac.setdefault(f, set()).add(sn + " (filter)")
        if o.get("beach_m") is not None:
            beach[sn] = min(beach.get(sn, 9999), o["beach_m"])
        if o.get("board") in ("AI", "UAI"):
            ai.add(sn)
        if o.get("price_exact") and o["source"] in EXACT_ROOM_SOURCES:
            fit.setdefault(o.get("party"), set()).add(sn)
    of = {}
    for p in parties:
        mine = sorted((o for o in offers if o.get("party") == p["id"]), key=lambda o: o["price_total"])
        seen, keep = set(), []
        for o in mine:
            k = (o["source"], o["nights"], o["date_from"])
            if k not in seen:
                seen.add(k)
                keep.append(compact_offer(o))
        if keep:
            of[p["id"]] = keep[:OFFERS_PER_PARTY]
    hotel["fac"] = {k: sorted(v) for k, v in sorted(fac.items())}
    if beach:  # the agency's own "distance to the beach" (DERTOUR tag), next to the OSM distance
        sn, m = min(beach.items(), key=lambda kv: kv[1])
        hotel["bd"] = [m, sn]
    hotel["fit"] = {k: sorted(v) for k, v in fit.items() if k}
    hotel["ai"] = sorted(ai)
    hotel["an"] = sorted(n for n in names if n != hotel["name"])[:3]
    hotel["of"] = of
    return hotel


def osm_hotels(scfg, now=None):
    """(hotels from the cache or a fresh Overpass query, cache dict, status text)."""
    cache = sh.load_cache(CACHE)
    if sh.cache_fresh(cache, now):
        return cache["hotels"], cache, f"cache z {cache['fetched_at'][:10]}"
    try:
        t0 = time.time()
        raw = sh.fetch_overpass(scfg)
        hotels = sh.process_osm(raw, scfg)
        cache = {"fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                 "bbox": list(sh.BBOX), "source": "© OpenStreetMap contributors (ODbL), Overpass API",
                 "keep_m": sh.CACHE_KEEP_M, "elements": len(raw.get("elements") or []), "hotels": hotels}
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"[side] Overpass: {cache['elements']} elements, {len(hotels)} hotels in {time.time() - t0:.0f} s")
        return hotels, cache, "nové dáta"
    except Exception as e:
        print(f"[side] Overpass failed: {type(e).__name__} {str(e)[:200]}")
        if cache and cache.get("hotels"):
            return cache["hotels"], cache, f"Overpass nedostupný, staršia cache z {cache.get('fetched_at', '?')[:10]}"
        return [], {}, f"Overpass nedostupný ({type(e).__name__})"


def daily(cfg, gids, now=None):
    """Hotel-only rows (hotel_only.py) and Ruefa attributes, refreshed at most every DAILY_HOURS (side_daily.json)."""
    now = now or datetime.now(timezone.utc)
    window = [cfg["date_from"].isoformat(), cfg["date_to"].isoformat()]
    try:
        cache = json.loads(DAILY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = None
    if cache and cache.get("window") == window and cache.get("fetched_at"):
        try:
            age = now - datetime.fromisoformat(cache["fetched_at"].replace("Z", "+00:00"))
            if age.total_seconds() < DAILY_HOURS * 3600:
                print(f"[side] daily data from cache {cache['fetched_at']}")
                return cache
        except ValueError:
            pass
    try:
        ho = hotel_only.fetch(cfg)
    except Exception as e:
        print(f"[side] hotel-only failed: {type(e).__name__} {str(e)[:160]}")
        ho = {"sources": [dict(x, requests=0) for x in hotel_only.SOURCES_INFO], "rows": {}}
    try:
        from adapters import ruefa
        attr = ruefa.side_attributes(cfg, gids)
    except Exception as e:
        print(f"[side] Ruefa attributes failed: {type(e).__name__} {str(e)[:160]}")
        attr = (cache or {}).get("ruefa_attr") or {}
    if not any(ho["rows"].values()) and cache and any((cache.get("rows") or {}).values()):
        ho = {"sources": cache["sources"], "rows": cache["rows"]}  # keep yesterday's prices over nothing
    out = {"fetched_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"), "window": window,
           "sources": ho["sources"], "rows": ho["rows"], "ruefa_attr": attr}
    if any(x.get("status") == "error" for x in ho["sources"]):
        print("[side] hotel-only source failed – not cached, the next run tries again")
        out["fetched_at"] = (cache or {}).get("fetched_at")
        return out
    DAILY.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return out


def hotel_only_prices(rows_by_src, hotels, parties, src_names):
    """{hotel id: {party id: [[source, price for the party, checkin, nights, board, url], …]}} – rows matched to the
    tab's hotels by name (same rule as the offers); price = € per person at 2 adults × persons (orientačne)."""
    out = {}
    for src, rows in rows_by_src.items():
        for r in rows:
            best = None
            for h in hotels:
                sc = name_score(r["hotel"], h["n"])
                if sc and (best is None or sc > best[0]):
                    best = (sc, h)
            if not best:
                continue
            h = best[1]
            for p in parties:
                lst = out.setdefault(h["id"], {}).setdefault(p["id"], [])
                lst.append([src, r["pp"] * party_size(p), r["checkin"], r["nights"], r.get("board"), r["url"]])
    for per in out.values():
        for pid, lst in per.items():
            seen, keep = set(), []
            for x in sorted(lst, key=lambda x: x[1]):
                if (x[0], x[2], x[3]) not in seen:
                    seen.add((x[0], x[2], x[3]))
                    keep.append(x)
            per[pid] = keep[:OFFERS_PER_PARTY]
    return out


def build(cfg=CONFIG, offers=None, osm=None, flights=None, hotel_prices=None, now=None):
    """The side.json dict. Arguments other than cfg are for tests (otherwise read/fetched here)."""
    scfg = cfg["side"]
    now = now or datetime.now(timezone.utc)
    doc = {"generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"), "enabled": scfg["enabled"],
           "max_m": scfg["max_m"], "transfer_eur": scfg["transfer_eur"], "kriteria": scfg["kriteria"],
           "areas": [{"id": k, "name": sh.AREAS[k][0]} for k in scfg["oblasti"]],
           "parties": [{"id": p["id"], "nazov": p["nazov"], "adults": p["adults"], "kids": p["children_ages"],
                        "persons": party_size(p)} for p in cfg["parties"]],
           "date_from": cfg["date_from"].isoformat(), "date_to": cfg["date_to"].isoformat(),
           "stays": flights_mod.stays(cfg)}
    if not scfg["enabled"]:
        return doc
    if osm is None:
        hotels, cache, osm_status = osm_hotels(scfg, now)
    else:
        hotels, cache, osm_status = osm, {"fetched_at": None}, "test"
    hotels = [dict(h) for h in hotels if h["area"] in scfg["oblasti"] and h["dist_m"] <= scfg["max_m"]]
    doc["osm"] = {"status": osm_status, "fetched_at": cache.get("fetched_at")}
    if offers is None:
        try:
            raw = json.loads(OFFERS.read_text(encoding="utf-8"))
            offers, sources = expand_offers(raw.get("offers") or []), raw.get("sources") or []
        except (OSError, ValueError):
            offers, sources = [], []
    else:
        sources = []
    src_name = {s["id"]: s["name"] for s in sources}
    for o in offers:
        src_name.setdefault(o["source"], o.get("source_name") or o["source"])
    primary = cfg["parties"][0]["id"]
    for o in offers:
        o.setdefault("party", primary)
    so = side_offers(offers, scfg)
    got, rest = match_offers(hotels, so)
    gids = sorted({o["gid"] for o in so if o.get("gid") and o["_area"] in scfg["oblasti"]})
    day = daily(cfg, gids, now) if hotel_prices is None else hotel_prices
    attr = day.get("ruefa_attr") or {}
    # agency hotels with no OSM match: kept when the agency says "directly on the beach" or gives a beach distance
    # within the limit (DERTOUR tag) – their distance is the agency's, not OSM's
    extra = {}
    for o in rest:
        if o["_area"] in scfg["oblasti"]:
            extra.setdefault(norm_name(o["hotel"]), []).append(o)
    out = []
    for i, h in enumerate(hotels):
        h = {"id": h["osm"], "n": h["name"], "a": h["area"], "d": h["dist_m"], "dk": h["dist_kind"][0],
             "lat": h["lat"], "lon": h["lon"], "st": h.get("stars"), "w": h.get("website"),
             "aqo": h.get("aquapark_osm"), "pools": h.get("pools"), "name": h["name"]}
        summarize(h, got.get(i, []), src_name, cfg["parties"], attr)
        if not h["st"]:
            h["st"] = next((o.get("stars") for o in got.get(i, []) if o.get("stars")), None)
        out.append(h)
    unmatched = 0
    for key, os_ in extra.items():
        bm = min((o["beach_m"] for o in os_ if o.get("beach_m") is not None), default=None)
        if not (any("pl" in (o.get("fac") or ()) for o in os_) or (bm is not None and bm <= scfg["max_m"])):
            unmatched += 1
            continue
        g = next((o["gps"] for o in os_ if o.get("gps")), None)
        h = {"id": "a:" + key.replace(" ", "-")[:40], "n": os_[0]["hotel"], "a": os_[0]["_area"], "d": None, "dk": None,
             "lat": g[0] if g else None, "lon": g[1] if g else None,
             "st": next((o.get("stars") for o in os_ if o.get("stars")), None), "w": None,
             "aqo": None, "pools": None, "name": os_[0]["hotel"]}
        out.append(summarize(h, os_, src_name, cfg["parties"], attr))
    for h in out:
        h.pop("name", None)
        for k in [k for k, v in h.items() if v in (None, [], {})]:
            del h[k]
    doc["src"] = src_name
    doc["stats"] = {"osm_hotels": len(hotels), "side_offers": len(so), "matched_offers": sum(map(len, got.values())),
                    "agency_only_beach": len(out) - len(hotels), "agency_unmatched_hotels": unmatched}
    # flights
    fl = flights_mod.fetch(cfg) if flights is None else flights
    doc["flights"] = {"status": fl["status"], "error": fl.get("error"), "dest": flights_mod.DEST,
                      "origins": flights_mod.origins(cfg), "list": fl["flights"]}
    # accommodation only
    doc["hotel_only"] = {"sources": day.get("sources") or [], "fetched_at": day.get("fetched_at")}
    hp = hotel_only_prices(day.get("rows") or {}, out, cfg["parties"], src_name)
    for h in out:
        if hp.get(h["id"]):
            h["ho"] = hp[h["id"]]
    doc["stats"]["hotel_only_hotels"] = len(hp)
    doc["stats"]["ruefa_attr_hotels"] = len(attr)
    doc["hotels"] = sorted(out, key=lambda h: (scfg["oblasti"].index(h["a"]) if h["a"] in scfg["oblasti"] else 99,
                                               h.get("d") if h.get("d") is not None else 9999, h["n"]))
    return doc


def summary(doc):
    hs = doc.get("hotels") or []
    print(f"[side] {len(hs)} hotels on the tab (≤ {doc['max_m']} m), stats {doc.get('stats')}")
    for a in doc["areas"]:
        mine = [h for h in hs if h["a"] == a["id"]]
        print(f"[side]   {a['name']}: {len(mine)} hotels, with agency offers {sum(bool(h.get('of')) for h in mine)}")
    crit = {"aquapark": lambda h: h.get("fac", {}).get("aq") or h.get("aqo"),
            "detsky_klub": lambda h: h.get("fac", {}).get("kc"),
            "all_inclusive": lambda h: h.get("ai"),
            "rodinna_izba": lambda h: h.get("fac", {}).get("fr") or h.get("fit"),
            "cena len ubytovania": lambda h: h.get("ho")}
    for k, fn in crit.items():
        print(f"[side]   {k}: {sum(bool(fn(h)) for h in hs)} hotels")
    print(f"[side] flights: {doc.get('flights', {}).get('status')} ({len(doc.get('flights', {}).get('list') or [])}), "
          f"hotel-only sources: " + ", ".join(f"{x['id']} {x['status']}" for x in doc.get("hotel_only", {}).get("sources", [])))
    for h in hs:
        if any(w in norm_name(h["n"]) for w in ("alhambra", "sural")):
            print(f"[side]   {h['n']} ({h['a']}, {h.get('d')} m): fac {h.get('fac')}, ai {h.get('ai')}, fit {h.get('fit')}, "
                  f"offers {{{', '.join(f'{k}: {v[0][1]}' for k, v in (h.get('of') or {}).items())}}}, "
                  f"hotel-only {{{', '.join(f'{k}: {v[0][1]}' for k, v in (h.get('ho') or {}).items())}}}")


def main():
    try:
        doc = build()
    except Exception as e:  # never fail the run because of the side tab: keep the previous file
        import traceback
        traceback.print_exc()
        print(f"[side] build failed, keeping the previous side.json: {type(e).__name__} {e}")
        return
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    summary(doc)
    print(f"[side] wrote {OUT.name} {OUT.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
