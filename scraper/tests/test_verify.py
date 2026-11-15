"""Offer verification: Ruefa's own availability check (adapters/ruefa.py verify), the verify.json cache and scoring
with verified prices (run.py), the digest lines (notify.py)."""
import json
from pathlib import Path

import notify
import run
from adapters import dertour, ruefa
from config import CONFIG

FX = Path(__file__).parent / "fixtures"
URL = ("https://pauschal.ruefa.at/index.php?page=hotel&start=2027-07-01&until=2027-07-08&adults=1&cabinClass=economy"
       "&ankunftshafen=AYT&children=12-10&anzZimmer=1&abflughafen=VIE%20BTS&reisetag=2027-07-01&rq=1&rva=VFVJRA=="
       "&bu=AYT41041&gid=239871&pos=5")


def _offer(**kw):
    o = {"id": "ruefa:alhambra", "source": "ruefa", "hotel": "Royal Alhambra Palace", "url": URL, "board": "AI",
         "date_from": "2027-07-01", "date_to": "2027-07-08", "nights": 7, "price_total": 3596, "party": "a1-c10-12",
         "transport": "flight", "country_code": "TR", "stars": 5, "rating": 8.7, "watched": "Alhambra"}
    o.update(kw)
    return o


def test_conf_is_the_hotel_page_conf_from_the_offer_url():
    c = ruefa.verify_conf(_offer())
    assert (c["start"], c["until"], c["adults"], c["children"], c["dauer"]) == ("2027-07-01", "2027-07-08", "1",
                                                                                "12-10", "128")
    assert (c["veranstalter"], c["gid"], c["abflughafen"], c["ankunftshafen"], c["reisetag"], c["sort"]) == \
        ("VFVJRA==", "239871", "VIE BTS", "AYT", "2027-07-01", "price")


def test_parse_real_offer_list_and_pick_comparable_options():
    opts = ruefa.parse_options((FX / "ruefa_hotel_offers.html").read_text())
    assert [x["price"] for x in opts][:3] == [3100, 3200, 3596]
    tui = next(x for x in opts if x["price"] == 3596)
    assert (tui["toc"], tui["room"], tui["kind"], tui["dep"], tui["board_code"], tui["transfer"]) == \
        ("TUI", "DOUBLE SUPERIOR ROOM", "Doppelzimmer", "VIE", "GT06-AIP", "inkl. Transfer")
    cands = ruefa.candidates(opts, _offer(), CONFIG)
    # half board (Bye bye, 3100) and the Prague departure (3200) are not comparable; Coral's transfer variant
    # (same operator, flights and room as its 3815 row) is not tried twice
    assert [(x["toc"], x["price"]) for x in cands] == [("TUI", 3596), ("TUI", 3706), ("TUI", 3707),
                                                       ("ITS Deutschland", 3725), ("DER Touristik", 3731),
                                                       ("Coral Travel", 3815)]
    assert ruefa.candidates(opts, _offer(date_from="2027-07-02"), CONFIG) == []


def test_parse_check_states():
    assert ruefa.parse_check((FX / "ruefa_checkprice_available.txt").read_text()) == ("available", 3692)
    assert ruefa.parse_check((FX / "ruefa_checkprice_unavailable.txt").read_text()) == ("unavailable", None)
    assert ruefa.parse_check("<preis>0</preis><error>Leistungslücke</error>")[0] == "retry"
    assert ruefa.parse_check("<preis>3900</preis><error>Nur auf Anfrage buchbar</error>") == ("on_request", 3900)
    assert ruefa.parse_check("") == ("unavailable", None)


def _fake_get(answers, log):
    def get(url, **kw):
        log.append((url.rsplit("/", 1)[-1], kw.get("data", {}).get("data", "")))
        if url.endswith("additionalOffersHotelpage.php"):
            return (FX / "ruefa_hotel_offers.html").read_text()
        return answers.pop(0)
    return get


def test_verify_first_bookable_option_like_the_hotel_page(monkeypatch):
    no = (FX / "ruefa_checkprice_unavailable.txt").read_text()
    yes = (FX / "ruefa_checkprice_available.txt").read_text()
    log = []
    monkeypatch.setattr(ruefa, "get", _fake_get([no, no, no, yes], log))
    out = ruefa.verify(CONFIG, [_offer()])
    r = out["ruefa:alhambra"]
    assert (r["status"], r["price"], r["checked"], r["options"], r["listed"]) == ("available", 3692, 4, 6, 3596)
    assert r["room"] == "Alhambra Suite (Suite mit Meerblick), All Inclusive ohne Transfer, ITS Deutschland"
    assert [x[0] for x in log] == ["additionalOffersHotelpage.php"] + ["checkPrice.php"] * 4
    assert log[-1][1].endswith("*AYT27016NI*ITS")


def test_verify_nothing_bookable_among_the_cheapest_is_partial(monkeypatch):
    no = (FX / "ruefa_checkprice_unavailable.txt").read_text()
    monkeypatch.setattr(ruefa, "get", _fake_get([no] * 10, []))
    r = ruefa.verify(CONFIG, [_offer()])["ruefa:alhambra"]
    assert (r["status"], r["price"], r["checked"], r.get("partial")) == ("unavailable", None, ruefa.VERIFY_CHECKS, True)


