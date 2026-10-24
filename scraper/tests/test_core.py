from datetime import date

import run
from common import norm_board, norm_country, parse_price
from config import CONFIG


def test_parse_price():
    assert parse_price("2 780 €") == 2780
    assert parse_price("2.780,00 EUR") == 2780
    assert parse_price("1,234.60") == 1235
    assert parse_price(999.4) == 999
    assert parse_price("") is None


def test_norm_board():
    assert norm_board("Ultra All Inclusive") == "UAI"
    assert norm_board("All inclusive") == "AI"
    assert norm_board("Polpenzia") == "HB"
    assert norm_board("Raňajky") == "BB"
    assert norm_board(None) is None


def test_norm_country():
    assert norm_country("Turecko") == "TR"
    assert norm_country("Kanárske ostrovy - Tenerife") == "ES"
    assert norm_country("Chorvátsko") == "HR"
    assert norm_country("Neznámo") is None


def _raw(**kw):
    o = {"hotel": "H", "country": "Turecko", "board": "All Inclusive", "transport": "flight",
         "departure": "BTS", "date_from": "2027-07-10", "nights": 7, "price_total": 2500,
         "url": "https://example.com/x"}
    o.update(kw)
    return o


def test_normalise_filters():
    n = run.normalise(_raw(), "t", "T", CONFIG)
    assert n["board"] == "AI" and n["country_code"] == "TR" and n["date_to"] == "2027-07-17"
    assert run.normalise(_raw(nights=5), "t", "T", CONFIG) is None
    assert run.normalise(_raw(date_from="2027-06-20"), "t", "T", CONFIG) is None
    assert run.normalise(_raw(price_total=9000), "t", "T", CONFIG) is None
    assert run.normalise(_raw(url="http://insecure"), "t", "T", CONFIG) is None
    assert run.normalise(_raw(transport="car", pets_allowed=False), "t", "T", CONFIG) is None


def test_discount_and_score():
    n = run.normalise(_raw(price_original=3000), "t", "T", CONFIG)
    assert n["discount_pct"] == 17
    cheap_ai = run.score(n, CONFIG)
    pricey_bb = run.score(run.normalise(_raw(price_total=4200, board="Raňajky"), "t", "T", CONFIG), CONFIG)
    assert 0 <= pricey_bb < cheap_ai <= 100


def test_merge_history(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "HISTORY", tmp_path / "h.json")
    monkeypatch.setattr(run, "OFFERS", tmp_path / "o.json")
    o = run.normalise(_raw(), "t", "T", CONFIG)
    h = run.merge_history([o], "2026-10-24")
    run.HISTORY.write_text(__import__("json").dumps(h))
    o2 = dict(o, price_total=2400)
    run.merge_history([o2], "2026-10-25")
    assert o2["price_history"] == [["2026-10-24", 2500], ["2026-10-25", 2400]]
    assert o2["price_change"] == -100 and o2["first_seen"] == "2026-10-24"
