/* ALUMA / GOREN — page behaviour. One file for both locales: every user-visible string and
   every asset URL comes from window.FX (embedded per page at build time), so the script never
   assembles a path by convention and content-hashed filenames stay correct. No third-party
   code loads until the visitor accepts the notice, and the notice only exists when a
   third-party id is configured. */
(function () {
  "use strict";
  var S = window.FX || {};
  var CFG = S.cfg || {};
  var ASSETS = S.assets || {};
  var root = document.documentElement;
  var LANG = root.getAttribute("lang") || "he";
  var qs = function (s, c) { return (c || document).querySelector(s); };
  var qsa = function (s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); };
  var fmt = function (s, vars) { return String(s || "").replace(/\{\{(\w+)\}\}/g, function (_, k) { return vars[k] != null ? vars[k] : ""; }); };
  var num = function (n) { return '<span class="num">' + n + '</span>'; };
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------------------------------------------------------------- storage / identity
  function store(key, val) {
    try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch (e) {}
    return null;
  }
  var params = new URLSearchParams(location.search);
  if (params.get("me") === "1") document.cookie = "fx_me=1;path=/;max-age=31536000;samesite=lax";
  var isMe = /(^|;\s*)fx_me=1/.test(document.cookie);

  var ctx = {
    page: location.pathname, landing_url: location.pathname + location.search, referrer: document.referrer || "",
    device: window.matchMedia("(min-width: 832px)").matches ? "desktop" : "mobile",
    viewport: window.innerWidth + "x" + window.innerHeight, lang: LANG
  };
  // Attribution is stored as ONE record: the set of parameters that arrived together, with the time
  // they arrived. A later visit without parameters reuses that whole record or none of it — mixing
  // a source from today with a campaign from last week would report a campaign that never ran.
  var ATTR_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid"];
  var ATTR_TTL_DAYS = 30;
  (function attribution() {
    var fresh = {}, any = false;
    ATTR_KEYS.forEach(function (k) { var v = params.get(k); if (v) { fresh[k] = v; any = true; } });
    var rec = null;
    if (any) {
      rec = { at: new Date().toISOString(), p: fresh };
      store("fx_attr", JSON.stringify(rec));
    } else {
      try { rec = JSON.parse(store("fx_attr") || "null"); } catch (e) { rec = null; }
      if (rec && rec.at && (Date.now() - Date.parse(rec.at)) > ATTR_TTL_DAYS * 864e5) rec = null;
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

  // ---------------------------------------------------------------- analytics (first party, non-blocking)
  var queue = [], flushTimer = null;
  function send(beacon) {
    if (!queue.length) return;
    var payload = JSON.stringify({ session_id: SID, ctx: ctx, events: queue.splice(0, 40) });
    try {
      if (beacon && navigator.sendBeacon) { navigator.sendBeacon("/api/fx/event", new Blob([payload], { type: "application/json" })); return; }
      fetch("/api/fx/event", { method: "POST", headers: { "content-type": "application/json" }, body: payload, keepalive: true }).catch(function () {});
    } catch (e) {}
  }
  function track(name, props) {
    if (isMe) return;
    queue.push({ name: name, props: props || {}, ts: new Date().toISOString(), page: ctx.page });
    if (queue.length >= 12) { send(false); return; }
    clearTimeout(flushTimer); flushTimer = setTimeout(function () { send(false); }, 2500);
  }

  // ---------------------------------------------------------------- third party, consent-gated
  var NOTICE_KEY = "fx_notice_v1";
  function loadThirdParty() {
    if (isMe) return;
    if (CFG.pixel) {
      /* eslint-disable */
      !function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};
      if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}
      (window,document,'script','https://connect.facebook.net/en_US/fbevents.js');
      /* eslint-enable */
      window.fbq("init", CFG.pixel); window.fbq("track", "PageView");
      window.fbq("track", "ViewContent", { content_name: CFG.brand + " " + CFG.model, content_type: "product", currency: "ILS", value: CFG.price });
    }
    if (CFG.clarity) {
      /* eslint-disable */
      (function(c,l,a,r,i,t,y){c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y)})(window,document,"clarity","script",CFG.clarity);
      /* eslint-enable */
    }
  }
  function pixel(name, props) { if (window.fbq) { try { window.fbq("track", name, props || {}); } catch (e) {} } }
  var notice = qs("#notice");
  if (notice && !(CFG.pixel || CFG.clarity)) { notice.remove(); }
  else if (notice) {
    if (store(NOTICE_KEY) === "1") loadThirdParty();
    else if (!isMe) {
      notice.hidden = false; document.body.classList.add("has-notice");
      qs("#notice-ok").addEventListener("click", function () { store(NOTICE_KEY, "1"); notice.hidden = true; document.body.classList.remove("has-notice"); loadThirdParty(); });
    }
  }

  // ---------------------------------------------------------------- product state
  var TONE_LONG = S.toneLong || {};
  var STATE_WORD = S.stateWord || { closed: "closed", open: "open" };
  var SIZES = S.sizes || { "160": "closed", "220": "open" };
  function tone() { return root.getAttribute("data-oak") || "natural"; }
  function size() { return root.getAttribute("data-size") || "160"; }
  function state() { return SIZES[size()] || "closed"; }
  var supportsAvif = null;
  (function detectAvif() {
    var img = new Image();
    img.onload = function () { supportsAvif = img.width > 0; };
    img.onerror = function () { supportsAvif = false; };
    img.src = "data:image/avif;base64,AAAAIGZ0eXBhdmlmAAAAAGF2aWZtaWYxbWlhZk1BMUIAAADybWV0YQAAAAAAAAAoaGRscgAAAAAAAAAAcGljdAAAAAAAAAAAAAAAAGxpYmF2aWYAAAAADnBpdG0AAAAAAAEAAAAeaWxvYwAAAABEAAABAAEAAAABAAABGgAAAB0AAAAoaWluZgAAAAAAAQAAABppbmZlAgAAAAABAABhdjAxQ29sb3IAAAAAamlwcnAAAABLaXBjbwAAABRpc3BlAAAAAAAAAAIAAAACAAAAEHBpeGkAAAAAAwgICAAAAAxhdjFDgQ0MAAAAABNjb2xybmNseAACAAIAAYAAAAAXaXBtYQAAAAAAAAABAAEEAQKDBAAAACVtZGF0EgAKCBgANogQEAwgMg8f8D///8WfhwB8+ErK42A=";
  })();

  // ---------------------------------------------------------------- compare picture: decode before swap
  // ASSETS[id] = { w, h, avif: {width: url}, webp: {width: url} } from the build manifest.
  var cmpPic = qs("#compare-pic"), cmpImg = qs("#compare-img"), cmpBuf = qs("#compare-buf");
  var cmpToken = 0;
  function assetFor(t, s) { return ASSETS["goren-compare-" + t + "-" + s] || null; }
  function srcsetOf(asset, ext) {
    var m = asset && asset[ext]; if (!m) return "";
    return Object.keys(m).map(function (w) { return m[w] + " " + w + "w"; }).join(", ");
  }
  function largestOf(asset, ext) {
    var m = asset && asset[ext]; if (!m) return "";
    var ws = Object.keys(m).map(Number).sort(function (a, b) { return a - b; });
    return ws.length ? m[ws[ws.length - 1]] : "";
  }
  function cmpAlt(t, s) {
    return fmt(S.cmp_alt, { tone: TONE_LONG[t] || t, state: STATE_WORD[s] || s, len: s === "open" ? (S.lenOpen || "220") : (S.lenClosed || "160") });
  }
  function applyCompare(asset, t, s) {
    qsa('source[type="image/avif"]', cmpPic).forEach(function (el) { el.srcset = srcsetOf(asset, "avif"); });
    qsa('source[type="image/webp"]', cmpPic).forEach(function (el) { el.srcset = srcsetOf(asset, "webp"); });
    var mid = asset.webp && (asset.webp["1200"] || largestOf(asset, "webp"));
    if (mid) cmpImg.src = mid;
    cmpImg.alt = cmpAlt(t, s);
    cmpImg.setAttribute("data-variant", t + "-" + s);
  }
  function paintCompare() {
    if (!cmpPic || !cmpImg) return;
    var t = tone(), s = state(), asset = assetFor(t, s);
    if (!asset) return;                                   // no variant produced: the old picture stays
    var my = ++cmpToken;
    if (cmpImg.getAttribute("data-variant") === t + "-" + s) return;
    // decode the variant the <picture> would pick, off-screen, before anything on screen changes;
    // if the AVIF candidate cannot be decoded here, try the WebP one before giving up
    var sizes = (qs("source", cmpPic) && qs("source", cmpPic).sizes) || "100vw";
    function load(ext) {
      return new Promise(function (res, rej) {
        var im = new Image();
        im.onload = function () { res(im); }; im.onerror = function () { rej(new Error("load " + ext)); };
        im.sizes = sizes; im.srcset = srcsetOf(asset, ext);
        if (!im.srcset) rej(new Error("no " + ext));
      }).then(function (im) { return im.decode ? im.decode().then(function () { return im; }, function () { return im; }) : im; });
    }
    var first = supportsAvif !== false && asset.avif ? "avif" : "webp";
    var ready = load(first).catch(function () { return first === "avif" ? load("webp") : Promise.reject(new Error("load")); });
    var probe = null;
    ready.then(function (im) {
      probe = im;
      if (my !== cmpToken) return;
      if (!cmpBuf || reduced) { applyCompare(asset, t, s); return; }
      cmpBuf.src = probe.currentSrc || probe.src;
      cmpBuf.classList.add("is-in");
      setTimeout(function () {
        if (my !== cmpToken) return;
        applyCompare(asset, t, s);
        var done = function () { if (my === cmpToken) cmpBuf.classList.remove("is-in"); };
        if (cmpImg.decode) cmpImg.decode().then(done, done); else setTimeout(done, 60);
      }, 230);
    }).catch(function () {
      // the old image is retained; nothing on screen changes
      track("image_error", { asset: "goren-compare-" + t + "-" + s });
    });
  }
  if (cmpImg) cmpImg.addEventListener("error", function () { track("image_error", { asset: cmpImg.getAttribute("data-variant") || "compare" }); });
  var heroImg = qs("#hero-img");
  if (heroImg) heroImg.addEventListener("error", function () { track("image_error", { asset: "hero" }); });

  // ---------------------------------------------------------------- bindings
  function paintBindings() {
    var s = state();
    qsa('[data-bind="len"]').forEach(function (el) { el.textContent = size(); });
    qsa('[data-bind="state"]').forEach(function (el) { el.textContent = STATE_WORD[s] || s; });
    qsa('[data-bind="oak"]').forEach(function (el) { el.textContent = TONE_LONG[tone()] || tone(); });
    qsa("[data-set-size]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-set-size") === size())); });
    var r = qs('input[name="size"][value="' + size() + '"]'); if (r && !r.checked) r.checked = true;
    var o = qs('input[name="oak"][value="' + tone() + '"]'); if (o && !o.checked) o.checked = true;
    var note = qs("#f-note"); if (note && S.f_note) note.innerHTML = fmt(S.f_note, { len: num(size()), tone: TONE_LONG[tone()] || tone(), state: STATE_WORD[s] || s });
    refreshWa();
    paintFit();
  }
  function setSize(v, source) {
    if (!SIZES[v] || v === size()) { paintBindings(); return; }
    root.setAttribute("data-size", v); store("fx_size", v);
    paintBindings(); paintCompare();
    track("size_toggle", { size: v, source: source || "control" });
  }
  function setTone(v) {
    if (!TONE_LONG[v] || v === tone()) { paintBindings(); return; }
    root.setAttribute("data-oak", v); store("fx_oak", v);
    paintBindings(); paintCompare();
    track("color_select", { color: v });
  }
  qsa('input[name="size"]').forEach(function (i) { i.addEventListener("change", function () { setSize(i.value, "control"); }); });
  qsa('input[name="oak"]').forEach(function (i) { i.addEventListener("change", function () { setTone(i.value); }); });
  qsa("[data-set-size]").forEach(function (b) { b.addEventListener("click", function () { setSize(b.getAttribute("data-set-size"), "dimensions"); }); });
  (function restore() {
    var s = store("fx_size"), o = store("fx_oak"), changed = false;
    if (s && SIZES[s] && s !== size()) { root.setAttribute("data-size", s); changed = true; }
    if (o && TONE_LONG[o] && o !== tone()) { root.setAttribute("data-oak", o); changed = true; }
    if (cmpImg && !cmpImg.getAttribute("data-variant")) cmpImg.setAttribute("data-variant", "natural-closed");
    paintBindings();
    if (changed) paintCompare();
  })();

  // ---------------------------------------------------------------- whatsapp (Contact intent, never a Lead)
  function waHref() {
    var msg = fmt(S.wa_prefill, { tone: TONE_LONG[tone()] || tone(), state: STATE_WORD[state()] || state(), len: size() });
    return "https://wa.me/" + CFG.wa + "?text=" + encodeURIComponent(msg);
  }
  function refreshWa() { if (!CFG.wa) return; qsa(".js-wa").forEach(function (a) { a.setAttribute("href", waHref()); a.setAttribute("target", "_blank"); }); }
  qsa(".js-wa").forEach(function (a) {
    a.addEventListener("click", function (e) {
      if (!CFG.wa) { e.preventDefault(); return; }
      var pl = a.getAttribute("data-placement") || "";
      track("whatsapp_click", { placement: pl, color: tone(), size: size() });
      pixel("Contact", { content_name: "whatsapp_" + pl });
    });
  });
  qsa(".js-anchor").forEach(function (a) { a.addEventListener("click", function () { track("form_anchor_click", { placement: a.getAttribute("data-placement") || "" }); }); });

  // ---------------------------------------------------------------- room length: numerical clearance only
  var verdictEl = qs("#verdict"), roomInput = qs("#roomlen"), fitHint = qs("#fit-hint"), fitTimer = null, lastFit = null;
  var L_CLOSED = parseInt(S.lenClosed || "160", 10), L_OPEN = parseInt(S.lenOpen || "220", 10);
  function parseLength(raw) {
    var s = String(raw || "").trim().replace(",", ".").replace(/[^\d.]/g, "");
    if (!s) return { empty: true };
    var v = parseFloat(s);
    if (!isFinite(v)) return { bad: true };
    if (v >= 1 && v < 20) v = v * 100;           // metres
    v = Math.round(v);
    var min = parseInt(roomInput.getAttribute("data-min") || "60", 10), max = parseInt(roomInput.getAttribute("data-max") || "1500", 10);
    if (v < min || v > max) return { bad: true };
    return { cm: v };
  }
  function fitLine(len, keyOk, keyExact, keyNo, wall) {
    var gap = Math.floor((wall - len) / 2);
    if (wall - len < 0) return fmt(S[keyNo], { n: num(len - wall) });
    if (gap === 0) return S[keyExact] || "";
    return fmt(S[keyOk], { n: num(gap) });
  }
  function fitBar(wall, len) {
    var gap = (wall - len) / 2;
    if (gap < 0) return "";
    var pct = function (cm) { return (cm / wall * 100).toFixed(2) + "%"; };
    var g = Math.floor(gap);
    var gapc = '<span class="gapc" style="flex-basis:' + pct(gap) + '">' + (g > 0 ? "<i>" + g + "</i>" : "") + "</span>";
    return '<div class="fitbar" role="img" aria-label="' + fmt(S.fit_bar_alt, { wall: wall, len: len, n: g }) + '">' +
      '<span class="wallmark"></span>' + gapc + '<span class="tbl" style="flex-basis:' + pct(len) + '">' + len + "</span>" + gapc + '<span class="wallmark"></span></div>';
  }
  function paintFit() {
    if (!verdictEl || !roomInput || lastFit == null) return null;
    var wall = lastFit, v = wall >= L_OPEN ? "open" : wall >= L_CLOSED ? "closed" : "no";
    verdictEl.setAttribute("data-v", v);
    var openLine = fitLine(L_OPEN, "fit_open_ok", "fit_open_exact", "fit_open_no", wall);
    var closedLine = fitLine(L_CLOSED, "fit_closed_ok", "fit_closed_exact", "fit_closed_no", wall);
    var cur = parseInt(size(), 10);
    verdictEl.innerHTML = "<p>" + (v === "no" ? closedLine : v === "closed" ? openLine : openLine) + "</p><p>" + (v === "no" ? "" : v === "closed" ? closedLine : closedLine) + "</p>" + (wall >= cur ? fitBar(wall, cur) : "");
    return v;
  }
  if (roomInput && verdictEl) {
    var fitForm = qs("#fitform");
    if (fitForm) fitForm.addEventListener("submit", function (e) { e.preventDefault(); });
    var settleTimer = null;
    function readFit(final) {
      var p = parseLength(roomInput.value);
      if (p.empty || p.bad) {
        lastFit = null; verdictEl.removeAttribute("data-v"); verdictEl.innerHTML = "";
        if (fitHint) fitHint.textContent = (p.bad && final) ? (S.fit_hint_bad || S.fit_hint) : (S.fit_hint || "");
        return;
      }
      if (fitHint) fitHint.textContent = S.fit_hint || "";
      lastFit = p.cm;
      var v = paintFit();
      clearTimeout(fitTimer);
      fitTimer = setTimeout(function () { track("room_fit_check", { room_length: p.cm, result: v, size: size() }); }, 900);
    }
    roomInput.addEventListener("input", function () {
      clearTimeout(settleTimer);
      settleTimer = setTimeout(function () { readFit(false); }, 450);   // one announcement per number, not per keystroke
    });
    roomInput.addEventListener("change", function () { clearTimeout(settleTimer); readFit(true); });
    roomInput.addEventListener("blur", function () { clearTimeout(settleTimer); readFit(true); });
  }

  // ---------------------------------------------------------------- enlargement (user action only)
  var imageDialog = qs("#image-dialog"), zoomBtn = qs("#compare-zoom");
  if (imageDialog && zoomBtn && typeof imageDialog.showModal === "function") {
    var opener = null;
    zoomBtn.addEventListener("click", function () {
      var asset = assetFor(tone(), state()); if (!asset) return;
      var large = qs("#image-large");
      large.src = largestOf(asset, supportsAvif !== false && asset.avif ? "avif" : "webp") || largestOf(asset, "webp");
      large.alt = cmpAlt(tone(), state());
      qs("#image-dialog-title").textContent = large.alt;
      opener = zoomBtn; imageDialog.showModal();
      track("gallery_open", { view: "compare", color: tone(), size: size() });
    });
    qs("#image-close").addEventListener("click", function () { imageDialog.close(); });
    imageDialog.addEventListener("click", function (e) { if (e.target === imageDialog) imageDialog.close(); });
    imageDialog.addEventListener("close", function () { if (opener) opener.focus({ preventScroll: true }); });
  } else if (zoomBtn) { zoomBtn.hidden = true; }

  // ---------------------------------------------------------------- faq
  qsa("#faq-list details").forEach(function (d) {
    d.addEventListener("toggle", function () { if (d.open) track("faq_open", { q: (qs("summary", d).textContent || "").trim().slice(0, 80) }); });
  });

  // ---------------------------------------------------------------- form
  // Mirror of api/handler.py normalize_phone — keep the two in lockstep.
  var PHONE_NATIONAL = /^(?:5\d{8}|[23489]\d{7}|7[2-9]\d{7})$/;
  function normalizePhone(raw) {
    var d = String(raw || "").replace(/[^0-9]/g, "");
    if (!d) return { e164: "", ok: false };
    if (d.length > 15) return { e164: "+" + d, ok: false };
    if (d.slice(0, 2) === "00") d = d.slice(2);
    var national;
    if (d.slice(0, 3) === "972") national = d.slice(3).replace(/^0+/, "");
    else if (d.charAt(0) === "0") national = d.slice(1);
    else return { e164: "+" + d, ok: false };
    return { e164: "+972" + national, ok: PHONE_NATIONAL.test(national) };
  }
  var form = qs("#leadform");
  if (form) {
    var started = false, inFlight = false, statusEl = qs("#f-status"), submitBtn = qs("#f-submit");
    form.addEventListener("focusin", function (e) { if (!started) { started = true; track("form_start", {}); } if (e.target.name) track("form_field", { field: e.target.name }); });
    function setError(field, message) {
      var el = qs("#f-" + field), err = qs("#e-" + field);
      if (err) { err.textContent = message || ""; err.hidden = !message; }
      if (el) { var lab = el.closest(".field") || el.closest(".consent"); if (lab) lab.classList.toggle("has-error", !!message); if (message) el.setAttribute("aria-invalid", "true"); else el.removeAttribute("aria-invalid"); }
      if (message) track("form_error", { field: field });
    }
    ["name", "phone"].forEach(function (f) { var el = qs("#f-" + f); if (el) el.addEventListener("input", function () { if (el.getAttribute("aria-invalid") === "true") setError(f, ""); }); });
    var consentEl = qs("#f-consent"); if (consentEl) consentEl.addEventListener("change", function () { if (consentEl.checked) setError("consent", ""); });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (inFlight) return;                                 // one enquiry per click, never two
      var data = {
        name: (qs("#f-name").value || "").trim(), phone: (qs("#f-phone").value || "").trim(),
        city: (qs("#f-city").value || "").trim(), comment: (qs("#f-comment").value || "").trim(),
        website: qs("#f-website").value, color: tone(), size: size(),
        consent: qs("#f-consent").checked, consent_marketing: qs("#f-marketing").checked,
        consent_text_version: CFG.consentVersion || "v1", session_id: SID, page: ctx.page, referrer: ctx.referrer, device: ctx.device,
        lang: LANG, utm_source: ctx.utm_source, utm_medium: ctx.utm_medium, utm_campaign: ctx.utm_campaign, utm_content: ctx.utm_content, utm_term: ctx.utm_term, fbclid: ctx.fbclid,
        attributed_at: ctx.attributed_at
      };
      var bad = false, missing = [], invalid = [];
      setError("name", ""); setError("phone", ""); setError("consent", "");
      if (data.name.length < 2) { setError("name", S.e_name); missing.push(S.f_name); bad = true; }
      if (!data.phone) { setError("phone", S.e_phone); missing.push(S.f_phone); bad = true; }
      else if (!normalizePhone(data.phone).ok) { setError("phone", S.e_phone_invalid || S.e_phone); invalid.push(S.e_phone_invalid || S.e_phone); bad = true; }
      if (!data.consent) { setError("consent", S.e_consent); missing.push(S.e_consent_short || S.e_consent); bad = true; }
      if (bad) {
        statusEl.setAttribute("data-s", "err");
        var parts = [];
        if (missing.length) parts.push((S.s_missing || "") + " " + missing.join(", ") + ".");
        if (invalid.length) parts.push(invalid.join(" "));
        statusEl.textContent = parts.join(" ");
        var first = qs(".has-error input, .has-error textarea");
        if (first) { first.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" }); setTimeout(function () { try { first.focus({ preventScroll: true }); } catch (x) {} }, 350); }
        return;
      }
      track("form_submit", {}); inFlight = true; submitBtn.disabled = true; submitBtn.setAttribute("aria-busy", "true");
      statusEl.removeAttribute("data-s"); statusEl.textContent = S.s_sending || "";
      var unlock = function () { inFlight = false; submitBtn.disabled = false; submitBtn.removeAttribute("aria-busy"); };
      fetch("/api/fx/lead", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(data) })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { status: r.status, body: b || {} }; }); })
        .then(function (res) {
          if (res.status === 200 && res.body.ok) {
            // the honeypot decoy answers ok too; it is not a conversion
            if (res.body.id !== "hp") { track("lead_success", { color: data.color, size: data.size }); pixel("Lead", { content_name: "form", currency: "ILS", value: 0 }); }
            send(false);
            location.href = S.thanks_href || "/thanks"; return;
          }
          unlock(); statusEl.setAttribute("data-s", "err");
          if (res.status === 429) statusEl.textContent = S.s_rate;
          else if (res.status === 422 && res.body && res.body.errors) {
            Object.keys(res.body.errors).forEach(function (k) { setError(k, k === "phone" ? (S.e_phone_invalid || S.e_phone) : (S["e_" + k] || S.s_invalid)); });
            statusEl.textContent = S.s_invalid;
          }
          else statusEl.textContent = S.s_fail;
        }).catch(function () { unlock(); statusEl.setAttribute("data-s", "err"); statusEl.textContent = S.s_offline; });
    });
  }

  // ---------------------------------------------------------------- sticky return shortcut
  var sticky = qs("#sticky"), heroActions = qs(".hero-actions"), formSec = qs("#form"), footer = qs("footer");
  if (sticky && heroActions && "IntersectionObserver" in window) {
    var barOn = false, overForm = false, typing = false;
    var apply = function () {
      var visible = barOn && !overForm && !typing;
      sticky.hidden = !visible; sticky.inert = !visible;
      sticky.classList.toggle("is-on", visible);
      root.classList.toggle("has-bar", visible);
    };
    new IntersectionObserver(function (es) {
      es.forEach(function (en) { barOn = !en.isIntersecting && en.boundingClientRect.top < 0; }); apply();
    }, { threshold: 0 }).observe(heroActions);
    var seenForm = {};
    var fo = new IntersectionObserver(function (es) {
      es.forEach(function (en) { seenForm[en.target.id || en.target.tagName] = en.isIntersecting; });
      overForm = Object.keys(seenForm).some(function (k) { return seenForm[k]; }); apply();
    }, { threshold: 0 });
    if (formSec) fo.observe(formSec);
    if (footer) fo.observe(footer);
    // never over a focused field or the keyboard
    document.addEventListener("focusin", function (e) { if (e.target && e.target.matches && e.target.matches("input, textarea, select")) { typing = true; apply(); } });
    document.addEventListener("focusout", function (e) { if (e.target && e.target.matches && e.target.matches("input, textarea, select")) { typing = false; apply(); } });
  }

  // ---------------------------------------------------------------- entrances, section views, scroll, exit
  if ("IntersectionObserver" in window) {
    var reveals = qsa(".reveal");
    if (reveals.length) {
      var ro = new IntersectionObserver(function (es) {
        es.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("is-in"); ro.unobserve(en.target); } });
      }, { threshold: 0.08, rootMargin: "0px 0px -8% 0px" });
      reveals.forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) { el.classList.add("is-in"); return; }   // already on screen: no delay
        el.classList.add("will-reveal"); ro.observe(el);
      });
    }
    // a tall section on a phone never reaches 35 % visibility: count it seen when at least
    // 35 % of the section OR half the viewport is on screen (compatible with the existing reports)
    var seen = {};
    var so = new IntersectionObserver(function (es) {
      es.forEach(function (en) {
        var k = en.target.getAttribute("data-section");
        if (seen[k] || !en.isIntersecting) return;
        var enough = en.intersectionRatio >= 0.35 || en.intersectionRect.height >= window.innerHeight * 0.5;
        if (enough) { seen[k] = true; track("section_view", { section: k }); }
      });
    }, { threshold: [0, 0.1, 0.2, 0.35, 0.5, 0.75, 1] });
    qsa("[data-section]").forEach(function (s) { so.observe(s); });
  } else {
    qsa(".reveal").forEach(function (el) { el.classList.add("is-in"); });
  }
  var maxScroll = 0, marks = {};
  window.addEventListener("scroll", function () {
    var h = document.documentElement.scrollHeight - window.innerHeight; if (h <= 0) return;
    var p = Math.round((window.scrollY / h) * 100); if (p > maxScroll) maxScroll = p;
    [25, 50, 75, 100].forEach(function (m) { if (p >= m && !marks[m]) { marks[m] = true; track("scroll_" + m, {}); } });
  }, { passive: true });
  var t0 = Date.now(), said_bye = false;
  function bye() {
    if (said_bye) { send(true); return; }                  // both events fire on an ordinary navigation
    said_bye = true;
    track("exit", { seconds: Math.round((Date.now() - t0) / 1000), max_scroll: maxScroll });
    send(true);
  }
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") bye(); });
  window.addEventListener("pagehide", bye);
  track("page_view", { path: ctx.page, lang: LANG });
})();
