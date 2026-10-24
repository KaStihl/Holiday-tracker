from pathlib import Path

from adapters import cedok, tiptravel
from config import CONFIG
import run

FX = Path(__file__).parent / "fixtures"


def test_cedok_parse_page():
    rates, count, links = cedok.parse_page((FX / "cedok_turecko.html").read_text())
    assert (len(rates), count) == (3, 67) and set(links) == {"ATRAYT9O7C", "AYT2SUN", "AYT2ORE"}
    offers = [cedok.to_offer(r, links, 3) for r in rates]
    assert offers[2] is None  # Orient Express is a round trip, not a stay
    o = offers[1]
    assert o["hotel"] == "Hotel Sunberk Side" and o["url"].startswith("https://www.cedok.sk/dovolena/turecko/")
    assert (o["country_code"], o["region"], o["board"], o["departure"]) == ("TR", "Turecká riviéra - Side", "AI", "BTS")
    assert (o["date_from"], o["date_to"], o["nights"], o["stars"], o["rating"]) == ("2027-07-02", "2027-07-09", 7, 3.0, 7.3)
    # 2 adults priced 1565 € together -> 782.5 € per person x 3
    assert (o["price_total"], o["price_original"]) == (2348, 2898)
    assert o["discount_label"] == "First Minute (cena za os. × 3, orientačne)"
    kept = run.normalise(o, "cedok", "Čedok", CONFIG)
    assert kept and kept["price_total"] == 2348 and kept["discount_pct"] == 19
    # 3-night Gallion term is dropped by the 7–14 nights rule
    assert run.normalise(offers[0], "cedok", "Čedok", CONFIG) is None


def test_cedok_exact_party_price():
    rates, _, links = cedok.parse_page((FX / "cedok_turecko.html").read_text())
    r = dict(rates[1], price=210000, baseCatalogPrice=0, participants=[
        {"type": "adult", "price": 90000}, {"type": "child", "price": 60000}, {"type": "child", "price": 60000}])
    o = cedok.to_offer(r, links, 3)
    assert (o["price_total"], o["price_original"], o["discount_label"]) == (2100, None, "First Minute")


def test_cedok_query_and_deeplinks():
    q = cedok._query(CONFIG, 2)
    assert q["dateFrom"] == "01.07.2027" and (q["durationMin"], q["durationMax"]) == (8, 15) and q["page"] == 2
    assert all(d["url"].startswith("https://www.cedok.sk/") for d in cedok.deeplinks(CONFIG))


def test_cedok_search_reports_total_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("403 blocked")
    monkeypatch.setattr(cedok, "get", boom)
    try:
        cedok.search(CONFIG)
    except RuntimeError as e:
        assert "403 blocked" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


def test_tip_search_json():
    resp = tiptravel.parse_response((FX / "tiptravel_search.js").read_text())
    assert resp["itemsCount"] == 1
    o = tiptravel.to_offer(resp["items"][0], tiptravel.HOME, 3, "BTS")
    assert o["hotel"] == "Barceló Playa Blanca" and o["country_code"] == "ES" and o["board"] == "UAI"
    assert (o["date_from"], o["nights"], o["departure"]) == ("2026-11-02", 7, "BTS")
    assert (o["price_total"], o["price_original"]) == (2061 * 3, 3020 * 3)
    assert o["image"].startswith("https://tiptravel.sk/FileHandler.ashx")
    assert run.normalise(o, "tiptravel", "TIP travel", CONFIG) is None  # November: outside Jul–Aug
    jul = dict(o, date_from="2027-07-05", date_to="2027-07-12")
    assert run.normalise(jul, "tiptravel", "TIP travel", CONFIG) is None  # 6183 € is over the 4500 € cap
    assert run.normalise(dict(jul, price_total=2900), "tiptravel", "TIP travel", CONFIG)["nights"] == 7


def test_tip_empty_response():
    assert tiptravel.parse_response("no wrapper") == {"items": [], "itemsCount": 0}


def test_tip_real_empty_summer_response():
    resp = tiptravel.parse_response((FX / "tiptravel_search_summer_empty.js").read_text())
    assert resp["itemsCount"] == 0 and resp["items"] == []
