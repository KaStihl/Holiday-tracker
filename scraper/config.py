"""Search criteria for the Dovolenka tracker, loaded from nastavenia.yml at the repo root (user-editable on
github.com). Everything else reads from CONFIG; nothing in scraper/ may hard-code the party or the budget.

DOVOLENKA_SETTINGS=<path> loads another file (the tests pin their own copy so editing nastavenia.yml never
breaks them).
"""

import os
from datetime import date, timedelta
from pathlib import Path

import yaml

from watch import norm_name, split_term

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = Path(os.environ.get("DOVOLENKA_SETTINGS") or ROOT / "nastavenia.yml")

COUNTRY_NAMES = {
    "HR": "Chorvátsko", "TR": "Turecko", "CY": "Cyprus", "IT": "Taliansko", "GR": "Grécko",
    "ES": "Španielsko", "MT": "Malta", "PT": "Portugalsko", "ME": "Čierna Hora", "AL": "Albánsko",
    "BG": "Bulharsko", "SI": "Slovinsko", "FR": "Francúzsko", "PL": "Poľsko", "SK": "Slovensko", "CZ": "Česko",
    "AT": "Rakúsko", "HU": "Maďarsko", "DE": "Nemecko", "RO": "Rumunsko",
    "EG": "Egypt", "TN": "Tunisko", "MA": "Maroko", "CV": "Kapverdy", "TZ": "Zanzibar (Tanzánia)", "KE": "Keňa",
    "AE": "Dubaj (SAE)", "OM": "Omán", "JO": "Jordánsko",
    "MV": "Maldivy", "MU": "Maurícius", "SC": "Seychely",
    "LK": "Srí Lanka", "TH": "Thajsko", "ID": "Bali (Indonézia)", "VN": "Vietnam",
    "DO": "Dominikánska republika", "MX": "Mexiko", "CU": "Kuba",
}

