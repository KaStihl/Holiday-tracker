from pathlib import Path

from adapters import satur
from config import CONFIG
import run

FX = Path(__file__).parent / "fixtures"


def test_parse_cards_car_dogs():
    cards = satur.parse_cards((FX / "satur_so_psom.html").read_text())
    assert len(cards) == 3
    c = cards[1]
    assert c["hotel"] == "Aminess Vival Velaris Resort"
    assert c["url"] == "https://www.satur.sk/produkt/aminess-vival-velaris-resort"
    assert (c["price_person"], c["price_person_original"], c["price_group"]) == (188, 269, 376)
    assert (c["nights"], c["stars"], c["rating"]) == (4, 4.0, 9.0)
    assert (c["country"], c["region"], c["place"]) == ("Chorvátsko", "Ostrov Brač", "Supetar")
    o = satur.to_offer(c, "car", True, 3)
    assert o["transport"] == "car" and o["pets_allowed"] is True and o["departure"] is None
    assert (o["date_from"], o["date_to"], o["board"]) == ("2026-10-24", "2026-10-28", "HB")
    assert (o["price_total"], o["price_original"]) == (564, 807)


def test_parse_cards_flight():
    cards = satur.parse_cards((FX / "satur_letecky.html").read_text())
    o = satur.to_offer(cards[1], "flight", None, 3)
    assert o["hotel"] == "Hotel Kouros Palace Active Lifestyle" and o["country_code"] == "GR"
    assert (o["transport"], o["departure"], o["board"], o["nights"]) == ("flight", "BTS", "AI", 7)
    assert (o["date_from"], o["price_total"]) == ("2027-09-11", 3459)
    # September is outside the Jul–Aug window, so run.py drops it
    assert run.normalise(o, "satur", "Satur.sk", CONFIG) is None
    jul = dict(o, date_from="2027-07-11", date_to="2027-07-18")
    assert run.normalise(jul, "satur", "Satur.sk", CONFIG)["price_total"] == 3459


def test_year_crossing_dates():
    assert satur._dates("28.12. - 4.1.2027")[0].isoformat() == "2026-12-28"


def test_pets_from_perks():
    cards = satur.parse_cards((FX / "satur_so_psom.html").read_text())
    assert all(c["pets"] for c in cards)
    o = satur.to_offer(cards[0], "car", None, 3)  # e.g. a /vlastna page: perks still say "so psom"
    assert o["pets_allowed"] is True


def test_deeplinks_and_pages():
    assert all(d["url"].startswith("https://www.satur.sk/") for d in satur.deeplinks(CONFIG))
    assert all(p[1] in ("car", "flight") for p in satur.PAGES)


def test_summer_listing_passes_the_criteria():
    # ?termin=01.07.2027-31.08.2027&dlzka-pobytu=7: every card is a 7-night Jul–Aug term
    cards = satur.parse_cards((FX / "satur_so_psom_summer.html").read_text())
    offers = [satur.to_offer(c, "car", True, 3) for c in cards]
    kept = [run.normalise(o, "satur", "Satur.sk", CONFIG) for o in offers]
    assert len(kept) == 3 and all(kept)
    assert {(k["transport"], k["nights"], k["pets_allowed"], k["country_code"]) for k in kept} == {("car", 7, True, "HR")}
    assert kept[1]["hotel"] == "Hotel Medora Auri Family Beach Resort" and kept[1]["date_from"] == "2027-07-01"
    assert kept[1]["price_total"] == 1248 * 3 and kept[1]["board"] == "HB"
    # same hotel + date twice (two apartment types): run.py keeps the cheaper one under one id
    assert kept[0]["id"] == kept[2]["id"] and kept[2]["price_total"] < kept[0]["price_total"]


def test_search_reports_total_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("403 blocked")
    monkeypatch.setattr(satur, "get", boom)
    try:
        satur.search(CONFIG)
    except RuntimeError as e:
        assert "403 blocked" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


