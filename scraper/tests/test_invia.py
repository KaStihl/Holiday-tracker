from adapters import invia
from config import CONFIG


def test_link_only():
    # invia.sk reserves its content against scraping (TDM reservation) – the adapter must stay link-only
    assert invia.DEEPLINK_ONLY and invia.search(CONFIG) == []


def test_deeplinks():
    links = invia.deeplinks(CONFIG)
    assert {d["transport"] for d in links} == {"flight", "car"}
    assert all(d["url"].startswith("https://www.invia.sk/") for d in links)
    vie = links[1]["url"]
    assert "nl_transportation_id%5B%5D=3_6" in vie and "d_start_from=01.07.2027" in vie
    assert "nl_ages_children%5B%5D=10" in vie and "nl_length_to=15" in vie
