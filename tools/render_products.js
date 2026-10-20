// Картинки каталогу ALUMA однією командою -> site/assets/products + поле images у catalog/products.json.
//
//   node tools/render_products.js                   усі товари й свотчі: AVIF/WebP/JPG + products.json
//   node tools/render_products.js tavor sahar       лише ці товари (finishes — лише свотчі)
//
// Джерела кадрів (усі — візуалізації, підпис «הדמיה» / «visualization», kind: "visualization"):
//   source "ai"     — кадри Figma AI (герой, крупний план), майстри PNG у $ALUMA_FIGMA
//                     (типово /opt/ihor/aluma-table/tmp/figma-ai, не в git): <товар>-<кадр>-v1.png;
//                     кожен звірено з моделлю (ніжки, опори, форма, пропорції) — docs/ASSETS.md;
//   свотчі тонувань — three.js-сцена tools/render_products.html (file://, без власного порту).
// Вихід: site/assets/products/<id>/<кадр>-{<ширина>,800}.{avif,webp} + <кадр>-<ширина>.jpg — у рідній ширині
// майстра, без збільшення; site/assets/products/finishes/<тонування>.{avif,webp,jpg}.
// Герой AVIF ≤ 180 КБ: якість знижується, поки файл не влізе.

const { chromium } = require('playwright');
const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT = path.resolve(__dirname, '..');
const HTML = 'file://' + path.join(__dirname, 'render_products.html');
const CATALOG = path.join(ROOT, 'catalog', 'products.json');
const MASTER = path.join(ROOT, 'renders-master', 'products');
const FIGMA = process.env.ALUMA_FIGMA || '/opt/ihor/aluma-table/tmp/figma-ai';
const OUT = path.join(ROOT, 'site', 'assets', 'products');
const HERO_AVIF_MAX = 180 * 1024;

const only = process.argv.slice(2).filter(a => !a.startsWith('--'));

// Розмір для кадрів — типовий у сітці (середній), щоб пропорції на фото відповідали найходовішому.
const MAIN_SIZE = { tavor: '180×90', sahar: null, ofek: '180', saf: '130', tal: '100×60' };

// Підписи кадрів (alt): he/en, за змістом, з «הדמיה» / «visualization» — контракт ночі, закон про захист
// споживача і доступність (ת"י 5568): що за річ, тонування, ракурс.
const KIND = {
  tavor: ['שולחן אוכל נפתח', 'extendable dining table'],
  sahar: ['שולחן אוכל עגול נפתח', 'round extendable dining table'],
  ofek:  ['מזנון טלוויזיה תלוי', 'wall-mounted media unit'],
  saf:   ['קונסולה', 'console table'],
  tal:   ['שולחן סלון', 'coffee table']
};
const VIEW_ALT = {
  hero:   ['בחלל מגורים באור יום', 'in a living room in daylight'],
  angle:  ['במבט נמוך מהצד', 'low three-quarter view'],
  open:   ['פתוח עם התוספת', 'extended with the leaf'],
  round:  ['בגרסה העגולה Ø80', 'round version, Ø80']
};
// крупний план — своя деталь у кожного товару
const DETAIL_ALT = {
  tavor: ['תקריב של הקנט המשופע מלמטה ושל הרגל המתחדדת', 'close-up of the edge bevelled underneath and the tapered leg'],
  sahar: ['תקריב של הפלטה העגולה ושל קו החיבור באמצע', 'close-up of the round top and the seam where it opens'],
  ofek:  ['תקריב של החזיתות עם חריצים אנכיים, בלי ידיות', 'close-up of the fluted fronts with no handles'],
  saf:   ['תקריב של המגירה עם חריץ אחיזה במקום ידית', 'close-up of the drawer with a finger groove instead of a handle'],
  tal:   ['תקריב של הפינה המעוגלת ושל הרגל העגולה העבה', 'close-up of the rounded corner and the chunky round leg']
};
function altFor(p, view, fin, base) {
  const [kh, ke] = KIND[p.id], [vh, ve] = view === 'detail' ? DETAIL_ALT[p.id] : VIEW_ALT[view];
  const bh = base === 'steel' && view !== 'steel' ? ', בסיס פלדה' : '', be = base === 'steel' && view !== 'steel' ? ', steel base' : '';
  return {
    he: `הדמיה: ${kh} ${p.name.he}, גוון ${fin.he}, ${vh}${bh}`,
    en: `Visualization: ${p.name.en} ${ke}, ${fin.en.toLowerCase()} finish, ${ve}${be}`
  };
}

// Кадри товару: перший — герой (головна картинка картки), далі крупний план.
function framesFor(p) {
  const base = p.bases.length ? 'oak' : 'none';
  return [
    { name: 'hero', view: 'hero', source: 'ai', file: `${p.id}-hero-v1.png`, finish: 'natural', base },
    { name: 'detail', view: 'detail', source: 'ai', file: `${p.id}-detail-v1.png`, finish: 'natural', base }
  ];
}

