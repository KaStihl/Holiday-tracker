"""Watched hotels (sledovane_hotely): normalisation, matching, settings, keep-above-cap, adapter lookups, digest."""

import json
from pathlib import Path

import pytest
import yaml

import config
import notify
import run
import watch
from adapters import cedok, dertour, fischer, kartago, satur
from config import CONFIG

FX = Path(__file__).parent / "fixtures"


def raw_settings(**kw):
    r = yaml.safe_load((FX / "nastavenia_test.yml").read_text(encoding="utf-8"))
    r.update(kw)
    return r


# --- normalisation / matching ----------------------------------------------------------------------------------

def test_norm_name_strips_accents_case_and_filler_words():
    assert watch.norm_name("Hotel Süral Hotel") == "sural"
    assert watch.norm_name("SURAL Resort & Spa") == "sural"
    assert watch.norm_name("Sural Saray") == "sural saray"
    assert watch.norm_name("Alhambra Beach Hotel") == "alhambra beach"
    assert watch.norm_name("Kıbrıs Hotel") == "kibris"  # Turkish dotless i
    assert watch.norm_name("Hotel & Resort") == ""


def test_match_partial_names_at_word_start():
    terms = ["Sural Resort", "Alhambra"]
    assert watch.match("Hotel Sural Hotel", terms) == "Sural Resort"
    assert watch.match("Hotel Süral Saray", terms) == "Sural Resort"
    assert watch.match("Club Alhambra Thalasso", terms) == "Alhambra"
    assert watch.match("Hotel Kasural Beach", terms) is None  # not at a word start
    assert watch.match("Hotel Saray", terms) is None
    assert watch.match(None, terms) is None and watch.match("Sural", []) is None
    assert watch.match("Seashell Resort & Spa", ["sea shell"]) is None
    assert watch.match("Sural Saray", ["sural saray"]) == "sural saray"


# --- settings ---------------------------------------------------------------------------------------------------

def test_settings_watched_list():
    assert CONFIG["watched"] == ["Sural", "Alhambra"]
    assert config.validate(raw_settings(sledovane_hotely=None))["watched"] == []
    assert config.validate(raw_settings(sledovane_hotely=[]))["watched"] == []
    assert config.validate(raw_settings(sledovane_hotely="Sural"))["watched"] == ["Sural"]
    c = config.validate(raw_settings(sledovane_hotely=["  Sural   Saray ", "sural saray", "", "Rixos", 1001]))
    assert c["watched"] == ["Sural Saray", "Rixos", "1001"]  # stripped, deduplicated after normalising
    assert "watched" in config.criteria_for_display(c)


@pytest.mark.parametrize("bad", [{"Sural": 1}, [["Sural"]], ["Hotel Resort"], ["x" * 61], [True], ["h%d" % i for i in range(21)]])
def test_settings_watched_invalid(bad):
    with pytest.raises(config.SettingsError, match="sledovane_hotely"):
        config.validate(raw_settings(sledovane_hotely=bad))


def test_repo_settings_watch_list_is_valid():
    # The user edits nastavenia.yml on GitHub, so only check that it loads, not which hotels it lists.
    c = config.load(Path(__file__).resolve().parents[2] / "nastavenia.yml")
    assert all(isinstance(t, str) and t for t in c["watched"])


# --- keep-above-cap rule ----------------------------------------------------------------------------------------

def _raw(**kw):
    o = {"hotel": "Hotel Sural Hotel", "country": "Turecko", "place": "Side", "board": "All Inclusive",
         "transport": "flight", "departure": "BTS", "date_from": "2027-07-10", "nights": 7, "price_total": 2500,
         "url": "https://example.com/x"}
    o.update(kw)
    return o


def test_watched_offer_kept_above_cap_up_to_twice():
    cap = CONFIG["price_cap"]
    n = run.normalise(_raw(), "t", "T", CONFIG)
    assert n["watched"] == "Sural" and "over_cap" not in n
    over = run.normalise(_raw(price_total=cap + 1), "t", "T", CONFIG)
    assert over["watched"] == "Sural" and over["over_cap"] is True
    assert run.normalise(_raw(price_total=2 * cap), "t", "T", CONFIG)["over_cap"]
    assert run.normalise(_raw(price_total=2 * cap + 1), "t", "T", CONFIG) is None
    other = run.normalise(_raw(hotel="Hotel Saray", price_total=cap + 1), "t", "T", CONFIG)
    assert other is None
    plain = run.normalise(_raw(hotel="Hotel Saray"), "t", "T", CONFIG)
    assert "watched" not in plain and "over_cap" not in plain
    # other criteria still apply to watched hotels
    assert run.normalise(_raw(nights=5), "t", "T", CONFIG) is None


