#!/usr/bin/env node
// Карусель Meta «один стіл у п'яти тонах» (розвідка Ad Library 21.10, висновок 4): картка на кожен тон каталогу,
// 1080×1080 і 1080×1350 → docs/creatives/tones/. Кадр — рендер тієї самої моделі з тією самою камерою, змінюється
// лише матеріал (site/assets/products/<товар>/finish-<тон>-1600.jpg, сесія 2, tools/render_products.js — тон тим самим
// фотосканом шпону з tools/oak_tones.py, що зразки й 3D на сайті);
// фото фільтром не перефарбовуємо. Назва тону — з catalog finishes, застереження «הגוון במסך הוא קירוב» — з i18n.
//
//   node tools/creatives/tones.js                                          # → docs/creatives/tones/
//   node tools/creatives/tones.js --out "$TMPDIR/t" --image natural=x.jpg  # чернетка (підміна кадру — лише з --out)
//   node tools/creatives/tones.js --lang ru                                # → docs/creatives/ru/tones/ (назви тонів — catalog ru)
//
// Перевірки ті самі, що в build.js (measure): текст ≤ 20 %, контраст ≥ 4.5:1, «הדמיה», JPG ≤ 500 КБ; плюс
// кадри всіх тонів — різні файли одного розміру (одна камера), інакше вихід 1.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const B = require('./build.js');

const { chromium } = require('@playwright/test');

const FORMATS = [{ id: '1x1', width: 1080, height: 1080 }, { id: '4x5', width: 1080, height: 1350 }];
const frameOf = (pid, tone) => path.join(B.ROOT, 'site', 'assets', 'products', pid, `finish-${tone}-1600.jpg`);
const swatchOf = (tone) => path.join(B.ROOT, 'site', 'assets', 'products', 'finishes', `${tone}.jpg`);

function args(argv) {
  const out = { out: null, images: {}, lang: 'he' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--out') out.out = path.resolve(argv[++i]);
    else if (a === '--lang') out.lang = argv[++i];
    else if (a === '--image') { const [id, p] = argv[++i].split('='); out.images[id] = path.resolve(p); }
    else throw new Error(`невідомий аргумент: ${a}`);
  }
  if (Object.keys(out.images).length && !out.out) throw new Error('--image (чернетка) — лише разом з --out');
  if (!B.LANGS[out.lang]) throw new Error(`невідома мова: ${out.lang}`);
  return out;
}

// Розмір JPG без залежностей: маркер SOF0/SOF2.
function jpegSize(file) {
  const b = fs.readFileSync(file);
  for (let i = 2; i < b.length - 9;) {
    if (b[i] !== 0xff) { i++; continue; }
    const m = b[i + 1];
    if (m >= 0xc0 && m <= 0xc3) return `${b.readUInt16BE(i + 7)}x${b.readUInt16BE(i + 5)}`;
    i += 2 + b.readUInt16BE(i + 2);
  }
  return null;
}

function cardHtml(template, cfg, product, tone, i, n, format, fonts, note) {
  const lang = cfg.lang;
  const map = {
    LANG: lang, DIR: B.LANGS[lang].dir, FONTS: fonts.css, SERIF: fonts.serif, W: format.width, H: format.height, FORMAT: format.id,
    IMAGE: `${B.ORIGIN}/img/frame`, SWATCH: `${B.ORIGIN}/img/swatch`,
    MARK: B.esc(cfg.mark), BRAND: B.esc(cfg.brand), TONE: B.esc(B.local(tone.name, lang, `finishes.${tone.id}.name`)),
    SUB: B.fill(cfg.tones.sub, { name: B.esc(B.local(product.name, lang, `${product.id}.name`)), i, n }), NOTE: B.esc(note),
  };
  return B.dropEmptyMark(template.replace(/\{\{(\w+)\}\}/g, (m, k) => {
    if (!(k in map)) throw new Error(`шаблон: невідомий ${m}`);
    return String(map[k]);
  }));
}

