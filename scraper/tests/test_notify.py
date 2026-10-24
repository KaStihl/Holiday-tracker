import notify


def _o(id, price, board="AI"):
    return {"id": id, "price_total": price, "board": board, "hotel": "H" + id, "url": "https://x/" + id,
            "place": "Side", "country": "Turecko", "date_from": "2027-07-10", "nights": 7,
            "transport": "flight", "departure": "BTS", "source_name": "T", "score": 50}


def test_nothing_new():
    prev = {"offers": [_o("a", 2500)]}
    assert notify.digest(prev, prev, 3000) is None


def test_new_and_drop():
    prev = {"offers": [_o("a", 2600)]}
    cur = {"offers": [_o("a", 2500), _o("b", 2800), _o("c", 2900, "HB"), _o("d", 3500)]}
    title, body = notify.digest(prev, cur, 3000)
    assert "1× zlacnenie" in title and "1× nová AI" in title
    assert "(−100 €)" in body and "Hb" in body and "Hc" not in body and "Hd" not in body


def test_first_run_is_summary():
    title, _ = notify.digest({}, {"offers": [_o("a", 2500)]}, 3000)
    assert title.startswith("Dovolenka: prvý prehľad")
