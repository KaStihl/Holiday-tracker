# Adapter modules run by run.py, in this order. Each module defines NAME, HOME, deeplinks(cfg) and
# search(cfg) -> list of offer dicts (see site/data/offers.json for the shape).
# A module with DEEPLINK_ONLY = True only contributes search links (see each module for why).
ADAPTERS = ["invia", "satur", "cedok", "tiptravel", "kartago", "fischer", "eximtours", "seneca", "koala", "firotour",
            "sorea", "blue_style",
            # added 2026-10-30: Austrian package sellers (from VIE) and airstop.sk; link-only ones say why in their docstring
            "ruefa", "billa_reisen", "tui_at", "hofer_reisen", "lidl_reisen", "ab_in_den_urlaub", "weg_de",
            "holidaycheck", "check24", "urlaubsguru", "gruber_reisen", "airstop"]