def test_refine_exact_keeps_watched_above_cap_and_asks_them_first():
    cap = CONFIG["price_cap"]
    w = run.normalise(_raw(board="Polpenzia", price_total=cap - 100), "s", "S", CONFIG)
    o = run.normalise(_raw(hotel="Hotel Other", price_total=2000), "s", "S", CONFIG)
    asked = []

    class Mod:
        EXACT_MAX = 1

        @staticmethod
        def exact_price(offer, cfg):
            asked.append(offer["hotel"])
            return {"price_total": cap + 500}

    out = run.refine_exact([o, w], {"s": Mod}, CONFIG)
    assert asked == ["Hotel Sural Hotel"]  # watched first although HB (not a preferred board)
    assert [x["hotel"] for x in out] == ["Hotel Other", "Hotel Sural Hotel"]
    assert w["price_exact"] and w["over_cap"] and w["price_total"] == cap + 500


# --- run.py watch phase -----------------------------------------------------------------------------------------

def test_watch_hints_from_this_and_previous_run():
    cur = [run.normalise(_raw(), "satur", "S", CONFIG)]
    prev = [{"hotel": "Hotel Sural Saray", "country_code": "TR", "place": "Evrenseki", "region": "Side"},
            {"hotel": "Hotel Sural Hotel", "country_code": "TR", "place": "Side", "region": None},
            {"hotel": "Other", "country_code": "GR", "place": "Kos", "region": None}]
    h = run.watch_hints(cur, prev, CONFIG)
    assert h == {"Sural": [{"country_code": "TR", "place": "Side", "region": None},
                           {"country_code": "TR", "place": "Evrenseki", "region": "Side"}], "Alhambra": []}


def test_run_watch_merges_new_offers(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "OFFERS", tmp_path / "none.json")
    seen = run.normalise(_raw(), "satur", "Satur", CONFIG)
    offers = {seen["id"]: seen}

    class Mod:
        NAME = "Satur"

        @staticmethod
        def watch(cfg, terms, hints):
            assert terms == ["Sural", "Alhambra"] and hints["Sural"][0]["place"] == "Side"
            return [_raw(), _raw(hotel="Hotel Sural Saray", price_total=7000, date_from="2027-08-01"),
                    _raw(hotel="Hotel Neighbour")]  # not watched: ignored

        @staticmethod
        def watch_links(cfg, term, hints):
            return [{"label": "x", "url": "https://www.satur.sk/dovolenka/turecko/side"}] if hints else []

    sources = [{"id": "satur", "status": "ok", "count": 1}]
    links = run.run_watch({"satur": Mod}, sources, offers, CONFIG)
    assert sorted(o["hotel"] for o in offers.values()) == ["Hotel Sural Hotel", "Hotel Sural Saray"]
    assert sources[0]["watch"]["new"] == 1 and sources[0]["count"] == 2
    summary = run.watched_summary(list(offers.values()), links, CONFIG)
    assert summary[0]["term"] == "Sural" and summary[0]["count"] == 2 and summary[0]["links"][0]["source"] == "satur"
    assert summary[1] == {"term": "Alhambra", "count": 0, "links": []}


# --- adapters ---------------------------------------------------------------------------------------------------

def test_satur_watch_reads_place_listings(monkeypatch):
    html = (FX / "satur_letecky.html").read_text(encoding="utf-8")
    calls = []

    def fake_get(url, params=None, **kw):
        calls.append((url, params))
        return html

    monkeypatch.setattr(satur, "get", fake_get)
    hints = {"Kouros": [{"country_code": "GR", "place": "Mastichari", "region": "Kos"}],
             "Nowhere": [{"country_code": "XX", "place": "Atlantis", "region": None}]}
    offers = satur.watch(CONFIG, ["Kouros", "Nowhere"], hints)
    assert [u for u, _ in calls] == ["https://www.satur.sk/dovolenka/grecko/mastichari",
                                     "https://www.satur.sk/dovolenka/grecko/kos"]
    assert calls[0][1]["dlzka-pobytu"] == "7,8,9,10,11,12,13,14" and calls[0][1]["termin"] == "01.07.2027-31.08.2027"
    assert {o["hotel"] for o in offers} == {"Hotel Kouros Palace Active Lifestyle"}
    assert satur.watch(CONFIG, ["Kouros"], {}) == []


def test_satur_watch_discards_generic_fallback_listing(monkeypatch):
    html = (FX / "satur_letecky.html").read_text(encoding="utf-8")
    monkeypatch.setattr(satur, "get", lambda url, params=None, **kw: html)
    assert satur.watch(CONFIG, ["Kouros"], {"Kouros": [{"country_code": "TR", "place": "Side"}]}) == []


