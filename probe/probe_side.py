"""TEMPORARY probe #4 (deleted after use): structure of BILLA /Hotels/Angebote.html (Nur Hotel)."""
import re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scraper"))
from common import get
q = {"bdid": "ib", "na": 2, "nc": 0, "dpfebl": "tr,dd,da", "pttid": "PH", "ptoj": "PH", "pdf": "3380096",
     "pdcoom": "o,c,h", "pdacf": "au", "dft": "apx", "psdf": "2027-07-01", "pedf": "2027-08-31",
     "pnnfl": 7, "pnnfh": 7, "pna": 2, "pnc": 0, "ps": "pr", "pdm": "pp", "idvfmb": 1, "pbtf": "ai"}
for path in ("/Hotels/Angebote.html", "/Hotel/Angebote.html", "/Hotels/Tuerkei.html"):
    try:
        h = get("https://www.billareisen.at" + path, params=q)
    except Exception as e:
        print(path, "ERROR", str(e)[:150]); continue
    print("=====", path, len(h), re.findall(r"<title>([^<]*)", h)[:1])
    cls = Counter(c for m in re.findall(r'class="([^"]+)"', h) for c in m.split() if re.search(r"product|hotel|offer|result|teaser|price", c, re.I))
    print("  classes:", cls.most_common(40))
    print("  scripts json:", re.findall(r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>', h)[:5], "ajax:", sorted(set(re.findall(r'["\'](/[A-Za-z/_-]*(?:ajax|api|json|Ajax|Api)[^"\']{0,80})', h)))[:15])
    print("  'Nur Hotel' count:", h.count("Nur Hotel"), "'p.P.':", h.count("p.P."), "Seite:", re.findall(r"Seite \d+ von \d+", h)[:2], "Side:", h.count("Side"))
    for k in ("Nur Hotel", "p.P."):
        i = h.find(k)
        if i > 0:
            print(f"  ctx {k}:", re.sub(r"\s+", " ", h[i - 700:i + 300])[:1000])
