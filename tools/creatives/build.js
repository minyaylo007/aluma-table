#!/usr/bin/env node
// Креативи для тесту Meta (docs/META-TEST.md §3): 3 варіанти × 1080×1080, 1080×1350, 1080×1920 → docs/creatives/.
// Кадр — візуалізації з catalog/products.json (images[].kind = "visualization"), текст — з каталогу й creatives.json,
// шаблон — tools/creatives/template.html, знімок — Playwright (chromium), без порту й без мережі (page.route).
//
//   node tools/creatives/build.js                       # → docs/creatives/*.jpg, preview.html, preview.jpg, report.json
//   node tools/creatives/build.js --out "$TMPDIR/cr" --image tavor=site/assets/renders/x.webp   # чернетка
//   node tools/creatives/build.js --lang ru             # група C «русский» → docs/creatives/ru/ (тексти — creatives.json "ru")
//
// Кожен знімок перевіряється, інакше вихід 1: текст ≤ 20 % площі, контраст кожного тексту ≥ 4.5:1 до його тла,
// позначка «הדמיה» («Визуализация» у ru) видима, шрифти й кадри завантажені, панель не переповнена, JPG ≤ 500 КБ.
// Підміна кадру (--image) — лише з --out: чернетка не потрапляє в docs/creatives/ як справжній креатив.
'use strict';
const fs = require('fs');
const path = require('path');

process.env.PLAYWRIGHT_BROWSERS_PATH = process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/ihor/aluma-table/ms-playwright';
const { chromium } = require('@playwright/test');

