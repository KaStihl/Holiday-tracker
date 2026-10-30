"""Build the weekly e-mail digest: best offers now + what changed since the last digest.

    python scraper/notify.py site/data/digest_snapshot.json site/data/offers.json OUT.md [YYYY-MM-DD]

Writes OUT.md (first line = title, then Markdown, Slovak) and refreshes the snapshot, so next week's
digest compares against this one. The workflow runs it once a week (Monday morning) and turns OUT.md
into a GitHub issue (GitHub e-mails the repo owner) and, if SMTP secrets are set, a plain e-mail.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import CONFIG, party_label, party_short, party_size  # noqa: E402
from watch import match  # noqa: E402

DROP_EUR = 50
MAX_ROWS = 10
TOP = 10
SITE = "https://github.com/KaStihl/Holiday-tracker/blob/main/dovolenka.html"


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


BOARD = {"UAI": "Ultra All Inclusive", "AI": "All Inclusive", "FB": "plná penzia", "HB": "polpenzia",
         "BB": "raňajky", "RO": "bez stravy"}


def eur(n):
    return f"{n:,}".replace(",", "\u00a0") + "\u00a0€"


def row(o, extra=""):
    """One offer as a two-line card: tables with 7 columns are unreadable in phone mail apps."""
    where = ", ".join(x for x in (o.get("place"), o.get("country")) if x)
    y, m, d = o["date_from"].split("-")
    how = f"✈️ {o.get('departure') or ''}".strip() if o["transport"] == "flight" else "🚗 autom" + (" 🐕" if o.get("pets_allowed") else "")
    stars = " " + "★" * int(o["stars"]) if o.get("stars") else ""
    exact = " ✓" if o.get("price_exact") else ""
    return (f"- **{eur(o['price_total'])}**{exact}{extra} · [{o['hotel']}]({o['url']}){stars}  \n"
            f"  {where} · {int(d)}.\u00a0{int(m)}.\u00a0{y} · {o['nights']}\u00a0nocí · "
            f"{BOARD.get(o.get('board'), '?')} · {how} · {o['source_name']}")


def boards_title(boards):
    if set(boards) <= {"AI", "UAI"}:
        return "All Inclusive"
    return " / ".join(BOARD.get(b, b) for b in boards)


def watched_best(offers, cfg=CONFIG):
    """{term: cheapest current offer} for every watched hotel (any board, also above price_cap); None = no offer."""
    best = {t: None for t in cfg.get("watched") or []}
    for o in offers:
        t = o.get("watched") if o.get("watched") in best else match(o.get("hotel"), cfg.get("watched"))
        if t and (best[t] is None or o["price_total"] < best[t]["price_total"]):
            best[t] = o
    return best


def watched_section(prev, offers, cfg=CONFIG):
    """'⭐ Sledované hotely' lines: cheapest offer per watched term and its change since the previous digest."""
    terms = cfg.get("watched") or []
    if not terms:
        return []
    old = prev.get("watched") or {}
    parts = ["### ⭐ Sledované hotely", ""]
    for t, o in watched_best(offers, cfg).items():
        if o is None:
            parts.append(f"- **{t}**: zatiaľ bez ponuky" + (" (minulý týždeň bola)" if old.get(t) else ""))
            continue
        was = old.get(t)
        if not was:
            change = " · 🆕 nová" if prev.get("offers") else ""
        elif bool(was.get("price_exact")) != bool(o.get("price_exact")):
            change = f" · minule {eur(was['price_total'])} (iný typ ceny)"
        else:
            d = o["price_total"] - was["price_total"]
            change = (f" · 📉 −{eur(-d)}" if d < 0 else f" · 📈 +{eur(d)}" if d > 0 else " · bez zmeny")
        cap = " · ⚠ nad strop" if o["price_total"] > cfg["price_cap"] else ""
        parts.append(f"- **{t}**{change}{cap}")
        parts.append(row(o).replace("- ", "  ", 1))
    return parts + [""]


def digest(prev, cur, budget, cfg=CONFIG):
    """Returns (title, markdown). prev is the snapshot of the previous digest ({} on the first one)."""
    old = {o["id"]: o for o in prev.get("offers", [])}
    offers = cur.get("offers", [])
    first_run = not old
    ai = [o for o in offers if o.get("board") in cfg["boards_preferred"] and o["price_total"] <= budget]
    new = [] if first_run else [o for o in ai if o["id"] not in old]
    # a switch between the per-person approximation and the exact party price is not a price drop
    drops = [o for o in offers if o["id"] in old and o["price_total"] <= budget * 1.1
             and bool(o.get("price_exact")) == bool(old[o["id"]].get("price_exact"))
             and old[o["id"]]["price_total"] - o["price_total"] >= DROP_EUR]
    top = sorted(ai, key=lambda o: (-o.get("score", 0), o["price_total"]))[:TOP]
    new.sort(key=lambda o: (-o.get("score", 0), o["price_total"]))
    drops.sort(key=lambda o: o["price_total"] - old[o["id"]]["price_total"])

    parts = watched_section(prev, offers, cfg)
    parts += [f"### ⭐ Top {len(top)} ponúk {boards_title(cfg['boards_preferred'])} do {eur(budget)} ({len(ai)} spolu)", ""]
    parts += [row(o) for o in top] or ["Zatiaľ žiadna."]
    if drops:
        parts += ["", f"### 📉 Zlacnené za týždeň o {DROP_EUR} € a viac ({len(drops)})", ""]
        parts += [row(o, f" (−{eur(old[o['id']]['price_total'] - o['price_total'])})") for o in drops[:MAX_ROWS]]
    if new:
        parts += ["", f"### 🆕 Nové za týždeň ({len(new)})", ""] + [row(o) for o in new[:MAX_ROWS]]
    if not first_run and not drops and not new:
        parts += ["", "Za týždeň nepribudlo nič nové do budgetu a nič výrazne nezlacnelo."]
    if max(len(new), len(drops)) > MAX_ROWS:
        parts += ["", "…a ďalšie – všetky sú v dovolenka.html."]

    shown = top + drops[:MAX_ROWS] + new[:MAX_ROWS]
    exact_src = sorted({o["source_name"] for o in shown if o.get("price_exact")})
    who, n, short = party_label(cfg, "gen"), party_size(cfg), party_short(cfg)
    if exact_src:
        note = (f"Ceny sú za {who}. ✓ = presná cena {short} priamo od cestovky ({', '.join(exact_src)}). "
                f"Ostatné sú orientačne cena za osobu pri 2 dospelých × {n} – pred rezerváciou overte u cestovky.")
    else:
        note = (f"Ceny sú za {who}, orientačne cena za osobu pri 2 dospelých × {n} – "
                "pred rezerváciou overte u cestovky.")
    parts += ["", "---", note,
              "", f"📄 Všetky ponuky: [dovolenka.html]({SITE}) – stiahnite (Download raw file) a otvorte v prehliadači."]

    bits = [f"od {eur(min(o['price_total'] for o in ai))}"] if ai else ["bez ponúk do budgetu"]
    bits += ([f"{len(new)}× nová"] if new else []) + ([f"{len(drops)}× zlacnenie"] if drops else [])
    return "Dovolenka – týždenný prehľad: " + ", ".join(bits), "\n".join(parts)


def snapshot(cur, sent=None, cfg=CONFIG):
    """Only what next week's comparison needs, to keep the committed file small."""
    keep = ("id", "price_total", "price_exact")
    best = {t: {k: o.get(k) for k in keep} for t, o in watched_best(cur.get("offers", []), cfg).items() if o}
    return {"generated_at": cur.get("generated_at"), "sent": sent,
            "offers": [{k: o.get(k) for k in keep} for o in cur.get("offers", [])], "watched": best}


def main(snap_path, cur_path, out_path, sent=None):
    cur = load(cur_path)
    title, body = digest(load(snap_path), cur, CONFIG["budget"])
    Path(out_path).write_text(title + "\n" + body + "\n", encoding="utf-8")
    Path(snap_path).write_text(json.dumps(snapshot(cur, sent), separators=(",", ":")), encoding="utf-8")
    print(title)


if __name__ == "__main__":
    main(*sys.argv[1:5])
