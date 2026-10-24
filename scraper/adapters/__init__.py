# Adapter modules run by run.py, in this order. Each module defines NAME, HOME, deeplinks(cfg) and
# search(cfg) -> list of offer dicts (see site/data/offers.json for the shape).
# A module with DEEPLINK_ONLY = True only contributes search links (see each module for why).
ADAPTERS = ["invia", "satur", "cedok", "tiptravel", "kartago", "fischer", "eximtours", "seneca", "koala", "firotour",
            "sorea", "blue_style"]
