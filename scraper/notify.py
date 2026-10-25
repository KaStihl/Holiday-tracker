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

from config import CONFIG  # noqa: E402

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


def digest(prev, cur, budget):
    """Returns (title, markdown). prev is the snapshot of the previous digest ({} on the first one)."""
    old = {o["id"]: o for o in prev.get("offers", [])}
    offers = cur.get("offers", [])
    first_run = not old
    ai = [o for o in offers if o.get("board") in ("AI", "UAI") and o["price_total"] <= budget]
    new = [] if first_run else [o for o in ai if o["id"] not in old]
    # a switch between the x3 approximation and the exact party price is not a price drop
    drops = [o for o in offers if o["id"] in old and o["price_total"] <= budget * 1.1
             and bool(o.get("price_exact")) == bool(old[o["id"]].get("price_exact"))
             and old[o["id"]]["price_total"] - o["price_total"] >= DROP_EUR]
    top = sorted(ai, key=lambda o: (-o.get("score", 0), o["price_total"]))[:TOP]
    new.sort(key=lambda o: (-o.get("score", 0), o["price_total"]))
    drops.sort(key=lambda o: o["price_total"] - old[o["id"]]["price_total"])

    parts = [f"### ⭐ Top {len(top)} ponúk All Inclusive do {eur(budget)} ({len(ai)} spolu)", ""]
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
    if exact_src:
        note = (f"Ceny sú za 1 dospelého + 2 deti. ✓ = presná cena 1+2 priamo od cestovky ({', '.join(exact_src)}). "
                "Ostatné sú orientačne cena za osobu pri 2 dospelých × 3 – pred rezerváciou overte u cestovky.")
    else:
        note = ("Ceny sú za 1 dospelého + 2 deti, orientačne cena za osobu pri 2 dospelých × 3 – "
                "pred rezerváciou overte u cestovky.")
    parts += ["", "---", note,
              "", f"📄 Všetky ponuky: [dovolenka.html]({SITE}) – stiahnite (Download raw file) a otvorte v prehliadači."]

    bits = [f"od {eur(min(o['price_total'] for o in ai))}"] if ai else ["bez ponúk do budgetu"]
    bits += ([f"{len(new)}× nová"] if new else []) + ([f"{len(drops)}× zlacnenie"] if drops else [])
    return "Dovolenka – týždenný prehľad: " + ", ".join(bits), "\n".join(parts)


def snapshot(cur, sent=None):
    """Only what next week's comparison needs, to keep the committed file small."""
    keep = ("id", "price_total", "price_exact")
    return {"generated_at": cur.get("generated_at"), "sent": sent,
            "offers": [{k: o.get(k) for k in keep} for o in cur.get("offers", [])]}


def main(snap_path, cur_path, out_path, sent=None):
    cur = load(cur_path)
    title, body = digest(load(snap_path), cur, CONFIG["budget"])
    Path(out_path).write_text(title + "\n" + body + "\n", encoding="utf-8")
    Path(snap_path).write_text(json.dumps(snapshot(cur, sent), separators=(",", ":")), encoding="utf-8")
    print(title)


if __name__ == "__main__":
    main(*sys.argv[1:5])
