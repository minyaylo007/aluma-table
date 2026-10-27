#!/usr/bin/env node
// Instagram @aluma.il, серія 2 (№35): пости 1080×1350, історії 1080×1920, обкладинки highlights і Reels 9:16 з одного
// опису tools/ig_series.json. Числа й назви — catalog/products.json і content.json (як на сайті), кадри — рендери сайту
// (site/assets/products/), 3D-кадри Reel 01 — та сама модель, що в 3D-перегляді картки (tools/ig_3d.html). Знімок —
// Playwright без порту й без мережі (page.route), ролик — системний /usr/bin/ffmpeg (H.264, yuv420p, faststart, тиша).
//
//   nice -n 19 node tools/ig_series.js                         # усе → docs/ig/
//   nice -n 19 node tools/ig_series.js --only posts,reels      # частина: posts, stories, highlights, reels
//   nice -n 19 node tools/ig_series.js --out "$TMPDIR/ig"      # чернетка (та сама розкладка тек)
//
// Перевірки (вихід 1 при порушенні): контраст кожного тексту ≥ 4.5:1 до непрозорого тла, текст не вилазить за рядок
// і лежить у безпечній смузі формату (історія: 250–1620 px; Reel: 220–1480 px — нижче підпис і кнопки), кадри й шрифт
// сайту завантажені, лишених {змінних} нема, JPG ≤ 1 МБ (пост) / 500 КБ (історія), Reel 10–15 с і ≤ 8 МБ.
// «הדמיה» на кадрах серії 2 немає (слово власника 27.10); рендер у підписах фото клієнта не називаємо.
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const B = require('./creatives/build.js');

const { chromium } = require('@playwright/test');

const FORMATS = {
  post: { w: 1080, h: 1350, top: 0, bottom: 1350, maxBytes: 1024 * 1024 },
  story: { w: 1080, h: 1920, top: 250, bottom: 1620, maxBytes: B.MAX_BYTES },
  reel: { w: 1080, h: 1920, top: 220, bottom: 1480, maxBytes: B.MAX_BYTES },
  cover: { w: 1080, h: 1920, top: 0, bottom: 1920, maxBytes: B.MAX_BYTES },
};
const PARTS = ['posts', 'stories', 'highlights', 'reels'];
const FFMPEG = '/usr/bin/ffmpeg';
const FPS = 30;
const FADE = 0.6;
const REEL_SECONDS = [10, 15];
const REEL_MAX_BYTES = 8 * 1024 * 1024;
// 3D: та сама точка зйомки на всі стани (камера — за габаритом розкладеного), стіл у нижній половині кадру 9:16
const VIEW_3D = { az: 52, el: 26, margin: 0.03, shiftY: 0.3 };
const GL_ARGS = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];

function args(argv) {
  const out = { out: null, only: PARTS };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--out') out.out = path.resolve(argv[++i]);
    else if (argv[i] === '--only') out.only = argv[++i].split(',');
    else throw new Error(`невідомий аргумент: ${argv[i]}`);
  }
  const bad = out.only.filter((p) => !PARTS.includes(p));
  if (bad.length) throw new Error(`--only: невідомо ${bad.join(',')} (є ${PARTS.join(',')})`);
  return out;
}

const productImage = (rel) => {
  const file = path.join(B.ROOT, 'site', 'assets', 'products', rel);
  if (!fs.existsSync(file)) throw new Error(`нема кадру site/assets/products/${rel}`);
  return file;
};
const ils = (n) => `₪${B.money(n)}`;
// «מ־» — лише коли в товару кілька цін (як картка сайту, build.js creatives).
const fromPrice = (p) => `${new Set(p.sizes.map((s) => s.price_ils)).size > 1 ? 'מ־' : ''}<bdi dir="ltr">${ils(p.price_from_ils)}</bdi>`;

