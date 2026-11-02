"""Run every adapter, normalise + score offers, merge price history, write site/data/*.json.

    python scraper/run.py            # all adapters
    python scraper/run.py invia      # just one (debugging)
"""

import importlib
import json
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters import ADAPTERS  # noqa: E402
from common import compact_offers, expand_offers, https_or_none, norm_board, norm_country, offer_id  # noqa: E402
from config import (CONFIG, COUNTRY_NAMES, approx_note, continent, criteria_for_display, extra_parties,  # noqa: E402
                    party_id, party_short, party_size)
from watch import keep_limit, match  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
OFFERS = DATA / "offers.json"
HISTORY = DATA / "history.json"

HISTORY_POINTS = 90
# offers.json is embedded in dovolenka.html: above this size the extra parties keep only their best offers
SIZE_LIMIT = 8_000_000
EXTRA_EXACT_MAX = 6  # exact_price() lookups (Čedok detail pages) per extra party and source
HISTORY_KEEP_DAYS = 60
BOARD_SCORE = {"UAI": 1.0, "AI": 0.95, "FB": 0.6, "HB": 0.45, "BB": 0.25, "RO": 0.1, None: 0.2}


def normalise(raw, source, source_name, cfg):
    """Validate one adapter offer; returns a clean dict or None when it does not match the criteria."""
    o = dict(raw)
    o["source"], o["source_name"] = source, source_name
    o["transport"] = o.get("transport") if o.get("transport") in ("flight", "car") else "flight"
    if o["transport"] not in cfg["transports"]:
        return None
    try:
        price = int(o.get("price_total"))
        nights = int(o.get("nights"))
        d_from = date.fromisoformat(str(o.get("date_from"))[:10])
    except (TypeError, ValueError):
        return None
    if not o.get("hotel") or price <= 0:
        return None
    # watched hotels (sledovane_hotely) stay even above price_cap, up to keep_limit(), flagged over_cap
    o["watched"] = match(o["hotel"], cfg.get("watched"))
    if price > (keep_limit(cfg) if o["watched"] else cfg["price_cap"]):
        return None
    if not (cfg["nights_min"] <= nights <= cfg["nights_max"]):
        return None
    if not (cfg["date_from"] <= d_from <= cfg["date_to"]):
        return None
    if o["transport"] == "car" and cfg["dogs"] and o.get("pets_allowed") is False:
        return None
    if o["transport"] == "flight" and o.get("departure") and \
            o["departure"] not in cfg["departures"] + cfg["departures_secondary"]:
        return None
    if o.get("board") not in BOARD_SCORE:
        o["board"] = norm_board(o.get("board"))
    cc = o.get("country_code") or norm_country(o.get("country")) or norm_country(o.get("region"))
    o["country_code"] = cc
    o["country"] = COUNTRY_NAMES.get(cc, o.get("country"))
    o["continent"] = continent(cc)
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
    o["price_exact"] = o.get("price_exact") is True
    # price_total is for the configured party; when it is extrapolated from a per-person price, say how.
    # fx_note: the price was converted from another currency (e.g. CZK at the ECB rate) – kept even for exact prices
    fx = o.pop("fx_note", None)
    note = None if o["price_exact"] else (o.get("price_note") or approx_note(cfg))
    o["price_note"] = "; ".join(x for x in (note, fx) if x) or None
    o["id"] = offer_id(source, o["hotel"], o["date_from"], nights, o["transport"], o["departure"])
    set_party(o, cfg)
    flag_cap(o, cfg)
    return o


def party_of(cfg):
    return cfg.get("party_id") or party_id(cfg["adults"], cfg["children_ages"])


def is_primary(cfg):
    """The default party (first of 'skupiny') keeps the offer ids it always had, so its price history goes on."""
    parties = cfg.get("parties")
    return not parties or party_of(cfg) == parties[0]["id"]


def set_party(o, cfg):
    """o["party"] = party id; offers of an extra party get '@<party id>' on their id (own price history)."""
    o["party"] = party_of(cfg)
    base = o["id"].split("@")[0]
    o["id"] = base if is_primary(cfg) else f"{base}@{o['party']}"


_TIMES = re.compile(r"× \d+")


