// Картинки каталогу ALUMA однією командою -> site/assets/products + поле images у catalog/products.json.
//
//   node tools/render_products.js                   усі товари й свотчі: AVIF/WebP/JPG + products.json
//   node tools/render_products.js tavor sahar       лише ці товари (finishes — лише свотчі)
//   --preview [--frames=a,b]  лише звірка ракурсів: ½ сторони, 12 семплів, renders-master/preview; каталог не чіпає
//   --reuse        не рендерити Blender, якщо майстер PNG уже є    --samples=48   семпли Cycles (+ OIDN)
//
// Джерела кадрів (усі — візуалізації, підпис «הדמיה» / «visualization», kind: "visualization"):
//   source "ai"     — кадри Figma AI (герой, крупний план), майстри PNG у $ALUMA_FIGMA
//                     (типово /opt/ihor/aluma-table/tmp/figma-ai, не в git): <товар>-<кадр>-v1.png;
//                     кожен звірено з моделлю (ніжки, опори, форма, пропорції) — docs/ASSETS.md;
//   source "render" — Blender Cycles (tools/blender_scene.py) над геометрією aluma3d.js: низький ракурс, розкладений;
//   свотчі тонувань — three.js-сцена tools/render_products.html (file://, без власного порту).
// Вихід: site/assets/products/<id>/<кадр>-{<ширина>,800[,400 — hero, angle]}.{avif,webp} + <кадр>-<ширина>.jpg — у рідній ширині
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

const argv = process.argv.slice(2), only = argv.filter(a => !a.startsWith('--'));
const opt = Object.fromEntries(argv.filter(a => a.startsWith('--')).map(a => { const i = a.indexOf('='); return i < 0 ? [a.slice(2), '1'] : [a.slice(2, i), a.slice(i + 1)]; }));

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
  round:  ['בגרסה העגולה Ø80', 'round version, Ø80'],
  'mechanism-half':   ['מנגנון הפתיחה: פתוח למחצה, רואים את המסילות ואת פלטת ההארכה המקופלת מתחת למשטח',
                       'opening mechanism: half open, showing the runners and the folded leaf under the top'],
  'mechanism-closed': ['מנגנון הפתיחה: סגור, קו החיבור באמצע המשטח', 'opening mechanism: closed, the seam in the middle of the top'],
  'light-morning':    ['באור בוקר קריר מהחלון', 'in cool morning light from the window'],
  'light-evening':    ['באור ערב חם של מנורה מעל השולחן', 'in warm evening light from a lamp above the table'],
  texture:            ['תקריב של פורניר האלון ושל קנט האלון המלא', 'close-up of the oak veneer and the solid-oak edge']
};
// крупний план — своя деталь у кожного товару
const DETAIL_ALT = {
  tavor: ['תקריב של הקנט המשופע מלמטה ושל הרגל המתחדדת', 'close-up of the edge bevelled underneath and the tapered leg'],
  sahar: ['תקריב של הפלטה העגולה ושל קו החיבור באמצע', 'close-up of the round top and the seam where it opens'],
  ofek:  ['תקריב של החזיתות עם חריצים אנכיים, בלי ידיות', 'close-up of the fluted fronts with no handles'],
  saf:   ['תקריב של המגירה עם חריץ אחיזה במקום ידית', 'close-up of the drawer with a finger groove instead of a handle'],
  tal:   ['תקריב של הפינה המעוגלת ושל הרגל העגולה העבה', 'close-up of the rounded corner and the chunky round leg']
};
function altFor(p, view, fin, base, key) {
  const [kh, ke] = KIND[p.id], [vh, ve] = view === 'detail' ? DETAIL_ALT[p.id] : VIEW_ALT[key || view];
  const bh = base === 'steel' && view !== 'steel' ? ', בסיס פלדה' : '', be = base === 'steel' && view !== 'steel' ? ', steel base' : '';
  return {
    he: `הדמיה: ${kh} ${p.name.he}, גוון ${fin.he}, ${vh}${bh}`,
    en: `Visualization: ${p.name.en} ${ke}, ${fin.en.toLowerCase()} finish, ${ve}${be}`
  };
}