function sizeFor(p) {
  const want = MAIN_SIZE[p.id];
  return p.sizes.find(s => s.label === want) || p.sizes[Math.floor((p.sizes.length - 1) / 2)];
}

function run(cmd, a) {
  const r = spawnSync(cmd, a, { stdio: ['ignore', 'pipe', 'pipe'] });
  if (r.status !== 0) throw new Error(cmd + ' ' + a.join(' ') + '\n' + r.stderr);
  return r.stdout.toString();
}
function dims(src) {
  const [w, h] = run('identify', ['-format', '%w %h', src + '[0]']).trim().split(' ').map(Number);
  return { w, h };
}
// Дві ширини: рідна ширина майстра (не більше 1600, без збільшення) і 800.
function encode(src, dstBase, W, hero) {
  for (const width of [W, 800]) {
    let q = hero && width === W ? 68 : 62;
    for (;;) {
      run('convert', [src, '-resize', width + 'x', '-strip', '-quality', String(q), `${dstBase}-${width}.avif`]);
      if (!(hero && width === W) || fs.statSync(`${dstBase}-${width}.avif`).size <= HERO_AVIF_MAX || q <= 30) break;
      q -= 4;
    }
    run('convert', [src, '-resize', width + 'x', '-strip', '-quality', '80', '-define', 'webp:method=6', `${dstBase}-${width}.webp`]);
  }
  run('convert', [src, '-resize', W + 'x', '-strip', '-sampling-factor', '4:2:0', '-interlace', 'JPEG', '-quality', '82', `${dstBase}-${W}.jpg`]);
}

(async () => {
  const catalog = JSON.parse(fs.readFileSync(CATALOG, 'utf8'));
  for (const p of catalog) {
    if (only.length && !only.includes(p.id)) continue;
    const dir = path.join(OUT, p.id);
    fs.rmSync(dir, { recursive: true, force: true });   // кадри товару — лише те, що в images
    fs.mkdirSync(dir, { recursive: true });
    const images = [];
    for (const f of framesFor(p)) {
      const src = path.join(FIGMA, f.file);
      if (!fs.existsSync(src)) throw new Error('немає майстра ' + src + ' (docs/ASSETS.md)');
      const { w, h } = dims(src), W = Math.min(1600, w), H = Math.round(h * W / w);
      encode(src, path.join(dir, f.name), W, f.view === 'hero');
      const size = sizeFor(p), fin = p.finishes.find(x => x.id === f.finish).name;
      const rel = `assets/products/${p.id}/${f.name}`;
      images.push({
        src: `${rel}-${W}.jpg`, avif: `${rel}-${W}.avif`, webp: `${rel}-${W}.webp`,
        srcset: { avif: `${rel}-800.avif 800w, ${rel}-${W}.avif ${W}w`, webp: `${rel}-800.webp 800w, ${rel}-${W}.webp ${W}w` },
        width: W, height: H, view: f.view, finish: f.finish, base: f.base, state: 'closed', size: size.label,
        alt: altFor(p, f.view, fin, f.base), kind: 'visualization', source: f.source
      });
      console.log(`${p.id}/${f.name} ${W}×${H}`);
    }
    p.images = images;
    p.model3d = 'assets/products/aluma3d.js';
  }
  fs.writeFileSync(CATALOG, JSON.stringify(catalog, null, 2) + '\n');
  if (!only.length || only.includes('finishes')) await swatches(catalog[0].finishes.map(f => f.id));
})().catch(e => { console.error(e); process.exit(1); });

// Свотчі тонувань: дощечка 60×60 згори під скісним світлом (three.js) — спільні для всіх товарів.
async function swatches(finishes) {
  if (!fs.existsSync(path.join(ROOT, 'renders-master', 'textures', 'oak-normal-2048.jpg'))) {
    throw new Error('немає renders-master/textures — python3 tools/fetch_assets.py && python3 tools/bake_textures.py');
  }
  const browser = await chromium.launch({ args: [
    '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
    '--allow-file-access-from-files'
  ] });
  const page = await browser.newPage();
  page.on('pageerror', e => console.error('page:', e.message));
  await page.goto(HTML);
  await page.waitForFunction(() => window.__ready === true && window.Aluma3D);
  for (const f of finishes) {
    const r = await page.evaluate(j => window.shot(j), { scene: 'swatch', finish: f, w: 480, h: 480, view: { az: 0, el: 89, fov: 20, margin: -0.9 } });
    const file = path.join(MASTER, 'finishes', f + '.png');
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, Buffer.from(r.png.split(',')[1], 'base64'));
    const dst = path.join(OUT, 'finishes', f);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    run('convert', [file, '-resize', '240x', '-strip', '-quality', '55', dst + '.avif']);
    run('convert', [file, '-resize', '240x', '-strip', '-quality', '80', dst + '.webp']);
    run('convert', [file, '-resize', '240x', '-strip', '-quality', '84', dst + '.jpg']);
    console.log('finishes/' + f);
  }
  await browser.close();
}
