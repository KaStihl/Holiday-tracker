import json
from datetime import date
from pathlib import Path

from adapters import firotour, koala
from common import Robots
from config import CONFIG
import run

FX = Path(__file__).parent / "fixtures"
# Trimmed copy of the real https://koala.redred.sk/json/encoded/tree.json (2026-10-25): a few destinations,
# at most 3 terms per hotel, one hotel without terms.
TREE = (FX / "koala_tree.json").read_text()

KOALA_ROBOTS = """User-agent: *
Allow: /

Disallow: /*?date=*
Disallow: *=date&date=*
Disallow: *&query=*
Disallow: /*?destinationId=*
Disallow: /*?DestinationRootID=*
Disallow: *&transportationId=*
Disallow: /*?DestinationID=*
Disallow: /objednavka/
Disallow: /objednavka
Disallow: /partner
"""


def test_dictionary_matches_the_site_keys():
    d = koala.dictionary()
    # keys seen in the real file: d=category, h=destinations, l=hotels, o=id, t=name, F=terms, L=url, M=videoId
    assert (d["d"], d["h"], d["l"], d["o"], d["t"], d["F"], d["L"], d["M"]) == (
        "category", "destinations", "hotels", "id", "name", "terms", "url", "videoId")
    # Slovak collation: 'ch' sorts after 'h' -> childAge between hours (m) and id (o)
    assert (d["m"], d["n"], d["y"], d["z"], d["J"]) == ("hours", "childAge", "price", "room", "transportationId")
    assert koala._key(53) == "_" and koala._key(54) == "aa"


def test_parse_tree_and_offers():
    dests = koala.parse_tree(TREE)
    hotels = {h["name"]: (names, top) for h, names, top in koala.iter_hotels(dests)}
    assert hotels["Barceló Playa Blanca"] == (["Španielsko", "Lanzarote", "Playa Blanca"], "spanielsko-a-ostrovy")
    offers = koala.offers_from_tree(dests, CONFIG)
    # pilgrimage (663), sightseeing (542) and the 2-person rooms are skipped; 2 Barceló rooms for 3 persons remain
    assert {o["hotel"] for o in offers} == {"Barceló Playa Blanca"} and len(offers) == 2
    o = offers[0]
    assert o["url"] == "https://koala.sk/dovolenka/spanielsko-a-ostrovy/barcelo-playa-blanca"
    assert (o["country_code"], o["region"], o["place"], o["board"], o["departure"]) == (
        "ES", "Lanzarote", "Playa Blanca", "UAI", "BTS")
    assert (o["date_from"], o["date_to"], o["nights"], o["stars"]) == ("2026-10-26", "2026-11-02", 7, 5)
    assert (o["price_total"], o["price_original"], o["discount_pct"]) == (1840 * 3, None, 35)
    assert o["discount_label"] == "Zľava 35 % (cena za os. × 3, orientačne)"
    assert o["image"] == "https://koala.sk/FileHandler.ashx?FileID=1821676&FormatID=19"
    # October 2026 is outside Jul–Aug 2027, and 5520 € is over the cap anyway
    assert run.normalise(o, "koala", koala.NAME, CONFIG) is None
    summer = dict(o, date_from="2027-07-10", date_to="2027-07-17", price_total=2900)
    kept = run.normalise(summer, "koala", koala.NAME, CONFIG)
    assert kept and kept["discount_pct"] == 35 and kept["price_exact"] is False


def test_room_capacity_and_departure():
    dests = koala.parse_tree(TREE)
    salamis = next(h for h, _, _ in koala.iter_hotels(dests) if h["name"] == "Salamis Bay Conti")
    t = salamis["terms"][0]
    assert not koala.fits(t, CONFIG)  # 2-person room
    big = dict(t, room=dict(t["room"], personCount=3, adultCount=3))
    o = koala.to_offer(salamis, ["Severný Cyprus", "Famagusta"], "severny-cyprus", big, CONFIG)
    assert (o["country_code"], o["departure"], o["board"], o["nights"]) == ("CY", "KSC", "UAI", 7)


def test_search_uses_one_robots_allowed_request(monkeypatch):
    calls = []
    monkeypatch.setattr(koala, "get", lambda url, **kw: calls.append(url) or TREE)
    assert len(koala.search(CONFIG)) == 2 and calls == [koala.TREE_URL]


def test_off_season_tree_is_empty():
    empty = json.dumps({"createdAt": 1, "encoded": json.loads(TREE)["encoded"][-1:]})
    assert koala.offers_from_tree(koala.parse_tree(empty), CONFIG) == []


def test_koala_robots_block_filters_but_not_the_data_file():
    rp = Robots(KOALA_ROBOTS, "dovolenka-tracker")
    assert not rp.can_fetch("https://koala.sk/vyhladavanie?destinationId=72")
    assert not rp.can_fetch("https://koala.sk/more?date=1756677600000,1759183200000")
    assert not rp.can_fetch("https://koala.sk/objednavka-prv/x/?DestinationID=1&StationID=2")
    assert rp.can_fetch("https://koala.sk/dovolenka/turecko/alba-resort")
    # tree.json lives on koala.redred.sk, whose robots.txt is 404 (= everything allowed)
    assert Robots("", "dovolenka-tracker").can_fetch(koala.TREE_URL)


def test_firotour_stays_links_only():
    assert firotour.DEEPLINK_ONLY and firotour.search(CONFIG) == []
    assert all(d["url"].startswith("https://") for d in firotour.deeplinks(CONFIG))
    assert date(2025, 12, 15) < date.today()  # the .cz certificate expiry documented in the module