def scale_offer(o, cfg, pcfg):
    """An approximated offer of the primary party (per-person price × party size) re-derived for another party:
    no extra request, the same per-person price × the other party's size. None when the price leaves the limit."""
    if o.get("price_exact"):
        return None
    n0, n1 = party_size(cfg), party_size(pcfg)
    s = dict(o)
    for k in ("price_total", "price_original"):
        if s.get(k):
            s[k] = round(s[k] * n1 / n0)
    if s.get("price_original") and s["price_original"] <= s["price_total"]:
        s["price_original"] = None
    for k in ("price_note", "discount_label"):
        if s.get(k):
            s[k] = _TIMES.sub(f"× {n1}", s[k])
    if not s.get("price_note"):
        s["price_note"] = approx_note(pcfg)
    set_party(s, pcfg)
    if not within_limit(s, pcfg):
        return None
    flag_cap(s, pcfg)
    return s


def flag_cap(o, cfg):
    """over_cap: a watched offer kept although it costs more than price_cap. Unwatched offers never carry it."""
    if o.get("watched") and o["price_total"] > cfg["price_cap"]:
        o["over_cap"] = True
    else:
        o.pop("over_cap", None)
    if not o.get("watched"):
        o.pop("watched", None)


def within_limit(o, cfg):
    return o["price_total"] <= (keep_limit(cfg) if o.get("watched") else cfg["price_cap"])


def score(o, cfg):
    budget = cfg["budget"]
    p = o["price_total"]
    price_s = 1.0 if p <= budget * 0.7 else max(0.0, 1 - (p - budget * 0.7) / (cfg["price_cap"] - budget * 0.7))
    board_s = BOARD_SCORE.get(o["board"], 0.2)
    if o["board"] in cfg["boards_preferred"]:
        board_s = max(board_s, 0.95)
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


def refine_exact(offers, mods, cfg, limit=None):
    """Ask adapters with an exact_price(offer, cfg) hook for the real total of the configured party for their best
    offers with a preferred board (top mod.EXACT_MAX by score). Offers the site doesn't confirm keep the
    per-person x party-size approximation."""
    for name, mod in mods.items():
        hook = getattr(mod, "exact_price", None)
        if not hook:
            continue
        todo = [o for o in offers if o["source"] == name and not o["price_exact"]
                and (o["board"] in cfg["boards_preferred"] or o.get("watched"))]
        # watched hotels first (any board), then the best-scoring ones
        todo = sorted(todo, key=lambda o: (not o.get("watched"), -score(o, cfg), o["price_total"]))
        todo = todo[:getattr(mod, "EXACT_MAX", 35) if limit is None else limit]
        if not todo:
            continue
        done = failed = 0
        for o in todo:
            try:
                res = hook(o, cfg)
            except Exception as e:
                failed += 1
                print(f"[{name}] exact price {o['hotel']}: {type(e).__name__} {str(e)[:120]}")
                if failed >= 5 and not done:
                    print(f"[{name}] exact prices: giving up after {failed} failures")
                    break
                continue
            if not res or not res.get("price_total"):
                continue
            o["price_approx"] = o["price_total"]
            o.update(res)
            o["price_total"], o["price_exact"], o["price_note"] = int(res["price_total"]), True, None
            po = o.get("price_original")
            o["price_original"] = int(po) if isinstance(po, (int, float)) and po > o["price_total"] else None
            o["discount_pct"] = round(100 * (1 - o["price_total"] / o["price_original"])) if o["price_original"] else None
            done += 1
        print(f"[{name}] exact {party_short(cfg)} prices: {done}/{len(todo)} confirmed")
    # an exact price above the cap no longer matches the criteria (watched hotels: above the wider limit)
    out = [o for o in offers if within_limit(o, cfg)]
    for o in out:
        flag_cap(o, cfg)
    return out


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def merge_history(offers, today, cfg=CONFIG):
    """Price history per offer id. Every party has its own ids (primary: the old ones, others '…@<party id>'), so
    each party has its own series; a series restarts when the party behind an id changes (nastavenia.yml)."""
    hist = load(HISTORY, {})
    prev_doc = load(OFFERS, {})
    prev_default = party_signature_of(prev_doc.get("criteria") or {})
    prev = {}
    for o in expand_offers(prev_doc.get("offers", [])):
        sig = signature_of_id(o["party"]) if o.get("party") else prev_default
        prev[o["id"]] = (o, sig)
    prev_price = {}
    for o in offers:
        party = signature_of_id(o["party"]) if o.get("party") else party_signature(cfg)
        h = hist.setdefault(o["id"], {"first_seen": today, "points": []})
        exact = bool(o.get("price_exact"))
        if bool(h.get("exact")) != exact or h.get("party", party) != party:
            # approximation <-> exact party price, or another party in nastavenia.yml: not a price change,
            # start a new series
            h["points"] = []
        else:
            p, sig = prev.get(o["id"], (None, None))
            if p and sig in (None, party) and bool(p.get("price_exact")) == exact:
                prev_price[o["id"]] = p["price_total"]
        h["exact"], h["party"] = exact, party
        pts = [p for p in h["points"] if p[0] != today] + [[today, o["price_total"]]]
        h["points"], h["last_seen"] = pts[-HISTORY_POINTS:], today
        o["first_seen"], o["last_seen"] = h["first_seen"], today
        o["price_history"] = h["points"]
        before = prev_price.get(o["id"]) or (pts[-2][1] if len(pts) > 1 else None)
        o["price_change"] = (o["price_total"] - before) if before is not None else None
    cutoff = date.fromisoformat(today).toordinal() - HISTORY_KEEP_DAYS
    return {k: v for k, v in hist.items() if date.fromisoformat(v.get("last_seen", today)).toordinal() >= cutoff}


