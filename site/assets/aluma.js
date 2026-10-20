/* ALUMA — вітрина. Ванільний JS, без залежностей.
   Піксель, PageView, згода й /api/fx/config — у tracking.js (сесія 3); тут лише виклики
   alumaTrack/alumaEventId/alumaConsent/alumaConfig, якщо вони є. Без tracking.js сайт працює. */
(function () {
  "use strict";
  var D = document, W = window;
  var qs = function (s, r) { return (r || D).querySelector(s); };
  var qsa = function (s, r) { return Array.prototype.slice.call((r || D).querySelectorAll(s)); };
  var DATA = {};
  try { DATA = JSON.parse((qs("#aluma-data") || {}).textContent || "{}"); } catch (e) { DATA = {}; }
  var S = DATA.s || {};
  var PRODUCTS = DATA.products || [];
  var reduced = W.matchMedia && W.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var track = function (name, params) { try { if (W.alumaTrack) return W.alumaTrack(name, params || {}); } catch (e) {} return ""; };
  var byId = function (id) { for (var i = 0; i < PRODUCTS.length; i++) if (PRODUCTS[i].id === id) return PRODUCTS[i]; return null; };
  var money = function (n) { return "₪" + Number(n || 0).toLocaleString("en-US"); };

  // ---------------------------------------------------------------- меню
  var menuBtn = qs(".menu-btn"), nav = qs("#nav");
  if (menuBtn && nav) {
    menuBtn.addEventListener("click", function () {
      var open = menuBtn.getAttribute("aria-expanded") !== "true";
      menuBtn.setAttribute("aria-expanded", String(open));
      nav.classList.toggle("is-open", open);
    });
    D.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && nav.classList.contains("is-open")) { menuBtn.click(); menuBtn.focus(); }
    });
  }
  var here = location.pathname.replace(/index\.html$/, "");
  qsa(".nav a").forEach(function (a) { if (a.getAttribute("href") === here) a.setAttribute("aria-current", "page"); });

  // ---------------------------------------------------------------- згода на cookies
  // "1" — згода (tracking.js вантажить Pixel/Clarity), "0" — лише необхідне; без запису — питаємо.
  var notice = qs("#notice");
  var NOTICE_KEY = "fx_notice_v1";
  var choice = null;
  try { choice = localStorage.getItem(NOTICE_KEY); } catch (e) {}
  var showNotice = function () { if (notice) { notice.hidden = false; var b = qs("[data-notice-ok]", notice); if (b) b.focus({ preventScroll: true }); } };
  if (notice) {
    if (choice !== "1" && choice !== "0") notice.hidden = false;
    var okBtn = qs("[data-notice-ok]", notice), noBtn = qs("[data-notice-no]", notice);
    if (okBtn) okBtn.addEventListener("click", function () {
      try { localStorage.setItem(NOTICE_KEY, "1"); } catch (e) {}
      notice.hidden = true;
      try { if (W.alumaConsent) W.alumaConsent(); } catch (e) {}
    });
    if (noBtn) noBtn.addEventListener("click", function () {
      var was = null;
      try { was = localStorage.getItem(NOTICE_KEY); localStorage.setItem(NOTICE_KEY, "0"); } catch (e) {}
      notice.hidden = true;
      if (was === "1") location.reload();            // відкликання згоди: сторонній код уже на сторінці — перезавантажуємо без нього
    });
  }
  qsa("[data-cookie-settings]").forEach(function (b) { b.addEventListener("click", showNotice); });

  // ---------------------------------------------------------------- меню נגישות
  var A11Y_KEY = "fx_a11y", root = D.documentElement, a11y = {};
  try { a11y = JSON.parse(localStorage.getItem(A11Y_KEY) || "{}") || {}; } catch (e) { a11y = {}; }
  var aBox = qs("[data-a11y]");
  if (aBox) {
    var aBtn = qs(".a11y-btn", aBox), aPanel = qs(".a11y-panel", aBox);
    var paint = function () {
      qsa("[data-a11y-opt]", aBox).forEach(function (b) {
        var k = b.getAttribute("data-a11y-opt");
        root.classList.toggle("a11y-" + k, !!a11y[k]);
        b.setAttribute("aria-pressed", a11y[k] ? "true" : "false");
      });
      try { localStorage.setItem(A11Y_KEY, JSON.stringify(a11y)); } catch (e) {}
    };
    var openPanel = function (open) {
      aPanel.hidden = !open; aBtn.setAttribute("aria-expanded", String(open));
      if (open) { var f = qs("button", aPanel); if (f) f.focus(); }
    };
    aBtn.addEventListener("click", function () { openPanel(aPanel.hidden); });
    aBox.addEventListener("click", function (e) {
      var b = e.target.closest("[data-a11y-opt]");
      if (b) { var k = b.getAttribute("data-a11y-opt"); a11y[k] = !a11y[k]; paint(); }
      if (e.target.closest("[data-a11y-reset]")) { a11y = {}; paint(); }
    });
    D.addEventListener("keydown", function (e) { if (e.key === "Escape" && !aPanel.hidden) { openPanel(false); aBtn.focus(); } });
    D.addEventListener("click", function (e) { if (!aPanel.hidden && !aBox.contains(e.target)) openPanel(false); });
    paint();
  }
  if (a11y.still) reduced = true;

  // ---------------------------------------------------------------- контакти й WhatsApp з /api/fx/config
  var CFG = null;
  function currentProduct() {
    var pdp = qs("[data-pdp]");
    return pdp ? byId(pdp.getAttribute("data-product")) : null;
  }
  function waHref(where) {
    if (!CFG || !CFG.wa_number) return "";
    var p = currentProduct(), text = (S.wa_text || "") + " " + (p ? p.name : "ALUMA");
    var sz = qs('input[name="size"]:checked');
    if (p && sz) text += " " + sz.value;
    return "https://wa.me/" + String(CFG.wa_number).replace(/[^0-9]/g, "") + "?text=" + encodeURIComponent(text.trim());
  }
  function applyConfig(cfg) {
    if (!cfg || CFG) return;
    CFG = cfg;
    var c = cfg.contact || {}, any = false;
    qsa("[data-c]").forEach(function (el) {
      var k = el.getAttribute("data-c"), v = c[k];
      if (!v) return;
      any = true;
      el.textContent = v;
      if (k === "phone") el.setAttribute("href", "tel:" + String(v).replace(/[^0-9+]/g, ""));
      if (k === "email") el.setAttribute("href", "mailto:" + v);
      el.hidden = false;
      var inline = el.closest("[data-c-inline]");
      if (inline) inline.hidden = false;
    });
    if (cfg.wa_number) {
      any = true;
      qsa(".js-wa").forEach(function (a) { a.hidden = false; a.setAttribute("href", waHref()); a.setAttribute("target", "_blank"); a.setAttribute("rel", "noopener"); });
    }
    var box = qs("[data-contact]");
    if (box && any) box.hidden = false;
    // רכז/ת נגישות — з налаштувань /admin (сесія 3), порожнє не показуємо
    var ac = cfg.accessibility_contact || {}, acAny = false;
    qsa("[data-ac]").forEach(function (el) {
      var k = el.getAttribute("data-ac"), v = ac[k];
      if (!v) return;
      acAny = true; el.textContent = v; el.hidden = false;
      if (k === "phone") el.setAttribute("href", "tel:" + String(v).replace(/[^0-9+]/g, ""));
      if (k === "email") el.setAttribute("href", "mailto:" + v);
    });
    qsa("[data-ac-box]").forEach(function (el) { el.hidden = !acAny; });
  }
  D.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest(".js-wa, a[data-c='phone'], a[data-c='email']");
    if (!a) return;
    if (a.classList.contains("js-wa")) a.setAttribute("href", waHref());
    var p = currentProduct();
    track("Contact", { method: a.classList.contains("js-wa") ? "whatsapp" : a.getAttribute("data-c"), content_ids: p ? [p.id] : [] });
  });
  D.addEventListener("aluma:config", function (e) { applyConfig(e.detail); });
  if (W.alumaConfig) {
    try { W.alumaConfig().then(applyConfig, function () {}); } catch (e) {}
  } else if (W.fetch) {
    // tracking.js ще не підключено — читаємо налаштування самі; 404/помилка = блоки лишаються схованими
    fetch("/api/fx/config", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (cfg) { if (cfg && !W.alumaConfig) applyConfig(cfg); }, function () {});
  }

  // ---------------------------------------------------------------- форма: селекти товару
  var form = qs("[data-form]");
  var fProduct = form && qs("#f-product", form), fSize = form && qs("#f-size", form),
      fFinish = form && qs("#f-finish", form), fBase = form && qs("#f-base", form),
      cfgRow = form && qs("[data-config-row]", form);
  function fillSelect(sel, items, label) {
    if (!sel) return;
    sel.innerHTML = "";
    var empty = D.createElement("option"); empty.value = ""; empty.textContent = S.any || "—"; sel.appendChild(empty);
    items.forEach(function (it) {
      var o = D.createElement("option"); o.value = it.value; o.textContent = it.text; sel.appendChild(o);
    });
    sel.closest(".f").hidden = !items.length;
  }
  function syncFormProduct(id, size, finish, base) {
    if (!fProduct) return;
    var p = byId(id);
    fProduct.value = p ? id : "";
    if (cfgRow) cfgRow.hidden = !p;
    if (!p) return;
    fillSelect(fSize, p.sizes.map(function (s) { return { value: s.label, text: s.label + " · " + money(s.price) }; }));
    fillSelect(fFinish, p.finishes.map(function (f) { return { value: f.id, text: f.name }; }));
    fillSelect(fBase, p.bases.map(function (b) { return { value: b.id, text: b.name }; }));
    if (size !== undefined && fSize) fSize.value = size;
    if (finish !== undefined && fFinish) fFinish.value = finish;
    if (base !== undefined && fBase) fBase.value = base;
  }
  if (fProduct) fProduct.addEventListener("change", function () { syncFormProduct(fProduct.value); });

  // ---------------------------------------------------------------- конфігуратор картки товару
  var pdp = qs("[data-pdp]"), config = qs("[data-config]");
  if (pdp) {
    var P = currentProduct();
    var priceEl = qs(".price[data-price] bdi"), mini = qs("[data-price-mini]"), finishName = qs("[data-finish-name]");
    var val = function (n) { var el = qs('input[name="' + n + '"]:checked', config || D); return el ? el.value : ""; };
    var syncAll = function () { if (P) syncFormProduct(P.id, val("size"), val("finish"), val("base")); };
    var updatePrice = function () {
      var sz = qs('input[name="size"]:checked', config || D);
      if (sz && sz.getAttribute("data-price")) {
        var m = money(sz.getAttribute("data-price"));
        if (priceEl) priceEl.textContent = m;
        if (mini) mini.textContent = m;
      }
    };
    if (config) config.addEventListener("change", function (e) {
      var t = e.target;
      if (t.name === "finish" && finishName) finishName.textContent = t.getAttribute("data-name") || "";
      updatePrice();
      syncAll();
      if (P) track("CustomizeProduct", { content_ids: [P.id], content_type: "product", size: val("size"), finish: val("finish"), base: val("base") });
    });
    updatePrice();
    syncAll();
    if (P) {
      var first = P.sizes[0];
      track("ViewContent", { content_ids: [P.id], content_type: "product", content_name: P.name, value: first ? first.price : P.from, currency: "ILS" });
    }
  }
  // «Інший розмір» → коментар у формі
  qsa(".js-custom").forEach(function (a) {
    a.addEventListener("click", function () {
      var c = form && qs("#f-comment", form);
      if (c && !c.value) c.value = S.custom_text || "";
      setTimeout(function () { if (c) { try { c.focus({ preventScroll: true }); } catch (e) {} } }, reduced ? 0 : 450);
    });
  });

  // ---------------------------------------------------------------- галерея: активна мініатюра
  qsa(".gallery").forEach(function (g) {
    var track_ = qs(".g-track", g), thumbs = qsa(".g-thumb", g);
    if (!track_ || !thumbs.length) return;
    thumbs[0].setAttribute("aria-current", "true");
    thumbs.forEach(function (t, i) {
      t.addEventListener("click", function (e) {
        e.preventDefault();
        var slide = track_.children[i];
        if (slide) track_.scrollTo({ left: slide.offsetLeft - track_.offsetLeft, behavior: reduced ? "auto" : "smooth" });
      });
    });
    track_.addEventListener("scroll", function () {
      var w = track_.clientWidth || 1, i = Math.round(Math.abs(track_.scrollLeft) / w);
      thumbs.forEach(function (t, j) { if (j === i) t.setAttribute("aria-current", "true"); else t.removeAttribute("aria-current"); });
    }, { passive: true });
  });
  // 3D — модуль сесії моделей вантажиться лише на натискання
  qsa(".js-3d").forEach(function (b) {
    b.addEventListener("click", function () {
      var box = b.nextElementSibling, src = b.getAttribute("data-model");
      if (!box || !src) return;
      box.hidden = false; b.hidden = true;
      import(src).then(function (m) { var fn = m.mount || m.default; if (typeof fn === "function") fn(box); }, function () { box.hidden = true; b.hidden = false; });
    });
  });

  // ---------------------------------------------------------------- атрибуція і сесія для заявки
  var params = new URLSearchParams(location.search);
  var ATTR_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid"];
  function attribution() {
    var rec = null;
    try { rec = JSON.parse(localStorage.getItem("fx_attr") || "null"); } catch (e) { rec = null; }
    var fresh = {}, any = false;
    ATTR_KEYS.forEach(function (k) { var v = params.get(k); if (v) { fresh[k] = v; any = true; } });
    if (any && !(rec && rec.p && JSON.stringify(rec.p) === JSON.stringify(fresh))) {
      rec = { at: new Date().toISOString(), p: fresh };
      try { localStorage.setItem("fx_attr", JSON.stringify(rec)); } catch (e) {}
    }
    if (rec && rec.at && (Date.now() - Date.parse(rec.at)) > 30 * 864e5) rec = null;   // запис старший 30 днів не вживаємо
    return rec || { at: "", p: {} };
  }
  function sessionId() {
    var id = null;
    try { id = sessionStorage.getItem("fx_sid"); } catch (e) {}
    if (!id) {
      id = Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
      try { sessionStorage.setItem("fx_sid", id); } catch (e) {}
    }
    return id;
  }
  attribution();

  // ---------------------------------------------------------------- форма: перевірка і надсилання
  var PHONE_NATIONAL = /^(?:5\d{8}|[23489]\d{7}|7[2-9]\d{7})$/;
  function phoneOk(raw) {
    var d = String(raw || "").replace(/[^0-9]/g, "");
    if (!d || d.length > 15) return false;
    if (d.slice(0, 2) === "00") d = d.slice(2);
    var nat;
    if (d.slice(0, 3) === "972") nat = d.slice(3).replace(/^0+/, "");
    else if (d.charAt(0) === "0") nat = d.slice(1);
    else return d.length >= 8;            // іноземний номер — нехай вирішує сервер
    return PHONE_NATIONAL.test(nat);
  }
  if (form) {
    var status = qs(".f-status", form), btn = qs('button[type="submit"]', form), busy = false;
    var thanks = qs("[data-thanks]");
    var setErr = function (name, msg) {
      var input = form.elements[name], err = qs("#e-" + name, form);
      if (err) { err.textContent = msg || ""; err.hidden = !msg; }
      if (input && input.setAttribute) { if (msg) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid"); }
    };
    ["name", "phone", "consent"].forEach(function (n) {
      var el = form.elements[n];
      if (el) el.addEventListener(n === "consent" ? "change" : "input", function () { setErr(n, ""); });
    });
    var radio = function (n) { var el = qs('input[name="' + n + '"]:checked', form); return el ? el.value : ""; };
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (busy) return;
      var el = form.elements, attr = attribution(), ap = attr.p || {};
      var data = {
        name: (el.name.value || "").trim(), phone: (el.phone.value || "").trim(), city: (el.city.value || "").trim(),
        comment: (el.comment.value || "").trim(), website: el.website ? el.website.value : "",
        consent: !!el.consent.checked, consent_marketing: !!(el.consent_marketing && el.consent_marketing.checked),
        consent_text_version: DATA.consent || "v1", lang: DATA.lang || D.documentElement.lang,
        product_id: fProduct ? fProduct.value : "", size_label: fSize ? fSize.value : "",
        finish_id: fFinish ? fFinish.value : "", base_id: fBase ? fBase.value : "",
        timeframe: radio("timeframe"), contact_pref: radio("contact_pref"),
        session_id: sessionId(), page: location.pathname, referrer: D.referrer || "",
        device: W.matchMedia("(min-width: 900px)").matches ? "desktop" : "mobile",
        attributed_at: attr.at || ""
      };
      data.color = data.finish_id.slice(0, 40);
      data.size = data.size_label.replace(/[^0-9]/g, "").slice(0, 3);
      ATTR_KEYS.forEach(function (k) { data[k] = ap[k] || ""; });
      var bad = [];
      setErr("name", ""); setErr("phone", ""); setErr("consent", "");
      if (data.name.length < 2) { setErr("name", S.e_name); bad.push("name"); }
      if (!phoneOk(data.phone)) { setErr("phone", S.e_phone); bad.push("phone"); }
      if (!data.consent) { setErr("consent", S.e_consent); bad.push("consent"); }
      if (bad.length) {
        status.className = "f-status is-err"; status.textContent = S.invalid || "";
        var f = form.elements[bad[0]]; if (f && f.focus) f.focus();
        return;
      }
      var eventId = "";
      try { eventId = W.alumaEventId ? W.alumaEventId("lead") : ""; } catch (x) { eventId = ""; }
      if (eventId) data.event_id = eventId;
      busy = true; form.setAttribute("aria-busy", "true"); btn.disabled = true;
      status.className = "f-status"; status.textContent = S.sending || "";
      var unlock = function () { busy = false; form.removeAttribute("aria-busy"); btn.disabled = false; };
      fetch("/api/fx/lead", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(data) })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { code: r.status, body: b || {} }; }); })
        .then(function (res) {
          if (res.code === 200 && res.body.ok) {
            // приманка для ботів теж відповідає ok — це не конверсія
            if (res.body.id !== "hp") {
              var lp = { content_ids: data.product_id ? [data.product_id] : [], content_type: "product", currency: "ILS" };
              if (eventId) lp.event_id = eventId;
              track("Lead", lp);
            }
            form.hidden = true;
            if (thanks) { thanks.hidden = false; try { thanks.focus({ preventScroll: true }); } catch (x) {} thanks.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" }); }
            D.body.classList.add("is-registered");
            return;
          }
          unlock(); status.className = "f-status is-err";
          if (res.code === 429) status.textContent = S.rate || "";
          else if (res.code === 503 && res.body && res.body.error === "preview_only") status.textContent = S.preview || "";
          else if (res.code === 422 && res.body && res.body.errors) {
            Object.keys(res.body.errors).forEach(function (k) { setErr(k, S["e_" + k] || S.invalid); });
            status.textContent = S.invalid || "";
          } else status.textContent = S.fail || "";
        }, function () { unlock(); status.className = "f-status is-err"; status.textContent = S.offline || ""; });
    });
  }

  // ---------------------------------------------------------------- липка кнопка: після першого екрана, не над формою
  // Положення рахуємо на scroll (пасивно, раз на кадр): IntersectionObserver пропускає якір, якщо
  // швидкий свайп перестрибує його за один кадр, і кнопка не з'являлася.
  var sticky = qs("[data-sticky]");
  if (sticky) {
    var anchor = qs(".hero .actions") || qs(".pdp-actions"), reg = qs("#register"), foot = qs(".foot"), queued = false;
    var visible = function (el) { if (!el) return false; var r = el.getBoundingClientRect(); return r.top < W.innerHeight && r.bottom > 0; };
    var apply = function () {
      queued = false;
      var past = anchor ? anchor.getBoundingClientRect().bottom < 0 : W.scrollY > W.innerHeight;
      var on = past && !visible(reg) && !visible(foot) && !D.body.classList.contains("is-registered");
      sticky.hidden = false;
      sticky.classList.toggle("is-on", on);
      sticky.inert = !on;
      D.body.classList.toggle("has-sticky", on);
    };
    var schedule = function () { if (!queued) { queued = true; W.requestAnimationFrame(apply); } };
    W.addEventListener("scroll", schedule, { passive: true });
    W.addEventListener("resize", schedule, { passive: true });
    apply();
  }
})();
