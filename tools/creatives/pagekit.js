#!/usr/bin/env node
// Стартовий набір сторінки ALUMA у Facebook/Instagram (docs/page-kit/README.md): аватар 1080×1080, обкладинка Facebook
// 1640×624, 9 постів × 1080×1080 і 1080×1350, 3 обкладинки Highlights 1080×1920, лист preview.jpg і report.json.
// Кадри — візуалізації з catalog/products.json (і рендери тонів, як у tones.js), цифри й назви — з каталогу, підписи —
// tools/creatives/pagekit.json, плашки «הדמיה» й ціни — creatives.json. Знімок — Playwright без порту й без мережі.
//
//   nice -n 19 node tools/creatives/pagekit.js                    # → docs/page-kit/
//   nice -n 19 node tools/creatives/pagekit.js --out "$TMPDIR/pk" # чернетка
//
// Перевірки (вихід 1 при порушенні): ті самі, що в build.js (measure) — текст ≤ 20 %, контраст ≥ 4.5:1, «הדמיה» на
// кожному кадрі з рендером, кожен кадр видно ≥ 5 %, шрифти й кадри завантажені, JPG ≤ 500 КБ; плюс аватар — усе в
// колі, яке Meta вирізає з квадрата; обкладинка — текст і позначка в центрі 1080×624 (видно на телефоні);
// кадр — лише з каталогу.
'use strict';
const fs = require('fs');
const path = require('path');
const B = require('./build.js');

const { chromium } = require('@playwright/test');

const COVER = { id: 'cover', width: 1640, height: 624, safe: 1080 };
const AVATAR = { id: '1x1', width: 1080, height: 1080 };
const STORY = { id: '9x16', width: 1080, height: 1920 };

function args(argv) {
  const out = { out: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--out') out.out = path.resolve(argv[++i]);
    else throw new Error(`невідомий аргумент: ${argv[i]}`);
  }
  return out;
}

// «tavor/home» → site/assets/products/tavor/home-<ширина>.jpg з images[].jpg (візуалізація), лише якщо кадр є в каталозі;
// ширина — рідна ширина майстра (AI-кадри 1264 / 1200, рендери 1600).
function catalogFrame(catalog, key) {
  const [pid, view] = key.split('/');
  const p = catalog.find((x) => x.id === pid);
  const img = p && (p.images || []).find((i) => i.kind === 'visualization' && i.jpg && new RegExp(`/${pid}/${view}-\\d+\\.jpg$`).test(i.jpg));
  if (!img) throw new Error(`${key}: кадру нема в catalog/products.json`);
  const file = path.join(B.ROOT, 'site', img.jpg.replace(/^\//, ''));
  if (!fs.existsSync(file)) throw new Error(`${key}: нема файлу ${path.relative(B.ROOT, file)}`);
  return file;
}
// Рендери тонів — ті самі, що в каруселі tones.js (одна камера, змінюється лише матеріал).
const toneFrame = (pid, tone) => path.join(B.ROOT, 'site', 'assets', 'products', pid, `finish-${tone}-1600.jpg`);

function varsOf(product) {
  const s = product.sizes[0];
  const v = {
    name: product.name.he, tagline: product.tagline.he, length: s.length_cm, extended: s.extended_cm ?? '',
    sizes: [...new Set(product.sizes.map((x) => x.label))].join(' / '),
    n_tones: product.finishes.length, tones: product.finishes.map((f) => f.name.he).join(' · '),
  };
  if (product.seats) Object.assign(v, { seats: product.seats.closed[0], seats_extended: product.seats.extended[0] });
  return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, B.esc(x)]));
}

function filled(text, vars, where) {
  const out = B.fill(text, vars);
  if (/\{\w+\}/.test(out)) throw new Error(`${where}: лишився плейсхолдер у «${out}»`);
  return out;
}

