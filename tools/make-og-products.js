// og:image, 1200x630 JPEG (Meta, WhatsApp, Telegram, X), усе — у site/assets/og/:
//   <slug>.jpg              — кожен товар: герой із catalog/products.json images[0];
//   <slug>.jpg              — «наступне видання» (catalog/next.json): його images[0];
//   home-<HERO>-<loc>.jpg   — головна й загальні сторінки he/en/ru: кадр героя HERO_PRODUCT (content.json), як у hero,
//                             hero_h1 з i18n, назва й діапазон цін із каталогу (як price_span у build.py). <HERO> в імені —
//                             щоб зміна HERO_PRODUCT без перегенерації ламала збірку, а не тихо лишала старе превью (№37).
// Без плашки «הדמיה» (з 25.10, слово власника 24.10: «не пиши, что это визуализация»; застереження — у terms);
// без знижок, телефонів, WhatsApp. Запуск після зміни героїв, цін, hero_h1 чи HERO_PRODUCT:
//   PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright node tools/make-og-products.js
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const root = path.resolve(__dirname, '..');
const cat = JSON.parse(fs.readFileSync(path.join(root, 'catalog/products.json'), 'utf8'));
const products = (Array.isArray(cat) ? cat : cat.products).filter((p) => !p.hidden);
const next = (JSON.parse(fs.readFileSync(path.join(root, 'catalog/next.json'), 'utf8')).items || []);
const content = JSON.parse(fs.readFileSync(path.join(root, 'content.json'), 'utf8'));
const LOCALES = ['he', 'en', 'ru'];
const out = (name) => path.join(root, 'site/assets/og', name);
// найбільший JPEG поруч із webp-кадром (hero-1264.webp → hero-1264.jpg); нема — сам webp (chromium його читає)
const frame = (src) => {
  const jpg = path.join(root, 'site', src.replace(/\.(webp|avif)$/, '.jpg'));
  return fs.existsSync(jpg) ? jpg : path.join(root, 'site', src);
};
// data: URL — setContent не дає читати file://
const b64 = (f) => `data:${f.endsWith('.webp') ? 'image/webp' : f.endsWith('.woff2') ? 'font/woff2' : 'image/jpeg'};base64,`
  + fs.readFileSync(f).toString('base64');
const font = (n) => b64(path.join(root, 'site/assets/fonts', n + '.woff2'));
// P — Plex (іврит, латиниця, кирилиця); F — Frank Ruhl (іврит, латиниця) + PT Serif (кирилиця), як у fonts-ru.css
const FONTS = [['P', 600, 'PlexSansHebrew-600-hebrew'], ['P', 600, 'PlexSansHebrew-600-latin'], ['PC', 600, 'PlexSans-600-cyrillic'],
  ['F', 400, 'FrankRuhlLibre-hebrew'], ['F', 400, 'FrankRuhlLibre-latin'], ['FC', 400, 'PTSerif-cyrillic']]
  .map(([f, w, n]) => `@font-face{font-family:${f};font-weight:${w};src:url(${font(n)}) format("woff2")}`).join('');
const esc = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;');
// ціни — як money()/price_span() у build.py: «₪4,490–5,290», ru «4 490–5 290 ₪»
const money = (v, loc) => (loc === 'ru' ? `${Number(v).toLocaleString('en-US').replace(/,/g, ' ')} ₪` : `₪${Number(v).toLocaleString('en-US')}`);
const priceSpan = (p, loc) => {
  const prices = [...new Set((p.sizes || []).filter((s) => s.price_ils).map((s) => Number(s.price_ils)))].sort((a, b) => a - b);
  if (!prices.length) return '';
  const [lo, hi] = [prices[0], prices[prices.length - 1]];
  if (lo === hi) return money(lo, loc);
  return loc === 'ru' ? `${money(lo, loc).slice(0, -2)}–${money(hi, loc)}` : `${money(lo, loc)}–${money(hi, loc).slice(1)}`;
};
const L = (v, loc) => (v && typeof v === 'object' ? v[loc] || v.en || v.he || '' : v || '');

