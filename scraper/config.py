"""Search criteria for the Dovolenka tracker, loaded from nastavenia.yml at the repo root (user-editable on
github.com). Everything else reads from CONFIG; nothing in scraper/ may hard-code the party or the budget.

DOVOLENKA_SETTINGS=<path> loads another file (the tests pin their own copy so editing nastavenia.yml never
breaks them).
"""

import os
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = Path(os.environ.get("DOVOLENKA_SETTINGS") or ROOT / "nastavenia.yml")

COUNTRY_NAMES = {
    "HR": "Chorvátsko", "TR": "Turecko", "CY": "Cyprus", "IT": "Taliansko", "GR": "Grécko",
    "ES": "Španielsko", "MT": "Malta", "PT": "Portugalsko", "ME": "Čierna Hora", "AL": "Albánsko",
    "BG": "Bulharsko", "SI": "Slovinsko", "FR": "Francúzsko",
    "EG": "Egypt", "TN": "Tunisko", "MA": "Maroko", "CV": "Kapverdy", "TZ": "Zanzibar (Tanzánia)", "KE": "Keňa",
    "AE": "Dubaj (SAE)", "OM": "Omán", "JO": "Jordánsko",
    "MV": "Maldivy", "MU": "Maurícius", "SC": "Seychely",
    "LK": "Srí Lanka", "TH": "Thajsko", "ID": "Bali (Indonézia)", "VN": "Vietnam",
    "DO": "Dominikánska republika", "MX": "Mexiko", "CU": "Kuba",
}

CONTINENTS = ("Európa", "Afrika", "Blízky východ", "Ázia", "Indický oceán", "Karibik a Amerika")
# country code -> continent (the frontend groups and filters by these exact strings)
CONTINENT_OF = {
    **{c: "Európa" for c in ("HR", "TR", "CY", "IT", "GR", "ES", "MT", "PT", "ME", "AL", "BG", "SI", "FR")},
    **{c: "Afrika" for c in ("EG", "TN", "MA", "CV", "TZ", "KE")},
    **{c: "Blízky východ" for c in ("AE", "OM", "JO")},
    **{c: "Indický oceán" for c in ("MV", "MU", "SC")},
    **{c: "Ázia" for c in ("LK", "TH", "ID", "VN")},
    **{c: "Karibik a Amerika" for c in ("DO", "MX", "CU")},
}
DEFAULT_CONTINENT = "Európa"  # unknown country (a few Satur cards): practically always a European resort

BOARDS = ("UAI", "AI", "FB", "HB", "BB", "RO")
TRANSPORTS = ("flight", "car")


def continent(code):
    return CONTINENT_OF.get(code, DEFAULT_CONTINENT)


class SettingsError(ValueError):
    pass


def _date(v, key):
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).strip())
    except ValueError:
        raise SettingsError(f"{key}: '{v}' nie je dátum v tvare RRRR-MM-DD (napr. 2027-07-01)") from None


def _int(v, key, lo, hi):
    if isinstance(v, bool) or not isinstance(v, int):
        try:
            v = int(str(v).strip())
        except ValueError:
            raise SettingsError(f"{key}: '{v}' nie je celé číslo") from None
    if not lo <= v <= hi:
        raise SettingsError(f"{key}: {v} musí byť od {lo} do {hi}")
    return v


def _codes(v, key, pattern_len=3):
    if v is None:
        return []
    if isinstance(v, str):
        v = [x for x in v.replace(",", " ").split()]
    if not isinstance(v, list):
        raise SettingsError(f"{key}: čakám zoznam, napr. [BTS, VIE]")
    out = [str(x).strip().upper() for x in v]
    bad = [x for x in out if len(x) != pattern_len or not x.isalpha()]
    if bad:
        raise SettingsError(f"{key}: neplatné kódy {bad}")
    return out


