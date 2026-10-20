// og:image кожного товару: герой із catalog/images[0] → site/assets/og/<slug>.jpg, 1200x630 (Meta, WhatsApp, X).
// Кадр — візуалізація, тож на ньому завжди позначка «הדמיה» (як на сайті). Запуск після зміни героїв:
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
  await b.close();
})();
