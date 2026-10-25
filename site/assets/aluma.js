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
  // tracking.js вантажиться після load: подію до нього (ViewContent при старті) кладемо в чергу alumaQ, він її програє
  var track = function (name, params, opts) {
    try { if (W.alumaTrack) return W.alumaTrack(name, params || {}, opts); (W.alumaQ = W.alumaQ || []).push([name, params || {}, opts]); } catch (e) {}
    return "";
  };
  // сторінка 404: шлях без query — у нашу аналітику (сторож журналу рахує повтори), Meta не потрібна
  if (qs("[data-not-found]")) track("NotFound", { path: location.pathname.slice(0, 200) }, { pixel: false });
  var byId = function (id) { for (var i = 0; i < PRODUCTS.length; i++) if (PRODUCTS[i].id === id) return PRODUCTS[i]; return null; };
  // ціна як у build.py money(): «₪4,490»; у ru — «4 490 ₪» з нерозривними пробілами
  var money = function (n) {
    var s = Number(n || 0).toLocaleString("en-US");
    return D.documentElement.lang === "ru" ? s.replace(/,/g, "\u00a0") + "\u00a0₪" : "₪" + s;
  };

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
  // opt-out (docs/COMPLIANCE-IL.md §3): без запису Pixel/Clarity працюють, банер про це каже й питає;
  // "1" — «אישור», "0" — «רק הכרחיות»: tracking.js одразу відкликає згоду в Meta/Clarity, без перезавантаження.
  var notice = qs("#notice");
  var NOTICE_KEY = "fx_notice_v1";
  var choice = null;
  try { choice = localStorage.getItem(NOTICE_KEY); } catch (e) {}
  // --dock: скільки знизу екрана зараз займають банер і липка смуга — кнопка נגישות стоїть над ними, не перекриває
  var dock = function () {
    var top = W.innerHeight, st = qs("[data-sticky]");
    var stOn = st && st.classList.contains("is-on") && st.offsetHeight;
    // висота разом із відступом знизу (липка «пігулка» в картці стоїть не впритул до краю)
    var stH = stOn ? st.offsetHeight + (parseFloat(getComputedStyle(st).bottom) || 0) : 0;
    D.documentElement.style.setProperty("--sticky-h", stH + "px");
    top -= stH;   // не getBoundingClientRect: смуга ще їде transform-ом
    // на десктопі банер — картка в протилежному куті, кнопку не піднімаємо
    if (notice && !notice.hidden && !notice.classList.contains("is-away") && notice.offsetWidth > W.innerWidth * .8) top = Math.min(top, notice.getBoundingClientRect().top);
    D.documentElement.style.setProperty("--dock", Math.max(0, Math.round(W.innerHeight - top)) + "px");
  };
  W.addEventListener("resize", function () { dock(); }, { passive: true });
  var shown = false;   // банер уже показано або вибір зроблено — відкладений показ не спрацьовує
  var showNotice = function () { if (notice) { shown = true; notice.hidden = false; dock(); var b = qs("[data-notice-ok]", notice); if (b) b.focus({ preventScroll: true }); } };
  if (notice) {
    // показ — коли шрифти вже на місці (не довше 1,5 с): банер прибитий до низу, і підміна шрифту
    // переносила рядки тексту — зсув рахувався в CLS (0,046 на проді). Поява нового елемента — не зсув.
    if (choice !== "1" && choice !== "0") {
      var reveal = function () { if (!shown) { shown = true; notice.hidden = false; dock(); } };
      var whenFonts = function () { if (D.fonts && D.fonts.ready) { D.fonts.ready.then(reveal, reveal); setTimeout(reveal, 1500); } else reveal(); };
      // телефон і планшет (банер на всю ширину, < 900 px): перший екран картки — кадр, ціна й кнопки, а не банер.
      // Показ — після першої прокрутки або через 6 с, що раніше (24.10). Згода не змінюється: без «אישור» пікселя нема.
      // №15: ≤ 380 px — лише після прокрутки, без таймера. І на картці банер не з'являється, поки накрив би
      // пару кнопок чи «התקשרו»: заміри 24.10 — банер на 360 займає 79–102 px знизу, на 390 — від 765 px, а «התקשרו»
      // стоїть на 756–815. Тоді чекаємо наступної прокрутки, доки трійка не підніметься над зоною банера.
      var NOTICE_ZONE = 130;   // px знизу: найвищий банер (ru, 360 px) — 102 px, із запасом
      var clear = function () {   // трійка вся над зоною банера або вся нижче екрана
        var c = qs(".pdp-actions [data-call]"), p = qs(".pdp-pair");
        if (!c || !p || !c.offsetHeight) return true;
        return c.getBoundingClientRect().bottom <= W.innerHeight - NOTICE_ZONE || p.getBoundingClientRect().top >= W.innerHeight;
      };
      if (W.matchMedia && W.matchMedia("(max-width: 899px)").matches) {
        var later = function () { if (!clear()) return; W.removeEventListener("scroll", later); clearTimeout(timer); whenFonts(); };
        var timer = W.matchMedia("(max-width: 380px)").matches ? 0 : setTimeout(later, 6000);
        W.addEventListener("scroll", later, { passive: true });
      } else whenFonts();
    }
    dock();
    // вибір пише tracking.js (alumaConsent); без нього — сам ключ, щоб банер не питав знову
    var choose = function (yes) {
      shown = true;
      notice.hidden = true;
      dock();
      if (W.alumaConsent) { try { W.alumaConsent(yes); } catch (e) {} }
      else { try { localStorage.setItem(NOTICE_KEY, yes ? "1" : "0"); } catch (e) {} }
    };
    var okBtn = qs("[data-notice-ok]", notice), noBtn = qs("[data-notice-no]", notice);
    if (okBtn) okBtn.addEventListener("click", function () { choose(true); });
    if (noBtn) noBtn.addEventListener("click", function () { choose(false); });
    // телефон: банер на всю ширину накрив би поле у фокусі — ховаємо, поки фокус у формі
    qsa("[data-form]").forEach(function (form) {
      form.addEventListener("focusin", function () {
        if (!notice.hidden && notice.offsetWidth > W.innerWidth * .8) { notice.classList.add("is-away"); dock(); }
      });
      form.addEventListener("focusout", function (e) {
        if (form.contains(e.relatedTarget)) return;
        notice.classList.remove("is-away"); dock();
      });
    });
  }
  qsa("[data-cookie-settings]").forEach(function (b) { b.addEventListener("click", function () {
    try { if (W.alumaConsentReset) W.alumaConsentReset(); } catch (e) {}
    showNotice();
  }); });
  var adsConsent = function () {
    try { if (W.alumaConsentState) return W.alumaConsentState() !== "denied"; } catch (e) {}   // opt-out: без вибору = згода
    try { return localStorage.getItem(NOTICE_KEY) !== "0"; } catch (e) { return false; }
  };

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
    // юридичні сторінки (legal.*.json): плейсхолдери з конфігу; абзац показуємо, лише коли є всі його значення
    var lv = {
      company_name: c.name, business_id: c.business_id, address: c.address || c.city, phone: c.phone, email: c.email,
      a11y_name: ac.name || c.name, a11y_phone: ac.phone || c.phone, a11y_email: ac.email || c.email,
      court_city: cfg.court_city || c.court_city
    };
    qsa("[data-lv]").forEach(function (el) { var v = lv[el.getAttribute("data-lv")]; if (v) el.textContent = v; });
    qsa("[data-lneed]").forEach(function (el) {
      el.hidden = !el.getAttribute("data-lneed").split(" ").every(function (k) { return !!lv[k]; });
    });
    qsa("[data-lsec]").forEach(function (sec) {
      var kids = qsa("p, li", sec);
      sec.hidden = kids.length > 0 && kids.every(function (k) { return k.hidden; });
    });
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
  var form = qs("#lead-form");
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

  // ---------------------------------------------------------------- «בוקר / ערב»: перемикаємо шар, приховане — aria-hidden
  qsa("[data-light]").forEach(function (b) {
    b.addEventListener("click", function () {
      var k = b.getAttribute("data-light"), fig = qs("[data-light-fig]");
      if (!fig) return;
      fig.setAttribute("data-on", k);
      qsa(".light-l", fig).forEach(function (l) { l.setAttribute("aria-hidden", l.getAttribute("data-l") === k ? "false" : "true"); });
      qsa("[data-light]").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
    });
  });

  // ---------------------------------------------------------------- конфігуратор картки товару
  var pdp = qs("[data-pdp]"), config = qs("[data-config]");
  if (pdp) {
    var P = currentProduct();
    var priceEl = qs(".price[data-price] bdi"), mini = qs("[data-price-mini]"), finishName = qs("[data-finish-name]");
    // розстрочка (24.10): «≈ ₪375/חודש» — ціна розміру / INSTALLMENTS, вгору до шекеля, як build.py P_MONTHLY
    var monthly = qs("[data-monthly]"), payN = parseInt((qs("[data-installments]") || { getAttribute: function () { return ""; } }).getAttribute("data-installments"), 10);
    var val = function (n) { var el = qs('input[name="' + n + '"]:checked', config || D); return el ? el.value : ""; };
    var syncAll = function () {
      if (P) syncFormProduct(P.id, val("size"), val("finish"), val("base"));
    };
    // план «סגור / פתוח» — лише для вибраного розміру
    var showPlan = function (v) {
      var all = qsa("[data-plan-size]"), hit = false, i;
      for (i = 0; i < all.length; i++) if (all[i].getAttribute("data-plan-size") === v) hit = true;
      if (hit) for (i = 0; i < all.length; i++) all[i].hidden = all[i].getAttribute("data-plan-size") !== v;
    };
    var updatePrice = function () {
      var sz = qs('input[name="size"]:checked', config || D);
      if (sz && sz.getAttribute("data-price")) {
        var m = money(sz.getAttribute("data-price"));
        if (priceEl) priceEl.textContent = m;
        if (mini) mini.textContent = m;
        if (monthly && payN > 0) monthly.textContent = "≈\u00a0" + money(Math.ceil(Number(sz.getAttribute("data-price")) / payN));
      }
    };
    if (config) config.addEventListener("change", function (e) {
      var t = e.target;
      if (t.name === "finish" && finishName) finishName.textContent = t.getAttribute("data-name") || "";
      updatePrice();
      syncAll();
      if (t.name === "size") showPlan(t.value);
      // кожен вибір — окремий крок воронки (specs/003): select_size / select_finish / select_base
      if (P && /^(size|finish|base)$/.test(t.name)) track("select_" + t.name, { content_ids: [P.id], content_type: "product", size: val("size"), finish: val("finish"), base: val("base") });
    });
    updatePrice();
    syncAll();
    showPlan(val("size"));
    if (P) {
      var first = P.sizes[0];
      track("ViewContent", { content_ids: [P.id], content_type: "product", content_name: P.name, value: first ? first.price : P.from, currency: "ILS" });
    }
  }
  // ---------------------------------------------------------------- картка: м'який крок «שאלה? נחזור אליכם»
  // [data-ask] біля «הוספה לסל» і в липкій панелі + «השאירו פרטים» під ціною → форма #register з цим столом.
  // cta_ask — лише в нашу аналітику (воронка: «вопрос с карточки»), Meta не потрібна. Форми нема — кнопок теж.
  var asks = qsa("[data-ask], .pdp-ask"), reg0 = qs("#register"), fName = form && qs("#f-name", form);
  if (asks.length && !(reg0 && form)) asks.forEach(function (b) { b.hidden = true; });
  else asks.forEach(function (b) {
    b.addEventListener("click", function (e) {
      e.preventDefault();
      var cur = pdp && currentProduct();
      if (cur && fProduct && !fProduct.value) syncFormProduct(cur.id);
      if (cur) track("cta_ask", { content_ids: [cur.id], content_type: "product", cta: b.getAttribute("data-cta") || "" }, { pixel: false });
      reg0.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
      setTimeout(function () { if (fName) { try { fName.focus({ preventScroll: true }); } catch (x) {} } }, reduced ? 0 : 450);
    });
  });
  // ---------------------------------------------------------------- картка: «התקשרו אלינו» — номера нема, є зворотний дзвінок
  // [data-call] під парою кнопок і іконка в липкій смузі → міні-форма #callback (телефон + згода, lead_source=callback).
  // №20: «що вам зручно» — дзвінок, відеодзвінок або «надішліть деталі» (тоді e-mail або телефон, хоч один).
  // cta_call — лише в нашу аналітику (воронка: «позвоните нам»), Meta не потрібна.
  var calls = qsa("[data-call]"), cbForm = qs("#callback"), cbMain = qs('.pdp-call[data-call]');
  if (calls.length && !cbForm) calls.forEach(function (b) { b.hidden = true; });
  else calls.forEach(function (b) {
    b.addEventListener("click", function () {
      var cur = pdp && currentProduct();
      if (cur && fProduct && !fProduct.value) syncFormProduct(cur.id);
      if (cur) track("cta_call", { content_ids: [cur.id], cta: b.getAttribute("data-cta") || "" }, { pixel: false });
      var done = qs("[data-callback-thanks]");
      if (done && !done.hidden) { done.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" }); return; }
      var open = b !== cbMain || cbForm.hidden;           // кнопка картки — перемикач; іконка смуги лише відкриває
      cbForm.hidden = !open;
      if (cbMain) cbMain.setAttribute("aria-expanded", String(open));
      if (!open) return;
      cbForm.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
      var ph = cbForm.elements.phone;
      setTimeout(function () { if (ph) { try { ph.focus({ preventScroll: true }); } catch (x) {} } }, reduced ? 0 : 450);
    });
  });
  if (cbForm) {
    var cbPref = function () { var x = qs('input[name="contact_pref"]:checked', cbForm); return x ? x.value : "call"; };
    var cbSync = function () {
      var pref = cbPref(), info = pref === "info";
      qsa("[data-pref-hint]", cbForm).forEach(function (h) { h.hidden = h.getAttribute("data-pref-hint") !== pref; });
      var em = qs("[data-cb-email]", cbForm), opt = qs("[data-phone-opt]", cbForm);
      if (em) em.hidden = !info;
      if (opt) opt.hidden = !info;
      if (cbForm.elements.phone) { if (info) cbForm.elements.phone.removeAttribute("required"); else cbForm.elements.phone.setAttribute("required", ""); }
    };
    qsa('input[name="contact_pref"]', cbForm).forEach(function (r) { r.addEventListener("change", cbSync); });
    cbSync();
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
  // 3D — three.js і модель вантажаться лише на натискання; помилка — коротким текстом у .viewer3d, не тишею (21.10)
  var scriptP = {};
  function loadScript(src) {
    if (!scriptP[src]) {
      scriptP[src] = new Promise(function (resolve, reject) {
        var s = D.createElement("script"); s.src = src; s.async = true;
        s.onload = resolve;
        s.onerror = function () { delete scriptP[src]; s.remove(); reject(new Error("script")); };
        D.head.appendChild(s);
      });
    }
    return scriptP[src];
  }
  qsa(".js-3d").forEach(function (b) {
    var box = qs("#" + b.getAttribute("aria-controls")), src = b.getAttribute("data-model");
    if (!box || !src) return;
    var msg = qs(".v3d-msg", box), states = qsa(".v3d-st", box), view = null, stage = null, state = "closed";
    var P3 = currentProduct();
    var cfg = qs("[data-config]");
    var val = function (n) { var el = cfg && qs('input[name="' + n + '"]:checked', cfg); return el ? el.value : ""; };
    var size = function () {
      var v = val("size"), s = P3 && (P3.sizes.filter(function (x) { return x.label === v; })[0] || P3.sizes[0]);
      return s ? s.dims : null;
    };
    var say = function (t) { if (msg) { msg.textContent = t || ""; msg.hidden = !t; } };
    var paintStates = function () { states.forEach(function (x) { x.setAttribute("aria-pressed", String(x.getAttribute("data-state") === state)); }); };
    function close() {
      if (view) view.dispose();
      view = null;
      if (stage) stage.remove();
      stage = null; say("");
      box.hidden = true; b.hidden = false; b.setAttribute("aria-expanded", "false");
      b.focus();
    }
    function open() {
      box.hidden = false; b.hidden = true; b.setAttribute("aria-expanded", "true");
      say(S.v3d_loading);
      stage = D.createElement("div"); stage.className = "v3d-stage";
      var old = qs(".v3d-stage", box);
      if (old) box.replaceChild(stage, old); else box.insertBefore(stage, box.firstChild);
      var mine = stage, sz = size() || {}, fin = cfg && qs('input[name="finish"]:checked', cfg);
      var desc = (P3 ? P3.name : "") + " " + (val("size") || "") + (fin ? ", " + (fin.getAttribute("data-name") || "") : "");
      loadScript(src).then(function () {
        if (!W.Aluma3D) throw new Error("model");
        return W.Aluma3D.mount(mine, { product: P3 ? P3.id : "", size: sz, finish: val("finish") || "natural",
          base: val("base") || "oak", state: state, label: P3 ? P3.name : "", description: desc,
          keysText: S.v3d_keys, roleText: S.v3d_role });
      }).then(function (v) {
        if (stage !== mine) { v.dispose(); return; }   // закрили, поки вантажилось
        view = v; say("");
        mine.focus({ preventScroll: true });
      }, function (e) {
        if (stage !== mine) return;
        stage = D.createElement("div"); stage.className = "v3d-stage"; box.replaceChild(stage, mine);   // порожнє місце під текст
        say(e && e.message === "webgl" ? S.v3d_err_webgl : S.v3d_err);
      });
    }
    b.addEventListener("click", open);
    var x = qs(".v3d-close", box);
    if (x) x.addEventListener("click", close);
    box.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
    states.forEach(function (s) {
      s.addEventListener("click", function () {
        state = s.getAttribute("data-state"); paintStates();
        if (view) view.setState(state);
      });
    });
    // вибір на сторінці — одразу в перегляді: тон без перебудови, розмір і опори — перебудова моделі
    if (cfg) cfg.addEventListener("change", function (e) {
      var t = e.target;
      if (!view || !t || t.type !== "radio") return;
      if (t.name === "finish") view.setFinish(t.value);
      else if (t.name === "size") view.setSize(size());
      else if (t.name === "base") view.setBase(t.value);
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
  var EMAIL_OK = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/;   // той самий шаблон, що LEAD_EMAIL у handler.py
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
  // повна форма (#lead-form): питання про розмір або тон
  function wireForm(form) {
    var status = qs(".f-status", form), btn = qs('button[type="submit"]', form), busy = false;
    var callback = form.getAttribute("data-source") === "callback", main = qs("#lead-form");
    var thanks = form.id === "lead-form" ? qs("[data-thanks]") : callback ? qs("[data-callback-thanks]") : qs(".thanks", form.parentNode);
    var pre = form.getAttribute("data-err") || "";
    var setErr = function (name, msg) {
      var input = form.elements[name], err = qs("#" + pre + "e-" + name, form);
      if (err) { err.textContent = msg || ""; err.hidden = !msg; }
      if (input && input.setAttribute) { if (msg) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid"); }
    };
    ["name", "phone", "email", "consent"].forEach(function (n) {
      var el = form.elements[n];
      if (el) el.addEventListener(n === "consent" ? "change" : "input", function () { setErr(n, ""); });
    });
    var radio = function (n) { var el = qs('input[name="' + n + '"]:checked', form); return el ? el.value : ""; };
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (busy) return;
      var el = form.elements, attr = attribution(), ap = attr.p || {};
      var fv = function (n) { var x = el[n]; return x && x.value ? String(x.value).trim() : ""; };
      // дзвінок з картки: який стіл і розмір — з основної форми, яку синхронізує конфігуратор
      var pv = function (n) { var x = callback && main ? main.elements[n] : el[n]; return x && x.value ? String(x.value).trim() : ""; };
      var data = {
        name: fv("name"), phone: fv("phone"), city: fv("city"), comment: fv("comment"), website: el.website ? el.website.value : "",
        consent: !!el.consent.checked, consent_marketing: !!(el.consent_marketing && el.consent_marketing.checked),
        marketing_consent: !!(el.consent_marketing && el.consent_marketing.checked), ads_consent: adsConsent(),
        consent_text_version: DATA.consent || "v1", lang: DATA.lang || D.documentElement.lang,
        product_id: pv("product_id"), size_label: pv("size_label"), finish_id: pv("finish_id"), base_id: pv("base_id"),
        timeframe: radio("timeframe"), contact_pref: radio("contact_pref"),
        session_id: sessionId(), page: location.pathname, referrer: D.referrer || "",
        device: W.matchMedia("(min-width: 900px)").matches ? "desktop" : "mobile",
        attributed_at: attr.at || ""
      };
      data.color = data.finish_id.slice(0, 40);
      data.size = data.size_label.replace(/[^0-9]/g, "").slice(0, 3);
      ATTR_KEYS.forEach(function (k) { data[k] = ap[k] || ""; });
      if (callback) {
        data.lead_source = "callback";
        data.contact_pref = data.contact_pref || "call";
        data.preferred_time = fv("preferred_time").slice(0, 80);
        if (data.contact_pref === "info") data.email = fv("email").slice(0, 120);
      }
      // спосіб отримання, якщо вже вибрали в кошику (shop.js, fx_ship_v1); нового поля у формі нема
      try { var way = sessionStorage.getItem("fx_ship_v1"); if (way === "pickup" || way === "door") data.delivery = way; } catch (x) {}
      var bad = [];
      setErr("name", ""); setErr("phone", ""); setErr("email", ""); setErr("consent", "");
      if (!callback && data.name.length < 2) { setErr("name", S.e_name); bad.push("name"); }
      if (callback && data.contact_pref === "info") {
        // «деталі»: e-mail або телефон — хоч один, і кожен заповнений має бути правильним
        if (!data.phone && !data.email) { setErr("phone", S.e_contact); bad.push("phone"); }
        if (data.phone && !phoneOk(data.phone)) { setErr("phone", S.e_phone); bad.push("phone"); }
        if (data.email && !EMAIL_OK.test(data.email)) { setErr("email", S.e_email); bad.push("email"); }
      } else if (!phoneOk(data.phone)) { setErr("phone", S.e_phone); bad.push("phone"); }
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
            if (callback && cbMain) cbMain.setAttribute("aria-expanded", "false");
            if (thanks) { thanks.hidden = false; try { thanks.focus({ preventScroll: true }); } catch (x) {} thanks.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" }); }
            if (!callback) D.body.classList.add("is-registered");
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
  if (form) wireForm(form);
  if (cbForm) wireForm(cbForm);

  // ---------------------------------------------------------------- липка кнопка: після якоря, не над формою, не з банером
  // Положення рахуємо на scroll (пасивно, раз на кадр): IntersectionObserver пропускає якір, якщо
  // швидкий свайп перестрибує його за один кадр, і кнопка не з'являлася.
  var sticky = qs("[data-sticky]");
  if (sticky) {
    // якір — кнопки hero на головній, «הוספה לסל» у картці: смуга лише коли якір пішов за верх екрана. До нього — ні:
    // перший екран картки на телефоні — плитки розмірів, а не смуга над ними (аудит 22.10, (б) 5)
    var anchor = qs(".hero .actions") || qs(".pdp-actions"), reg = qs("#register"), foot = qs(".foot"), queued = false;
    var visible = function (el) { if (!el) return false; var r = el.getBoundingClientRect(); return r.top < W.innerHeight && r.bottom > 0; };
    // банер згоди відкритий — смуги немає: удвох вони закривали третину екрана над розмірами (аудит 22.10)
    var noticeOpen = function () { return !!notice && !notice.hidden && !notice.classList.contains("is-away"); };
    var apply = function () {
      queued = false;
      var past = anchor ? anchor.getBoundingClientRect().bottom < 0 : W.scrollY > W.innerHeight;
      var on = past && !noticeOpen() && !visible(reg) && !visible(foot) && !D.body.classList.contains("is-registered");
      sticky.hidden = false;
      sticky.classList.toggle("is-on", on);
      sticky.inert = !on;
      D.body.classList.toggle("has-sticky", on);
      dock();
    };
    var schedule = function () { if (!queued) { queued = true; W.requestAnimationFrame(apply); } };
    W.addEventListener("scroll", schedule, { passive: true });
    W.addEventListener("resize", schedule, { passive: true });
    // банер з'являється після шрифтів, ховається на вибір — межа «вся на екрані» зсувається без прокрутки
    if (notice && W.MutationObserver) new MutationObserver(schedule).observe(notice, { attributes: true, attributeFilter: ["hidden", "class"] });
    apply();
  }

  // ---------------------------------------------------------------- глави картки: aria-current на главі під шапкою
  // IntersectionObserver лише будить перерахунок; поточна — остання глава, чий верх уже вище лінії 40 % екрана
  var chap = qs("[data-chapters]");
  if (chap && "IntersectionObserver" in W) {
    var ol = qs("ol", chap), cur = null, links = qsa("a", chap), secs = links.map(function (a) { return D.getElementById(a.hash.slice(1)); });
    var mark = function () {
      var line = W.innerHeight * .4, a = null;
      secs.forEach(function (s, i) { if (s && s.getBoundingClientRect().top < line) a = links[i]; });
      if (a === cur) return;
      if (cur) cur.removeAttribute("aria-current");
      cur = a;
      if (!a) return;
      a.setAttribute("aria-current", "location");
      // активна пігулка — у полі зору смуги (на телефоні смуга гортається вбік)
      var r = a.getBoundingClientRect(), o = ol.getBoundingClientRect();
      if (r.left < o.left || r.right > o.right) ol.scrollBy({ left: r.left - o.left - (o.width - r.width) / 2, behavior: reduced ? "auto" : "smooth" });
    };
    // шапка з рядком «סדרת השקה» вища за 64 px і різна на he/en: смуга глав стає рівно під неї, якорі — під обидві
    var top = qs(".top"), fit = function () {
      var h = top ? top.getBoundingClientRect().height : 64;
      chap.style.top = h + "px";
      D.documentElement.style.scrollPaddingTop = h + chap.getBoundingClientRect().height + "px";
    };
    fit(); W.addEventListener("resize", fit, { passive: true });
    var io = new IntersectionObserver(mark, { rootMargin: "-40% 0px -59% 0px" });
    secs.forEach(function (s) { if (s) io.observe(s); });
    mark();
  }
})();