def test_cedok_watch_pages_the_hinted_country(monkeypatch):
    html = (FX / "cedok_turecko.html").read_text(encoding="utf-8")
    calls = []

    def fake_get(url, params=None, **kw):
        calls.append((url, params))
        return html

    monkeypatch.setattr(cedok, "get", fake_get)
    offers = cedok.watch(CONFIG, ["Sunberk"], {"Sunberk": [{"country_code": "TR", "place": "Side"}]})
    assert calls[0][0] == "https://www.cedok.sk/vysledky-vyhladavania/dovolenky/turecko/"
    assert 1 <= len(calls) <= cedok.WATCH_REQUESTS
    assert offers and {o["hotel"] for o in offers} == {"Hotel Sunberk Side"}
    assert cedok.watch(CONFIG, ["Sunberk"], {"Sunberk": []}) == []


def test_dertour_watch_scans_hinted_country_without_board_filter(monkeypatch):
    cats = json.loads((FX / "dertour_categories.json").read_text(encoding="utf-8"))
    tours = json.loads((FX / "fischer_tours_turecko.json").read_text(encoding="utf-8"))
    calls = []

    def fake_get(url, params=None, headers=None, as_json=False, **kw):
        calls.append(params)
        return cats if "d" not in params else dict(tours, toursCount=250)

    monkeypatch.setattr(dertour, "get", fake_get)
    hints = {"Kilikya": [{"country_code": "TR", "place": "Side"}], "Dosinia": [{"country_code": "TR"}]}
    k = kartago.watch(CONFIG, ["Kilikya", "Dosinia"], hints)
    assert all("m" not in c for c in calls) and calls[1]["pitg"] == 100
    assert len(calls) == 2  # categories + one page (a short page is the last one)
    assert {o["hotel"] for o in k} == {"Kilikya Palace"}  # Dosinia is a FISCHER product
    calls.clear()
    f = fischer.watch(CONFIG, ["Kilikya", "Dosinia"], hints)
    assert {o["hotel"] for o in f} == {"Dosinia Luxury Resort"} and len(calls) <= dertour.WATCH_CALLS
    calls.clear()
    assert kartago.watch(CONFIG, ["Kilikya"], {"Kilikya": []}) == [] and calls == []


# --- weekly digest ----------------------------------------------------------------------------------------------

def _o(id, hotel, price, exact=False):
    return {"id": id, "hotel": hotel, "price_total": price, "price_exact": exact, "board": "AI", "url": "https://x/" + id,
            "place": "Side", "country": "Turecko", "date_from": "2027-07-10", "nights": 7, "transport": "flight",
            "departure": "BTS", "source_name": "Satur.sk", "score": 40}


def test_digest_watched_section_on_top_with_change():
    prev = {"offers": [{"id": "z", "price_total": 2000}],
            "watched": {"Sural": {"id": "a", "price_total": 3500, "price_exact": False}}}
    cur = {"offers": [_o("a", "Hotel Sural Hotel", 3237), _o("b", "Hotel Sural Saray", 7000), _o("c", "Other", 2500)]}
    title, body = notify.digest(prev, cur, 3000)
    assert body.startswith("### ⭐ Sledované hotely")
    sural = body.split("- **Sural**", 1)[1].split("\n- ", 1)[0]
    assert "📉 −263 €" in sural and "Hotel Sural Hotel" in sural and "Saray" not in sural
    assert "- **Alhambra**: zatiaľ bez ponuky" in body
    assert body.index("Sledované hotely") < body.index("Top")


def test_digest_watched_above_cap_new_and_type_switch():
    cap = CONFIG["price_cap"]
    prev = {"offers": [{"id": "z", "price_total": 1}], "watched": {"Alhambra": {"price_total": 3000, "price_exact": False}}}
    cur = {"offers": [_o("b", "Hotel Sural Saray", cap + 900), _o("d", "Alhambra Palace", 2900, exact=True)]}
    _, body = notify.digest(prev, cur, 3000)
    assert "- **Sural** · 🆕 nová · ⚠ nad strop" in body
    assert "- **Alhambra** · minule 3 000 € (iný typ ceny)" in body


def test_digest_without_watched_terms_has_no_section():
    cfg = dict(CONFIG, watched=[])
    _, body = notify.digest({}, {"offers": [_o("a", "Hotel Sural Hotel", 2500)]}, 3000, cfg)
    assert "Sledované" not in body


def test_snapshot_keeps_cheapest_per_watched_term(tmp_path):
    cur = {"generated_at": "x", "offers": [_o("a", "Hotel Sural Hotel", 3300), _o("b", "Sural Saray", 3100)]}
    snap = notify.snapshot(cur, "2026-11-02")
    assert snap["watched"] == {"Sural": {"id": "b", "price_total": 3100, "price_exact": False}}
