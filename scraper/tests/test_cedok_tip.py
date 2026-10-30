from pathlib import Path

from adapters import cedok, tiptravel
from config import CONFIG
import run

FX = Path(__file__).parent / "fixtures"


def test_cedok_parse_page():
    rates, count, links = cedok.parse_page((FX / "cedok_turecko.html").read_text())
    assert (len(rates), count) == (3, 67) and set(links) == {"ATRAYT9O7C", "AYT2SUN", "AYT2ORE"}
    offers = [cedok.to_offer(r, links, CONFIG) for r in rates]
    assert offers[2] is None  # Orient Express is a round trip, not a stay
    o = offers[1]
    assert o["hotel"] == "Hotel Sunberk Side" and o["url"].startswith("https://www.cedok.sk/dovolena/turecko/")
    assert (o["country_code"], o["region"], o["board"], o["departure"]) == ("TR", "Turecká riviéra - Side", "AI", "BTS")
    assert (o["date_from"], o["date_to"], o["nights"], o["stars"], o["rating"]) == ("2027-07-02", "2027-07-09", 7, 3.0, 7.3)
    # 2 adults priced 1565 € together -> 782.5 € per person x 3
    assert (o["price_total"], o["price_original"]) == (2348, 2898)
    assert o["discount_label"] == "First Minute (cena za os. × 3, orientačne)"
    assert o["price_note"] == "orientačne: cena za osobu pri 2 dospelých × 3"
    kept = run.normalise(o, "cedok", "Čedok", CONFIG)
    assert kept and kept["price_total"] == 2348 and kept["discount_pct"] == 19
    # 3-night Gallion term is dropped by the 7–14 nights rule
    assert run.normalise(offers[0], "cedok", "Čedok", CONFIG) is None


def test_cedok_exact_party_price():
    rates, _, links = cedok.parse_page((FX / "cedok_turecko.html").read_text())
    r = dict(rates[1], price=210000, baseCatalogPrice=0, participants=[
        {"type": "adult", "price": 90000}, {"type": "child", "price": 60000}, {"type": "child", "price": 60000}])
    o = cedok.to_offer(r, links, CONFIG)
    assert (o["price_total"], o["price_original"], o["discount_label"]) == (2100, None, "First Minute")
    assert o["price_exact"] is True and run.normalise(o, "cedok", "Čedok", CONFIG)["price_note"] is None


def test_cedok_query_and_deeplinks():
    q = cedok._query(CONFIG, 2)
    assert q["dateFrom"] == "01.07.2027" and (q["durationMin"], q["durationMax"]) == (8, 15) and q["page"] == 2
    assert all(d["url"].startswith("https://www.cedok.sk/") for d in cedok.deeplinks(CONFIG))


def test_cedok_10_11_and_14_night_pages():
    # durationMin=11&durationMax=12 -> 10 and 11 night terms; 15/15 -> 14 nights
    rates, count, links = cedok.parse_page((FX / "cedok_grecko_11_12.html").read_text())
    offers = [cedok.to_offer(r, links, CONFIG) for r in rates]
    assert count == 42 and [o["nights"] for o in offers] == [10, 11, 10]
    o = offers[1]
    assert o["hotel"] == "Marianna Studios" and (o["date_from"], o["date_to"], o["departure"]) == ("2027-07-01", "2027-07-12", "VIE")
    assert o["price_total"] == 2428 and o["discount_label"] == "Cena za os. × 3 (orientačne)"
    assert all(run.normalise(o, "cedok", "Čedok", CONFIG) for o in offers)
    rates, count, links = cedok.parse_page((FX / "cedok_turecko_15.html").read_text())
    o = cedok.to_offer(rates[1], links, CONFIG)
    assert count == 65 and o["hotel"] == "Hotel Sunberk Side" and o["nights"] == 14
    assert (o["date_from"], o["date_to"], o["board"], o["price_total"], o["price_original"]) == (
        "2027-07-03", "2027-07-17", "AI", 3388, 4131)
    assert o["discount_label"] == "First Minute (cena za os. × 3, orientačne)"
    assert run.normalise(o, "cedok", "Čedok", CONFIG)["nights"] == 14


def test_cedok_search_queries_each_length(monkeypatch):
    calls = []
    html = (FX / "cedok_turecko_15.html").read_text()
    monkeypatch.setattr(cedok, "get", lambda url, params=None: calls.append(params) or html)
    cedok.search(CONFIG)
    days = [(p["durationMin"], p["durationMax"]) for p in calls]
    assert sorted(set(days)) == [(8, 10), (8, 15), (11, 12), (15, 15)]  # 8–15: one wide page per long-haul slug
    # 65 rates = 3 pages, capped per range; long-haul countries one page each
    near = sum(min(3, pages) for _, pages in cedok.DURATIONS) * len(cedok.DESTINATIONS)
    far = [c for c in calls if (c["durationMin"], c["durationMax"]) == (8, 15)]
    assert len(far) == len(cedok.FAR) and len(calls) == near + len(far)
    assert len(calls) + cedok.EXACT_MAX <= 85  # polite: ≤ ~80 requests per run
    # only countries listed in the settings are asked
    calls.clear()
    cedok.search(dict(CONFIG, countries={"TR": 1.0, "MV": 0.5}))
    assert {c.get("page", 1) for c in calls} == {1, 2} and len(calls) == 4 + 1


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


def test_cedok_long_haul_rates():
    # trimmed real rates (job log 2026-10-30): Maurícius (VIE) and SAE, priced for 2 adults -> per person x 3
    rates, count, links = cedok.parse_page((FX / "cedok_far.html").read_text())
    mu, ae = [cedok.to_offer(r, links, CONFIG) for r in rates]
    assert (mu["hotel"], mu["country_code"], mu["departure"], mu["board"]) == (
        "Hotel Hibiscus Beach Resort & Spa", "MU", "VIE", "HB")
    assert mu["price_total"] == round(3251 / 2 * 3) and mu["price_note"] == "orientačne: cena za osobu pri 2 dospelých × 3"
    k = run.normalise(mu, "cedok", "Čedok", CONFIG)
    assert k["continent"] == "Indický oceán" and k["country"] == "Maurícius" and not k["price_exact"]
    assert ae["country_code"] == "AE" and run.normalise(ae, "cedok", "Čedok", CONFIG)["continent"] == "Blízky východ"


def test_cedok_unknown_slug_tries_next_candidate(monkeypatch):
    calls = []
    far = (FX / "cedok_far.html").read_text()

    def fake_get(url, params=None):
        calls.append(url)
        return "<html></html>" if "/zanzibar/" in url else far  # 0 rates for the first candidate

    monkeypatch.setattr(cedok, "get", fake_get)
    cedok.search(dict(CONFIG, countries={"TZ": 0.6}))
    assert [u.split("/")[-2] for u in calls] == ["zanzibar", "tanzania"]
