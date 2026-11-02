"""Party profiles ('skupiny' in nastavenia.yml): config, per-party offers/ids/history, adapters' extra passes,
offers.json compaction and the digest (primary party only)."""

import json
from pathlib import Path

import pytest

import config
import notify
import run
from adapters import dertour, fischer, kartago, ruefa
from common import compact_offers, expand_offers
from config import CONFIG, SettingsError, criteria_for_display, extra_parties, party_cfg, validate

FX = Path(__file__).parent / "fixtures"
BASE = {"date_from": "2027-07-01", "date_to": "2027-08-31", "nights_min": 7, "nights_max": 14, "budget": 3000,
        "price_cap": 6000, "departures": ["BTS", "VIE"], "destinations": {"TR": 1.0, "GR": 0.9}}
SKUPINY = [{"nazov": "Ja + 2 deti", "adults": 1, "children_ages": [10, 12]},
           {"nazov": "2 dospelí + 2 deti", "adults": 2, "children_ages": [10, 12]},
           {"nazov": "2 dospelí", "adults": 2, "children_ages": []}]
MULTI = validate(dict(BASE, skupiny=SKUPINY, departures_secondary=["BRQ"]))


# --- config -------------------------------------------------------------------------------------------------------

def test_skupiny_parsed_primary_first_with_ids_and_birthdates():
    ps = MULTI["parties"]
    assert [p["id"] for p in ps] == ["a1-c10-12", "a2-c10-12", "a2"]
    assert [p["nazov"] for p in ps] == ["Ja + 2 deti", "2 dospelí + 2 deti", "2 dospelí"]
    assert ps[1]["children_birthdates"] == ["2017-06-30", "2015-06-30"] and ps[2]["children_birthdates"] == []
    # the primary party is also the top-level party every adapter reads
    assert (MULTI["adults"], MULTI["children_ages"], MULTI["party_id"]) == (1, [10, 12], "a1-c10-12")
    assert MULTI["children_birthdates"] == ps[0]["children_birthdates"]
    two = party_cfg(MULTI, ps[1])
    assert (two["adults"], two["children_ages"], two["party_id"], two["budget"]) == (2, [10, 12], "a2-c10-12", 3000)
    assert [p["id"] for p, _ in extra_parties(MULTI)] == ["a2-c10-12", "a2"]


def test_backward_compatible_single_party():
    c = validate(dict(BASE, adults=2, children_ages=[7]))
    assert [(p["id"], p["nazov"]) for p in c["parties"]] == [("a2-c7", "2 dospelí + 1 dieťa (7 r.)")]
    assert extra_parties(c) == [] and c["party_id"] == "a2-c7"
    assert [p["id"] for p in CONFIG["parties"]] == ["a1-c10-12"]  # the test settings file has no 'skupiny'


def test_top_level_party_stays_the_default_one():
    c = validate(dict(BASE, skupiny=SKUPINY, adults=2, children_ages=[]))  # matches the 3rd skupina
    assert [p["id"] for p in c["parties"]] == ["a2", "a1-c10-12", "a2-c10-12"] and c["parties"][0]["nazov"] == "2 dospelí"
    c = validate(dict(BASE, skupiny=SKUPINY[:1], adults=1, children_ages=[5]))  # not among skupiny: added first
    assert [p["id"] for p in c["parties"]] == ["a1-c5", "a1-c10-12"]


@pytest.mark.parametrize("raw, msg", [
    (dict(BASE, skupiny=SKUPINY + [{"adults": 3}, {"adults": 4}]), "najviac 4"),
    (dict(BASE, skupiny=[SKUPINY[0], dict(SKUPINY[0], nazov="Iná")]), "rovnaké zloženie"),
    (dict(BASE, skupiny=[SKUPINY[0], dict(SKUPINY[1], nazov="ja + 2 DETI")]), "už má iná skupina"),
    (dict(BASE, skupiny=[{"nazov": "x", "adults": 0}]), "adults: 0 musí byť od 1 do 6"),
    (dict(BASE, skupiny=[{"nazov": "x", "adults": 1, "children_ages": 10}]), "čakám zoznam vekov"),
    (dict(BASE, skupiny=[{"nazov": "x", "children_ages": [1]}]), "chýba adults"),
    (dict(BASE, skupiny=[{"nazov": "x", "adults": 1, "deti": [1]}]), "neznáme položky"),
    (dict(BASE, skupiny=[{"nazov": "x", "adults": 6, "children_ages": [1, 2, 3]}]), "najviac 8 osôb"),
    (dict(BASE, skupiny=[{"nazov": "x" * 31, "adults": 1}]), "príliš dlhý"),
    (dict(BASE, skupiny=[]), "čakám zoznam skupín"),
    (dict(BASE, skupiny=["1+2"]), "čakám {nazov"),
    (dict(BASE, skupiny=SKUPINY, adults=1), "patria k sebe"),
    (dict(BASE), "chýbajú položky: adults, children_ages"),
])
def test_skupiny_validation_messages(raw, msg):
    with pytest.raises(SettingsError, match=msg):
        validate(raw)


