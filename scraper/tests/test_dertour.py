import json
from pathlib import Path

from adapters import dertour, eximtours, fischer, kartago
from config import CONFIG
import run

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text())


def test_query_asks_for_the_real_party_and_criteria():
    q = dertour.query(CONFIG, (10, 14), "1|2", 50)
    assert (q["ac1"], q["kc1"], q["ka1"]) == (1, 2, "10|12")  # without ka1 the kids would be priced as infants
    assert (q["to"], q["dd"], q["rd"], q["m"], q["tt"]) == ("483|3789", "2027-07-01", "2027-08-31", 5, 1)
    assert q["nn"] == "10|11|12|13|14" and (q["d"], q["pitg"], q["pstg"]) == ("1|2", 50, 50)
    assert "d" not in dertour.query(CONFIG) and "pstg" not in dertour.query(CONFIG, None, "1")


def test_countries_keeps_preferred_ones_by_weight():
    got = dertour.countries(load("dertour_categories.json"), CONFIG)
    codes = [c[0] for c in got]
    europe = {"GR", "TR", "EG", "BG", "ES", "TN", "CY", "IT", "PT", "HR", "MT", "AL"}
    far = {"AE", "MV", "MX", "LK", "CV", "DO", "TZ", "TH", "OM"}  # real destination ids from the categories call
    assert set(codes) == europe | far
    assert codes[:4] == ["TR", "CY", "IT", "HR"]  # weight 1.0 first, bigger countries first
    tr = got[0]
    assert tr[1] == "Turecko" and tr[3] == 375 and tr[2].startswith("63260|")


def test_tour_to_offer_exact_party_price():
    tours = load("fischer_tours_turecko.json")["tours"]
    o = dertour.to_offer(tours[0], fischer.HOME, CONFIG)
    assert o["hotel"] == "Dosinia Luxury Resort" and o["url"].startswith("https://www.fischer.sk/turecko/")
    assert "KA1=10%7C12" in o["url"] and "AC1=1" in o["url"]  # the link opens the same 1+2 search
    assert (o["date_from"], o["date_to"], o["nights"], o["departure"]) == ("2027-08-23", "2027-08-30", 7, "BTS")
    assert (o["board"], o["country_code"], o["region"], o["stars"]) == ("UAI", "TR", "Turecká riviéra", 5.0)
    # 1024 (adult) + 1024 (child 12) + 369 (child 10) = 2417, discount 1020
    assert (o["price_total"], o["price_original"], o["price_exact"]) == (2417, 3437, True)
    kept = run.normalise(o, "fischer", "Fischer", CONFIG)
    assert kept and kept["price_exact"] is True and kept["discount_pct"] == 30
    o = dertour.to_offer(tours[1], fischer.HOME, CONFIG)
    assert (o["hotel"], o["board"], o["price_total"]) == ("Sentido Lycus Beach", "AI", 2332)


def test_other_party_falls_back_to_approximation():
    t = load("fischer_tours_turecko.json")["tours"][0]
    t["tour"]["rooms"][0]["children"][0]["age"] = 0  # e.g. kids priced as infants
    o = dertour.to_offer(t, fischer.HOME, CONFIG)
    assert "price_exact" not in o and o["price_total"] == 1024 * 3 and o["price_original"] is None
    assert o["discount_label"] == "Cena za os. × 3 (orientačne)"


def test_brand_split_between_kartago_and_fischer():
    tours = load("fischer_tours_turecko.json")["tours"]
    assert [dertour._mine(t, True) for t in tours] == [True, True, True, False, False]
    assert [dertour._mine(t, False) for t in tours] == [False, False, False, True, True]


def test_search_pages_and_budget(monkeypatch):
    cats, tours = load("dertour_categories.json"), load("fischer_tours_turecko.json")
    calls = []

    def fake_get(url, params=None, headers=None, as_json=False, **kw):
        assert url == "https://www.kartago.sk/api/searchapi/getsearchresult" and as_json
        calls.append(params)
        return cats if "d" not in params else dict(tours, toursCount=len(tours["tours"]))

    monkeypatch.setattr(dertour, "get", fake_get)
    offers = kartago.search(CONFIG)
    assert len(calls) <= 1 + dertour.MAX_CALLS
    assert {o["hotel"] for o in offers} == {"Monachus Hotel & Spa", "Kilikya Palace"}  # non-FISCHER products
    assert all(o["price_exact"] and o["url"].startswith("https://www.kartago.sk/") for o in offers)
    assert {c.get("nn") for c in calls[1:]} == {"7|8|9|10|11|12|13|14", "10|11|12|13|14"}


def test_deeplinks_and_exim_redirect():
    for mod in (kartago, fischer):
        (d,) = mod.deeplinks(CONFIG)
        assert d["url"].startswith(mod.HOME + mod.PATH + "?") and "ka1=10%7C12" in d["url"]
    assert eximtours.DEEPLINK_ONLY and eximtours.search(CONFIG) == []
    assert eximtours.deeplinks(CONFIG)[0]["url"].startswith("https://www.kartago.sk/")


def test_long_haul_countries_get_their_first_page_within_budget(monkeypatch):
    cats, tours = load("dertour_categories.json"), load("fischer_tours_turecko.json")
    calls = []

    def fake_get(url, params=None, headers=None, as_json=False, **kw):
        calls.append(params)
        return cats if "d" not in params else dict(tours, toursCount=500)  # always "more pages"

    monkeypatch.setattr(dertour, "get", fake_get)
    fischer.search(CONFIG)
    asked = {c["d"] for c in calls[1:]}
    assert len(calls) == 1 + dertour.MAX_CALLS
    for dest in ("220441", "64077", "63862|63863|63864|63865|63866"):  # Maldivy, Srí Lanka, Dominikánska rep.
        assert dest in asked
    # round 1 = every country once, before any second page
    first = [c["d"] for c in calls[1:22]]
    assert len(set(first)) == 21 and all("pstg" not in c for c in calls[1:22])
