/* Dovolenka tracker – vanilla JS, no dependencies.
 * Data contract: scraper/run.py writes ./data/offers.json.
 * Everything coming from the data file is treated as untrusted: DOM is built with
 * textContent / setAttribute only and URLs must start with https://.
 */
(function () {
  "use strict";

  var BUDGET = 3000;
  var PRICE_MAX = 4500;
  var TZ = "Europe/Bratislava";
  // Must match the cron in .github/workflows/dovolenka-refresh.yml (UTC); data lands ~15 min later.
  var RUN_UTC = [[4, 17], [16, 17]];
  var STORE_KEY = "dovolenka.filters.v1";
  var PAGE = 40;
  var AI_BOARDS = { AI: 1, UAI: 1 };
  var BOARD_LABEL = { UAI: "Ultra All Inclusive", AI: "All Inclusive", FB: "Plná penzia", HB: "Polpenzia", BB: "Raňajky", RO: "Bez stravy" };
  var STATUS_LABEL = { ok: "ok", error: "chyba", empty: "prázdne", disabled: "vypnuté" };

  var DEFAULTS = { t: "all", c: [], p: BUDGET, ai: true, nmin: 7, nmax: 14, d: "", z: false, s: "score" };

  var params = new URLSearchParams(location.search);
  var isSample = params.get("sample") === "1";
  var DATA_URL = isSample ? "./data/offers.sample.json" : "./data/offers.json";

  var data = null;
  var allOffers = [];
  var state = clone(DEFAULTS);
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

  var nf = new Intl.NumberFormat("sk-SK", { maximumFractionDigits: 0 });
  function eur(v) { v = num(v); return v === null ? "—" : nf.format(Math.round(v)) + " €"; }
  function signedEur(v) { return (v > 0 ? "+" : v < 0 ? "−" : "±") + nf.format(Math.abs(Math.round(v))) + " €"; }

  function nightsWord(n) {
    if (n === 1) return "noc";
    if (n >= 2 && n <= 4) return "noci";
    return "nocí";
  }
  function offersWord(n) {
    if (n === 1) return "ponuka";
    if (n >= 2 && n <= 4) return "ponuky";
    return "ponúk";
  }

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

  // ---------- state persistence ----------
  function sanitizeState(s) {
    var o = clone(DEFAULTS);
    if (!s || typeof s !== "object") return o;
    if (s.t === "flight" || s.t === "car" || s.t === "all") o.t = s.t;
    if (Array.isArray(s.c)) o.c = s.c.filter(function (x) { return typeof x === "string" && x.length <= 40; }).slice(0, 40);
    var p = num(s.p); if (p !== null) o.p = Math.min(PRICE_MAX, Math.max(500, p));
    if (typeof s.ai === "boolean") o.ai = s.ai;
    if (typeof s.z === "boolean") o.z = s.z;
    var a = num(s.nmin), b = num(s.nmax);
    if (a !== null && a >= 7 && a <= 14) o.nmin = a;
    if (b !== null && b >= 7 && b <= 14) o.nmax = b;
    if (o.nmin > o.nmax) { var t = o.nmin; o.nmin = o.nmax; o.nmax = t; }
    if (typeof s.d === "string" && /^[A-Z]{0,4}$/.test(s.d)) o.d = s.d;
    if (["score", "price", "discount", "date", "drop"].indexOf(s.s) >= 0) o.s = s.s;
    return o;
  }
  function stateToHash(s) {
    var h = new URLSearchParams();
    if (s.t !== DEFAULTS.t) h.set("t", s.t);
    if (s.c.length) h.set("c", s.c.join(","));
    if (s.p !== DEFAULTS.p) h.set("p", String(s.p));
    if (s.ai !== DEFAULTS.ai) h.set("ai", s.ai ? "1" : "0");
    if (s.nmin !== DEFAULTS.nmin || s.nmax !== DEFAULTS.nmax) h.set("n", s.nmin + "-" + s.nmax);
    if (s.d) h.set("d", s.d);
    if (s.z) h.set("z", "1");
    if (s.s !== DEFAULTS.s) h.set("s", s.s);
    return h.toString();
  }
  function hashToState(hash) {
    var h = new URLSearchParams(hash.replace(/^#/, ""));
    if (!Array.from(h.keys()).length) return null;
    var s = clone(DEFAULTS);
    if (h.has("t")) s.t = h.get("t");
    if (h.has("c")) s.c = h.get("c").split(",").filter(Boolean);
    if (h.has("p")) s.p = h.get("p");
    if (h.has("ai")) s.ai = h.get("ai") === "1";
    if (h.has("n")) { var n = h.get("n").split("-"); s.nmin = n[0]; s.nmax = n[1]; }
    if (h.has("d")) s.d = h.get("d");
    if (h.has("z")) s.z = h.get("z") === "1";
    if (h.has("s")) s.s = h.get("s");
    return sanitizeState(s);
  }
  function loadState() {
    var fromHash = hashToState(location.hash);
    if (fromHash) return fromHash;
    try {
      var raw = window.localStorage.getItem(STORE_KEY);
      if (raw) return sanitizeState(JSON.parse(raw));
    } catch (e) { /* storage blocked */ }
    return clone(DEFAULTS);
  }
  function saveState() {
    try { window.localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) { /* ignore */ }
    var h = stateToHash(state);
    var url = location.pathname + location.search + (h ? "#" + h : "");
    try { history.replaceState(null, "", url); } catch (e) { /* ignore */ }
  }

  // ---------- normalize data ----------
  function normOffer(o) {
    if (!o || typeof o !== "object") return null;
    var price = num(o.price_total);
    if (price === null) return null;
    var hist = Array.isArray(o.price_history) ? o.price_history.filter(function (p) {
      return Array.isArray(p) && p.length >= 2 && num(p[1]) !== null;
    }).map(function (p) { return [str(p[0]), num(p[1])]; }) : [];
    return {
      id: str(o.id),
      source: str(o.source), source_name: str(o.source_name || o.source),
      hotel: str(o.hotel) || "Bez názvu",
      stars: num(o.stars), rating: num(o.rating),
      country: str(o.country) || "Iné", country_code: str(o.country_code),
      region: str(o.region), place: str(o.place),
      board: o.board ? str(o.board).toUpperCase() : null,
      transport: o.transport === "car" ? "car" : "flight",
      departure: o.departure ? str(o.departure).toUpperCase() : null,
      date_from: str(o.date_from), date_to: str(o.date_to), nights: num(o.nights),
      price_total: price, price_original: num(o.price_original),
      discount_pct: num(o.discount_pct), discount_label: o.discount_label ? str(o.discount_label) : null,
      price_exact: o.price_exact === true,
      pets_allowed: o.pets_allowed === true ? true : o.pets_allowed === false ? false : null,
      image: safeUrl(o.image), url: safeUrl(o.url),
      score: num(o.score),
      first_seen: str(o.first_seen), last_seen: str(o.last_seen),
      price_history: hist,
      price_change: num(o.price_change)
    };
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
  function baseFilter(o, ignoreCountry) {
    if (state.t !== "all" && o.transport !== state.t) return false;
    if (!ignoreCountry && state.c.length && state.c.indexOf(o.country) < 0) return false;
    if (o.price_total > state.p) return false;
    if (state.ai && !(o.board && AI_BOARDS[o.board])) return false;
    if (o.nights !== null && (o.nights < state.nmin || o.nights > state.nmax)) return false;
    if (state.d && o.departure !== state.d) return false;
    if (state.z && !isDiscount(o)) return false;
    return true;
  }
  function sortOffers(list) {
    var by = {
      score: function (a, b) { return (b.score || 0) - (a.score || 0) || a.price_total - b.price_total; },
      price: function (a, b) { return a.price_total - b.price_total; },
      discount: function (a, b) { return discPct(b) - discPct(a) || a.price_total - b.price_total; },
      date: function (a, b) { return a.date_from < b.date_from ? -1 : a.date_from > b.date_from ? 1 : a.price_total - b.price_total; },
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

  // ---------- render: controls ----------
  function renderTransport() {
    [].forEach.call($("transport").querySelectorAll("button"), function (b) {
      b.setAttribute("aria-checked", b.getAttribute("data-transport") === state.t ? "true" : "false");
      b.tabIndex = b.getAttribute("data-transport") === state.t ? 0 : -1;
    });
  }
  function renderCountryChips() {
    var box = $("f-countries");
    clear(box);
    var counts = {}, codes = {};
    allOffers.forEach(function (o) {
      if (state.t !== "all" && o.transport !== state.t) return;
      counts[o.country] = (counts[o.country] || 0) + 1;
      codes[o.country] = o.country_code;
    });
    // keep selected countries visible even if not present in current transport
    state.c.forEach(function (c) { if (!(c in counts)) counts[c] = 0; });
    var names = Object.keys(counts).sort(function (a, b) { return a.localeCompare(b, "sk"); });
    var all = el("button", "chip", "Všetky krajiny");
    all.type = "button";
    all.setAttribute("aria-pressed", state.c.length ? "false" : "true");
    all.addEventListener("click", function () { state.c = []; update(); });
    box.appendChild(all);
    names.forEach(function (name) {
      var b = el("button", "chip");
      b.type = "button";
      b.appendChild(document.createTextNode((codes[name] ? flag(codes[name]) + " " : "") + name + " "));
      b.appendChild(el("span", "cnt", counts[name]));
      b.setAttribute("aria-pressed", state.c.indexOf(name) >= 0 ? "true" : "false");
      b.addEventListener("click", function () {
        var i = state.c.indexOf(name);
        if (i >= 0) state.c.splice(i, 1); else state.c.push(name);
        update();
      });
      box.appendChild(b);
    });
  }
  function initControls() {
    var nmin = $("f-nmin"), nmax = $("f-nmax");
    for (var n = 7; n <= 14; n++) {
      nmin.appendChild(new Option(n + " " + nightsWord(n), n));
      nmax.appendChild(new Option(n + " " + nightsWord(n), n));
    }
    var deps = {};
    allOffers.forEach(function (o) { if (o.departure) deps[o.departure] = 1; });
    Object.keys(deps).sort().forEach(function (d) { $("f-dep").appendChild(new Option(d, d)); });

    $("transport").addEventListener("click", function (e) {
      var b = e.target.closest("button[data-transport]");
      if (!b) return;
      state.t = b.getAttribute("data-transport");
      update();
    });
    $("transport").addEventListener("keydown", function (e) {
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].indexOf(e.key) < 0) return;
      var btns = [].slice.call(this.querySelectorAll("button"));
      var i = btns.indexOf(document.activeElement);
      if (i < 0) return;
      e.preventDefault();
      var j = (i + (e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1) + btns.length) % btns.length;
      state.t = btns[j].getAttribute("data-transport");
      update();
      btns[j].focus();
    });
    $("f-price").addEventListener("input", function () { state.p = +this.value; update(); });
    $("f-ai").addEventListener("change", function () { state.ai = this.checked; update(); });
    $("f-disc").addEventListener("change", function () { state.z = this.checked; update(); });
    nmin.addEventListener("change", function () { state.nmin = +this.value; if (state.nmax < state.nmin) state.nmax = state.nmin; update(); });
    nmax.addEventListener("change", function () { state.nmax = +this.value; if (state.nmin > state.nmax) state.nmin = state.nmax; update(); });
    $("f-dep").addEventListener("change", function () { state.d = this.value; update(); });
    $("f-sort").addEventListener("change", function () { state.s = this.value; update(); });
    $("f-reset").addEventListener("click", resetFilters);
    window.addEventListener("hashchange", function () {
      var s = hashToState(location.hash);
      if (s && stateToHash(s) !== stateToHash(state)) { state = s; update(true); }
    });
  }
  function resetFilters() {
    var t = state.t;
    state = clone(DEFAULTS);
    state.t = t;
    update();
  }
  function syncControls() {
    $("f-price").value = state.p;
    $("f-price-out").textContent = eur(state.p);
    $("f-ai").checked = state.ai;
    $("f-disc").checked = state.z;
    $("f-nmin").value = state.nmin;
    $("f-nmax").value = state.nmax;
    var dep = $("f-dep");
    if (state.d && !dep.querySelector('option[value="' + state.d + '"]')) dep.appendChild(new Option(state.d, state.d));
    dep.value = state.d;
    $("f-sort").value = state.s;
    var active = 0;
    if (state.c.length) active++;
    if (state.p !== DEFAULTS.p) active++;
    if (state.ai !== DEFAULTS.ai) active++;
    if (state.nmin !== 7 || state.nmax !== 14) active++;
    if (state.d) active++;
    if (state.z) active++;
    $("filter-count").textContent = active ? "aktívne zmeny: " + active : "";
  }

  // ---------- render: KPIs ----------
  function kpi(label, value, sub, cls) {
    var k = el("div", "kpi");
    k.appendChild(el("div", "kpi-label", label));
    k.appendChild(el("div", "kpi-value" + (cls ? " " + cls : ""), value));
    k.appendChild(el("div", "kpi-sub", sub || " "));
    return k;
  }
  function renderKpis(list) {
    var box = $("kpis");
    clear(box);
    var cheapest = null, drop = null, aiSum = 0, aiN = 0;
    list.forEach(function (o) {
      if (!cheapest || o.price_total < cheapest.price_total) cheapest = o;
      if (o.price_change !== null && o.price_change < 0 && (!drop || o.price_change < drop.price_change)) drop = o;
      if (o.board && AI_BOARDS[o.board] && o.price_total <= BUDGET) { aiSum += o.price_total; aiN++; }
    });
    box.appendChild(kpi("Počet ponúk", nf.format(list.length), "z " + nf.format(allOffers.length) + " celkom"));
    box.appendChild(kpi("Najlacnejšia ponuka", cheapest ? eur(cheapest.price_total) : "—",
      cheapest ? flag(cheapest.country_code) + " " + cheapest.hotel : ""));
    box.appendChild(kpi("Najväčší pokles ceny", drop ? signedEur(drop.price_change) : "—",
      drop ? drop.hotel : "od posledného behu bez poklesu", drop ? "good" : ""));
    box.appendChild(kpi("Priemer AI v budgete", aiN ? eur(aiSum / aiN) : "—",
      aiN ? aiN + " " + offersWord(aiN) + " AI/UAI do " + eur(BUDGET) : "žiadna AI ponuka do " + eur(BUDGET)));
  }

  // ---------- render: cheapest per country ----------
  function renderCheapStrip() {
    var box = $("cheap-strip");
    clear(box);
    var best = {};
    allOffers.forEach(function (o) {
      if (!baseFilter(o, true)) return;
      if (!best[o.country] || o.price_total < best[o.country].price_total) best[o.country] = o;
    });
    var arr = Object.keys(best).map(function (k) { return best[k]; }).sort(function (a, b) { return a.price_total - b.price_total; });
    $("cheap-block").hidden = !allOffers.length;
    if (!arr.length) { box.appendChild(el("p", "muted", "Pri aktuálnych filtroch nič.")); return; }
    arr.forEach(function (o) {
      var b = el("button", "strip-item");
      b.type = "button";
      var only = state.c.length === 1 && state.c[0] === o.country;
      b.setAttribute("aria-pressed", only ? "true" : "false");
      b.setAttribute("aria-label", o.country + ": najlacnejšie " + eur(o.price_total) + ", " + o.hotel + ". Filtrovať túto krajinu.");
      b.appendChild(el("div", "strip-country", flag(o.country_code) + " " + o.country));
      b.appendChild(el("div", "strip-price", eur(o.price_total)));
      b.appendChild(el("div", "strip-meta", (o.nights ? o.nights + " " + nightsWord(o.nights) + " · " : "") + (o.board || "?") + " · " + (o.transport === "car" ? "🚗" : "✈️ " + (o.departure || ""))));
      b.addEventListener("click", function () { state.c = only ? [] : [o.country]; update(); });
      box.appendChild(b);
    });
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
    var over = o.price_total > BUDGET;
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
    var stars = node.querySelector(".offer-stars");
    if (o.stars) {
      var full = Math.floor(o.stars), half = o.stars - full >= 0.5;
      stars.textContent = "★".repeat(Math.min(full, 6)) + (half ? "½" : "");
      stars.setAttribute("aria-label", String(o.stars).replace(".", ",") + " hviezdičky");
      stars.setAttribute("role", "img");
    }
    var place = [o.place, o.region].filter(Boolean).filter(function (v, i, a) { return a.indexOf(v) === i; }).join(", ");
    node.querySelector(".offer-place").textContent = flag(o.country_code) + " " + (place ? place + " · " : "") + o.country;

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
      orig.textContent = eur(o.price_original);
      orig.setAttribute("aria-label", "pôvodne " + eur(o.price_original));
    } else orig.remove();
    var dp = discPct(o);
    var badge = node.querySelector(".disc-badge");
    if (dp > 0 || o.discount_label) badge.textContent = (dp > 0 ? "−" + dp + " %" : "") + (o.discount_label ? (dp > 0 ? " · " : "") + o.discount_label : "");

    node.querySelector(".price-total").textContent = eur(o.price_total);
    node.querySelector(".price-total").setAttribute("title", o.price_exact
      ? "Presná cena za 1 dospelého + 2 deti (10 a 12 r.) podľa cestovky"
      : "Cena za 1 dospelého + 2 deti" + (o.source === "satur" || o.source === "cedok" || o.source === "tiptravel"
        ? " – orientačne: cena za osobu pri 2 dospelých × 3" : ""));
    if (o.price_exact) {
      var ex = el("span", "exact-badge", "presná cena 1+2");
      ex.title = "Cestovka vypočítala cenu priamo pre 1 dospelého + 2 deti";
      node.querySelector(".price-row").appendChild(ex);
    }

    var trend = node.querySelector(".price-trend");
    var pc = o.price_change;
    var tr;
    if (pc !== null && pc < 0) tr = el("span", "trend-down", "▼ " + signedEur(pc));
    else if (pc !== null && pc > 0) tr = el("span", "trend-up", "▲ " + signedEur(pc));
    else if (pc === 0) tr = el("span", "trend-flat", "▬ bez zmeny");
    else tr = el("span", "trend-flat", o.first_seen && o.first_seen === o.last_seen ? "🆕 nová" : "");
    if (pc) tr.setAttribute("aria-label", (pc < 0 ? "Zlacnené o " : "Zdražené o ") + eur(Math.abs(pc)) + " od posledného behu");
    trend.appendChild(tr);
    var sp = sparkline(o.price_history);
    if (sp) trend.appendChild(sp);

    if (over) node.querySelector(".price-warn").textContent = "⚠ nad budget o " + eur(o.price_total - BUDGET);

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
      box.appendChild(el("p", "", "Skúste zvýšiť maximálnu cenu, vypnúť filter All Inclusive alebo vybrať iné krajiny."));
      var b = el("button", "btn-ghost", "Zrušiť filtre");
      b.type = "button";
      b.addEventListener("click", resetFilters);
      box.appendChild(b);
    }
    return box;
  }
  function renderOffers(list) {
    var box = $("offers");
    clear(box);
    $("result-count").textContent = allOffers.length ? list.length + " " + offersWord(list.length) : "";
    if (!allOffers.length) { box.appendChild(emptyState("nodata")); return; }
    if (!list.length) { box.appendChild(emptyState("filtered")); return; }
    var tpl = $("tpl-offer");
    var frag = document.createDocumentFragment();
    list.slice(0, shown).forEach(function (o) { frag.appendChild(renderOffer(o, tpl)); });
    box.appendChild(frag);
    if (list.length > shown) {
      var more = el("button", "btn-ghost", "Zobraziť ďalšie (" + (list.length - shown) + ")");
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
    var groups = [
      { key: "flight", title: "✈️ Letecky (bez psov)" },
      { key: "car", title: "🚗 Autom – vlastná doprava (so 2 psami)" },
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
    renderTransport();
    renderCountryChips();
    syncControls();
    var list = sortOffers(allOffers.filter(function (o) { return baseFilter(o, false); }));
    renderKpis(list);
    renderCheapStrip();
    renderOffers(list);
    renderDeeplinks();
    if (!fromHash) saveState();
  }

  function start(json) {
    data = json && typeof json === "object" ? json : {};
    allOffers = (Array.isArray(data.offers) ? data.offers : []).map(normOffer).filter(Boolean);
    if (isSample) $("sample-note").hidden = false;
    $("filters-box").hidden = !allOffers.length;
    if (window.matchMedia && window.matchMedia("(max-width: 720px)").matches) $("filters-box").open = false;
    state = loadState();
    initControls();
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
      start({ generated_at: null, offers: [], sources: [], deeplinks: [] });
    });
})();
