"""Side – hotels near the beach (second tab of dovolenka.html, "🏨 Side – hotely pri pláži").

OpenStreetMap part: one Overpass API query (overpass-api.de, usage policy: https://dev.overpass-api.de/overpass-doc/en/
preface/commons.html – few queries, honest User-Agent) for a bounding box around Side, at most once a week; the
result is reduced to the hotels within max_vzdialenost_od_plaze_m of a beach and cached in site/data/side_hotels.json
(committed with the other data files). Between refreshes every run reuses the cache.

Elements asked (all inside BBOX):
  tourism=hotel|resort and leisure=resort (geometry)       -> hotel candidates (named ones)
  natural=beach (geometry), natural=coastline ways          -> distance to the beach / the water line
  leisure=water_park, attraction=water_slide (center)       -> "aquapark" from OSM (inside / next to the hotel)
  leisure=swimming_pool (center)                            -> pool count (information only)
  place=town|village|suburb|… nodes                          -> where the areas (oblasti) are
Distances are computed on a local flat projection (fine at a few km): from every hotel vertex (polygon edges densified
to ~20 m) to the nearest beach / coastline segment, using a grid index.
"""

import json
import math
import re
from datetime import datetime, timezone

from watch import norm_name

OVERPASS = "https://overpass-api.de/api/interpreter"
# south, west, north, east: Kızılağaç/Çolaklı in the west to the Manavgat river mouth / Kızılot road in the east
BBOX = (36.70, 31.18, 36.86, 31.60)
OSM_MAX_AGE_DAYS = 7
CACHE_KEEP_M = 1000  # the cache keeps hotels up to this far from the beach, so a larger limit needs no new query

# Areas (oblasti in nastavenia.yml): normalised key -> (display name, fallback lat, lon). The coordinates are only a
# fallback – the query also returns the OSM place nodes and their positions win when the name matches.
AREAS = {
    "side": ("Side", 36.7675, 31.3890),
    "kumkoy": ("Kumköy", 36.7780, 31.3600),
    "colakli": ("Çolaklı", 36.8000, 31.2950),
    "evrenseki": ("Evrenseki", 36.7880, 31.3280),
    "titreyengol": ("Titreyengöl", 36.7560, 31.4480),
    "sorgun": ("Sorgun", 36.7650, 31.4250),
    "kizilagac": ("Kızılağaç", 36.8150, 31.2550),
    "manavgat": ("Manavgat (pobrežie)", 36.7400, 31.4850),
}
AREA_MAX_KM = 4.5  # a hotel farther than this from every configured area is outside "Side and surroundings"


def area_key(name):
    return norm_name(name).replace(" ", "")


# --- query --------------------------------------------------------------------------------------------------------

def overpass_query(bbox=BBOX):
    s, w, n, e = bbox
    return f"""[out:json][timeout:120][bbox:{s},{w},{n},{e}];
(nwr["tourism"~"^(hotel|resort)$"]["name"]; nwr["leisure"="resort"]["name"];);
out tags geom;
(nwr["natural"="beach"]; way["natural"="coastline"];);
out geom;
(nwr["leisure"="water_park"]; nwr["attraction"="water_slide"]; nwr["leisure"="swimming_pool"];);
out center;
node["place"~"^(town|village|suburb|neighbourhood|quarter|hamlet)$"]["name"];
out;"""


def fetch_overpass(scfg=None, bbox=BBOX):
    """The raw Overpass JSON (one POST). robots.txt and the polite delay come from common.get()."""
    from common import get
    return get(OVERPASS, method="POST", data={"data": overpass_query(bbox)}, as_json=True, retries=1, delay=2)


# --- geometry -----------------------------------------------------------------------------------------------------

LAT0 = (BBOX[0] + BBOX[2]) / 2
KX = 111_320 * math.cos(math.radians(LAT0))  # metres per degree of longitude
KY = 110_574  # metres per degree of latitude


def xy(lat, lon):
    return lon * KX, lat * KY


def _seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if not L else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