def party_signature(cfg):
    return f"{cfg['adults']}|" + ",".join(str(a) for a in sorted(cfg["children_ages"]))


def signature_of_id(pid):
    """party_signature() of a party id ('a2-c10-12' -> '2|10,12', 'a2' -> '2|'); None when it isn't one."""
    m = re.fullmatch(r"a(\d+)(?:-c([\d-]+))?", str(pid or ""))
    if not m:
        return None
    return f"{m[1]}|" + ",".join(str(a) for a in sorted(int(x) for x in (m[2] or "").split("-") if x))


def party_signature_of(criteria):
    """Party of a previous offers.json, or None when it doesn't say."""
    if "adults" not in criteria or "children_ages" not in criteria:
        return None
    return party_signature(criteria)


def _timed_search(mod, cfg):
    """(raw offers, error text or None, seconds). Runs in a worker thread: one per agency, so every agency still
    gets one request at a time (polite) while the slow ones no longer add up."""
    t0 = time.time()
    try:
        return mod.search(cfg), None, time.time() - t0
    except Exception as e:
        traceback.print_exc()
        return None, f"{type(e).__name__}: {str(e)[:200]}", time.time() - t0


def watch_hints(offers, prev_offers, cfg):
    """{term: [{country_code, place, region}]}: where each watched hotel was seen – this run's offers first, then
    the previous offers.json (re-matched, so a term added to nastavenia.yml uses older data too)."""
    out = {t: [] for t in cfg.get("watched", [])}
    for o in list(offers) + list(prev_offers):
        term = match(o.get("hotel"), cfg.get("watched"))
        if not term:
            continue
        h = {"country_code": o.get("country_code"), "place": o.get("place"), "region": o.get("region")}
        if h["country_code"] and h not in out[term]:
            out[term].append(h)
    return out


def _timed_watch(name, mod, cfg, hints):
    t0 = time.time()
    try:
        return mod.watch(cfg, cfg["watched"], hints), None, time.time() - t0
    except Exception as e:
        print(f"[{name}] watch failed: {type(e).__name__} {str(e)[:200]}")
        return [], f"{type(e).__name__}: {str(e)[:200]}", time.time() - t0