def test_repo_settings_file_is_valid():
    c = config.load(Path(__file__).resolve().parents[2] / "nastavenia.yml")
    assert 1 <= len(c["parties"]) <= config.PARTIES_MAX


def test_criteria_lists_the_parties():
    c = criteria_for_display(MULTI)
    assert c["default_party"] == "a1-c10-12" and "party_id" not in c
    assert c["parties"][1] == {"id": "a2-c10-12", "nazov": "2 dospelí + 2 deti", "adults": 2, "children_ages": [10, 12],
                               "party_size": 4, "label": "2 dospelí + 2 deti (10 a 12 r.)"}
    assert all("children_birthdates" not in p for p in c["parties"])
    json.dumps(c)


# --- per-party offers -----------------------------------------------------------------------------------------------

def _raw(**kw):
    o = {"hotel": "Hotel Test", "url": "https://x.sk/h", "country": "Turecko", "board": "AI", "transport": "flight",
         "departure": "BTS", "date_from": "2027-07-10", "nights": 7, "price_total": 2400, "price_original": 3000,
         "discount_label": "Zľava (cena za os. × 3, orientačne)",
         "price_note": "orientačne: cena za osobu pri 2 dospelých × 3"}
    o.update(kw)
    return o


def test_primary_keeps_old_ids_extra_parties_get_their_own():
    p1, p2, p3 = MULTI["parties"]
    a = run.normalise(_raw(), "satur", "Satur", MULTI)
    b = run.normalise(_raw(), "satur", "Satur", party_cfg(MULTI, p2))
    assert a["id"] == run.offer_id("satur", "Hotel Test", "2027-07-10", 7, "flight", "BTS") and a["party"] == p1["id"]
    assert b["id"] == a["id"] + "@a2-c10-12" and b["party"] == "a2-c10-12"
    assert run.normalise(_raw(), "t", "T", CONFIG)["party"] == "a1-c10-12"  # single-party settings


def test_scale_approximation_to_other_parties():
    p1, p2, p3 = MULTI["parties"]
    a = run.normalise(_raw(), "satur", "Satur", MULTI)  # 800 €/person × 3
    s4 = run.scale_offer(a, MULTI, party_cfg(MULTI, p2))
    assert (s4["price_total"], s4["price_original"], s4["discount_pct"]) == (3200, 4000, 20)
    assert s4["price_note"] == "orientačne: cena za osobu pri 2 dospelých × 4"
    assert s4["discount_label"] == "Zľava (cena za os. × 4, orientačne)"
    assert s4["id"] == a["id"] + "@a2-c10-12" and s4["party"] == "a2-c10-12" and s4["price_exact"] is False
    s2 = run.scale_offer(a, MULTI, party_cfg(MULTI, p3))
    assert s2["price_total"] == 1600 and s2["price_note"].endswith("× 2") and s2["id"].endswith("@a2")
    assert a["price_total"] == 2400 and a["id"].count("@") == 0  # the primary offer is untouched
    # above price_cap for the bigger party: dropped (a watched hotel up to the wider limit, flagged)
    big = run.normalise(_raw(price_total=5400, price_original=None), "satur", "Satur", MULTI)
    assert run.scale_offer(big, MULTI, party_cfg(MULTI, p2)) is None
    w = run.normalise(_raw(hotel="Sural Resort", price_total=5400), "satur", "Satur", dict(MULTI, watched=["Sural"]))
    sw = run.scale_offer(w, MULTI, party_cfg(dict(MULTI, watched=["Sural"]), p2))
    assert sw["price_total"] == 7200 and sw["over_cap"] is True and sw["watched"] == "Sural"
    # exact party prices are never scaled
    ex = run.normalise(_raw(price_exact=True), "kartago", "Kartago", MULTI)
    assert run.scale_offer(ex, MULTI, party_cfg(MULTI, p2)) is None


