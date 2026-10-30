"""Shared helpers for adapters: polite HTTP, normalisation, offer construction."""

import hashlib
import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

import requests

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 dovolenka-tracker/1.0 (+https://github.com/KaStihl/Holiday-tracker)"
)

_local = threading.local()  # run.py scrapes the agencies in parallel threads (each agency itself sequentially)
_robots = {}


def session():
    s = getattr(_local, "session", None)
    if s is None:
        s = _local.session = requests.Session()
        s.headers.update({
            "User-Agent": UA,
            "Accept-Language": "sk-SK,sk;q=0.9,cs;q=0.8,en;q=0.7",
        })
    return s


DUMP_DIR = Path(__file__).resolve().parent / "debug"
_dump_n = 0


def dump(url, status, body):
    """DOVOLENKA_DUMP=1: keep every response body (max 1.5 MB) in debug/ for offline parser work."""
    global _dump_n
    if os.environ.get("DOVOLENKA_DUMP") != "1":
        return
    if not _dump_n and (DUMP_DIR / "index.txt").exists():  # continue numbering across processes
        _dump_n = len((DUMP_DIR / "index.txt").read_text().splitlines())
    _dump_n += 1
    parts = urlsplit(url)
    slug = re.sub(r"[^a-z0-9]+", "-", (parts.path + "-" + parts.query).lower()).strip("-")[:60] or "root"
    ext = "json" if body.lstrip()[:1] in ("{", "[") else "html"
    name = f"{_dump_n:03d}_{parts.netloc.replace('www.', '')}_{slug}.{ext}"
    DUMP_DIR.mkdir(exist_ok=True)
    (DUMP_DIR / name).write_text(body[:1_500_000], encoding="utf-8")
    with open(DUMP_DIR / "index.txt", "a", encoding="utf-8") as f:
        f.write(f"{_dump_n:03d} {status} {url}\n")


_diag_seen = set()


def diag(tag, obj):
    """TEMPORARY (long-haul fixture collection): DOVOLENKA_DIAG=1 prints one sample per tag to the job log."""
    if os.environ.get("DOVOLENKA_DIAG") != "1" or tag in _diag_seen:
        return
    _diag_seen.add(tag)
    import json
    print(f"DIAG {tag} " + (obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)))


class RobotsDisallowed(Exception):
    pass


class Robots:
    """robots.txt with Google-style matching: '*' wildcards, '$' anchor, longest rule wins, Allow wins ties.
    (urllib.robotparser ignores wildcards and on Python 3.12 even let /direct/tour_hotel/ through.)"""

    def __init__(self, text, agent):
        agent = agent.lower()
        groups, cur, in_rules = [], None, False
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = (x.strip() for x in line.split(":", 1))
            k = k.lower()
            if k == "user-agent":
                if cur is None or in_rules:
                    cur, in_rules = {"agents": [], "rules": []}, False
                    groups.append(cur)
                cur["agents"].append(v.lower())
            elif k in ("allow", "disallow") and cur is not None:
                in_rules = True
                if v:
                    cur["rules"].append((k == "allow", v))
        mine = [g for g in groups if any(a != "*" and a in agent for a in g["agents"])]
        mine = mine or [g for g in groups if "*" in g["agents"]]
        self.rules = [r for g in mine for r in g["rules"]]

    @staticmethod
    def _rx(pattern):
        rx = re.escape(pattern).replace(r"\*", ".*")
        return re.compile(rx[:-2] + "$" if rx.endswith(r"\$") else rx)

    def can_fetch(self, url):
        parts = urlsplit(url)
        path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        best = None
        for allow, pat in self.rules:
            if self._rx(pat).match(path) and (best is None or len(pat) > len(best[1])
                                              or (len(pat) == len(best[1]) and allow)):
                best = (allow, pat)
        return best is None or best[0]


def allowed(url):
    """robots.txt check, cached per host. Unreachable robots.txt counts as allowed."""
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    rp = _robots.get(base)
    if rp is None:
        try:
            r = session().get(base + "/robots.txt", timeout=15)
            dump(r.url, r.status_code, r.text)
            rp = Robots(r.text if r.ok else "", UA)
        except requests.RequestException:
            rp = Robots("", UA)
        _robots[base] = rp
    return rp.can_fetch(url)


def get(url, *, params=None, headers=None, retries=2, delay=1.5, as_json=False, method="GET", json_body=None,
        data=None):
    """GET/POST with robots check, small retry loop and a pause between calls."""
    if not allowed(url):
        raise RobotsDisallowed(url)
    last = None
    for attempt in range(retries + 1):
        try:
            r = session().request(method, url, params=params, headers=headers, json=json_body, data=data,
                                  timeout=30)
            dump(r.url if method == "GET" else url, r.status_code, r.text)
            if 400 <= r.status_code < 500 and r.status_code != 429:
                time.sleep(delay)
                r.raise_for_status()  # client errors (403 block, 404) are final, no retry
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(delay * (attempt + 2))
                continue
            r.raise_for_status()
            time.sleep(delay)
            return r.json() if as_json else r.text
        except requests.HTTPError as e:
            if e.response is not None and 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                raise
            last = e
        except requests.RequestException as e:
            last = e
            if attempt < retries:
                time.sleep(delay * (attempt + 2))
    raise last


