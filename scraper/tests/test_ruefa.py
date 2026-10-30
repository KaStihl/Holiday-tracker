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


def test_watch_lookup_reads_hotel_ids_from_the_autocomplete(monkeypatch):
    # getDestination.php?destination=Sural, real answer 2026-10-30
    answer = json.loads((FX / "ruefa_autocomplete_sural.json").read_text())
    monkeypatch.setattr(ruefa, "get", lambda *a, **k: answer)
    assert ruefa.watch_lookup("Sural") == [("53099", "Sural Resort"), ("4924", "Sural Saray"),
                                           ("4923", "Sural Garden"), ("4922", "Sural Hotel")]
    assert ruefa.watch_lookup("Royal Alhambra") == []  # names the term doesn't match are not taken


def test_watch_form_asks_the_hotel_ids_any_board():
    f = ruefa.watch_form(CONFIG, ["53099", "239871"], 7, *ruefa.watch_windows(CONFIG)[0])
    assert (f["gid"], f["destination"], f["verpflegung"], f["children"], f["airport"], f["dauer"]) == \
        ("53099 239871", "", "", "10-12", "VIE-BTS", "128")
    assert ruefa.watch_windows(CONFIG)[-1][1].isoformat() == "2027-08-31"


def test_watch_parse_real_answer_keeps_asked_hotels_only():
    # deliver.php for gid=4923 4922 53099 4924 239871, 7 nights, trimmed to Süral Resort + Royal Alhambra Palace
    data = json.loads((FX / "ruefa_watch_deliver.json").read_text())
    offers = ruefa.watch_parse(data, CONFIG, {"53099", "239871"})
    assert [(o["hotel"], o["price_total"], o["nights"], o["date_from"]) for o in offers] == \
        [("Süral Resort", 2438, 7, "2027-07-01"), ("Royal Alhambra Palace", 3407, 7, "2027-07-01")]
    assert all(o["price_exact"] and o["country_code"] == "TR" and o["departure"] == "VIE" for o in offers)
    assert [o["hotel"] for o in ruefa.watch_parse(data, CONFIG, {"239871"})] == ["Royal Alhambra Palace"]
    # a hotel without offers: resultCount 0 plus unrelated fallback cards -> nothing
    fallback = json.loads((FX / "ruefa_deliver.json").read_text())
    assert ruefa.watch_parse(dict(fallback, resultCount=0), CONFIG, {"4924"}) == []
    assert ruefa.watch_parse(fallback, CONFIG, {"4924"}) == []


def test_watch_hook_budget_and_watch_rule(monkeypatch):
    cfg = dict(CONFIG, watched=["Sural", "Royal Alhambra"])
    ac = json.loads((FX / "ruefa_autocomplete_sural.json").read_text())
    data = json.loads((FX / "ruefa_watch_deliver.json").read_text())
    calls = []

    def fake(url, **kw):
        calls.append(kw.get("data") or kw.get("params"))
        if "getDestination" in url:
            return ac if kw["params"]["destination"] == "Sural" else []
        return data

    monkeypatch.setattr(ruefa, "get", fake)
    offers = ruefa.watch(cfg, cfg["watched"], {})
    assert len(calls) <= ruefa.WATCH_CALLS
    # Royal Alhambra: autocomplete empty -> cached id
    assert calls[-1]["gid"] == "53099 4924 4923 4922 239871"
    assert len(offers) == 2 * len(ruefa.stays(cfg)) * len(ruefa.watch_windows(cfg))
    kept = [run.normalise(o, "ruefa", ruefa.NAME, cfg) for o in offers]
    alh = next(k for k in kept if k and k["hotel"] == "Royal Alhambra Palace")
    assert alh["watched"] == "Royal Alhambra" and alh["price_exact"] is True
    assert ruefa.watch(dict(cfg, transports=["car"]), cfg["watched"], {}) == []