def birthdate(age, on):
    """A birth date that makes the child exactly `age` on `on` and for the following year (the whole trip)."""
    try:
        d = on.replace(year=on.year - age)
    except ValueError:  # 29 February
        d = on.replace(year=on.year - age, day=28)
    return (d - timedelta(days=1)).isoformat()


def validate(raw):
    """nastavenia.yml dict -> CONFIG dict; raises SettingsError with a message the user can act on."""
    if not isinstance(raw, dict):
        raise SettingsError("súbor musí obsahovať položky v tvare 'kľúč: hodnota'")
    required = ("adults", "children_ages", "date_from", "date_to", "nights_min", "nights_max", "budget",
                "price_cap", "departures", "destinations")
    missing = [k for k in required if k not in raw]
    if missing:
        raise SettingsError(f"chýbajú položky: {', '.join(missing)}")
    known = set(required) | {"departures_secondary", "transports", "dogs", "boards_preferred", "car_start"}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise SettingsError(f"neznáme položky (preklep?): {', '.join(unknown)}")

    c = {"adults": _int(raw["adults"], "adults", 1, 6)}
    ages = raw["children_ages"] if raw["children_ages"] is not None else []
    if not isinstance(ages, list):
        raise SettingsError("children_ages: čakám zoznam vekov, napr. [10, 12] alebo [] bez detí")
    c["children_ages"] = [_int(a, "children_ages", 0, 17) for a in ages]
    if c["adults"] + len(c["children_ages"]) > 8:
        raise SettingsError("spolu najviac 8 osôb")
    c["date_from"] = _date(raw["date_from"], "date_from")
    c["date_to"] = _date(raw["date_to"], "date_to")
    if c["date_to"] < c["date_from"]:
        raise SettingsError("date_to musí byť rovnako alebo neskôr ako date_from")
    if (c["date_to"] - c["date_from"]).days > 366:
        raise SettingsError("date_from – date_to: najviac jeden rok")
    c["nights_min"] = _int(raw["nights_min"], "nights_min", 1, 30)
    c["nights_max"] = _int(raw["nights_max"], "nights_max", 1, 30)
    if c["nights_max"] < c["nights_min"]:
        raise SettingsError("nights_max musí byť aspoň nights_min")
    c["budget"] = _int(raw["budget"], "budget", 100, 100000)
    c["price_cap"] = _int(raw["price_cap"], "price_cap", 100, 100000)
    if c["price_cap"] < c["budget"]:
        raise SettingsError("price_cap (strop) musí byť aspoň budget")
    c["departures"] = _codes(raw["departures"], "departures")
    if not c["departures"]:
        raise SettingsError("departures: zadajte aspoň jedno letisko, napr. [BTS, VIE]")
    c["departures_secondary"] = _codes(raw.get("departures_secondary"), "departures_secondary")
    tr = raw.get("transports", list(TRANSPORTS))
    tr = [str(x).strip().lower() for x in (tr if isinstance(tr, list) else [tr])]
    if not tr or any(t not in TRANSPORTS for t in tr):
        raise SettingsError(f"transports: povolené sú len {', '.join(TRANSPORTS)} (aspoň jedno)")
    c["transports"] = [t for t in TRANSPORTS if t in tr]
    c["dogs"] = _int(raw.get("dogs", 0) or 0, "dogs", 0, 10)
    bp = raw.get("boards_preferred") or ["UAI", "AI"]
    bp = [str(x).strip().upper() for x in (bp if isinstance(bp, list) else [bp])]
    if any(b not in BOARDS for b in bp):
        raise SettingsError(f"boards_preferred: povolené sú {', '.join(BOARDS)}")
    c["boards_preferred"] = bp
    c["car_start"] = str(raw.get("car_start") or "Bratislava")
    dest = raw["destinations"]
    if not isinstance(dest, dict) or not dest:
        raise SettingsError("destinations: čakám zoznam 'KÓD: váha', napr. 'TR: 1.0'")
    c["countries"] = {}
    for k, w in dest.items():
        code = str(k).strip().upper()
        if code not in COUNTRY_NAMES:
            raise SettingsError(f"destinations: neznámy kód krajiny '{k}' (známe: {', '.join(COUNTRY_NAMES)})")
        try:
            w = float(w)
        except (TypeError, ValueError):
            raise SettingsError(f"destinations: váha pri {code} musí byť číslo 0.1–1.0") from None
        if not 0 < w <= 1:
            raise SettingsError(f"destinations: váha pri {code} musí byť od 0.1 do 1.0")
        c["countries"][code] = w
    c["children_birthdates"] = [birthdate(a, c["date_from"]) for a in c["children_ages"]]
    return c