CONTINENTS = ("Európa", "Afrika", "Blízky východ", "Ázia", "Indický oceán", "Karibik a Amerika")
# country code -> continent (the frontend groups and filters by these exact strings)
CONTINENT_OF = {
    **{c: "Európa" for c in ("HR", "TR", "CY", "IT", "GR", "ES", "MT", "PT", "ME", "AL", "BG", "SI", "FR",
                                     "PL", "SK", "CZ", "AT", "HU", "DE", "RO")},
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


def _plural(n, one, few, many):
    return one if n == 1 else few if 2 <= n <= 4 else many


def _party_text(a, kids, case="nom"):
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


def validate(raw):
    """nastavenia.yml dict -> CONFIG dict; raises SettingsError with a message the user can act on."""
    if not isinstance(raw, dict):
        raise SettingsError("súbor musí obsahovať položky v tvare 'kľúč: hodnota'")
    required = ("date_from", "date_to", "nights_min", "nights_max", "budget", "price_cap", "departures",
                "destinations")
    # the party: 'skupiny' (list of parties) and/or the older single-party keys adults + children_ages
    if "skupiny" not in raw:
        required = ("adults", "children_ages") + required
    missing = [k for k in required if k not in raw]
    if missing:
        raise SettingsError(f"chýbajú položky: {', '.join(missing)}")
    known = set(required) | {"adults", "children_ages", "skupiny", "departures_secondary", "transports", "dogs",
                             "boards_preferred", "car_start", "sledovane_hotely", "side_hotely"}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise SettingsError(f"neznáme položky (preklep?): {', '.join(unknown)}")

    c = {}
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
    c["watched"] = _watched(raw.get("sledovane_hotely"))
    c["side"] = _side(raw.get("side_hotely"))
    c["parties"] = _parties(raw, c["date_from"])
    primary = c["parties"][0]
    c["party_id"] = primary["id"]
    c["adults"], c["children_ages"] = primary["adults"], primary["children_ages"]
    c["children_birthdates"] = primary["children_birthdates"]
    return c


PARTIES_MAX = 4


def party_id(adults, ages):
    """Stable id of a party composition: 'a1-c10-12', 'a2-c10-12', 'a2' (URL-safe; offer ids and the price history
    of extra parties carry it, so renaming a party in nastavenia.yml keeps its history)."""
    return f"a{adults}" + ("-c" + "-".join(str(a) for a in sorted(ages)) if ages else "")


def _party(adults, ages, nazov, key, on):
    a = _int(adults, f"{key}: adults", 1, 6)
    if ages is None:
        ages = []
    if not isinstance(ages, list):
        raise SettingsError(f"{key}: children_ages – čakám zoznam vekov, napr. [10, 12] alebo [] bez detí")
    ages = [_int(x, f"{key}: children_ages", 0, 17) for x in ages]
    if a + len(ages) > 8:
        raise SettingsError(f"{key}: spolu najviac 8 osôb")
    p = {"id": party_id(a, ages), "nazov": None, "adults": a, "children_ages": ages,
         "children_birthdates": [birthdate(x, on) for x in ages]}
    p["nazov"] = nazov or _party_text(a, ages)
    return p


def _parties(raw, on):
    """[primary party, extra parties…]. Without 'skupiny' the top-level adults/children_ages are the only party; with
    both, the top-level party is the default one (the matching skupina, or an extra first entry)."""
    top = None
    if "adults" in raw or "children_ages" in raw:
        if "adults" not in raw or "children_ages" not in raw:
            raise SettingsError("adults a children_ages patria k sebe – zadajte obe alebo ani jednu "
                                "(skupiny sa zadávajú v 'skupiny')")
        top = _party(raw["adults"], raw["children_ages"], None, "adults/children_ages", on)
    if "skupiny" not in raw:
        return [top]
    sk = raw["skupiny"]
    if not isinstance(sk, list) or not sk:
        raise SettingsError("skupiny: čakám zoznam skupín, každá na novom riadku začínajúcom '- ', napr. "
                            "- {nazov: Ja + 2 deti, adults: 1, children_ages: [10, 12]}")
    out = []
    for i, x in enumerate(sk, 1):
        key = f"skupiny ({i}.)"
        if not isinstance(x, dict):
            raise SettingsError(f"{key}: čakám {{nazov: ..., adults: N, children_ages: [...]}}")
        bad = sorted(set(map(str, x)) - {"nazov", "adults", "children_ages"})
        if bad:
            raise SettingsError(f"{key}: neznáme položky (preklep?): {', '.join(bad)}")
        if "adults" not in x:
            raise SettingsError(f"{key}: chýba adults (počet dospelých)")
        nazov = " ".join(str(x.get("nazov") or "").split())
        if len(nazov) > 30:
            raise SettingsError(f"{key}: názov '{nazov[:20]}…' je príliš dlhý (najviac 30 znakov)")
        p = _party(x["adults"], x.get("children_ages"), nazov, key, on)
        if any(q["id"] == p["id"] for q in out):
            raise SettingsError(f"{key}: rovnaké zloženie ({party_label(p)}) už má iná skupina")
        if any(q["nazov"].lower() == p["nazov"].lower() for q in out):
            raise SettingsError(f"{key}: názov '{p['nazov']}' už má iná skupina")
        out.append(p)
    if top:
        same = next((q for q in out if q["id"] == top["id"]), None)
        if same:
            out.remove(same)
            top = same
        out.insert(0, top)
    if len(out) > PARTIES_MAX:
        raise SettingsError(f"skupiny: najviac {PARTIES_MAX} skupiny" +
                            (" (vrátane adults/children_ages)" if top else ""))
    return out


def party_cfg(cfg, party):
    """cfg for one party of cfg['parties']: the party's adults/children_ages/birthdates, everything else shared."""
    return dict(cfg, adults=party["adults"], children_ages=list(party["children_ages"]),
                children_birthdates=list(party["children_birthdates"]), party_id=party["id"])


def extra_parties(cfg):
    """[(party, party cfg)] of the parties other than the primary (default) one."""
    return [(p, party_cfg(cfg, p)) for p in cfg.get("parties", [])[1:]]


SIDE_CRITERIA = ("rodinna_izba", "aquapark", "detsky_klub", "all_inclusive")
SIDE_DEFAULT = {"enabled": True, "max_vzdialenost_od_plaze_m": 300,
                "oblasti": ["Side", "Kumköy", "Çolaklı", "Evrenseki", "Titreyengöl", "Sorgun", "Kızılağaç", "Manavgat"],
                "kriteria": list(SIDE_CRITERIA), "transfer_eur": 60}


def _side(v):
    """side_hotely (tab "Side – hotely pri pláži") -> {enabled, max_m, oblasti: [area keys], kriteria, transfer_eur}.
    Missing section = defaults; missing keys inside it = their defaults."""
    from side_hotels import AREAS, area_key
    if v is None:
        v = {}
    if not isinstance(v, dict):
        raise SettingsError("side_hotely: čakám položky v tvare 'kľúč: hodnota' (enabled, max_vzdialenost_od_plaze_m, "
                            "oblasti, kriteria, transfer_eur)")
    bad = sorted(set(map(str, v)) - set(SIDE_DEFAULT))
    if bad:
        raise SettingsError(f"side_hotely: neznáme položky (preklep?): {', '.join(bad)}")
    r = dict(SIDE_DEFAULT, **v)
    en = r["enabled"]
    if not isinstance(en, bool):
        raise SettingsError("side_hotely: enabled musí byť true alebo false")
    ob = r["oblasti"]
    if isinstance(ob, str):
        ob = [ob]
    if not isinstance(ob, list) or not ob:
        raise SettingsError("side_hotely: oblasti – čakám zoznam, napr. [Side, Kumköy, Çolaklı]")
    keys = []
    for x in ob:
        k = area_key(str(x))
        if k not in AREAS:
            raise SettingsError(f"side_hotely: neznáma oblasť '{x}' (známe: "
                                f"{', '.join(a[0] for a in AREAS.values())})")
        if k not in keys:
            keys.append(k)
    kr = r["kriteria"] if r["kriteria"] is not None else []
    if isinstance(kr, str):
        kr = [kr]
    if not isinstance(kr, list) or any(str(x) not in SIDE_CRITERIA for x in kr):
        raise SettingsError(f"side_hotely: kriteria – povolené sú {', '.join(SIDE_CRITERIA)}")
    return {"enabled": en, "max_m": _int(r["max_vzdialenost_od_plaze_m"], "side_hotely: max_vzdialenost_od_plaze_m",
                                         50, 1000),
            "oblasti": keys, "kriteria": [k for k in SIDE_CRITERIA if k in kr],
            "transfer_eur": _int(r["transfer_eur"], "side_hotely: transfer_eur", 0, 1000)}


WATCH_MAX = 20


def _watched(v):
    """sledovane_hotely: list of hotel names (partial, any case/diacritics) -> list of unique stripped strings."""
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        raise SettingsError("sledovane_hotely: čakám zoznam názvov, každý na novom riadku začínajúcom '- '")
    out, seen = [], set()
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (str, int, float)):
            raise SettingsError(f"sledovane_hotely: '{x}' nie je názov hotela (čakám text, napr. - Sural)")
        name = " ".join(str(x).split())
        if not name:
            continue
        if len(name) > 60:
            raise SettingsError(f"sledovane_hotely: '{name[:30]}…' je príliš dlhý názov (najviac 60 znakov)")
        base, cc = split_term(name)
        if "@" in name and not cc:
            raise SettingsError(f"sledovane_hotely: '{name}' – krajinu píšte ako @ a dvojpísmenový kód, napr. @TR")
        key = norm_name(base) + ("@" + cc if cc else "")
        if not norm_name(base):
            raise SettingsError(f"sledovane_hotely: '{name}' – zadajte aj vlastný názov hotela, nie len "
                                "slová ako hotel/resort/spa")
        if key not in seen:
            seen.add(key)
            out.append(name)
    if len(out) > WATCH_MAX:
        raise SettingsError(f"sledovane_hotely: najviac {WATCH_MAX} hotelov")
    return out


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


def party_label(cfg=CONFIG, case="nom"):
    """'1 dospelý + 2 deti (10 a 12 r.)'; case='gen' -> '1 dospelého + 2 detí (10 a 12 r.)'."""
    return _party_text(cfg["adults"], cfg["children_ages"], case)


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
    c.pop("party_id", None)
    c["parties"] = [{"id": p["id"], "nazov": p["nazov"], "adults": p["adults"], "children_ages": p["children_ages"],
                     "party_size": party_size(p), "label": party_label(p)} for p in cfg.get("parties") or []]
    c["default_party"] = cfg.get("party_id") or (c["parties"][0]["id"] if c["parties"] else None)
    return c
