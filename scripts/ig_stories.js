#!/usr/bin/env node
// Історії @aluma.il 1080×1920 → docs/ig/stories/NN-<id>.jpg (+ .mp4 для «закритий → відкритий»).
// Слова — scripts/ig_stories.json, цифри й назви — catalog/products.json, кадри — рендери сайту (site/assets/products/),
// шрифти — ті самі файли, що на вітрині (через tools/creatives/build.js fontFaces). Знімок — Playwright без порту й
// без мережі (page.route), ролик — системний /usr/bin/ffmpeg (H.264, yuv420p, faststart, тиха AAC-доріжка).
//
//   nice -n 19 node scripts/ig_stories.js                    # → docs/ig/stories/
//   nice -n 19 node scripts/ig_stories.js --out "$TMPDIR/st" # чернетка
//
// Перевірки (вихід 1 при порушенні): контраст кожного тексту ≥ 4.5:1 до непрозорого тла, «הדמיה» видима, шрифт сайту
// й кадри завантажені, увесь текст у безпечній смузі історії (нижче 250 px — шапка з аватаром, вище 1620 px — поле
// відповіді), JPG ≤ 500 КБ, MP4 ≤ 60 с і ≤ 4 МБ. Підпису й стікерів API історій не приймає — усе на кадрі.
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const B = require('../tools/creatives/build.js');

const { chromium } = require('@playwright/test');

const W = 1080;
const H = 1920;
const SAFE_TOP = 250;
const SAFE_BOTTOM = 1620;
const MAX_VIDEO_BYTES = 4 * 1024 * 1024;
const FFMPEG = '/usr/bin/ffmpeg';
// Ролик: кадр 1 — HOLD с, перехід FADE с, кадр 2 — HOLD + 1 с (на ньому головний текст).
const HOLD = 3;
const FADE = 1;
const FPS = 30;

function args(argv) {
  const out = { out: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--out') out.out = path.resolve(argv[++i]);
    else throw new Error(`невідомий аргумент: ${argv[i]}`);
  }
  return out;
}

const productImage = (rel) => {
  const file = path.join(B.ROOT, 'site', 'assets', 'products', rel);
  if (!fs.existsSync(file)) throw new Error(`нема кадру site/assets/products/${rel}`);
  return file;
};