const signSvg = (d) => `<svg class="sign keep" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="${d}"/></svg>`;
const logo = (he, d, withSign) =>
  `<div class="logo">${withSign ? signSvg(d) : ''}<span class="logo-lat keep" data-text>ALUMA</span><span class="logo-he keep" data-text>${B.esc(he)}</span></div>`;
const EXTEND = '<svg class="extend" viewBox="0 0 400 240" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="10" stroke-linejoin="round" stroke-linecap="round">' +
  '<rect x="16" y="90" width="134" height="120" rx="6"/><rect x="250" y="90" width="134" height="120" rx="6"/>' +
  '<rect x="164" y="90" width="72" height="120" rx="4" stroke-dasharray="16 12"/>' +
  '<path d="M40 36H360M40 36l22-18M40 36l22 18M360 36l-22-18M360 36l-22 18"/></g></svg>';

async function main() {
  const opts = args(process.argv.slice(2));
  const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, 'pagekit.json'), 'utf8'));
  const ccfg = JSON.parse(fs.readFileSync(path.join(__dirname, 'creatives.json'), 'utf8'));
  const catalog = JSON.parse(fs.readFileSync(path.join(B.ROOT, 'catalog', 'products.json'), 'utf8'));
  const he = JSON.parse(fs.readFileSync(path.join(B.ROOT, 'i18n', 'he.json'), 'utf8'));
  const byId = Object.fromEntries(catalog.map((p) => [p.id, p]));
  const template = fs.readFileSync(path.join(__dirname, 'pagekit.html'), 'utf8');
  const signPath = fs.readFileSync(path.join(B.ROOT, 'site', 'assets', 'favicon.svg'), 'utf8').match(/ d="([^"]+)"/)[1];
  const outDir = opts.out || path.join(B.ROOT, 'docs', 'page-kit');
  const fonts = B.fontFaces();
  const notes = {
    '@tone_note': he.matb_3_p.split(';')[0].trim(),   // «הגוון במסך הוא קירוב» — як на сайті біля тонів
    '@includes': he.pt_1,                             // «המחיר כולל מע״מ, משלוח והרכבה»
  };
  const mark = ccfg.mark ? `<div class="mark" data-text>${B.esc(ccfg.mark)}</div>` : '';
  const tiles = (n) => Array.from({ length: n }, (_, i) => `<img src="${B.ORIGIN}/img/${i}" alt="">`).join('');

  // План знімків: {file, kind, format, body, images[], products[]}.
  const jobs = [];
  jobs.push({ file: 'avatar-1080x1080.jpg', kind: 'avatar', format: AVATAR, images: [], products: [],
    body: logo(cfg.avatar.he, signPath, true) });
  const coverImg = catalogFrame(catalog, cfg.cover.image);
  jobs.push({ file: 'cover-1640x624.jpg', kind: 'cover', format: COVER, images: [coverImg], products: [cfg.cover.image.split('/')[0]],
    body: `<div class="media n1">${tiles(1)}</div>${mark}<div class="card">${logo(cfg.avatar.he, signPath, false)}` +
      `<h1 data-text>${B.esc(cfg.cover.headline)}</h1><p data-text>${B.esc(cfg.cover.sub)}</p></div>` });
  cfg.posts.forEach((post, k) => {
    const product = byId[post.product];
    if (!product) throw new Error(`${post.id}: товару нема в каталозі`);
    const vars = varsOf(product);
    const images = post.images === '@tones' ? product.finishes.map((f) => toneFrame(product.id, f.id)) : post.images.map((x) => catalogFrame(catalog, x));
    for (const f of images) if (!fs.existsSync(f)) throw new Error(`${post.id}: нема ${path.relative(B.ROOT, f)}`);
    let foot;
    if (post.price) {
      const pv = B.priceVars([product], ccfg);
      foot = `<b data-text>${pv.from}₪${pv.price}</b><small data-text>${B.esc(ccfg.price_note)} · ${B.esc(ccfg.includes)}</small>`;
    } else {
      if (!(post.note in notes)) throw new Error(`${post.id}: невідомий note ${post.note}`);
      foot = `<small data-text>${B.esc(notes[post.note])}</small>`;
    }
    const body = `<div class="media n${images.length}">${tiles(images.length)}</div>${mark}<div class="panel">` +
      `<div class="brand" data-text>${B.esc(ccfg.brand)}</div>` +
      `<h1 class="headline" data-text>${filled(post.headline, vars, post.id)}</h1>` +
      `<p class="sub" data-text>${filled(post.sub, vars, post.id)}</p><div class="foot">${foot}</div></div>`;
    for (const f of cfg.formats) {
      jobs.push({ file: `post-${String(k + 1).padStart(2, '0')}-${post.id}-${f.width}x${f.height}.jpg`, kind: 'post', format: f,
        post: post.id, order: k + 1, images, products: images.map(() => product.id), body });
    }
  });
  const natural = byId.tavor.finishes.find((f) => f.id === 'natural').hex;
  for (const h of cfg.highlights) {
    const icon = h.icon === 'mark' ? signSvg(signPath)
      : h.icon === 'tones' ? `<div class="dots">${byId.tavor.finishes.map((f) => `<i style="background:${B.esc(f.hex)}"></i>`).join('')}</div>`
        : EXTEND;
    jobs.push({ file: `highlight-${h.id}-1080x1920.jpg`, kind: 'hl', format: STORY, images: [], products: [], title: h.title,
      body: `<div class="disc">${icon}</div>`, style: `--hl-bg:${natural}` });
  }

  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const failures = [];
  const report = { generated_by: 'tools/creatives/pagekit.js',
    limits: { max_bytes: B.MAX_BYTES, max_text_share: B.MAX_TEXT_SHARE, min_contrast: B.MIN_CONTRAST, min_tile_share: B.MIN_TILE_SHARE, cover_safe_width: COVER.safe },
    items: [] };
  try {
    for (const job of jobs) {
      const f = job.format;
      const page = await browser.newPage({ viewport: { width: f.width, height: f.height }, deviceScaleFactor: 1, locale: 'he-IL' });
      await page.route('**/*', (route) => {
        const url = new URL(route.request().url());
        if (url.origin !== B.ORIGIN) return route.abort();
        let file = null;
        const m = url.pathname.match(/^\/img\/(\d+)$/);
        if (m) file = job.images[Number(m[1])];
        else if (url.pathname.startsWith('/fonts/')) file = path.join(B.ROOT, 'site', 'assets', 'fonts', path.basename(url.pathname));
        if (!file || !fs.existsSync(file)) return route.fulfill({ status: 404, body: '' });
        return route.fulfill({ status: 200, contentType: B.TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', body: fs.readFileSync(file) });
      });
      await page.goto(B.ORIGIN + '/');
      const map = { FONTS: fonts.css, SERIF: fonts.serif, W: f.width, H: f.height, KIND: job.kind, FORMAT: f.id, BODY: job.body };
      const html = template.replace(/\{\{(\w+)\}\}/g, (mm, key) => {
        if (!(key in map)) throw new Error(`шаблон: невідомий ${mm}`);
        return String(map[key]);
      }).replace('<div class="canvas">', job.style ? `<div class="canvas" style="${job.style}">` : '<div class="canvas">');
      await page.setContent(html, { waitUntil: 'load' });
      await page.evaluate(() => document.fonts.ready);
      const m = await page.evaluate(B.measure);
      // Аватар: кути кожного елемента лого — у колі Ø 1080 з відступом 40 px. Обкладинка: тексти й позначка — у центрі.
      const boxes = await page.evaluate(() => [...document.querySelectorAll('.keep, [data-text]')].map((el) => {
        const r = el.getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, text: el.textContent.trim().slice(0, 30) };
      }));
      // Без unicode-range check() чекає обидва підмножини: у лого аватара нема латиниці Plex — довантажуємо явно.
      const logoFonts = await page.evaluate(async () => {
        if (!document.querySelector('.logo')) return true;
        const sets = await Promise.all([document.fonts.load('400 52px "Frank Ruhl Libre"', 'ALUMA'), document.fonts.load('400 30px "IBM Plex Sans Hebrew"', 'אלומה')]);
        return sets.every((faces) => faces.length > 0) && document.fonts.check('400 52px "Frank Ruhl Libre"', 'ALUMA');
      });
      const shot = await B.shoot(page, path.join(outDir, job.file));
      await page.close();

      const minContrast = m.texts.length ? Math.min(...m.texts.map((t) => t.contrast)) : null;
      const problems = [];
      if (m.textShare > B.MAX_TEXT_SHARE) problems.push(`текст ${(m.textShare * 100).toFixed(1)} % > 20 %`);
      for (const t of m.texts) {
        if (t.contrast < B.MIN_CONTRAST) problems.push(`контраст ${t.contrast.toFixed(2)} «${t.text}»`);
        if (!t.inside) problems.push(`виходить за кадр «${t.text}»`);
      }
      if (job.images.length && ccfg.mark && (m.mark !== ccfg.mark || !m.markVisible)) problems.push('кадр без позначки «הדמיה»');
      if (m.panelOverflow) problems.push('панель переповнена');
      if (!m.imagesOk) problems.push('кадр не завантажився');
      // Позначка «הדמיה» (Plex 600) є лише на кадрах; лого — Frank Ruhl Libre 400 + Plex 400, Highlights — без тексту.
      if ((job.images.length && !m.fontsOk) || !logoFonts) problems.push('шрифт сайту не завантажився');
      m.tiles.forEach((share, i) => { if (share < B.MIN_TILE_SHARE) problems.push(`кадр ${i} видно на ${(share * 100).toFixed(1)} %`); });
      if (job.kind === 'avatar') {
        for (const b of boxes) {
          for (const [x, y] of [[b.left, b.top], [b.right, b.top], [b.left, b.bottom], [b.right, b.bottom]]) {
            if (Math.hypot(x - f.width / 2, y - f.height / 2) > f.width / 2 - 40) { problems.push(`«${b.text || 'знак'}» виходить за коло аватара`); break; }
          }
        }
      }
      if (job.kind === 'cover') {
        const lo = (f.width - COVER.safe) / 2, hi = lo + COVER.safe;
        for (const b of boxes) if (b.left < lo || b.right > hi) problems.push(`«${b.text}» поза центром ${COVER.safe} px (обріже телефон)`);
      }
      if (shot.bytes > B.MAX_BYTES) problems.push(`${Math.round(shot.bytes / 1024)} КБ > 500`);
      if (problems.length) failures.push(`${job.file}: ${[...new Set(problems)].join('; ')}`);
      report.items.push({ file: job.file, kind: job.kind, post: job.post, order: job.order, title: job.title,
        width: f.width, height: f.height, bytes: shot.bytes, jpeg_quality: shot.quality,
        text_share: Number(m.textShare.toFixed(4)), min_contrast: minContrast === null ? null : Number(minContrast.toFixed(2)),
        has_mark: m.mark === ccfg.mark, tiles: m.tiles.map((t) => Number(t.toFixed(4))), products: job.products,
        images: job.images.map((p) => path.relative(B.ROOT, p).split(path.sep).join('/')) });
      console.log(`${problems.length ? '✗' : '✓'} ${job.file}  ${Math.round(shot.bytes / 1024)} KB q${shot.quality}  текст ${(m.textShare * 100).toFixed(1)} %` +
        (minContrast === null ? '' : `  контраст ≥ ${minContrast.toFixed(1)}`));
    }
    fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 2) + '\n');
    fs.writeFileSync(path.join(outDir, 'preview.html'), previewHtml(report.items));
    const sheet = await browser.newPage({ viewport: { width: 1240, height: 800 }, deviceScaleFactor: 1 });
    await sheet.goto('file://' + path.join(outDir, 'preview.html'), { waitUntil: 'load' });
    for (let q = 82; q >= 40; q -= 6) {
      const buf = await sheet.screenshot({ type: 'jpeg', quality: q, fullPage: true });
      if (buf.length <= 900 * 1024 || q <= 40) { fs.writeFileSync(path.join(outDir, 'preview.jpg'), buf); break; }
    }
  } finally {
    await browser.close();
  }
  if (failures.length) {
    console.error('Перевірки не пройдено:\n  ' + failures.join('\n  '));
    process.exit(1);
  }
  console.log(`готово: ${report.items.length} зображень → ${path.relative(B.ROOT, outDir) || outDir}`);
}

