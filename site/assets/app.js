/* aluma / fx-table — interactions + first-party analytics.
   No dependencies. Nothing third-party loads until the notice is acknowledged. */
(function () {
  "use strict";

  var CFG = {
    wa: "{{WA_NUMBER}}",
    pixel: "{{META_PIXEL_ID}}",
    clarity: "{{CLARITY_ID}}",
    consentVersion: "{{CONSENT_VERSION}}",
    brand: "{{BRAND_HE}}",
    model: "{{MODEL_HE}}"
  };

  var OAK_HE = { natural: "אלון טבעי", smoked: "אלון מעושן", white: "אלון מולבן" };
  var SEATS = { "160": "{{SEATS_CLOSED}}", "220": "{{SEATS_OPEN}}" };

  var root = document.documentElement;
  var qs = function (s, c) { return (c || document).querySelector(s); };
  var qsa = function (s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); };

  // ---------------------------------------------------------------- state

  function store(key, val) {
    try {
      if (val === undefined) return localStorage.getItem(key);
      localStorage.setItem(key, val);
    } catch (e) { /* private mode */ }
    return null;
  }

  var params = new URLSearchParams(location.search);

  // owner's own visits must not pollute a 20-lead dataset
  if (params.get("me") === "1") {
    document.cookie = "fx_me=1;path=/;max-age=31536000;samesite=lax";
  }
  var isMe = /(^|;\s*)fx_me=1/.test(document.cookie);

  var ctx = {
    page: location.pathname,
    landing_url: location.pathname + location.search,
    referrer: document.referrer || "",
    device: window.matchMedia("(min-width: 832px)").matches ? "desktop" : "mobile",
    viewport: window.innerWidth + "x" + window.innerHeight,
    lang: navigator.language || ""
  };
  ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid"].forEach(function (k) {
    var v = params.get(k);
    if (v) { store("fx_" + k, v); }
    ctx[k] = v || store("fx_" + k) || "";
  });

  function sessionId() {
    var id = null;
    try { id = sessionStorage.getItem("fx_sid"); } catch (e) {}
    if (!id) {
      id = (Date.now().toString(36) + Math.random().toString(36).slice(2, 10));
      try { sessionStorage.setItem("fx_sid", id); } catch (e) {}
    }
    return id;
  }
  var SID = sessionId();

  // ---------------------------------------------------------------- events

  var queue = [];
  var flushTimer = null;

  function send(useBeacon) {
    if (!queue.length) return;
    var payload = JSON.stringify({ session_id: SID, ctx: ctx, events: queue.splice(0, 40) });
    if (useBeacon && navigator.sendBeacon) {
      navigator.sendBeacon("/api/fx/event", new Blob([payload], { type: "application/json" }));
      return;
    }
    fetch("/api/fx/event", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: payload,
      keepalive: true
    }).catch(function () { /* analytics must never break the page */ });
  }

  function track(name, props) {
    if (isMe) return;
    queue.push({ name: name, props: props || {}, ts: new Date().toISOString(), page: ctx.page });
    if (queue.length >= 12) { send(false); return; }
    clearTimeout(flushTimer);
    flushTimer = setTimeout(function () { send(false); }, 2500);
  }

  // ---------------------------------------------------------------- third party (consent-gated)

  var NOTICE_KEY = "fx_notice_v1";

  function loadThirdParty() {
    if (isMe) return;
    if (CFG.pixel) {
      /* eslint-disable */
      !function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
      n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
      n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
      t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}
      (window,document,'script','https://connect.facebook.net/en_US/fbevents.js');
      /* eslint-enable */
      window.fbq("init", CFG.pixel);
      window.fbq("track", "PageView");
      window.fbq("track", "ViewContent", {
        content_name: CFG.brand + " " + CFG.model,
        content_type: "product",
        currency: "ILS",
        value: {{PRICE_PLAIN}}
      });
    }
    if (CFG.clarity) {
      /* eslint-disable */
      (function(c,l,a,r,i,t,y){c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
      t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
      y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y)})
      (window,document,"clarity","script",CFG.clarity);
      /* eslint-enable */
    }
  }

  function pixel(name, props) {
    if (window.fbq) { try { window.fbq("track", name, props || {}); } catch (e) {} }
  }

  var notice = qs("#notice");
  var needsNotice = !!(CFG.pixel || CFG.clarity);
  if (notice && !needsNotice) {
    notice.remove();                      // nothing third-party is configured: no bar
  } else if (notice) {
    var acknowledged = store(NOTICE_KEY) === "1";
    if (acknowledged || isMe) {
      if (acknowledged) loadThirdParty();
    } else {
      notice.hidden = false;
      // the notice and the sticky bar both sit at the bottom of the screen;
      // while the notice is up the sticky bar stays down
      document.body.classList.add("has-notice");
      qs("#notice-ok").addEventListener("click", function () {
        store(NOTICE_KEY, "1");
        notice.hidden = true;
        document.body.classList.remove("has-notice");
        loadThirdParty();
      });
    }
  }

  // ---------------------------------------------------------------- switchers

  function currentSize() { return root.getAttribute("data-size") || "160"; }
  function currentOak() { return root.getAttribute("data-oak") || "natural"; }

  function paintBindings() {
    qsa('[data-bind="len"]').forEach(function (el) { el.textContent = currentSize(); });
    qsa('[data-bind="seats"]').forEach(function (el) { el.textContent = SEATS[currentSize()]; });
    qsa('[data-bind="oak"]').forEach(function (el) { el.textContent = OAK_HE[currentOak()]; });
    qsa(".state").forEach(function (el) {
      el.setAttribute("data-current", String(el.getAttribute("data-state") === currentSize()));
    });
    refreshWa();
  }

  qsa('input[name="size"]').forEach(function (input) {
    input.addEventListener("change", function () {
      root.setAttribute("data-size", input.value);
      store("fx_size", input.value);
      paintBindings();
      track("size_toggle", { size: input.value });
    });
  });

  qsa('input[name="oak"]').forEach(function (input) {
    input.addEventListener("change", function () {
      root.setAttribute("data-oak", input.value);
      store("fx_oak", input.value);
      paintBindings();
      track("color_select", { color: input.value });
    });
  });

  // restore a previous choice — the page should remember what you configured
  (function restore() {
    var s = store("fx_size"), o = store("fx_oak");
    if (s && SEATS[s]) {
      root.setAttribute("data-size", s);
      var si = qs('input[name="size"][value="' + s + '"]');
      if (si) si.checked = true;
    }
    if (o && OAK_HE[o]) {
      root.setAttribute("data-oak", o);
      var oi = qs('input[name="oak"][value="' + o + '"]');
      if (oi) oi.checked = true;
    }
    paintBindings();
  })();

  // ---------------------------------------------------------------- whatsapp

  function waHref() {
    var msg = "היי, מתעניין/ת בשולחן " + CFG.model + ", גוון " + OAK_HE[currentOak()] +
              ", אורך " + currentSize() + " ס״מ";
    return "https://wa.me/" + CFG.wa + "?text=" + encodeURIComponent(msg);
  }

  function refreshWa() {
    if (!CFG.wa) return;
    qsa(".js-wa").forEach(function (a) {
      a.setAttribute("href", waHref());
      a.setAttribute("target", "_blank");
    });
  }

  qsa(".js-wa").forEach(function (a) {
    a.addEventListener("click", function () {
      var placement = a.getAttribute("data-placement") || "unknown";
      track("whatsapp_click", { placement: placement, color: currentOak(), size: currentSize() });
      pixel("Contact", { content_name: "whatsapp_" + placement });
      pixel("Lead", { content_name: "whatsapp_" + placement, currency: "ILS", value: 0 });
    });
  });

  qsa(".js-anchor").forEach(function (a) {
    a.addEventListener("click", function () {
      track("form_anchor_click", { placement: a.getAttribute("data-placement") || "" });
    });
  });

  // ---------------------------------------------------------------- room fit

  // Clearance is measured at the ENDS of the table, along the wall it stands against —
  // not the 90 cm walkway you need at the sides. Demanding 90 cm at each end rejected a
  // 3.3 m wall, which is an ordinary Israeli living room.
  var ROOMY = 90;   // generous: walk round the end without thinking
  var EASY  = 60;   // comfortable: pull a chair out and pass
  var SNUG  = 35;   // possible: squeeze past, one end effectively against the wall

  var verdictEl = qs("#verdict");
  var roomInput = qs("#roomlen");
  var fitTimer = null;

  var DEFAULT_VERDICT =
    '<strong>מזינים אורך ומקבלים תשובה</strong>' +
    '<p>נשארים <span class="num">60</span> ס״מ פנויים בכל קצה? אפשר למשוך כיסא ולעבור בנוחות.</p>';

  function cmText(n) { return '<span class="num">' + n + '</span> ס״מ'; }

  function verdict(len) {
    // one number, computed once, printed everywhere — so 399 and 400 cannot disagree
    var open = Math.floor((len - 220) / 2);
    var closed = Math.floor((len - 160) / 2);

    if (open >= ROOMY) {
      return { v: "ok", t: "נכנס בנוח, גם פתוח",
        p: "פתוח ל־220 יישארו " + cmText(open) + " בכל קצה. מספיק כדי לעבור בלי לחשוב." };
    }
    if (open >= EASY) {
      return { v: "ok", t: "נכנס, גם פתוח",
        p: "פתוח ל־220 יישארו " + cmText(open) + " בכל קצה — מספיק כדי למשוך כיסא ולעבור." };
    }
    if (open >= SNUG) {
      return { v: "tight", t: "נכנס פתוח, אבל צמוד",
        p: "יישארו " + cmText(open) + " בכל קצה. עובד אם קצה אחד ממילא צמוד לקיר; " +
           "אם צריך לעבור משני הצדדים, זה יהיה צפוף." };
    }
    if (open >= 0) {
      return { v: "tight", t: open === 0 ? "נכנס בדיוק, בלי מרווח" : "נכנס, כמעט בלי מרווח",
        p: "פתוח ל־220 יישארו " + cmText(open) + " בכל קצה — השולחן נכנס, אבל לא נשאר מקום לעבור בקצוות." };
    }
    if (closed >= SNUG) {
      return { v: "tight", t: "מתאים סגור. פתוח לא ייכנס.",
        p: "ב־160 יישארו " + cmText(closed) + " בכל קצה. כדי לפתוח ל־220 חסרים " +
           cmText(Math.abs(open) * 2) + "." };
    }
    if (closed >= 0) {
      return { v: "tight", t: "נכנס סגור, צמוד משני הצדדים",
        p: "ב־160 יישארו " + cmText(closed) + " בכל קצה. שווה לשקול להצמיד צד אחד לקיר." };
    }
    return { v: "no", t: "קצר מדי",
      p: "השולחן הסגור הוא " + cmText(160) + ", וקיר של " + cmText(len) + " לא יספיק." };
  }

  function resetVerdict() {
    clearTimeout(fitTimer);
    verdictEl.removeAttribute("data-v");
    verdictEl.innerHTML = DEFAULT_VERDICT;
  }

  if (roomInput && verdictEl) {
    roomInput.addEventListener("input", function () {
      clearTimeout(fitTimer);
      var raw = parseInt(roomInput.value, 10);
      // an empty or nonsense field must clear the answer, not leave the last one standing
      if (!raw || raw < 60 || raw > 1500) { resetVerdict(); return; }
      var r = verdict(raw);
      verdictEl.setAttribute("data-v", r.v);
      verdictEl.innerHTML = "<strong></strong><p></p>";
      qs("strong", verdictEl).textContent = r.t;
      qs("p", verdictEl).innerHTML = r.p;
      fitTimer = setTimeout(function () {
        track("room_fit_check", { room_length: raw, result: r.v });
      }, 900);
    });
  }

  // ---------------------------------------------------------------- faq

  qsa("#faq details").forEach(function (d) {
    d.addEventListener("toggle", function () {
      if (d.open) {
        track("faq_open", { q: (qs("summary", d).textContent || "").trim().slice(0, 80) });
      }
    });
  });

  // ---------------------------------------------------------------- form

  var form = qs("#leadform");
  if (form) {
    var started = false;
    var statusEl = qs("#f-status");
    var submitBtn = qs("#f-submit");

    form.addEventListener("focusin", function (e) {
      if (!started) { started = true; track("form_start", {}); }
      if (e.target.name) track("form_field", { field: e.target.name });
    });

    function setError(field, message) {
      var wrap = qs("#f-" + field);
      var err = qs("#e-" + field);
      if (err) { err.textContent = message || ""; err.hidden = !message; }
      if (wrap) {
        var label = wrap.closest(".field") || wrap.closest(".consent");
        if (label) label.classList.toggle("has-error", !!message);
        wrap.setAttribute("aria-invalid", message ? "true" : "false");
      }
      if (message) track("form_error", { field: field });
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var data = {
        name: (qs("#f-name").value || "").trim(),
        phone: (qs("#f-phone").value || "").trim(),
        city: (qs("#f-city").value || "").trim(),
        comment: (qs("#f-comment").value || "").trim(),
        website: qs("#f-website").value,
        color: currentOak(),
        size: currentSize(),
        consent: qs("#f-consent").checked,
        consent_marketing: qs("#f-marketing").checked,
        consent_text_version: CFG.consentVersion,
        session_id: SID,
        page: ctx.page,
        referrer: ctx.referrer,
        device: ctx.device,
        utm_source: ctx.utm_source, utm_medium: ctx.utm_medium,
        utm_campaign: ctx.utm_campaign, utm_content: ctx.utm_content,
        utm_term: ctx.utm_term, fbclid: ctx.fbclid
      };

      var bad = false;
      setError("name", ""); setError("phone", ""); setError("consent", "");
      if (data.name.length < 2) { setError("name", "צריך שם כדי לדעת למי לפנות"); bad = true; }
      var phoneOk = /^0?5\d[\d\-\s]{7,}$|^\+?972[\d\-\s]{8,}$|^0[23489][\d\-\s]{7,}$/.test(data.phone);
      if (!phoneOk) {
        setError("phone", "מספר טלפון ישראלי, למשל 050-000-0000"); bad = true;
      }
      if (!data.consent) { setError("consent", "צריך לאשר שאפשר לחזור אליכם"); bad = true; }
      if (bad) {
        // say what is missing where the thumb is, and bring the first bad field into view
        var missing = [];
        if (data.name.length < 2) missing.push("שם");
        if (!phoneOk) missing.push("טלפון");
        if (!data.consent) missing.push("אישור שאפשר לחזור אליכם");
        statusEl.setAttribute("data-s", "err");
        statusEl.textContent = "חסר: " + missing.join(", ") + ".";
        var first = qs(".has-error input, .has-error textarea");
        if (first) {
          first.scrollIntoView({ block: "center", behavior: "smooth" });
          setTimeout(function () { try { first.focus({ preventScroll: true }); } catch (e) {} }, 350);
        }
        return;
      }

      track("form_submit", {});
      submitBtn.disabled = true;
      statusEl.removeAttribute("data-s");
      statusEl.textContent = "רגע…";

      fetch("/api/fx/lead", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(data)
      }).then(function (r) {
        return r.json().then(function (b) { return { status: r.status, body: b }; });
      }).then(function (res) {
        if (res.status === 200 && res.body.ok) {
          track("lead_success", { color: data.color, size: data.size });
          pixel("Lead", { content_name: "form", currency: "ILS", value: 0 });
          send(false);
          location.href = "/thanks";
          return;
        }
        submitBtn.disabled = false;
        statusEl.setAttribute("data-s", "err");
        if (res.status === 429) {
          statusEl.textContent = "נשלחו כמה פניות מהחיבור הזה. נסו שוב עוד קצת, או כתבו לנו בוואטסאפ.";
        } else if (res.body && res.body.errors) {
          Object.keys(res.body.errors).forEach(function (k) { setError(k, "לא תקין"); });
          statusEl.textContent = "משהו בפרטים לא עבר. בדקו את השדות המסומנים.";
        } else {
          statusEl.textContent = "לא הצלחנו לשלוח. נסו שוב, או כתבו לנו בוואטסאפ.";
        }
      }).catch(function () {
        submitBtn.disabled = false;
        statusEl.setAttribute("data-s", "err");
        statusEl.textContent = "אין חיבור לרגע. נסו שוב.";
      });
    });
  }

  // ---------------------------------------------------------------- scroll, sections, sticky

  var sticky = qs("#sticky");
  var hero = qs('[data-section="hero"]');
  if (sticky && hero && "IntersectionObserver" in window) {
    sticky.hidden = false;
    new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { sticky.classList.toggle("is-on", !en.isIntersecting); });
    }, { rootMargin: "-70% 0px 0px 0px" }).observe(hero);
  }

  if ("IntersectionObserver" in window) {
    var seen = {};
    var so = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var key = en.target.getAttribute("data-section");
        if (en.isIntersecting && !seen[key]) {
          seen[key] = true;
          track("section_view", { section: key });
        }
      });
    }, { threshold: 0.35 });
    qsa("[data-section]").forEach(function (s) { so.observe(s); });
  }

  var maxScroll = 0, marks = {};
  window.addEventListener("scroll", function () {
    var h = document.documentElement.scrollHeight - window.innerHeight;
    if (h <= 0) return;
    var p = Math.round((window.scrollY / h) * 100);
    if (p > maxScroll) maxScroll = p;
    [25, 50, 75, 100].forEach(function (m) {
      if (p >= m && !marks[m]) { marks[m] = true; track("scroll_" + m, {}); }
    });
  }, { passive: true });

  qsa('a[href^="tel:"]').forEach(function (a) {
    a.addEventListener("click", function () { track("phone_click", {}); });
  });
  qsa('a[href="/privacy"]').forEach(function (a) {
    a.addEventListener("click", function () { track("privacy_open", {}); });
  });

  var t0 = Date.now();
  function bye() {
    track("exit", { seconds: Math.round((Date.now() - t0) / 1000), max_scroll: maxScroll });
    send(true);
  }
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") bye();
  });
  window.addEventListener("pagehide", bye);

  track("page_view", { path: ctx.page });
})();