def test_search_uses_summer_filter(monkeypatch):
    calls = []
    html = (FX / "satur_so_psom_summer.html").read_text()
    monkeypatch.setattr(satur, "get", lambda url, params=None: calls.append((url, params)) or html)
    offers = satur.search(CONFIG)
    n = sum(t in budget for _, budget in satur.STAYS for _, t, _, _ in satur.PAGES)  # 3 cards < 20: no page 2
    far = len(satur.FAR)  # one page per long-haul country, every allowed length at once
    assert len(calls) == n + far and len(offers) == 3 * (n + far)
    assert len(calls) <= 80  # polite
    assert calls[0][1] == {"termin": "01.07.2027-31.08.2027", "dlzka-pobytu": 7}
    assert {c[1]["dlzka-pobytu"] for c in calls} == {7, "10,11", 14, "7,8,9,10,11,12,13,14"}
    assert calls[-1][0] == satur.HOME + "/dovolenka/kuba/letecky"
    # no 10–11 night car terms exist, so car pages are only asked for 7 and 14 nights
    car = {p for p, t, _, _ in satur.PAGES if t == "car"}
    assert not [c for c in calls if c[1]["dlzka-pobytu"] == "10,11" and c[0].removeprefix(satur.HOME) in car]


def test_14_night_car_listing():
    # ?dlzka-pobytu=14: Sat–Sat fortnights; the 2-person apartment at 1480 €/os. stays under the cap
    cards = satur.parse_cards((FX / "satur_so_psom_14.html").read_text())
    kept = [run.normalise(satur.to_offer(c, "car", True, 3), "satur", "Satur.sk", CONFIG) for c in cards]
    assert [k and k["nights"] for k in kept] == [14, None, 14, 14]  # Medora Auri: 7866 € is over the cap
    k = kept[3]
    assert k["hotel"] == "Zaton (mobilné domčeky)" and (k["date_from"], k["date_to"]) == ("2027-08-17", "2027-08-31")
    assert (k["price_total"], k["price_original"]) == (836 * 3, 1195 * 3)
    assert k["discount_label"] == "Zľava (cena za os. × 3, orientačne)" and k["transport"] == "car"


def test_10_11_night_flight_listing():
    # ?dlzka-pobytu=10,11 (a comma list; "10-11" is ignored by the site)
    cards = satur.parse_cards((FX / "satur_letecky_10_11.html").read_text())
    offers = [satur.to_offer(c, "flight", None, 3) for c in cards]
    assert [(o["nights"], o["departure"], o["board"]) for o in offers] == [(10, "BTS", "AI")] * 3
    o = offers[0]
    assert o["hotel"] == "Hotel Jaz Tamerina" and (o["date_from"], o["date_to"]) == ("2027-07-07", "2027-07-17")
    assert o["price_total"] == 1651 * 3  # 4953 € is over the 4500 € cap ...
    cap = dict(CONFIG, price_cap=4500)
    assert run.normalise(o, "satur", "Satur.sk", cap) is None
    assert run.normalise(dict(o, price_total=4400), "satur", "Satur.sk", cap)["nights"] == 10  # ... not the length


def test_paging_stops_on_length_fallback(monkeypatch):
    # a page with no term of the asked length (site fell back to 7 nights) is not paged further
    cards = satur.parse_cards((FX / "satur_so_psom_summer.html").read_text())  # 7-night terms
    calls = []
    monkeypatch.setattr(satur, "parse_cards", lambda h: cards * 7)  # 21 cards: a "full" page
    monkeypatch.setattr(satur, "get", lambda url, params=None: calls.append(params) or "")
    satur.search(CONFIG)
    assert not [p for p in calls if p["dlzka-pobytu"] == 14 and "stranka" in p]
    assert [p for p in calls if p["dlzka-pobytu"] == 7 and "stranka" in p]


def test_search_follows_settings(monkeypatch):
    calls = []
    monkeypatch.setattr(satur, "get", lambda url, params=None: calls.append(url) or "")
    # no car, only Turkey and the Maldives
    satur.search(dict(CONFIG, transports=["flight"], countries={"TR": 1.0, "MV": 0.6}))
    paths = {u.removeprefix(satur.HOME) for u in calls}
    assert not [p for p in paths if "so-psom" in p or "vlastna" in p]
    assert "/dovolenka/turecko/letecky/z-bratislavy/all-inclusive" in paths
    assert "/dovolenka/grecko/letecky/z-bratislavy/all-inclusive" not in paths
    assert "/dovolenka/maldivy/letecky" in paths and "/dovolenka/thajsko/letecky" not in paths
    # car without dogs: the so-psom listings are not needed
    calls.clear()
    satur.search(dict(CONFIG, transports=["car"], dogs=0))
    assert calls and not [u for u in calls if "so-psom" in u] and not [u for u in calls if "letecky" in u]
