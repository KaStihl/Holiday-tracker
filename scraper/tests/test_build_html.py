import json
import shutil
from pathlib import Path

import build_html

SITE = Path(__file__).resolve().parents[2] / "site"


def test_bundle_is_self_contained(tmp_path):
    site = tmp_path / "site"
    shutil.copytree(SITE, site)
    (site / "data" / "offers.json").write_text(json.dumps({"offers": [{"hotel": "</script><b>x"}]}))
    html = build_html.build(site, tmp_path / "out.html").read_text(encoding="utf-8")
    assert 'href="style.css"' not in html and 'src="app.js"' not in html
    assert '<script id="offers-data"' in html
    assert "</script><b>" not in html and "<\\/script><b>x" in html
