/* ALUMA tracking.js — піксель Meta, Clarity і перша сторона (/api/fx/event) з налаштувань власника.
 * Контракт: specs/002-meta-settings/contracts/tracking.md. Конфіг — GET /api/fx/config (без збірки сайту).
 * Правила: немає pixel_id — жодного запиту до Meta; немає clarity_id — до Clarity; сторонній код —
 * лише після згоди (localStorage fx_notice_v1 = "1"; "0" — «лише необхідні», більше не питаємо);
 * ?me=1 / cookie fx_me=1 — нічого не пишемо;
 * будь-яка помилка — тихо, сайт не ламається. Самодостатній файл, без залежностей. */
(function () {
  "use strict";
  if (window.alumaTrack) return;                       // підключено двічі — працює перший

  var doc = document, root = doc.documentElement;
  var LANG = (root.getAttribute("lang") || "he").slice(0, 2).toLowerCase();   // he | en | ru — як <html lang>
  var NOTICE_KEY = "fx_notice_v1";
  var STANDARD = ["PageView", "ViewContent", "Lead", "Contact", "CustomizeProduct", "Search", "AddToCart",
    "InitiateCheckout", "Schedule", "SubmitApplication", "CompleteRegistration", "FindLocation"];
  var SCRIPT = doc.currentScript;

  function store(key, val) {
    try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch (e) {}
    return null;
  }
  var params;
  try { params = new URLSearchParams(location.search); } catch (e) { params = { get: function () { return null; } }; }
  if (params.get("me") === "1") doc.cookie = "fx_me=1;path=/;max-age=31536000;samesite=lax";
  var isMe = /(^|;\s*)fx_me=1/.test(doc.cookie);

  // ------------------------------------------------------------ контекст, як у app-next.js
  var ctx = {
    page: location.pathname, landing_url: location.pathname + location.search, referrer: doc.referrer || "",
    device: window.matchMedia && window.matchMedia("(min-width: 832px)").matches ? "desktop" : "mobile",
    viewport: window.innerWidth + "x" + window.innerHeight, lang: LANG
  };
  var ATTR_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid"];
  (function attribution() {                            // той самий запис fx_attr: увесь набір або нічого
    var fresh = {}, any = false, rec = null;
    ATTR_KEYS.forEach(function (k) { var v = params.get(k); if (v) { fresh[k] = v; any = true; } });
    if (any) { rec = { at: new Date().toISOString(), p: fresh }; store("fx_attr", JSON.stringify(rec)); }
    else {
      try { rec = JSON.parse(store("fx_attr") || "null"); } catch (e) { rec = null; }
      if (rec && rec.at && (Date.now() - Date.parse(rec.at)) > 30 * 864e5) rec = null;
    }
    var p = (rec && rec.p) || {};
    ATTR_KEYS.forEach(function (k) { ctx[k] = p[k] || ""; });
    ctx.attributed_at = (rec && rec.at) || "";
  })();
  var SID = (function () {
    var id = null; try { id = sessionStorage.getItem("fx_sid"); } catch (e) {}
    if (!id) { id = Date.now().toString(36) + Math.random().toString(36).slice(2, 10); try { sessionStorage.setItem("fx_sid", id); } catch (e) {} }
    return id;
  })();

  function eventId(prefix) {
    var rnd = "";
    try { var a = new Uint32Array(2); crypto.getRandomValues(a); rnd = a[0].toString(36) + a[1].toString(36); }
    catch (e) { rnd = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2); }
    return (prefix || "ev") + "." + Date.now().toString(36) + "." + rnd.slice(0, 12);
  }

  // ------------------------------------------------------------ перша сторона: /api/fx/event
  var queue = [], flushTimer = null;
  function send(beacon) {
    if (!queue.length) return;
    var c = ctx;
    if (ctx.fbclid && !consented()) {                  // без згоди — жодного рекламного ідентифікатора
      c = {}; for (var k in ctx) c[k] = ctx[k];
      c.fbclid = "";
    }
    var payload = JSON.stringify({ session_id: SID, ctx: c, events: queue.splice(0, 40) });
    try {
      if (beacon && navigator.sendBeacon) { navigator.sendBeacon("/api/fx/event", new Blob([payload], { type: "application/json" })); return; }
      fetch("/api/fx/event", { method: "POST", headers: { "content-type": "application/json" }, body: payload, keepalive: true }).catch(function () {});
    } catch (e) {}
  }
  // leaving: подія після pagehide (leave зі shop.js) іде маяком одразу — таймер черги вже не спрацює
  var leaving = false;
  window.addEventListener("pagehide", function () { leaving = true; send(true); });
  window.addEventListener("pageshow", function () { leaving = false; });

  // ------------------------------------------------------------ конфіг
  var config = null, configPromise = null;
  function loadConfig() {
    if (configPromise) return configPromise;
    configPromise = (window.fetch ? fetch("/api/fx/config", { credentials: "same-origin" }) : Promise.reject())
      .then(function (r) { return r.ok ? r.json() : {}; })
      .catch(function () { return {}; })
      .then(function (c) {
        config = c && typeof c === "object" ? c : {};
        try { doc.dispatchEvent(new CustomEvent("aluma:config", { detail: config })); } catch (e) {}
        start();
        return config;
      });
    return configPromise;
  }

  // ------------------------------------------------------------ сторонній код після згоди
  var pending = [], pixelOn = false, clarityOn = false;
  function consentState() { var v = store(NOTICE_KEY); return v === "1" ? "granted" : v === "0" ? "denied" : null; }
  function consented() { return consentState() === "granted"; }
  function wantsThirdParty() { return !!(config && (config.pixel_id || config.clarity_id)); }

  function loadPixel(id) {
    if (pixelOn || !/^\d{6,20}$/.test(String(id))) return;
    pixelOn = true;
    if (!window.fbq) {
      /* eslint-disable */
      !function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};
      if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}
      (window,doc,'script','https://connect.facebook.net/en_US/fbevents.js');
      /* eslint-enable */
    }
    try { window.fbq("init", String(id)); } catch (e) {}
  }
  function loadClarity(id) {
    if (clarityOn || !/^[a-z0-9]{6,20}$/i.test(String(id))) return;
    clarityOn = true;
    /* eslint-disable */
    (function(c,l,a,r,i,t,y){c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y)})(window,doc,"clarity","script",String(id));
    /* eslint-enable */
  }
  function toPixel(ev) {
    if (!pixelOn || !window.fbq) return;
    try { window.fbq(STANDARD.indexOf(ev.name) >= 0 ? "track" : "trackCustom", ev.name, ev.params, { eventID: ev.id }); } catch (e) {}
  }
  function loadThirdParty() {
    if (isMe || !config || !consented()) return;
    if (config.pixel_id) loadPixel(config.pixel_id);
    if (config.clarity_id) loadClarity(config.clarity_id);
    var list = pending; pending = [];
    list.forEach(toPixel);
  }

  // Тексти — i18n/legal.<lang>.json → cookies (вітрина може передати свої через data-атрибути тега <script>).
  var TEXT = {
    he: {"label": "הודעת עוגיות", "text": "עוגיות הכרחיות פועלות תמיד. Meta Pixel ו־Microsoft Clarity רק באישור, למדידת פרסום ולשיפור האתר. ניתן לשנות.", "accept": "אישור", "decline": "רק הכרחיות", "more": "מדיניות הפרטיות"},
    en: {"label": "Cookie notice", "text": "Essential cookies always on; Meta Pixel and Microsoft Clarity (ad and site stats) only if you accept. Changeable.", "accept": "Accept", "decline": "Essential only", "more": "Privacy policy"},
    ru: {"label": "Уведомление о cookie", "text": "Необходимые cookie — всегда; Meta Pixel, Microsoft Clarity — по согласию. Можно изменить.", "accept": "Принять", "decline": "Только необходимые", "more": "Политика конфиденциальности"}
  };
  function attr(name) { return (SCRIPT && SCRIPT.getAttribute(name)) || ""; }
  function hideNotice() { var b = doc.getElementById("aluma-notice"); if (b && b.parentNode) b.parentNode.removeChild(b); }
  function showNotice() {                              // власний блок — лише коли на сторінці немає #notice
    if (doc.getElementById("notice") || doc.getElementById("aluma-notice")) return;
    var t = TEXT[LANG] || TEXT.en;
    var box = doc.createElement("div");
    box.id = "aluma-notice";
    box.setAttribute("role", "region");
    box.setAttribute("aria-label", attr("data-notice-label") || t.label);
    box.dir = LANG === "he" ? "rtl" : "ltr";
    box.lang = TEXT[LANG] ? LANG : "en";
    box.style.cssText = "position:fixed;inset-inline:12px;bottom:12px;z-index:2147483000;display:flex;flex-wrap:wrap;gap:8px 12px;" +
      "align-items:center;padding:12px 16px;background:#1f1d1a;color:#f4efe6;" +
      "font:14px/1.4 system-ui,sans-serif;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.25);max-width:720px;margin-inline:auto";
    var p = doc.createElement("span");
    p.textContent = attr("data-notice") || t.text;
    p.style.cssText = "flex:1 1 260px";
    function button(label, primary, choice) {
      var b = doc.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.style.cssText = "flex:none;padding:8px 16px;border-radius:6px;font:inherit;cursor:pointer;min-height:44px;" +
        (primary ? "border:0;background:#f4efe6;color:#1f1d1a" : "border:1px solid #f4efe6;background:transparent;color:#f4efe6");
      b.addEventListener("click", function () { window.alumaConsent(choice); });
      return b;
    }
    box.appendChild(p);
    box.appendChild(button(attr("data-notice-ok") || t.accept, true, true));
    box.appendChild(button(attr("data-notice-decline") || t.decline, false, false));
    var a = doc.createElement("a");
    a.href = attr("data-privacy-href") || (LANG === "he" ? "/privacy" : "/" + LANG + "/privacy");
    a.textContent = attr("data-notice-more") || t.more;
    a.style.cssText = "color:#f4efe6;text-decoration:underline";
    box.appendChild(a);
    (doc.body || root).appendChild(box);
  }

  var pageViewId = eventId("pv");
  function start() {
    if (isMe) return;
    if (!wantsThirdParty()) { pending = []; return; }  // без пікселя й Clarity — тиша
    if (consented()) { loadThirdParty(); return; }
    if (consentState() === "denied") { pending = []; return; }   // «лише необхідні» — не питаємо знову
    if (!doc.getElementById("notice")) {                // #notice веде вітрина й сама викликає alumaConsent()
      if (doc.body) showNotice(); else doc.addEventListener("DOMContentLoaded", showNotice);
    }
  }

  // ------------------------------------------------------------ публічне API
  window.alumaEventId = eventId;
  window.alumaConfig = loadConfig;
  // alumaConsent() / alumaConsent(true) — згода; alumaConsent(false) — «лише необхідні» або відкликання
  // (уже завантажений піксель живе до кінця сторінки, з наступної — нічого); alumaConsentReset() — спитати знову.
  window.alumaConsent = function (choice) {
    var yes = choice === undefined || choice === true || choice === "granted";
    store(NOTICE_KEY, yes ? "1" : "0");
    hideNotice();
    if (yes) loadThirdParty(); else pending = [];
    try { doc.dispatchEvent(new CustomEvent("aluma:consent", { detail: consentState() })); } catch (e) {}
  };
  window.alumaConsentState = consentState;
  window.alumaConsentReset = function () {
    try { localStorage.removeItem(NOTICE_KEY); } catch (e) {}
    if (config) start(); else loadConfig();
  };
  // opts.pixel === false — лише в нашу аналітику (scroll, leave): Meta ці події не потрібні
  window.alumaTrack = function (name, params, opts) {
    name = String(name || "").slice(0, 60);
    if (!name) return "";
    var p = {}, k;
    if (params && typeof params === "object") for (k in params) if (Object.prototype.hasOwnProperty.call(params, k)) p[k] = params[k];
    var id = typeof p.event_id === "string" && /^[A-Za-z0-9_.-]{8,64}$/.test(p.event_id) ? p.event_id : eventId(name.toLowerCase().slice(0, 12));
    delete p.event_id;
    if (isMe) return id;
    var props = {}; for (k in p) props[k] = p[k];
    props.event_id = id;
    queue.push({ name: name, props: props, ts: new Date().toISOString(), page: ctx.page });
    if (leaving) send(true);
    else if (queue.length >= 12) send(false);
    else { clearTimeout(flushTimer); flushTimer = setTimeout(function () { send(false); }, 2500); }
    var ev = { name: name, params: p, id: id };
    if (opts && opts.pixel === false) return id;
    if (pixelOn) toPixel(ev);
    else if ((!config || wantsThirdParty()) && pending.length < 50) pending.push(ev);   // до конфігу/згоди — черга для пікселя
    return id;
  };

  window.alumaTrack("PageView", { event_id: pageViewId });
  // події, які aluma.js надіслав до завантаження цього файлу
  var early = window.alumaQ || []; window.alumaQ = [];
  for (var qi = 0; qi < early.length; qi++) try { window.alumaTrack(early[qi][0], early[qi][1], early[qi][2]); } catch (e) {}
  loadConfig();
})();