// Кадри товару: перший — герой (головна картинка картки), далі низький ракурс (Blender), крупний план,
// розкладений (розсувні, Blender). cam — параметри камери tools/blender_scene.py (--cam).
const ANGLE = {
  tavor: { az: 38, eye: 1.0, margin: 0.06 },
  sahar: { az: 34, eye: 1.0, margin: 0.06 },
  ofek:  { az: 30, eye: 1.05, margin: 0.08, end_chair: false },
  saf:   { az: 32, eye: 1.05, margin: 0.08, end_chair: false },
  tal:   { az: 36, eye: 0.85, margin: 0.08, end_chair: false }
};
// Крупний план дуба: кут стільниці — торець, кромка і шпон; fit — частка габариту (x, y, z), об'єктив 85 мм.
const TEXTURE = {
  ofek: { az: 40, eye: 1.25, lens: 85, fstop: 2.8, margin: 0.02, fit: [[0.78, 0, 0.7], [1, 0.6, 1]], end_chair: false },
  saf:  { az: 40, eye: 1.05, lens: 85, fstop: 2.8, margin: 0.02, fit: [[0.78, 0, 0.82], [1, 0.6, 1]], end_chair: false }
};
// Світло пари: ранок — холодне бічне сонце з вікна; вечір — сутінки за вікном і тепла лампа над столом.
const LIGHT = {
  morning: { sun: 9.0, sun_color: [0.94, 0.97, 1.0], sun_dir: [0.95, 0.15, -0.32], window: 170, window_color: [0.82, 0.9, 1.0],
             hdri_strength: 0.12 },
  evening: { sun: 0.0, window: 10, window_color: [0.5, 0.6, 0.95], hdri_strength: 0.01, lamp: 90, lamp_color: [1.0, 0.7, 0.42],
             glow: 0.05, exposure: 1.1 }
};
// Герой рендером моделі (а не Figma AI), де кадр AI не збігся з моделлю (docs/ASSETS.md): інтер'єр, ранкове сонце
// з вікна ліворуч, м'яка тінь; 3:2, як герой Figma.
const HERO_RENDER = {
  tavor: { az: 30, eye: 1.25, margin: 0.2, sun: 7.0, window: 180, hdri_strength: 0.18 },
  ofek:  { az: 28, eye: 1.2, margin: 0.22, sun: 7.0, window: 180, hdri_strength: 0.18, end_chair: false },
  saf:   { az: 30, eye: 1.2, margin: 0.22, sun: 7.0, window: 180, hdri_strength: 0.18, end_chair: false }
};
// Крупний план рендером, де деталь AI не збіглася з моделлю: fit — частка габариту (x, y, z), спереду y = 0.
const DETAIL_RENDER = {
  tavor: { az: 42, eye: 1.05, lens: 70, fstop: 2.8, margin: 0.03, fit: [[0.78, 0, 0.35], [1, 0.45, 1]], sun: 7.0, window: 180 },
  sahar: { az: 15, eye: 1.25, lens: 70, fstop: 2.8, margin: 0.03, fit: [[0.3, 0, 0.6], [0.7, 0.35, 1]], sun: 7.0, window: 180 },
  saf:   { az: 25, eye: 1.15, lens: 70, fstop: 2.8, margin: 0.03, fit: [[0.05, 0, 0.7], [0.6, 0.3, 1]], sun: 7.0, window: 180,
           end_chair: false }
};
function framesFor(p) {
  const base = p.bases.length ? 'oak' : 'none', ext = p.badges.some(b => b.id === 'extendable');
  const decor = p.category === 'dining_table' ? 'dining' : 'top';
  const L = [
    HERO_RENDER[p.id]
      ? { name: 'hero', view: 'hero', source: 'render', finish: 'natural', base, w: 1600, h: 1068, decor, cam: HERO_RENDER[p.id] }
      : { name: 'hero', view: 'hero', source: 'ai', file: `${p.id}-hero-v1.png`, finish: 'natural', base },
    { name: 'angle', view: 'angle', source: 'render', finish: 'natural', base, w: 1600, h: 1200, decor, cam: ANGLE[p.id] },
    DETAIL_RENDER[p.id]
      ? { name: 'detail', view: 'detail', source: 'render', finish: 'natural', base, w: 1600, h: 1200, decor: 'none', cam: DETAIL_RENDER[p.id] }
      : { name: 'detail', view: 'detail', source: 'ai', file: `${p.id}-detail-v1.png`, finish: 'natural', base }
  ];
  if (ext) L.push({ name: 'open', view: 'open', source: 'render', finish: 'natural', base, state: 'open', w: 1600, h: 1000, decor,
    cam: { az: 30, eye: 1.42, margin: 0.1 } });
  // крупний план дуба (торець і шпон) без інтер'єру — одразу після героя: картка тумби й консолі
  if (TEXTURE[p.id]) L.splice(1, 0, { name: 'texture', view: 'texture', source: 'render', finish: 'natural', base, w: 1600, h: 1200,
    decor: 'none', cam: TEXTURE[p.id] });
  if (p.id === 'tavor') {
    // механізм: та сама камера над центром стола, вікно кадру — ±0,42 м від шва в обох станах
    const sz = sizeFor(p), leaf = (sz.extended_cm - sz.length_cm) / 100;
    for (const st of ['half', 'closed']) {
      const len = sz.length_cm / 100 + (st === 'half' ? leaf / 2 : 0), fx = 0.42 / len;
      L.push({ name: 'mechanism-' + st, view: 'mechanism', source: 'render', finish: 'natural', base, state: st, w: 1600, h: 1200,
        decor: 'none', cam: { az: 22, eye: 1.6, margin: 0.02, lens: 50, fstop: 5.6,
          fit: [[0.5 - fx, 0, 0.8], [0.5 + fx, 1, 1]] } });
    }
    // «ранок / вечір»: один ракурс і одна сцена, міняється лише світло — на сайті кадри змінюються плавно
    const cam = Object.assign({}, ANGLE.tavor, { pendant: 'off', pendant_dx: 0.32, margin: 0.1, shift_y: 0.21 });   // запас угорі — у кадрі лампа
    L.push({ name: 'light-morning', view: 'light', light: 'morning', source: 'render', finish: 'natural', base, w: 1600, h: 1200, decor,
      cam: Object.assign({}, cam, LIGHT.morning) });
    L.push({ name: 'light-evening', view: 'light', light: 'evening', source: 'render', finish: 'natural', base, w: 1600, h: 1200, decor,
      cam: Object.assign({}, cam, LIGHT.evening, { pendant: 'on' }) });
  }
  return L;
}

