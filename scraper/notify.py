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


def row(o, extra=""):
    where = ", ".join(x for x in (o.get("place"), o.get("country")) if x)
    how = "✈️ " + (o.get("departure") or "") if o["transport"] == "flight" else "🚗 autom" + (" 🐕" if o.get("pets_allowed") else "")
    return (f"| **{o['price_total']} €**{extra} | [{o['hotel']}]({o['url']}) | {where} | "
            f"{o['date_from']} · {o['nights']} nocí | {o.get('board') or '?'} | {how} | {o['source_name']} |")


def digest(prev, cur, budget):
    """Returns (title, markdown) or None when nothing is worth sending."""
    old = {o["id"]: o for o in prev.get("offers", [])}
    offers = cur.get("offers", [])
    first_run = not old
    new = [o for o in offers if o["id"] not in old and o.get("board") in ("AI", "UAI") and o["price_total"] <= budget]
    drops = [o for o in offers if o["id"] in old and o["price_total"] <= budget * 1.1
             and old[o["id"]]["price_total"] - o["price_total"] >= DROP_EUR]
    if not new and not drops:
        return None
    new.sort(key=lambda o: (-o.get("score", 0), o["price_total"]))
    drops.sort(key=lambda o: o["price_total"] - old[o["id"]]["price_total"])
    head = "| Cena | Hotel | Kde | Termín | Strava | Doprava | Zdroj |\n|---|---|---|---|---|---|---|"
    parts = []
    if drops:
        parts += [f"## 📉 Zlacnené o {DROP_EUR} € a viac ({len(drops)})", head]
        parts += [row(o, f" (−{old[o['id']]['price_total'] - o['price_total']} €)") for o in drops[:MAX_ROWS]]
    if new:
        label = "Najlepšie ponuky All Inclusive do budgetu" if first_run else "Nové ponuky All Inclusive do budgetu"
        parts += [f"## 🆕 {label} ({len(new)})", head] + [row(o) for o in new[:MAX_ROWS]]
    parts += ["", f"Ceny sú za 1 dospelého + 2 deti; pri označení „orientačne“ ide o cenu za osobu × 3 – overte u cestovky.",
              f"Všetky ponuky: stiahnite si dovolenka.html (tlačidlo „Download raw file“) a otvorte ho v prehliadači – {SITE}"]
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
