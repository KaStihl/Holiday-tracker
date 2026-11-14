import json
from datetime import date
from pathlib import Path

import run
from adapters import hydrotour
from config import CONFIG, party_cfg, party_id

FX = Path(__file__).parent / "fixtures"
DATA = json.loads((FX / "hydrotour_terminy.json").read_text())


def test_offers_from_search_json():
    offers = hydrotour.to_offers(DATA, CONFIG)
    # 1 BA term of Azure + 2 terms of Diamond De Luxe from BA and KE
    assert len(offers) == 5
    o = next(o for o in offers if o["url"].endswith("#375698"))
    assert o["hotel"] == "Diamond De Luxe Hotel & SPA" and o["departure"] == "KSC"
    assert o["url"] == "https://www.hydrotour.sk/dovolenky/turecko/side/diamond-de-luxe-hotel-spa#375698"
    assert (o["country_code"], o["place"], o["stars"], o["board"]) == ("TR", "Side", 5, "AI")
    assert (o["date_from"], o["date_to"], o["nights"]) == ("2027-07-02", "2027-07-09", 7)
    # per-adult price incl. fees (1493.30) × 3 persons; catalogue 1849 + fees 224 = 2073 × 3
    assert (o["price_total"], o["price_original"]) == (4480, 6219)
    assert "price_exact" not in o and "× 3" in o["price_note"]
    azure = next(o for o in offers if o["hotel"] == "Azure by Yelken")
    assert (azure["departure"], azure["board"], azure["place"]) == ("BTS", "UAI", "Bodrum")


def test_run_normalise_keeps_july_drops_june():
    offers = hydrotour.to_offers(DATA, CONFIG)
    kept = [k for k in (run.normalise(o, "hydrotour", hydrotour.NAME, CONFIG) for o in offers) if k]
    assert len(kept) == 4 and {k["departure"] for k in kept} == {"BTS", "KSC"}
    assert all(not k["price_exact"] and k["price_note"].startswith("orientačne") for k in kept)


def test_countries_outside_settings_and_unknown_airports_are_skipped():
    cfg = dict(CONFIG, countries={"GR": 1.0})
    assert hydrotour.to_offers(DATA, cfg) == []
    data = json.loads(json.dumps(DATA))
    for t in data["terminy"]:
        for od in t["odlety"]:
            od["letisko1"] = 99
    assert hydrotour.to_offers(data, CONFIG) == []


def test_request_body_and_windows():
    b = hydrotour.body(CONFIG, date(2027, 7, 8))
    assert b["cestujuci"] == [[18, 10, 12]] and b["datumOd"] == "2027-07-08"
    assert b["dni"] == list(range(8, 16)) and b["terminyPocet"] == 3
    w = hydrotour.windows(CONFIG)
    assert w[0] == date(2027, 7, 1) and w[-1] <= CONFIG["date_to"] and len(w) == 9
    two = party_cfg(CONFIG, {"id": party_id(2, []), "adults": 2, "children_ages": [], "children_birthdates": []})
    assert hydrotour.cestujuci(two) == [[18, 18]]
    assert hydrotour.to_offers(DATA, two)[1]["price_total"] == round(1493.3 * 2)


def test_watch_routes():
    routes = hydrotour.parse_routes((FX / "hydrotour_routes.html").read_text())
    assert ("/dovolenky/turecko/side/royal-alhambra-palace", 215, "royal alhambra palace") in routes
    hits = hydrotour.watched_routes(routes, ["Royal Alhambra"])
    assert [i for _, i, _ in hits] == [215]
    # "Alhambra" alone also matches the Tunisian Alhambra Thalasso (run.py re-checks the country of @XX terms)
    assert {i for _, i, _ in hydrotour.watched_routes(routes, ["Alhambra"])} == {215, 832}
    links = hydrotour.watch_links(CONFIG, "Royal Alhambra", [])
    assert links and links[0]["url"].startswith("https://www.hydrotour.sk/dovolenky/turecko/side/royal-alhambra")


def test_deeplinks():
    links = hydrotour.deeplinks(CONFIG)
    assert all(d["url"].startswith("https://www.hydrotour.sk/") for d in links)
    assert "cestujuci=dospely%2Cdieta-10%2Cdieta-12" in links[0]["url"]
