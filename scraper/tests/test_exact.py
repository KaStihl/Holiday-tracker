"""Exact prices for the configured party (1 adult + 2 children in the pinned test settings): Čedok detail page parsing, run.py shortlist, history and digest handling."""

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import notify
import run
from adapters import cedok
from config import CONFIG

FX = Path(__file__).parent / "fixtures"
URL = ("https://www.cedok.sk/dovolena/grecko/kreta/hotel-fragiskos-beach,HER2FRA/?id=CgVDZWRvaxIEVklUQxoDQ1pL"
       "IgdIRVIyRlJBKAQ6BEcyMDBC%253D&participants%5B0%5D%5Badults%5D=2&airports=BTS%2CVIE")
OFFER = {"hotel": "Hotel Fragiskos Beach", "url": URL, "date_from": "2027-08-22", "date_to": "2027-08-29",
         "price_total": 2324, "discount_label": "First Minute (cena za os. × 3, orientačne)"}


def test_occupancy_url_keeps_term_and_asks_for_the_party():
    u = cedok.occupancy_url(URL, CONFIG)
    assert "id=CgVDZWRvaxIEVklUQxoDQ1pLIgdIRVIyRlJBKAQ6BEcyMDBC%253D" in u  # double-encoded term id untouched
    q = parse_qsl(urlsplit(u).query)
    assert [kv for kv in q if kv[0].startswith("participants")] == [
        ("participants[0][adults]", "1"), ("participants[0][children][0]", "30.06.2017"),
        ("participants[0][children][1]", "30.06.2015")]
    assert ("airports", "BTS,VIE") in q


def test_parse_detail_real_payload():
    # the stream is split across several self.__next_f.push() chunks, mid-row
    v = cedok.parse_detail((FX / "cedok_detail_1_2.html").read_text())
    assert v == [{"start": "2027-08-22", "end": "2027-08-29", "adults": 1, "children": 2,
                  "birthdates": ["2017-01-01", "2015-01-01"], "total": 1920.0}]
    assert cedok.pick_exact(v, OFFER, CONFIG) == 1920


def test_pick_exact_refuses_anything_but_the_same_term_and_party():
    v = cedok.parse_detail((FX / "cedok_detail_1_2.html").read_text())[0]
    assert cedok.pick_exact([dict(v, start="2027-08-23")], OFFER, CONFIG) is None  # other term
    assert cedok.pick_exact([dict(v, adults=2, children=0, birthdates=[])], OFFER, CONFIG) is None  # site fell back
    assert cedok.pick_exact([dict(v, birthdates=["2020-01-01", "2015-01-01"])], OFFER, CONFIG) is None  # wrong ages
    assert cedok.pick_exact([], OFFER, CONFIG) is None
    assert cedok.parse_detail("<html>no payload</html>") == []


def test_exact_price_hook(monkeypatch):
    calls = []
    html = (FX / "cedok_detail_1_2.html").read_text()
    monkeypatch.setattr(cedok, "get", lambda url: calls.append(url) or html)
    res = cedok.exact_price(OFFER, CONFIG)
    assert res == {"price_total": 1920, "price_original": None, "url": calls[0], "discount_label": "First Minute"}
    assert "participants%5B0%5D%5Bchildren%5D%5B1%5D=30.06.2015" in calls[0]
    monkeypatch.setattr(cedok, "get", lambda url: "<html></html>")
    assert cedok.exact_price(OFFER, CONFIG) is None


def _offer(i, price, board="AI", source="cedok"):
    o = run.normalise({"hotel": f"H{i}", "url": f"https://x/{i}", "date_from": "2027-07-10", "nights": 7,
                       "price_total": price, "board": board, "country": "Turecko",
                       "discount_label": "Cena za os. × 3 (orientačne)"}, source, source, CONFIG)
    return o