def test_extra_party_offers_exact_passes_and_scaling():
    import types
    p1, p2, p3 = MULTI["parties"]
    asked = []
    exact_mod = types.SimpleNamespace(NAME="Kartago", search_party=lambda cfg, prim: asked.append(
        (cfg["party_id"], len(prim))) or [_raw(hotel="Exact " + cfg["party_id"], price_exact=True, price_total=2000)])
    approx = run.normalise(_raw(), "satur", "Satur", MULTI)
    ex = run.normalise(_raw(hotel="K", price_exact=True), "kartago", "Kartago", MULTI)
    sources = [{"id": "kartago", "status": "ok"}, {"id": "satur", "status": "ok"}]
    by = run.extra_party_offers({"kartago": exact_mod, "satur": types.SimpleNamespace(NAME="Satur")}, sources,
                                {approx["id"]: approx, ex["id"]: ex}, MULTI)
    assert sorted(asked) == [("a2", 1), ("a2-c10-12", 1)]  # each extra party once, with this source's primary offers
    for pid, total in (("a2-c10-12", 3200), ("a2", 1600)):
        offers = list(by[pid].values())
        assert {o["hotel"] for o in offers} == {"Exact " + pid, "Hotel Test"}  # no scaled copy of the exact "K"
        assert next(o for o in offers if o["hotel"] == "Hotel Test")["price_total"] == total
        assert all(o["party"] == pid and o["id"].endswith("@" + pid) for o in offers)
    assert sources[0]["parties"]["a2"]["kept"] == 1


def test_history_per_party_and_primary_history_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "HISTORY", tmp_path / "h.json")
    monkeypatch.setattr(run, "OFFERS", tmp_path / "o.json")
    a = run.normalise(_raw(), "satur", "Satur", MULTI)
    # history written before parties existed (single party 1+2): no "@", party signature of 1+2
    run.HISTORY.write_text(json.dumps({a["id"]: {"first_seen": "2026-10-20", "points": [["2026-10-20", 2500]],
                                                 "exact": False, "party": "1|10,12", "last_seen": "2026-10-20"}}))
    run.OFFERS.write_text(json.dumps({"criteria": {"adults": 1, "children_ages": [10, 12]},
                                      "offers": [dict(a, price_total=2500, party=None)]}))
    b = run.scale_offer(a, MULTI, party_cfg(MULTI, MULTI["parties"][1]))
    h = run.merge_history([a, b], "2026-11-02", MULTI)
    assert a["price_history"] == [["2026-10-20", 2500], ["2026-11-02", 2400]] and a["price_change"] == -100
    assert a["first_seen"] == "2026-10-20"
    assert b["price_history"] == [["2026-11-02", 3200]] and b["price_change"] is None
    assert h[b["id"]]["party"] == "2|10,12" and h[a["id"]]["party"] == "1|10,12"
    # next run: each party continues its own series; previous offers.json is compacted
    run.HISTORY.write_text(json.dumps(h))
    run.OFFERS.write_text(json.dumps({"criteria": criteria_for_display(MULTI), "offers": compact_offers([a, b])}))
    a2, b2 = dict(a, price_total=2300), dict(b, price_total=3100)
    run.merge_history([a2, b2], "2026-11-03", MULTI)
    assert (a2["price_change"], b2["price_change"]) == (-100, -100)
    assert b2["price_history"] == [["2026-11-02", 3200], ["2026-11-03", 3100]]


def test_history_restarts_when_the_primary_party_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "HISTORY", tmp_path / "h.json")
    monkeypatch.setattr(run, "OFFERS", tmp_path / "o.json")
    a = run.normalise(_raw(), "satur", "Satur", MULTI)
    run.HISTORY.write_text(json.dumps({a["id"]: {"first_seen": "2026-10-20", "points": [["2026-10-20", 2500]],
                                                 "exact": False, "party": "2|", "last_seen": "2026-10-20"}}))
    run.merge_history([a], "2026-11-02", MULTI)
    assert a["price_history"] == [["2026-11-02", 2400]] and a["price_change"] is None
    assert run.signature_of_id("a2-c10-12") == "2|10,12" and run.signature_of_id("a2") == "2|"
    assert run.signature_of_id("x") is None