// Перша візуалізація товару з каталогу (як build.js imageFor): /assets/… → site/assets/….
function catalogImage(p) {
  const img = (p.images || []).find((i) => i.kind === 'visualization');
  const file = img && path.join(B.ROOT, 'site', img.src.replace(/^\//, ''));
  if (!file || !fs.existsSync(file)) throw new Error(`${p.id}: нема візуалізації в каталозі`);
  return file;
}

function varsOf(p, catalog) {
  const he = (f) => B.local(f, 'he', p ? p.id : 'catalog');
  const v = { n_products: catalog.length };
  if (p) {
    const s = p.sizes[0];
    Object.assign(v, { name: B.esc(he(p.name)), tagline: B.esc(he(p.tagline)), length: s.length_cm, extended: s.extended_cm ?? '',
      n_tones: (p.finishes || []).length, seats: p.seats ? p.seats.closed[0] : '', seats_extended: p.seats ? p.seats.extended[0] : '' });
  }
  return v;
}

function text(tpl, p, catalog) {
  if (tpl === '@material') return B.esc(B.local(p.material, 'he', `${p.id}.material`).split(';')[0]);
  if (tpl === '@names') return catalog.map((x) => B.esc(B.local(x.name, 'he', `${x.id}.name`))).join(' · ') + ' — פורניר אלון';
  const out = B.fill(tpl, varsOf(p, catalog));
  if (/\{\w+\}/.test(out)) throw new Error(`лишився плейсхолдер: ${out}`);
  return out;
}

function page(fonts, body, extraCss = '') {
  return `<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><style>
${fonts.css}
:root { --paper: #F6F1E9; --ink: #211C17; --muted: #5E554C; --oak-deep: #7A5534; --dark: #1F1A15; --cream: #F6F1E9;
  --serif: ${fonts.serif}; --sans: "IBM Plex Sans Hebrew", Arial, sans-serif; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: ${W}px; height: ${H}px; background: var(--paper); overflow: hidden; }
body { font-family: var(--sans); color: var(--ink); -webkit-font-smoothing: antialiased; }
.canvas { position: relative; width: ${W}px; height: ${H}px; overflow: hidden; background: var(--paper); }
.media { position: absolute; inset: 0; overflow: hidden; }
.media img { width: 100%; height: 100%; object-fit: cover; display: block; }
/* «הדמיה» — непрозора, нижче шапки історії (аватар, смужки прогресу ~ 250 px). */
.mark { position: absolute; top: 270px; left: 40px; padding: 8px 18px; border-radius: 4px;
  background: var(--dark); color: var(--cream); font: 600 28px/1.2 var(--sans); letter-spacing: .02em; }
.panel { position: absolute; left: 48px; right: 48px; top: 1060px; background: var(--paper); border-radius: 12px;
  padding: 40px 52px; display: flex; flex-direction: column; gap: 14px; }
.brand { font: 600 24px/1 var(--sans); letter-spacing: .32em; color: var(--oak-deep); }
.headline { font: 500 66px/1.12 var(--serif); color: var(--ink); text-wrap: balance; }
.sub { font: 400 32px/1.3 var(--sans); color: var(--muted); }
.cta { position: absolute; top: 1500px; left: 50%; transform: translateX(-50%); white-space: nowrap;
  background: var(--dark); color: var(--cream); font: 600 36px/1 var(--sans); padding: 26px 40px; border-radius: 999px; }
${extraCss}
</style></head><body><div class="canvas">${body}</div></body></html>`;
}

const panelHtml = (cfg, headline, sub) => `<div class="panel"><div class="brand" data-text>${B.esc(cfg.brand)}</div>` +
  `<h1 class="headline" data-text>${headline}</h1><p class="sub" data-text>${sub}</p></div>`;
const chrome = (cfg) => `<div class="mark" data-text>${B.esc(cfg.mark)}</div><div class="cta" data-text>${B.esc(cfg.cta)}</div>`;

// Кадр історії → { html, files }: files — карта /img/<n> → шлях на диску для page.route.
function frameHtml(cfg, fonts, story, frame, catalog, byId) {
  const p = story.product ? byId[story.product] : null;
  const files = [];
  const img = (file, cls = '', style = '') => { files.push(file); return `<img class="${cls}" style="${style}" src="${B.ORIGIN}/img/${files.length - 1}" alt="">`; };
  if (story.kind === 'video') {
    // scale 1.03 — у open-9x16 TAVOR по лівому краю темна смуга рендера; масштаб однаковий на обох кадрах, щоб перехід не стрибав.
    const body = `<div class="media">${img(productImage(frame.image), '', 'transform:scale(1.03)')}</div>${chrome(cfg)}` +
      panelHtml(cfg, text(frame.headline, p, catalog), text(frame.sub, p, catalog));
    return { html: page(fonts, body), files };
  }
  if (story.kind === 'detail') {
    // Крупний план на верхні 1040 px (рендер 4:3 обрізано по куту стільниці), картка на папері нижче.
    const body = `<div class="media" style="bottom:${H - 1040}px">${img(productImage(story.image), '', 'object-position:72% 50%')}</div>` +
      `${chrome(cfg)}${panelHtml(cfg, text(story.headline, p, catalog), text(story.sub, p, catalog))}`;
    return { html: page(fonts, body), files };
  }
  if (story.kind === 'tones') {
    // П'ять смуг — той самий стіл у кожному тоні каталогу (рендери finish-<id>-1600.jpg), підпис тону на смузі.
    const bands = p.finishes.map((f) => `<div class="band">${img(productImage(`${p.id}/finish-${f.id}-1600.jpg`), '', 'object-position:50% 42%')}` +
      `<span class="tone" data-text>${B.esc(B.local(f.name, 'he', `${p.id}.finish`))}</span></div>`).join('');
    const css = `.head { position: absolute; top: 250px; left: 48px; right: 48px; display: flex; flex-direction: column; gap: 10px; }
.bands { position: absolute; top: 470px; left: 0; right: 0; display: grid; gap: 6px; grid-template-rows: repeat(${p.finishes.length}, 186px); }
.band { position: relative; overflow: hidden; } .band img { width: 100%; height: 100%; object-fit: cover; display: block; }
.tone { position: absolute; right: 40px; bottom: 18px; background: var(--paper); color: var(--ink); font: 600 30px/1 var(--sans); padding: 12px 20px; border-radius: 4px; }
.mark { top: 490px; }`;
    const body = `<div class="head"><h1 class="headline" data-text>${text(story.headline, p, catalog)}</h1>` +
      `<p class="sub" data-text>${text(story.sub, p, catalog)}</p></div><div class="bands">${bands}</div>${chrome(cfg)}`;
    return { html: page(fonts, body, css), files };
  }
  if (story.kind === 'collection') {
    // Усі товари каталогу: перший на всю ширину, решта сіткою 2×2 у верхніх 1040 px.
    const tiles = catalog.map((x) => img(catalogImage(x))).join('');
    const css = `.grid { position: absolute; inset: 0 0 ${H - 1040}px 0; display: grid; gap: 6px; grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-rows: minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, 1fr); }
.grid img { width: 100%; height: 100%; min-height: 0; object-fit: cover; display: block; } .grid img:first-child { grid-column: 1 / -1; }`;
    const body = `<div class="grid">${tiles}</div>${chrome(cfg)}${panelHtml(cfg, text(story.headline, null, catalog), text(story.sub, null, catalog))}`;
    return { html: page(fonts, body, css), files };
  }
  throw new Error(`${story.id}: невідомий kind ${story.kind}`);
}

// У сторінці: контраст кожного тексту до непрозорого тла, межі тексту, позначка, кадри, шрифт.
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
  const mark = document.querySelector('.mark');
  const mbox = mark.getBoundingClientRect();
  // Позначку не перекриває нічого: точка в її центрі належить їй.
  const markOnTop = document.elementFromPoint(mbox.left + mbox.width / 2, mbox.top + mbox.height / 2) === mark;
  return { texts, mark: mark.textContent.trim(), markVisible: mbox.width > 0 && markOnTop,
    imagesOk: [...document.images].every((i) => i.complete && i.naturalWidth > 0),
    fontsOk: ![...document.fonts].some((f) => f.status === 'error') && document.fonts.check('600 28px "IBM Plex Sans Hebrew"', 'הדמיה') };
}

function ffmpeg(argv) {
  const r = spawnSync(FFMPEG, ['-hide_banner', '-loglevel', 'error', '-y', ...argv], { stdio: ['ignore', 'ignore', 'pipe'] });
  if (r.status !== 0) throw new Error(`ffmpeg: ${String(r.stderr).slice(0, 400)}`);
}

// Два кадри → ролик із плавним переходом; CRF підбирається, доки файл не влізе в 4 МБ.
function encode(a, b, file) {
  const duration = HOLD + FADE + HOLD + 1;
  for (let crf = 20; crf <= 32; crf += 3) {
    ffmpeg(['-loop', '1', '-framerate', String(FPS), '-t', String(HOLD + FADE), '-i', a,
      '-loop', '1', '-framerate', String(FPS), '-t', String(HOLD + 1 + FADE), '-i', b,
      '-f', 'lavfi', '-t', String(duration), '-i', 'anullsrc=r=48000:cl=stereo',
      '-filter_complex', `[0:v][1:v]xfade=transition=fade:duration=${FADE}:offset=${HOLD},format=yuv420p[v]`,
      '-map', '[v]', '-map', '2:a', '-c:v', 'libx264', '-preset', 'slow', '-crf', String(crf), '-profile:v', 'high',
      '-r', String(FPS), '-c:a', 'aac', '-b:a', '32k', '-shortest', '-movflags', '+faststart', '-threads', '1', file]);
    const bytes = fs.statSync(file).size;
    if (bytes <= MAX_VIDEO_BYTES || crf >= 32) return { bytes, crf, duration };
  }
  return null;
}

async function render(browser, cfg, fonts, story, frame, catalog, byId, file) {
  const { html, files } = frameHtml(cfg, fonts, story, frame, catalog, byId);
  const pg = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1, locale: 'he-IL' });
  await pg.route('**/*', (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== B.ORIGIN) return route.abort();
    let f = null;
    const m = url.pathname.match(/^\/img\/(\d+)$/);
    if (m) f = files[Number(m[1])];
    else if (url.pathname.startsWith('/fonts/')) f = path.join(B.ROOT, 'site', 'assets', 'fonts', path.basename(url.pathname));
    if (!f || !fs.existsSync(f)) return route.fulfill({ status: 404, body: '' });
    return route.fulfill({ status: 200, contentType: B.TYPES[path.extname(f).toLowerCase()] || 'application/octet-stream', body: fs.readFileSync(f) });
  });
  await pg.goto(B.ORIGIN + '/');
  await pg.setContent(html, { waitUntil: 'load' });
  await pg.evaluate(() => document.fonts.ready);
  const m = await pg.evaluate(measure);
  const shot = await B.shoot(pg, file);
  await pg.close();
  const problems = [];
  for (const t of m.texts) {
    if (t.contrast < B.MIN_CONTRAST) problems.push(`контраст ${t.contrast.toFixed(2)} «${t.text}»`);
    if (t.top < SAFE_TOP - 0.5 || t.bottom > SAFE_BOTTOM + 0.5 || t.left < 0 || t.right > W) problems.push(`поза безпечною смугою «${t.text}»`);
    if (t.overflow) problems.push(`не влазить «${t.text}»`);
  }
  if (m.mark !== cfg.mark || !m.markVisible) problems.push(`нема позначки «${cfg.mark}»`);
  if (!m.imagesOk) problems.push('кадр не завантажився');
  if (!m.fontsOk) problems.push('шрифт сайту не завантажився');
  if (shot.bytes > B.MAX_BYTES) problems.push(`${Math.round(shot.bytes / 1024)} КБ > 500`);
  return { problems, bytes: shot.bytes, quality: shot.quality, minContrast: Math.min(...m.texts.map((t) => t.contrast)) };
}