async function main() {
  const opts = args(process.argv.slice(2));
  const cfg = B.localize(JSON.parse(fs.readFileSync(path.join(__dirname, 'creatives.json'), 'utf8')), opts.lang);
  const catalog = JSON.parse(fs.readFileSync(path.join(B.ROOT, 'catalog', 'products.json'), 'utf8'));
  const site = JSON.parse(fs.readFileSync(path.join(B.ROOT, 'i18n', `${opts.lang}.json`), 'utf8'));
  const product = catalog.find((p) => p.id === cfg.tones.product);
  if (!product) throw new Error(`${cfg.tones.product}: товару нема в каталозі`);
  // Те саме застереження, що на сайті поруч із тонами, — перша частина речення, до «;».
  const note = site.matb_3_p.split(';')[0].trim();
  const template = fs.readFileSync(path.join(__dirname, 'tones.html'), 'utf8');
  const outDir = opts.out || path.join(B.ROOT, 'docs', 'creatives', B.LANGS[opts.lang].out, 'tones');
  const fonts = B.fontFaces(opts.lang);

  const tones = product.finishes;
  const frames = tones.map((t) => opts.images[t.id] || frameOf(product.id, t.id));
  const missing = tones.filter((t, i) => !fs.existsSync(frames[i]) || !fs.existsSync(swatchOf(t.id))).map((t) => t.id);
  if (missing.length) {
    console.error(`Нема рендера тону для ${product.id}: ${missing.join(', ')}\n  очікую ${path.relative(B.ROOT, frameOf(product.id, '<тон>'))} (сесія 2, tools/render_products.js)`);
    process.exit(1);
  }
  const problemsAll = [];
  if (!opts.out) {
    const hashes = new Set(frames.map((f) => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex')));
    if (hashes.size !== frames.length) problemsAll.push('кадри тонів однакові — це не п\'ять тонів');
    const sizes = new Set(frames.map(jpegSize));
    if (sizes.size !== 1) problemsAll.push(`кадри різного розміру (${[...sizes].join(', ')}) — не одна камера`);
  }

  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const report = { generated_by: 'tools/creatives/tones.js', ...(cfg.lang === 'he' ? {} : { lang: cfg.lang }), product: product.id, note,
    limits: { max_bytes: B.MAX_BYTES, max_text_share: B.MAX_TEXT_SHARE, min_contrast: B.MIN_CONTRAST }, cards: [] };
  try {
    for (const [k, tone] of tones.entries()) {
      for (const f of FORMATS) {
        const page = await browser.newPage({ viewport: { width: f.width, height: f.height }, deviceScaleFactor: 1, locale: B.LANGS[cfg.lang].locale });
        await page.route('**/*', (route) => {
          const url = new URL(route.request().url());
          if (url.origin !== B.ORIGIN) return route.abort();
          let file = null;
          if (url.pathname === '/img/frame') file = frames[k];
          else if (url.pathname === '/img/swatch') file = swatchOf(tone.id);
          else if (url.pathname.startsWith('/fonts/')) file = path.join(B.ROOT, 'site', 'assets', 'fonts', path.basename(url.pathname));
          if (!file || !fs.existsSync(file)) return route.fulfill({ status: 404, body: '' });
          return route.fulfill({ status: 200, contentType: B.TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', body: fs.readFileSync(file) });
        });
        await page.goto(B.ORIGIN + '/');
        await page.setContent(cardHtml(template, cfg, product, tone, k + 1, tones.length, f, fonts, note), { waitUntil: 'load' });
        await page.evaluate(() => document.fonts.ready);
        const m = await page.evaluate(B.measure);
        const name = `${product.id}-${tone.id}-${f.width}x${f.height}.jpg`;
        const shot = await B.shoot(page, path.join(outDir, name));
        await page.close();
        const minContrast = Math.min(...m.texts.map((t) => t.contrast));
        const problems = [];
        if (m.textShare > B.MAX_TEXT_SHARE) problems.push(`текст ${(m.textShare * 100).toFixed(1)} % > 20 %`);
        for (const t of m.texts) {
          if (t.contrast < B.MIN_CONTRAST) problems.push(`контраст ${t.contrast.toFixed(2)} «${t.text}»`);
          if (!t.inside) problems.push(`виходить за кадр «${t.text}»`);
        }
        if (!cfg.mark && m.mark) problems.push('плашка на кадрі, хоча mark порожній');
        if (cfg.mark && (m.mark !== cfg.mark || !m.markVisible)) problems.push(`нема позначки «${cfg.mark}»`);
        if (m.panelOverflow) problems.push('панель переповнена');
        if (!m.imagesOk) problems.push('кадр не завантажився');
        if (!m.fontsOk) problems.push('шрифт сайту не завантажився');
        if (shot.bytes > B.MAX_BYTES) problems.push(`${Math.round(shot.bytes / 1024)} КБ > 500`);
        if (problems.length) problemsAll.push(`${name}: ${problems.join('; ')}`);
        report.cards.push({ file: name, tone: tone.id, tone_name: tone.name[cfg.lang], width: f.width, height: f.height,
          bytes: shot.bytes, text_share: Number(m.textShare.toFixed(4)), min_contrast: Number(minContrast.toFixed(2)),
          image: path.relative(B.ROOT, frames[k]).split(path.sep).join('/') });
        console.log(`${problems.length ? '✗' : '✓'} ${name}  ${Math.round(shot.bytes / 1024)} KB  текст ${(m.textShare * 100).toFixed(1)} %  контраст ≥ ${minContrast.toFixed(1)}`);
      }
    }
    fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 2) + '\n');
    // Лист: картки 1:1 в ряд, як їх гортають у каруселі.
    const strip = report.cards.filter((c) => c.width === c.height)
      .map((c) => `<img src="${B.esc(c.file)}" width="360" height="360" alt="">`).join('');
    const sheet = await browser.newPage({ viewport: { width: 5 * 360 + 6 * 12, height: 384 }, deviceScaleFactor: 1 });
    fs.writeFileSync(path.join(outDir, 'sheet.html'), `<!doctype html><meta charset="utf-8"><body style="margin:0;padding:12px;display:flex;gap:12px;background:#ddd6cb">${strip}</body>`);
    await sheet.goto('file://' + path.join(outDir, 'sheet.html'), { waitUntil: 'load' });
    fs.writeFileSync(path.join(outDir, 'sheet.jpg'), await sheet.screenshot({ type: 'jpeg', quality: 82 }));
    fs.unlinkSync(path.join(outDir, 'sheet.html'));
  } finally {
    await browser.close();
  }
  if (problemsAll.length) {
    console.error('Перевірки не пройдено:\n  ' + problemsAll.join('\n  '));
    process.exit(1);
  }
  console.log(`готово: ${report.cards.length} карток → ${path.relative(B.ROOT, outDir) || outDir}`);
}

main().catch((e) => { console.error(e.message || e); process.exit(1); });
