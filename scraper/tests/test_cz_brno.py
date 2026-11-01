"""Brno (BRQ) as a secondary departure, Itaka (CZK, ECB rate) and the link-only Coral Travel module."""

import json
from pathlib import Path

import common
import run
from adapters import cedok, coral_travel, dertour, fischer, itaka
from config import CONFIG

FX = Path(__file__).parent / "fixtures"
RATE = (24.353, "prepočet z CZK kurzom ECB 24,353 CZK/€ (2026-10-30)")
KTW = dict(CONFIG, departures=["KTW"])  # the fixture's real departure, as if the user flew from Katowice


def itaka_page():
    return (FX / "itaka_turecko_ktw.html").read_text()


def test_settings_have_brno_as_secondary_airport():
    assert "BRQ" in CONFIG["departures_secondary"] and "BRQ" not in CONFIG["departures"]


def test_run_keeps_brno_flights_and_drops_other_airports():
    t = json.loads((FX / "fischer_tours_turecko.json").read_text())["tours"][0]
    seg = t["tour"]["flight"]["departure"]["segments"][0]["airport"]
    seg.update(fromId=4305, fromIATA="BRQ")
    o = dertour.to_offer(t, fischer.HOME, CONFIG)
    assert o["departure"] == "BRQ" and run.normalise(o, "fischer", "Fischer", CONFIG)["departure"] == "BRQ"
    seg.update(fromId=4312, fromIATA="PRG")
    assert run.normalise(dertour.to_offer(t, fischer.HOME, CONFIG), "fischer", "Fischer", CONFIG) is None


def test_cedok_brno_title_and_query():
    html = (FX / "cedok_turecko.html").read_text().replace("Bratislava (letisko)", "Brno (letisko)")
    rates, _, links = cedok.parse_page(html)
    deps = {o["departure"] for o in (cedok.to_offer(r, links, CONFIG) for r in rates) if o}
    assert "BRQ" in deps
    assert cedok._query(CONFIG, airports=("BRQ",))["departuresByPlane"] == "BRQ"
    assert cedok.secondary(CONFIG) == ["BRQ"] and cedok.secondary(dict(CONFIG, departures_secondary=["KSC"])) == []


def test_ecb_rate_parsing_and_fallback(monkeypatch):
    xml = ("<gesmes:Envelope><Cube><Cube time='2026-10-30'><Cube currency='USD' rate='1.1172'/>"
           "<Cube currency='CZK' rate='24.353'/></Cube></Cube></gesmes:Envelope>")
    assert common.parse_ecb(xml) == ({"USD": 1.1172, "CZK": 24.353}, "2026-10-30")
    monkeypatch.setattr(common, "_fx", {})
    monkeypatch.setattr(common, "get", lambda url, **kw: xml)
    rate, note = common.eur_rate("CZK")
    assert rate == 24.353 and note == "prepočet z CZK kurzom ECB 24,353 CZK/€ (2026-10-30)"

    def down(url, **kw):
        raise OSError("unreachable")
    monkeypatch.setattr(common, "_fx", {})
    monkeypatch.setattr(common, "get", down)
    rate, note = common.eur_rate("CZK")
    assert rate == common.FX_FALLBACK["CZK"] and "kurz ECB nedostupný" in note
    common.eur_rate("CZK")  # cached: no second attempt


def test_itaka_rate_exact_party_price_in_eur():
    rates, count, links = cedok.parse_page(itaka_page())
    assert count == 136 and len(rates) == 3
    o = itaka.to_offer(rates[0], links, KTW, RATE)
    assert (o["hotel"], o["country_code"], o["region"], o["departure"], o["board"]) == (
        "Hotel Stella Camyuva", "TR", "Kemer", "KTW", "AI")
    assert (o["date_from"], o["date_to"], o["nights"]) == ("2027-07-01", "2027-07-08", 7)
    # priceWithSurcharges 46 326 Kč for 1 adult + 2 children (incl. airport fees) / 24.353
    assert (o["price_total"], o["price_original"], o["price_exact"]) == (round(46326 / 24.353), round(56427 / 24.353), True)
    k = run.normalise(o, "itaka", "Itaka", KTW)
    assert k["price_exact"] and k["price_note"] == "prepočet z CZK kurzom ECB 24,353 CZK/€ (2026-10-30): 46 326 Kč"
    assert k["url"].startswith("https://www.itaka.cz/dovolena/turecko/kemer/") and "fx_note" not in k
    assert run.normalise(o, "itaka", "Itaka", CONFIG) is None  # Katowice is not a configured airport