function varsOf(catalog, content) {
  const v = {};
  for (const p of catalog) {
    v[`${p.id}_name`] = B.esc(B.local(p.name, 'he', `${p.id}.name`));
    v[`${p.id}_tagline`] = B.esc(B.local(p.tagline, 'he', `${p.id}.tagline`));
    v[`${p.id}_from`] = ils(p.price_from_ils);
    for (const s of p.sizes) {
      if (`${p.id}_l${s.length_cm}` in v) continue;   // перша ширина довжини — ціна в TAVOR від ширини не залежить
      v[`${p.id}_l${s.length_cm}`] = s.length_cm;
      v[`${p.id}_x${s.length_cm}`] = s.extended_cm ?? '';
      v[`${p.id}_p${s.length_cm}`] = ils(s.price_ils);
    }
    if (p.seats) {
      v[`${p.id}_seats_min`] = p.seats.closed[0];
      v[`${p.id}_seats_closed_max`] = p.seats.closed[p.seats.closed.length - 1];
      v[`${p.id}_seats_max`] = p.seats.extended[p.seats.extended.length - 1];
    }
  }
  const n = (k) => {
    if (!(k in content)) throw new Error(`content.json: нема ${k}`);
    return Number(content[k]);
  };
  const area = ((content.OWNER_FACTS || {}).SHOWROOM_AREA_HE || '').trim();
  if (!area) throw new Error('content.json: нема OWNER_FACTS.SHOWROOM_AREA_HE');
  return Object.assign(v, {
    delivery: ils(n('DELIVERY_ILS')), delivery_assembly: ils(n('DELIVERY_ILS') + n('ASSEMBLY_ILS')), pickup: ils(n('PICKUP_ILS')),
    assembly_min: n('ASSEMBLY_MIN'), warranty: n('WARRANTY_MONTHS'), top_mm: n('TOP_MM'), veneer_mm: n('VENEER_MM'),
    board_mm: n('BOARD_MM'), insert_cm: n('INSERT_CM'), installments: n('INSTALLMENTS'), series_size: n('SERIES_SIZE'),
    area: B.esc(area),
  });
}

function filler(vars) {
  return (tpl) => {
    const out = B.fill(tpl || '', vars);
    if (/\{\w+\}/.test(out)) throw new Error(`лишилась змінна: ${out}`);
    return out;
  };
}

function page(fonts, f, body, extraCss = '') {
  return `<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><style>
${fonts.css}
:root { --paper: #F6F1E9; --ink: #211C17; --muted: #5E554C; --oak-deep: #7A5534; --dark: #1F1A15; --cream: #F6F1E9; --line: #DDD3C4;
  --serif: ${fonts.serif}; --sans: "IBM Plex Sans Hebrew", Arial, sans-serif; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: ${f.w}px; height: ${f.h}px; background: var(--paper); overflow: hidden; }
body { font-family: var(--sans); color: var(--ink); -webkit-font-smoothing: antialiased; }
.canvas { position: relative; width: ${f.w}px; height: ${f.h}px; overflow: hidden; background: var(--paper); }
.media { position: absolute; left: 0; right: 0; top: 0; overflow: hidden; }
.media img { width: 100%; height: 100%; object-fit: cover; display: block; }
.panel { position: absolute; left: 48px; right: 48px; background: var(--paper); border-radius: 12px;
  padding: 36px 52px; display: flex; flex-direction: column; gap: 12px; }
.brand { font: 600 24px/1 var(--sans); letter-spacing: .32em; color: var(--oak-deep); }
.headline { font: 500 62px/1.12 var(--serif); color: var(--ink); text-wrap: balance; }
.sub { font: 400 32px/1.3 var(--sans); color: var(--muted); }
.foot { font: 400 26px/1.35 var(--sans); color: var(--muted); border-top: 1px solid var(--line); padding-top: 14px; margin-top: 6px; }
.rows { display: grid; grid-template-columns: max-content 1fr; column-gap: 28px; row-gap: 14px; align-items: baseline; }
.rows dt { font: 600 28px/1.3 var(--sans); color: var(--oak-deep); }
.rows dd { font: 400 28px/1.3 var(--sans); color: var(--ink); }
.steps { display: flex; flex-direction: column; gap: 18px; }
.step { display: flex; gap: 22px; align-items: center; }
.num { flex: none; width: 64px; height: 64px; border-radius: 50%; background: var(--dark); color: var(--cream);
  font: 600 32px/64px var(--sans); text-align: center; }
.step b { display: block; font: 600 34px/1.2 var(--sans); color: var(--ink); }
.step span { display: block; font: 400 27px/1.3 var(--sans); color: var(--muted); }
.cta { position: absolute; top: 1500px; left: 50%; transform: translateX(-50%); white-space: nowrap;
  background: var(--dark); color: var(--cream); font: 600 36px/1 var(--sans); padding: 26px 40px; border-radius: 999px; }
.chip { position: absolute; right: 24px; bottom: 20px; background: var(--paper); color: var(--ink); border-radius: 6px;
  padding: 12px 18px; font: 600 28px/1.15 var(--sans); }
.chip small { display: block; font: 400 24px/1.2 var(--sans); color: var(--muted); }
${extraCss}
</style></head><body><div class="canvas">${body}</div></body></html>`;
}