async function shot(page, html, file) {
  await page.setContent(html, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: file, type: 'jpeg', quality: 82 });
  console.log(path.relative(root, file), fs.statSync(file).size, 'B');
}

(async () => {
  fs.mkdirSync(path.join(root, 'site/assets/og'), { recursive: true });
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  const plain = (img) => `<!doctype html><html><style>
    html,body{margin:0;width:1200px;height:630px;overflow:hidden;background:#F6F1E9}
    img{width:1200px;height:630px;object-fit:cover;object-position:50% 62%;display:block}
  </style><img src="${img}"></html>`;
  for (const item of [...products, ...next]) {
    const hero = (item.images || []).find((i) => i.src);
    if (!hero) { console.log('skip', item.slug, '(нема кадру)'); continue; }
    await shot(page, plain(b64(frame(hero.src))), out(item.slug + '.jpg'));
  }

  // головна: те, що бачать у WhatsApp і Facebook, коли діляться адресою сайту — той самий кадр, що в hero
  const heroP = products.find((x) => x.slug === content.HERO_PRODUCT) || products[0];
  const heroImg = (heroP.images || []).find((i) => i.src);
  for (const loc of LOCALES) {
    const t = JSON.parse(fs.readFileSync(path.join(root, 'i18n', loc + '.json'), 'utf8'));
    // hero_h1 несе <span class="acc"> — друга частина serif, як на сайті; іншої розмітки не пускаємо
    const m = String(t.hero_h1).match(/^(.*?)<span class="acc">(.*?)<\/span>(.*)$/);
    const h1 = m ? `${esc(m[1])}<span class="acc">${esc(m[2])}</span>${esc(m[3])}` : esc(String(t.hero_h1).replace(/<[^>]+>/g, ''));
    await shot(page, `<!doctype html><html dir="${loc === 'he' ? 'rtl' : 'ltr'}" lang="${loc}"><style>${FONTS}
      html,body{margin:0;width:1200px;height:630px;overflow:hidden;background:#211C17}
      img{position:absolute;inset:0;width:1200px;height:630px;object-fit:cover;object-position:50% 62%;display:block}
      .sh{position:absolute;inset:0;background:linear-gradient(to top,rgba(22,17,12,.88) 0%,rgba(22,17,12,.55) 42%,rgba(22,17,12,0) 74%)}
      .txt{position:absolute;inset-inline:64px;bottom:50px;color:#F6F1E9;font-family:P,PC,sans-serif}
      .logo{display:inline-block;font:400 28px/1 F,serif;letter-spacing:.32em;margin-bottom:20px}
      .logo small{font:600 22px/1 P,sans-serif;letter-spacing:0;margin-inline-start:14px;opacity:.85}
      h1{margin:0;font:600 50px/1.1 P,PC,sans-serif;letter-spacing:-.01em;max-width:1000px;text-shadow:0 2px 24px rgba(0,0,0,.3)}
      h1 .acc{display:block;font:400 50px/1.12 F,FC,serif;letter-spacing:0}
      .prod{margin:20px 0 0;font:600 30px/1.2 P,PC,sans-serif}
      .prod b{font:400 30px/1 F,FC,serif;letter-spacing:.12em;margin-inline-end:18px}
      p{margin:10px 0 0;font:600 21px/1.3 P,PC,sans-serif;opacity:.85}
    </style><img src="${b64(frame(heroImg.src))}"><div class="sh"></div>
    <div class="txt"><div class="logo" dir="ltr">ALUMA<small>אלומה</small></div><h1>${h1}</h1>
    <div class="prod"><b>${esc(L(heroP.name, loc))}</b><bdi dir="ltr">${esc(priceSpan(heroP, loc))}</bdi></div>
    <p>${esc(t.launch_bar_short)}</p></div></html>`, out(`home-${heroP.slug}-${loc}.jpg`));
  }
  await b.close();
})();