# --- normalisation ---------------------------------------------------------

def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


_BOARD_PATTERNS = [
    ("UAI", r"ultra\s*all|uai|ultra\s*all\s*inclusive|ultra\s*a\.?i"),
    ("AI", r"all\s*inclusive|\bai\b|all\s*incl|vsetko\s*v\s*cene|all-inclusive"),
    ("FB", r"plna\s*penzia|\bfb\b|full\s*board"),
    ("HB", r"polpenzia|\bhb\b|half\s*board|polopenze"),
    ("BB", r"ranajky|\bbb\b|snidane|breakfast"),
    ("RO", r"bez\s*stravy|\bro\b|room\s*only|\bos\b"),
]


def norm_board(text):
    if not text:
        return None
    t = strip_accents(str(text)).lower()
    for code, pat in _BOARD_PATTERNS:
        if re.search(pat, t):
            return code
    return None


# country code -> name prefixes (accent-free, lower case; Slovak, Czech, English and well-known resorts).
# Matched at a word start, so short names like "kuba" or "oman" don't fire inside other words.
_COUNTRIES = {
    "HR": ["chorvatsko", "croatia", "hrvatska"],
    "TR": ["turecko", "turkey", "turkiye"],
    "CY": ["cyprus", "kypr", "cypr"],
    "IT": ["taliansko", "italie", "italy", "italia", "sicilia", "sardinia", "sardinie", "sicilie"],
    "GR": ["grecko", "recko", "greece"],
    "ES": ["spanielsko", "spanelsko", "spain", "kanarske", "mallorca", "malorka", "tenerife", "gran canaria",
           "fuerteventura", "lanzarote", "ibiza", "menorca"],
    "MT": ["malta"],
    "PT": ["portugalsko", "portugal", "madeira"],
    "ME": ["cierna hora", "cerna hora", "montenegro"],
    "AL": ["albansko", "albanie", "albania"],
    "BG": ["bulharsko", "bulgaria"],
    "EG": ["egypt"],
    "TN": ["tunisko", "tunisia"],
    "SI": ["slovinsko", "slovenia"],
    "FR": ["francuzsko", "francie", "france", "korzika"],
    "MA": ["maroko", "morocco"],
    "PL": ["polsko", "poland", "polska"],
    "SK": ["slovensko", "slovakia"],
    "CZ": ["cesko", "ceska republika", "czech"],
    "AT": ["rakusko", "austria", "osterreich"],
    "HU": ["madarsko", "hungary", "balaton"],
    "DE": ["nemecko", "germany", "deutschland"],
    "RO": ["rumunsko", "romania"],
    "AE": ["spojene arabske emiraty", "arabske emiraty", "emiraty", "united arab emirates", "sae\\b", "uae\\b",
           "dubaj", "dubai", "abu dhabi", "ras al khaimah", "fujairah", "sharjah"],
    "OM": ["oman\\b", "omanu", "omansky", "salalah", "muscat", "maskat"],
    "JO": ["jordansko", "jordan", "akaba", "aqaba"],
    "MV": ["maldiv", "maledivy", "maldives"],
    "MU": ["mauricius", "mauritius"],
    "SC": ["seychel", "sejsel"],
    "LK": ["sri lanka", "srilanka"],
    "TH": ["thajsko", "thailand", "phuket", "krabi", "koh samui", "ko samui", "khao lak", "pattaya"],
    "ID": ["indonez", "bali\\b", "lombok"],
    "VN": ["vietnam", "phu quoc", "nha trang"],
    "TZ": ["tanzan", "zanzibar"],
    "KE": ["kena\\b", "kenya", "kenia", "mombasa", "diani"],
    "CV": ["kapverd", "cape verde", "cabo verde", "boa vista"],
    "DO": ["dominikansk", "dominican", "punta cana", "puerto plata", "bayahibe", "la romana"],
    "MX": ["mexiko", "mexico", "cancun", "riviera maya", "playa del carmen"],
    "CU": ["kuba\\b", "cuba\\b", "varadero", "havana", "habana"],
}
_COUNTRY_RX = [(code, re.compile(r"\b(?:" + "|".join(names) + ")")) for code, names in _COUNTRIES.items()]


def norm_country(text):
    """Country code from a free-text country/region name, or None."""
    if not text:
        return None
    t = strip_accents(str(text)).lower()
    if len(t) == 2 and t.upper() in _COUNTRIES:
        return t.upper()
    for code, rx in _COUNTRY_RX:
        if rx.search(t):
            return code
    return None


def parse_price(text):
    """'2 780 €' / '2.780,00 EUR' / 2780 -> 2780 (int) or None."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(round(text))
    t = re.sub(r"[^\d,.]", "", str(text))
    if not t:
        return None
    # thousands separators: dots or commas followed by exactly 3 digits
    t = re.sub(r"[.,](?=\d{3}(\D|$))", "", t)
    t = t.replace(",", ".")
    try:
        return int(round(float(t)))
    except ValueError:
        return None


def offer_id(source, hotel, date_from, nights, transport, departure):
    key = "|".join(str(x or "").lower() for x in (source, hotel, date_from, nights, transport, departure))
    return f"{source}:{hashlib.sha1(key.encode()).hexdigest()[:12]}"


def https_or_none(url):
    return url if isinstance(url, str) and url.startswith("https://") else None