def test_refine_exact_shortlist(monkeypatch):
    offers = [_offer(i, 2000 + 10 * i) for i in range(5)] + [_offer(9, 1500, board="HB"), _offer(8, 1600, source="satur")]
    asked = []

    def hook(o, cfg):
        asked.append(o["hotel"])
        if o["hotel"] == "H1":
            return None  # page did not confirm -> stays approximate
        if o["hotel"] == "H2":
            raise OSError("500")
        return {"price_total": 4600 if o["hotel"] == "H3" else o["price_total"] - 300, "discount_label": None}

    mod = SimpleNamespace(exact_price=hook, EXACT_MAX=4)
    out = run.refine_exact(offers, {"cedok": mod, "satur": SimpleNamespace()}, dict(CONFIG, price_cap=4500))
    assert asked == ["H0", "H1", "H2", "H3"]  # AI/UAI only, best score first, capped at EXACT_MAX
    by = {o["hotel"]: o for o in out}
    assert "H3" not in by  # exact price above price_cap no longer matches
    assert (by["H0"]["price_total"], by["H0"]["price_approx"], by["H0"]["price_exact"]) == (1700, 2000, True)
    assert by["H0"]["discount_label"] is None and by["H0"]["price_note"] is None
    assert by["H1"]["price_note"] == "orientačne: cena za osobu pri 2 dospelých × 3"
    assert not by["H1"]["price_exact"] and by["H1"]["price_total"] == 2010
    assert not by["H4"]["price_exact"] and not by["H9"]["price_exact"] and not by["H8"]["price_exact"]


def test_history_restarts_when_price_becomes_exact(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "HISTORY", tmp_path / "h.json")
    monkeypatch.setattr(run, "OFFERS", tmp_path / "o.json")
    o = _offer(1, 2400)
    run.OFFERS.write_text(json.dumps({"offers": [dict(o)]}))
    run.HISTORY.write_text(json.dumps({o["id"]: {"first_seen": "2026-10-20", "last_seen": "2026-10-24",
                                                 "points": [["2026-10-24", 2400]]}}))
    exact = dict(o, price_total=2000, price_exact=True)
    hist = run.merge_history([exact], "2026-10-25")
    assert exact["price_change"] is None and exact["price_history"] == [["2026-10-25", 2000]]
    assert hist[o["id"]]["exact"] is True and hist[o["id"]]["first_seen"] == "2026-10-20"
    # next run, still exact: a normal price change again
    run.OFFERS.write_text(json.dumps({"offers": [exact]}))
    run.HISTORY.write_text(json.dumps(hist))
    again = dict(o, price_total=1950, price_exact=True)
    run.merge_history([again], "2026-10-26")
    assert again["price_change"] == -50 and len(again["price_history"]) == 2


def _n(id, price, exact=False):
    return {"id": id, "price_total": price, "board": "AI", "hotel": "H" + id, "url": "https://x/" + id,
            "place": "Side", "country": "Turecko", "date_from": "2027-07-10", "nights": 7, "transport": "flight",
            "departure": "BTS", "source_name": "Čedok", "score": 50, "price_exact": exact}


def test_digest_ignores_switch_to_exact_and_says_which_are_exact():
    prev = {"offers": [_n("a", 2600), _n("b", 2600)]}
    title, _ = notify.digest(prev, {"offers": [_n("a", 2100, exact=True), _n("b", 2600)]}, 3000)
    assert "zlacnenie" not in title
    _, body = notify.digest({"offers": [_n("x", 1)]}, {"offers": [_n("a", 2100, exact=True), _n("b", 2600)]}, 3000)
    assert "2100 €** ✓" not in body and "**2\u00a0100\u00a0€** ✓" in body
    assert "✓ = presná cena 1+2 priamo od cestovky (Čedok)" in body
    _, body = notify.digest({}, {"offers": [_n("b", 2600)]}, 3000)
    assert "orientačne cena za osobu" in body and "✓" not in body