// Кадр → { html, files }: files — карта /img/<n> → файл на диску для page.route.
function frameHtml(ctx, fmt, item) {
  const { cfg, fonts, t, byId } = ctx;
  const f = FORMATS[fmt];
  const files = [];
  const img = (file, pos = '50% 50%') => { files.push(file); return `<img style="object-position:${pos}" src="${B.ORIGIN}/img/${files.length - 1}" alt="">`; };
  const brand = `<div class="brand" data-text>${B.esc(cfg.brand)}</div>`;
  const head = `${brand}<h1 class="headline" data-text>${t(item.headline)}</h1>` + (item.sub ? `<p class="sub" data-text>${t(item.sub)}</p>` : '');
  const foot = item.foot ? `<p class="foot" data-text>${t(item.foot)}</p>` : '';
  const cta = fmt === 'story' ? `<div class="cta" data-text>${B.esc(cfg.cta)}</div>` : '';
  const rows = () => `<dl class="rows">${item.rows.map(([a, b]) => `<dt data-text>${t(a)}</dt><dd data-text>${t(b)}</dd>`).join('')}</dl>`;
  const steps = () => `<div class="steps">${item.rows.map(([a, b], i) => `<div class="step"><div class="num" data-text>${i + 1}</div><div>` +
    `<b data-text>${t(a)}</b>${b ? `<span data-text>${t(b)}</span>` : ''}</div></div>`).join('')}</div>`;

  if (fmt === 'cover') {
    // Обкладинка highlights: суцільний колір, одне слово в центрі (Instagram обрізає коло по центру кадру).
    const css = `.canvas { background: ${item.bg}; display: flex; align-items: center; justify-content: center; }
.word { font: 600 150px/1 var(--sans); color: var(--cream); background: ${item.bg}; }`;
    return { html: page(fonts, f, `<div class="word" data-text>${B.esc(item.word)}</div>`, css), files };
  }
  if (item.kind === 'photo') {
    if (fmt === 'post') {
      const body = `<div class="media" style="height:${f.h - 400}px">${img(productImage(item.image), item.pos)}</div>` +
        `<div class="panel" style="left:0;right:0;bottom:0;border-radius:0;padding:36px 64px 40px">${head}${foot}</div>`;
      return { html: page(fonts, f, body), files };
    }
    const body = `<div class="media" style="bottom:0">${img(productImage(item.image), item.pos)}</div>` +
      `<div class="panel" style="top:1060px">${head}${foot}</div>${cta}`;
    return { html: page(fonts, f, body), files };
  }
  if (item.kind === 'list' || item.kind === 'steps') {
    const content = item.kind === 'list' ? rows() : steps();
    if (fmt === 'post') {
      const mediaH = item.kind === 'list' && item.rows.length > 4 ? 380 : 470;
      const body = `<div class="media" style="height:${mediaH}px">${img(productImage(item.image), item.pos)}</div>` +
        `<div class="panel" style="left:0;right:0;top:${mediaH}px;bottom:0;border-radius:0;padding:40px 64px;gap:22px">${head}${content}${foot}</div>`;
      return { html: page(fonts, f, body), files };
    }
    // історія: крупніше, щоб список заповнив екран телефона між кадром і кнопкою
    const css = `.rows dt, .rows dd { font-size: 38px; } .rows { row-gap: 24px; } .steps { gap: 30px; }
.num { width: 84px; height: 84px; font-size: 40px; line-height: 84px; } .step b { font-size: 46px; } .step span { font-size: 32px; }
.headline { font-size: 72px; }`;
    const body = `<div class="media" style="height:1000px">${img(productImage(item.image), item.pos)}</div>` +
      `<div class="panel" style="top:${item.kind === 'steps' ? 790 : 880}px;gap:30px">${head}${content}${foot}</div>${cta}`;
    return { html: page(fonts, f, body, css), files };
  }
  if (item.kind === 'trio') {
    // Три предмети: перший на всю ширину, два під ним; на кожному — назва і ціна, як на картці каталогу.
    const tiles = item.products.map((id) => {
      const p = byId[id];
      if (!p) throw new Error(`${item.id}: нема товару ${id}`);
      return `<div class="tile">${img(productImage(`${id}/${item.image}`))}<div class="chip" data-text>${B.esc(B.local(p.name, 'he', `${id}.name`))}` +
        `<small data-text>${fromPrice(p)}</small></div></div>`;
    }).join('');
    const gridH = fmt === 'post' ? f.h - 330 : 1040;
    const css = `.grid { position: absolute; top: 0; left: 0; right: 0; height: ${gridH}px; display: grid; gap: 6px;
  grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-rows: minmax(0, 1.15fr) minmax(0, 1fr); }
.tile { position: relative; overflow: hidden; min-height: 0; } .tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
.tile:first-child { grid-column: 1 / -1; }`;
    const panel = fmt === 'post'
      ? `<div class="panel" style="left:0;right:0;bottom:0;top:${gridH}px;border-radius:0;padding:36px 64px">${head}${foot}</div>`
      : `<div class="panel" style="top:1060px">${head}${foot}</div>${cta}`;
    return { html: page(fonts, f, `<div class="grid">${tiles}</div>${panel}`, css), files };
  }
  if (item.kind === 'reelphoto' || item.kind === '3d') {
    // Reel: текст угорі (нижче — підпис і кнопки Instagram), кадр під ним; 3D — на всю висоту, стіл у нижній половині.
    const media = item.kind === '3d'
      ? `<div class="media" style="bottom:0">${img(item.file)}</div>`
      : `<div class="media" style="top:560px;height:1000px">${img(item.file, item.pos)}</div>`;
    const body = `${media}<div class="panel" style="top:250px">${head}</div>`;
    return { html: page(fonts, f, body, '.headline { font-size: 88px; } .sub { font-size: 40px; } .brand { font-size: 28px; }'), files };
  }
  if (item.kind === 'card') {
    const list = (item.rows || []).length ? `<div class="sizes">${item.rows.map((r) => `<p data-text>${t(r)}</p>`).join('')}</div>` : '';
    const css = `.card { position: absolute; top: 420px; left: 80px; right: 80px; display: flex; flex-direction: column; gap: 26px; }
.card .headline { font-size: 84px; } .sizes { display: flex; flex-direction: column; gap: 18px; border-top: 1px solid var(--line); padding-top: 26px; }
.sizes p { font: 600 44px/1.2 var(--sans); color: var(--ink); } .card .sub { font-size: 36px; }
.url { position: absolute; top: 1330px; left: 80px; right: 80px; font: 600 40px/1.2 var(--sans); color: var(--oak-deep); }`;
    const body = `<div class="card">${brand}<h1 class="headline" data-text>${t(item.headline)}</h1>${list}` +
      `<p class="sub" data-text>${t(item.sub)}</p></div><div class="url" data-text>${B.esc(cfg.cta)}</div>`;
    return { html: page(fonts, f, body, css), files };
  }
  throw new Error(`${item.id || '?'}: невідомий kind ${item.kind}`);
}