# --- offers.json size -----------------------------------------------------------------------------------------------

def test_compact_and_expand_round_trip():
    a = run.normalise(_raw(hotel="Sural", price_total=2400), "satur", "Satur", dict(MULTI, watched=["Sural"]))
    a["over_cap"] = True  # base has a field the party's offer lacks -> null
    b = run.scale_offer(dict(a, over_cap=None), MULTI, party_cfg(dict(MULTI, watched=["Sural"]), MULTI["parties"][2]))
    alone = dict(b, id="other:1@a2", hotel="Other")
    packed = compact_offers([a, b, alone])
    assert packed[0] is a and packed[2] is alone
    c = packed[1]
    assert c["base"] == a["id"] and "hotel" not in c and "url" not in c and c["over_cap"] is None
    assert c["price_total"] == 1600 and c["party"] == "a2"
    back = expand_offers(packed)
    assert back[1] == dict(b, over_cap=None) and back[0] == a
    assert expand_offers([{"id": "x@a2", "base": "missing"}]) == []


def test_fit_size_caps_extra_parties_only():
    offers = []
    for i in range(300):
        o = run.normalise(_raw(hotel=f"H{i}", price_total=1000 + i), "satur", "Satur", MULTI)
        o["score"] = 300 - i
        offers.append(o)
        for p in MULTI["parties"][1:]:
            s = run.scale_offer(o, MULTI, party_cfg(MULTI, p))
            s["url"] = f"https://x.sk/{p['id']}/{i}"  # not compactable
            if s:
                offers.append(s)
    out, cap = run.fit_size(offers, MULTI, limit=10 ** 9)
    assert cap is None and len(out) == len(offers)
    full = len(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    out, cap = run.fit_size(offers, MULTI, limit=full * 2 // 3)
    assert cap and len(json.dumps(out, ensure_ascii=False, separators=(",", ":"))) <= full * 2 // 3
    assert sum("@" not in o["id"] for o in out) == 300  # the primary party is never capped
    kept = [o for o in expand_offers(out) if o["party"] == "a2"]
    assert len(kept) == cap and {o["hotel"] for o in kept} == {f"H{i}" for i in range(cap)}  # best scores


def test_dump_is_valid_json_one_offer_per_line():
    out = {"generated_at": "x", "criteria": {}, "offers": [{"id": "a", "hotel": "x"}, {"id": "b"}], "watched": []}
    text = run.dump(out)
    assert json.loads(text) == out
    assert '\n{"id":"a","hotel":"x"},\n{"id":"b"}\n' in text
    assert json.loads(run.dump(dict(out, offers=[]))) == dict(out, offers=[])


# --- adapters: extra-party passes -----------------------------------------------------------------------------------

def _two_two():
    return party_cfg(CONFIG, {"id": "a2-c10-12", "adults": 2, "children_ages": [10, 12],
                              "children_birthdates": ["2017-06-30", "2015-06-30"]})


def test_dertour_party_pass_budget_and_party_query(monkeypatch):
    cats = json.loads((FX / "dertour_categories.json").read_text())
    tours = json.loads((FX / "fischer_tours_turecko.json").read_text())
    calls = []

    def fake(url, params=None, **kw):
        calls.append(params)
        return tours if "d" in params else cats

    monkeypatch.setattr(dertour, "get", fake)
    primary = [{"country_code": c} for c in ("TR", "TR", "GR", "EG", "ES", "BG", "TN", "CY", "IT", "HR", "MT")]
    pcfg = _two_two()
    offers = kartago.search_party(pcfg, primary)
    assert len(calls) <= dertour.EXTRA_CALLS
    assert all((q["ac1"], q["kc1"], q["ka1"]) == (2, 2, "10|12") for q in calls)
    assert all(q["to"] == "483|3789" for q in calls)  # BTS/VIE only, no Brno pass for extra parties
    # countries the brand sold in the primary pass, by preference weight (TR, CY, IT, HR = 1.0 first)
    asked = [q["d"] for q in calls[1:]]
    order = [c[0] for c in dertour.countries(cats, pcfg) if c[2] in asked]
    assert order[:4] == ["TR", "CY", "IT", "HR"] and len(asked) == dertour.EXTRA_CALLS - 1
    # the fixture tours are priced for 1+2, not 2+2: never passed off as exact for this party
    assert offers and all("price_exact" not in o and o["price_note"].endswith("× 4") for o in offers)
    # Fischer keeps only its own brand, and a source without primary offers asks nothing
    calls.clear()
    assert fischer.search_party(pcfg, []) == [] and calls == []


def test_dertour_party_pass_exact_for_matching_party(monkeypatch):
    tours = json.loads((FX / "fischer_tours_turecko.json").read_text())
    cats = json.loads((FX / "dertour_categories.json").read_text())
    monkeypatch.setattr(dertour, "get", lambda url, params=None, **kw: tours if "d" in params else cats)
    pcfg = party_cfg(CONFIG, {"id": "same", "adults": 1, "children_ages": [10, 12], "children_birthdates": []})
    offers = fischer.search_party(pcfg, [{"country_code": "TR"}])
    assert offers and all(o["price_exact"] for o in offers)


def test_ruefa_party_pass_budget_form_and_watched(monkeypatch):
    data = json.loads((FX / "ruefa_deliver.json").read_text())
    calls = []

    def fake(url, **kw):
        calls.append(kw["data"])
        return data

    monkeypatch.setattr(ruefa, "get", fake)
    monkeypatch.setattr(ruefa, "_WATCH_GIDS", ["53099"])
    primary = [{"country_code": c} for c in ("BG", "GR", "GR", "TR", "HR", "CY", "IT", "EG", "MT")]
    pcfg = _two_two()
    offers = ruefa.search_party(pcfg, primary)
    assert len(calls) == ruefa.EXTRA_CALLS
    assert all((f["adults"], f["children"]) == ("2", "10-12") for f in calls)
    assert calls[-1]["gid"] == "53099"  # the watched hotels found by watch()
    assert [f["destination"] for f in calls[:2]] == [ruefa.DEST_IDS["TR"], ruefa.DEST_IDS["HR"]]
    assert offers == []  # the fixture cards are priced for 1+2: dropped for 2+2
    same = party_cfg(CONFIG, {"id": "same", "adults": 1, "children_ages": [10, 12], "children_birthdates": []})
    monkeypatch.setattr(ruefa, "_WATCH_GIDS", [])
    calls.clear()
    got = ruefa.search_party(same, [{"country_code": "BG"}, {"country_code": "GR"}])
    assert len(calls) == 2 and {o["country_code"] for o in got} == {"BG", "GR"} and all(o["price_exact"] for o in got)


def test_cedok_exact_lookup_uses_the_party():
    from adapters import cedok
    url = cedok.occupancy_url("https://www.cedok.sk/dovolena/x/?id=1&participants%5B0%5D%5Badults%5D=2", _two_two())
    assert "participants%5B0%5D%5Badults%5D=2" in url and "children%5D%5B1%5D=30.06.2015" in url
    assert url.count("adults") == 1


# --- digest ---------------------------------------------------------------------------------------------------------

def test_digest_is_for_the_primary_party_only(monkeypatch):
    a = dict(run.normalise(_raw(), "satur", "Satur", MULTI), score=90)
    b = run.scale_offer(a, MULTI, party_cfg(MULTI, MULTI["parties"][2]))
    b["score"] = 95
    cur = {"criteria": criteria_for_display(MULTI), "offers": compact_offers([a, b])}
    assert notify.primary_offers(cur, MULTI) == [a]
    title, body = notify.digest({}, cur, 3000, MULTI)
    assert "2\u00a0400" in title and "1\u00a0600" not in body
    assert "👥 Prehľad je len pre hlavnú skupinu „Ja + 2 deti“" in body and "„2 dospelí“" in body
    snap = notify.snapshot(cur, "2026-11-02", MULTI)
    assert [o["id"] for o in snap["offers"]] == [a["id"]]
    # single party: no parties line, older files without "party" still count
    _, body1 = notify.digest({}, {"offers": [dict(a, party=None)]}, 3000, CONFIG)
    assert "👥" not in body1 and "2\u00a0400" in body1
