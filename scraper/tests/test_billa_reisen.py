from pathlib import Path

from adapters import billa_reisen
from config import CONFIG
import run

FX = Path(__file__).parent / "fixtures"


def test_query_uses_criteria_and_two_adults():
    q = billa_reisen.query(CONFIG, "3380096", 1)
    assert (q["pdf"], q["pdaf"], q["psdf"], q["pedf"]) == ("3380096", "VIE", "2027-07-01", "2027-08-31")
    assert (q["pnnfl"], q["pnnfh"], q["na"], q["pna"], q["pbtf"], q["ps"], q["ppn"]) == (7, 14, 2, 2, "ai", "pr", 1)
    assert "ppn" not in billa_reisen.query(CONFIG, "3380096") and "pdf" not in billa_reisen.query(CONFIG)


def test_parse_real_result_page():
    offers, pages = billa_reisen.parse_page((FX / "billa_tuerkei.html").read_text(), CONFIG)
    assert pages == 6 and len(offers) == 4
    o = offers[0]
    assert o["hotel"] == "Kaila City Hotel" and o["url"].startswith("https://www.billareisen.at/Reisen/Kaila+City+Hotel-")
    assert (o["country_code"], o["region"], o["place"], o["stars"], o["rating"]) == ("TR", "Türkische Riviera", "Alanya", 4.0, 9.2)
    assert (o["date_from"], o["date_to"], o["nights"], o["board"], o["departure"]) == ("2027-08-05", "2027-08-12", 7, "AI", "VIE")
    # "p.P. ab € 672,-" at 2 adults x party of 3 (1 adult + 2 children), strike price 814 x 3
    assert (o["price_total"], o["price_original"]) == (2016, 2442)
    assert o["price_note"] == "orientačne: cena za osobu pri 2 dospelých × 3" and "orientačne" in o["discount_label"]
    kept = run.normalise(o, "billa_reisen", billa_reisen.NAME, CONFIG)
    assert kept and kept["price_exact"] is False and kept["continent"] == "Európa" and kept["discount_pct"] == 17


def test_plan_covers_configured_countries_once():
    plan = billa_reisen.plan(CONFIG)
    firsts = [c for c, d, p in plan if p == 0]
    assert firsts[0] in ("HR", "TR", "CY", "IT") and len(firsts) == len({d for c, d, p in plan})
    assert all(c in CONFIG["countries"] for c in firsts)
    assert len(plan) <= billa_reisen.MAX_CALLS


def test_board_and_country_names():
    assert billa_reisen.board_of("Alles Inklusive plus") == "AI" and billa_reisen.board_of("Ultra All Inclusive") == "UAI"
    assert billa_reisen.board_of("Halbpension") == "HB" and billa_reisen.board_of("Frühstück") == "BB"
    assert billa_reisen.country_of("Ägypten • Rotes Meer • Hurghada") == "EG"
    assert billa_reisen.country_of("Vereinigte Arabische Emirate • Dubai") == "AE"