const ROOT = path.resolve(__dirname, '..', '..');
const ORIGIN = 'https://creative.test';
const MAX_BYTES = 500 * 1024;
const MAX_TEXT_SHARE = 0.20;
const MIN_CONTRAST = 4.5;
const MIN_TILE_SHARE = 0.05;   // кожен кадр товару — щонайменше 5 % полотна
// Мова креативу: he — як було (вихід байт-у-байт той самий), ru — група C, ліворуч-праворуч, кирилиця з сайту.
const LANGS = {
  he: { dir: 'rtl', locale: 'he-IL', out: '' },
  ru: { dir: 'ltr', locale: 'ru-RU', out: 'ru' },
};
const TYPES = { '.webp': 'image/webp', '.avif': 'image/avif', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.woff2': 'font/woff2' };

function args(argv) {
  const out = { out: null, images: {}, only: null, lang: 'he' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--out') out.out = path.resolve(argv[++i]);
    else if (a === '--lang') out.lang = argv[++i];
    else if (a === '--image') { const [id, p] = argv[++i].split('='); out.images[id] = path.resolve(p); }
    else if (a === '--only') out.only = argv[++i];
    else throw new Error(`невідомий аргумент: ${a}`);
  }
  if (Object.keys(out.images).length && !out.out) throw new Error('--image (чернетка) — лише разом з --out');
  if (!LANGS[out.lang]) throw new Error(`невідома мова: ${out.lang} (є: ${Object.keys(LANGS).join(', ')})`);
  return out;
}

// Конфіг мовою креативу: he — корінь creatives.json як є; інша мова — її блок ("ru") поверх кореня, структура
// один в один. Товари, формати й порядок варіантів — лише з кореня: мова міняє слова, не план.
function localize(cfg, lang) {
  if (lang === 'he') return { ...cfg, lang };
  const loc = cfg[lang];
  if (!loc) throw new Error(`creatives.json: нема блоку "${lang}"`);
  const variants = cfg.variants.map((v) => {
    const t = (loc.variants || []).find((x) => x.id === v.id);
    if (!t) throw new Error(`creatives.json "${lang}": нема варіанта ${v.id}`);
    return { ...v, headline: t.headline, sub: t.sub, price: t.price };
  });
  const keys = ['brand', 'mark', 'cta', 'cta_note', 'from', 'price_note', 'price_note_many', 'includes'];
  const missing = keys.filter((k) => typeof loc[k] !== 'string');
  if (missing.length) throw new Error(`creatives.json "${lang}": нема ${missing.join(', ')}`);
  const out = { ...cfg, variants, tones: { ...cfg.tones, ...loc.tones }, lang };
  for (const k of keys) out[k] = loc[k];
  delete out[lang];
  return out;
}

// Текст каталогу мовою креативу; нема перекладу — помилка, а не тихий іврит у російському креативі.
function local(field, lang, what) {
  if (!field || typeof field[lang] !== 'string') throw new Error(`каталог: нема ${what}.${lang}`);
  return field[lang];
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// he — «4,490» (₪ ставить шаблон ціни), ru — «4 490» з нерозривним пробілом, як money() у build.py сайту.
const money = (n, lang = 'he') => (lang === 'ru' ? Number(n).toLocaleString('en-US').replace(/,/g, '\u00a0') : Number(n).toLocaleString('en-US'));

function fontFaces(lang = 'he') {
  const dir = path.join(ROOT, 'site', 'assets', 'fonts');
  const faces = [];
  for (const w of [400, 600, 700]) {
    for (const part of ['hebrew', 'latin']) {
      const f = `PlexSansHebrew-${w}-${part}.woff2`;
      if (fs.existsSync(path.join(dir, f))) {
        faces.push(`@font-face{font-family:"IBM Plex Sans Hebrew";font-weight:${w};src:url(${ORIGIN}/fonts/${f}) format("woff2");}`);
      }
    }
  }
  // Frank Ruhl Libre — шрифт заголовків вітрини (сесія 1); нема у дереві — заголовок іде Plex.
  let serif = '"IBM Plex Sans Hebrew", serif';
  for (const part of ['hebrew', 'latin']) {
    const f = `FrankRuhlLibre-${part}.woff2`;
    if (fs.existsSync(path.join(dir, f))) {
      faces.push(`@font-face{font-family:"Frank Ruhl Libre";font-weight:300 900;src:url(${ORIGIN}/fonts/${f}) format("woff2");}`);
      serif = '"Frank Ruhl Libre", "IBM Plex Sans Hebrew", serif';
    }
  }
  // Кирилиця (ru): Plex Sans і PT Serif із сайту (site/assets/aluma.css) — під тими самими іменами родин і з тим самим
  // unicode-range, тож цифри, «₪» і латиниця лишаються з облич вище. he-креативи цих облич не бачать.
  if (lang === 'ru') {
    const range = 'unicode-range:U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116;';
    const cyr = [[400, 'PlexSans-400-cyrillic.woff2', 'IBM Plex Sans Hebrew'], [600, 'PlexSans-600-cyrillic.woff2', 'IBM Plex Sans Hebrew'],
      [700, 'PlexSans-700-cyrillic.woff2', 'IBM Plex Sans Hebrew'], ['300 900', 'PTSerif-cyrillic.woff2', 'Frank Ruhl Libre']];
    for (const [w, f, family] of cyr) {
      if (!fs.existsSync(path.join(dir, f))) throw new Error(`нема кириличного шрифту site/assets/fonts/${f}`);
      faces.push(`@font-face{font-family:"${family}";font-weight:${w};src:url(${ORIGIN}/fonts/${f}) format("woff2");${range}}`);
    }
    if (!serif.startsWith('"Frank Ruhl Libre"')) throw new Error('ru: PT Serif іде під іменем Frank Ruhl Libre — а його нема');
  }
  return { css: faces.join('\n'), serif };
}

// Кадр товару: перша візуалізація з каталогу (src від кореня сайту: /assets/… → site/assets/…).
function imageFor(product, overrides) {
  if (overrides[product.id]) return overrides[product.id];
  const img = (product.images || []).find((i) => i.kind === 'visualization');
  if (!img) return null;
  const rel = img.src.replace(/^\//, '');
  const candidates = [path.join(ROOT, 'site', rel), path.join(ROOT, rel)];
  return candidates.find((p) => fs.existsSync(p)) || null;
}

function fill(text, vars) {
  return text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
}

// «מ־» (від) — лише коли цін кілька: кілька товарів або розміри товару з різною ціною.
// У SAHAR одна міра, у TAL обидві форми по одній ціні — там «מ־» було б неправдою (аудит чесності, рядок 35).
function priceVars(products, cfg) {
  const prices = new Set(products.flatMap((p) => p.sizes.map((s) => s.price_ils)));
  return { price: money(Math.min(...prices), cfg.lang), from: prices.size > 1 ? esc(cfg.from) : '' };
}

// Заголовок: «@tagline» — слоган товару з каталогу; інакше текст із {seats}/{seats_extended} — місця найменшого розміру
// з catalog seats (розвідка Ad Library 21.10: ринок продає столи кількістю місць). Цифр у creatives.json немає.
function headlineOf(variant, products, lang = 'he') {
  const p = products[0];
  if (variant.headline === '@tagline') return esc(local(p.tagline, lang, `${p.id}.tagline`));
  const vars = p.seats ? { seats: esc(p.seats.closed[0]), seats_extended: esc(p.seats.extended[0]) } : {};
  const out = fill(esc(variant.headline), vars);
  if (/\{\w+\}/.test(out)) throw new Error(`${variant.id}: у заголовку лишився плейсхолдер — нема seats у каталозі?`);
  return out;
}

// 9:16 одного товару: вертикальний рендер сесії 2 (<ракурс>-9x16.jpg поруч із кадром, стіл у смузі 300–1000 px,
// підлога до низу) — на все полотно, картка на підлозі. Без нього кадр 16:10 у 9:16 ріже ніжки — креатив не готовий.
const tallOf = (file) => file.replace(/-\d+\.\w+$/, '-9x16.jpg');
const frameFor = (file, format, count) => (format.id === '9x16' && count === 1 && fs.existsSync(tallOf(file)) ? tallOf(file) : file);

function variantHtml(template, cfg, variant, format, products, fonts, imagePaths) {
  const first = products[0];
  const size = first.sizes[0];
  const vars = { length: esc(size.length_cm), extended: esc(size.extended_cm ?? ''), ...priceVars(products, cfg) };
  const headline = headlineOf(variant, products, cfg.lang);
  const tiles = imagePaths.map((_, i) =>
    `<img src="${ORIGIN}/img/${variant.id}/${i}" alt="">`).join('');
  const tall = imagePaths.length === 1 && frameFor(imagePaths[0], format, 1) !== imagePaths[0];
  const map = {
    LANG: cfg.lang, DIR: LANGS[cfg.lang].dir, FONTS: fonts.css, SERIF: fonts.serif, W: format.width, H: format.height, FORMAT: format.id + (tall ? ' tall' : ''),
    COUNT: imagePaths.length, TILES: tiles, MARK: esc(cfg.mark), BRAND: esc(cfg.brand), HEADLINE: headline,
    SUB: fill(variant.sub, vars), PRICE: fill(variant.price, vars),
    PRICE_NOTE: esc(products.length > 1 ? cfg.price_note_many : cfg.price_note), INCLUDES: esc(cfg.includes),
    CTA: esc(cfg.cta), CTA_NOTE: esc(cfg.cta_note),
  };
  return template.replace(/\{\{(\w+)\}\}/g, (m, k) => {
    if (!(k in map)) throw new Error(`шаблон: невідомий ${m}`);
    return String(map[k]);
  });
}

// У сторінці: частка площі під текстом (прямокутники рядків), контраст кожного тексту до непрозорого тла,
// видимість позначки, завантаження кадрів і шрифтів, переповнення панелі.
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
      if (c[3] > 0) return null;          // напівпрозоре тло над кадром — контраст не гарантований
    }
    return null;
  };
  // Шрифт позначки: жодне обличчя не впало, і письмо позначки (іврит чи кирилиця) покриває завантажене обличчя Plex
  // потрібної ваги. fonts.check() тут не годиться: у ru він чекає й іврит-обличчя, якого на кадрі нема.
  const covers = (f, cp) => f.unicodeRange.split(',').some((r) => {
    const [a, b] = r.trim().replace(/^U\+/i, '').split('-').map((x) => parseInt(x, 16));
    return cp >= a && cp <= (Number.isNaN(b) || b === undefined ? a : b);
  });
  const fontFor = (text, weight) => {
    const faces = [...document.fonts];
    const cp = text.codePointAt(0);
    return !faces.some((f) => f.status === 'error') && faces.some((f) => f.status === 'loaded'
      && f.family.replace(/"/g, '') === 'IBM Plex Sans Hebrew' && String(f.weight) === weight && covers(f, cp));
  };
  const W = document.documentElement.clientWidth, H = document.documentElement.clientHeight;
  let textArea = 0;
  const texts = [];
  for (const el of document.querySelectorAll('[data-text]')) {
    const range = document.createRange();
    range.selectNodeContents(el);
    for (const r of range.getClientRects()) textArea += r.width * r.height;
    const fg = rgba(getComputedStyle(el).color), bg = bgOf(el);
    const [a, b] = bg ? [lum(fg), lum(bg)].sort((x, y) => y - x) : [0, 0];
    const box = el.getBoundingClientRect();
    texts.push({ text: el.textContent.trim().slice(0, 40), contrast: bg ? (a + 0.05) / (b + 0.05) : 0,
      inside: box.left >= 0 && box.top >= 0 && box.right <= W && box.bottom <= H });
  }
  // Яка частка полотна реально показує кожен кадр (сітка точок + elementFromPoint: враховує обрізання
  // сіткою й картку 9:16 поверх кадру). Товар, якого не видно, не може стояти в креативі — і його ціна теж.
  const STEP = 12;
  const tiles = [...document.querySelectorAll('.media img')].map((img) => {
    let hit = 0;
    for (let y = STEP / 2; y < H; y += STEP) for (let x = STEP / 2; x < W; x += STEP) if (document.elementFromPoint(x, y) === img) hit += 1;
    return hit * STEP * STEP / (W * H);
  });
  // Аватар і обкладинки Highlights (pagekit.js) — без кадру, позначки й панелі: тоді поля порожні.
  const none = { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 };
  const boxOf = (sel) => { const el = document.querySelector(sel); return el ? el.getBoundingClientRect() : none; };
  const panel = document.querySelector('.panel');
  const mark = document.querySelector('.mark');
  const mbox = boxOf('.mark');
  const pbox = boxOf('.panel');
  const media = boxOf('.media');
  return {
    panelBox: { top: pbox.top, bottom: pbox.bottom }, mediaBottom: media.bottom, tall: !!document.querySelector('.canvas.tall'),
    tallNot916: [...document.querySelectorAll('.canvas.tall .media img')].some((i) => i.naturalWidth * 16 !== i.naturalHeight * 9),
    textShare: textArea / (W * H),
    texts,
    tiles,
    panelOverflow: !!panel && (panel.scrollHeight > panel.clientHeight + 1 || panel.scrollWidth > panel.clientWidth + 1),
    mark: mark ? mark.textContent.trim() : '', markVisible: mbox.width > 0 && mbox.height > 0 && mbox.top >= 0 && mbox.left >= 0,
    imagesOk: [...document.images].every((i) => i.complete && i.naturalWidth > 0),
    fontsOk: mark ? fontFor(mark.textContent.trim(), '600') : document.fonts.check('600 26px "IBM Plex Sans Hebrew"', 'הדמיה'),
  };
}

async function shoot(page, file) {
  for (let q = 88; q >= 56; q -= 4) {
    const buf = await page.screenshot({ type: 'jpeg', quality: q, fullPage: false });
    if (buf.length <= MAX_BYTES || q === 56) {
      fs.writeFileSync(file, buf);
      return { bytes: buf.length, quality: q };
    }
  }
  return null;
}

function previewHtml(rows, formats, cfg) {
  const cells = rows.map((r) => `<section><h2>${esc(r.variant)}</h2><div class="row">${formats.map((f) => {
    const it = r.items[f.id];
    return `<figure><img src="${esc(it.file)}" alt="${esc(r.variant)} ${f.width}×${f.height}" width="${f.width / 4}" height="${f.height / 4}">` +
      `<figcaption>${f.width}×${f.height} · ${Math.round(it.bytes / 1024)} KB · текст ${(it.textShare * 100).toFixed(1)} % · контраст ≥ ${it.minContrast.toFixed(1)}</figcaption></figure>`;
  }).join('')}</div></section>`).join('\n');
  return `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ALUMA — креативи Meta</title>
<style>body{margin:0;padding:24px;background:#F6F1E9;color:#211C17;font:15px/1.4 system-ui,sans-serif}
h1{font-size:22px;margin:0 0 16px}h2{font-size:17px;margin:24px 0 8px}.row{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}
figure{margin:0}img{display:block;height:auto;max-width:100%;box-shadow:0 1px 4px rgba(0,0,0,.18)}figcaption{font-size:13px;color:#5E554C;margin-top:6px}</style>
</head><body><h1>ALUMA — креативи для тесту Meta (візуалізації, «${esc(cfg.mark)}»)</h1>
<p>Згенеровано: node tools/creatives/build.js${cfg.lang === 'he' ? '' : ` --lang ${cfg.lang}`}. Ціни — «${esc(cfg.price_note)}», з каталогу.</p>
${cells}
</body></html>
`;
}

async function main() {
  const opts = args(process.argv.slice(2));
  const cfg = localize(JSON.parse(fs.readFileSync(path.join(__dirname, 'creatives.json'), 'utf8')), opts.lang);
  const catalog = JSON.parse(fs.readFileSync(path.join(ROOT, 'catalog', 'products.json'), 'utf8'));
  const byId = Object.fromEntries(catalog.map((p) => [p.id, p]));
  const template = fs.readFileSync(path.join(__dirname, 'template.html'), 'utf8');
  const outDir = opts.out || path.join(ROOT, 'docs', 'creatives', LANGS[opts.lang].out);
  const fonts = fontFaces(opts.lang);

  const variants = cfg.variants.filter((v) => !opts.only || v.id === opts.only);
  const plan = [];
  const missing = [];
  for (const v of variants) {
    const products = v.products.map((id) => byId[id]).filter(Boolean);
    if (products.length !== v.products.length) throw new Error(`${v.id}: товару нема в каталозі`);
    const withImg = products.map((p) => ({ p, img: imageFor(p, opts.images) }));
    // Колекція бере ті товари, що вже мають кадр (не менше двох); одиночний варіант без кадру — помилка.
    const ready = withImg.filter((x) => x.img);
    if (v.products.length > 1 ? ready.length < 2 : !ready.length) {
      missing.push(`${v.id}: ${withImg.filter((x) => !x.img).map((x) => x.p.id).join(', ')}`);
      continue;
    }
    plan.push({ v, products: ready.map((x) => x.p), images: ready.map((x) => x.img) });
  }
  if (missing.length) {
    console.error('Нема візуалізацій у catalog/products.json (images[].kind = "visualization"):\n  ' + missing.join('\n  '));
    process.exit(1);
  }

  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const failures = [];
  const report = { generated_by: 'tools/creatives/build.js', ...(cfg.lang === 'he' ? {} : { lang: cfg.lang }), limits: { max_bytes: MAX_BYTES, max_text_share: MAX_TEXT_SHARE, min_contrast: MIN_CONTRAST, min_tile_share: MIN_TILE_SHARE }, creatives: [] };
  const rows = [];
  try {
    for (const { v, products, images } of plan) {
      const row = { variant: v.id, items: {} };
      for (const f of cfg.formats) {
        const page = await browser.newPage({ viewport: { width: f.width, height: f.height }, deviceScaleFactor: 1, locale: LANGS[cfg.lang].locale });
        await page.route('**/*', (route) => {
          const url = new URL(route.request().url());
          if (url.origin !== ORIGIN) return route.abort();
          let file = null;
          const m = url.pathname.match(/^\/img\/([\w-]+)\/(\d+)$/);
          if (m && m[1] === v.id) file = frameFor(images[Number(m[2])], f, images.length);
          else if (url.pathname.startsWith('/fonts/')) file = path.join(ROOT, 'site', 'assets', 'fonts', path.basename(url.pathname));
          if (!file || !fs.existsSync(file)) return route.fulfill({ status: 404, body: '' });
          return route.fulfill({ status: 200, contentType: TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', body: fs.readFileSync(file) });
        });
        await page.goto(ORIGIN + '/');
        await page.setContent(variantHtml(template, cfg, v, f, products, fonts, images), { waitUntil: 'load' });
        await page.evaluate(() => document.fonts.ready);
        const m = await page.evaluate(measure);
        const name = `${v.id}-${f.width}x${f.height}.jpg`;
        const shot = await shoot(page, path.join(outDir, name));
        await page.close();
        const minContrast = Math.min(...m.texts.map((t) => t.contrast));
        const problems = [];
        if (m.textShare > MAX_TEXT_SHARE) problems.push(`текст ${(m.textShare * 100).toFixed(1)} % > 20 %`);
        for (const t of m.texts) {
          if (t.contrast < MIN_CONTRAST) problems.push(`контраст ${t.contrast.toFixed(2)} «${t.text}»`);
          if (!t.inside) problems.push(`виходить за кадр «${t.text}»`);
        }
        if (m.mark !== cfg.mark || !m.markVisible) problems.push(`нема позначки «${cfg.mark}»`);
        if (m.panelOverflow) problems.push('панель переповнена');
        if (!m.imagesOk) problems.push('кадр не завантажився');
        m.tiles.forEach((share, i) => {
          if (share < MIN_TILE_SHARE) problems.push(`кадр ${products[i] ? products[i].id : i} видно на ${(share * 100).toFixed(1)} % < ${MIN_TILE_SHARE * 100} %`);
        });
        if (!m.fontsOk) problems.push('шрифт сайту не завантажився');
        if (f.id === '9x16') {
          // Інтерфейс Reels/Stories займає нижні ~20 %; картка не лягає на кадр (крім вертикального рендера,
          // де під нею підлога, а стіл вище 1000 px).
          if (m.panelBox.bottom > 0.8 * f.height + 0.5) problems.push('картка в нижніх 20 % (інтерфейс Reels)');
          if (m.tall && m.panelBox.top < 1000) problems.push('картка вище 1000 px — закриє стіл вертикального рендера');
          if (m.tall && m.tallNot916) problems.push('вертикальний рендер не 9:16');
          if (!m.tall && m.panelBox.top < m.mediaBottom - 0.5) problems.push('картка закриває кадр товару');
        }
        if (shot.bytes > MAX_BYTES) problems.push(`${Math.round(shot.bytes / 1024)} КБ > 500`);
        if (problems.length) failures.push(`${name}: ${problems.join('; ')}`);
        const item = { file: name, width: f.width, height: f.height, bytes: shot.bytes, jpeg_quality: shot.quality,
          textShare: m.textShare, minContrast, tiles: m.tiles.map((t) => Number(t.toFixed(4))), products: products.map((p) => p.id),
          images: images.map((p) => path.relative(ROOT, frameFor(p, f, images.length)).split(path.sep).join('/')) };
        row.items[f.id] = item;
        report.creatives.push({ ...item, text_share: Number(m.textShare.toFixed(4)), min_contrast: Number(minContrast.toFixed(2)),
          textShare: undefined, minContrast: undefined });
        console.log(`${problems.length ? '✗' : '✓'} ${name}  ${Math.round(shot.bytes / 1024)} KB q${shot.quality}  текст ${(m.textShare * 100).toFixed(1)} %  контраст ≥ ${minContrast.toFixed(1)}`);
      }
      rows.push(row);
    }
    fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 2) + '\n');
    fs.writeFileSync(path.join(outDir, 'preview.html'), previewHtml(rows, cfg.formats, cfg));
    // Превʼю-лист одним JPG — щоб показати в чаті без браузера.
    const sheet = await browser.newPage({ viewport: { width: 1200, height: 800 }, deviceScaleFactor: 1 });
    await sheet.goto('file://' + path.join(outDir, 'preview.html'), { waitUntil: 'load' });
    for (let q = 80; q >= 40; q -= 10) {
      const buf = await sheet.screenshot({ type: 'jpeg', quality: q, fullPage: true });
      if (buf.length <= MAX_BYTES || q === 40) { fs.writeFileSync(path.join(outDir, 'preview.jpg'), buf); break; }
    }
  } finally {
    await browser.close();
  }
  if (failures.length) {
    console.error('Перевірки не пройдено:\n  ' + failures.join('\n  '));
    process.exit(1);
  }
  console.log(`готово: ${report.creatives.length} креативів → ${path.relative(ROOT, outDir) || outDir}`);
}

module.exports = { ROOT, ORIGIN, TYPES, LANGS, MAX_BYTES, MAX_TEXT_SHARE, MIN_CONTRAST, MIN_TILE_SHARE, localize, local, esc, money, fontFaces, fill, priceVars, headlineOf, measure, shoot };

// Модулем його бере tools/creatives/video.js — тоді знімки не робимо.
if (require.main === module) main().catch((e) => { console.error(e.message || e); process.exit(1); });