def run_watch(mods, sources, offers, cfg, link_mods=None):
    """Second phase: adapters with a watch(cfg, terms, hints) hook look up the watched hotels directly (in
    parallel, one agency per thread as in phase 1). Returns {term: [deeplink dicts]} for the page: watch_links()
    of link_mods (default mods; run.py passes every adapter, link-only ones included)."""
    terms = cfg.get("watched") or []
    if not terms:
        return {}
    hints = watch_hints(offers.values(), expand_offers(load(OFFERS, {}).get("offers", [])), cfg)
    print("watched hotels seen at: " + "; ".join(
        f"{t}: " + (", ".join(f"{h['country_code']} {h['place'] or ''}/{h['region'] or ''}" for h in hs) or "nowhere yet")
        for t, hs in hints.items()))
    ok = {s["id"] for s in sources if s["status"] in ("ok", "empty")}
    todo = [(n, m) for n, m in mods.items() if n in ok and getattr(m, "watch", None)]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(len(todo), 1)) as pool:
        futures = [(n, m, pool.submit(_timed_watch, n, m, cfg, hints)) for n, m in todo]
        for name, mod, fut in futures:
            raw, err, secs = fut.result()
            info = next(s for s in sources if s["id"] == name)
            clean = [n for n in (normalise(r, name, mod.NAME, cfg) for r in raw or []) if n and n.get("watched")]
            new = 0
            for o in clean:
                if o["id"] not in offers:
                    new += 1
                if o["id"] not in offers or o["price_total"] < offers[o["id"]]["price_total"]:
                    offers[o["id"]] = o
            info["watch"] = {"found": len(clean), "new": new, "seconds": round(secs, 1), "error": err}
            if new and info["status"] == "empty":
                info["status"] = "ok"
            info["count"] = sum(o["source"] == name for o in offers.values())
            print(f"[{name}] watch: {len(raw or [])} raw, {len(clean)} watched offers, {new} not in the listings")
    print(f"watch lookups took {time.time() - t0:.0f} s")
    links = {}
    for t in terms:
        for name, mod in (link_mods or mods).items():
            fn = getattr(mod, "watch_links", None)
            if fn:
                try:
                    links.setdefault(t, []).extend(dict(d, source=name, name=mod.NAME)
                                                   for d in fn(cfg, t, hints.get(t, [])))
                except Exception as e:
                    print(f"[{name}] watch_links failed: {e}", file=sys.stderr)
    return links


def watched_summary(offers, links, cfg):
    """offers.json "watched": one entry per term with its offer count and term-specific search links."""
    primary = party_of(cfg)
    out = []
    for t in cfg.get("watched") or []:
        counts = {}
        for o in offers:
            if o.get("watched") == t:
                counts[o.get("party") or primary] = counts.get(o.get("party") or primary, 0) + 1
        out.append({"term": t, "count": counts.get(primary, 0), "counts": counts,
                    "links": [d for d in links.get(t, []) if https_or_none(d.get("url"))]})
    return out


def _timed_party(name, mod, cfg, primary):
    """Extra parties of one source: mod.search_party(party cfg, this source's primary offers) per party, in a
    worker thread (one agency per thread, one request at a time). -> ({party id: [normalised offers]}, log)."""
    out, log = {}, {}
    for party, pcfg in extra_parties(cfg):
        t0 = time.time()
        try:
            raw = mod.search_party(pcfg, primary)
            err = None
        except Exception as e:
            raw, err = [], f"{type(e).__name__}: {str(e)[:200]}"
            print(f"[{name}] party {party['id']} failed: {err}")
        clean = [n for n in (normalise(r, name, mod.NAME, pcfg) for r in raw or []) if n]
        out[party["id"]] = clean
        log[party["id"]] = {"raw": len(raw or []), "kept": len(clean), "seconds": round(time.time() - t0, 1),
                            "error": err}
        print(f"[{name}] party {party['id']} ({party['nazov']}): {len(raw or [])} raw, {len(clean)} kept, "
              f"{time.time() - t0:.0f} s")
    return out, log


def extra_party_offers(mods, sources, offers, cfg):
    """{party id: {offer id: offer}} for every extra party: exact passes of adapters with a search_party() hook (in
    parallel) + the primary party's approximated offers re-scaled to the party size (no request)."""
    extras = extra_parties(cfg)
    if not extras:
        return {}
    ok = {s["id"] for s in sources if s["status"] == "ok"}
    todo = [(n, m) for n, m in mods.items() if n in ok and getattr(m, "search_party", None)]
    by_party = {p["id"]: {} for p, _ in extras}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(len(todo), 1)) as pool:
        futures = [(n, pool.submit(_timed_party, n, m, cfg, [o for o in offers.values() if o["source"] == n]))
                   for n, m in todo]
        for name, fut in futures:
            got, log = fut.result()
            next(s for s in sources if s["id"] == name)["parties"] = log
            for pid, clean in got.items():
                for o in clean:
                    cur = by_party[pid].get(o["id"])
                    if not cur or o["price_total"] < cur["price_total"]:
                        by_party[pid][o["id"]] = o
    print(f"extra party passes took {time.time() - t0:.0f} s")
    for party, pcfg in extras:
        scaled = 0
        for o in offers.values():
            s = scale_offer(o, cfg, pcfg)
            if s and s["id"] not in by_party[party["id"]]:
                by_party[party["id"]][s["id"]] = s
                scaled += 1
        print(f"party {party['id']}: {len(by_party[party['id']]) - scaled} exact-pass offers, {scaled} re-scaled "
              f"approximations")
    return by_party


