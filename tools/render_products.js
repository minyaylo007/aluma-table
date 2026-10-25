// Картинки каталогу ALUMA однією командою -> site/assets/products + поле images у catalog/products.json.
//
//   node tools/render_products.js                   усі товари: AVIF/WebP/JPG + products.json
//   node tools/render_products.js tavor sahar       лише ці товари
//   --preview [--frames=a,b]  лише звірка ракурсів: ½ сторони, 12 семплів, renders-master/preview; каталог не чіпає
//   --add=home,finish,home-9x16  лише ці кадри (finish — карусель тонів): решта файлів і images товару лишається
//   --reuse        не рендерити Blender, якщо майстер PNG уже є    --samples=48   семпли Cycles (+ OIDN)
//
// Джерела кадрів (усі — візуалізації, kind: "visualization"; з 24.10 у підписі без «הדמיה», слово власника):
//   source "ai"     — кадри Figma AI (герой, крупний план), майстри PNG у $ALUMA_FIGMA
//                     (типово /opt/ihor/aluma-table/tmp/figma-ai, не в git): <товар>-<кадр>-v1.png;
//                     кожен звірено з моделлю (ніжки, опори, форма, пропорції) — docs/ASSETS.md;
//   source "render" — Blender Cycles (tools/blender_scene.py) над геометрією aluma3d.js: низький ракурс, розкладений;
//   зразки тонів — шматки справжніх сканів шпону, їх робить tools/oak_tones.py (не цей скрипт).
// Широкий кадр 16:9 (<товар>-wide-v1.png, якщо є) — поле товару wide, не в images.
// Вихід: site/assets/products/<id>/<кадр>-{<ширина>,800[,400 — hero, angle]}.{avif,webp} + <кадр>-<ширина>.jpg — у рідній ширині
// майстра, без збільшення.
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
// 800 px першого кадру героя головної (content.json HERO_PRODUCT) — LCP головної на телефоні: ≤ 12 КБ влазить
// у перше вікно TCP (~14 КБ), інакше Lighthouse mobile додає ще один круг мережі (+0,25 с; OFEK 21.10 — 18 КБ при q62).
// Решті карток якість важливіша за 0,2 с LCP (дирижер 21.10): ≤ 30 КБ, без помітної м'якості.
const HERO_PRODUCT = JSON.parse(fs.readFileSync(path.join(ROOT, 'content.json'), 'utf8')).HERO_PRODUCT;
const HERO_800_AVIF_MAX = 12 * 1024;
const CARD_800_AVIF_MAX = 30 * 1024;

const argv = process.argv.slice(2), only = argv.filter(a => !a.startsWith('--'));
const opt = Object.fromEntries(argv.filter(a => a.startsWith('--')).map(a => { const i = a.indexOf('='); return i < 0 ? [a.slice(2), '1'] : [a.slice(2, i), a.slice(i + 1)]; }));

// Розмір для кадрів — типовий у сітці (середній), щоб пропорції на фото відповідали найходовішому.
const MAIN_SIZE = { tavor: '180×90', sahar: null, ofek: '180', saf: '130', tal: '100×60' };