// Лист для власника: як сторінка виглядатиме — обкладинка з аватаром-колом, сітка 3×3 (останній пост зліва вгорі,
// як в Instagram), 4:5 у ряд, Highlights колами.
function previewHtml(items) {
  const img = (it, w, cls = '') => `<img class="${cls}" src="${B.esc(it.file)}" width="${w}" height="${Math.round(w * it.height / it.width)}" alt="${B.esc(it.file)}">`;
  const avatar = items.find((i) => i.kind === 'avatar');
  const cover = items.find((i) => i.kind === 'cover');
  const sq = items.filter((i) => i.kind === 'post' && i.width === i.height).sort((a, b) => b.order - a.order);
  const tall = items.filter((i) => i.kind === 'post' && i.width !== i.height).sort((a, b) => a.order - b.order);
  const hl = items.filter((i) => i.kind === 'hl');
  const cap = (it) => `<figcaption>${it.order ? `${it.order}. ` : ''}${B.esc(it.post || it.title || it.kind)}</figcaption>`;
  return `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>ALUMA — набор страницы</title>
<style>body{margin:0;padding:24px 28px;background:#ECE5DA;color:#211C17;font:15px/1.4 system-ui,sans-serif;width:1184px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:22px 0 8px}p{margin:0 0 10px;color:#5E554C}
.cover{position:relative;width:1184px}.cover>img{display:block;width:1184px;height:auto}
.safe{position:absolute;top:0;bottom:0;left:${(1 - 1080 / 1640) / 2 * 100}%;right:${(1 - 1080 / 1640) / 2 * 100}%;outline:2px dashed rgba(255,255,255,.9)}
.cover>img.ava{position:absolute;left:24px;bottom:-70px;border-radius:50%;border:5px solid #ECE5DA;width:150px;height:150px}
.grid{display:grid;grid-template-columns:repeat(3,300px);gap:4px}.grid img{display:block;width:300px;height:300px}
.row{display:flex;gap:10px;flex-wrap:wrap}.row img{display:block}figure{margin:0}figcaption{font-size:12px;color:#5E554C;margin-top:3px}
.hl img{border-radius:50%;object-fit:cover;width:130px;height:130px}.flex{display:flex;gap:28px;align-items:flex-start}</style></head>
<body><h1>ALUMA — стартовый набор страницы Facebook / Instagram</h1>
<p>Сгенерировано: nice -n 19 node tools/creatives/pagekit.js. Пунктир — то, что видно на телефоне (центр 1080 px).</p>
<div class="cover">${img(cover, 1184)}<div class="safe"></div>${img(avatar, 150, 'ava')}</div>
<div style="height:84px"></div>
<div class="flex"><div><h2>Лента Instagram 1:1 (так будет выглядеть сетка; 9 — закрепить)</h2><div class="grid">${sq.map((it) => img(it, 300)).join('')}</div></div>
<div><h2>Highlights</h2><div class="row hl">${hl.map((it) => `<figure>${img(it, 130)}${cap(it)}</figure>`).join('')}</div>
<h2>Аватар</h2>${img(avatar, 200)}</div></div>
<h2>Посты 4:5 (лента), в порядке публикации</h2><div class="row">${tall.map((it) => `<figure>${img(it, 228)}${cap(it)}</figure>`).join('')}</div>
</body></html>
`;
}

main().catch((e) => { console.error(e.message || e); process.exit(1); });
