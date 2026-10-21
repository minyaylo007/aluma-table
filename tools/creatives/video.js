#!/usr/bin/env node
// Відео-креативи для Reels / Stories / стрічки (docs/META-TEST.md): 3 ролики × 1080×1920, 1080×1350 і 1080×1080 → docs/creatives/video/.
// Кадри й тексти — з catalog/products.json і tools/creatives/creatives.json (ті самі, що в статичних креативах);
// шаблон — tools/creatives/video.html. Кожен кадр малює window.render(t) і знімає Playwright (без порту й мережі),
// ролик збирає системний /usr/bin/ffmpeg (H.264, yuv420p, faststart, тиха AAC-доріжка).
//
//   nice -n 19 node tools/creatives/video.js                  # → docs/creatives/video/*.mp4, sheet.jpg, report.json
//   nice -n 19 node tools/creatives/video.js --only tavor --out "$TMPDIR/v"   # чернетка
//
// Перевірки на кадрах кожні 0.5 с, інакше вихід 1: «הדמיה» видно на кожному, текст не заходить у верхні й нижні 14 %
// (9:16, інтерфейс Reels), контраст кожного видимого тексту ≥ 4.5:1 до його тла, картка не переповнена,
// кадри й шрифти завантажені; файл ≤ 4 МБ.
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { ROOT, TYPES, esc, fontFaces, fill, priceVars, headlineOf } = require('./build');

process.env.PLAYWRIGHT_BROWSERS_PATH = process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/ihor/aluma-table/ms-playwright';
const { chromium } = require('@playwright/test');

const ORIGIN = 'https://creative.test';
const FFMPEG = '/usr/bin/ffmpeg';
const FPS = 30;
const MAX_BYTES = 4 * 1024 * 1024;
const MIN_CONTRAST = 4.5;
const SAFE = 0.14;            // Reels/Stories: верх і низ по 14 % — під інтерфейсом
const FADE = 0.6;
const FORMATS = [{ id: '9x16', width: 1080, height: 1920 }, { id: '4x5', width: 1080, height: 1350 },
  { id: '1x1', width: 1080, height: 1080 }];
const SHEET_AT = [0, 3, 6];   // секунди для листа кадрів

function args(argv) {
  const out = { out: null, only: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--out') out.out = path.resolve(argv[++i]);
    else if (argv[i] === '--only') out.only = argv[++i];
    else throw new Error(`невідомий аргумент: ${argv[i]}`);
  }
  return out;
}