def fit_size(offers, cfg, limit=SIZE_LIMIT):
    """Compacted offers list; when its JSON is above limit, every extra party keeps only its best offers by score
    (watched hotels always stay). Returns (offers, cap or None)."""
    primary = party_of(cfg)
    rest = [o for o in offers if (o.get("party") or primary) != primary]
    out = compact_offers(offers)
    size = len(json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode())
    cap = None
    if size > limit and rest:
        per = {}
        for o in rest:
            per.setdefault(o["party"], []).append(o)
        cap = max(len(v) for v in per.values())
        while size > limit and cap > 50:
            cap = int(cap * 0.8)
            keep = set()
            for v in per.values():
                v = sorted(v, key=lambda o: (not o.get("watched"), -o.get("score", 0), o["price_total"]))
                keep |= {o["id"] for o in v[:cap]} | {o["id"] for o in v if o.get("watched")}
            out = compact_offers([o for o in offers if (o.get("party") or primary) == primary or o["id"] in keep])
            size = len(json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode())
        print(f"offers.json above {limit / 1e6:.0f} MB: extra parties capped to their best {cap} offers")
    return out, cap


def dump(out):
    """offers.json text: indented, but one offer per line (small diffs, ~20 % smaller than indent=1)."""
    head = json.dumps(dict(out, offers=["@OFFERS@"]), ensure_ascii=False, indent=1)
    rows = ",\n".join(json.dumps(o, ensure_ascii=False, separators=(",", ":")) for o in out["offers"])
    return head.replace('[\n  "@OFFERS@"\n ]', "[\n" + rows + "\n ]" if rows else "[]", 1)