// У сторінці: контраст кожного тексту до непрозорого тла, межі, переповнення, кадри, шрифт.
function measure() {
  const lum = (c) => {
    const [r, g, b] = c.slice(0, 3).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const rgba = (s) => (s.match(/[\d.]+/g) || []).map(Number).concat([1]).slice(0, 4);
  const bgOf = (el) => {
    for (let n = el; n; n = n.parentElement) {
      const c = rgba(getComputedStyle(n).backgroundColor);
      if (c[3] >= 0.999) return c;
      if (c[3] > 0) return null;
    }
    return null;
  };
  const texts = [...document.querySelectorAll('[data-text]')].map((el) => {
    const fg = rgba(getComputedStyle(el).color), bg = bgOf(el);
    const [a, b] = bg ? [lum(fg), lum(bg)].sort((x, y) => y - x) : [0, 0];
    const r = el.getBoundingClientRect();
    return { text: el.textContent.trim().slice(0, 40), contrast: bg ? (a + 0.05) / (b + 0.05) : 0,
      top: r.top, bottom: r.bottom, left: r.left, right: r.right, overflow: el.scrollWidth > el.clientWidth + 1 };
  });
  // жоден текст не налазить на кнопку історії
  const cta = document.querySelector('.cta');
  const c = cta && cta.getBoundingClientRect();
  const clash = c ? texts.filter((x) => x.text !== cta.textContent.trim().slice(0, 40) && x.bottom > c.top && x.top < c.bottom &&
    x.left < c.right && x.right > c.left).map((x) => x.text) : [];
  return { texts, clash, imagesOk: [...document.images].every((i) => i.complete && i.naturalWidth > 0),
    // жодне обличчя не впало, і хоч одне обличчя Plex Hebrew справді завантажене (вага — яка є на кадрі)
    fontsOk: ![...document.fonts].some((f) => f.status === 'error') &&
      [...document.fonts].some((f) => f.family.includes('IBM Plex Sans Hebrew') && f.status === 'loaded') };
}

async function route(pg, files) {
  await pg.route('**/*', (r) => {
    const url = new URL(r.request().url());
    if (url.origin !== B.ORIGIN) return r.abort();
    let file = null;
    const m = url.pathname.match(/^\/img\/(\d+)$/);
    if (m) file = files[Number(m[1])];
    else if (url.pathname.startsWith('/fonts/')) file = path.join(B.ROOT, 'site', 'assets', 'fonts', path.basename(url.pathname));
    if (!file || !fs.existsSync(file)) return r.fulfill({ status: 404, body: '' });
    return r.fulfill({ status: 200, contentType: B.TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', body: fs.readFileSync(file) });
  });
}

async function render(browser, ctx, fmt, item, file) {
  const f = FORMATS[fmt];
  const { html, files } = frameHtml(ctx, fmt, item);
  const pg = await browser.newPage({ viewport: { width: f.w, height: f.h }, deviceScaleFactor: 1, locale: 'he-IL' });
  await route(pg, files);
  await pg.goto(B.ORIGIN + '/');
  await pg.setContent(html, { waitUntil: 'load' });
  await pg.evaluate(() => document.fonts.ready);
  const m = await pg.evaluate(measure);
  const shot = await B.shoot(pg, file);
  await pg.close();
  const problems = [];
  for (const x of m.texts) {
    if (x.contrast < B.MIN_CONTRAST) problems.push(`контраст ${x.contrast.toFixed(2)} «${x.text}»`);
    if (x.top < f.top - 0.5 || x.bottom > f.bottom + 0.5 || x.left < 0 || x.right > f.w) problems.push(`поза безпечною смугою «${x.text}»`);
    if (x.overflow) problems.push(`не влазить «${x.text}»`);
  }
  if (!m.imagesOk) problems.push('кадр не завантажився');
  if (!m.fontsOk) problems.push('шрифт сайту не завантажився');
  m.clash.forEach((x) => problems.push(`налазить на кнопку «${x}»`));
  if (shot.bytes > f.maxBytes) problems.push(`${Math.round(shot.bytes / 1024)} КБ > ${Math.round(f.maxBytes / 1024)}`);
  return { problems, bytes: shot.bytes, minContrast: Math.min(...m.texts.map((x) => x.contrast)) };
}

// 3D-кадри TAVOR (tools/ig_3d.html + three з site/assets/vendor) → PNG на диску, по одному на стан.
async function render3d(states, size, dir) {
  const browser = await chromium.launch({ args: GL_ARGS });
  const out = {};
  try {
    const pg = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    await pg.route('**/*', (r) => {
      const url = new URL(r.request().url());
      if (url.origin !== B.ORIGIN) return r.abort();
      const file = url.pathname === '/' ? path.join(__dirname, 'ig_3d.html') : path.join(B.ROOT, 'site', url.pathname);
      if (!file.startsWith(path.join(B.ROOT, 'site')) && url.pathname !== '/') return r.fulfill({ status: 404, body: '' });
      if (!fs.existsSync(file)) return r.fulfill({ status: 404, body: '' });
      const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.js') ? 'text/javascript' : B.TYPES[path.extname(file)] || 'application/octet-stream';
      return r.fulfill({ status: 200, contentType: type, body: fs.readFileSync(file) });
    });
    await pg.goto(B.ORIGIN + '/');
    await pg.waitForFunction(() => window.__ready, null, { timeout: 60000 });
    for (const state of states) {
      const url = await pg.evaluate((job) => window.shot(job), { product: 'tavor', size, state, w: 1080, h: 1920, view: VIEW_3D, bg: '#F6F1E9' });
      out[state] = path.join(dir, `3d-${state}.png`);
      fs.writeFileSync(out[state], Buffer.from(url.split(',')[1], 'base64'));
    }
  } finally {
    await browser.close();
  }
  return out;
}

function ffmpeg(argv) {
  const r = spawnSync(FFMPEG, ['-hide_banner', '-loglevel', 'error', '-y', ...argv], { stdio: ['ignore', 'ignore', 'pipe'] });
  if (r.status !== 0) throw new Error(`ffmpeg: ${String(r.stderr).slice(0, 400)}`);
}

// Кадри → ролик: кожен кадр seconds с, між ними плавний перехід FADE; тиха AAC-доріжка (без чужої музики).
function encode(shots, file) {
  const inputs = [];
  shots.forEach((s) => inputs.push('-loop', '1', '-framerate', String(FPS), '-t', String(s.seconds + FADE), '-i', s.file));
  const duration = shots.reduce((a, s) => a + s.seconds, 0) + FADE;
  inputs.push('-f', 'lavfi', '-t', duration.toFixed(2), '-i', 'anullsrc=r=48000:cl=stereo');
  const chain = [];
  let prev = '[0:v]', offset = 0;
  for (let i = 1; i < shots.length; i++) {
    offset += shots[i - 1].seconds;
    const out = i === shots.length - 1 ? '[x]' : `[v${i}]`;
    chain.push(`${prev}[${i}:v]xfade=transition=fade:duration=${FADE}:offset=${offset.toFixed(2)}${out}`);
    prev = out;
  }
  chain.push(`${shots.length > 1 ? '[x]' : '[0:v]'}format=yuv420p[v]`);
  ffmpeg([...inputs, '-filter_complex', chain.join(';'), '-map', '[v]', '-map', `${shots.length}:a`,
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '22', '-profile:v', 'high', '-r', String(FPS),
    '-c:a', 'aac', '-b:a', '32k', '-shortest', '-movflags', '+faststart', '-threads', '1', file]);
  return { bytes: fs.statSync(file).size, duration: Number(duration.toFixed(2)) };
}

// Кадри Reel: явний список, «@tones» (той самий стіл у п'яти тонах) або «@series» (усі предмети каталогу) + фінальна картка.
function reelFrames(reel, ctx, threeD) {
  const { catalog, byId } = ctx;
  if (Array.isArray(reel.frames)) {
    return reel.frames.map((fr) => (fr.kind === '3d' ? Object.assign({}, fr, { file: threeD[fr.state] }) : fr));
  }
  let frames;
  if (reel.frames === '@tones') {
    const p = byId.tavor;
    frames = p.finishes.map((fin) => ({ kind: 'reelphoto', file: productImage(`tavor/finish-${fin.id}-1600.jpg`), pos: '50% 45%',
      seconds: reel.seconds, headline: B.esc(B.local(fin.name, 'he', 'tavor.finish')), sub: '{tavor_name} · פורניר אלון' }));
  } else if (reel.frames === '@series') {
    frames = catalog.map((p) => ({ kind: 'reelphoto', file: productImage(`${p.id}/life-1600.webp`), seconds: reel.seconds,
      headline: `{${p.id}_name}`, sub: `{${p.id}_tagline} · ${fromPrice(p)}` }));
  } else {
    throw new Error(`${reel.id}: невідомі кадри ${reel.frames}`);
  }
  return frames.concat(reel.card ? [reel.card] : []);
}

async function main() {
  const opts = args(process.argv.slice(2));
  const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, 'ig_series.json'), 'utf8'));
  const catalog = JSON.parse(fs.readFileSync(path.join(B.ROOT, 'catalog', 'products.json'), 'utf8'));
  const content = JSON.parse(fs.readFileSync(path.join(B.ROOT, 'content.json'), 'utf8'));
  const byId = Object.fromEntries(catalog.map((p) => [p.id, p]));
  const ctx = { cfg, catalog, byId, fonts: B.fontFaces('he'), t: filler(varsOf(catalog, content)) };
  const root = opts.out || path.join(B.ROOT, 'docs', 'ig');
  const dirs = { posts: root, stories: path.join(root, 'stories'), highlights: path.join(root, 'highlights'), reels: path.join(root, 'reels') };
  const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'ig-series-'));
  const failures = [];
  const report = [];
  const log = (part, id, r, extra = '') => {
    r.problems.forEach((p) => failures.push(`${part}/${id}: ${p}`));
    report.push({ part, id, bytes: r.bytes, min_contrast: Number(r.minContrast.toFixed(2)) });
    console.log(`${r.problems.length ? '✗' : '✓'} ${part}/${id}  ${Math.round(r.bytes / 1024)} KB  контраст ≥ ${r.minContrast.toFixed(2)}${extra}`);
  };
  try {
    const threeD = opts.only.includes('reels') && cfg.reels.some((r) => Array.isArray(r.frames) && r.frames.some((f) => f.kind === '3d'))
      ? await render3d(['closed', 'half', 'open'], Object.assign({ height_cm: 75 }, byId.tavor.sizes.find((s) => s.length_cm === 200 && s.width_cm === 100)), tmp)
      : {};
    const browser = await chromium.launch();
    try {
      for (const part of opts.only) dirs[part] && fs.mkdirSync(dirs[part], { recursive: true });
      if (opts.only.includes('posts')) {
        for (const item of cfg.posts) log('posts', item.id, await render(browser, ctx, 'post', item, path.join(dirs.posts, `${item.id}.jpg`)));
      }
      if (opts.only.includes('stories')) {
        for (const item of cfg.stories) log('stories', item.id, await render(browser, ctx, 'story', item, path.join(dirs.stories, `${item.id}.jpg`)));
      }
      if (opts.only.includes('highlights')) {
        for (const item of cfg.highlights) log('highlights', item.id, await render(browser, ctx, 'cover', item, path.join(dirs.highlights, `${item.id}.jpg`)));
      }
      if (opts.only.includes('reels')) {
        for (const reel of cfg.reels) {
          const shots = [];
          const frames = reelFrames(reel, ctx, threeD);
          for (let i = 0; i < frames.length; i++) {
            const file = path.join(tmp, `${reel.id}-${i}.jpg`);
            const r = await render(browser, ctx, 'reel', frames[i], file);
            r.problems.forEach((p) => failures.push(`reels/${reel.id}[${i}]: ${p}`));
            shots.push({ file, seconds: frames[i].seconds });
          }
          const v = encode(shots, path.join(dirs.reels, `${reel.id}.mp4`));
          if (v.duration < REEL_SECONDS[0] || v.duration > REEL_SECONDS[1]) failures.push(`reels/${reel.id}: ${v.duration} с поза ${REEL_SECONDS.join('–')}`);
          if (v.bytes > REEL_MAX_BYTES) failures.push(`reels/${reel.id}: ${Math.round(v.bytes / 1024)} КБ > 8 МБ`);
          // обкладинка Reel у стрічці — останній кадр (картка з текстом), поруч із роликом
          fs.copyFileSync(shots[shots.length - 1].file, path.join(dirs.reels, `${reel.id}.jpg`));
          report.push({ part: 'reels', id: reel.id, bytes: v.bytes, seconds: v.duration, frames: shots.length });
          console.log(`✓ reels/${reel.id}  ${Math.round(v.bytes / 1024)} KB  ${v.duration} с  кадрів ${shots.length}`);
        }
      }
    } finally {
      await browser.close();
    }
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  if (failures.length) {
    console.error('Перевірки не пройдено:\n  ' + failures.join('\n  '));
    process.exit(1);
  }
  console.log(`готово: ${report.length} файлів → ${path.relative(B.ROOT, root) || root}`);
}

main().catch((e) => { console.error(e.message || e); process.exit(1); });