// Рендер Blender — лише в рамці дирижера (systemd-run, ≤ 4 ГБ, ≤ 3 ядра), один процес за раз.
const BLENDER = process.env.ALUMA_BLENDER || '/opt/ihor/aluma-table/tmp/blender/blender-4.5.14-linux-x64/blender';
const SAMPLES = +(opt.samples || 48);
function blender(geoFile, out, f, samples) {
  const a = ['120m', 'nice', '-n', '19', 'systemd-run', '--user', '--scope', '-q', '--slice=app-ihor\\x2dconductor.slice',
    '-p', 'MemoryMax=4G', '-p', 'CPUQuota=200%', BLENDER, '-b', '--factory-startup', '-P', path.join(__dirname, 'blender_scene.py'), '--',
    '--geo', geoFile, '--out', out, '--shot', f.view, '--w', String(f.w), '--h', String(f.h), '--samples', String(samples || SAMPLES), '--threads', '2',
    '--decor', f.decor, '--cam', JSON.stringify(f.cam || {})];
  const r = spawnSync('timeout', a, { stdio: ['ignore', 'pipe', 'pipe'], env: Object.assign({}, process.env, { TMPDIR: '/tmp' }), cwd: ROOT });
  if (r.status !== 0 || !/ALUMA_RENDER_OK/.test(r.stdout)) throw new Error('blender ' + f.name + '\n' + String(r.stderr).slice(-2000) + String(r.stdout).slice(-2000));
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
// Ширини: рідна ширина майстра (не більше 1600, без збільшення), 800, а для hero і angle ще 400 — їх вітрина
// ставить у картку й плитку каталогу на телефоні (srcset).
function widthsFor(view, W) {
  return [...new Set([(view === 'hero' || view === 'angle') && 400, 800, W])].filter(x => x && x <= W);
}
function encode(src, dstBase, W, hero, widths) {
  for (const width of widths) {
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

async function openPage() {
  const browser = await chromium.launch({ args: [
    '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
    '--allow-file-access-from-files'
  ] });
  const page = await browser.newPage();
  page.on('pageerror', e => console.error('page:', e.message));
  await page.goto(HTML);
  await page.waitForFunction(() => window.__ready === true && window.Aluma3D);
  return { browser, page };
}

(async () => {
  if (!fs.existsSync(path.join(ROOT, 'renders-master', 'textures', 'oak-normal-2048.jpg'))) {
    throw new Error('немає renders-master/textures — python3 tools/fetch_assets.py && python3 tools/bake_textures.py');
  }
  const catalog = JSON.parse(fs.readFileSync(CATALOG, 'utf8'));
  const { browser, page } = await openPage();
  for (const p of catalog) {
    if (only.length && !only.includes(p.id)) continue;
    const dir = path.join(OUT, p.id);
    if (!opt.preview) {
      fs.rmSync(dir, { recursive: true, force: true });   // кадри товару — лише те, що в images
      fs.mkdirSync(dir, { recursive: true });
    }
    const images = [];
    for (const f of framesFor(p)) {
      if (opt.preview) {
        if (opt.frames && !opt.frames.split(',').includes(f.name)) continue;
        // превью для звірки ракурсу: ¼ площі, 12 семплів, у renders-master/preview; images і каталог не чіпає
        if (f.source !== 'render') continue;
        const pf = Object.assign({}, f, { w: Math.round(f.w / 2), h: Math.round(f.h / 2) });
        const g = await page.evaluate(j => window.geo(j), { product: p.id, size: sizeFor(p), base: f.base, state: f.state || 'closed' });
        const pdir = path.join(MASTER, 'preview', p.id), geoFile = path.join(pdir, f.name + '.geo.json');
        fs.mkdirSync(pdir, { recursive: true });
        fs.writeFileSync(geoFile, JSON.stringify(g));
        const t0 = Date.now();
        blender(geoFile, path.join(pdir, f.name + '.png'), pf, 12);
        console.log(`preview ${p.id}/${f.name} ${((Date.now() - t0) / 1000).toFixed(0)} s`);
        continue;
      }
      let src;
      if (f.source === 'ai') {
        src = path.join(FIGMA, f.file);
        if (!fs.existsSync(src)) throw new Error('немає майстра ' + src + ' (docs/ASSETS.md)');
      } else {
        // геометрія з aluma3d.js (той самий код, що 3D-перегляд на сторінці) -> Blender -> майстер PNG
        src = path.join(MASTER, p.id, f.name + '.png');
        if (!(opt.reuse && fs.existsSync(src))) {
          const g = await page.evaluate(j => window.geo(j), { product: p.id, size: sizeFor(p), base: f.base, state: f.state || 'closed' });
          const geoFile = path.join(MASTER, p.id, f.name + '.geo.json');
          fs.mkdirSync(path.dirname(geoFile), { recursive: true });
          fs.writeFileSync(geoFile, JSON.stringify(g));
          const t0 = Date.now();
          blender(geoFile, src, f);
          console.log(`${p.id}/${f.name} blender ${((Date.now() - t0) / 1000).toFixed(0)} s`);
        }
      }
      const { w, h } = dims(src), W = Math.min(1600, w), H = Math.round(h * W / w);
      const widths = widthsFor(f.view, W);
      encode(src, path.join(dir, f.name), W, f.view === 'hero', widths);
      const size = sizeFor(p), fin = p.finishes.find(x => x.id === f.finish).name;
      // формат вітрини (build.py picture()): src — WebP від кореня сайту, srcset/srcset_avif — рядки, jpg — запасний
      const rel = `/assets/products/${p.id}/${f.name}`, set = ext => widths.map(x => `${rel}-${x}.${ext} ${x}w`).join(', ');
      images.push({
        src: `${rel}-${W}.webp`, srcset: set('webp'), srcset_avif: set('avif'), jpg: `${rel}-${W}.jpg`,
        width: W, height: H, view: f.view, finish: f.finish, base: f.base, state: f.state || 'closed', size: size.label,
        alt: altFor(p, f.view, fin, f.base, f.name), kind: 'visualization', source: f.source
      });
      if (f.light) images[images.length - 1].light = f.light;
      console.log(`${p.id}/${f.name} ${W}×${H}`);
    }
    if (opt.preview) continue;
    p.images = images;
    p.model3d = 'assets/products/aluma3d.js';
  }
  if (!opt.preview) fs.writeFileSync(CATALOG, JSON.stringify(catalog, null, 2) + '\n');
  if (!opt.preview && (!only.length || only.includes('finishes'))) await swatches(page, catalog[0].finishes.map(f => f.id));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });

// Свотчі тонувань: дощечка 60×60 згори під скісним світлом (three.js) — спільні для всіх товарів.
async function swatches(page, finishes) {
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
}
