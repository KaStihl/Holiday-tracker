/* Dovolenka tracker – vanilla JS, no dependencies.
 * Data contract: scraper/run.py writes ./data/offers.json ({generated_at, criteria, sources, deeplinks, offers}).
 * Everything coming from the data file is treated as untrusted: DOM is built with
 * textContent / setAttribute only and URLs must start with https://.
 */
(function () {
  "use strict";

  var TZ = "Europe/Bratislava";
  // Must match the cron in .github/workflows/dovolenka-refresh.yml (UTC); data lands ~15 min later.
  var RUN_UTC = [[4, 17], [16, 17]];
  var STORE_KEY = "dovolenka.filters.v2";
  var OLD_STORE_KEY = "dovolenka.filters.v1";
  var SETTINGS_URL = "https://github.com/KaStihl/Holiday-tracker/edit/main/nastavenia.yml";
  var PAGE = 40;
  var AI_BOARDS = { AI: 1, UAI: 1 };
  var BOARDS = ["UAI", "AI", "FB", "HB", "BB", "RO"];
  var BOARD_LABEL = { UAI: "Ultra All Inclusive", AI: "All Inclusive", FB: "Plná penzia", HB: "Polpenzia", BB: "Raňajky", RO: "Bez stravy" };
  var STATUS_LABEL = { ok: "ok", error: "chyba", empty: "prázdne", disabled: "vypnuté" };
  var CONTINENTS = ["Európa", "Afrika", "Blízky východ", "Ázia", "Indický oceán", "Karibik a Amerika"];
  var CONT_ICON = { "Európa": "🏛️", "Afrika": "🐪", "Blízky východ": "🕌", "Ázia": "🛕", "Indický oceán": "🐠", "Karibik a Amerika": "🌴" };
  // Fallback when an offer has no "continent" field; anything not listed is Európa.
  var CC_CONT = {};
  [["Afrika", "EG TN MA CV TZ KE ZA GM SN"], ["Blízky východ", "AE OM JO QA BH IL SA"],
   ["Ázia", "LK TH ID VN MY PH KH LA CN JP"], ["Indický oceán", "MV MU SC RE"],
   ["Karibik a Amerika", "DO MX CU JM BS BB US BR CR PA AW CW LC"]].forEach(function (g) {
    g[1].split(" ").forEach(function (cc) { CC_CONT[cc] = g[0]; });
  });
  var SORTS = {
    score: "Skóre (najlepšia zhoda)", price: "Cena spolu (od najnižšej)", pp: "Cena za osobu (od najnižšej)",
    discount: "Zľava (najväčšia)", date: "Dátum odchodu", rating: "Hodnotenie hostí", drop: "Pokles ceny (najväčší)"
  };
  var STAR_OPTS = [0, 2, 3, 4, 4.5, 5];
  var RATING_OPTS = [0, 7, 8, 8.5, 9];

  var params = new URLSearchParams(location.search);
  var isSample = params.get("sample") === "1";
  var DATA_URL = isSample ? "./data/offers.sample.json" : "./data/offers.json";

  var data = null;
  var allOffers = [];
  var CFG = null;      // derived from data.criteria + data
  var DEFAULTS = null; // filter state on first visit (criteria-based)
  var OPEN = null;     // "no filter at all" state
  var state = null;
  var shown = PAGE;

  // ---------- helpers ----------
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function safeUrl(u) {
    if (typeof u !== "string") return null;
    u = u.trim();
    if (!/^https:\/\//i.test(u)) return null;
    try { var p = new URL(u); return p.protocol === "https:" ? p.href : null; } catch (e) { return null; }
  }
  function num(v) { var n = typeof v === "number" ? v : parseFloat(v); return isFinite(n) ? n : null; }
  function str(v) { return v === null || v === undefined ? "" : String(v); }
  function fold(s) { return str(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
  function isDay(s) { return typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s); }
  function sameArr(a, b) { return a.length === b.length && a.every(function (x, i) { return x === b[i]; }); }
  function strList(v, max) {
    return Array.isArray(v) ? v.filter(function (x) { return typeof x === "string" && x.length && x.length <= 60; }).slice(0, max || 60) : [];
  }

  var nf = new Intl.NumberFormat("sk-SK", { maximumFractionDigits: 0 });
  function eur(v) { v = num(v); return v === null ? "—" : nf.format(Math.round(v)) + " €"; }
  function signedEur(v) { return (v > 0 ? "+" : v < 0 ? "−" : "±") + nf.format(Math.abs(Math.round(v))) + " €"; }
  function decimal(v) { return String(v).replace(".", ","); }

  function plural(n, one, few, many) { return n === 1 ? one : n >= 2 && n <= 4 ? few : many; }
  function nightsWord(n) { return plural(n, "noc", "noci", "nocí"); }
  function offersWord(n) { return plural(n, "ponuka", "ponuky", "ponúk"); }

  function flag(cc) {
    if (typeof cc !== "string" || !/^[A-Za-z]{2}$/.test(cc)) return "🏳️";
    cc = cc.toUpperCase();
    return String.fromCodePoint(0x1F1E6 + cc.charCodeAt(0) - 65, 0x1F1E6 + cc.charCodeAt(1) - 65);
  }

  var WD = ["ne", "po", "ut", "st", "št", "pi", "so"];
  function parseDay(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(str(s));
    return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])) : null;
  }
  function fmtDay(d, withYear) {
    return WD[d.getUTCDay()] + " " + d.getUTCDate() + ". " + (d.getUTCMonth() + 1) + "." + (withYear ? " " + d.getUTCFullYear() : "");
  }
  function shortDay(s, withYear) {
    var d = parseDay(s);
    return d ? d.getUTCDate() + ". " + (d.getUTCMonth() + 1) + "." + (withYear ? " " + d.getUTCFullYear() : "") : "";
  }

  function nextRun(now) {
    for (var add = 0; add < 2; add++) {
      for (var i = 0; i < RUN_UTC.length; i++) {
        var cand = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + add, RUN_UTC[i][0], RUN_UTC[i][1]));
        if (cand.getTime() > now.getTime()) return cand;
      }
    }
    return null;
  }
  var dtFmt = new Intl.DateTimeFormat("sk-SK", { timeZone: TZ, day: "numeric", month: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
  var rtf = typeof Intl.RelativeTimeFormat === "function" ? new Intl.RelativeTimeFormat("sk", { numeric: "auto" }) : null;
  function relTime(date, now) {
    var diff = (date.getTime() - now.getTime()) / 1000;
    var a = Math.abs(diff);
    var unit, val;
    if (a < 60) { unit = "second"; val = Math.round(diff); }
    else if (a < 3600) { unit = "minute"; val = Math.round(diff / 60); }
    else if (a < 86400 * 2) { unit = "hour"; val = Math.round(diff / 3600); }
    else { unit = "day"; val = Math.round(diff / 86400); }
    if (!rtf) return "";
    if (unit === "second") return diff < 0 ? "práve teraz" : "o chvíľu";
    return rtf.format(val, unit);
  }

  // ---------- criteria / party ----------
  function buildConfig() {
    var c = data && data.criteria && typeof data.criteria === "object" ? data.criteria : {};
    var adults = num(c.adults);
    adults = adults !== null && adults >= 1 && adults <= 20 ? Math.round(adults) : null;
    var kids = Array.isArray(c.children_ages) ? c.children_ages.map(num).filter(function (a) { return a !== null && a >= 0 && a < 30; }).map(Math.round) : [];
    var budget = num(c.budget); if (budget === null) budget = num(c.budget_eur);
    if (budget === null || budget <= 0) budget = 3000;
    var cap = num(c.price_cap); if (cap === null || cap <= 0) cap = 6000;
    var maxP = 0, minN = null, maxN = null, minD = "", maxD = "";
    allOffers.forEach(function (o) {
      if (o.price_total > maxP) maxP = o.price_total;
      if (o.nights !== null) { minN = minN === null ? o.nights : Math.min(minN, o.nights); maxN = maxN === null ? o.nights : Math.max(maxN, o.nights); }
      if (isDay(o.date_from)) { if (!minD || o.date_from < minD) minD = o.date_from; if (!maxD || o.date_from > maxD) maxD = o.date_from; }
    });
    var priceMax = Math.ceil(Math.max(cap, budget, maxP) / 100) * 100;
    var cnMin = num(c.nights_min), cnMax = num(c.nights_max);
    var nLo = Math.min(cnMin !== null ? cnMin : 7, minN !== null ? minN : 99);
    var nHi = Math.max(cnMax !== null ? cnMax : 14, maxN !== null ? maxN : 0);
    nLo = Math.max(1, Math.round(nLo)); nHi = Math.min(60, Math.max(nLo, Math.round(nHi)));
    var dMin = isDay(c.date_from) ? c.date_from : minD;
    var dMax = isDay(c.date_to) ? c.date_to : maxD;
    if (minD && dMin && minD < dMin) dMin = minD;
    if (maxD && dMax && maxD > dMax) dMax = maxD;
    var pref = strList(c.boards_preferred).map(function (b) { return b.toUpperCase(); }).filter(function (b) { return BOARDS.indexOf(b) >= 0; });
    var dogs = num(c.dogs);
    var transports = strList(c.transports).filter(function (t) { return t === "flight" || t === "car"; });
    return {
      raw: c, adults: adults, kids: kids,
      persons: adults !== null ? adults + kids.length : null,
      budget: budget, cap: cap, priceMax: priceMax,
      critNights: cnMin !== null && cnMax !== null ? [cnMin, cnMax] : null,
      nLo: nLo, nHi: nHi, dMin: dMin, dMax: dMax,
      critDates: isDay(c.date_from) && isDay(c.date_to) ? [c.date_from, c.date_to] : null,
      boardsPref: pref.length ? pref : ["UAI", "AI"],
      departures: strList(c.departures).map(function (d) { return d.toUpperCase(); }).filter(function (d) { return /^[A-Z]{3,4}$/.test(d); }),
      transports: transports,
      dogs: dogs !== null && dogs >= 0 ? Math.round(dogs) : null,
      watched: watchedTerms(c)
    };
  }
  // watched hotel terms: offers.json "watched" [{term, count, links}] (newer files) or criteria.watched
  function watchedTerms(c) {
    var list = Array.isArray(data.watched) ? data.watched.filter(function (w) { return w && typeof w.term === "string"; })
      .map(function (w) { return w.term; }) : strList(c.watched, 20);
    allOffers.forEach(function (o) { if (o.watched && list.indexOf(o.watched) < 0) list.push(o.watched); });
    return list.filter(function (t) { return t.length && t.length <= 80; }).slice(0, 20);
  }
  function partyLong() {
    if (!CFG || CFG.adults === null) return "skupina neuvedená";
    var a = CFG.adults, k = CFG.kids.length;
    var s = a + " " + plural(a, "dospelý", "dospelí", "dospelých");
    if (k) s += " + " + k + " " + plural(k, "dieťa", "deti", "detí") + " (" + CFG.kids.join(", ") + " r.)";
    return s;
  }
  function partyShort() {
    if (!CFG || CFG.adults === null) return "";
    return CFG.kids.length ? CFG.adults + "+" + CFG.kids.length : CFG.adults + " dosp.";
  }
  function dogsText() {
    if (!CFG || !CFG.dogs) return "";
    return CFG.dogs === 1 ? "so psom" : "s " + CFG.dogs + " " + plural(CFG.dogs, "psom", "psami", "psami");
  }
  function perPerson() { return !!(state && state.pp && CFG.persons); }
  function pv(v) { return perPerson() ? v / CFG.persons : v; }
  function priceText(v) { return eur(pv(v)) + (perPerson() ? " /os." : ""); }

  // ---------- state ----------
  function makeDefaults() {
    DEFAULTS = {
      t: "all", ct: [], c: [], pmin: 0, pmax: Math.min(CFG.budget, CFG.priceMax), df: "", dt: "",
      nmin: CFG.nLo, nmax: CFG.nHi, b: CFG.boardsPref.slice(), st: 0, r: 0, d: [], src: [],
      ex: false, z: false, dog: false, dr: false, w: false, q: "", s: "score", pp: false
    };
    OPEN = clone(DEFAULTS);
    OPEN.pmax = CFG.priceMax;
    OPEN.b = [];
  }
  function sanitizeState(s) {
    var o = clone(DEFAULTS);
    if (!s || typeof s !== "object") return o;
    if (s.t === "flight" || s.t === "car" || s.t === "all") o.t = s.t;
    o.ct = strList(s.ct, 10).filter(function (x) { return CONTINENTS.indexOf(x) >= 0; });
    o.c = strList(s.c, 60);
    o.d = strList(s.d, 20).map(function (x) { return x.toUpperCase(); }).filter(function (x) { return /^[A-Z]{3,4}$/.test(x); });
    o.src = strList(s.src, 40);
    if (Array.isArray(s.b)) o.b = s.b.filter(function (x) { return BOARDS.indexOf(x) >= 0; });
    // legacy v1 state: p = max price, ai = only AI
    if (s.pmax === undefined && s.p !== undefined) s.pmax = s.p;
    if (s.b === undefined && typeof s.ai === "boolean") o.b = s.ai ? CFG.boardsPref.slice() : [];
    if (typeof s.d === "string" && s.d) o.d = [s.d.toUpperCase()].filter(function (x) { return /^[A-Z]{3,4}$/.test(x); });
    var pmin = num(s.pmin), pmax = num(s.pmax);
    if (pmin !== null) o.pmin = Math.min(CFG.priceMax, Math.max(0, Math.round(pmin)));
    if (pmax !== null) o.pmax = Math.min(CFG.priceMax, Math.max(0, Math.round(pmax)));
    if (o.pmin > o.pmax) { var tp = o.pmin; o.pmin = o.pmax; o.pmax = tp; }
    if (isDay(s.df)) o.df = s.df;
    if (isDay(s.dt)) o.dt = s.dt;
    if (o.df && o.dt && o.df > o.dt) { var td = o.df; o.df = o.dt; o.dt = td; }
    var a = num(s.nmin), b = num(s.nmax);
    if (a !== null && a >= CFG.nLo && a <= CFG.nHi) o.nmin = Math.round(a);
    if (b !== null && b >= CFG.nLo && b <= CFG.nHi) o.nmax = Math.round(b);
    if (o.nmin > o.nmax) { var t = o.nmin; o.nmin = o.nmax; o.nmax = t; }
    var st = num(s.st); if (st !== null && STAR_OPTS.indexOf(st) >= 0) o.st = st;
    var r = num(s.r); if (r !== null && RATING_OPTS.indexOf(r) >= 0) o.r = r;
    ["ex", "z", "dog", "dr", "w", "pp"].forEach(function (k) { if (typeof s[k] === "boolean") o[k] = s[k]; });
    if (typeof s.q === "string") o.q = s.q.slice(0, 80);
    if (SORTS[s.s]) o.s = s.s;
    return o;
  }
  var ARR_KEYS = ["ct", "c", "b", "d", "src"];
  var BOOL_KEYS = ["ex", "z", "dog", "dr", "w", "pp"];
  function stateToHash(s) {
    var h = new URLSearchParams();
    Object.keys(DEFAULTS).forEach(function (k) {
      if (k === "nmin" || k === "nmax") return;
      var v = s[k], dv = DEFAULTS[k];
      if (ARR_KEYS.indexOf(k) >= 0) { if (!sameArr(v, dv)) h.set(k, v.join(",")); }
      else if (BOOL_KEYS.indexOf(k) >= 0) { if (v !== dv) h.set(k, v ? "1" : "0"); }
      else if (v !== dv) h.set(k, String(v));
    });
    if (s.nmin !== DEFAULTS.nmin || s.nmax !== DEFAULTS.nmax) h.set("n", s.nmin + "-" + s.nmax);
    return h.toString();
  }
  function hashToState(hash) {
    var h = new URLSearchParams(hash.replace(/^#/, ""));
    if (!Array.from(h.keys()).length) return null;
    var s = clone(DEFAULTS);
    h.forEach(function (v, k) {
      if (ARR_KEYS.indexOf(k) >= 0) s[k] = v.split(",").filter(Boolean);
      else if (BOOL_KEYS.indexOf(k) >= 0) s[k] = v === "1";
      else if (k === "n") { var n = v.split("-"); s.nmin = n[0]; s.nmax = n[1]; }
      else if (k === "ai") s.ai = v === "1";  // legacy v1 link
      else if (k === "p") { if (!h.has("pmax")) s.pmax = v; } // legacy v1 link
      else s[k] = v;
    });
    if (h.has("ai") && !h.has("b")) delete s.b;
    if (h.has("d") && s.d.length === 1) s.d = s.d[0];
    return sanitizeState(s);
  }
  function loadState() {
    var fromHash = hashToState(location.hash);
    if (fromHash) return fromHash;
    try {
      var raw = window.localStorage.getItem(STORE_KEY);
      if (raw) return sanitizeState(JSON.parse(raw));
      raw = window.localStorage.getItem(OLD_STORE_KEY);
      if (raw) return sanitizeState(JSON.parse(raw));
    } catch (e) { /* storage blocked */ }
    return clone(DEFAULTS);
  }
  function saveState() {
    try { window.localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) { /* ignore */ }
    var h = stateToHash(state);
    var url = location.pathname + location.search + (h ? "#" + h : "");
    try { history.replaceState(null, "", url); } catch (e) { /* ignore (file://) */ }
  }

  // ---------- normalize data ----------
  function normOffer(o) {
    if (!o || typeof o !== "object") return null;
    var price = num(o.price_total);
    if (price === null) return null;
    var hist = Array.isArray(o.price_history) ? o.price_history.filter(function (p) {
      return Array.isArray(p) && p.length >= 2 && num(p[1]) !== null;
    }).map(function (p) { return [str(p[0]), num(p[1])]; }) : [];
    var cc = str(o.country_code).toUpperCase();
    var cont = CONTINENTS.indexOf(o.continent) >= 0 ? o.continent : (CC_CONT[cc] || "Európa");
    var n = {
      id: str(o.id),
      source: str(o.source) || "?", source_name: str(o.source_name || o.source) || "?",
      hotel: str(o.hotel) || "Bez názvu",
      stars: num(o.stars), rating: num(o.rating),
      country: str(o.country) || "Iné", country_code: cc, continent: cont,
      region: str(o.region), place: str(o.place),
      board: o.board ? str(o.board).toUpperCase() : null,
      transport: o.transport === "car" ? "car" : "flight",
      departure: o.departure ? str(o.departure).toUpperCase() : null,
      date_from: str(o.date_from).slice(0, 10), date_to: str(o.date_to).slice(0, 10), nights: num(o.nights),
      price_total: price, price_original: num(o.price_original),
      discount_pct: num(o.discount_pct), discount_label: o.discount_label ? str(o.discount_label) : null,
      price_exact: o.price_exact === true,
      price_note: o.price_note ? str(o.price_note).slice(0, 200) : "",
      pets_allowed: o.pets_allowed === true ? true : o.pets_allowed === false ? false : null,
      image: safeUrl(o.image), url: safeUrl(o.url),
      score: num(o.score),
      first_seen: str(o.first_seen), last_seen: str(o.last_seen),
      price_history: hist,
      price_change: num(o.price_change),
      watched: typeof o.watched === "string" && o.watched.length <= 80 ? o.watched : ""
    };
    n._text = fold([n.hotel, n.place, n.region, n.country].join(" "));
    return n;
  }
  function isDiscount(o) {
    return !!(o.discount_label || (o.discount_pct && o.discount_pct > 0) || (o.price_original && o.price_original > o.price_total));
  }
  function discPct(o) {
    if (o.discount_pct) return o.discount_pct;
    if (o.price_original && o.price_original > o.price_total) return Math.round((1 - o.price_total / o.price_original) * 100);
    return 0;
  }

  // ---------- filtering ----------
  // skip: facet to ignore ("geo" = continent+country, "c" = country only, "b", "d", "src", "t") for counts.
  var qWords = [];
  function matches(o, skip) {
    var s = state;
    if (skip !== "t" && s.t !== "all" && o.transport !== s.t) return false;
    if (skip !== "geo") {
      if (s.ct.length && s.ct.indexOf(o.continent) < 0) return false;
      if (skip !== "c" && s.c.length && s.c.indexOf(o.country) < 0) return false;
    }
    if (o.price_total < s.pmin) return false;
    if (s.pmax < CFG.priceMax && o.price_total > s.pmax) return false;
    if (s.df && !(o.date_from && o.date_from >= s.df)) return false;
    if (s.dt && !(o.date_from && o.date_from <= s.dt)) return false;
    if (o.nights !== null && (o.nights < s.nmin || o.nights > s.nmax)) return false;
    if (skip !== "b" && s.b.length && !(o.board && s.b.indexOf(o.board) >= 0)) return false;
    if (s.st && !(o.stars !== null && o.stars >= s.st)) return false;
    if (s.r && !(o.rating !== null && o.rating >= s.r)) return false;
    if (skip !== "d" && s.d.length && !(o.transport === "flight" && s.d.indexOf(o.departure) >= 0)) return false;
    if (skip !== "src" && s.src.length && s.src.indexOf(o.source) < 0) return false;
    if (s.ex && !o.price_exact) return false;
    if (s.z && !isDiscount(o)) return false;
    if (s.dog && !(o.transport === "car" && o.pets_allowed === true)) return false;
    if (s.dr && !(o.price_change !== null && o.price_change < 0)) return false;
    if (s.w && !o.watched) return false;
    for (var i = 0; i < qWords.length; i++) if (o._text.indexOf(qWords[i]) < 0) return false;
    return true;
  }
  function facetCounts(skip, keyFn) {
    var out = {};
    allOffers.forEach(function (o) {
      if (!matches(o, skip)) return;
      var k = keyFn(o);
      if (k !== null && k !== undefined) out[k] = (out[k] || 0) + 1;
    });
    return out;
  }
  function sortOffers(list) {
    function nullLast(v) { return v === null ? -Infinity : v; }
    var by = {
      score: function (a, b) { return (b.score || 0) - (a.score || 0) || a.price_total - b.price_total; },
      price: function (a, b) { return a.price_total - b.price_total; },
      pp: function (a, b) { return a.price_total - b.price_total; }, // same party for every offer
      discount: function (a, b) { return discPct(b) - discPct(a) || a.price_total - b.price_total; },
      date: function (a, b) { return a.date_from < b.date_from ? -1 : a.date_from > b.date_from ? 1 : a.price_total - b.price_total; },
      rating: function (a, b) { return nullLast(b.rating) - nullLast(a.rating) || a.price_total - b.price_total; },
      drop: function (a, b) {
        var x = a.price_change === null ? Infinity : a.price_change;
        var y = b.price_change === null ? Infinity : b.price_change;
        return x - y || a.price_total - b.price_total;
      }
    }[state.s];
    return list.slice().sort(by);
  }

  // ---------- render: header ----------
  function renderTimes() {
    var now = new Date();
    var gen = data && data.generated_at ? new Date(data.generated_at) : null;
    if (gen && !isNaN(gen)) {
      $("updated").textContent = dtFmt.format(gen);
      $("updated-rel").textContent = relTime(gen, now);
      $("updated").setAttribute("title", gen.toISOString());
    } else {
      $("updated").textContent = "zatiaľ nikdy";
      $("updated-rel").textContent = "čaká sa na prvé spustenie";
    }
    var nr = nextRun(now);
    if (nr) {
      $("next-run").textContent = dtFmt.format(nr);
      $("next-run-rel").textContent = relTime(nr, now);
    }
  }
  function renderCriteria() {
    var ul = $("criteria");
    clear(ul);
    function chip(text, title) { var li = el("li", "chip-c", text); if (title) li.title = title; ul.appendChild(li); }
    if (CFG.adults !== null) chip("👨‍👧‍👦 " + partyLong(), "Ceny sú stiahnuté pre túto skupinu");
    if (CFG.critNights) chip("🌙 " + CFG.critNights[0] + "–" + CFG.critNights[1] + " " + nightsWord(CFG.critNights[1]));
    if (CFG.critDates) chip("📅 " + shortDay(CFG.critDates[0]) + " – " + shortDay(CFG.critDates[1], true), "Termín odchodu");
    chip("💶 budget " + eur(CFG.budget), "Ponuky do " + eur(CFG.cap) + " sa sťahujú, nad budget sú označené");
    if (CFG.raw.boards_preferred) chip("🍹 " + CFG.boardsPref.join(" / "), "Preferovaná strava");
    if (CFG.departures.length) chip("✈️ " + CFG.departures.join(", "), "Odletové letiská");
    if (CFG.dogs) chip("🐕 " + CFG.dogs + " " + plural(CFG.dogs, "pes", "psy", "psov") + " (autom)");

    var dn = dogsText();
    $("t-car-note").textContent = dn ? "(" + dn + ")" : "(vlastná doprava)";
    $("t-flight-note").textContent = dn ? "(bez psov)" : "";
    $("foot-party").textContent = partyLong();
    if (CFG.transports.length) {
      ["flight", "car"].forEach(function (t) {
        var has = CFG.transports.indexOf(t) >= 0 || allOffers.some(function (o) { return o.transport === t; });
        [].forEach.call(document.querySelectorAll('[data-transport="' + t + '"]'), function (b) { b.hidden = !has; });
      });
    }
  }

  // ---------- render: party panel ----------
  function renderParty() {
    var box = $("party-people");
    clear(box);
    if (CFG.adults === null) {
      box.appendChild(el("span", "muted", "Dáta neobsahujú zloženie skupiny."));
    } else {
      for (var i = 0; i < Math.min(CFG.adults, 8); i++) box.appendChild(el("span", "person", "👤 dospelý"));
      CFG.kids.forEach(function (a) { box.appendChild(el("span", "person kid", "🧒 " + a + " r.")); });
      if (CFG.adults > 8) box.appendChild(el("span", "person", "… spolu " + CFG.adults + " dospelých"));
    }
    $("party-text").textContent = partyLong() + (CFG.persons ? " · spolu " + CFG.persons + " " + plural(CFG.persons, "osoba", "osoby", "osôb") : "");
    var ex = allOffers.filter(function (o) { return o.price_exact; }).length;
    $("party-exact").textContent = allOffers.length
      ? ex + " z " + allOffers.length + " " + offersWord(allOffers.length) + " má presnú cenu, ktorú cestovka vypočítala priamo pre túto skupinu. Ostatné ceny sú orientačné (prepočet z ceny za osobu) – pri takej ponuke je poznámka „≈ orientačne“."
      : "Ponuky zatiaľ nie sú stiahnuté.";
    var a = $("party-edit");
    a.href = SETTINGS_URL;
    var dis = !CFG.persons;
    [].forEach.call(document.querySelectorAll("[data-view]"), function (b) {
      b.disabled = dis && b.getAttribute("data-view") === "pp";
    });
  }
  function syncView() {
    [].forEach.call(document.querySelectorAll("[data-view]"), function (b) {
      var on = (b.getAttribute("data-view") === "pp") === perPerson();
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  // ---------- render: filter controls ----------
  function chipBtn(label, pressed, onClick, count, key) {
    var b = el("button", "chip");
    b.type = "button";
    b.appendChild(document.createTextNode(label));
    if (count !== undefined && count !== null) { b.appendChild(document.createTextNode(" ")); b.appendChild(el("span", "cnt", count)); }
    b.setAttribute("aria-pressed", pressed ? "true" : "false");
    if (count === 0 && !pressed) b.classList.add("zero");
    if (key) b.setAttribute("data-key", key);
    b.addEventListener("click", onClick);
    return b;
  }
  // re-render a chip box while keeping keyboard focus on the same chip
  function withFocus(box, fn) {
    var a = document.activeElement;
    var key = a && box.contains(a) ? a.getAttribute("data-key") : null;
    clear(box);
    fn();
    if (key) {
      var n = box.querySelector('[data-key="' + key.replace(/["\\]/g, "\\$&") + '"]');
      if (n) n.focus();
    }
  }
  function toggle(arr, v) { var i = arr.indexOf(v); if (i >= 0) arr.splice(i, 1); else arr.push(v); }

  function renderTransport() {
    [].forEach.call(document.querySelectorAll("[data-transport]"), function (b) {
      var on = b.getAttribute("data-transport") === state.t;
      if (b.getAttribute("role") === "radio") { b.setAttribute("aria-checked", on ? "true" : "false"); b.tabIndex = on ? 0 : -1; }
      else b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  function renderGeo() {
    var cc = facetCounts("geo", function (o) { return o.continent; });
    var present = {};
    allOffers.forEach(function (o) { present[o.continent] = 1; });
    var box = $("f-continents");
    withFocus(box, function () {
      box.appendChild(chipBtn("Všetky", !state.ct.length, function () { state.ct = []; update(); }, null, "*"));
      CONTINENTS.forEach(function (k) {
        if (!present[k] && state.ct.indexOf(k) < 0) return;
        box.appendChild(chipBtn(CONT_ICON[k] + " " + k, state.ct.indexOf(k) >= 0, function () {
          toggle(state.ct, k);
          if (state.ct.length) {
            // drop selected countries that are no longer in a selected continent
            state.c = state.c.filter(function (c) { return state.ct.indexOf(countryCont[c] || "Európa") >= 0; });
          }
          update();
        }, cc[k] || 0, k));
      });
    });

    var counts = facetCounts("geo", function (o) { return o.country; });
    var box2 = $("f-countries");
    withFocus(box2, function () {
      var top = el("div", "chips");
      top.appendChild(chipBtn("Všetky krajiny", !state.c.length, function () { state.c = []; update(); }, null, "*"));
      box2.appendChild(top);
      CONTINENTS.forEach(function (k) {
        if (state.ct.length && state.ct.indexOf(k) < 0) return;
        var names = Object.keys(countryCont).filter(function (n) { return countryCont[n] === k; });
        state.c.forEach(function (n) { if (!countryCont[n] && k === "Európa" && names.indexOf(n) < 0) names.push(n); });
        if (!names.length) return;
        names.sort(function (a, b) { return a.localeCompare(b, "sk"); });
        var g = el("div", "c-group");
        g.appendChild(el("div", "c-group-title", CONT_ICON[k] + " " + k));
        var row = el("div", "chips");
        names.forEach(function (name) {
          row.appendChild(chipBtn((countryCode[name] ? flag(countryCode[name]) + " " : "") + name, state.c.indexOf(name) >= 0,
            function () { toggle(state.c, name); update(); }, counts[name] || 0, "c:" + name));
        });
        g.appendChild(row);
        box2.appendChild(g);
      });
    });
  }
  function renderMulti(boxId, facet, values, labelFn, titleFn) {
    var counts = facetCounts(facet, function (o) {
      return facet === "b" ? o.board : facet === "d" ? (o.transport === "flight" ? o.departure : null) : o.source;
    });
    var box = $(boxId);
    withFocus(box, function () {
      box.appendChild(chipBtn("Všetky", !state[facet].length, function () { state[facet] = []; update(); }, null, "*"));
      values.forEach(function (v) {
        var b = chipBtn(labelFn(v), state[facet].indexOf(v) >= 0, function () { toggle(state[facet], v); update(); }, counts[v] || 0, v);
        if (titleFn) b.title = titleFn(v);
        box.appendChild(b);
      });
    });
  }
  var countryCont = {}, countryCode = {}, depList = [], srcList = [], srcName = {};
  function indexData() {
    var deps = {};
    CFG.departures.forEach(function (d) { deps[d] = 1; });
    allOffers.forEach(function (o) {
      if (!countryCont[o.country]) countryCont[o.country] = o.continent;
      if (o.country_code && !countryCode[o.country]) countryCode[o.country] = o.country_code;
      if (o.departure && o.transport === "flight") deps[o.departure] = 1;
      if (!srcName[o.source]) { srcName[o.source] = o.source_name; srcList.push(o.source); }
    });
    depList = Object.keys(deps).sort();
    srcList.sort(function (a, b) { return srcName[a].localeCompare(srcName[b], "sk"); });
  }

  function initControls() {
    var nmin = $("f-nmin"), nmax = $("f-nmax");
    for (var n = CFG.nLo; n <= CFG.nHi; n++) {
      nmin.appendChild(new Option(n + " " + nightsWord(n), n));
      nmax.appendChild(new Option(n + " " + nightsWord(n), n));
    }
    STAR_OPTS.forEach(function (v) { $("f-stars").appendChild(new Option(v ? "aspoň " + decimal(v) + " ★" : "Ľubovoľne", v)); });
    RATING_OPTS.forEach(function (v) { $("f-rating").appendChild(new Option(v ? "aspoň " + decimal(v) + " / 10" : "Ľubovoľne", v)); });
    Object.keys(SORTS).forEach(function (k) { $("f-sort").appendChild(new Option(SORTS[k], k)); });
    ["f-pmin", "f-pmax"].forEach(function (id) {
      var r = $(id);
      r.min = 0; r.max = CFG.priceMax; r.step = 50;
    });
    ["f-df", "f-dt"].forEach(function (id) {
      if (CFG.dMin) $(id).min = CFG.dMin;
      if (CFG.dMax) $(id).max = CFG.dMax;
    });

    document.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-transport]");
      if (b) { state.t = b.getAttribute("data-transport"); update(); return; }
      var v = e.target.closest && e.target.closest("[data-view]");
      if (v && !v.disabled) { state.pp = v.getAttribute("data-view") === "pp"; update(); }
    });
    $("transport").addEventListener("keydown", function (e) {
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].indexOf(e.key) < 0) return;
      var btns = [].slice.call(this.querySelectorAll("button:not([hidden])"));
      var i = btns.indexOf(document.activeElement);
      if (i < 0) return;
      e.preventDefault();
      var j = (i + (e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1) + btns.length) % btns.length;
      state.t = btns[j].getAttribute("data-transport");
      update();
      btns[j].focus();
    });
    $("f-pmin").addEventListener("input", function () { state.pmin = +this.value; if (state.pmax < state.pmin) state.pmax = state.pmin; update(); });
    $("f-pmax").addEventListener("input", function () { state.pmax = +this.value; if (state.pmin > state.pmax) state.pmin = state.pmax; update(); });
    $("f-df").addEventListener("change", function () {
      state.df = isDay(this.value) ? this.value : "";
      if (state.df && state.dt && state.dt < state.df) state.dt = state.df;
      update();
    });
    $("f-dt").addEventListener("change", function () {
      state.dt = isDay(this.value) ? this.value : "";
      if (state.df && state.dt && state.df > state.dt) state.df = state.dt;
      update();
    });
    nmin.addEventListener("change", function () { state.nmin = +this.value; if (state.nmax < state.nmin) state.nmax = state.nmin; update(); });
    nmax.addEventListener("change", function () { state.nmax = +this.value; if (state.nmin > state.nmax) state.nmin = state.nmax; update(); });
    $("f-stars").addEventListener("change", function () { state.st = +this.value; update(); });
    $("f-rating").addEventListener("change", function () { state.r = +this.value; update(); });
    $("f-sort").addEventListener("change", function () { state.s = this.value; update(); });
    [["f-ex", "ex"], ["f-disc", "z"], ["f-dog", "dog"], ["f-drop", "dr"]].forEach(function (p) {
      $(p[0]).addEventListener("change", function () { state[p[1]] = this.checked; update(); });
    });
    $("f-watch").addEventListener("change", function () { setWatchOnly(this.checked); });
    $("watch-filter").addEventListener("click", function () {
      setWatchOnly(true);
      var t = $("ponuky");
      if (t.scrollIntoView) t.scrollIntoView({ block: "start" });
      t.focus({ preventScroll: true });
    });
    var qt = null;
    $("f-q").addEventListener("input", function () {
      var v = this.value;
      clearTimeout(qt);
      qt = setTimeout(function () { state.q = v.slice(0, 80); update(); }, 160);
    });
    $("f-reset").addEventListener("click", clearAll);
    $("f-defaults").addEventListener("click", restoreDefaults);
    window.addEventListener("hashchange", function () {
      var s = hashToState(location.hash);
      if (s && stateToHash(s) !== stateToHash(state)) { state = s; update(true); }
    });
  }
  // "only watched": watched hotels are kept above price_cap and in any board, so turning it on also lifts
  // the default price/board filters that would hide them (each can be set again afterwards)
  function setWatchOnly(on) {
    state.w = on;
    if (on) {
      if (state.pmax === DEFAULTS.pmax) state.pmax = CFG.priceMax;
      if (sameArr(state.b, DEFAULTS.b)) state.b = [];
    }
    update();
  }
  function clearAll() {
    var keep = { s: state.s, pp: state.pp };
    state = clone(OPEN);
    state.s = keep.s; state.pp = keep.pp;
    update();
  }
  function restoreDefaults() {
    var keep = { s: state.s, pp: state.pp };
    state = clone(DEFAULTS);
    state.s = keep.s; state.pp = keep.pp;
    update();
  }
  function setVal(id, v) { var n = $(id); if (String(n.value) !== String(v)) n.value = v; }
  function syncControls() {
    setVal("f-pmin", state.pmin);
    setVal("f-pmax", state.pmax);
    $("f-pmin-out").textContent = eur(state.pmin);
    $("f-pmax-out").textContent = state.pmax >= CFG.priceMax ? "bez limitu" : eur(state.pmax);
    var pct = function (v) { return (v / CFG.priceMax * 100).toFixed(2) + "%"; };
    var track = $("price-track");
    track.style.setProperty("--lo", pct(state.pmin));
    track.style.setProperty("--hi", pct(state.pmax));
    track.style.setProperty("--bud", pct(Math.min(CFG.budget, CFG.priceMax)));
    $("f-price-pp").textContent = CFG.persons
      ? "≈ " + eur(state.pmin / CFG.persons) + " – " + (state.pmax >= CFG.priceMax ? "∞" : eur(state.pmax / CFG.persons)) + " na osobu · budget " + eur(CFG.budget)
      : "budget " + eur(CFG.budget);
    setVal("f-df", state.df);
    setVal("f-dt", state.dt);
    setVal("f-nmin", state.nmin);
    setVal("f-nmax", state.nmax);
    setVal("f-stars", state.st);
    setVal("f-rating", state.r);
    setVal("f-sort", state.s);
    if (document.activeElement !== $("f-q")) setVal("f-q", state.q);
    $("f-ex").checked = state.ex;
    $("f-disc").checked = state.z;
    $("f-dog").checked = state.dog;
    $("f-drop").checked = state.dr;
    $("f-watch").checked = state.w;
    $("f-watch-wrap").hidden = !CFG.watched.length && !state.w;
    $("f-ex-label").textContent = "Len presné ceny pre našu skupinu" + (partyShort() ? " (" + partyShort() + ")" : "");
  }

  // ---------- active filter pills ----------
  function activePills() {
    var s = state, out = [];
    function add(label, undo) { out.push({ label: label, undo: undo }); }
    if (s.t !== "all") add(s.t === "car" ? "🚗 Autom" : "✈️ Letecky", function () { s.t = "all"; });
    s.ct.forEach(function (k) { add(CONT_ICON[k] + " " + k, function () { toggle(s.ct, k); }); });
    s.c.forEach(function (k) { add((countryCode[k] ? flag(countryCode[k]) + " " : "") + k, function () { toggle(s.c, k); }); });
    if (s.pmin > 0 || s.pmax < CFG.priceMax) {
      add(s.pmin > 0 && s.pmax < CFG.priceMax ? "Cena " + eur(s.pmin) + " – " + eur(s.pmax)
        : s.pmin > 0 ? "Cena od " + eur(s.pmin) : "Cena do " + eur(s.pmax),
      function () { s.pmin = 0; s.pmax = CFG.priceMax; });
    }
    if (s.df || s.dt) {
      add("Odchod " + (s.df ? "od " + shortDay(s.df) : "") + (s.df && s.dt ? " " : "") + (s.dt ? "do " + shortDay(s.dt) : ""),
        function () { s.df = ""; s.dt = ""; });
    }
    if (s.nmin !== CFG.nLo || s.nmax !== CFG.nHi) add(s.nmin + "–" + s.nmax + " " + nightsWord(s.nmax), function () { s.nmin = CFG.nLo; s.nmax = CFG.nHi; });
    if (s.b.length) add("Strava: " + s.b.join(", "), function () { s.b = []; });
    if (s.st) add("aspoň " + decimal(s.st) + " ★", function () { s.st = 0; });
    if (s.r) add("hodnotenie ≥ " + decimal(s.r), function () { s.r = 0; });
    s.d.forEach(function (k) { add("✈️ z " + k, function () { toggle(s.d, k); }); });
    s.src.forEach(function (k) { add("🏢 " + (srcName[k] || k), function () { toggle(s.src, k); }); });
    if (s.ex) add("len presné ceny", function () { s.ex = false; });
    if (s.z) add("len so zľavou", function () { s.z = false; });
    if (s.dog) add("len so psami", function () { s.dog = false; });
    if (s.dr) add("len zlacnené", function () { s.dr = false; });
    if (s.w) add("⭐ len sledované", function () { s.w = false; });
    if (s.q) add("„" + s.q + "“", function () { s.q = ""; setVal("f-q", ""); });
    return out;
  }
  function renderPills(list) {
    var pills = activePills();
    var box = $("pills");
    clear(box);
    pills.forEach(function (p, i) {
      var b = el("button", "pill");
      b.type = "button";
      b.setAttribute("data-key", "p" + i);
      b.appendChild(el("span", "", p.label));
      b.appendChild(el("span", "pill-x", "✕"));
      b.setAttribute("aria-label", "Zrušiť filter: " + p.label);
      b.addEventListener("click", function () {
        p.undo();
        update();
        var next = $("pills").querySelector(".pill") || $("f-reset");
        if (next && !next.hidden) next.focus();
      });
      box.appendChild(b);
    });
    $("pills-bar").hidden = !allOffers.length;
    $("pills-empty").hidden = !!pills.length;
    $("f-reset").hidden = !pills.length;
    $("f-defaults").hidden = stateToHash(state).replace(/(^|&)(s|pp)=[^&]*/g, "") === "";
    $("filter-count").textContent = pills.length ? "aktívne: " + pills.length : "žiadne";
    $("result-count").textContent = allOffers.length ? list.length + " " + offersWord(list.length) + " z " + allOffers.length : "";
    $("filter-results").textContent = allOffers.length ? "→ " + list.length + " " + offersWord(list.length) : "";
  }

  // ---------- render: KPIs ----------
  function kpi(label, value, sub, cls) {
    var k = el("div", "kpi");
    k.appendChild(el("div", "kpi-label", label));
    k.appendChild(el("div", "kpi-value" + (cls ? " " + cls : ""), value));
    k.appendChild(el("div", "kpi-sub", sub || " "));
    return k;
  }
  function renderKpis(list) {
    var box = $("kpis");
    clear(box);
    var cheapest = null, drop = null, aiSum = 0, aiN = 0;
    list.forEach(function (o) {
      if (!cheapest || o.price_total < cheapest.price_total) cheapest = o;
      if (o.price_change !== null && o.price_change < 0 && (!drop || o.price_change < drop.price_change)) drop = o;
      if (o.board && AI_BOARDS[o.board] && o.price_total <= CFG.budget) { aiSum += o.price_total; aiN++; }
    });
    var ppNote = perPerson() ? " /os." : "";
    box.appendChild(kpi("Počet ponúk", nf.format(list.length), "z " + nf.format(allOffers.length) + " celkom"));
    box.appendChild(kpi("Najlacnejšia ponuka" + ppNote, cheapest ? eur(pv(cheapest.price_total)) : "—",
      cheapest ? flag(cheapest.country_code) + " " + cheapest.hotel : ""));
    box.appendChild(kpi("Najväčší pokles ceny" + ppNote, drop ? signedEur(pv(drop.price_change)) : "—",
      drop ? drop.hotel : "od posledného behu bez poklesu", drop ? "good" : ""));
    box.appendChild(kpi("Priemer AI v budgete" + ppNote, aiN ? eur(pv(aiSum / aiN)) : "—",
      aiN ? aiN + " " + offersWord(aiN) + " AI/UAI do " + eur(CFG.budget) : "žiadna AI ponuka do " + eur(CFG.budget)));
  }

  // ---------- render: cheapest per country (respects continent, ignores country) ----------
  function renderCheapStrip() {
    var box = $("cheap-strip");
    clear(box);
    var best = {};
    allOffers.forEach(function (o) {
      if (!matches(o, "c")) return;
      if (!best[o.country] || o.price_total < best[o.country].price_total) best[o.country] = o;
    });
    var arr = Object.keys(best).map(function (k) { return best[k]; }).sort(function (a, b) { return a.price_total - b.price_total; });
    $("cheap-block").hidden = !allOffers.length;
    $("cheap-sub").textContent = perPerson() ? "cena za osobu" : "cena spolu za " + (partyShort() || "skupinu");
    if (!arr.length) { box.appendChild(el("p", "muted", "Pri aktuálnych filtroch nič.")); return; }
    arr.forEach(function (o) {
      var b = el("button", "strip-item");
      b.type = "button";
      var only = state.c.length === 1 && state.c[0] === o.country;
      b.setAttribute("aria-pressed", only ? "true" : "false");
      b.setAttribute("aria-label", o.country + ": najlacnejšie " + priceText(o.price_total) + ", " + o.hotel + ". Filtrovať túto krajinu.");
      b.appendChild(el("div", "strip-country", flag(o.country_code) + " " + o.country));
      b.appendChild(el("div", "strip-price", priceText(o.price_total)));
      b.appendChild(el("div", "strip-meta", (o.nights ? o.nights + " " + nightsWord(o.nights) + " · " : "") + (o.board || "?") + " · " + (o.transport === "car" ? "🚗" : "✈️ " + (o.departure || ""))));
      b.addEventListener("click", function () { state.c = only ? [] : [o.country]; update(); });
      box.appendChild(b);
    });
  }

  // ---------- render: watched hotels (ignores the filters: the user always wants to see these) ----------
  var BOARD_SHORT = { UAI: "Ultra AI", AI: "All Inclusive", FB: "plná penzia", HB: "polpenzia", BB: "raňajky", RO: "bez stravy" };
  function watchLinks(term) {
    var out = [], seen = {};
    var w = Array.isArray(data.watched) ? data.watched.filter(function (x) { return x && x.term === term; })[0] : null;
    var own = w && Array.isArray(w.links) ? w.links : [];
    var generic = (Array.isArray(data.deeplinks) ? data.deeplinks : []).filter(function (d) { return d && d.transport !== "car"; });
    own.concat(generic).forEach(function (d) {
      var u = d && safeUrl(d.url);
      var src = str(d && (d.source || d.name));
      if (!u || out.length >= 4 || (seen[src] && own.indexOf(d) < 0)) return;
      seen[src] = 1;
      out.push({ url: u, name: str(d.name || d.source), label: str(d.label) });
    });
    return out;
  }
  function watchRow(o, more) {
    var li = el("li", "watch-row");
    var name = el("div", "watch-hotel", flag(o.country_code) + " " + o.hotel);
    li.appendChild(name);
    var place = [o.place, o.region].filter(Boolean).filter(function (v, i, a) { return a.indexOf(v) === i; }).join(", ");
    li.appendChild(el("div", "watch-meta", (place ? place + ", " : "") + o.country + " · " + o.source_name));
    var when = shortDay(o.date_from) + (o.date_to ? " – " + shortDay(o.date_to, true) : "") +
      (o.nights ? " · " + o.nights + " " + nightsWord(o.nights) : "") +
      " · " + (o.board ? BOARD_SHORT[o.board] || o.board : "strava ?") +
      " · " + (o.transport === "car" ? "🚗 autom" : "✈️ " + (o.departure || "let"));
    li.appendChild(el("div", "watch-meta mono", when));
    var tags = el("div", "watch-tags");
    if (o.price_exact) {
      var ex = el("span", "exact-badge", "✓ presná" + (partyShort() ? " " + partyShort() : ""));
      ex.title = "Cestovka vypočítala cenu priamo pre " + partyLong();
      tags.appendChild(ex);
    } else {
      var ap = el("span", "approx-badge", "≈ orientačne");
      ap.title = o.price_note || "Prepočítané z ceny za osobu – overte pred rezerváciou";
      tags.appendChild(ap);
    }
    if (o.price_total > CFG.cap) {
      var cb = el("span", "cap-badge", "nad strop");
      cb.title = "Drahšie ako strop " + eur(CFG.cap) + " z nastavení – zobrazené len preto, že hotel sledujete";
      tags.appendChild(cb);
    } else if (o.price_total > CFG.budget) tags.appendChild(el("span", "tag", "nad budget"));
    if (more) tags.appendChild(el("span", "tag", "+" + more + " " + plural(more, "ďalší termín", "ďalšie termíny", "ďalších termínov")));
    li.appendChild(tags);
    var pr = el("div", "watch-price");
    pr.appendChild(el("div", "price-total mono", priceText(o.price_total)));
    if (o.url) {
      var a = el("a", "btn", "Ponuka ↗");
      a.href = o.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      a.setAttribute("aria-label", "Zobraziť ponuku " + o.hotel + " na " + o.source_name + " (nové okno)");
      pr.appendChild(a);
    }
    li.appendChild(pr);
    return li;
  }
  function renderWatch() {
    var box = $("watch-list");
    clear(box);
    $("watch-block").hidden = !CFG.watched.length;
    if (!CFG.watched.length) return;
    $("watch-sub").textContent = "najlacnejšia ponuka každého hotela v každej cestovke · " +
      (perPerson() ? "cena za osobu" : "cena spolu za " + (partyShort() || "skupinu"));
    var any = false;
    CFG.watched.forEach(function (term) {
      var groups = {};
      allOffers.forEach(function (o) {
        if (o.watched !== term) return;
        var k = fold(o.hotel) + "|" + o.source;
        var g = groups[k] || (groups[k] = { best: o, n: 0 });
        g.n++;
        if (o.price_total < g.best.price_total) g.best = o;
      });
      var rows = Object.keys(groups).map(function (k) { return groups[k]; })
        .sort(function (a, b) { return a.best.price_total - b.best.price_total; });
      var card = el("article", "watch-term");
      var h = el("h3", "", "⭐ " + term);
      var hotels = {};
      rows.forEach(function (g) { hotels[fold(g.best.hotel)] = 1; });
      var nh = Object.keys(hotels).length, no = rows.reduce(function (s, g) { return s + g.n; }, 0);
      h.appendChild(el("span", "muted", rows.length
        ? nh + " " + plural(nh, "hotel", "hotely", "hotelov") + " · " + no + " " + offersWord(no) + " · od " + priceText(rows[0].best.price_total)
        : "zatiaľ bez ponuky"));
      card.appendChild(h);
      if (rows.length) {
        any = true;
        var ul = el("ul", "watch-rows");
        rows.slice(0, 8).forEach(function (g) { ul.appendChild(watchRow(g.best, g.n - 1)); });
        card.appendChild(ul);
        if (rows.length > 8) card.appendChild(el("p", "muted watch-how", "…a ďalšie v zozname ponúk (filter ⭐ len sledované)."));
      } else {
        card.appendChild(el("p", "watch-empty", "Žiadna cestovka ho teraz pre vaše termíny nepredáva – hľadajte priamo:"));
        var links = watchLinks(term);
        var dl = el("ul", "deep-list");
        links.forEach(function (d) {
          var li = el("li"), a = el("a");
          a.href = d.url; a.target = "_blank"; a.rel = "noopener noreferrer";
          a.appendChild(el("span", "deep-name", d.name));
          var r = el("span", "deep-label", d.label);
          r.appendChild(el("span", "deep-arrow", " ↗"));
          a.appendChild(r);
          a.setAttribute("aria-label", d.name + ": " + d.label + " (nové okno)");
          li.appendChild(a);
          dl.appendChild(li);
        });
        if (links.length) card.appendChild(dl);
      }
      box.appendChild(card);
    });
    $("watch-filter").hidden = !any;
  }

  // ---------- render: offers ----------
  function sparkline(hist) {
    if (hist.length < 2) return null;
    var W = 84, H = 26, P = 2;
    var vals = hist.map(function (p) { return p[1]; });
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    var span = max - min || 1;
    var pts = vals.map(function (v, i) {
      var x = P + (i * (W - 2 * P)) / (vals.length - 1);
      var y = P + (H - 2 * P) * (1 - (v - min) / span);
      return x.toFixed(1) + "," + y.toFixed(1);
    });
    var NS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "spark");
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("role", "img");
    var first = vals[0], last = vals[vals.length - 1];
    svg.setAttribute("aria-label", "Vývoj ceny: " + hist.length + " meraní, od " + eur(first) + " po " + eur(last) + ", min " + eur(min) + ", max " + eur(max));
    var color = last < first ? "var(--good)" : last > first ? "var(--bad)" : "var(--muted)";
    var line = document.createElementNS(NS, "polyline");
    line.setAttribute("points", pts.join(" "));
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", color);
    line.setAttribute("stroke-width", "1.8");
    line.setAttribute("stroke-linejoin", "round");
    line.setAttribute("stroke-linecap", "round");
    svg.appendChild(line);
    var lp = pts[pts.length - 1].split(",");
    var dot = document.createElementNS(NS, "circle");
    dot.setAttribute("cx", lp[0]); dot.setAttribute("cy", lp[1]); dot.setAttribute("r", "2.6");
    dot.setAttribute("fill", color);
    svg.appendChild(dot);
    return svg;
  }
  function tag(cls, text, title) {
    var t = el("span", "tag " + cls, text);
    if (title) t.title = title;
    return t;
  }
  function renderOffer(o, tpl) {
    var node = tpl.content.firstElementChild.cloneNode(true);
    var over = o.price_total > CFG.budget;
    if (over) node.classList.add("over");

    var hue = 0;
    for (var hi = 0; hi < o.country.length; hi++) hue = (hue * 31 + o.country.charCodeAt(hi)) % 360;
    node.querySelector(".offer-media").style.setProperty("--hue", hue);
    var img = node.querySelector("img");
    if (o.image) {
      img.addEventListener("error", function () { img.classList.add("broken"); img.removeAttribute("src"); }, { once: true });
      img.referrerPolicy = "no-referrer";
      img.src = o.image;
      img.alt = "Foto: " + o.hotel;
    } else {
      img.classList.add("broken");
    }

    node.querySelector(".offer-hotel").textContent = o.hotel;
    if (o.watched) {
      node.classList.add("watched");
      var wm = node.querySelector(".watch-mark");
      wm.hidden = false;
      wm.title = "Sledovaný hotel (" + o.watched + ")";
      wm.setAttribute("role", "img");
      wm.setAttribute("aria-label", "Sledovaný hotel");
    }
    var stars = node.querySelector(".offer-stars");
    if (o.stars) {
      var full = Math.floor(o.stars), half = o.stars - full >= 0.5;
      stars.textContent = "★".repeat(Math.min(full, 6)) + (half ? "½" : "");
      stars.setAttribute("aria-label", decimal(o.stars) + " hviezdičky");
      stars.setAttribute("role", "img");
    }
    var place = [o.place, o.region].filter(Boolean).filter(function (v, i, a) { return a.indexOf(v) === i; }).join(", ");
    node.querySelector(".offer-place").textContent = flag(o.country_code) + " " + (place ? place + " · " : "") + o.country +
      (o.continent !== "Európa" ? " · " + o.continent : "");

    var df = parseDay(o.date_from), dt = parseDay(o.date_to);
    var dates = df ? fmtDay(df, !dt) + (dt ? " → " + fmtDay(dt, true) : "") : "termín neuvedený";
    if (o.nights) dates += " · " + o.nights + " " + nightsWord(o.nights);
    node.querySelector(".offer-dates").textContent = dates;

    var tags = node.querySelector(".offer-tags");
    if (o.board) tags.appendChild(tag("tag-board" + (AI_BOARDS[o.board] ? " ai" : ""), o.board, BOARD_LABEL[o.board] || o.board));
    else tags.appendChild(tag("", "strava ?", "Strava neuvedená"));
    if (o.transport === "flight") tags.appendChild(tag("tag-dep", "✈️ " + (o.departure || "let"), "Odlet"));
    else tags.appendChild(tag("", "🚗 vlastná doprava"));
    if (o.transport === "car") {
      if (o.pets_allowed === true) tags.appendChild(tag("tag-pets-yes", "🐕 psy povolené"));
      else if (o.pets_allowed === false) tags.appendChild(tag("tag-pets-no", "🚫 psy zakázané"));
      else tags.appendChild(tag("tag-pets-unk", "🐕 psy: neznáme", "Overte u ubytovania"));
    }
    if (o.rating) tags.appendChild(tag("", "⭐ " + o.rating.toFixed(1).replace(".", ",") + "/10", "Hodnotenie hostí"));
    if (o.score !== null) tags.appendChild(tag("tag-score", "skóre " + Math.round(o.score), "Skóre zhody s kritériami (0–100)"));

    var orig = node.querySelector(".price-orig");
    if (o.price_original && o.price_original > o.price_total) {
      orig.textContent = eur(pv(o.price_original));
      orig.setAttribute("aria-label", "pôvodne " + eur(pv(o.price_original)));
    } else orig.remove();
    var dp = discPct(o);
    var badge = node.querySelector(".disc-badge");
    if (dp > 0 || o.discount_label) badge.textContent = (dp > 0 ? "−" + dp + " %" : "") + (o.discount_label ? (dp > 0 ? " · " : "") + o.discount_label : "");

    var party = partyLong();
    var total = node.querySelector(".price-total");
    total.textContent = eur(pv(o.price_total));
    var sub = node.querySelector(".price-sub");
    sub.textContent = perPerson() ? "za osobu · spolu " + eur(o.price_total) : "spolu za " + (partyShort() || "skupinu");
    total.setAttribute("title", (o.price_exact ? "Presná cena za " : "Orientačná cena za ") + party + (o.price_note ? " – " + o.price_note : ""));
    if (o.price_exact) {
      var ex = el("span", "exact-badge", "✓ presná cena" + (partyShort() ? " " + partyShort() : ""));
      ex.title = "Cestovka vypočítala cenu priamo pre " + party;
      node.querySelector(".price-row").appendChild(ex);
    } else {
      var note = node.querySelector(".price-note");
      note.textContent = "≈ orientačne" + (o.price_note ? ": " + o.price_note.replace(/^orientačne:?\s*/i, "") : "");
      note.title = o.price_note || ("Cestovka nedáva cenu presne pre " + party + " – prepočítané, overte pred rezerváciou");
    }

    var trend = node.querySelector(".price-trend");
    var pc = o.price_change;
    var tr;
    if (pc !== null && pc < 0) tr = el("span", "trend-down", "▼ " + signedEur(pv(pc)));
    else if (pc !== null && pc > 0) tr = el("span", "trend-up", "▲ " + signedEur(pv(pc)));
    else if (pc === 0) tr = el("span", "trend-flat", "▬ bez zmeny");
    else tr = el("span", "trend-flat", o.first_seen && o.first_seen === o.last_seen ? "🆕 nová" : "");
    if (pc) tr.setAttribute("aria-label", (pc < 0 ? "Zlacnené o " : "Zdražené o ") + eur(Math.abs(pv(pc))) + " od posledného behu");
    trend.appendChild(tr);
    var sp = sparkline(o.price_history);
    if (sp) trend.appendChild(sp);

    if (o.price_total > CFG.cap) node.querySelector(".price-warn").textContent = "⚠ nad strop " + eur(CFG.cap) + " (sledovaný hotel)";
    else if (over) node.querySelector(".price-warn").textContent = "⚠ nad budget o " + eur(o.price_total - CFG.budget);

    var a = node.querySelector(".btn");
    if (o.url) {
      a.href = o.url;
      a.setAttribute("aria-label", "Zobraziť ponuku " + o.hotel + " na " + o.source_name + " (nové okno)");
    } else {
      a.removeAttribute("target");
      a.setAttribute("aria-disabled", "true");
      a.textContent = "Odkaz chýba";
    }
    node.querySelector(".offer-source").textContent = "zdroj: " + o.source_name;
    return node;
  }
  function emptyState(kind) {
    var box = el("div", "empty");
    box.appendChild(el("div", "empty-icon", kind === "nodata" ? "🛫" : "🔍"));
    if (kind === "nodata") {
      box.appendChild(el("h3", "", data && data.generated_at ? "Zatiaľ žiadne ponuky" : "Prvé sťahovanie ešte neprebehlo"));
      box.appendChild(el("p", "", "Scraper beží 2× denne (ráno a večer). Kým sa objavia prvé ponuky, môžete hľadať priamo v cestovkách – odkazy už majú predvyplnené termíny a osoby."));
      var a = el("a", "btn", "Hľadať priamo v cestovkách ↓");
      a.href = "#deeplinks-block";
      box.appendChild(a);
    } else {
      box.appendChild(el("h3", "", "Filtrom nevyhovuje žiadna ponuka"));
      box.appendChild(el("p", "", "Zrušte niektorý z aktívnych filtrov (✕ pri filtri nad zoznamom), zvýšte maximálnu cenu alebo pridajte ďalšie typy stravy."));
      var b = el("button", "btn-ghost", "Zrušiť všetky filtre");
      b.type = "button";
      b.addEventListener("click", clearAll);
      box.appendChild(b);
    }
    return box;
  }
  function renderOffers(list) {
    var box = $("offers");
    clear(box);
    if (!allOffers.length) { box.appendChild(emptyState("nodata")); return; }
    if (!list.length) { box.appendChild(emptyState("filtered")); return; }
    var tpl = $("tpl-offer");
    var frag = document.createDocumentFragment();
    list.slice(0, shown).forEach(function (o) { frag.appendChild(renderOffer(o, tpl)); });
    box.appendChild(frag);
    if (list.length > shown) {
      var more = el("button", "btn-ghost more", "Zobraziť ďalšie (" + (list.length - shown) + ")");
      more.type = "button";
      more.addEventListener("click", function () { shown += PAGE; renderOffers(list); });
      box.appendChild(more);
    }
  }

  // ---------- render: deeplinks + sources ----------
  function renderDeeplinks() {
    var box = $("deeplinks");
    clear(box);
    var links = (data && Array.isArray(data.deeplinks) ? data.deeplinks : []).filter(function (d) { return d && safeUrl(d.url); });
    if (!links.length) { box.appendChild(el("p", "muted", "Odkazy zatiaľ nie sú k dispozícii.")); return; }
    var dn = dogsText();
    var groups = [
      { key: "flight", title: "✈️ Letecky" + (dn ? " (bez psov)" : "") },
      { key: "car", title: "🚗 Autom – vlastná doprava" + (dn ? " (" + dn + ")" : "") },
      { key: "other", title: "Ďalšie" }
    ];
    if (state.t === "car") groups.unshift(groups.splice(1, 1)[0]);
    groups.forEach(function (g) {
      var items = links.filter(function (d) {
        var t = d.transport === "flight" || d.transport === "car" ? d.transport : "other";
        return t === g.key;
      });
      if (!items.length) return;
      var sec = el("div", "deep-group");
      sec.appendChild(el("h3", "", g.title));
      var ul = el("ul", "deep-list");
      items.forEach(function (d) {
        var li = el("li");
        var a = el("a");
        a.href = safeUrl(d.url);
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        var left = el("span");
        left.appendChild(el("span", "deep-name", str(d.name || d.source)));
        a.appendChild(left);
        var right = el("span", "deep-label", str(d.label));
        right.appendChild(el("span", "deep-arrow", " ↗"));
        a.appendChild(right);
        a.setAttribute("aria-label", str(d.name || d.source) + ": " + str(d.label) + " (nové okno)");
        li.appendChild(a);
        ul.appendChild(li);
      });
      sec.appendChild(ul);
      box.appendChild(sec);
    });
  }
  function renderSources() {
    var tb = $("sources");
    clear(tb);
    var src = data && Array.isArray(data.sources) ? data.sources : [];
    if (!src.length) {
      var tr0 = el("tr"), td0 = el("td", "muted", "Zatiaľ bez behu – stav zdrojov sa zobrazí po prvom sťahovaní.");
      td0.colSpan = 5;
      tr0.appendChild(td0);
      tb.appendChild(tr0);
      return;
    }
    src.forEach(function (s) {
      if (!s) return;
      var tr = el("tr");
      var tdN = el("td");
      var home = safeUrl(s.home);
      if (home) {
        var a = el("a", "", str(s.name || s.id));
        a.href = home; a.target = "_blank"; a.rel = "noopener noreferrer";
        tdN.appendChild(a);
      } else tdN.textContent = str(s.name || s.id);
      tr.appendChild(tdN);
      var st = STATUS_LABEL[s.status] ? s.status : "disabled";
      var tdS = el("td");
      tdS.appendChild(el("span", "status st-" + st, (st === "ok" ? "✓ " : st === "error" ? "✕ " : st === "empty" ? "∅ " : "– ") + STATUS_LABEL[st]));
      tr.appendChild(tdS);
      tr.appendChild(el("td", "num", num(s.count) !== null ? num(s.count) : "—"));
      var d = num(s.duration_s);
      tr.appendChild(el("td", "num", d !== null ? d.toFixed(1).replace(".", ",") + " s" : "—"));
      tr.appendChild(el("td", "err col-err", s.error ? str(s.error).slice(0, 240) : ""));
      tb.appendChild(tr);
    });
    tb.parentNode.querySelector("thead th:last-child").classList.add("col-err");
  }

  // ---------- main update ----------
  function update(fromHash) {
    shown = PAGE;
    qWords = fold(state.q).split(/\s+/).filter(Boolean);
    renderTransport();
    renderGeo();
    renderMulti("f-boards", "b", BOARDS, function (v) { return v; }, function (v) { return BOARD_LABEL[v]; });
    renderMulti("f-deps", "d", depList, function (v) { return "✈️ " + v; });
    renderMulti("f-srcs", "src", srcList, function (v) { return srcName[v]; });
    syncControls();
    syncView();
    var list = sortOffers(allOffers.filter(function (o) { return matches(o); }));
    renderPills(list);
    renderKpis(list);
    renderWatch();
    renderCheapStrip();
    renderOffers(list);
    renderDeeplinks();
    if (!fromHash) saveState();
  }

  function start(json) {
    data = json && typeof json === "object" ? json : {};
    allOffers = (Array.isArray(data.offers) ? data.offers : []).map(normOffer).filter(Boolean);
    CFG = buildConfig();
    makeDefaults();
    indexData();
    if (isSample) $("sample-note").hidden = false;
    $("filters-box").hidden = !allOffers.length;
    if (window.matchMedia && window.matchMedia("(max-width: 720px)").matches) $("filters-box").open = false;
    state = loadState();
    initControls();
    renderCriteria();
    renderParty();
    renderTimes();
    renderSources();
    update();
    setInterval(renderTimes, 60000);
  }

  // dovolenka.html (single local file) carries the data inline; site/index.html fetches it.
  var inline = document.getElementById("offers-data");
  if (inline && !isSample) {
    try { start(JSON.parse(inline.textContent)); } catch (e) { start(null); }
    return;
  }

  fetch(DATA_URL, { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(start)
    .catch(function (err) {
      var box = $("load-error");
      box.hidden = false;
      box.textContent = "Nepodarilo sa načítať dáta (" + DATA_URL + "): " + (err && err.message ? err.message : "neznáma chyba");
      if (!CFG) start({ generated_at: null, offers: [], sources: [], deeplinks: [] });
    });
})();