def test_verify_respects_the_request_budget(monkeypatch):
    no = (FX / "ruefa_checkprice_unavailable.txt").read_text()
    log = []
    monkeypatch.setattr(ruefa, "get", _fake_get([no] * 100, log))
    monkeypatch.setattr(ruefa, "VERIFY_CALLS", 7)
    offers = [_offer(id=f"ruefa:{i}") for i in range(5)]
    out = ruefa.verify(CONFIG, offers)
    assert len(log) <= 7 and len(out) == 2


def test_cache_once_a_day_and_dropped_when_gone(tmp_path, monkeypatch):
    path = tmp_path / "verify.json"
    path.write_text(json.dumps({
        "ruefa:alhambra": {"status": "available", "price": 3692, "room": "Suite", "checked_at": "2026-11-15T04:30:00Z"},
        "ruefa:old": {"status": "unavailable", "checked_at": "2026-11-01T04:30:00Z"},
        "ruefa:gone": {"status": "unavailable", "checked_at": "2026-11-15T04:30:00Z"},
        "ruefa:other": {"status": "available", "price": 2000, "checked_at": "2026-11-14T16:30:00Z"},
    }))
    offers = [_offer(), _offer(id="ruefa:old", watched=None), _offer(id="ruefa:other", watched=None, price_total=2000)]
    asked = []

    class Mod:
        @staticmethod
        def verify(cfg, todo):
            asked.extend(o["id"] for o in todo)
            return {"ruefa:old": {"status": "unavailable", "checked_at": "2026-11-15T05:00:00Z", "checked": 2}}

    sources = [{"id": "ruefa", "status": "ok"}]
    cache = run.run_verify(offers, {"ruefa": Mod}, sources, CONFIG, "2026-11-15", path)
    assert asked == ["ruefa:other", "ruefa:old"]  # by score; alhambra was verified today already
    assert set(cache) == {"ruefa:alhambra", "ruefa:old", "ruefa:other"}  # gone dropped, old one re-verified
    assert cache["ruefa:old"]["listing"] == 3596
    a, old, other = offers
    assert a["verified"]["status"] == "available" and a["price_verified"] == 3692
    assert old["verified"] == {"status": "unavailable", "checked_at": "2026-11-15T05:00:00Z", "checked": 2}
    assert "price_verified" not in other  # bookable at the listing price
    assert sources[0]["verify"]["checked"] == 1 and sources[0]["verify"]["cached"] == 1


def test_shortlist_watched_first_primary_party_only():
    a = _offer(id="ruefa:w2", price_total=4000)
    b = _offer(id="ruefa:w1", price_total=3000)
    c = _offer(id="ruefa:x", watched=None, price_total=1500, board="AI")
    d = _offer(id="ruefa:x@a2", watched=None, party="a2")
    e = _offer(id="kartago:y", source="kartago")
    assert [o["id"] for o in run.verify_shortlist([a, b, c, d, e], "ruefa", CONFIG)] == ["ruefa:w1", "ruefa:w2", "ruefa:x"]


def test_score_uses_the_verified_price_and_penalises_unavailable():
    base = _offer(watched=None, region=None, discount_pct=None)
    plain = run.score(base, CONFIG)
    dear = dict(base, price_verified=5500, verified={"status": "available"})
    gone = dict(base, verified={"status": "unavailable"})
    req = dict(base, verified={"status": "on_request"})
    assert run.score(dear, CONFIG) < plain
    assert run.score(gone, CONFIG) < run.score(req, CONFIG) < plain
    assert run.effective_price(dear) == 5500 and run.effective_price(base) == 3596


def test_dertour_on_request_flag_becomes_verified_status():
    data = json.loads((FX / "fischer_tours_turecko.json").read_text())
    t = data["tours"][0]
    t["tour"]["isOnline"] = False
    o = dertour.to_offer(t, "https://www.fischer.sk", CONFIG)
    assert o["on_request"] is True
    run.attach_verified(o, None)
    assert o["verified"] == {"status": "on_request", "via": "listing"}


def test_digest_shows_verified_prices_and_unverified_marks():
    o = {"id": "a", "price_total": 3596, "price_verified": 3692, "board": "AI", "hotel": "Royal Alhambra Palace",
         "url": "https://x/a", "place": "Çolaklı", "country": "Turecko", "date_from": "2027-07-01", "nights": 7,
         "transport": "flight", "departure": "VIE", "source_name": "Ruefa", "score": 50, "watched": "Alhambra",
         "verified": {"status": "available", "price": 3692, "room": "Alhambra Suite", "checked_at": "2026-11-15T04:30Z"}}
    u = dict(o, id="b", hotel="Süral Garden", watched="Sural", price_total=2100, verified=None, price_verified=None)
    _, body = notify.digest({}, {"offers": [o, u]}, 3000)
    assert "⚠ za 3 596 € nedostupné – overené 15. 11.: dostupné od **3 692 €** (Alhambra Suite)" in body
    assert "? cena neoverená" in body
    assert "→ overené 3 692 €" in body


def test_side_compact_offer_carries_the_verification():
    import side
    o = _offer(price_verified=3692, verified={"status": "available", "price": 3692, "room": "Alhambra Suite",
                                              "checked_at": "2026-11-15T04:30:00Z"})
    assert side.compact_offer(o)[8] == ["available", 3692, "Alhambra Suite", "2026-11-15T04:30:00Z"]
    assert side.compact_offer(_offer())[8] is None