// Підписи кадрів (alt): he/en, за змістом — доступність (ת"י 5568): що за річ, тонування, ракурс. Без «הדמיה» /
// «visualization» (власник 24.10: «не пиши, що це візуалізація»); застереження про кадри — у terms_html, розділ «תמונות».
const KIND = {
  tavor: ['שולחן אוכל נפתח', 'extendable dining table'],
  sahar: ['שולחן אוכל עגול נפתח', 'round extendable dining table'],
  ofek:  ['מזנון טלוויזיה תלוי', 'wall-mounted media unit'],
  saf:   ['קונסולה', 'console table'],
  tal:   ['שולחן סלון', 'coffee table']
};
const VIEW_ALT = {
  hero:   ['בחלל מגורים באור יום', 'in a living room in daylight'],
  home:   ['בבית, ליד חלון באור יום, על ריצוף טראצו', 'at home by a window in daylight, on a terrazzo floor'],
  life:   ['בבית, באור יום מהחלון, ועליו ספר, כד וקערת לימונים', 'at home in daylight from the window, with a book, a jug and a bowl of lemons on it'],
  angle:  ['במבט נמוך מהצד', 'low three-quarter view'],
  open:   ['פתוח עם התוספת', 'extended with the leaf'],
  round:  ['בגרסה העגולה Ø80', 'round version, Ø80'],
  'mechanism-half':   ['מנגנון הפתיחה: פתוח למחצה, רואים את המסילות ואת פלטת ההארכה המקופלת מתחת למשטח',
                       'opening mechanism: half open, showing the runners and the folded leaf under the top'],
  'mechanism-closed': ['מנגנון הפתיחה: סגור, קו החיבור באמצע המשטח', 'opening mechanism: closed, the seam in the middle of the top'],
  'light-morning':    ['באור בוקר קריר מהחלון', 'in cool morning light from the window'],
  'light-evening':    ['באור ערב חם של מנורה מעל השולחן', 'in warm evening light from a lamp above the table'],
  texture:            ['תקריב של פורניר האלון ושל קנט האלון המלא', 'close-up of the oak veneer and the solid-oak edge'],
  wide:               ['בחלל מגורים מואר, מבט רחב', 'in a bright room, wide view']
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
  const [kh, ke] = KIND[p.id], [vh, ve] = view === 'detail' ? DETAIL_ALT[p.id]
    : view === 'angle' && ANGLE_ALT[p.id] ? ANGLE_ALT[p.id] : VIEW_ALT[key || view];
  const bh = base === 'steel' && view !== 'steel' ? ', בסיס פלדה' : '', be = base === 'steel' && view !== 'steel' ? ', steel base' : '';
  return {
    he: `${kh} ${p.name.he}, גוון ${fin.he}, ${vh}${bh}`,
    en: `${p.name.en} ${ke}, ${fin.en.toLowerCase()} finish, ${ve}${be}`
  };
}

// Підпис кадру AI_FRAMES: та сама схема, що в altFor, плюс ru (його altFor не дає — у каталозі ru дописано окремо).
function aiAlt(p, fin, [vh, ve, vr]) {
  const [kh, ke] = KIND[p.id], kr = { tavor: 'раздвижной обеденный стол' }[p.id];
  return {
    he: `${kh} ${p.name.he}, גוון ${fin.he}, ${vh}`,
    en: `${p.name.en} ${ke}, ${fin.en.toLowerCase()} finish, ${ve}`,
    ru: `${kr ? kr[0].toUpperCase() + kr.slice(1) : ''} ${p.name.ru || p.name.en}, тон «${fin.ru.toLowerCase()}», ${vr}`.trim()
  };
}

