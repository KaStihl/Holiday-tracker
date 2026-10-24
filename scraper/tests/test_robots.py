from pathlib import Path

from common import UA, Robots

FX = Path(__file__).parent / "fixtures"


def test_invia_robots():
    rb = Robots((FX / "invia_robots.txt").read_text(), UA)
    assert rb.can_fetch("https://www.invia.sk/dovolenka/turecko/all-inclusive/")
    assert rb.can_fetch("https://www.invia.sk/dovolenka/turecko/all-inclusive/2/")
    assert rb.can_fetch("https://www.invia.sk/hotel/turecko/side/orfeus-park/")
    assert not rb.can_fetch("https://www.invia.sk/direct/tour_hotel/ajax-term-picker-data/?selectedTab=tours")
    assert not rb.can_fetch("https://www.invia.sk/dovolenka/?d_start_from=01.07.2027")
    assert not rb.can_fetch("https://www.invia.sk/dovolenka/?nl_occupancy_adults=1")
    assert not rb.can_fetch("https://www.invia.sk/dovolenka/turecko/?page=2")
    assert not rb.can_fetch("https://www.invia.sk/hotel/x/y/z/zajazd/?s_offer_id=abc")


def test_satur_robots():
    rb = Robots((FX / "satur_robots.txt").read_text(), UA)
    assert rb.can_fetch("https://www.satur.sk/dovolenka/chorvatsko/so-psom?termin=01.07.2027-31.08.2027")
    assert not rb.can_fetch("https://www.satur.sk/ajax/tour-filter/328482")
    assert not Robots((FX / "satur_robots.txt").read_text(), "ClaudeBot/1.0").can_fetch("https://www.satur.sk/")


def test_wildcards_and_precedence():
    rb = Robots("User-agent: *\nDisallow: /a\nAllow: /a/ok$\nDisallow: *.pdf$\n", "x")
    assert not rb.can_fetch("https://h/a/b") and rb.can_fetch("https://h/a/ok")
    assert not rb.can_fetch("https://h/a/ok/more") and not rb.can_fetch("https://h/f.pdf")
    assert rb.can_fetch("https://h/f.pdf?x=1") and rb.can_fetch("https://h/b")
    assert Robots("", "x").can_fetch("https://h/anything")


def test_group_for_our_own_token():
    txt = "User-agent: dovolenka-tracker\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    assert not Robots(txt, UA).can_fetch("https://h/x") and Robots(txt, "Other/1").can_fetch("https://h/x")