class SegIndex:
    """Grid of line segments (and single points as zero-length segments) for nearest-distance lookups."""

    def __init__(self, cell=400.0):
        self.cell, self.grid = cell, {}

    def _cells(self, a, b):
        c = self.cell
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        for i in range(int(x0 // c), int(x1 // c) + 1):
            for j in range(int(y0 // c), int(y1 // c) + 1):
                yield i, j

    def add(self, a, b=None):
        b = b or a
        for k in self._cells(a, b):
            self.grid.setdefault(k, []).append((a, b))

    def nearest(self, p, max_d):
        c = self.cell
        r = int(max_d // c) + 1
        i0, j0 = int(p[0] // c), int(p[1] // c)
        best = None
        for i in range(i0 - r, i0 + r + 1):
            for j in range(j0 - r, j0 + r + 1):
                for a, b in self.grid.get((i, j), ()):
                    d = _seg_dist(p, a, b)
                    if best is None or d < best:
                        best = d
        return best if best is not None and best <= max_d else None


def _lines(el):
    """[[(lat, lon), …], …] of an element: one point for a node, its geometry for a way, member ways of a relation."""
    if el["type"] == "node":
        return [[(el["lat"], el["lon"])]] if "lat" in el else []
    if el["type"] == "way":
        g = el.get("geometry") or []
        return [[(p["lat"], p["lon"]) for p in g if p]] if g else []
    out = []
    for m in el.get("members") or []:
        g = m.get("geometry") or []
        if g:
            out.append([(p["lat"], p["lon"]) for p in g if p])
        elif "lat" in m:
            out.append([(m["lat"], m["lon"])])
    return out


def _point(el):
    if "lat" in el:
        return el["lat"], el["lon"]
    c = el.get("center")
    if c:
        return c["lat"], c["lon"]
    pts = [p for line in _lines(el) for p in line]
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _densify(line, step=20.0):
    pts = [xy(*p) for p in line]
    out = pts[:1]
    for a, b in zip(pts, pts[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = int(d // step)
        for k in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * k / (n + 1), a[1] + (b[1] - a[1]) * k / (n + 1)))
        out.append(b)
    return out


def _inside(p, ring):
    x, y = p
    ins = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            ins = not ins
    return ins


def _rings(el):
    """Closed rings (projected) of a way / multipolygon relation, for point-in-polygon tests."""
    out = []
    for line in _lines(el):
        if len(line) >= 4 and line[0] == line[-1]:
            out.append([xy(*p) for p in line[:-1]])
    return out


# --- processing ---------------------------------------------------------------------------------------------------

def _stars(v):
    m = re.match(r"\s*(\d(?:[.,]5)?)", str(v or ""))
    if not m:
        return None
    s = float(m[1].replace(",", "."))
    return s if 1 <= s <= 5 else None


def _website(tags):
    for k in ("website", "contact:website", "url"):
        v = (tags.get(k) or "").strip()
        if v.startswith("https://"):
            return v
        if v.startswith("http://"):
            return "https://" + v[7:]
        if v and "." in v and " " not in v and not v.startswith(("ftp", "mailto")):
            return "https://" + v
    return None


def _name(tags):
    return (tags.get("name:en") if re.search(r"[^\x00-ɏ]", tags.get("name", "")) else None) or \
        tags.get("name") or tags.get("name:en") or tags.get("name:de")


def area_centers(elements, scfg):
    """{area key: (display name, lat, lon)} for the configured areas: the OSM place node of that name (the biggest
    place kind wins), else the fallback coordinates."""
    rank = {"town": 0, "village": 1, "suburb": 2, "quarter": 3, "neighbourhood": 4, "hamlet": 5}
    found = {}
    for el in elements:
        t = el.get("tags") or {}
        if el["type"] != "node" or "place" not in t:
            continue
        for nm in (t.get("name"), t.get("name:en"), t.get("name:tr")):
            k = area_key(nm or "")
            if k in AREAS and (k not in found or rank.get(t["place"], 9) < found[k][0]):
                found[k] = (rank.get(t["place"], 9), el["lat"], el["lon"])
    out = {}
    for k in scfg["oblasti"]:
        name, lat, lon = AREAS[k]
        if k in found:
            lat, lon = found[k][1], found[k][2]
        out[k] = (name, lat, lon, k in found)
    return out


def nearest_area(lat, lon, centers, tags=None):
    """(area key, km) – an addr:suburb/addr:city/is_in naming a configured area wins, else the nearest center."""
    p = xy(lat, lon)
    for k in ("addr:suburb", "addr:neighbourhood", "addr:quarter", "addr:village", "addr:city", "addr:place"):
        a = area_key((tags or {}).get(k) or "")
        if a in centers and a != "manavgat":  # addr:city=Manavgat is the whole district – use the distance then
            c = centers[a]
            return a, math.hypot(p[0] - xy(c[1], c[2])[0], p[1] - xy(c[1], c[2])[1]) / 1000
    best = None
    for k, c in centers.items():
        d = math.hypot(p[0] - xy(c[1], c[2])[0], p[1] - xy(c[1], c[2])[1]) / 1000
        if best is None or d < best[1]:
            best = (k, d)
    return best


def process_osm(raw, scfg, keep_m=CACHE_KEEP_M):
    """Overpass JSON -> list of hotel dicts within keep_m of a beach / the coastline, deduplicated by name:
    {osm, name, lat, lon, dist_m, dist_kind ('beach'|'coast'), area, stars, website, aquapark_osm, pools}."""
    els = raw.get("elements") or []
    beach, coast = SegIndex(), SegIndex()
    hotels, parks, pools = [], [], []
    for el in els:
        t = el.get("tags") or {}
        if t.get("natural") == "beach":
            for line in _lines(el):
                pts = [xy(*p) for p in line]
                if len(pts) == 1:
                    beach.add(pts[0])
                for a, b in zip(pts, pts[1:]):
                    beach.add(a, b)
        elif t.get("natural") == "coastline":
            for line in _lines(el):
                pts = [xy(*p) for p in line]
                for a, b in zip(pts, pts[1:]):
                    coast.add(a, b)
        elif t.get("leisure") == "water_park" or t.get("attraction") == "water_slide":
            p = _point(el)
            if p:
                parks.append((xy(*p), t.get("name") or ("vodný park" if t.get("leisure") == "water_park" else "tobogan")))
        elif t.get("leisure") == "swimming_pool":
            p = _point(el)
            if p:
                pools.append(xy(*p))
        elif (t.get("tourism") in ("hotel", "resort") or t.get("leisure") == "resort") and _name(t):
            hotels.append(el)
    centers = area_centers(els, scfg)
    out = {}
    for el in hotels:
        t = el["tags"]
        lines = _lines(el)
        if not lines:
            continue
        pts = [p for line in lines for p in _densify(line)]
        rings = _rings(el)
        db = [d for d in (beach.nearest(p, keep_m) for p in pts) if d is not None]
        dc = [d for d in (coast.nearest(p, keep_m) for p in pts) if d is not None]
        d_b, d_c = (min(db) if db else None), (min(dc) if dc else None)
        if d_b is None and d_c is None:
            continue
        # the beach polygon counts first; the water line only when it is clearly closer (unmapped beach strip)
        if d_b is not None and (d_c is None or d_b <= d_c + 80):
            dist, kind = d_b, "beach"
        else:
            dist, kind = d_c, "coast"
        lat, lon = _point(el)
        area = nearest_area(lat, lon, centers, t)
        if not area or area[1] > AREA_MAX_KM:
            continue

        def near(q, r):
            if any(_inside(q, ring) for ring in rings):
                return True
            return min(math.hypot(q[0] - p[0], q[1] - p[1]) for p in pts) <= r

        aq = sorted({nm for q, nm in parks if near(q, 60)})
        n_pools = sum(1 for q in pools if near(q, 25 if rings else 120))
        h = {"osm": f"{el['type'][0]}{el['id']}", "name": _name(t).strip(), "lat": round(lat, 5), "lon": round(lon, 5),
             "dist_m": int(round(dist)), "dist_kind": kind, "area": area[0], "stars": _stars(t.get("stars")),
             "website": _website(t), "aquapark_osm": aq or None, "pools": n_pools or None}
        key = norm_name(h["name"])
        cur = out.get(key)
        if cur and math.hypot(*(a - b for a, b in zip(xy(cur["lat"], cur["lon"]), xy(lat, lon)))) > 1500:
            key = f"{key}#{h['osm']}"  # same name far apart: a different hotel
            cur = out.get(key)
        if cur:  # the same hotel mapped twice (node + resort polygon): keep the best of both
            if h["dist_m"] < cur["dist_m"]:
                cur.update(dist_m=h["dist_m"], dist_kind=h["dist_kind"])
            for k in ("stars", "website", "aquapark_osm", "pools"):
                cur[k] = cur[k] or h[k]
            continue
        out[key] = h
    return sorted(out.values(), key=lambda h: (list(centers).index(h["area"]), h["dist_m"]))


def print_summary(hotels, scfg):
    lim = scfg["max_m"]
    near = [h for h in hotels if h["dist_m"] <= lim]
    print(f"[side] OSM: {len(hotels)} hotels ≤ {CACHE_KEEP_M} m from the beach/coast, {len(near)} ≤ {lim} m")
    for k in scfg["oblasti"]:
        hs = [h for h in near if h["area"] == k]
        print(f"[side]   {AREAS[k][0]}: {len(hs)} ≤ {lim} m, aquapark (OSM) {sum(bool(h['aquapark_osm']) for h in hs)}: "
              + ", ".join(f"{h['name']} {h['dist_m']}m" for h in hs[:12]))


def side_cfg(cfg):
    """The side_hotely section of CONFIG (config.py fills defaults)."""
    return cfg["side"]


def load_cache(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cache_fresh(cache, now=None, max_age_days=OSM_MAX_AGE_DAYS, bbox=BBOX):
    if not cache or not cache.get("fetched_at") or cache.get("bbox") != list(bbox):
        return False
    try:
        t = datetime.fromisoformat(cache["fetched_at"].replace("Z", "+00:00"))
    except ValueError:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - t).total_seconds() < max_age_days * 86400