// Кадри товару: перший — герой (головна картинка картки), далі низький ракурс (Blender), крупний план,
// розкладений (розсувні, Blender). cam — параметри камери tools/blender_scene.py (--cam).
// Галерея (запит дирижера 21.10): angle — не той самий кадр, що герой, а низько і з другого боку; у sahar — крупно
// ніжка з царгою (fit — частка габариту, як у DETAIL_RENDER).
const ANGLE = {
  tavor: { az: -38, eye: 0.6, margin: 0.04, sun: 7.0, window: 180 },
  sahar: { az: 20, eye: 0.45, lens: 70, fstop: 2.8, margin: 0.03, fit: [[0.62, 0, 0.25], [1, 0.4, 1]], sun: 7.0, window: 180 },
  ofek:  { az: -34, eye: 0.7, margin: 0.05, sun: 7.0, window: 180, end_chair: false },
  saf:   { az: -34, eye: 0.6, margin: 0.05, sun: 7.0, window: 180, end_chair: false },
  tal:   { az: 36, eye: 0.85, margin: 0.08, end_chair: false }
};
const ANGLE_ALT = { sahar: ['תקריב של הרגל ושל המסגרת מתחת למשטח', 'close-up of a leg and the apron under the top'] };
// Світло героя (HERO_RENDER): крупний план під тим самим світлом, інакше шпон виходить темнішим і теплішим, ніж у героя.
const HERO_LIGHT = { sun: 7.0, window: 180, hdri_strength: 0.18, exposure: 1.6 };
// Крупний план дуба: кут стільниці — торець, кромка і шпон; fit — частка габариту (x, y, z), об'єктив 85 мм.
const TEXTURE = {
  ofek: { az: 40, eye: 1.25, lens: 85, fstop: 2.8, margin: 0.02, fit: [[0.78, 0, 0.7], [1, 0.6, 1]], end_chair: false, ...HERO_LIGHT },
  saf:  { az: 40, eye: 1.05, lens: 85, fstop: 2.8, margin: 0.02, fit: [[0.78, 0, 0.82], [1, 0.6, 1]], end_chair: false, ...HERO_LIGHT }
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
  tavor: { az: 30, eye: 1.25, margin: 0.2, sun: 7.0, window: 240, hdri_strength: 0.18, fstop: 2.8 },
  sahar: { az: 30, eye: 1.25, margin: 0.2, sun: 7.0, window: 240, hdri_strength: 0.18, fstop: 2.8 },
  ofek:  { az: 28, eye: 1.2, margin: 0.22, sun: 7.0, window: 240, hdri_strength: 0.18, fstop: 2.8, end_chair: false },
  saf:   { az: 30, eye: 1.2, margin: 0.22, sun: 7.0, window: 240, hdri_strength: 0.18, fstop: 2.8, end_chair: false }
};
// Крупний план рендером, де деталь AI не збіглася з моделлю: fit — частка габариту (x, y, z), спереду y = 0.
const DETAIL_RENDER = {
  tavor: { az: 42, eye: 1.05, lens: 70, fstop: 2.8, margin: 0.03, fit: [[0.78, 0, 0.35], [1, 0.45, 1]], sun: 7.0, window: 180 },
  sahar: { az: 15, eye: 1.25, lens: 70, fstop: 2.8, margin: 0.03, fit: [[0.3, 0, 0.6], [0.7, 0.35, 1]], sun: 7.0, window: 180 },
  ofek:  { az: 22, eye: 1.0, lens: 70, fstop: 2.8, margin: 0.04, fit: [[0, 0, 0], [0.52, 1, 1]], sun: 7.0, window: 180, end_chair: false },
  saf:   { az: 25, eye: 1.15, lens: 70, fstop: 2.8, margin: 0.03, fit: [[0.05, 0, 0.7], [0.6, 0.3, 1]], sun: 7.0, window: 180,
           end_chair: false },
  tal:   { az: 40, eye: 0.7, lens: 85, fstop: 2.8, margin: 0.03, fit: [[0.8, 0, 0.35], [1, 0.3, 1]], sun: 7.0, window: 180,
           end_chair: false }
};
// Кадри Figma AI другого заходу (22.10, docs/ASSETS.md): мають перевагу над HERO_RENDER / DETAIL_RENDER — запис
// HERO_RENDER.tavor лишається камерою вертикалі hero-9x16 і запасним шляхом (прибрати рядок тут — повернеться рендер).
// file — відносно $ALUMA_FIGMA; alt [he, en, ru] — сцена саме цього кадру (оливкова гілка, лимони, терацо, льон).
const AI_FRAMES = {
  tavor: {
    hero: { file: 'v2/tavor-hero-2.png', size: '200×100',
      alt: ['בחלל מגורים ים־תיכוני באור יום: ענפי זית באגרטל, קערת לימונים, ריצוף טראצו ווילון פשתן',
            'in a Mediterranean living room in daylight: olive branches in a vase, a bowl of lemons, terrazzo floor and a linen curtain',
            'в средиземноморской гостиной при дневном свете: ветки оливы в вазе, миска с лимонами, пол из терраццо и льняная штора'] },
    detail: { file: 'v2/tavor-detail-1.png',
      alt: ['תקריב של פינת המשטח: קנט ישר עם שיפוע מלמטה, המסגרת והרגל המתחדדת, וכוס קרמיקה על השולחן',
            'close-up of the top corner: a straight edge bevelled underneath, the apron and the tapered leg, with a ceramic cup on the table',
            'крупный план угла столешницы: прямая кромка со скосом снизу, царга и сужающаяся ножка, на столе керамическая чашка'] }
  }
};
// Широкий кадр 16:9 рендером, де кадр AI не збігся з моделлю: та сама сцена, що в героя, камера далі.
const WIDE_RENDER = {
  sahar: { az: 26, eye: 1.3, lens: 85, margin: 0.5, sun: 7.0, window: 240, hdri_strength: 0.18 }
};
// Тонування рендером (карусель Meta, сесія 4): той самий кадр, камера й світло, міняється лише матеріал стола —
// справжній скан шпону цього тону (tools/oak_tones.py — ті самі файли, що зразок і 3D на сторінці), а не готовий кадр.
// Файли finish-<тонування>-{800,1600}.{avif,webp} і -1600.jpg; у images не йдуть.
const FINISH_SET = { tavor: 'home' };   // 21.10: карусель — у жилому кадрі, як і герой
// Вертикальні кадри 9:16 для Reels (сесія 4): та сама сцена, світло й камера, що в кадру; 1080×1920, лише JPG
// <кадр>-9x16.jpg поруч з кадром, у images не йдуть. Стіл цілком — у смузі y 300–1000 px (shift_y піднімає його
// вгору), нижче — підлога під плашку з текстом. Кадр без рендер-камери (герой tal — AI) бере VERTICAL_CAM.
const VERTICAL = { tavor: ['home', 'open', 'hero'], sahar: ['home', 'open', 'hero'], ofek: ['home', 'hero'], saf: ['home', 'hero'], tal: ['home', 'hero'] };
const VERTICAL_CAM = { az: 30, eye: 1.1, margin: 0.2, sun: 7.0, window: 180, hdri_strength: 0.18, end_chair: false };
const VERTICAL_SHIFT = { eye: 1.9, margin: 0.12, shift_y: -0.34 };
// Жилий кадр (власник 21.10: «у живому інтер'єрі»): та сама модель і матеріал, а кімната — ізраїльська квартира
// (blender_scene.py room: home) — плитка-терацо, вікно в кадрі з алюмінієвою рамою й жалюзі, фіранка, рослини, килим.
// Перший у images: він і обкладинка картки, і герой головної (content.json HERO_PRODUCT).
const HOME_LIGHT = { room: 'home', sun: 7.0, window: 150, hdri_strength: 0.16, exposure: 1.5, end_chair: false, fstop: 2.8 };
const HOME = {
  tavor: { az: 30, eye: 1.3, margin: 0.2, ...HOME_LIGHT, end_chair: true },
  sahar: { az: 30, eye: 1.3, margin: 0.22, ...HOME_LIGHT, end_chair: true },
  ofek:  { az: 24, eye: 1.2, margin: 0.42, ...HOME_LIGHT, plant: 'right' },
  saf:   { az: 26, eye: 1.15, margin: 0.32, ...HOME_LIGHT, plant: 'right' },
  tal:   { az: 28, eye: 1.1, margin: 0.4, ...HOME_LIGHT, rug: [1.9, 1.3, 0] }
};
// Кадр «як фото» (власник 24.10: «реальних фото не буде — зроби, щоб виглядало як фото»): та сама квартира, що в home,
// але камера на висоті очей (1,55 м, 40 мм), мала глибина різкості (f/2.2) і книжка на столі поруч із глечиком і
// лимонами — як знімає людина, що зайшла в кімнату. Перший у images: обкладинка картки й герой головної.
// №21 (власник 25.10: «щоб прям як справжні»): photo вмикає в blender_scene.py шпон смугами-листами, подряпини
// й пил, нерівну стіну й плитку, тканинну доріжку, паперовий шнур сидіння, чашку, другу книжку, розетку й
// вимикач; камера — пересвічене вікно з ореолом, бочка об'єктива, нахил горизонту на пів градуса, грубіше зерно.
const PHOTO = { photo: true, view_strength: 24, roll: 0.5, bloom: 0.4, distort: 0.025, grain: 0.012, ca: 1.0, vignette: 0.2 };
const LIFE = {
  tavor: { ...HOME.tavor, eye: 1.55, lens: 45, fstop: 2.2, margin: 0.03, az: 32, target_z: 0.55, book: true, ...PHOTO },
  sahar: { ...HOME.sahar, eye: 1.5, lens: 50, fstop: 2.2, margin: 0.02, az: 30, target_z: 0.5, book: true, ...PHOTO },
  ofek:  { ...HOME.ofek, eye: 1.5, lens: 45, fstop: 2.2, margin: 0.22, target_z: 0.6, book: true, ...PHOTO, mug: false },
  saf:   { ...HOME.saf, eye: 1.5, lens: 45, fstop: 2.2, margin: 0.14, book: true, ...PHOTO },
  tal:   { ...HOME.tal, eye: 1.35, lens: 45, fstop: 2.2, margin: 0.16, rug: [1.6, 1.1, 0], book: true, ...PHOTO }
};
function framesFor(p) {
  const base = p.bases.length ? 'oak' : 'none', ext = p.badges.some(b => b.id === 'extendable');
  const decor = p.category === 'dining_table' ? 'dining' : 'top';
  const L = [
    { name: 'life', view: 'hero', source: 'render', finish: 'natural', base, w: 1600, h: 1068, decor, cam: LIFE[p.id] },
    AI_FRAMES[p.id]?.hero
      ? { name: 'hero', view: 'hero', source: 'ai', finish: 'natural', base, ...AI_FRAMES[p.id].hero }
      : HERO_RENDER[p.id]
      ? { name: 'hero', view: 'hero', source: 'render', finish: 'natural', base, w: 1600, h: 1068, decor, cam: HERO_RENDER[p.id] }
      : { name: 'hero', view: 'hero', source: 'ai', file: `${p.id}-hero-v1.png`, finish: 'natural', base },
    { name: 'home', view: 'hero', source: 'render', finish: 'natural', base, w: 1600, h: 1068, decor, cam: HOME[p.id] },
    { name: 'angle', view: 'angle', source: 'render', finish: 'natural', base, w: 1600, h: 1200,
      decor: ANGLE_ALT[p.id] ? 'none' : decor, cam: ANGLE[p.id] },
    AI_FRAMES[p.id]?.detail
      ? { name: 'detail', view: 'detail', source: 'ai', finish: 'natural', base, ...AI_FRAMES[p.id].detail }
      : DETAIL_RENDER[p.id]
      ? { name: 'detail', view: 'detail', source: 'render', finish: 'natural', base, w: 1600, h: 1200, decor: 'none', cam: DETAIL_RENDER[p.id] }
      : { name: 'detail', view: 'detail', source: 'ai', file: `${p.id}-detail-v1.png`, finish: 'natural', base }
  ];
  if (ext) L.push({ name: 'open', view: 'open', source: 'render', finish: 'natural', base, state: 'open', w: 1600, h: 1000, decor,
    cam: { az: 30, eye: 2.1, margin: 0.1 } });   // згори: видно всю розкладену стільницю
  // порядок галереї (24.10): life (інтер'єр «як фото») → hero (чистий кадр) → крупний план дуба (тумба, консоль) → home → решта
  if (TEXTURE[p.id]) L.splice(2, 0, { name: 'texture', view: 'texture', source: 'render', finish: 'natural', base, w: 1600, h: 1200,
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
    const cam = Object.assign({ az: 38, eye: 1.0 }, { pendant: 'off', pendant_dx: 0.32, margin: 0.1, shift_y: 0.21 });   // запас угорі — у кадрі лампа
    L.push({ name: 'light-morning', view: 'light', light: 'morning', source: 'render', finish: 'natural', base, w: 1600, h: 1200, decor,
      cam: Object.assign({}, cam, LIGHT.morning) });
    L.push({ name: 'light-evening', view: 'light', light: 'evening', source: 'render', finish: 'natural', base, w: 1600, h: 1200, decor,
      cam: Object.assign({}, cam, LIGHT.evening, { pendant: 'on' }) });
  }
  return L;
}

// Рендер Blender — лише в рамці дирижера (systemd-run, ≤ 4 ГБ, ≤ 3 ядра, nice 15), один процес за раз.
// Фотореальний прохід (22.10): 256–512 семплів + OIDN, кадр 1600 px — до ~40 хв на 3 потоках.
const BLENDER = process.env.ALUMA_BLENDER || '/opt/ihor/aluma-table/tmp/blender/blender-4.5.14-linux-x64/blender';
const SAMPLES = +(opt.samples || 48);
function blender(geoFile, out, f, samples) {
  const a = ['180m', 'nice', '-n', '15', 'systemd-run', '--user', '--scope', '-q', '--slice=app-ihor\\x2dconductor.slice',
    '-p', 'MemoryMax=4G', '-p', 'CPUQuota=300%', BLENDER, '-b', '--factory-startup', '-P', path.join(__dirname, 'blender_scene.py'), '--',
    '--geo', geoFile, '--out', out, '--shot', f.view, '--w', String(f.w), '--h', String(f.h), '--samples', String(samples || SAMPLES), '--threads', '3',
    '--decor', f.decor, '--cam', JSON.stringify(f.cam || {}), '--finish', f.finish || 'natural'];
  if (f.albedo) a.push('--albedo', f.albedo);
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
// ставить у картку й плитку каталогу на телефоні (srcset). Для hero ще 1200: телефон 390 px з DPR 3 хоче 1170 px
// і без неї качав 1600 (22.10). AVIF, важчий за WebP, build.py picture() не віддає — увесь набір картинки йде WebP.
function widthsFor(view, W) {
  return [...new Set([(view === 'hero' || view === 'angle') && 400, 800, view === 'hero' && W > 1200 && 1200, W])]
    .filter(x => x && x <= W);
}
function encode(src, dstBase, W, hero, widths, max800 = CARD_800_AVIF_MAX) {
  for (const width of widths) {
    run('convert', [src, '-resize', width + 'x', '-strip', '-quality', '80', '-define', 'webp:method=6', `${dstBase}-${width}.webp`]);
    // AVIF має бути легшим за свій WebP, інакше build.py picture() не віддає AVIF-набір картинки взагалі (22.10):
    // якість знижується до першого «легший» (не нижче 45 — тоді лишається як є, і набір іде WebP)
    const webp = fs.statSync(`${dstBase}-${width}.webp`).size;
    let q = hero && width === W ? 68 : 62;
    const max = !hero ? Infinity : width === W ? HERO_AVIF_MAX : width === 800 ? max800 : Infinity;
    for (;;) {
      run('convert', [src, '-resize', width + 'x', '-strip', '-quality', String(q), `${dstBase}-${width}.avif`]);
      const size = fs.statSync(`${dstBase}-${width}.avif`).size;
      if ((size <= max && (size < webp || q <= 45)) || q <= 30) break;
      q -= size > max ? 4 : 5;
    }
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
  if (!fs.existsSync(path.join(ROOT, 'renders-master', 'textures', 'tone-black-albedo-2048.jpg'))) {
    throw new Error('немає renders-master/textures — python3 tools/fetch_assets.py && python3 tools/bake_textures.py && python3 tools/oak_tones.py');
  }
  const catalog = JSON.parse(fs.readFileSync(CATALOG, 'utf8'));
  const { browser, page } = await openPage();
  for (const p of catalog) {
    if (only.length && !only.includes(p.id)) continue;
    const dir = path.join(OUT, p.id);
    const add = opt.add ? opt.add.split(',') : null;
    if (!opt.preview && !add) {
      fs.rmSync(dir, { recursive: true, force: true });   // кадри товару — лише те, що в images
      fs.mkdirSync(dir, { recursive: true });
    }
    const images = [];
    for (const f of framesFor(p)) {
      if (add && !add.includes(f.name)) continue;
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
        src = path.join(FIGMA, f.file);   // AI_FRAMES: v2/<кадр>.png; решта — <товар>-<кадр>-v1.png
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
      encode(src, path.join(dir, f.name), W, f.view === 'hero', widths,
        p.id === HERO_PRODUCT ? HERO_800_AVIF_MAX : CARD_800_AVIF_MAX);
      const size = sizeFor(p), fin = p.finishes.find(x => x.id === f.finish).name;
      // формат вітрини (build.py picture()): src — WebP від кореня сайту, srcset/srcset_avif — рядки, jpg — запасний
      const rel = `/assets/products/${p.id}/${f.name}`, set = ext => widths.map(x => `${rel}-${x}.${ext} ${x}w`).join(', ');
      images.push({
        src: `${rel}-${W}.webp`, srcset: set('webp'), srcset_avif: set('avif'), jpg: `${rel}-${W}.jpg`,
        width: W, height: H, view: f.view, finish: f.finish, base: f.base, state: f.state || 'closed', size: f.size || size.label,
        alt: f.alt ? aiAlt(p, fin, f.alt) : altFor(p, f.view, fin, f.base, f.name), kind: 'visualization', source: f.source
      });
      if (f.light) images[images.length - 1].light = f.light;
      console.log(`${p.id}/${f.name} ${W}×${H}`);
    }
    if (FINISH_SET[p.id] && (!add || add.includes('finish'))) {
      const hero = framesFor(p).find(f => f.name === FINISH_SET[p.id]);
      for (const fin of p.finishes) {
        const f = Object.assign({}, hero, { name: 'finish-' + fin.id, finish: fin.id });
        const pdir = opt.preview ? path.join(MASTER, 'preview', p.id) : path.join(MASTER, p.id);
        if (opt.preview && opt.frames && !opt.frames.split(',').includes(f.name)) continue;
        // натуральний — це сам кадр героя, другий рендер не потрібен
        let src = path.join(pdir, (fin.id === hero.finish ? hero.name : f.name) + '.png');
        if (!(opt.reuse && fs.existsSync(src)) && !(fin.id === hero.finish && !opt.preview)) {
          const g = await page.evaluate(j => window.geo(j), { product: p.id, size: sizeFor(p), base: f.base, state: 'closed' });
          const geoFile = path.join(pdir, f.name + '.geo.json');
          fs.mkdirSync(pdir, { recursive: true });
          fs.writeFileSync(geoFile, JSON.stringify(g));
          src = path.join(pdir, f.name + '.png');
          const t0 = Date.now();
          blender(geoFile, src, opt.preview ? Object.assign({}, f, { w: Math.round(f.w / 2), h: Math.round(f.h / 2) }) : f, opt.preview ? 12 : undefined);
          console.log(`${p.id}/${f.name} blender ${((Date.now() - t0) / 1000).toFixed(0)} s`);
        }
        if (opt.preview) continue;
        const W = Math.min(1600, dims(src).w);
        encode(src, path.join(dir, f.name), W, false, widthsFor(f.view === 'hero' ? 'tone' : f.view, W));
        console.log(`${p.id}/${f.name} ${W}`);
      }
    }
    for (const name of VERTICAL[p.id] || []) {
      const base = framesFor(p).find(f => f.name === name);
      const f = Object.assign({}, base, { name: name + '-9x16', w: 1080, h: 1920,
        cam: Object.assign({}, base.source === 'render' ? base.cam : (name === 'hero' && HERO_RENDER[p.id]) || VERTICAL_CAM, VERTICAL_SHIFT) });
      if (opt.preview && !(opt.frames || '').split(',').includes(f.name)) continue;
      if (add && !add.includes(f.name)) continue;
      const pdir = opt.preview ? path.join(MASTER, 'preview', p.id) : path.join(MASTER, p.id);
      const src = path.join(pdir, f.name + '.png');
      if (!(opt.reuse && fs.existsSync(src) && !opt.preview)) {
        const g = await page.evaluate(j => window.geo(j), { product: p.id, size: sizeFor(p), base: f.base, state: f.state || 'closed' });
        const geoFile = path.join(pdir, f.name + '.geo.json');
        fs.mkdirSync(pdir, { recursive: true });
        fs.writeFileSync(geoFile, JSON.stringify(g));
        const t0 = Date.now();
        blender(geoFile, src, opt.preview ? Object.assign({}, f, { w: 540, h: 960 }) : f, opt.preview ? 12 : undefined);
        console.log(`${p.id}/${f.name} blender ${((Date.now() - t0) / 1000).toFixed(0)} s`);
      }
      if (opt.preview) continue;
      run('convert', [src, '-resize', '1080x1920!', '-strip', '-sampling-factor', '4:2:0', '-interlace', 'JPEG', '-quality', '84',
        path.join(dir, f.name + '.jpg')]);
      console.log(`${p.id}/${f.name} 1080×1920`);
    }
    if (add) {
      // --add=<кадри>: нові кадри стають на своє місце за framesFor, старі записи images лишаються; wide — лише якщо названо
      const order = framesFor(p).map(f => f.name), nameOf = im => im.src.split('/').pop().replace(/-\d+\.webp$/, '');
      if (!opt.preview) {
        p.images = [...images, ...p.images.filter(im => !images.some(n => nameOf(n) === nameOf(im)))]
          .sort((a, b) => order.indexOf(nameOf(a)) - order.indexOf(nameOf(b)));
      }
      if (!add.includes('wide')) continue;
    } else if (!opt.preview) p.images = images;
    // широкий кадр 16:9 (Figma AI або рендер, WIDE_RENDER) — для шапки й обкладинок Meta; окреме поле, не в images: у галерею картки не йде
    let wide = path.join(FIGMA, `${p.id}-wide-v1.png`);
    if (WIDE_RENDER[p.id]) {
      const f = { name: 'wide', view: 'hero', finish: 'natural', base: p.bases.length ? 'oak' : 'none', w: 1600, h: 900,
        decor: p.category === 'dining_table' ? 'dining' : 'top', cam: WIDE_RENDER[p.id] };
      const pdir = opt.preview ? path.join(MASTER, 'preview', p.id) : path.join(MASTER, p.id);
      wide = path.join(pdir, 'wide.png');
      if (!(opt.reuse && fs.existsSync(wide)) && (!opt.preview || (opt.frames || '').split(',').includes('wide'))) {
        const g = await page.evaluate(j => window.geo(j), { product: p.id, size: sizeFor(p), base: f.base, state: 'closed' });
        const geoFile = path.join(pdir, 'wide.geo.json');
        fs.mkdirSync(pdir, { recursive: true });
        fs.writeFileSync(geoFile, JSON.stringify(g));
        const t0 = Date.now();
        blender(geoFile, wide, opt.preview ? Object.assign({}, f, { w: 800, h: 450 }) : f, opt.preview ? 12 : undefined);
        console.log(`${p.id}/wide blender ${((Date.now() - t0) / 1000).toFixed(0)} s`);
      }
    }
    if (opt.preview) continue;
    if (fs.existsSync(wide)) {
      const { w, h } = dims(wide), W = Math.min(1600, w), H = Math.round(h * W / w), widths = widthsFor('wide', W);
      encode(wide, path.join(dir, 'wide'), W, false, widths);
      const rel = `/assets/products/${p.id}/wide`, set = ext => widths.map(x => `${rel}-${x}.${ext} ${x}w`).join(', ');
      p.wide = { src: `${rel}-${W}.webp`, srcset: set('webp'), srcset_avif: set('avif'), jpg: `${rel}-${W}.jpg`, width: W, height: H,
        view: 'wide', finish: 'natural', base: p.bases.length ? 'oak' : 'none', state: 'closed', size: sizeFor(p).label,
        alt: altFor(p, 'wide', p.finishes.find(x => x.id === 'natural').name, 'oak'), kind: 'visualization',
        source: WIDE_RENDER[p.id] ? 'render' : 'ai' };
      console.log(`${p.id}/wide ${W}×${H}`);
    } else delete p.wide;
    p.model3d = 'assets/products/aluma3d.js';
  }
  if (!opt.preview) fs.writeFileSync(CATALOG, JSON.stringify(catalog, null, 2) + '\n');
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