def test_itaka_other_party_is_approximated_and_noted():
    rates, _, links = cedok.parse_page(itaka_page())
    r = dict(rates[0], participants=rates[0]["participants"][:2])  # e.g. priced for 2 persons
    o = run.normalise(itaka.to_offer(r, links, KTW, RATE), "itaka", "Itaka", KTW)
    assert not o["price_exact"] and o["price_total"] == round(46326 / 2 * 3 / 24.353)
    assert o["price_note"].startswith("orientačne: cena za osobu pri 2 osobách × 3; prepočet z CZK")


def test_itaka_skips_round_trips_hotel_only_and_unknown_airports():
    rates, _, links = cedok.parse_page(itaka_page())
    r = rates[0]
    assert itaka.to_offer(dict(r, rateType="roundTrip"), links, KTW, RATE) is None
    hotel_only = dict(r, segments=[s for s in r["segments"] if s["type"] == "hotel"])
    assert itaka.to_offer(hotel_only, links, KTW, RATE) is None
    odd = json.loads(json.dumps(r))
    odd["segments"][0]["departure"]["title"] = "Mars (letiště)"
    assert itaka.to_offer(odd, links, KTW, RATE) is None
    assert itaka.airport("Brno (letiště)") == "BRQ" and itaka.airport("Vídeň (letiště)") == "VIE"


def test_itaka_search_stops_after_one_request_when_no_configured_airport_is_served(monkeypatch):
    calls = []
    monkeypatch.setattr(itaka, "eur_rate", lambda cur: RATE)
    monkeypatch.setattr(itaka, "get", lambda url, params=None: calls.append((url, params)) or itaka_page())
    assert itaka.search(CONFIG) == []  # the page only has Katowice flights
    assert len(calls) == 1 and calls[0][1]["departuresByPlane"] == "BTS,VIE,BUD,KSC,BRQ"
    assert calls[0][1]["participants[0][children][1]"] == "30.06.2015"
    # when a configured airport is served: one page per country (+ a second for favourites), within budget
    calls.clear()
    got = itaka.search(dict(KTW, countries={"TR": 1.0, "GR": 0.5}))
    assert {o["departure"] for o in got} == {"KTW"} and all(o["price_exact"] for o in got)
    # Turecko p1, Grécko p1 (the fixture only has Turkish hotels -> discarded), Turecko p2 (136 rates, weight 1.0)
    assert [(u.rsplit("/", 2)[-2], p.get("page", 1)) for u, p in calls[1:]] == [("turecko", 1), ("recko", 1),
                                                                               ("turecko", 2)]
    assert all(p["departuresByPlane"] == "KTW" for _, p in calls[1:]) and len(calls) <= itaka.MAX_REQUESTS


def test_itaka_watch_reads_the_hotel_page(monkeypatch):
    rates, _, _ = cedok.parse_page(itaka_page())

    def page(gv):
        nd = {"props": {"pageProps": {"initialQueryState": {"queries": [
            {"queryKey": ["variants", {"currency": "CZK", "supplierObjectId": "AYTALHA"}],
             "state": {"data": {"groupedVariants": gv}}}]}}}}
        return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script>'

    monkeypatch.setattr(itaka, "eur_rate", lambda cur: RATE)
    asked = []
    # real state on 2026-11-01: Royal Alhambra Palace has no variants on sale at Itaka
    monkeypatch.setattr(itaka, "get", lambda url, params=None: asked.append(url) or page(None))
    assert itaka.watch(CONFIG, ["Sural", "Royal Alhambra"]) == []
    assert asked == ["https://www.itaka.cz/dovolena/turecko/side/royal-alhambra-palace,AYTALHA/"]
    # a variant (same shape as a listing rate) becomes an offer with the hotel page as link
    ref = dict(rates[0], supplierObjectId="AYTALHA")
    monkeypatch.setattr(itaka, "get", lambda url, params=None: page({"referenceRate": ref, "departureCode": []}))
    (o,) = itaka.watch(KTW, ["Royal Alhambra"])
    assert o["url"].startswith("https://www.itaka.cz/dovolena/turecko/side/royal-alhambra-palace,AYTALHA/?")
    assert o["price_exact"] and o["departure"] == "KTW"
    assert itaka.watch_links(CONFIG, "Royal Alhambra", [])[0]["label"] == "Royal Alhambra Palace na itaka.cz"
    assert itaka.watch_links(CONFIG, "Sural", []) == []


def test_coral_travel_is_link_only_with_hotel_link():
    assert coral_travel.DEEPLINK_ONLY and coral_travel.search(CONFIG) == [] and coral_travel.REASON
    (link,) = coral_travel.watch_links(CONFIG, "Royal Alhambra", [])
    assert link["url"] == "https://www.coraltravel.cz/hotels/turkey/royal-alhambra-palace-side/"