def load(path=SETTINGS):
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise SettingsError(f"{Path(path).name}: chybný formát YAML: {e}") from None
    try:
        return validate(raw)
    except SettingsError as e:
        raise SettingsError(f"{Path(path).name}: {e}") from None


CONFIG = load()


# --- party helpers (labels shared by adapters, run.py and notify.py) -------------------------------------

def party_size(cfg=CONFIG):
    return cfg["adults"] + len(cfg["children_ages"])


def party_short(cfg=CONFIG):
    """'1+2' (adults+children)."""
    return f"{cfg['adults']}+{len(cfg['children_ages'])}"


def _plural(n, one, few, many):
    return one if n == 1 else few if 2 <= n <= 4 else many


def party_label(cfg=CONFIG, case="nom"):
    """'1 dospelý + 2 deti (10 a 12 r.)'; case='gen' -> '1 dospelého + 2 detí (10 a 12 r.)'."""
    a, kids = cfg["adults"], cfg["children_ages"]
    if case == "gen":
        s = f"{a} {_plural(a, 'dospelého', 'dospelých', 'dospelých')}"
    else:
        s = f"{a} {_plural(a, 'dospelý', 'dospelí', 'dospelých')}"
    if kids:
        n = len(kids)
        word = (_plural(n, "dieťaťa", "detí", "detí") if case == "gen" else _plural(n, "dieťa", "deti", "detí"))
        ages = " a ".join(str(x) for x in kids) if n <= 2 else ", ".join(str(x) for x in kids)
        s += f" + {n} {word} ({ages} r.)"
    return s


def approx_note(cfg=CONFIG, basis="pri 2 dospelých"):
    """price_note for an approximated party price, e.g. 'orientačne: cena za osobu pri 2 dospelých × 3'."""
    return f"orientačne: cena za osobu{(' ' + basis) if basis else ''} × {party_size(cfg)}"


def approx_label(cfg=CONFIG, promo=None):
    """discount_label of an approximated offer: 'Cena za os. × N (orientačne)' / '<promo> (cena za os. × N, orientačne)'."""
    n = party_size(cfg)
    return f"{promo} (cena za os. × {n}, orientačne)" if promo else f"Cena za os. × {n} (orientačne)"


MONTHS = ["jan", "feb", "mar", "apr", "máj", "jún", "júl", "aug", "sep", "okt", "nov", "dec"]


def period_label(cfg=CONFIG):
    """'júl–aug' from date_from/date_to."""
    a, b = MONTHS[cfg["date_from"].month - 1], MONTHS[cfg["date_to"].month - 1]
    return a if a == b and cfg["date_from"].year == cfg["date_to"].year else f"{a}–{b}"


def criteria_for_display(cfg=CONFIG):
    c = dict(cfg)
    c["date_from"] = c["date_from"].isoformat()
    c["date_to"] = c["date_to"].isoformat()
    c["countries"] = dict(c["countries"])
    c["destinations"] = [{"code": k, "name": COUNTRY_NAMES.get(k, k), "weight": w, "continent": continent(k)}
                         for k, w in cfg["countries"].items()]
    c["continents"] = list(CONTINENTS)
    c["party_size"] = party_size(cfg)
    c["party_label"] = party_label(cfg)
    return c
