"""Build an e-mail digest of what changed since the previous run.

    python scraper/notify.py PREVIOUS_offers.json site/data/offers.json OUT.md

Writes OUT.md (Markdown, Slovak) only when there is something worth an e-mail:
new All Inclusive offers within budget, or price drops of at least DROP_EUR on offers near budget.
The workflow turns OUT.md into a GitHub issue (GitHub e-mails the repo owner) and, if SMTP secrets
are set, also sends it as a plain e-mail.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import CONFIG  # noqa: E402

DROP_EUR = 50
MAX_ROWS = 15
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
    """Returns (title, markdown) or None when nothing is worth sending."""
    old = {o["id"]: o for o in prev.get("offers", [])}
    offers = cur.get("offers", [])
    first_run = not old
    new = [o for o in offers if o["id"] not in old and o.get("board") in ("AI", "UAI") and o["price_total"] <= budget]
    # a switch between the x3 approximation and the exact party price is not a price drop
    drops = [o for o in offers if o["id"] in old and o["price_total"] <= budget * 1.1
             and bool(o.get("price_exact")) == bool(old[o["id"]].get("price_exact"))
             and old[o["id"]]["price_total"] - o["price_total"] >= DROP_EUR]
    if not new and not drops:
        return None
    new.sort(key=lambda o: (-o.get("score", 0), o["price_total"]))
    drops.sort(key=lambda o: o["price_total"] - old[o["id"]]["price_total"])
    parts = []
    if drops:
        parts += [f"### 📉 Zlacnené o {DROP_EUR} € a viac ({len(drops)})", ""]
        parts += [row(o, f" (−{eur(old[o['id']]['price_total'] - o['price_total'])})") for o in drops[:MAX_ROWS]]
    if new:
        label = "Najlepšie ponuky All Inclusive do budgetu" if first_run else "Nové ponuky All Inclusive do budgetu"
        parts += ["", f"### 🆕 {label} ({len(new)})", ""] + [row(o) for o in new[:MAX_ROWS]]
    if max(len(new), len(drops)) > MAX_ROWS:
        parts += ["", f"…a ďalšie – všetky sú v dovolenka.html."]
    shown = drops[:MAX_ROWS] + new[:MAX_ROWS]
    n_exact = sum(bool(o.get("price_exact")) for o in shown)
    exact_src = sorted({o["source_name"] for o in offers if o.get("price_exact")})
    if n_exact:
        note = (f"Ceny sú za 1 dospelého + 2 deti. ✓ = presná cena 1+2 priamo od cestovky ({n_exact} z {len(shown)} "
                f"vyššie; {', '.join(exact_src)}). Ostatné sú orientačne cena za osobu pri 2 dospelých × 3 – "
                "pred rezerváciou overte u cestovky.")
    else:
        note = ("Ceny sú za 1 dospelého + 2 deti. Satur, Čedok a TIP uvádzajú len cenu za osobu pri 2 dospelých, "
                "preto je to orientačne cena × 3 – pred rezerváciou overte u cestovky.")
    parts += ["", "---", note,
              "", f"📄 Všetky ponuky: [dovolenka.html]({SITE}) – stiahnite (Download raw file) a otvorte v prehliadači."]
    bits = ([f"{len(drops)}× zlacnenie"] if drops else []) + ([f"{len(new)}× nová AI do {budget} €"] if new else [])
    title = ("Dovolenka: prvý prehľad – " if first_run else "Dovolenka: ") + ", ".join(bits)
    return title, "\n".join(parts)


def main(prev_path, cur_path, out_path):
    res = digest(load(prev_path), load(cur_path), CONFIG["budget"])
    if not res:
        print("nothing to notify")
        return
    title, body = res
    Path(out_path).write_text(title + "\n" + body + "\n", encoding="utf-8")
    print(title)


if __name__ == "__main__":
    main(*sys.argv[1:4])