const fileOf = (i) => path.join(ROOT, 'site', i.src.replace(/^\//, ''));
const visuals = (p) => (p.images || []).filter((i) => i.kind === 'visualization' && fs.existsSync(fileOf(i)));
const imagesOf = (p) => visuals(p).map(fileOf);
// 9:16: вертикальний рендер того самого ракурсу (<ракурс>-9x16.jpg поруч із кадром, сесія 2) — стіл цілком у смузі
// 300–1000 px, під карткою підлога; тоді кадр на все полотно. Нема такого — смуга 3:2 над карткою (video.html).
const tallOf = (file) => file.replace(/-\d+\.\w+$/, '-9x16.jpg');
const frameFor = (file, f) => (f.id === '9x16' && fs.existsSync(tallOf(file)) ? tallOf(file) : file);
// Крупний план (механізм, деталь) у 9:16 — теж на все полотно: ніжки там не потрібні, смуга лишила б порожнечу.
const fullIn = (file, f) => f.id === '9x16' && (frameFor(file, f) !== file || /^(mechanism|detail)-/.test(path.basename(file)));

// Розкладання результатом у перші 3 с (docs/META-TEST.md, розвідка Ad Library 21.10): якщо в каталозі є кадри
// «розкладений» і «механізм наполовину» — ролик іде розкладений → механізм → звичайний вигляд. Інакше — два перші кадри.
function storyOf(p) {
  const vs = visuals(p);
  const open = vs.find((i) => i.state === 'open');
  const half = vs.find((i) => i.view === 'mechanism' && i.state === 'half');
  const closed = vs.find((i) => i.state === 'closed');
  return open && half && closed ? [open, half, closed].map(fileOf) : null;
}
const at = (t) => `data-text data-at="${t}"`;

// Один товар (8 с): загальний кадр → деталь (або розкладений → механізм → звичайний, див. storyOf). Бренд і слоган — з першого кадру (його Meta бере обкладинкою),
// далі по черзі розмір, смуга «складено → розкладено» (числа каталогу), ціна, заклик.
function single(cfg, v, p) {
  const story = p.sizes[0].extended_cm ? storyOf(p) : null;
  // Розкладний без кадру механізму (SAHAR): другий кадр — розкладений, а не angle (у SAHAR це крупний план ніжки
  // без вертикального рендера, сесія 2, 21.10): ролик показує результат розкладання, у 9:16 обидва кадри вертикальні.
  const opened = p.sizes[0].extended_cm ? visuals(p).find((i) => i.state === 'open') : null;
  const imgs = story || (opened ? [imagesOf(p)[0], fileOf(opened)] : imagesOf(p).slice(0, 2));
  if (!imgs.length) throw new Error(`${v.id}: нема візуалізацій у каталозі`);
  const s = p.sizes[0];
  const duration = 8;
  let shots;
  if (story) {
    shots = [{ from: 0, to: 2.4, z: [1.0, 1.06], x: [0, -1] },
      { from: 2.4, to: 5.2, z: [1.02, 1.1], x: [1, 0] },
      { from: 5.2, to: duration, z: [1.04, 1.1], x: [0, -1] }];
  } else {
    // Розкладений кадр — з 3 с, наїзд слабкий, щоб овал (155) читався до кінця ролика (дирижер, 21.10).
    const half = imgs.length > 1 ? (opened ? 3.0 : 4.2) : duration;
    shots = [{ from: 0, to: half, z: [1.0, 1.08], x: [0, -1.5] }];
    if (imgs.length > 1) shots.push(opened ? { from: half, to: duration, z: [1.0, 1.04], x: [0, 0] } : { from: half, to: duration, z: [1.04, 1.12], x: [1, 0] });
  }
  // У «story» плашка «складено → розкладено» видна з першого кадру й доростає до розкладеного за першу секунду.
  const sizeAt = story ? -1 : 1.2;
  // Без story, але з розкладеним кадром — плашка доростає разом зі зміною кадру «складено → розкладено».
  const grow = story ? { from: 0.2, to: 1.4 } : opened ? { from: 2.6, to: 3.6 } : { from: 1.6, to: 3.0 };
  const sub = fill(v.sub, { length: esc(s.length_cm), extended: esc(s.extended_cm ?? '') });
  const size = s.extended_cm ? `<div class="size" ${at(sizeAt)}><div class="nums"><span>${esc(s.length_cm)}</span>` +
    `<span>${esc(s.extended_cm)}</span></div><div class="track"><div class="bar"></div></div></div>` : '';
  const card = `<div class="card"><div class="brand" ${at(-1)}>${esc(cfg.brand)}</div>` +
    `<h1 class="headline" ${at(-1)}>${headlineOf(v, [p])}</h1><p class="sub" ${at(0.6)}>${sub}</p>${size}` +
    `<div class="foot"><div class="price"><b ${at(3.4)}>${fill(v.price, priceVars([p], cfg))}</b>` +
    `<small ${at(3.4)}>${esc(cfg.price_note)} · ${esc(cfg.includes)}</small></div><div class="act"><div class="cta" ${at(4.6)}>${esc(cfg.cta)}</div>` +
    `<small class="cta-note" ${at(4.6)}>${esc(cfg.cta_note)}</small></div></div></div>`;
  const timeline = { duration, fade: FADE, shots, items: [],
    size: { ratio: s.extended_cm ? s.length_cm / s.extended_cm : 1, ...grow } };
  return { duration, imgs, card, timeline, products: [p.id] };
}

// Колекція (10 с): п'ять товарів по 1.5 с з назвою й ціною (з «מ־», якщо цін кілька), далі фінальна картка серії.
function collection(cfg, v, products) {
  const step = 1.5, duration = 10;
  const imgs = products.map((p) => imagesOf(p)[0]);
  if (imgs.some((f) => !f)) throw new Error(`${v.id}: не в усіх товарів є візуалізація`);
  const end = step * products.length;
  const shots = products.map((_, i) => ({ from: i * step, to: i === products.length - 1 ? duration : (i + 1) * step,
    z: [1.0, 1.06], x: [i % 2 ? 1 : -1, 0] }));
  const items = products.map((_, i) => ({ from: i * step, to: (i + 1) * step }));
  items.push({ from: end, to: duration });
  const rows = products.map((p) => `<div class="item"><div class="name" data-text>${esc(p.name.he)}</div>` +
    `<div class="line" data-text>${esc(p.tagline.he)}</div>` +
    `<div class="from" data-text>${fill(v.price, priceVars([p], cfg))}</div></div>`).join('');
  const last = `<div class="item"><div class="brand" data-text>${esc(cfg.brand)}</div>` +
    `<h1 class="headline" data-text>${esc(v.headline)}</h1><p class="sub" data-text>${esc(v.sub)}</p>` +
    `<div class="foot"><div class="price"><b data-text>${fill(v.price, priceVars(products, cfg))}</b>` +
    `<small data-text>${esc(cfg.price_note_many)}</small></div><div class="act"><div class="cta" data-text>${esc(cfg.cta)}</div>` +
    `<small class="cta-note" data-text>${esc(cfg.cta_note)}</small></div></div></div>`;
  const card = `<div class="card collection">${rows}${last}</div>`;
  return { duration, imgs, card, timeline: { duration, fade: FADE, shots, items, size: null }, products: products.map((p) => p.id) };
}

function html(template, cfg, f, plan, fonts, id) {
  const shots = plan.imgs.map((file, i) => `<div class="shot${fullIn(file, f) ? ' full' : ''}${frameFor(file, f) !== file ? ' tall' : ''}"><img src="${ORIGIN}/img/${id}/${i}" alt=""></div>`).join('');
  const map = { FONTS: fonts.css, SERIF: fonts.serif, W: f.width, H: f.height, FORMAT: f.id, SHOTS: shots,
    CARD: plan.card, MARK: esc(cfg.mark), TIMELINE: JSON.stringify(plan.timeline) };
  return template.replace(/\{\{(\w+)\}\}/g, (m, k) => {
    if (!(k in map)) throw new Error(`шаблон: невідомий ${m}`);
    return String(map[k]);
  });
}

// У сторінці, на кадрі часу t: що з тексту видно, де воно, який контраст; «הדמיה»; переповнення картки.
function inspect(safe) {
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
  const alpha = (el) => { let a = 1; for (let n = el; n; n = n.parentElement) a *= Number(getComputedStyle(n).opacity); return a; };
  const W = innerWidth, H = innerHeight;
  const out = [];
  for (const el of document.querySelectorAll('[data-text]')) {
    const a = alpha(el);
    if (a < 0.01) continue;
    const r = el.getBoundingClientRect();
    const fg = rgba(getComputedStyle(el).color), bg = bgOf(el);
    const [x, y] = bg ? [lum(fg), lum(bg)].sort((p, q) => q - p) : [0, 0];
    out.push({ text: el.textContent.trim().slice(0, 30), alpha: a, contrast: bg ? (x + 0.05) / (y + 0.05) : 0,
      inside: r.left >= 0 && r.right <= W && r.top >= safe * H - 0.5 && r.bottom <= (1 - safe) * H + 0.5 });
  }
  const mark = document.querySelector('.mark'); const m = mark.getBoundingClientRect();
  const card = document.querySelector('.card');
  const over = [card, ...card.querySelectorAll('.item')].some((e) => e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1);
  // Товар не під карткою: де кадр — смуга (9:16, 4:5), картка починається нижче за неї; у 9:16 картка ще й вище нижніх 20 %.
  // Вертикальний рендер (.tall) картка перекриває лише підлогою — стіл у смузі 300–1000 px; крупний план (.full) — без умов.
  const cr = card.getBoundingClientRect();
  const covered = [...document.querySelectorAll('.shot:not(.full)')].map((e) => e.getBoundingClientRect())
    .some((sh) => sh.height < H - 0.5 && cr.top < sh.bottom - 0.5);
  const fullTooHigh = !!document.querySelector('.shot.tall') && cr.top < 1000;
  const fullNot916 = [...document.querySelectorAll('.shot.tall img')].some((i) => i.naturalWidth * 16 !== i.naturalHeight * 9);
  const low = safe > 0 && cr.bottom > 0.8 * H + 0.5;
  return { texts: out, covered, low, fullTooHigh, fullNot916, mark: mark.textContent.trim(), markAlpha: alpha(mark), markInside: m.top >= safe * H - 0.5 && m.left >= 0 && m.width > 0,
    over, imagesOk: [...document.images].every((i) => i.complete && i.naturalWidth > 0),
    fontsOk: document.fonts.check('600 30px "IBM Plex Sans Hebrew"', 'הדמיה') };
}

function ffmpeg(argv) {
  const r = spawnSync(FFMPEG, ['-hide_banner', '-loglevel', 'error', '-y', ...argv], { stdio: ['ignore', 'ignore', 'pipe'] });
  if (r.status !== 0) throw new Error(`ffmpeg: ${String(r.stderr).slice(0, 400)}`);
}

// CRF підбирається, доки файл не влізе в 4 МБ.
function encode(frames, duration, file) {
  for (let crf = 22; crf <= 34; crf += 3) {
    ffmpeg(['-framerate', String(FPS), '-i', path.join(frames, '%04d.jpg'),
      '-f', 'lavfi', '-t', String(duration), '-i', 'anullsrc=r=48000:cl=stereo',
      '-c:v', 'libx264', '-preset', 'slow', '-crf', String(crf), '-pix_fmt', 'yuv420p', '-profile:v', 'high',
      '-r', String(FPS), '-c:a', 'aac', '-b:a', '32k', '-shortest', '-movflags', '+faststart', '-threads', '1', file]);
    const bytes = fs.statSync(file).size;
    if (bytes <= MAX_BYTES || crf >= 34) return { bytes, crf };
  }
  return null;
}

async function sheet(browser, outDir, items, tmp) {
  const cells = [];
  for (const it of items) {
    const row = [];
    for (const s of SHEET_AT) {
      const png = path.join(tmp, `${it.file}-${s}.jpg`);
      ffmpeg(['-ss', String(s), '-i', path.join(outDir, it.file), '-frames:v', '1', '-vf', 'scale=-2:480', '-q:v', '3', png]);
      row.push(`<figure><img src="data:image/jpeg;base64,${fs.readFileSync(png).toString('base64')}"><figcaption>${s} с</figcaption></figure>`);
    }
    cells.push(`<section><h2>${esc(it.file)} · ${it.duration} с · ${(it.bytes / 1048576).toFixed(2)} МБ</h2><div class="row">${row.join('')}</div></section>`);
  }
  const page = await browser.newPage({ viewport: { width: 1400, height: 800 }, deviceScaleFactor: 1 });
  await page.setContent(`<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>body{margin:0;padding:20px;background:#F6F1E9;color:#211C17;font:15px/1.4 system-ui,sans-serif}
h1{font-size:20px;margin:0 0 8px}h2{font-size:15px;margin:16px 0 6px}.row{display:flex;gap:12px}figure{margin:0}img{display:block;height:480px;box-shadow:0 1px 4px rgba(0,0,0,.2)}
figcaption{font-size:12px;color:#5E554C}</style></head><body><h1>ALUMA — відео-креативи, кадри 0 / 3 / 6 с (з готових MP4)</h1>${cells.join('')}</body></html>`);
  const buf = await page.screenshot({ type: 'jpeg', quality: 70, fullPage: true });
  fs.writeFileSync(path.join(outDir, 'sheet.jpg'), buf);
  await page.close();
}

async function main() {
  const opts = args(process.argv.slice(2));
  if (!fs.existsSync(FFMPEG)) throw new Error(`нема ${FFMPEG}`);
  const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, 'creatives.json'), 'utf8'));
  const catalog = JSON.parse(fs.readFileSync(path.join(ROOT, 'catalog', 'products.json'), 'utf8'));
  const byId = Object.fromEntries(catalog.map((p) => [p.id, p]));
  const template = fs.readFileSync(path.join(__dirname, 'video.html'), 'utf8');
  const outDir = opts.out || path.join(ROOT, 'docs', 'creatives', 'video');
  const fonts = fontFaces();
  const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'aluma-video-'));
  fs.mkdirSync(outDir, { recursive: true });

  const plans = cfg.variants.filter((v) => !opts.only || v.id === opts.only).map((v) => {
    const products = v.products.map((id) => byId[id]);
    if (products.some((p) => !p)) throw new Error(`${v.id}: товару нема в каталозі`);
    return { v, plan: products.length > 1 ? collection(cfg, v, products) : single(cfg, v, products[0]) };
  });

  const browser = await chromium.launch();
  const failures = [];
  const report = { generated_by: 'tools/creatives/video.js', fps: FPS,
    limits: { max_bytes: MAX_BYTES, min_contrast: MIN_CONTRAST, safe_zone: SAFE }, videos: [] };
  try {
    for (const { v, plan } of plans) {
      for (const f of FORMATS) {
        const name = `${v.id}-${f.width}x${f.height}.mp4`;
        const safe = f.id === '9x16' ? SAFE : 0;
        const page = await browser.newPage({ viewport: { width: f.width, height: f.height }, deviceScaleFactor: 1, locale: 'he-IL' });
        await page.route('**/*', (route) => {
          const url = new URL(route.request().url());
          if (url.origin !== ORIGIN) return route.abort();
          let file = null;
          const m = url.pathname.match(/^\/img\/([\w-]+)\/(\d+)$/);
          if (m && m[1] === v.id) file = frameFor(plan.imgs[Number(m[2])], f);
          else if (url.pathname.startsWith('/fonts/')) file = path.join(ROOT, 'site', 'assets', 'fonts', path.basename(url.pathname));
          if (!file || !fs.existsSync(file)) return route.fulfill({ status: 404, body: '' });
          return route.fulfill({ status: 200, contentType: TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', body: fs.readFileSync(file) });
        });
        await page.goto(ORIGIN + '/');
        await page.setContent(html(template, cfg, f, plan, fonts, v.id), { waitUntil: 'load' });
        await page.evaluate(() => document.fonts.ready);

        const frames = fs.mkdtempSync(path.join(tmp, 'f-'));
        const problems = new Set();
        let minContrast = Infinity;
        const total = Math.round(plan.duration * FPS);
        for (let i = 0; i < total; i++) {
          const t = i / FPS;
          await page.evaluate((x) => window.render(x), t);
          if (i % (FPS / 2) === 0) {
            const c = await page.evaluate(inspect, safe);
            if (c.mark !== cfg.mark || c.markAlpha < 0.999 || !c.markInside) problems.add(`${t.toFixed(1)} с: нема «הדמיה»`);
            if (c.over) problems.add(`${t.toFixed(1)} с: картка переповнена`);
            if (c.covered) problems.add(`${t.toFixed(1)} с: картка закриває кадр товару`);
            if (c.fullNot916) problems.add('вертикальний рендер не 9:16');
            if (c.fullTooHigh) problems.add(`${t.toFixed(1)} с: картка вище 1000 px — закриє стіл вертикального рендера`);
            if (c.low) problems.add(`${t.toFixed(1)} с: картка в нижніх 20 % (інтерфейс Reels)`);
            if (!c.imagesOk) problems.add('кадр не завантажився');
            if (!c.fontsOk) problems.add('шрифт сайту не завантажився');
            for (const x of c.texts) {
              if (!x.inside) problems.add(`${t.toFixed(1)} с: «${x.text}» поза безпечною зоною`);
              if (x.alpha > 0.99) {
                minContrast = Math.min(minContrast, x.contrast);
                if (x.contrast < MIN_CONTRAST) problems.add(`${t.toFixed(1)} с: контраст ${x.contrast.toFixed(2)} «${x.text}»`);
              }
            }
          }
          fs.writeFileSync(path.join(frames, String(i + 1).padStart(4, '0') + '.jpg'), await page.screenshot({ type: 'jpeg', quality: 92 }));
        }
        await page.close();
        const enc = encode(frames, plan.duration, path.join(outDir, name));
        fs.rmSync(frames, { recursive: true, force: true });
        if (enc.bytes > MAX_BYTES) problems.add(`${(enc.bytes / 1048576).toFixed(2)} МБ > 4`);
        if (problems.size) failures.push(`${name}: ${[...problems].join('; ')}`);
        report.videos.push({ file: name, width: f.width, height: f.height, duration: plan.duration, fps: FPS, bytes: enc.bytes,
          crf: enc.crf, min_contrast: Number(minContrast.toFixed(2)), products: plan.products,
          images: plan.imgs.map((p) => path.relative(ROOT, frameFor(p, f)).split(path.sep).join('/')) });
        console.log(`${problems.size ? '✗' : '✓'} ${name}  ${(enc.bytes / 1048576).toFixed(2)} МБ crf ${enc.crf}  контраст ≥ ${minContrast.toFixed(1)}`);
      }
    }
    if (!opts.only) fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 2) + '\n');
    await sheet(browser, outDir, report.videos, tmp);
  } finally {
    await browser.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  if (failures.length) {
    console.error('Перевірки не пройдено:\n  ' + failures.join('\n  '));
    process.exit(1);
  }
  console.log(`готово: ${report.videos.length} роликів → ${path.relative(ROOT, outDir) || outDir}`);
}

main().catch((e) => { console.error(e.message || e); process.exit(1); });
