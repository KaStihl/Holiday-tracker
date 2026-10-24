"""Search criteria for the Dovolenka tracker. Edit here, everything else reads from CONFIG."""

from datetime import date

CONFIG = {
    "adults": 1,
    "children_ages": [10, 12],
    # Some sites want birth dates instead of ages; these give 10 and 12 in summer 2027.
    "children_birthdates": ["2017-01-15", "2015-01-15"],
    "date_from": date(2027, 7, 1),
    "date_to": date(2027, 8, 31),
    "nights_min": 7,
    "nights_max": 14,
    "budget": 3000,
    "price_cap": 4500,  # offers above this are dropped
    "boards_preferred": ["UAI", "AI"],
    "departures": ["BTS", "VIE"],
    "departures_secondary": ["BUD", "KSC"],
    "car_start": "Bratislava",
    "dogs": 2,
    # country code -> preference weight (1.0 = favourite). Unlisted countries get 0.5.
    "countries": {
        "HR": 1.0, "TR": 1.0, "CY": 1.0, "IT": 1.0, "GR": 0.95, "ES": 0.95,
        "MT": 0.9, "PT": 0.8, "ME": 0.8, "AL": 0.75, "BG": 0.7, "EG": 0.7, "TN": 0.65,
    },
}

COUNTRY_NAMES = {
    "HR": "Chorvátsko", "TR": "Turecko", "CY": "Cyprus", "IT": "Taliansko", "GR": "Grécko",
    "ES": "Španielsko", "MT": "Malta", "PT": "Portugalsko", "ME": "Čierna Hora", "AL": "Albánsko",
    "BG": "Bulharsko", "EG": "Egypt", "TN": "Tunisko", "SI": "Slovinsko", "FR": "Francúzsko",
    "MA": "Maroko", "AE": "SAE",
}


def criteria_for_display():
    c = dict(CONFIG)
    c["date_from"] = c["date_from"].isoformat()
    c["date_to"] = c["date_to"].isoformat()
    return c
