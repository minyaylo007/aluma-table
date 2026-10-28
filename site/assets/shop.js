/* ALUMA — магазин: кошик і оформлення одним екраном без оплати на сайті (specs/003-shop-funnel, №38).
   Кошик — localStorage fx_cart_v1, поля оформлення — sessionStorage fx_checkout_v1; ціни — лише з каталогу (#aluma-data).
   Події — через alumaTrack (tracking.js); поки його нема — черга alumaQ, а перед переходом на іншу сторінку
   вона переїжджає в sessionStorage і програється вже там. Жодних особистих даних у подіях. */
(function () {
  "use strict";
  var D = document, W = window;
  var qs = function (s, r) { return (r || D).querySelector(s); };
  var qsa = function (s, r) { return Array.prototype.slice.call((r || D).querySelectorAll(s)); };
  var DATA = {};
  try { DATA = JSON.parse((qs("#aluma-data") || {}).textContent || "{}"); } catch (e) { DATA = {}; }
  var S = DATA.s || {}, PRODUCTS = DATA.products || [], CITIES = DATA.cities || [], PREFIX = DATA.prefix || "";
  var CART_KEY = "fx_cart_v1", CO_KEY = "fx_checkout_v1", CARRY_KEY = "fx_pq", MAX_QTY = 9, MAX_LINES = 10;
  var reduced = W.matchMedia && W.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------------------------------------------------------------- події
  // події, що не встигли піти зі сторінки до завантаження tracking.js, — у чергу першими
  try {
    var carried = JSON.parse(sessionStorage.getItem(CARRY_KEY) || "[]");
    sessionStorage.removeItem(CARRY_KEY);
    if (carried.length) {
      if (W.alumaTrack) carried.forEach(function (q) { W.alumaTrack(q[0], q[1], q[2]); });
      else W.alumaQ = carried.concat(W.alumaQ || []);
    }
  } catch (e) {}
  var track = function (name, params, opts) {
    try { if (W.alumaTrack) return W.alumaTrack(name, params || {}, opts); (W.alumaQ = W.alumaQ || []).push([name, params || {}, opts]); } catch (e) {}
    return "";
  };
  var newId = function (prefix) {
    try { if (W.alumaEventId) return W.alumaEventId(prefix); } catch (e) {}
    return prefix + "." + Date.now().toString(36) + "." + Math.random().toString(36).slice(2, 14);
  };
  var adsConsent = function () {
    try { if (W.alumaConsentState) return W.alumaConsentState() !== "denied"; } catch (e) {}   // opt-out: без вибору = згода
    try { return localStorage.getItem("fx_notice_v1") !== "0"; } catch (e) { return false; }
  };

  // ---------------------------------------------------------------- кошик
  var byId = function (id) { for (var i = 0; i < PRODUCTS.length; i++) if (PRODUCTS[i].id === id) return PRODUCTS[i]; return null; };
  // ціна як у build.py money(): «₪4,490»; у ru — «4 490 ₪» з нерозривними пробілами
  var money = function (n) {
    var s = Number(n || 0).toLocaleString("en-US");
    return D.documentElement.lang === "ru" ? s.replace(/,/g, "\u00a0") + "\u00a0₪" : "₪" + s;
  };
  var find = function (list, key, v) { for (var i = 0; i < list.length; i++) if (list[i][key] === v) return list[i]; return null; };
  // рядок кошика лише з того, що є в каталозі: товар, розмір із ціною, тон і опора зі списку товару
  function line(it) {
    var p = it && byId(it.id), sz = p && find(p.sizes, "label", it.size);
    if (!sz) return null;
    var fin = find(p.finishes, "id", it.finish) || p.finishes[0] || null, base = find(p.bases, "id", it.base) || p.bases[0] || null;
    var qty = Math.max(1, Math.min(MAX_QTY, parseInt(it.qty, 10) || 1));
    return { id: p.id, size: sz.label, finish: fin ? fin.id : "", base: base ? base.id : "", qty: qty,
             p: p, price: sz.price, finishName: fin ? fin.name : "", baseName: base ? base.name : "" };
  }
  function readCart() {
    var raw = null;
    try { raw = JSON.parse(localStorage.getItem(CART_KEY) || "null"); } catch (e) { raw = null; }
    var items = raw && raw.v === 1 && Array.isArray(raw.items) ? raw.items : [];
    return items.map(line).filter(Boolean).slice(0, MAX_LINES);
  }
  function saveCart(lines) {
    var items = lines.map(function (l) { return { id: l.id, size: l.size, finish: l.finish, base: l.base, qty: l.qty }; });
    try { localStorage.setItem(CART_KEY, JSON.stringify({ v: 1, items: items })); } catch (e) {}
    badge(lines);
  }
  // спосіб отримання — sessionStorage fx_ship_v1: "door" (за замовчуванням), "assembled" або "pickup"; ціни — DATA.ship (content.json)
  var SHIP = DATA.ship || {}, SHIP_KEY = "fx_ship_v1", shipMem = "";
  var shipWay = function () {
    var v = shipMem;
    try { v = sessionStorage.getItem(SHIP_KEY) || v; } catch (e) {}
    // №31: без передвибору — доки людина не обрала, спосіб "" і в сумі лише товар (раніше «door» за замовчуванням
    // додавав ₪950 і підсумок у кошику стрибав)
    return v === "pickup" || v === "assembled" || v === "door" ? v : "";
  };
  var shipFee = function () { return Number(SHIP[shipWay()]) || 0; };
  // радіо name="ship" у box: показати збережений вибір, на зміну — зберегти, подія select_ship, перерахувати суми
  function wireShip(box, redraw, where) {
    qsa('input[name="ship"]', box).forEach(function (r) {
      r.checked = r.value === shipWay();
      r.addEventListener("change", function () {
        if (!r.checked) return;
        shipMem = r.value;
        try { sessionStorage.setItem(SHIP_KEY, r.value); } catch (e) {}
        var err = qs("#ship-err", box);
        if (err) { err.textContent = ""; err.hidden = true; }
        track("select_ship", { ship: r.value, fee: shipFee(), step: where }, { pixel: false });
        redraw();
      });
    });
  }
  // «מוצרים / משלוח / סה״כ»: сума товарів, ціна доставки (або «לבחירה למטה», доки не обрано), разом
  function sums(box, lines, totalSel) {
    var g = qs("[data-sum-goods]", box), f = qs("[data-sum-ship]", box), t = qs(totalSel, box), way = shipWay();
    if (g) g.textContent = money(total(lines));
    if (f) {
      f.textContent = way ? money(shipFee()) : (f.getAttribute("data-none") === "below" ? S.ship_below : S.ship_none) || "";
      f.setAttribute("dir", way ? "ltr" : "auto");
    }
    if (t) t.textContent = money(total(lines) + shipFee());
  }
  // PDF збирання біля «עד הדלת»: лише для товарів кошика, що мають PDF (своєю мовою, інакше en)
  function shipPdf(box, lines) {
    var el = qs("[data-ship-pdf]", box);
    if (!el) return;
    var seen = [], links = [];
    lines.forEach(function (l) { if (l.p.pdf && seen.indexOf(l.p.id) < 0) { seen.push(l.p.id); links.push(l.p); } });
    el.innerHTML = "";
    links.forEach(function (p, i) {
      var own = !p.pdf_en, a = D.createElement("a");
      a.href = p.pdf; a.target = "_blank"; a.rel = "noopener"; a.setAttribute("data-cta", "assembly_pdf");
      a.textContent = el.getAttribute("data-l-door") + " · " + el.getAttribute(own ? "data-l-own" : "data-l-en") +
        (links.length > 1 ? " — " + p.name : "");
      if (i) el.appendChild(D.createElement("br"));
      el.appendChild(a);
    });
    el.hidden = !links.length;
  }
  var count = function (lines) { return lines.reduce(function (n, l) { return n + l.qty; }, 0); };
  var total = function (lines) { return lines.reduce(function (n, l) { return n + l.qty * l.price; }, 0); };
  var ids = function (lines) { var out = []; lines.forEach(function (l) { if (out.indexOf(l.id) < 0) out.push(l.id); }); return out; };
  // для заявки: slug:розмір:тон:опора:кількість через «;» (api/handler.py CART_ITEM)
  var cartString = function (lines) {
    return lines.map(function (l) { return [l.p.slug, l.size, l.finish, l.base, l.qty].join(":"); }).join(";");
  };
  // спільні параметри подій кроку: без імен і телефонів
  function cartParams(lines) {
    var first = lines[0] || {};
    return { content_ids: ids(lines), content_type: "product", value: total(lines), currency: "ILS", num_items: count(lines),
             size: first.size || "", finish: first.finish || "", base: first.base || "" };
  }

  function badge(lines) {
    var n = count(lines || readCart());
    qsa("[data-cart-n]").forEach(function (el) { el.textContent = n ? String(n) : ""; el.hidden = !n; });
    qsa("[data-cart-sr]").forEach(function (el) { el.hidden = !n; });
  }
  badge();

  // ---------------------------------------------------------------- картка товару: «הוספה לסל»
  var pdp = qs("[data-pdp]");
  if (pdp) {
    var config = qs("[data-config]");
    var picked = function (n) { var el = qs('input[name="' + n + '"]:checked', config || pdp); return el ? el.value : ""; };
    qsa("[data-add-cart]").forEach(function (b) {
      b.addEventListener("click", function () {
        var l = line({ id: pdp.getAttribute("data-product"), size: picked("size"), finish: picked("finish"), base: picked("base"), qty: 1 });
        if (!l && byId(pdp.getAttribute("data-product"))) {
          var p0 = byId(pdp.getAttribute("data-product"));
          l = line({ id: p0.id, size: (p0.sizes[0] || {}).label, finish: picked("finish"), base: picked("base"), qty: 1 });
        }
        if (!l) return;
        var lines = readCart(), same = null;
        lines.forEach(function (x) { if (x.id === l.id && x.size === l.size && x.finish === l.finish && x.base === l.base) same = x; });
        if (same) same.qty = Math.min(MAX_QTY, same.qty + 1);
        else { if (lines.length >= MAX_LINES) lines.shift(); lines.push(l); }
        saveCart(lines);
        track("AddToCart", { content_ids: [l.id], content_type: "product", size: l.size, finish: l.finish, base: l.base,
                             price: l.price, value: l.price, currency: "ILS", num_items: count(lines), cta: b.getAttribute("data-cta") || "" });
        go(PREFIX + "/cart/");
      });
    });
  }

  // перехід після події: спершу черга tracking.js маяком (pagehide лишається страховкою); якщо tracking.js
  // ще не прийшов — черга alumaQ переживе сторінку (pagehide нижче)
  function go(href) { try { if (W.alumaFlush) W.alumaFlush(); } catch (e) {} W.location.href = href; }

  // ---------------------------------------------------------------- сторінка кошика
  var cartBox = qs("[data-cart]");
  if (cartBox) {
    var list = qs("[data-cart-list]", cartBox), L = function (k) { return cartBox.getAttribute("data-l-" + k) || ""; };
    var render = function () {
      var lines = readCart();
      list.innerHTML = "";
      lines.forEach(function (l, i) { list.appendChild(cartRow(l, i, L)); });
      qs("[data-cart-empty]", cartBox).hidden = !!lines.length;
      qs("[data-cart-sum]", cartBox).hidden = !lines.length;
      sums(cartBox, lines, "[data-cart-total]");
      shipPdf(cartBox, lines);
      return lines;
    };
    var shown = render();
    wireShip(cartBox, render, "cart");
    track("view_cart", cartParams(shown));
    list.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("button[data-act]");
      if (!b) return;
      var lines = readCart(), i = parseInt(b.getAttribute("data-i"), 10), act = b.getAttribute("data-act"), l = lines[i];
      if (!l) return;
      if (act === "more") l.qty = Math.min(MAX_QTY, l.qty + 1);
      else if (act === "less") l.qty = Math.max(1, l.qty - 1);
      else if (act === "remove") lines.splice(i, 1);
      saveCart(lines);
      render();
      // фокус лишається на тій самій кнопці (або на заголовку, якщо рядок зник)
      var again = qs('button[data-act="' + act + '"][data-i="' + i + '"]', list) || qs("[data-cart-pay]") || qs(".shop-h1");
      if (again && again.focus) try { again.focus({ preventScroll: true }); } catch (x) {}
    });
    var pay = qs("[data-cart-pay]", cartBox);
    if (pay) pay.addEventListener("click", function () {
      var lines = readCart();
      if (!lines.length) return;
      var p = cartParams(lines);
      p.event_id = newId("ic");
      p.ads_consent = adsConsent();
      track("InitiateCheckout", p);
      try { if (W.alumaFlush) W.alumaFlush(); } catch (e) {}   // посилання: маяк до переходу, як у go()
    });
  }

  function cartRow(l, i, L) {
    var li = D.createElement("li"); li.className = "cart-line";
    var img = l.p.img ? '<img class="cart-img" src="' + esc(l.p.img) + '" alt="" width="96" height="96" loading="lazy" decoding="async">' : "";
    var meta = [L("size") + ": <bdi dir=\"ltr\">" + esc(l.size) + "</bdi>"];
    if (l.finishName) meta.push(L("finish") + ": " + esc(l.finishName));
    if (l.baseName) meta.push(L("base") + ": " + esc(l.baseName));
    var ctrls = L("qty") ? '<div class="qty" role="group" aria-label="' + esc(L("qty") + " — " + l.p.name) + '">' +
      '<button type="button" class="qty-b" data-act="less" data-i="' + i + '"' + (l.qty <= 1 ? " disabled" : "") + ' aria-label="' + esc(L("less")) + '">−</button>' +
      '<output class="qty-n" aria-live="polite">' + l.qty + "</output>" +
      '<button type="button" class="qty-b" data-act="more" data-i="' + i + '"' + (l.qty >= MAX_QTY ? " disabled" : "") + ' aria-label="' + esc(L("more")) + '">+</button></div>' +
      '<button type="button" class="link-btn cart-rm" data-act="remove" data-i="' + i + '">' + esc(L("remove")) + "</button>" : "";
    li.innerHTML = img + '<div class="cart-info"><p class="cart-name"><a href="' + esc(PREFIX + "/p/" + l.p.slug + "/") + '">' + esc(l.p.name) + "</a></p>" +
      '<p class="cart-meta">' + meta.join(" · ") + "</p>" + ctrls + "</div>" +
      '<p class="cart-price"><bdi dir="ltr">' + money(l.price * l.qty) + "</bdi></p>";
    return li;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }

  // ---------------------------------------------------------------- оформлення: один екран (№38)
  // місто, спосіб отримання, «коли», телефон (обов'язковий), ім'я, згода → POST /api/fx/lead (lead_source=checkout);
  // підтвердження — текстом тут же, без переходу. Події: checkout_details — коли вперше заповнено місто й «коли»,
  // reach_payment — натиснуто «להזמנה» з правильними полями (крок «payment» воронки), Lead — успіх, checkout_error — збій
  var co = qs('[data-shop="checkout"]');
  var payShown = false;
  if (co) {
    var lines = readCart();
    var form = qs("[data-co-form]", co), side = qs("[data-co-side]", co);
    if (!lines.length) qs("[data-co-empty]", co).hidden = false;
    else {
      form.hidden = false; side.hidden = false;
      var mini = qs("[data-co-list]", co);
      var LS = function (k) { return k === "qty" ? "" : side.getAttribute("data-l-" + k) || ""; };
      lines.forEach(function (l, i) { mini.appendChild(cartRow(l, i, LS)); });
      var toggle = qs("[data-co-sum-toggle]", co), body = qs("[data-co-sum-body]", co);
      // рядок «תבור 200×100 · משלוח עד הדלת · ₪6,240» для телефону
      var sumLine = function () {
        var first = lines[0], n = count(lines), way = qs('input[name="ship"]:checked', form);
        var bits = [first.p.name + " " + first.size + (n > 1 ? " +" + (n - 1) : "")];
        if (way) bits.push(way.parentNode.textContent.split(" —")[0].trim());
        qs("[data-co-sum-text]", co).textContent = bits.join(" · ");
        qs("[data-co-total-line]", co).textContent = money(total(lines) + shipFee());
      };
      var coSums = function () { sums(co, lines, "[data-co-total]"); sumLine(); };
      wireShip(form, coSums, "checkout");
      shipPdf(form, lines);
      coSums();
      var narrow = W.matchMedia ? W.matchMedia("(max-width: 899px)") : { matches: false };
      var fold = function () {
        var open = !narrow.matches || toggle.getAttribute("aria-expanded") === "true";
        toggle.hidden = !narrow.matches; body.hidden = !open;
      };
      toggle.addEventListener("click", function () {
        toggle.setAttribute("aria-expanded", toggle.getAttribute("aria-expanded") === "true" ? "false" : "true");
        fold();
      });
      if (narrow.addEventListener) narrow.addEventListener("change", fold);
      fold();

      var el = form.elements;
      var when = function () { var x = qs('input[name="when"]:checked', form); return x ? x.value : ""; };
      var readSaved = function () { try { return JSON.parse(sessionStorage.getItem(CO_KEY) || "{}") || {}; } catch (e) { return {}; } };
      // поля переживають перезавантаження й помилку мережі (sessionStorage цієї вкладки, як і раніше)
      var keep = function () {
        var d = { city: el.city.value, when: when(), name: String(el.name.value || "").trim(), phone: String(el.phone.value || "").trim() };
        try { sessionStorage.setItem(CO_KEY, JSON.stringify(d)); } catch (x) {}
        return d;
      };
      var saved = readSaved();
      if (saved.city && find(CITIES, "id", saved.city)) el.city.value = saved.city;
      if (saved.when) { var r = qs('input[name="when"][value="' + saved.when + '"]', form); if (r) r.checked = true; }
      if (saved.name) el.name.value = saved.name;
      if (saved.phone) el.phone.value = saved.phone;

      var setErr = function (id, msg, input) {
        var err = qs("#" + id, form);
        if (err) { err.textContent = msg || ""; err.hidden = !msg; }
        if (input && input.setAttribute) { if (msg) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid"); }
      };
      var detailsSent = false;
      var details = function () {
        var d = keep();
        if (detailsSent || !d.city || !d.when) return;
        detailsSent = true;
        var p = cartParams(lines);
        p.city = d.city; p.when = d.when; p.ship = shipWay(); p.has_name = !!d.name; p.has_phone = !!d.phone;
        track("checkout_details", p);
      };
      el.city.addEventListener("change", function () { setErr("co-e-city", "", el.city); details(); });
      qsa('input[name="when"]', form).forEach(function (x) { x.addEventListener("change", function () { setErr("co-e-when", ""); details(); }); });
      el.phone.addEventListener("input", function () { setErr("co-e-phone", "", el.phone); keep(); });
      el.name.addEventListener("input", keep);
      el.consent.addEventListener("change", function () { setErr("co-e-consent", "", el.consent); });

      var status = qs(".f-status", form), btn = qs('button[type="submit"]', form), busy = false, thanks = qs("[data-co-thanks]", co);
      var fail = function (code, msg) {
        busy = false; form.removeAttribute("aria-busy"); btn.disabled = false;
        btn.textContent = btn.getAttribute("data-l-retry") || btn.textContent;
        status.className = "f-status is-err"; status.textContent = msg || "";
        track("checkout_error", { code: code, step: "checkout", value: total(lines), num_items: count(lines) }, { pixel: false });
      };
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        if (busy) return;
        var d = keep(), city = find(CITIES, "id", d.city), bad = null;
        setErr("co-e-city", "", el.city); setErr("ship-err", ""); setErr("co-e-when", "");
        setErr("co-e-phone", "", el.phone); setErr("co-e-consent", "", el.consent);
        // перша помилка в порядку полів на екрані: місто → спосіб отримання → «коли» → телефон → згода
        if (!city) { setErr("co-e-city", S.e_city, el.city); bad = el.city; }
        if (!shipWay()) { setErr("ship-err", S.e_ship); bad = bad || qs('input[name="ship"]', form); }
        if (!d.when) { setErr("co-e-when", S.e_when); bad = bad || qs('input[name="when"]', form); }
        if (!phoneOk(d.phone)) { setErr("co-e-phone", S.e_phone, el.phone); bad = bad || el.phone; }
        if (!el.consent.checked) { setErr("co-e-consent", S.e_consent, el.consent); bad = bad || el.consent; }
        if (bad) { status.className = "f-status is-err"; status.textContent = S.invalid || ""; bad.focus(); return; }
        if (!payShown) {
          payShown = true;
          var pp = cartParams(lines);
          pp.city = d.city.slice(0, 30); pp.when = d.when;
          track("reach_payment", pp);
        }
        var first = lines[0], attr = attribution(), ap = attr.p || {};
        var data = {
          name: d.name, phone: d.phone, city: city.name, comment: "",
          website: el.website ? el.website.value : "", consent: true, consent_marketing: false, marketing_consent: false,
          ads_consent: adsConsent(), consent_text_version: DATA.consent || "v1", lang: DATA.lang || D.documentElement.lang,
          product_id: first.id, size_label: first.size, finish_id: first.finish, base_id: first.base,
          timeframe: d.when, contact_pref: "whatsapp", lead_source: "checkout",
          cart: cartString(lines), order_total: total(lines), delivery: shipWay(),
          session_id: sessionId(), page: location.pathname, referrer: D.referrer || "",
          device: W.matchMedia("(min-width: 900px)").matches ? "desktop" : "mobile", attributed_at: attr.at || ""
        };
        data.color = data.finish_id.slice(0, 40);
        data.size = data.size_label.replace(/[^0-9]/g, "").slice(0, 3);
        ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid"].forEach(function (k) { data[k] = ap[k] || ""; });
        var eventId = newId("lead");
        data.event_id = eventId;
        busy = true; form.setAttribute("aria-busy", "true"); btn.disabled = true;
        status.className = "f-status"; status.textContent = S.sending || "";
        fetch("/api/fx/lead", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(data) })
          .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { code: r.status, body: b || {} }; }); })
          .then(function (res) {
            if (res.code === 200 && res.body.ok) {
              if (res.body.id !== "hp") {          // приманка для ботів теж «ok» — це не конверсія
                var lp = cartParams(lines); lp.event_id = eventId;
                track("Lead", lp);
              }
              form.hidden = true;
              saveCart([]);                         // замовлення пішло — кошик порожній, бейдж зникає
              try { sessionStorage.removeItem(CO_KEY); } catch (x) {}
              thanks.hidden = false;
              try { thanks.focus({ preventScroll: true }); } catch (x) {}
              try { thanks.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" }); } catch (x) {}
              D.body.classList.add("is-registered");
              return;
            }
            if (res.code === 422 && res.body && res.body.errors) {
              if (res.body.errors.phone) setErr("co-e-phone", S.e_phone, el.phone);
              if (res.body.errors.consent) setErr("co-e-consent", S.e_consent, el.consent);
            }
            fail(res.code === 429 ? "rate" : res.code === 422 ? "invalid" : "http_" + res.code,
                 res.code === 429 ? S.rate : res.code === 503 && res.body && res.body.error === "preview_only" ? S.preview
                   : res.code === 422 ? S.invalid : S.fail);
          }, function () { fail("offline", S.offline); });
      });
    }
  }

  // телефон заявки: ізраїльський номер (05x…, 0x…, +972…) або міжнародний від 8 цифр
  var PHONE_NATIONAL = /^(?:5\d{8}|[23489]\d{7}|7[2-9]\d{7})$/;
  function phoneOk(raw) {
    var d = String(raw || "").replace(/[^0-9]/g, "");
    if (!d || d.length > 15) return false;
    if (d.slice(0, 2) === "00") d = d.slice(2);
    var nat;
    if (d.slice(0, 3) === "972") nat = d.slice(3).replace(/^0+/, "");
    else if (d.charAt(0) === "0") nat = d.slice(1);
    else return d.length >= 8;
    return PHONE_NATIONAL.test(nat);
  }
  function attribution() {
    var rec = null;
    try { rec = JSON.parse(localStorage.getItem("fx_attr") || "null"); } catch (e) { rec = null; }
    if (rec && rec.at && (Date.now() - Date.parse(rec.at)) > 30 * 864e5) rec = null;
    return rec || { at: "", p: {} };
  }
  function sessionId() {
    var id = null;
    try { id = sessionStorage.getItem("fx_sid"); } catch (e) {}
    if (!id) { id = Date.now().toString(36) + Math.random().toString(36).slice(2, 10); try { sessionStorage.setItem("fx_sid", id); } catch (e) {} }
    return id;
  }

  // ---------------------------------------------------------------- глибина прокрутки і догляд зі сторінки
  // лише в нашу аналітику (pixel:false): Meta ці події не потрібні
  var nextCard = qs("[data-next]");   // №22: картка варіанта наступного видання — свій крок, час на ній окремо
  var step = pdp ? "pdp" : nextCard ? "next" : cartBox ? "cart" : co ? "checkout" : "other";
  var t0 = Date.now(), maxDepth = 0, maxPx = 0, marks = { 50: false, 90: false };
  // 24.10: scroll був 0 у 45 із 49 мобільних сесій, зокрема в тих, що вибирали тон нижче згину. Позицію беремо
  // з усіх трьох джерел (вбудовані браузери Instagram/Facebook не завжди ведуть W.scrollY), px — окремо від %
  var top = function () {
    var se = D.scrollingElement, de = D.documentElement;
    return Math.max(W.scrollY || W.pageYOffset || 0, se ? se.scrollTop : 0, de ? de.scrollTop : 0, D.body ? D.body.scrollTop : 0);
  };
  var depth = function (y) {
    var h = D.documentElement.scrollHeight - W.innerHeight;
    return h > 0 ? Math.min(100, Math.round(y / h * 100)) : 100;
  };
  var onScroll = function () {
    var y = Math.round(top()), d = depth(y);
    if (y > maxPx) maxPx = y;
    if (d > maxDepth) maxDepth = d;
    [50, 90].forEach(function (m) { if (!marks[m] && d >= m) { marks[m] = true; track("scroll", { depth: m, step: step }, { pixel: false }); } });
  };
  W.addEventListener("scroll", onScroll, { passive: true });
  D.addEventListener("scroll", onScroll, { passive: true, capture: true });   // прокрутка не вікна, а кореня/body
  var left = false;
  W.addEventListener("pagehide", function () {
    if (!left) {
      left = true;
      onScroll();   // остання позиція — навіть якщо подія scroll так і не прийшла
      // scroll_px — найглибша позиція в px, vh — висота екрана, ph — висота сторінки: лише числа, без ПД
      track("leave", { step: payShown ? "payment" : step, seconds: Math.round((Date.now() - t0) / 1000), scroll: maxDepth,
                       scroll_px: maxPx, vh: W.innerHeight, ph: D.documentElement.scrollHeight,
                       product: (pdp || nextCard) ? (pdp || nextCard).getAttribute("data-product") : "" }, { pixel: false });
    }
    // tracking.js не встиг завантажитися — черга їде на наступну сторінку
    try { if (!W.alumaTrack && W.alumaQ && W.alumaQ.length) sessionStorage.setItem(CARRY_KEY, JSON.stringify(W.alumaQ.slice(-30))); } catch (e) {}
  });
  W.addEventListener("pageshow", function (e) { if (e.persisted) { left = false; t0 = Date.now(); badge(); } });
})();
