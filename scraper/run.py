"""Run every adapter, normalise + score offers, merge price history, write site/data/*.json.

    python scraper/run.py            # all adapters
    python scraper/run.py invia      # just one (debugging)
"""

import importlib
import json
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters import ADAPTERS  # noqa: E402
from common import https_or_none, norm_board, norm_country, offer_id  # noqa: E402
from config import CONFIG, COUNTRY_NAMES, criteria_for_display  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
OFFERS = DATA / "offers.json"
HISTORY = DATA / "history.json"

HISTORY_POINTS = 90
HISTORY_KEEP_DAYS = 60
BOARD_SCORE = {"UAI": 1.0, "AI": 0.95, "FB": 0.6, "HB": 0.45, "BB": 0.25, "RO": 0.1, None: 0.2}


def normalise(raw, source, source_name, cfg):
    """Validate one adapter offer; returns a clean dict or None when it does not match the criteria."""
    o = dict(raw)
    o["source"], o["source_name"] = source, source_name
    o["transport"] = o.get("transport") if o.get("transport") in ("flight", "car") else "flight"
    try:
        price = int(o.get("price_total"))
        nights = int(o.get("nights"))
        d_from = date.fromisoformat(str(o.get("date_from"))[:10])
    except (TypeError, ValueError):
        return None
    if not o.get("hotel") or price <= 0 or price > cfg["price_cap"]:
        return None
    if not (cfg["nights_min"] <= nights <= cfg["nights_max"]):
        return None
    if not (cfg["date_from"] <= d_from <= cfg["date_to"]):
        return None
    if o["transport"] == "car" and o.get("pets_allowed") is False:
        return None
    if o.get("board") not in BOARD_SCORE:
        o["board"] = norm_board(o.get("board"))
    cc = o.get("country_code") or norm_country(o.get("country")) or norm_country(o.get("region"))
    o["country_code"] = cc
    o["country"] = COUNTRY_NAMES.get(cc, o.get("country"))
    o["price_total"], o["nights"], o["date_from"] = price, nights, d_from.isoformat()
    if o.get("date_to"):
        o["date_to"] = str(o["date_to"])[:10]
    else:
        o["date_to"] = date.fromordinal(d_from.toordinal() + nights).isoformat()
    po = o.get("price_original")
    o["price_original"] = int(po) if isinstance(po, (int, float)) and po > price else None
    if o["price_original"] and not o.get("discount_pct"):
        o["discount_pct"] = round(100 * (1 - price / o["price_original"]))
    o["url"] = https_or_none(o.get("url"))
    o["image"] = https_or_none(o.get("image"))
    if not o["url"]:
        return None
    for k in ("stars", "rating", "region", "place", "departure", "discount_label", "discount_pct", "pets_allowed"):
        o.setdefault(k, None)
    o["id"] = offer_id(source, o["hotel"], o["date_from"], nights, o["transport"], o["departure"])
    return o


def score(o, cfg):
    budget = cfg["budget"]
    p = o["price_total"]
    price_s = 1.0 if p <= budget * 0.7 else max(0.0, 1 - (p - budget * 0.7) / (cfg["price_cap"] - budget * 0.7))
    board_s = BOARD_SCORE.get(o["board"], 0.2)
    country_s = cfg["countries"].get(o["country_code"], 0.5)
    disc_s = min((o.get("discount_pct") or 0) / 30, 1.0)
    q = o.get("rating")
    qual_s = (q / 10) if q else ((o.get("stars") or 3) / 5)
    s = 0.45 * price_s + 0.20 * board_s + 0.15 * country_s + 0.10 * disc_s + 0.10 * qual_s
    if p > budget:
        s *= 0.9
    if o["transport"] == "car" and o.get("pets_allowed") is None:
        s *= 0.85
    return round(100 * s)


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def merge_history(offers, today):
    hist = load(HISTORY, {})
    prev_price = {o["id"]: o["price_total"] for o in load(OFFERS, {}).get("offers", [])}
    for o in offers:
        h = hist.setdefault(o["id"], {"first_seen": today, "points": []})
        pts = [p for p in h["points"] if p[0] != today] + [[today, o["price_total"]]]
        h["points"], h["last_seen"] = pts[-HISTORY_POINTS:], today
        o["first_seen"], o["last_seen"] = h["first_seen"], today
        o["price_history"] = h["points"]
        before = prev_price.get(o["id"]) or (pts[-2][1] if len(pts) > 1 else None)
        o["price_change"] = (o["price_total"] - before) if before is not None else None
    cutoff = date.fromisoformat(today).toordinal() - HISTORY_KEEP_DAYS
    return {k: v for k, v in hist.items() if date.fromisoformat(v.get("last_seen", today)).toordinal() >= cutoff}


def main(only=None):
    cfg = CONFIG
    sources, deeplinks, offers = [], [], {}
    for name in ADAPTERS:
        if only and name not in only:
            continue
        mod = importlib.import_module(f"adapters.{name}")
        info = {"id": name, "name": mod.NAME, "home": mod.HOME, "status": "ok", "count": 0, "error": None}
        try:
            deeplinks += [dict(d, source=name, name=mod.NAME) for d in mod.deeplinks(cfg)]
        except Exception as e:  # deeplinks are pure string building; a failure here is a bug
            print(f"[{name}] deeplinks failed: {e}", file=sys.stderr)
        if getattr(mod, "DEEPLINK_ONLY", False):
            info["status"] = "disabled"
            sources.append(info)
            continue
        t0 = time.time()
        try:
            raw = mod.search(cfg)
            clean = [n for n in (normalise(r, name, mod.NAME, cfg) for r in raw) if n]
            for o in clean:
                if o["id"] not in offers or o["price_total"] < offers[o["id"]]["price_total"]:
                    offers[o["id"]] = o
            info["count"] = len({o["id"] for o in clean})
            info["status"] = "ok" if clean else "empty"
            print(f"[{name}] {len(raw)} raw, {len(clean)} kept")
        except Exception as e:
            info["status"], info["error"] = "error", f"{type(e).__name__}: {str(e)[:200]}"
            traceback.print_exc()
        info["duration_s"] = round(time.time() - t0, 1)
        sources.append(info)

    today = datetime.now(timezone.utc).date().isoformat()
    result = sorted(offers.values(), key=lambda o: (-score(o, cfg), o["price_total"]))
    for o in result:
        o["score"] = score(o, cfg)
    hist = merge_history(result, today)

    DATA.mkdir(parents=True, exist_ok=True)
    out = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "criteria": criteria_for_display(),
        "sources": sources,
        "deeplinks": deeplinks,
        "offers": result,
    }
    if only:
        print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
        return
    if not result and any(s["status"] == "ok" for s in load(OFFERS, {}).get("sources", [])):
        # Every scraper failed this run: keep yesterday's offers on the page instead of blanking it.
        prev = load(OFFERS, {})
        out["offers"] = prev.get("offers", [])
        out["stale"] = True
    OFFERS.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(out['offers'])} offers from {sum(s['status'] == 'ok' for s in sources)} sources")


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
