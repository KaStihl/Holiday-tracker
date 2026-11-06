"""Bundle site/ + site/data/offers.json (+ side.json, tab "Side – hotely pri pláži") into one self-contained dovolenka.html (opens offline by double-click).

    python scraper/build_html.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = ROOT / "dovolenka.html"


def build(site=SITE, out=OUT):
    html = (site / "index.html").read_text(encoding="utf-8")
    css = (site / "style.css").read_text(encoding="utf-8")
    js = (site / "app.js").read_text(encoding="utf-8")
    side_js = (site / "side.js").read_text(encoding="utf-8")
    data = json.loads((site / "data" / "offers.json").read_text(encoding="utf-8"))
    try:  # tab "Side – hotely pri pláži" (scraper/side.py); without it the tab says there is no data yet
        side = json.loads((site / "data" / "side.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        side = None
    # "</" would end the <script> element early; JSON allows it escaped.
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    side_blob = json.dumps(side, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace('<link rel="stylesheet" href="style.css">', f"<style>\n{css}\n</style>")
    html = html.replace('<link rel="icon" href="/favicon-32x32.png" sizes="32x32">\n', "")
    html = html.replace(
        '<script src="app.js" defer></script>',
        f'<script id="offers-data" type="application/json">{blob}</script>\n<script>\n{js}\n</script>',
    )
    html = html.replace(
        '<script src="side.js" defer></script>',
        f'<script id="side-data" type="application/json">{side_blob}</script>\n<script>\n{side_js}\n</script>',
    )
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    print(f"wrote {build()}")
