import json
from pathlib import Path

from adapters import ruefa
from config import CONFIG
import run

FX = Path(__file__).parent / "fixtures"


def test_form_asks_for_the_party_and_one_stay_length():
    f = ruefa.form(CONFIG, "1670 1650", 10, 2)
    assert (f["adults"], f["children"], f["anzZimmer"]) == ("1", "10-12", "1")
    assert (f["start"], f["until"], f["airport"], f["dauer"]) == ("2027-07-01", "2027-08-31", "VIE-BTS", "1024")
    # the region ids go to "destination" (ids in "destinationId" are ignored by deliver.php)
    assert (f["destination"], f["destinationId"], f["page"], f["level"], f["sort"], f["verpflegung"]) == \
        ("1670 1650", "", "2", "2", "price", "AI AIP AIU AIR")
    assert ruefa.stays(CONFIG) == [7, 10, 14]


def test_parse_real_deliver_answer_exact_party_prices():
    # deliver.php answer for adults=1, children=10-12 (worldwide, any board), trimmed to 3 cards
    data = json.loads((FX / "ruefa_deliver.json").read_text())
    offers = ruefa.parse(data, CONFIG)
    assert [o["hotel"] for o in offers] == ["Evridika", "Anemoessa Studios", "Alexandra beach"]
    o = offers[0]
    assert o["url"].startswith("https://pauschal.ruefa.at/index.php?page=hotel&") and "children=12-10" in o["url"]
    assert (o["country_code"], o["region"], o["place"], o["stars"]) == ("BG", "Bulgarische Riviera Süden (Burgas)",
                                                                        "Nessebar", 3.0)
    assert (o["date_from"], o["date_to"], o["nights"], o["departure"], o["board"]) == \
        ("2027-07-11", "2027-07-21", 10, "VIE", "RO")
    assert o["price_total"] == 1684 and o["price_exact"] is True  # "Gesamtpreis" for 1 adult + kids 10 and 12
    a = offers[2]
    assert (a["country_code"], a["board"], a["price_total"], a["price_original"]) == ("GR", "BB", 2372, 2512)
    kept = run.normalise(a, "ruefa", ruefa.NAME, CONFIG)
    assert kept and kept["price_exact"] is True and kept["price_note"] is None and kept["discount_pct"] == 6


def test_cards_for_another_party_are_dropped():
    data = json.loads((FX / "ruefa_deliver.json").read_text())
    other = dict(CONFIG, children_ages=[5])
    assert ruefa.parse(data, other) == []


def test_plan_starts_with_every_country_once():
    plan = ruefa.plan(CONFIG)
    n = len({c for c, _, _ in plan})
    first = [c for c, _, _ in plan[:n]]
    assert len(set(first)) == n and first[0] in ("HR", "TR", "CY", "IT")
    assert set(first) == {c for c in CONFIG["countries"] if c in ruefa.COUNTRY_NAMES}
    nights = {c: d for c, d, _ in plan[:n]}
    assert nights["TR"] == 7 and nights["MV"] == 8  # overnight flight counts as a travel night outside Europe


def test_lookup_reads_the_country_entry(monkeypatch):
    answer = [{"name": "<b>Länder</b>", "id": 0, "headline": 1},
              {"name": "Türkei", "id": " 1670 1650 1444", "country": 1},
              {"field": "hotelname", "name": "Anemon Manisa<span> Türkei</span>", "id": 204595}]
    monkeypatch.setattr(ruefa, "get", lambda *a, **k: answer)
    assert ruefa.lookup("TR") == ("1670 1650 1444", 1)
    monkeypatch.setattr(ruefa, "get", lambda *a, **k: [])
    assert ruefa.lookup("AE") == (None, 1 + len(ruefa.ALT_NAMES["AE"]))
