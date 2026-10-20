/* ALUMA tracking.js — піксель Meta, Clarity і перша сторона (/api/fx/event) з налаштувань власника.
 * Контракт: specs/002-meta-settings/contracts/tracking.md. Конфіг — GET /api/fx/config (без збірки сайту).
 * Правила: немає pixel_id — жодного запиту до Meta; немає clarity_id — до Clarity; сторонній код —
 * лише після згоди (localStorage fx_notice_v1 = "1"); ?me=1 / cookie fx_me=1 — нічого не пишемо;
 * будь-яка помилка — тихо, сайт не ламається. Самодостатній файл, без залежностей. */
(function () {
  "use strict";
  if (window.alumaTrack) return;                       // підключено двічі — працює перший

  var doc = document, root = doc.documentElement;
  var LANG = /^en/i.test(root.getAttribute("lang") || "") ? "en" : "he";
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
    var payload = JSON.stringify({ session_id: SID, ctx: ctx, events: queue.splice(0, 40) });
    try {
      if (beacon && navigator.sendBeacon) { navigator.sendBeacon("/api/fx/event", new Blob([payload], { type: "application/json" })); return; }
      fetch("/api/fx/event", { method: "POST", headers: { "content-type": "application/json" }, body: payload, keepalive: true }).catch(function () {});
    } catch (e) {}
  }
  window.addEventListener("pagehide", function () { send(true); });

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
  function consented() { return store(NOTICE_KEY) === "1"; }
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

  function showNotice() {                              // власний мінімальний блок — лише коли на сторінці немає #notice
    if (doc.getElementById("notice") || doc.getElementById("aluma-notice")) return;
    var text = (SCRIPT && SCRIPT.getAttribute("data-notice")) ||
      (LANG === "en" ? "This site uses cookies for its operation and for statistical analysis of use."
                     : "האתר משתמש בעוגיות לתפעולו התקין ולניתוח סטטיסטי של השימוש בו.");
    var ok = (SCRIPT && SCRIPT.getAttribute("data-notice-ok")) || (LANG === "en" ? "Got it" : "הבנתי");
    var box = doc.createElement("div");
    box.id = "aluma-notice";
    box.setAttribute("role", "region");
    box.setAttribute("aria-label", ok);
    box.dir = LANG === "en" ? "ltr" : "rtl";
    box.lang = LANG;
    box.style.cssText = "position:fixed;inset-inline:12px;bottom:12px;z-index:2147483000;display:flex;gap:12px;" +
      "align-items:center;justify-content:space-between;padding:12px 16px;background:#1f1d1a;color:#f4efe6;" +
      "font:14px/1.4 system-ui,sans-serif;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.25);max-width:720px;margin-inline:auto";
    var p = doc.createElement("span");
    p.textContent = text;
    var btn = doc.createElement("button");
    btn.type = "button";
    btn.textContent = ok;
    btn.style.cssText = "flex:none;padding:8px 16px;border:0;border-radius:6px;background:#f4efe6;color:#1f1d1a;font:inherit;cursor:pointer";
    btn.addEventListener("click", function () { box.parentNode && box.parentNode.removeChild(box); window.alumaConsent(); });
    box.appendChild(p); box.appendChild(btn);
    (doc.body || root).appendChild(box);
  }

  var pageViewId = eventId("pv");
  function start() {
    if (isMe) return;
    if (!wantsThirdParty()) { pending = []; return; }  // без пікселя й Clarity — тиша
    if (consented()) { loadThirdParty(); return; }
    if (!doc.getElementById("notice")) {                // #notice веде вітрина й сама викликає alumaConsent()
      if (doc.body) showNotice(); else doc.addEventListener("DOMContentLoaded", showNotice);
    }
  }

  // ------------------------------------------------------------ публічне API
  window.alumaEventId = eventId;
  window.alumaConfig = loadConfig;
  window.alumaConsent = function () { store(NOTICE_KEY, "1"); loadThirdParty(); };
  window.alumaTrack = function (name, params) {
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
    if (queue.length >= 12) send(false);
    else { clearTimeout(flushTimer); flushTimer = setTimeout(function () { send(false); }, 2500); }
    var ev = { name: name, params: p, id: id };
    if (pixelOn) toPixel(ev);
    else if ((!config || wantsThirdParty()) && pending.length < 50) pending.push(ev);   // до конфігу/згоди — черга для пікселя
    return id;
  };

  window.alumaTrack("PageView", { event_id: pageViewId });
  loadConfig();
})();