async function main() {
  const opts = args(process.argv.slice(2));
  const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, 'ig_stories.json'), 'utf8'));
  const catalog = JSON.parse(fs.readFileSync(path.join(B.ROOT, 'catalog', 'products.json'), 'utf8'));
  const byId = Object.fromEntries(catalog.map((p) => [p.id, p]));
  const outDir = opts.out || path.join(B.ROOT, 'docs', 'ig', 'stories');
  const fonts = B.fontFaces('he');
  fs.mkdirSync(outDir, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'ig-stories-'));
  const browser = await chromium.launch();
  const failures = [];
  const report = { generated_by: 'scripts/ig_stories.js', limits: { max_jpg_bytes: B.MAX_BYTES, max_mp4_bytes: MAX_VIDEO_BYTES,
    min_contrast: B.MIN_CONTRAST, safe_top: SAFE_TOP, safe_bottom: SAFE_BOTTOM }, stories: [] };
  try {
    for (const story of cfg.stories) {
      const frames = story.kind === 'video' ? story.frames : [null];
      const shots = [];
      for (let i = 0; i < frames.length; i++) {
        // Останній кадр — він же JPG історії (запасний варіант без ролика й обкладинка для звіту).
        const file = i === frames.length - 1 ? path.join(outDir, `${story.id}.jpg`) : path.join(tmp, `${story.id}-${i}.jpg`);
        const r = await render(browser, cfg, fonts, story, frames[i], catalog, byId, file);
        r.problems.forEach((p) => failures.push(`${story.id}[${i}]: ${p}`));
        shots.push({ file, ...r });
      }
      const last = shots[shots.length - 1];
      const item = { id: story.id, jpg: `${story.id}.jpg`, jpg_bytes: last.bytes, min_contrast: Number(Math.min(...shots.map((s) => s.minContrast)).toFixed(2)) };
      if (story.kind === 'video') {
        const v = encode(shots[0].file, last.file, path.join(outDir, `${story.id}.mp4`));
        if (v.bytes > MAX_VIDEO_BYTES) failures.push(`${story.id}.mp4: ${Math.round(v.bytes / 1024)} КБ > 4 МБ`);
        Object.assign(item, { mp4: `${story.id}.mp4`, mp4_bytes: v.bytes, crf: v.crf, duration: v.duration });
      }
      report.stories.push(item);
      console.log(`${shots.some((s) => s.problems.length) ? '✗' : '✓'} ${story.id}  ${Math.round(last.bytes / 1024)} KB${item.mp4 ? `  + mp4 ${Math.round(item.mp4_bytes / 1024)} KB ${item.duration} с` : ''}  контраст ≥ ${item.min_contrast}`);
    }
    fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  } finally {
    await browser.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  if (failures.length) {
    console.error('Перевірки не пройдено:\n  ' + failures.join('\n  '));
    process.exit(1);
  }
  console.log(`готово: ${report.stories.length} історій → ${path.relative(B.ROOT, outDir) || outDir}`);
}

main().catch((e) => { console.error(e.message || e); process.exit(1); });
