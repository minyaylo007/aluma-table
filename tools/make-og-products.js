// og:image кожного товару: герой із catalog/images[0] → site/assets/og/<slug>.jpg, 1200x630 (Meta, WhatsApp, X).
// Загальні сторінки: home-he.jpg / home-en.jpg — герой HERO_PRODUCT із content.json, ALUMA і hero_h1 з i18n.
// Кадр — візуалізація, тож на ньому завжди позначка «הדמיה» / «Visualisation» (як на сайті). Запуск після зміни героїв:
//   PLAYWRIGHT_BROWSERS_PATH=... node tools/make-og-products.js
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const root = path.resolve(__dirname, '..');
const cat = JSON.parse(fs.readFileSync(path.join(root, 'catalog/products.json'), 'utf8'));
const products = (Array.isArray(cat) ? cat : cat.products).filter((p) => !p.hidden);
(async () => {
  fs.mkdirSync(path.join(root, 'site/assets/og'), { recursive: true });
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  for (const prod of products) {
    const hero = (prod.images || []).find((i) => i.src);
    if (!hero) continue;
    // найбільший JPEG поруч із webp-героєм (hero-1264.webp → hero-1264.jpg)
    const src = path.join(root, 'site', hero.src.replace(/\.(webp|avif)$/, '.jpg'));
    if (!fs.existsSync(src)) { console.log('skip', prod.slug, '(нема jpg)'); continue; }
    // data: URL — setContent не дає читати file://
    const font = 'data:font/woff2;base64,' + fs.readFileSync(path.join(root, 'site/assets/fonts/PlexSansHebrew-600-hebrew.woff2')).toString('base64');
    const img = 'data:image/jpeg;base64,' + fs.readFileSync(src).toString('base64');
    await p.setContent(`<!doctype html><html dir="rtl"><style>
      @font-face{font-family:P;src:url(${font}) format("woff2")}
      html,body{margin:0;width:1200px;height:630px;overflow:hidden;background:#F6F1E9}
      img{width:1200px;height:630px;object-fit:cover;object-position:50% 62%;display:block}
      span{position:absolute;top:24px;right:24px;font:600 22px/1 P,sans-serif;color:#F6F1E9;background:rgba(33,28,23,.72);
        padding:8px 14px;border-radius:999px}
    </style><img src="${img}"><span>הדמיה</span></html>`, { waitUntil: 'load' });
    await p.evaluate(() => document.fonts.ready);
    const out = path.join(root, 'site/assets/og', prod.slug + '.jpg');
    await p.screenshot({ path: out, type: 'jpeg', quality: 82 });
    console.log(out.replace(root + '/', ''));
  }
  // превью головної he/en: те, що бачать у WhatsApp і Facebook, коли діляться адресою сайту
  const content = JSON.parse(fs.readFileSync(path.join(root, 'content.json'), 'utf8'));
  const heroP = products.find((x) => x.slug === content.HERO_PRODUCT) || products[0];
  const heroImg = (heroP.images || []).find((i) => i.src);
  const b64 = (f, type) => `data:${type};base64,` + fs.readFileSync(path.join(root, f)).toString('base64');
  const fonts = [['P', 600, 'PlexSansHebrew-600-hebrew'], ['P', 600, 'PlexSansHebrew-600-latin'],
    ['F', 400, 'FrankRuhlLibre-hebrew'], ['F', 400, 'FrankRuhlLibre-latin']]
    .map(([f, w, n]) => `@font-face{font-family:${f};font-weight:${w};src:url(${b64('site/assets/fonts/' + n + '.woff2', 'font/woff2')}) format("woff2")}`).join('');
  const esc = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  for (const loc of ['he', 'en']) {
    if (!heroImg) break;
    const t = JSON.parse(fs.readFileSync(path.join(root, 'i18n', loc + '.json'), 'utf8'));
    const img = b64('site/' + heroImg.src.replace(/\.(webp|avif)$/, '.jpg'), 'image/jpeg');
    await p.setContent(`<!doctype html><html dir="${loc === 'he' ? 'rtl' : 'ltr'}" lang="${loc}"><style>${fonts}
      html,body{margin:0;width:1200px;height:630px;overflow:hidden;background:#211C17}
      img{position:absolute;inset:0;width:1200px;height:630px;object-fit:cover;object-position:50% 62%;display:block}
      .sh{position:absolute;inset:0;background:linear-gradient(to top,rgba(22,17,12,.86) 0%,rgba(22,17,12,.5) 40%,rgba(22,17,12,0) 72%)}
      .tag{position:absolute;top:28px;inset-inline-end:28px;font:600 22px/1 P,sans-serif;color:#F6F1E9;background:rgba(33,28,23,.72);
        padding:8px 14px;border-radius:999px}
      .txt{position:absolute;inset-inline:64px;bottom:56px;color:#F6F1E9}
      .logo{display:inline-block;font:400 30px/1 F,serif;letter-spacing:.32em;margin-bottom:22px}
      .logo small{font:600 24px/1 P,sans-serif;letter-spacing:0;margin-inline-start:14px;opacity:.85}
      h1{margin:0;font:400 64px/1.08 F,serif;max-width:900px;text-shadow:0 2px 24px rgba(0,0,0,.3)}
      p{margin:18px 0 0;font:600 24px/1.3 P,sans-serif;opacity:.88}
    </style><img src="${img}"><div class="sh"></div><span class="tag">${esc(t.viz_tag)}</span>
    <div class="txt"><div class="logo" dir="ltr">ALUMA<small>אלומה</small></div><h1>${esc(t.hero_h1)}</h1><p>${esc(t.launch_bar)}</p></div></html>`,
    { waitUntil: 'load' });
    await p.evaluate(() => document.fonts.ready);
    const out = path.join(root, 'site/assets/og', `home-${loc}.jpg`);
    await p.screenshot({ path: out, type: 'jpeg', quality: 82 });
    console.log(out.replace(root + '/', ''));
  }
  await b.close();
})();
