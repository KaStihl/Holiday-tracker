"""nastavenia.yml: loading, validation, derived values and the party-size labels everything else uses."""

from datetime import date
from pathlib import Path

import pytest
import yaml

import config
import notify
import run
from adapters import cedok, dertour, koala, satur, tiptravel
from config import CONFIG

ROOT = Path(__file__).resolve().parents[2]
FX = Path(__file__).parent / "fixtures"


def raw(**kw):
    r = yaml.safe_load((FX / "nastavenia_test.yml").read_text(encoding="utf-8"))
    r.update(kw)
    return r


def test_repo_settings_file_loads():
    c = config.load(ROOT / "nastavenia.yml")
    for k in ("adults", "children_ages", "date_from", "date_to", "nights_min", "nights_max", "budget",
              "price_cap", "departures", "transports", "dogs", "countries", "children_birthdates"):
        assert k in c
    assert set(c["countries"]) <= set(config.COUNTRY_NAMES)


def test_pinned_test_settings():
    assert (CONFIG["adults"], CONFIG["children_ages"], CONFIG["budget"], CONFIG["price_cap"]) == (1, [10, 12], 3000, 6000)
    assert CONFIG["date_from"] == date(2027, 7, 1) and CONFIG["transports"] == ["flight", "car"]
    assert {"AE", "MV", "TH", "MX", "DO", "TZ", "EG", "TN", "MA"} <= set(CONFIG["countries"])


def test_birthdates_keep_the_age_for_the_whole_season():
    c = config.validate(raw())
    assert c["children_birthdates"] == ["2017-06-30", "2015-06-30"]
    for age, bd in zip(c["children_ages"], c["children_birthdates"]):
        born = date.fromisoformat(bd)
        for day in (c["date_from"], c["date_to"], date(2027, 9, 14)):  # last departure + 14 nights
            assert cedok._age(born, day) == age
    assert config.birthdate(4, date(2028, 2, 29)) == "2024-02-28"


@pytest.mark.parametrize("bad,msg", [
    ({"adults": 0}, "adults"),
    ({"adults": "jeden"}, "celé číslo"),
    ({"children_ages": [10, 25]}, "children_ages"),
    ({"children_ages": 10}, "zoznam"),
    ({"date_from": "1.7.2027"}, "RRRR-MM-DD"),
    ({"date_to": "2027-06-01"}, "date_to"),
    ({"nights_min": 10, "nights_max": 7}, "nights_max"),
    ({"budget": 5000, "price_cap": 4000}, "price_cap"),
    ({"departures": []}, "departures"),
    ({"departures": ["Bratislava"]}, "departures"),
    ({"transports": ["bus"]}, "transports"),
    ({"boards_preferred": ["XX"]}, "boards_preferred"),
    ({"destinations": {"ZZ": 1}}, "ZZ"),
    ({"destinations": {"TR": 3}}, "TR"),
    ({"price_kap": 1}, "preklep"),
])
def test_validation_errors_are_clear(bad, msg):
    with pytest.raises(config.SettingsError, match=msg):
        config.validate(raw(**bad))


def test_missing_and_broken_file(tmp_path):
    r = raw()
    del r["budget"]
    with pytest.raises(config.SettingsError, match="chýbajú položky: budget"):
        config.validate(r)
    p = tmp_path / "nastavenia.yml"
    p.write_text("adults: [1\n")
    with pytest.raises(config.SettingsError, match="nastavenia.yml: chybný formát YAML"):
        config.load(p)


def test_no_children_and_codes_normalised():
    c = config.validate(raw(children_ages=[], departures="bts, vie", transports="flight"))
    assert c["children_ages"] == [] and c["children_birthdates"] == []
    assert c["departures"] == ["BTS", "VIE"] and c["transports"] == ["flight"]
    assert config.party_label(c) == "1 dospelý" and config.party_size(c) == 1


def test_party_labels():
    assert config.party_label(CONFIG) == "1 dospelý + 2 deti (10 a 12 r.)"
    assert config.party_label(CONFIG, "gen") == "1 dospelého + 2 detí (10 a 12 r.)"
    big = config.validate(raw(adults=2, children_ages=[3, 8, 12]))
    assert config.party_label(big) == "2 dospelí + 3 deti (3, 8, 12 r.)" and config.party_short(big) == "2+3"
    assert config.approx_note(big) == "orientačne: cena za osobu pri 2 dospelých × 5"
    assert config.period_label(CONFIG) == "júl–aug"


def test_criteria_contract_for_the_frontend():
    c = config.criteria_for_display(CONFIG)
    for k in ("adults", "children_ages", "date_from", "date_to", "nights_min", "nights_max", "budget",
              "price_cap", "departures", "transports", "dogs"):
        assert k in c
    assert c["date_from"] == "2027-07-01" and c["party_size"] == 3
    assert {d["continent"] for d in c["destinations"]} == set(config.CONTINENTS)
    import json
    json.dumps(c)  # serialisable