def main(only=None):
    cfg = CONFIG
    sources, deeplinks, offers, mods, all_mods = [], [], {}, {}, {}
    todo = []
    for name in ADAPTERS:
        if only and name not in only:
            continue
        mod = all_mods[name] = importlib.import_module(f"adapters.{name}")
        info = {"id": name, "name": mod.NAME, "home": mod.HOME, "status": "ok", "count": 0, "error": None}
        try:
            deeplinks += [dict(d, source=name, name=mod.NAME) for d in mod.deeplinks(cfg)]
        except Exception as e:  # deeplinks are pure string building; a failure here is a bug
            print(f"[{name}] deeplinks failed: {e}", file=sys.stderr)
        if getattr(mod, "DEEPLINK_ONLY", False):
            info["status"] = "disabled"
            sources.append(info)
            continue
        mods[name] = mod
        todo.append((name, mod, info))
        sources.append(info)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(len(todo), 1)) as pool:
        futures = [(name, mod, info, pool.submit(_timed_search, mod, cfg)) for name, mod, info in todo]
        for name, mod, info, fut in futures:  # results in ADAPTERS order -> deterministic dedup
            raw, err, secs = fut.result()
            info["duration_s"] = round(secs, 1)
            if err:
                info["status"], info["error"] = "error", err
                continue
            clean = [n for n in (normalise(r, name, mod.NAME, cfg) for r in raw) if n]
            for o in clean:
                if o["id"] not in offers or o["price_total"] < offers[o["id"]]["price_total"]:
                    offers[o["id"]] = o
            info["count"] = len({o["id"] for o in clean})
            info["status"] = "ok" if clean else "empty"
            print(f"[{name}] {len(raw)} raw, {len(clean)} kept")
            log_drops(name, raw, cfg)
    print(f"scraping took {time.time() - t0:.0f} s")
    watch_links = run_watch(mods, sources, offers, cfg, all_mods)
    for info in sources:
        info.setdefault("counts", {})[party_of(cfg)] = info["count"]
    # extra parties (skupiny): before the exact-price refinement, so their re-scaled offers start from the
    # per-person approximations, not from the primary party's confirmed totals
    party_offers = extra_party_offers(mods, sources, offers, cfg)

    today = datetime.now(timezone.utc).date().isoformat()
    t0 = time.time()
    exact_src = {n: m for n, m in mods.items() if any(s["id"] == n and s["status"] == "ok" for s in sources)}
    result = refine_exact(list(offers.values()), exact_src, cfg)
    for party, pcfg in extra_parties(cfg):
        result += refine_exact(list(party_offers.get(party["id"], {}).values()), exact_src, pcfg, EXTRA_EXACT_MAX)
    print(f"exact prices took {time.time() - t0:.0f} s")
    result = sorted(result, key=lambda o: (-score(o, cfg), o["price_total"]))
    for o in result:
        o["score"] = score(o, cfg)
    for info in sources:
        for pid in [p["id"] for p in cfg["parties"]]:
            info["counts"][pid] = sum(o["source"] == info["id"] and o["party"] == pid for o in result)
    hist = merge_history(result, today, cfg)

    DATA.mkdir(parents=True, exist_ok=True)
    out = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "criteria": criteria_for_display(cfg),
        "sources": sources,
        "deeplinks": deeplinks,
        "offers": result,
        "watched": watched_summary(result, watch_links, cfg),
    }
    if only:
        print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
        return
    if not result and any(s["status"] == "ok" for s in load(OFFERS, {}).get("sources", [])):
        # Every scraper failed this run: keep yesterday's offers on the page instead of blanking it.
        prev = load(OFFERS, {})
        out["offers"] = expand_offers(prev.get("offers", []))
        for o in out["offers"]:  # older files predate these fields
            o.setdefault("continent", continent(o.get("country_code")))
            o.setdefault("price_note", None if o.get("price_exact") else approx_note(cfg))
            o.setdefault("party", party_of(cfg))
        out["stale"] = True
        out["watched"] = watched_summary(out["offers"], watch_links, cfg)
    out["offers"], cap = fit_size(out["offers"], cfg)
    if cap:
        out["party_cap"] = cap
    text = dump(out)
    OFFERS.write_text(text, encoding="utf-8")
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(out['offers'])} offers from {sum(s['status'] == 'ok' for s in sources)} sources "
          f"(party {party_short(cfg)}, {party_size(cfg)} persons), offers.json {len(text.encode()) / 1e6:.2f} MB")
    summary(expand_offers(out["offers"]), cfg)


def log_drops(name, raw, cfg):
    """Per-country raw offers vs. those above price_cap (why a destination may end up with no offers)."""
    from collections import Counter
    seen, over = Counter(), Counter()
    for r in raw:
        cc = r.get("country_code") or norm_country(r.get("country")) or "?"
        seen[cc] += 1
        try:
            if int(r.get("price_total")) > cfg["price_cap"]:
                over[cc] += 1
        except (TypeError, ValueError):
            pass
    print(f"[{name}] raw by country (over price_cap): "
          + ", ".join(f"{k} {v}" + (f" ({over[k]})" if over[k] else "") for k, v in seen.most_common()))


def summary(offers, cfg=CONFIG):
    """Counts by party x source (exact/approx), by continent and by source x country for the job log."""
    from collections import Counter
    for p in cfg.get("parties") or []:
        mine = [o for o in offers if (o.get("party") or cfg["party_id"]) == p["id"]]
        by = Counter((o["source"], "exact" if o.get("price_exact") else "approx") for o in mine)
        print(f"party {p['id']} ({p['nazov']}): {len(mine)} offers: "
              + ", ".join(f"{s} {k} {v}" for (s, k), v in sorted(by.items())))
    offers = [o for o in offers if (o.get("party") or party_of(cfg)) == party_of(cfg)]
    print("by continent: " + ", ".join(f"{k} {v}" for k, v in Counter(o["continent"] for o in offers).most_common()))
    by_src = {}
    for o in offers:
        by_src.setdefault(o["source"], Counter())[o["country_code"] or "?"] += 1
    for src, cnt in by_src.items():
        print(f"  {src}: " + ", ".join(f"{k} {v}" for k, v in cnt.most_common()))


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
