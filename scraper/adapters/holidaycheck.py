"""HolidayCheck (holidaycheck.at) – link only: bot wall.

Checked 2026-10-30 from GitHub runners: robots.txt and the home page answer 400 from AkamaiGHost (Akamai bot
manager) to our honest user agent. No circumvention."""

NAME = "HolidayCheck.at"
HOME = "https://www.holidaycheck.at"
DEEPLINK_ONLY = True


def deeplinks(cfg):
    return [{"transport": "flight", "label": "Pauschalreisen a hodnotenia hotelov – vyhľadajte na stránke", "url": "https://www.holidaycheck.at/"}]


def search(cfg):
    return []
