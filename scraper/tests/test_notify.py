import notify


def _o(id, price, board="AI"):
    return {"id": id, "price_total": price, "board": board, "hotel": "H" + id, "url": "https://x/" + id,
            "place": "Side", "country": "Turecko", "date_from": "2027-07-10", "nights": 7,
            "transport": "flight", "departure": "BTS", "source_name": "T", "score": 50}


def test_quiet_week_still_sends_top():
    prev = {"offers": [_o("a", 2500)]}
    title, body = notify.digest(prev, prev, 3000)
    assert title == "Dovolenka – týždenný prehľad: od 2\u00a0500\u00a0€"
    assert "Ha" in body and "nepribudlo nič nové" in body


def test_new_and_drop():
    prev = {"offers": [_o("a", 2600)]}
    cur = {"offers": [_o("a", 2500), _o("b", 2800), _o("c", 2900, "HB"), _o("d", 3500)]}
    title, body = notify.digest(prev, cur, 3000)
    assert "1× zlacnenie" in title and "1× nová" in title
    assert "(−100\u00a0€)" in body and "Hb" in body and "Hc" not in body and "Hd" not in body


def test_first_digest_has_only_top():
    title, body = notify.digest({}, {"offers": [_o("a", 2500)]}, 3000)
    assert "nová" not in title and "Nové za týždeň" not in body and "Ha" in body


def test_snapshot_roundtrip(tmp_path):
    import json
    cur = tmp_path / "o.json"
    cur.write_text(json.dumps({"generated_at": "x", "offers": [_o("a", 2500)]}))
    snap = tmp_path / "s.json"
    notify.main(snap, cur, tmp_path / "d.md")
    assert json.loads(snap.read_text())["offers"] == [{"id": "a", "price_total": 2500, "price_exact": None}]
    assert (tmp_path / "d.md").read_text().startswith("Dovolenka – týždenný prehľad")
