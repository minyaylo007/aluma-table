// Обв'язка для tests/test_tracking_js.py: виконує site/assets/tracking.js у node:vm з фальшивим DOM
// і друкує JSON із тим, що скрипт зробив назовні. Без мережі, без браузера, без порту.
// Вхід — argv[2]: {config, consent, stored, me, search, lang, hasNotice, calls:[[event, params]], consentAfter,
//                  clickNotice, clickDecline, declineAfter, resetAfter, callsAfter}
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const sc = JSON.parse(process.argv[2] || "{}");
const src = fs.readFileSync(path.join(__dirname, "..", "site", "assets", "tracking.js"), "utf8");
const out = { fetches: [], posts: [], scripts: [], fbq: [], notice: null, noticeText: null, noticeDir: null, ids: [], events: [] };

const stored = sc.stored !== undefined ? sc.stored : sc.consent ? "1" : null;
const ls = new Map(stored !== null ? [["fx_notice_v1", stored]] : []);
const ss = new Map();
function el(tag) {
  return {
    tagName: tag, style: {}, attrs: {}, children: [], textContent: "", parentNode: null,
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] ?? null; },
    appendChild(c) { c.parentNode = this; this.children.push(c); if (c.id === "aluma-notice") { out.notice = c; out.noticeText = c.children[0].textContent; out.noticeDir = c.dir; } return c; },
    removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parentNode = null; if (c === out.notice) out.notice = "removed"; },
    insertBefore(c) { c.parentNode = this; if (c.src) out.scripts.push(c.src); return c; },
    addEventListener(t, fn) { (this.l = this.l || {})[t] = fn; },
  };
}
const head = el("head");
const firstScript = el("script");
firstScript.parentNode = head;
const body = el("body");
const listeners = {};
const document = {
  documentElement: { getAttribute: (k) => (k === "lang" ? sc.lang || "he" : null) },
  cookie: sc.me ? "fx_me=1" : "",
  referrer: "",
  currentScript: { getAttribute: () => null },
  body,
  createElement: el,
  getElementById: (id) => (id === "notice" && sc.hasNotice ? el("div") : id === "aluma-notice" && out.notice && out.notice !== "removed" ? out.notice : null),
  getElementsByTagName: () => [firstScript],
  addEventListener: (t, fn) => { listeners[t] = fn; },
  dispatchEvent: (e) => { if (!out.dispatched) out.dispatched = e.type; (out.consentEvents = out.consentEvents || []); if (e.type === "aluma:consent") out.consentEvents.push(e.detail); },
};
function fetchFake(url, opts) {
  out.fetches.push(url);
  if (url === "/api/fx/config") {
    if (sc.config === "fail") return Promise.reject(new Error("offline"));
    return Promise.resolve({ ok: true, json: () => Promise.resolve(sc.config || {}) });
  }
  if (opts && opts.body) out.posts.push(JSON.parse(opts.body));
  return Promise.resolve({ ok: true });
}
const win = {
  document, location: { pathname: sc.lang === "en" ? "/en/" : "/", search: sc.search || "" },
  innerWidth: 390, innerHeight: 844, matchMedia: () => ({ matches: false }),
  localStorage: { getItem: (k) => (ls.has(k) ? ls.get(k) : null), setItem: (k, v) => ls.set(k, String(v)), removeItem: (k) => ls.delete(k) },
  sessionStorage: { getItem: (k) => (ss.has(k) ? ss.get(k) : null), setItem: (k, v) => ss.set(k, String(v)) },
  navigator: {}, fetch: fetchFake, URLSearchParams, Promise, JSON, Date, Math, Object, String, Array, Uint32Array,
  crypto: require("crypto").webcrypto,
  CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
  addEventListener: () => {}, setTimeout: (fn) => { fn(); return 0; }, clearTimeout: () => {},
  Blob: function () {},
};
win.window = win;
const ctx = vm.createContext(win);
vm.runInContext(src, ctx);

// fbevents.js ніколи не вантажиться, тож заглушка fbq зі сніпета складає всі виклики у свою чергу
setImmediate(() => setImmediate(() => {
  for (const [name, params] of sc.calls || []) out.ids.push(win.alumaTrack(name, params));
  if (sc.consentAfter) win.alumaConsent();
  if (sc.clickNotice && out.notice && out.notice.children) out.notice.children[1].l.click();
  if (sc.clickDecline && out.notice && out.notice.children) out.notice.children[2].l.click();
  if (sc.declineAfter) win.alumaConsent(false);
  if (sc.resetAfter) { out.notice = null; win.alumaConsentReset(); }
  for (const name of sc.callsAfter || []) out.ids.push(win.alumaTrack(name, {}));
  out.buttons = out.notice && out.notice.children ? out.notice.children.slice(1).map((c) => c.textContent) : null;
  out.fbq = win.fbq && win.fbq.queue ? win.fbq.queue.map((a) => Array.from(a)) : [];
  out.events = out.posts.flatMap((p) => p.events.map((e) => ({ name: e.name, id: e.props.event_id })));
  out.notice = out.notice ? (out.notice === "removed" ? "removed" : "shown") : null;
  out.consent = ls.get("fx_notice_v1") || null;
  out.state = win.alumaConsentState ? win.alumaConsentState() : null;
  out.globals = ["alumaTrack", "alumaEventId", "alumaConsent", "alumaConsentState", "alumaConsentReset", "alumaConfig"].filter((k) => typeof win[k] === "function");
  process.stdout.write(JSON.stringify(out));
}));
