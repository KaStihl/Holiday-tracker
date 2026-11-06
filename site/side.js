/* Tab "🏨 Side – hotely pri pláži" – vanilla JS, no dependencies.
 * Data contract: scraper/side.py writes ./data/side.json (embedded in dovolenka.html as #side-data).
 * Everything from the data file is untrusted: DOM via textContent / setAttribute, URLs must be https://.
 * The tab switch only toggles <main id="main"> (offers, app.js) and <main id="side-main">; it never touches the
 * URL hash (app.js keeps its filters there). The tab is remembered in localStorage and ?tab=side opens it.
 */
(function () {
  "use strict";

  var TAB_KEY = "dovolenka.tab";
  var STORE_KEY = "dovolenka.side.v1";
  var PAGE = 30;
  var CRIT = {
    rodinna_izba: { icon: "🛏️", label: "Rodinná izba (3–4 os.)" },
    aquapark: { icon: "🛝", label: "Aquapark / tobogany" },
    detsky_klub: { icon: "🧸", label: "Detský klub / animácie" },
    all_inclusive: { icon: "🍽️", label: "All Inclusive" }
  };
  var SORTS = { dist: "Vzdialenosť od pláže", crit: "Najviac splnených kritérií", pkg: "Cena zájazdu (od najnižšej)", own: "Vlastný balík (od najnižšieho)" };
  var BOARD = { UAI: "Ultra All Inclusive", AI: "All Inclusive", FB: "Plná penzia", HB: "Polpenzia", BB: "Raňajky", RO: "Bez stravy" };
  var AIRPORT = { VIE: "Viedeň", BTS: "Bratislava", BRQ: "Brno" };

  var params = new URLSearchParams(location.search);
  var isSample = params.get("sample") === "1";
  var D = null;          // side.json
  var S = null;          // UI state
  var shown = PAGE;

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function num(v) { var n = typeof v === "number" ? v : parseFloat(v); return isFinite(n) ? n : null; }
  function str(v) { return v === null || v === undefined ? "" : String(v); }
  function fold(s) { return str(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
  function isDay(s) { return typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s); }
  function safeUrl(u) {
    if (typeof u !== "string" || !/^https:\/\//i.test(u.trim())) return null;
    try { var p = new URL(u.trim()); return p.protocol === "https:" ? p.href : null; } catch (e) { return null; }
  }
  var nf = new Intl.NumberFormat("sk-SK", { maximumFractionDigits: 0 });
  function eur(v) { v = num(v); return v === null ? "—" : nf.format(Math.round(v)) + " €"; }
  function signed(v) { return (v > 0 ? "+" : v < 0 ? "−" : "±") + nf.format(Math.abs(Math.round(v))) + " €"; }
  function plural(n, one, few, many) { return n === 1 ? one : n >= 2 && n <= 4 ? few : many; }
  function day(s) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(str(s)); return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : null; }
  function iso(t) { return new Date(t).toISOString().slice(0, 10); }
  function addDays(s, n) { var t = day(s); return t === null ? "" : iso(t + n * 86400000); }
  function diffDays(a, b) { var x = day(a), y = day(b); return x === null || y === null ? null : Math.round((x - y) / 86400000); }
  function short(s) { var t = day(s); if (t === null) return ""; var d = new Date(t); return d.getUTCDate() + ". " + (d.getUTCMonth() + 1) + "."; }
  function link(href, text, cls) {
    var u = safeUrl(href);
    if (!u) return el("span", cls || "", text);
    var a = el("a", cls || "", text);
    a.href = u; a.target = "_blank"; a.rel = "noopener noreferrer";
    return a;
  }

  // ---------- tabs ----------
  function setTab(tab, focus) {
    var side = tab === "side";
    $("main").hidden = side;
    $("side-main").hidden = !side;
    var oh = $("offers-head"); if (oh) oh.hidden = side;
    ["deeplinks-block", "sources-block"].forEach(function (id) { var n = $(id); if (n && n.parentNode !== $("main")) n.hidden = side; });
    $("tab-offers").setAttribute("aria-selected", side ? "false" : "true");
    $("tab-side").setAttribute("aria-selected", side ? "true" : "false");
    $("tab-offers").tabIndex = side ? -1 : 0;
    $("tab-side").tabIndex = side ? 0 : -1;
    try { localStorage.setItem(TAB_KEY, tab); } catch (e) { /* ignore */ }
    if (focus) $(side ? "tab-side" : "tab-offers").focus();
    if (side && !D) init();
  }
  function initTabs() {
    $("tab-offers").addEventListener("click", function () { setTab("offers"); });
    $("tab-side").addEventListener("click", function () { setTab("side"); });
    $("tabs").addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        setTab($("tab-side").getAttribute("aria-selected") === "true" ? "offers" : "side", true);
      }
    });
    var t = params.get("tab");
    if (t !== "side" && t !== "offers") { try { t = localStorage.getItem(TAB_KEY); } catch (e) { t = null; } }
    setTab(t === "side" ? "side" : "offers");
  }

  // ---------- data ----------
  function parties() { return Array.isArray(D.parties) ? D.parties.filter(function (p) { return p && typeof p.id === "string"; }) : []; }
  function party() { var ps = parties(); return ps.filter(function (p) { return p.id === S.p; })[0] || ps[0] || { id: "", adults: 2, kids: [], persons: 2, nazov: "" }; }
  function stays() { var s = Array.isArray(D.stays) ? D.stays.map(num).filter(function (n) { return n && n > 0 && n < 40; }) : []; return s.length ? s : [7, 10, 14]; }
  function flights() { return D.flights && Array.isArray(D.flights.list) ? D.flights.list.filter(function (f) { return f && isDay(f.dep) && isDay(f.ret) && num(f.p) !== null; }) : []; }
  function srcName(id) { return (D.src && typeof D.src[id] === "string") ? D.src[id] : str(id); }

  function defaultState() {
    var st = stays();
    var s = { p: (parties()[0] || {}).id || "", n: st[0], d: "", dep: "", a: [], c: [], sort: "dist", q: "", of: false, ho: false };
    s.d = cheapestFlightDay(s.n, "") || addDays(D.date_from, 9) || D.date_from || "";
    return s;
  }
  function loadState() {
    var s = defaultState();
    try {
      var raw = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
      if (raw && typeof raw === "object") {
        if (parties().some(function (p) { return p.id === raw.p; })) s.p = raw.p;
        if (stays().indexOf(raw.n) >= 0) s.n = raw.n;
        if (isDay(raw.d) && raw.d >= D.date_from && raw.d <= D.date_to) s.d = raw.d;
        if (["", "VIE", "BTS", "BRQ"].indexOf(raw.dep) >= 0) s.dep = raw.dep;
        if (Array.isArray(raw.a)) s.a = raw.a.filter(function (x) { return (D.areas || []).some(function (a) { return a.id === x; }); });
        if (Array.isArray(raw.c)) s.c = raw.c.filter(function (x) { return CRIT[x]; });
        if (SORTS[raw.sort]) s.sort = raw.sort;
        s.of = raw.of === true; s.ho = raw.ho === true;
      }
    } catch (e) { /* storage blocked */ }
    return s;
  }
  function save() { try { localStorage.setItem(STORE_KEY, JSON.stringify(S)); } catch (e) { /* ignore */ } }

  // ---------- flights ----------
  function cheapestFlightDay(n, dep) {
    var best = null;
    flights().forEach(function (f) { if (f.n === n && (!dep || f.o === dep) && (!best || f.p < best.p)) best = f; });
    return best ? best.dep : null;
  }
  // the flight used for the package: nights = selected and departure within ±3 days of the chosen date (cheapest);
  // else the cheapest of those nights anywhere in the window ("iný termín"); else – the 2027 cache is thin – the
  // cheapest with the nearest stay length (±3 nights, "N nocí"), labelled on the page
  function pickFlight(dep) {
    var near = null, any = null, close = null;
    flights().forEach(function (f) {
      if (dep && f.o !== dep) return;
      var dn = Math.abs(f.n - S.n);
      if (f.n === S.n) {
        var dd = diffDays(f.dep, S.d);
        if (dd !== null && Math.abs(dd) <= 3 && (!near || f.p < near.p)) near = f;
        if (!any || f.p < any.p) any = f;
      } else if (dn <= 3 && (!close || dn < Math.abs(close.n - S.n) || (dn === Math.abs(close.n - S.n) && f.p < close.p))) close = f;
    });
    return near ? { f: near, exact: true, nights: true } : any ? { f: any, exact: false, nights: true } :
      close ? { f: close, exact: false, nights: false } : null;
  }
  // airline passenger types: 12+ = adult, 2–11 child, under 2 infant
  function paxOf(p) {
    var kids = Array.isArray(p.kids) ? p.kids : [];
    return { a: p.adults + kids.filter(function (x) { return x >= 12; }).length, c: kids.filter(function (x) { return x >= 2 && x < 12; }).length, i: kids.filter(function (x) { return x < 2; }).length };
  }
  function ddmm(s) { return s.slice(8, 10) + s.slice(5, 7); }
  function aviasales(f, p) {
    var x = paxOf(p);
    var pax = String(x.a) + (x.c || x.i ? String(x.c) : "") + (x.i ? String(x.i) : "");
    return "https://www.aviasales.com/search/" + f.o + ddmm(f.dep) + str(D.flights.dest || "AYT") + ddmm(f.ret) + pax;
  }
  // Booking redirects a bare searchresults URL to its home page; these extra fields are the ones its own
  // search form sends (sb/src/src_elem), which makes it apply ss + dates + party.
  function booking(h, p) {
    var q = new URLSearchParams();
    q.set("ss", h.n + ", Side, Antalya");
    q.set("checkin", S.d);
    q.set("checkout", addDays(S.d, S.n));
    q.set("group_adults", String(p.adults));
    q.set("group_children", String((p.kids || []).length));
    (p.kids || []).forEach(function (a) { q.append("age", String(a)); });
    q.set("no_rooms", "1");
    q.set("sb", "1");
    q.set("src", "index");
    q.set("src_elem", "sb");
    q.set("lang", "sk");
    q.set("selected_currency", "EUR");
    return "https://www.booking.com/searchresults.html?" + q.toString();
  }
  // Fallback that always lands on the hotel's own Booking page (first Google hit); dates are set there.
  function bookingViaGoogle(h) {
    return "https://www.google.com/search?q=" + encodeURIComponent(h.n + " Side site:booking.com/hotel");
  }

  // ---------- per hotel ----------
  function critOf(h, key, p) {
    var src = [];
    var fac = h.fac && typeof h.fac === "object" ? h.fac : {};
    function add(list) { (Array.isArray(list) ? list : []).forEach(function (s) { if (typeof s === "string" && src.indexOf(s) < 0) src.push(s); }); }
    if (key === "aquapark") { add(fac.aq); if (Array.isArray(h.aqo) && h.aqo.length) src.push("OSM: " + h.aqo.slice(0, 2).join(", ")); }
    else if (key === "detsky_klub") add(fac.kc);
    else if (key === "all_inclusive") add(h.ai);
    else if (key === "rodinna_izba") {
      add(fac.fr);
      var fit = h.fit && Array.isArray(h.fit[p.id]) ? h.fit[p.id] : [];
      if (fit.length && p.persons >= 3) src.push(fit.join(", ") + ": cena pre " + p.persons + " os. v 1 izbe");
    }
    return src;
  }
  function critCount(h, p) { return (D.kriteria || []).filter(function (k) { return critOf(h, k, p).length; }).length; }

  function pickRow(rows, idxDate, idxNights) {
    // rows: arrays; nights = selected; date within ±3 days -> cheapest; else cheapest of those nights; else cheapest at all
    var near = null, same = null, any = null;
    rows.forEach(function (r) {
      var price = num(r[1]); if (price === null) return;
      var dd = diffDays(r[idxDate], S.d);
      if (r[idxNights] === S.n && dd !== null && Math.abs(dd) <= 3 && (!near || price < near[1])) near = r;
      if (r[idxNights] === S.n && (!same || price < same[1])) same = r;
      if (!any || price < any[1]) any = r;
    });
    return near ? { r: near, how: "term" } : same ? { r: same, how: "nights" } : any ? { r: any, how: "other" } : null;
  }
  function agencyFor(h, p) { var rows = h.of && Array.isArray(h.of[p.id]) ? h.of[p.id] : []; return pickRow(rows, 3, 4); }
  function hotelOnlyFor(h, p) { var rows = h.ho && Array.isArray(h.ho[p.id]) ? h.ho[p.id] : []; var x = pickRow(rows, 2, 3); return x && x.how !== "other" ? x : null; }

  function ownPackage(h, p) {
    var fl = pickFlight(S.dep);
    var ho = hotelOnlyFor(h, p);
    var tr = num(D.transfer_eur) || 0;
    var out = { flight: fl, ho: ho, transfer: tr * 2, total: null, partial: null };
    var fsum = fl ? fl.f.p * p.persons : null;
    out.fsum = fsum;
    if (fsum !== null && ho) out.total = fsum + ho.r[1] + tr * 2;
    else if (fsum !== null) out.partial = fsum + tr * 2;
    return out;
  }

  // ---------- render ----------
  function chip(label, pressed, onClick, title) {
    var b = el("button", "chip", label);
    b.type = "button";
    b.setAttribute("aria-pressed", pressed ? "true" : "false");
    if (title) b.title = title;
    b.addEventListener("click", onClick);
    return b;
  }
  function toggle(arr, v) { var i = arr.indexOf(v); if (i >= 0) arr.splice(i, 1); else arr.push(v); }

  function renderControls() {
    var box = $("side-party"); clear(box);
    parties().forEach(function (p) {
      box.appendChild(chip(p.nazov || (p.adults + "+" + (p.kids || []).length), S.p === p.id, function () { S.p = p.id; update(); }, p.persons + " " + plural(p.persons, "osoba", "osoby", "osôb")));
    });
    box = $("side-nights"); clear(box);
    stays().forEach(function (n) {
      box.appendChild(chip(n + " " + plural(n, "noc", "noci", "nocí"), S.n === n, function () { S.n = n; update(); }));
    });
    box = $("side-deps"); clear(box);
    var origins = D.flights && Array.isArray(D.flights.origins) ? D.flights.origins : [];
    box.appendChild(chip("Najlacnejšie", !S.dep, function () { S.dep = ""; update(); }));
    origins.forEach(function (o) { if (AIRPORT[o]) box.appendChild(chip(o + " " + AIRPORT[o], S.dep === o, function () { S.dep = o; update(); })); });
    var di = $("side-date");
    di.min = D.date_from || ""; di.max = D.date_to || "";
    if (di.value !== S.d) di.value = S.d;
    box = $("side-areas"); clear(box);
    box.appendChild(chip("Všetky", !S.a.length, function () { S.a = []; update(); }));
    (D.areas || []).forEach(function (a) {
      var n = (D.hotels || []).filter(function (h) { return h.a === a.id; }).length;
      var c = chip(a.name + " ", S.a.indexOf(a.id) >= 0, function () { toggle(S.a, a.id); update(); });
      c.appendChild(el("span", "cnt", n));
      box.appendChild(c);
    });
    box = $("side-crit"); clear(box);
    var p = party();
    (D.kriteria || []).forEach(function (k) {
      if (!CRIT[k]) return;
      var n = (D.hotels || []).filter(function (h) { return critOf(h, k, p).length; }).length;
      var c = chip(CRIT[k].icon + " " + CRIT[k].label + " ", S.c.indexOf(k) >= 0, function () { toggle(S.c, k); update(); }, "Len hotely, kde to potvrdzuje cestovka alebo OpenStreetMap");
      c.appendChild(el("span", "cnt", n));
      box.appendChild(c);
    });
    var sel = $("side-sort");
    if (!sel.options.length) Object.keys(SORTS).forEach(function (k) { sel.appendChild(new Option(SORTS[k], k)); });
    sel.value = S.sort;
    $("side-only-offers").checked = S.of;
    $("side-only-ho").checked = S.ho;
  }

  function renderFlights() {
    var box = $("side-flights"); clear(box);
    var fl = D.flights || {};
    var p = party();
    var h = el("div", "sf-head");
    h.appendChild(el("strong", "", "✈️ Letenky do Antalye (AYT)"));
    h.appendChild(el("span", "muted", " – Travelpayouts / Aviasales cache, cena za 1 os. × " + p.persons + " (orientačne)"));
    box.appendChild(h);
    if (fl.status === "no_token") {
      var w = el("div", "sf-warn");
      w.appendChild(el("strong", "", "Letenky: chýba TRAVELPAYOUTS_TOKEN – návod"));
      var ol = el("ol", "sf-steps");
      ["Zaregistrujte sa na travelpayouts.com (zadarmo) → Profil → API token, skopírujte token.",
       "Na github.com otvorte repozitár KaStihl/Holiday-tracker → Settings → Secrets and variables → Actions.",
       "New repository secret: názov TRAVELPAYOUTS_TOKEN, hodnota = token → Add secret.",
       "Spustite Actions → Refresh → Run workflow (alebo počkajte na ďalší automatický beh)."].forEach(function (t) { ol.appendChild(el("li", "", t)); });
      w.appendChild(ol);
      box.appendChild(w);
      return;
    }
    if (fl.status === "error") { box.appendChild(el("p", "sf-warn", "Letenky sa nepodarilo načítať: " + str(fl.error).slice(0, 160))); return; }
    var origins = (Array.isArray(fl.origins) ? fl.origins : []).filter(function (o) { return !S.dep || o === S.dep; });
    var row = el("div", "sf-list");
    var any = false;
    origins.forEach(function (o) {
      var pick = pickFlight(o);
      var c = el("div", "sf-item");
      c.appendChild(el("div", "sf-o", o + " " + (AIRPORT[o] || "")));
      if (!pick) {
        c.appendChild(el("div", "muted", "bez ceny v cache pre " + S.n + " nocí"));
        c.appendChild(link(aviasales({ o: o, dep: S.d, ret: addDays(S.d, S.n) }, p), "Hľadať " + short(S.d) + " na Aviasales ↗", "sf-link"));
        row.appendChild(c);
        return;
      }
      any = true;
      var f = pick.f;
      c.appendChild(el("div", "sf-p mono", eur(f.p * p.persons)));
      c.appendChild(el("div", "sf-d", eur(f.p) + "/os. · " + short(f.dep) + " – " + short(f.ret) + (f.k === "ow" ? " · 2× jednosmerná" : "") + (f.tr ? " · prestup" : " · priamy") + (f.al ? " · " + f.al : "")));
      if (!pick.nights) c.appendChild(el("div", "sf-other", f.n + " nocí (na " + S.n + " nocí cache nemá cenu)"));
      else if (!pick.exact) c.appendChild(el("div", "sf-other", "iný termín ako " + short(S.d) + " (±3 dni bez ceny)"));
      c.appendChild(link(aviasales(f, p), "Aviasales ↗", "sf-link"));
      row.appendChild(c);
    });
    box.appendChild(row);
    if (!any) box.appendChild(el("p", "muted sf-empty", "Cache Aviasales zatiaľ nemá ceny na " + S.n + " nocí v júli–auguste " + str(D.date_from).slice(0, 4) + " – pribudnú, keď ľudia začnú leto hľadať. Overte priamo cez odkaz Aviasales pri hoteli."));
    var x = paxOf(p);
    box.appendChild(el("p", "muted sf-note", "Cache cien z vyhľadávaní za posledné dni, nie rezervovateľná cena. Deti od 12 r. letia ako dospelí; deti 2–11 r. väčšinou tiež za plnú cenu – preto cena × " + p.persons + ". Odkaz Aviasales: " + x.a + " dosp." + (x.c ? " + " + x.c + " dieťa/deti" : "") + "."));
  }

  function matches(h, p) {
    if (S.a.length && S.a.indexOf(h.a) < 0) return false;
    for (var i = 0; i < S.c.length; i++) if (!critOf(h, S.c[i], p).length) return false;
    if (S.of && !(h.of && Array.isArray(h.of[p.id]) && h.of[p.id].length)) return false;
    if (S.ho && !hotelOnlyFor(h, p)) return false;
    if (S.q && fold(h.n).indexOf(fold(S.q)) < 0) return false;
    return true;
  }
  function sortKey(h, p) {
    if (S.sort === "crit") return [-critCount(h, p), num(h.d) === null ? 9999 : h.d];
    if (S.sort === "pkg") { var a = agencyFor(h, p); return [a ? a.r[1] : 1e9, num(h.d) || 0]; }
    if (S.sort === "own") { var o = ownPackage(h, p); return [o.total !== null ? o.total : 1e9, num(h.d) || 0]; }
    return [num(h.d) === null ? 9999 : h.d, -critCount(h, p)];
  }

  function areaName(id) { var a = (D.areas || []).filter(function (x) { return x.id === id; })[0]; return a ? a.name : str(id); }

  function card(h, p) {
    var c = el("article", "sh");
    var head = el("div", "sh-head");
    head.appendChild(el("h3", "sh-name", h.n));
    var st = num(h.st);
    if (st) head.appendChild(el("span", "offer-stars", "★".repeat(Math.floor(st)) + (st % 1 ? "½" : "")));
    c.appendChild(head);
    var meta = el("p", "sh-meta");
    var dist = num(h.d);
    meta.appendChild(el("span", "sh-dist", dist !== null ? "🏖️ ~" + nf.format(dist) + " m od " + (h.dk === "c" ? "pobrežia" : "pláže") + " (OSM)" : "🏖️ vzdialenosť z mapy neznáma"));
    if (Array.isArray(h.bd) && num(h.bd[0]) !== null) meta.appendChild(el("span", "sh-dist2", " · " + str(h.bd[1]) + ": " + nf.format(h.bd[0]) + " m k pláži"));
    meta.appendChild(el("span", "muted", " · " + areaName(h.a)));
    if (num(h.pools)) meta.appendChild(el("span", "muted", " · bazény v mape: " + h.pools));
    c.appendChild(meta);

    var badges = el("div", "sh-badges");
    (D.kriteria || []).forEach(function (k) {
      if (!CRIT[k]) return;
      var src = critOf(h, k, p);
      var b = el("span", "sh-badge " + (src.length ? "yes" : "unk"), (src.length ? "✓ " : "? ") + CRIT[k].icon + " " + CRIT[k].label);
      b.title = src.length ? "Zdroj: " + src.join("; ") : "Neznáme – cestovka ani OpenStreetMap to neuvádza (neznamená „nie“)";
      badges.appendChild(b);
      if (src.length) badges.lastChild.appendChild(el("small", "sh-src", " · " + src.slice(0, 2).join(", ") + (src.length > 2 ? " +" + (src.length - 2) : "")));
    });
    c.appendChild(badges);

    // prices
    var pr = el("div", "sh-prices");
    var ag = agencyFor(h, p);
    var own = ownPackage(h, p);
    var colA = el("div", "sh-col");
    colA.appendChild(el("div", "sh-col-t", "Zájazd od cestovky"));
    if (ag) {
      var r = ag.r;
      colA.appendChild(el("div", "sh-big mono", eur(r[1])));
      colA.appendChild(el("div", "sh-small", srcName(r[0]) + " · " + short(r[3]) + " · " + r[4] + " " + plural(r[4], "noc", "noci", "nocí") + (r[2] ? " · " + (BOARD[r[2]] || r[2]) : "") + (r[5] ? " · z " + r[5] : "")));
      colA.appendChild(el("div", "sh-small " + (r[6] ? "ok" : "approx"), r[6] ? "✓ presná cena pre " + p.persons + " os." : "orientačne (cena za os. × " + p.persons + ")"));
      if (ag.how !== "term") colA.appendChild(el("div", "sh-other", ag.how === "nights" ? "iný dátum ako " + short(S.d) : "iná dĺžka/termín – " + S.n + " nocí bez ponuky"));
      colA.appendChild(link(r[7], "Zobraziť zájazd ↗", "btn btn-sm"));
    } else colA.appendChild(el("div", "muted sh-small", "Žiadna ponuka cestovky pre túto skupinu."));
    pr.appendChild(colA);

    var colB = el("div", "sh-col");
    colB.appendChild(el("div", "sh-col-t", "Vlastný balík (odhad)"));
    var lines = el("ul", "sh-lines");
    function line(label, value, note) {
      var li = el("li");
      li.appendChild(el("span", "", label));
      li.appendChild(el("span", "mono", value));
      if (note) li.appendChild(el("small", "muted", note));
      lines.appendChild(li);
    }
    if (own.flight) {
      var f = own.flight.f;
      line("✈️ Letenky " + f.o + " " + short(f.dep) + "–" + short(f.ret), eur(own.fsum), "orientačne (cache, cena za 1 os. × " + p.persons + ")" + (!own.flight.nights ? " · " + f.n + " nocí, iná dĺžka" : own.flight.exact ? "" : " · iný termín"));
    } else line("✈️ Letenky", "?", D.flights && D.flights.status === "no_token" ? "chýba TRAVELPAYOUTS_TOKEN" : "v cache bez ceny na " + S.n + " nocí");
    if (own.ho) {
      var hr = own.ho.r;
      line("🏨 Ubytovanie " + short(hr[2]) + ", " + hr[3] + " n." + (hr[4] ? ", " + hr[4] : ""), eur(hr[1]), srcName(hr[0]) + " – orientačne" + (own.ho.how === "term" ? "" : " · iný dátum"));
    } else line("🏨 Ubytovanie", "?", "cena len ubytovania nedostupná");
    line("🚐 Transfer AYT ↔ hotel", eur(own.transfer), "odhad " + eur(D.transfer_eur) + " za cestu (nastavenia.yml)");
    colB.appendChild(lines);
    if (own.total !== null) {
      colB.appendChild(el("div", "sh-big mono", eur(own.total)));
      if (ag) {
        var diff = own.total - ag.r[1];
        colB.appendChild(el("div", "sh-diff " + (diff < 0 ? "good" : "bad"), "vlastný balík vs. zájazd od cestovky: " + signed(diff) + (diff < 0 ? " (lacnejší)" : " (drahší)")));
      }
    } else if (own.partial !== null) {
      colB.appendChild(el("div", "sh-small muted", "letenky + transfer: " + eur(own.partial) + " + ubytovanie ?"));
    }
    if (ho0(h, p)) colB.appendChild(link(own.ho ? own.ho.r[5] : ho0(h, p)[5], "Ubytovanie (" + srcName((own.ho ? own.ho.r : ho0(h, p))[0]) + ") ↗", "sh-link"));
    pr.appendChild(colB);
    c.appendChild(pr);

    var links = el("div", "sh-links");
    links.appendChild(link(booking(h, p), "Overiť na Booking.com ↗", "btn-ghost btn-sm"));
    links.appendChild(link(bookingViaGoogle(h), "Hotel na Booking (cez Google) ↗", "btn-ghost btn-sm"));
    links.appendChild(link(aviasales({ o: S.dep || (own.flight ? own.flight.f.o : "VIE"), dep: S.d, ret: addDays(S.d, S.n) }, p), "Letenky na Aviasales ↗", "btn-ghost btn-sm"));
    if (h.w) links.appendChild(link(h.w, "Web hotela ↗", "btn-ghost btn-sm"));
    if (num(h.lat) !== null && num(h.lon) !== null) links.appendChild(link("https://www.openstreetmap.org/?mlat=" + h.lat + "&mlon=" + h.lon + "#map=17/" + h.lat + "/" + h.lon, "Mapa ↗", "btn-ghost btn-sm"));
    c.appendChild(links);
    if (Array.isArray(h.an) && h.an.length) c.appendChild(el("p", "muted sh-an", "V cestovkách aj ako: " + h.an.join(", ")));
    return c;
  }
  function ho0(h, p) { var rows = h.ho && Array.isArray(h.ho[p.id]) ? h.ho[p.id] : []; return rows[0] || null; }

  function renderList() {
    var p = party();
    var list = (D.hotels || []).filter(function (h) { return h && typeof h.n === "string" && matches(h, p); });
    var keys = {};
    list.forEach(function (h) { keys[h.id] = sortKey(h, p); });
    list.sort(function (a, b) { var x = keys[a.id], y = keys[b.id]; return x[0] - y[0] || x[1] - y[1] || a.n.localeCompare(b.n, "sk"); });
    var box = $("side-list"); clear(box);
    $("side-count").textContent = list.length + " / " + (D.hotels || []).length;
    $("side-list-sub").textContent = list.length + " " + plural(list.length, "hotel", "hotely", "hotelov") + " · ceny pre: " + (p.nazov || "") + " (" + p.persons + " os.), " + S.n + " nocí od " + short(S.d);
    if (!list.length) box.appendChild(el("p", "muted", (D.hotels || []).length ? "Žiadny hotel nespĺňa filtre – skúste vypnúť niektoré kritérium (neznáme ≠ nie)." : "Zatiaľ bez hotelov – dáta z OpenStreetMap pribudnú po najbližšom behu."));
    list.slice(0, shown).forEach(function (h) { box.appendChild(card(h, p)); });
    $("side-more").hidden = list.length <= shown;
  }

  function renderNotes() {
    var ul = $("side-notes"); clear(ul);
    var osm = D.osm || {};
    var notes = [
      "Hotely a vzdialenosť od pláže: © OpenStreetMap prispievatelia (ODbL), cez Overpass API, obnova najviac raz týždenne" + (osm.fetched_at ? " (posledná " + short(osm.fetched_at) + str(osm.fetched_at).slice(0, 4) + ")" : "") + ". Vzdialenosť je od budovy/areálu hotela k najbližšej pláži (natural=beach) alebo k pobrežiu – orientačná. Limit: " + (num(D.max_m) || 300) + " m (nastavenia.yml → side_hotely).",
      "Rodinné kritériá: ✓ = potvrdené cestovkou (ikony/popis hotela v Kartago/Fischer, Satur, BILLA, názov izby, filter Ruefa) alebo mapou OSM (vodný park/tobogan v areáli); zdroj je pri odznaku. „?“ = nikto to neuvádza – neznamená to „nie“. Rodinná izba: aj keď cestovka ponúka presnú cenu pre celú skupinu v 1 izbe.",
      "Zájazd od cestovky: najlacnejšia ponuka hotela pre zvolenú skupinu a počet nocí s odletom ±3 dni od zvoleného dňa (inak iný termín, je to označené).",
      "Vlastný balík = letenky (cache Travelpayouts/Aviasales, cena za 1 os. × počet osôb – orientačne) + cena len ubytovania (ak ju má niektorý legitímny zdroj – zoznam nižšie; inak „cena len ubytovania nedostupná“ a súčet je bez ubytovania – overte cez „Overiť na Booking.com“) + transfer letisko Antalya ↔ hotel 2 × " + eur(D.transfer_eur) + " (odhad z nastavení). Všetky časti sú odhady – pred rezerváciou overte.",
      "Booking.com sa nesťahuje (podmienky to zakazujú) – tlačidlo „Overiť na Booking.com“ otvorí ich vyhľadávanie s menom hotela, termínom a osobami."
    ];
    var hos = D.hotel_only && Array.isArray(D.hotel_only.sources) ? D.hotel_only.sources : [];
    if (hos.length) notes.push("Zdroje ceny len ubytovania: " + hos.map(function (s) { return str(s.name) + " – " + (s.status === "ok" ? "funguje" : s.status === "unavailable" ? "nedostupné" : s.status === "empty" ? "bez ponúk v okolí Side" : "chyba") + (s.note ? " (" + str(s.note) + ")" : ""); }).join("; ") + ".");
    notes.forEach(function (t) { ul.appendChild(el("li", "", t)); });
  }

  function update() {
    shown = PAGE;
    if (!isDay(S.d)) S.d = D.date_from;
    renderControls();
    renderFlights();
    renderList();
    save();
  }
  function rerenderOnly() { renderFlights(); renderList(); save(); }

  function bind() {
    $("side-date").addEventListener("change", function () { if (isDay(this.value)) { S.d = this.value; update(); } });
    $("side-sort").addEventListener("change", function () { if (SORTS[this.value]) { S.sort = this.value; rerenderOnly(); } });
    $("side-only-offers").addEventListener("change", function () { S.of = this.checked; rerenderOnly(); });
    $("side-only-ho").addEventListener("change", function () { S.ho = this.checked; rerenderOnly(); });
    var t = null;
    $("side-q").addEventListener("input", function () { var v = this.value; clearTimeout(t); t = setTimeout(function () { S.q = v.slice(0, 60); rerenderOnly(); }, 160); });
    $("side-more").addEventListener("click", function () { shown += PAGE; renderList(); });
  }

  function start(json) {
    D = json && typeof json === "object" ? json : {};
    if (!Array.isArray(D.hotels)) D.hotels = [];
    if (!Array.isArray(D.kriteria)) D.kriteria = Object.keys(CRIT);
    if (!isDay(D.date_from)) D.date_from = "2027-07-01";
    if (!isDay(D.date_to)) D.date_to = "2027-08-31";
    if (isSample) $("side-sample-note").hidden = false;
    $("side-sub").textContent = D.enabled === false ? "Záložka je vypnutá v nastavenia.yml (side_hotely: enabled: false)." :
      "Hotely do " + (num(D.max_m) || 300) + " m od pláže v oblastiach " + (D.areas || []).map(function (a) { return a.name; }).join(", ") + ". Ceny zájazdov z cestoviek, letenky Viedeň/Bratislava/Brno → Antalya a vlastný balík.";
    if (window.matchMedia && window.matchMedia("(max-width: 720px)").matches) $("side-filters").open = false;
    S = loadState();
    bind();
    renderNotes();
    update();
  }

  function init() {
    D = {};
    var inline = document.getElementById("side-data");
    if (inline && !isSample) {
      var j = null;
      try { j = JSON.parse(inline.textContent); } catch (e) { j = null; }
      if (!j) { $("side-error").hidden = false; $("side-error").textContent = "Dáta pre záložku Side zatiaľ nie sú – pribudnú po najbližšom behu (Actions → Refresh)."; }
      start(j);
      return;
    }
    fetch(isSample ? "./data/side.sample.json" : "./data/side.json", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(start)
      .catch(function (err) {
        $("side-error").hidden = false;
        $("side-error").textContent = "Nepodarilo sa načítať dáta záložky Side: " + (err && err.message ? err.message : "neznáma chyba");
        start(null);
      });
  }

  initTabs();
})();
