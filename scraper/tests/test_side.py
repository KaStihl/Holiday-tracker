"""Tab "Side – hotely pri pláži": settings, OSM processing, agency facilities, flights, hotel-only, package data.
All offline: Overpass and Travelpayouts fixtures are CONSTRUCTED from the documented / observed response shapes."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

import build_html
import config
import flights
import hotel_only
import side
import side_hotels as sh
from adapters import billa_reisen, dertour, ruefa, satur
from common import facilities
from config import CONFIG

FX = Path(__file__).parent / "fixtures"
SITE = Path(__file__).resolve().parents[2] / "site"


def raw(**kw):
    r = yaml.safe_load((FX / "nastavenia_test.yml").read_text(encoding="utf-8"))
    r.update(kw)
    return r


def osm():
    return sh.process_osm(json.loads((FX / "overpass_side.json").read_text(encoding="utf-8")), CONFIG["side"])


# --- settings -------------------------------------------------------------------------------------------------------

def test_side_settings_defaults_and_repo_file():
    c = config.validate(raw())
    assert c["side"] == {"enabled": True, "max_m": 300, "oblasti": list(sh.AREAS), "kriteria": list(config.SIDE_CRITERIA),
                         "transfer_eur": 60}
    repo = config.load(Path(__file__).resolve().parents[2] / "nastavenia.yml")
    assert repo["side"]["enabled"] and repo["side"]["max_m"] == 300 and "colakli" in repo["side"]["oblasti"]


def test_side_settings_values_and_errors():
    c = config.validate(raw(side_hotely={"max_vzdialenost_od_plaze_m": 500, "oblasti": ["side", "ÇOLAKLI"],
                                         "kriteria": ["aquapark"], "transfer_eur": 0, "enabled": False}))
    assert c["side"] == {"enabled": False, "max_m": 500, "oblasti": ["side", "colakli"], "kriteria": ["aquapark"],
                         "transfer_eur": 0}
    for bad, msg in [({"oblasti": ["Alanya"]}, "neznáma oblasť"), ({"kriteria": ["bazen"]}, "kriteria"),
                     ({"max_vzdialenost_od_plaze_m": 5000}, "max_vzdialenost"), ({"enabled": "ano"}, "enabled"),
                     ({"transfer": 1}, "neznáme položky"), ("x", "kľúč")]:
        with pytest.raises(config.SettingsError, match=msg):
            config.validate(raw(side_hotely=bad))


# --- OSM ------------------------------------------------------------------------------------------------------------

def test_overpass_query_asks_everything_in_one_request():
    q = sh.overpass_query()
    assert q.count("\nout") == 4 and "[bbox:36.7,31.18,36.86,31.6]" in q
    for k in ('"tourism"~"^(hotel|resort)$"', '"natural"="beach"', '"natural"="coastline"', '"leisure"="water_park"',
              '"attraction"="water_slide"', '"leisure"="swimming_pool"', '"place"~'):
        assert k in q
    assert all("overpass-api.de" not in u for u in sh.OVERPASS)  # its robots.txt disallows /api/


def test_process_osm_distances_merge_aquapark_and_areas():
    hs = {h["name"]: h for h in osm()}
    assert set(hs) == {"Süral Resort", "Royal Alhambra Palace", "Sueno Hotels Beach Side", "Far Inland Hotel"}
    sural = hs["Süral Resort"]
    assert sural["dist_m"] < 40 and sural["dist_kind"] == "beach" and sural["aquapark_osm"] == ["Süral Aqua"]
    assert sural["pools"] == 1 and sural["area"] == "colakli"
    ra = hs["Royal Alhambra Palace"]  # node + "… Hotel" node merged, the closer distance kept, tags combined
    assert 90 < ra["dist_m"] < 130 and ra["stars"] == 5.0 and ra["website"].startswith("https://www.royal")
    assert hs["Far Inland Hotel"]["dist_m"] > 300  # kept in the cache (≤ 1000 m), filtered by max_m later


def test_cache_freshness():
    now = datetime(2026, 11, 6, tzinfo=timezone.utc)
    c = {"fetched_at": "2026-11-01T00:00:00Z", "bbox": list(sh.BBOX)}
    assert sh.cache_fresh(c, now) and not sh.cache_fresh(dict(c, fetched_at="2026-10-20T00:00:00Z"), now)
    assert not sh.cache_fresh(dict(c, bbox=[0, 0, 1, 1]), now) and not sh.cache_fresh(None, now)


# --- agency facilities ----------------------------------------------------------------------------------------------

def test_facility_codes():
    assert facilities("Aquapark, tobogan · Klub Detský svet · Priamo na pláži") == ["aq", "kc", "pl"]
    assert facilities("Pestré animačné programy pre deti · Hotel priamo pri pláži") == ["kc", "pl"]
    assert facilities("Rutschenhotels") == ["aq"] and facilities("Familienzimmer Meerblick") == ["fr"]
    assert facilities("Rodinná izba", ("fr",)) == ["fr"] and facilities("Dvojlôžková izba") == []
    assert facilities("Detský akciový paušál · Klub pre dospelých") == []


def test_dertour_hotel_facts():
    h = {"tags": ["Vzdialenosť k pláži 0 m", "Aquapark v hotelu"], "countryId": "TR",
         "descriptions": [{"name": "Detský klub s česky/slovensky hovoriacim animátorom"}],
         "gps": {"latitude": 36.753053, "longitude": 31.447779}}
    assert dertour.hotel_facts(h, {"name": "Rodinná izba"}) == {"beach_m": 0, "fac": ["aq", "fr", "kc", "pl"],
                                                                 "gps": [36.75305, 31.44778]}
    assert dertour.hotel_facts({"tags": ["Vzdialenosť k pláži 400 m"], "countryId": "GR",
                                "gps": {"latitude": 1, "longitude": 2}}, {}) == {"beach_m": 400}


def test_satur_and_billa_cards_carry_facilities():
    cards = satur.parse_cards((FX / "satur_letecky.html").read_text(encoding="utf-8"))
    assert any(c["fac"] == ["aq", "kc", "pl"] for c in cards)
    offers, _ = billa_reisen.parse_page((FX / "billa_tuerkei.html").read_text(encoding="utf-8"), CONFIG)
    assert any("aq" in (o.get("fac") or []) for o in offers)
    assert all("pl" not in (o.get("fac") or []) for o in offers)  # BILLA "Strand" is a holiday type, not "on the beach"


# --- matching / build -----------------------------------------------------------------------------------------------

def test_name_score_and_area():
    assert side.name_score("Hotel Sural Hotel", "Süral Resort") == 1
    assert side.name_score("Sural Saray", "Süral Resort") == 0
    assert side.name_score("Side Royal Palace", "Royal Alhambra Palace") == 0
    keys = list(sh.AREAS)
    assert side.offer_area({"place": "Çolakli", "country_code": "TR"}, keys) == "colakli"
    assert side.offer_area({"region": "Turecká riviéra - Side", "country_code": "TR"}, keys) == "side"
    assert side.offer_area({"place": "Alanya", "country_code": "TR"}, keys) is None
    assert side.offer_area({"place": "Side", "country_code": "GR"}, keys) is None


def offer(hotel, party="a1-c10-12", **kw):
    o = {"hotel": hotel, "source": "ruefa", "place": "Çolakli", "country_code": "TR", "party": party, "price_total": 2500,
         "date_from": "2027-07-10", "nights": 7, "departure": "VIE", "price_exact": True, "board": "AI",
         "url": "https://pauschal.ruefa.at/x"}
    o.update(kw)
    return o


def test_build_side_doc():
    offers = [offer("Hotel Süral Hotel", fac=["fr"], gid="53099"), offer("Hotel Süral Hotel", "a2-c10-12", price_total=3400),
              offer("Royal Alhambra Palace", source="satur", price_exact=False, fac=["aq", "kc"], board="UAI"),
              offer("Unknown Beach Hotel", source="kartago", fac=["pl"], beach_m=0),
              offer("Somewhere Inland", source="kartago"),
              offer("Gps Only Name", source="fischer", gps=[36.7925, 31.2951])]
    day = {"sources": [{"id": "billa_reisen", "status": "ok"}], "ruefa_attr": {"53099": ["aq"]},
           "rows": {"billa_reisen": [{"hotel": "Royal Alhambra Palace Hotel", "pp": 700, "checkin": "2027-07-10",
                                      "nights": 7, "board": "AI", "url": "https://www.billareisen.at/x"}]}}
    fl = {"status": "ok", "flights": [{"o": "VIE", "dep": "2027-07-10", "ret": "2027-07-17", "n": 7, "p": 250}]}
    cfg = config.validate(raw(skupiny=[{"nazov": "Ja + 2 deti", "adults": 1, "children_ages": [10, 12]},
                                       {"nazov": "2 + 2", "adults": 2, "children_ages": [10, 12]},
                                       {"nazov": "2", "adults": 2, "children_ages": []}]))
    doc = side.build(cfg, offers=offers, osm=osm(), flights=fl, hotel_prices=day,
                     now=datetime(2026, 11, 6, tzinfo=timezone.utc))
    hs = {h["n"]: h for h in doc["hotels"]}
    assert "Far Inland Hotel" not in hs  # > 300 m
    assert set(hs) == {"Süral Resort", "Royal Alhambra Palace", "Sueno Hotels Beach Side", "Unknown Beach Hotel"}
    s = hs["Süral Resort"]
    assert s["fac"] == {"aq": ["ruefa (filter)"], "fr": ["ruefa"]} and s["aqo"] == ["Süral Aqua"]
    assert s["fit"] == {"a1-c10-12": ["ruefa"], "a2-c10-12": ["ruefa"]}
    assert s["of"]["a2-c10-12"][0][:2] == ["ruefa", 3400]
    ra = hs["Royal Alhambra Palace"]
    assert ra["fac"] == {"aq": ["satur"], "kc": ["satur"]} and ra["ai"] == ["fischer", "satur"]  # fischer: matched by GPS only
    assert ra["ho"]["a1-c10-12"][0][:2] == ["billa_reisen", 2100] and ra["ho"]["a2-c10-12"][0][1] == 2800
    assert "d" not in hs["Unknown Beach Hotel"]  # distance unknown (no OSM match) – the agency's is in "bd"
    assert hs["Unknown Beach Hotel"]["bd"] == [0, "kartago"]
    assert doc["stats"]["agency_unmatched_hotels"] == 1  # "Somewhere Inland": no OSM match, no beach info
    assert doc["flights"]["list"] == fl["flights"] and doc["transfer_eur"] == 60
    assert [p["id"] for p in doc["parties"]] == ["a1-c10-12", "a2-c10-12", "a2"]


def test_build_disabled():
    cfg = dict(CONFIG, side=dict(CONFIG["side"], enabled=False))
    doc = side.build(cfg, offers=[], osm=[], flights={"status": "no_token", "flights": []}, hotel_prices={})
    assert doc["enabled"] is False and "hotels" not in doc


# --- flights --------------------------------------------------------------------------------------------------------

def test_flight_parsing_and_combinations():
    rt = json.loads((FX / "tp_prices_for_dates_rt.json").read_text(encoding="utf-8"))
    got = flights.parse(rt, CONFIG, "VIE")
    assert [(f["dep"], f["n"], f["p"]) for f in got] == [("2027-07-01", 9, 219), ("2027-07-05", 14, 248)]  # 3 nights
    there = flights.cheapest_by_day(json.loads((FX / "tp_oneway_vie_ayt.json").read_text(encoding="utf-8")))
    back = flights.cheapest_by_day(json.loads((FX / "tp_oneway_ayt_vie.json").read_text(encoding="utf-8")))
    combos = flights.combine("VIE", there, back, CONFIG)
    assert {(c["dep"], c["n"], c["p"]) for c in combos} == {("2027-07-10", 7, 250), ("2027-07-10", 10, 270),
                                                            ("2027-07-10", 14, 210), ("2027-07-03", 14, 229)}
    assert all(c["k"] == "ow" for c in combos)


def test_flights_without_token(monkeypatch):
    monkeypatch.delenv("TRAVELPAYOUTS_TOKEN", raising=False)
    assert flights.fetch(CONFIG, get=lambda *a, **k: pytest.fail("no request without token"))["status"] == "no_token"


def test_flights_token_only_in_header(monkeypatch):
    monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "SECRET123")
    calls = []

    def fake_get(url, params=None, headers=None, **kw):
        calls.append((params, headers))
        assert "SECRET123" not in json.dumps(params) and headers["X-Access-Token"] == "SECRET123"
        name = "tp_prices_for_dates_rt.json" if params["one_way"] == "false" else \
            "tp_oneway_vie_ayt.json" if params["origin"] != "AYT" else "tp_oneway_ayt_vie.json"
        return json.loads((FX / name).read_text(encoding="utf-8"))

    res = flights.fetch(CONFIG, get=fake_get)
    assert res["status"] == "ok" and len(calls) == 9 * len(flights.origins(CONFIG))
    assert {f["k"] for f in res["flights"]} == {"rt", "ow"}


def test_flights_401_is_an_error_not_a_crash(monkeypatch):
    monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "BAD")

    def fake_get(*a, **k):
        raise RuntimeError("401 Client Error: Unauthorized for url: https://x?token=BAD")

    res = flights.fetch(CONFIG, get=fake_get)
    assert res["status"] == "error" and "BAD" not in res["error"] and res["requests"] == 1


def test_aviasales_link_passengers():
    # 1 adult + children 10 and 12: airlines count 12+ as adults -> 2 adults, 1 child
    assert flights.aviasales_link("VIE", "AYT", "2027-07-10", "2027-07-17", 1, [10, 12]) == \
        "https://www.aviasales.com/search/VIE1007AYT170721"
    assert flights.aviasales_link("BTS", "AYT", "2027-08-01", "2027-08-15", 2, []) == \
        "https://www.aviasales.com/search/BTS0108AYT15082"


# --- hotel only / Ruefa attributes ----------------------------------------------------------------------------------

def test_billa_hotel_only_query_and_parse():
    q = hotel_only.billa_query(CONFIG, 7)
    assert (q["pttid"], q["ptoj"], q["ttid"], q["pnnfl"], q["pnnfh"], q["pdf"]) == ("PH", "PH", "PH", 7, 7, "3380096")
    assert "pdaf" not in q and hotel_only.billa_url(CONFIG, 7).startswith("https://www.billareisen.at/Hotels/Angebote.html?")
    rows, pages = hotel_only.parse_billa((FX / "billa_tuerkei.html").read_text(encoding="utf-8"), CONFIG)
    assert rows and all(r["pp"] > 0 and r["nights"] >= 1 for r in rows)
    assert hotel_only.in_side({"place": "Çolakli"}) and not hotel_only.in_side({"place": "Alanya"})


def test_ruefa_side_attributes(monkeypatch):
    def card(g):
        return f'<div class="card-hotel" data-giataid="{g}p" data-href="x"></div>'

    answers = {"": ["1", "2", "3"], "GT03-WASL": ["2"], "ST04-FA": ["1", "2", "3"], "GT03-DIBE#ST03-DIRE": []}

    def fake_get(url, data=None, **kw):
        code = data.get("globalType") or data.get("zimmer") or ""
        gs = [g for g in answers[code] if g in data["gid"].split()]
        return {"resultCount": len(gs), "value": "".join(card(g) for g in gs)}

    monkeypatch.setattr(ruefa, "get", fake_get)
    # family-room filter answering every hotel = ignored filter -> discarded
    assert ruefa.side_attributes(CONFIG, ["1", "2", "3", "x"]) == {"2": ["aq"]}


# --- page -----------------------------------------------------------------------------------------------------------

def test_bundle_embeds_side_data_and_script(tmp_path):
    site_dir = tmp_path / "site"
    shutil.copytree(SITE, site_dir)
    (site_dir / "data" / "offers.json").write_text(json.dumps({"offers": []}))
    (site_dir / "data" / "side.json").write_text(json.dumps({"hotels": [{"n": "</script><i>x"}]}))
    html = build_html.build(site_dir, tmp_path / "out.html").read_text(encoding="utf-8")
    assert '<script id="side-data" type="application/json">' in html and 'src="side.js"' not in html
    assert "</script><i>" not in html and "Overiť na Booking.com" in html
    (site_dir / "data" / "side.json").unlink()
    html = build_html.build(site_dir, tmp_path / "out.html").read_text(encoding="utf-8")
    assert '<script id="side-data" type="application/json">null</script>' in html


def test_sample_side_data_is_marked_and_valid():
    doc = json.loads((SITE / "data" / "side.sample.json").read_text(encoding="utf-8"))
    assert "UKÁŽKOVÉ" in doc["_note"] and doc["hotels"] and doc["flights"]["list"]