def test_continent_table():
    assert set(config.CONTINENT_OF.values()) == set(config.CONTINENTS)
    assert set(config.CONTINENT_OF) == set(config.COUNTRY_NAMES)
    assert config.continent("HR") == "Európa" and config.continent("EG") == "Afrika"
    assert config.continent("AE") == "Blízky východ" and config.continent("MV") == "Indický oceán"
    assert config.continent("TH") == "Ázia" and config.continent("DO") == "Karibik a Amerika"
    assert config.continent(None) == "Európa"


# --- the party size really drives every price and label -------------------------------------------------

FAMILY = config.validate(raw(adults=2, children_ages=[5, 7, 9], price_cap=9000))  # 5 persons


def test_satur_scales_by_party():
    card = satur.parse_cards((FX / "satur_so_psom_summer.html").read_text())[1]
    o = satur.to_offer(card, "car", True, config.party_size(FAMILY))
    assert o["price_total"] == 1248 * 5 and "× 5" in o["discount_label"] and o["price_note"].endswith("× 5")
    kept = run.normalise(o, "satur", "Satur.sk", FAMILY)
    assert kept["price_note"] == "orientačne: cena za osobu pri 2 dospelých × 5" and kept["continent"] == "Európa"


def test_cedok_scales_by_party_and_asks_detail_for_it():
    rates, _, links = cedok.parse_page((FX / "cedok_turecko.html").read_text())
    o = cedok.to_offer(rates[1], links, FAMILY)
    assert o["price_total"] == round(1565 / 2 * 5) and "× 5" in o["discount_label"]
    u = cedok.occupancy_url(o["url"], FAMILY)
    assert "participants%5B0%5D%5Badults%5D=2" in u and "participants%5B0%5D%5Bchildren%5D%5B2%5D=" in u
    # the listing priced 2 adults: for a 2-adult, no-children party that is the exact price
    duo = config.validate(raw(adults=2, children_ages=[]))
    r = dict(rates[1], participants=[{"type": "adult"}, {"type": "adult"}])
    o = cedok.to_offer(r, links, duo)
    assert o["price_exact"] is True and o["price_total"] == 1565


def test_dertour_query_and_approximation_use_the_party():
    q = dertour.query(FAMILY)
    assert (q["ac1"], q["kc1"], q["ka1"]) == (2, 3, "5|7|9")
    assert "ka1" not in dertour.query(config.validate(raw(children_ages=[])))
    assert "m" not in dertour.query(config.validate(raw(boards_preferred=["HB", "AI"])))
    assert "2 dospelí + 3 deti (5, 7, 9 r.)" in dertour.deeplinks("https://x", "/y", FAMILY)[0]["label"]


def test_koala_and_tip_scale_by_party():
    term = {"date": [20270710, 20270717], "price": 500, "transportationId": 201, "service": "AI",
            "room": {"adultCount": 2, "personCount": 5}}
    o = koala.to_offer({"name": "H", "category": koala.CATEGORY_SEASIDE, "url": "h"}, ["Turecko"], "turecko",
                       term, FAMILY)
    assert o["price_total"] == 2500 and o["price_note"] == "orientačne: cena za osobu × 5"
    it = {"transportationType": "airplane", "productType": "pobytove", "price": "700", "days": 8,
          "accommodationName": "H", "url": "https://tiptravel.sk/h", "dateFrom": "2027-07-10", "dateTo": "2027-07-17"}
    assert tiptravel.to_offer(it, tiptravel.HOME, 5)["price_total"] == 3500


def test_normalise_follows_transports_dogs_and_departures():
    base = {"hotel": "H", "country": "Maldivy", "board": "HB", "transport": "flight", "departure": "VIE",
            "date_from": "2027-07-10", "nights": 9, "price_total": 5400, "url": "https://example.com/x"}
    o = run.normalise(base, "t", "T", CONFIG)
    assert (o["country_code"], o["continent"], o["country"]) == ("MV", "Indický oceán", "Maldivy")
    assert run.normalise(dict(base, departure="PRG"), "t", "T", CONFIG) is None
    assert run.normalise(dict(base, departure="BUD"), "t", "T", CONFIG)  # secondary airport is fine
    assert run.normalise(base, "t", "T", dict(CONFIG, transports=["car"])) is None
    car = dict(base, transport="car", departure=None, pets_allowed=False, country="Chorvátsko")
    assert run.normalise(car, "t", "T", CONFIG) is None
    assert run.normalise(car, "t", "T", dict(CONFIG, dogs=0))
    assert run.normalise(dict(base, price_total=6100), "t", "T", CONFIG) is None  # above price_cap


def test_digest_texts_follow_the_party():
    o = {"id": "a", "price_total": 2500, "board": "AI", "hotel": "Ha", "url": "https://x/a", "place": "Side",
         "country": "Turecko", "date_from": "2027-07-10", "nights": 7, "transport": "flight", "departure": "BTS",
         "source_name": "T", "score": 50, "price_exact": True}
    _, body = notify.digest({}, {"offers": [o]}, 3000, FAMILY)
    assert "Ceny sú za 2 dospelých + 3 detí (5, 7, 9 r.)" in body and "presná cena 2+3" in body and "× 5" in body
