// Ad creative from the 3D renders. Output: night/meta/creative/.
//
//   node tools/make-ads.js
//
// Every frame is a render of the modelled table on the brand's paper; the copy is
// the approved Hebrew from night/meta/ads.md. Nothing pretends to be a photograph
// and every image is labelled as a render in the ad text where Meta shows it.

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const OUT = path.resolve(ROOT, '..', 'night', 'meta', 'creative');
// the encoded variants are auto-cropped to the table, so the product fills each frame
const R = (n) => {
  for (const w of [1600, 1200, 800]) {
    const f = path.join(ROOT, 'site', 'assets', 'renders', n + '-' + w + '.webp');
    if (fs.existsSync(f)) return 'file:///' + f.split(path.sep).join('/');
  }
  throw new Error('no render variant for ' + n);
};
const FONTS = fs.readFileSync(path.join(ROOT, 'dist', 'assets', 'fonts', 'fonts.css'), 'utf8')
  .replace(/\/assets\/fonts\//g, 'file:///' + path.join(ROOT, 'dist', 'assets', 'fonts').replace(/\\/g, '/') + '/');
const C = JSON.parse(fs.readFileSync(path.join(ROOT, 'content.json'), 'utf8'));

const page = ({ w, h, body, extra = '' }) => `<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<style>${FONTS}
  :root{--paper:#e9e6de;--ink:#1a2434;--soft:#5c6678;--rule:#cbc5b7}
  html,body{margin:0;width:${w}px;height:${h}px;overflow:hidden;background:var(--paper);color:var(--ink);
    font-family:Assistant,sans-serif;-webkit-font-smoothing:antialiased}
  .ad{position:relative;width:${w}px;height:${h}px;box-sizing:border-box;display:flex;flex-direction:column;
      justify-content:space-between;padding:${Math.round(w * 0.06)}px}
  .mark{font-family:"Frank Ruhl Libre",serif;font-weight:700;font-size:${Math.round(w * 0.034)}px;line-height:1}
  .mark small{display:block;font-family:Assistant,sans-serif;font-weight:600;color:var(--soft);
      font-size:${Math.round(w * 0.016)}px;margin-top:6px;letter-spacing:.08em}
  .img{flex:1;display:flex;align-items:center;justify-content:center;min-height:0}
  .img img{max-width:100%;max-height:100%;object-fit:contain}
  h1{font-family:"Frank Ruhl Libre",serif;font-weight:700;font-size:${Math.round(w * 0.078)}px;line-height:1.1;margin:0}
  .sub{font-size:${Math.round(w * 0.032)}px;color:var(--soft);margin:${Math.round(w * 0.018)}px 0 0;max-width:26ch}
  .row{display:flex;align-items:baseline;gap:${Math.round(w * 0.02)}px;flex-wrap:wrap;margin-top:${Math.round(w * 0.02)}px}
  .price{font-family:"Frank Ruhl Libre",serif;font-weight:700;font-size:${Math.round(w * 0.075)}px;line-height:1;direction:ltr;unicode-bidi:isolate}
  .note{font-size:${Math.round(w * 0.026)}px;color:var(--soft)}
  .big{font-family:"Frank Ruhl Libre",serif;font-weight:700;font-size:${Math.round(w * 0.16)}px;line-height:1;direction:ltr;unicode-bidi:isolate}
  .num{direction:ltr;unicode-bidi:isolate}
  .tones{display:flex;gap:${Math.round(w * 0.02)}px}
  .tones div{flex:1;text-align:center;font-weight:600;font-size:${Math.round(w * 0.028)}px}
  .tones img{width:100%;display:block;border-radius:6px;background:var(--paper)}
  .render-note{position:absolute;bottom:${Math.round(w * 0.02)}px;left:${Math.round(w * 0.03)}px;font-size:${Math.round(w * 0.018)}px;color:var(--soft);direction:ltr}
  ${extra}
</style></head><body><div class="ad">${body}<div class="render-note">3D render · הדמיה</div></div></body></html>`;

const MARK = `<div class="mark">${C.BRAND_HE}<small>${C.BRAND_LAT}</small></div>`;
const PRICE = `<div class="row"><span class="price">${C.PRICE}</span><span class="note">כולל מע״מ, משלוח והרכבה</span></div>`;
const IMG = (n) => `<div class="img"><img src="${R(n)}" alt=""></div>`;

const ADS = [
  { file: 'a1_fits_1080x1080.png', w: 1080, h: 1080,
    body: `${MARK}${IMG('hero-natural-open')}
      <div><h1>שישה ביום שני.<br>עשרה בשישי בערב.</h1>
      <p class="sub">מ־<span class="num">160</span> ל־<span class="num">220</span> ס״מ בעשר שניות. הלוח שמור בתוך השולחן.</p>${PRICE}</div>` },
  { file: 'a1_fits_1080x1350.png', w: 1080, h: 1350,
    body: `${MARK}${IMG('hero-natural-open')}
      <div><h1>שישה ביום שני.<br>עשרה בשישי בערב.</h1>
      <p class="sub">מ־<span class="num">160</span> ל־<span class="num">220</span> ס״מ בעשר שניות. הלוח שמור בתוך השולחן.</p>${PRICE}</div>` },

  { file: 'a2_oak_1080x1080.png', w: 1080, h: 1080,
    body: `${MARK}${IMG('detail-smoked-closed')}
      <div class="tones">
        <div><img src="${R('end-natural-closed')}"><span>טבעי</span></div>
        <div><img src="${R('end-smoked-closed')}"><span>מעושן</span></div>
        <div><img src="${R('end-white-closed')}"><span>מולבן</span></div>
      </div>
      <div><h1>אלון אמיתי, לא הדפס</h1>
      <p class="sub">פורניר אלון, קנט אלון מלא, רגליים מאלון מלא. גימור שמן־שעווה שמתקנים במקום.</p>${PRICE}</div>`,
    extra: '.img img{max-height:44%}' },

  { file: 'a3_roomfit_1080x1080.png', w: 1080, h: 1080,
    body: `${MARK}
      <div class="img" style="flex:0 0 auto"><img src="${R('front-natural-open')}" style="max-height:330px"></div>
      <div style="border:1px solid var(--rule);border-radius:6px;padding:28px 32px;background:#f4f2ec">
        <div style="font-size:28px;color:var(--soft);margin-bottom:10px">אורך הקיר שלידו יעמוד השולחן</div>
        <div style="font-size:58px;font-weight:600" class="num">340 ס״מ</div>
        <div style="margin-top:18px;border-inline-start:4px solid #1f6f4a;padding-inline-start:18px">
          <div style="font-size:40px;font-weight:600">נכנס, גם פתוח</div>
          <div style="font-size:28px;color:var(--soft)">פתוח ל־<span class="num">220</span> יישארו <span class="num">60</span> ס״מ בכל קצה — מספיק כדי למשוך כיסא ולעבור.</div>
        </div>
      </div>
      <div><h1>ייכנס אצלכם? בדקו ב־<span class="num">20</span> שניות.</h1>
      <p class="sub">מזינים אורך קיר, מקבלים תשובה ישרה. בלי הרשמה.</p></div>` },

  { file: 'a4_story_1080x1080.png', w: 1080, h: 1080,
    body: `${MARK}${IMG('hero2-white-closed')}
      <div><h1>שולחן אחד. מידה אחת.<br>שלושה גוונים. זהו.</h1>
      <p class="sub">נגרייה משפחתית, אלון אירופי. שתי אריזות שטוחות, הרכבה של <span class="num">20</span> דקות — אצלכם.</p>
      <p class="sub" style="margin-top:10px">הזמנה מוקדמת · סדרה ראשונה</p></div>` },
];

const STORY = (img, headline, foot) => ({
  w: 1080, h: 1920,
  body: `<div style="height:200px"></div>${MARK}${IMG(img)}
    <div><div class="big">${headline}</div><p class="sub" style="font-size:44px;max-width:none">${foot}</p></div>
    <div style="height:200px"></div>`,
});
ADS.push({ file: 's1_grow_frame1_1080x1920.png', ...STORY('hero-natural-closed', '6', 'מקומות. יום רגיל.') });
ADS.push({ file: 's1_grow_frame2_1080x1920.png', ...STORY('hero-natural-open', '10', 'מקומות. עשר שניות אחר כך.') });
ADS.push({ file: 's1_grow_frame3_1080x1920.png', ...STORY('hero-natural-open', C.PRICE, 'כולל מע״מ, משלוח והרכבה. הזמנה מוקדמת.') });
for (const [tone, he] of [['natural', 'טבעי'], ['smoked', 'מעושן'], ['white', 'מולבן']]) {
  ADS.push({ file: `s2_tones_${tone}_1080x1920.png`, w: 1080, h: 1920,
    body: `<div style="height:200px"></div>${MARK}${IMG(`hero-${tone}-closed`)}
      <div><h1 style="font-size:110px">אלון ${he}</h1>
      <p class="sub" style="font-size:44px;max-width:none">שלושה גוונים. מידה אחת. ${C.PRICE} כולל הכול.</p></div>
      <div style="height:200px"></div>` });
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  // Chromium refuses file:// subresources from a setContent() document, so each ad is
  // written to disk and navigated to as a real file:// page.
  const TMP = path.join(ROOT, 'renders-master', '_ads-tmp');
  fs.mkdirSync(TMP, { recursive: true });
  const b = await chromium.launch();
  for (const ad of ADS) {
    const p = await b.newPage({ viewport: { width: ad.w, height: ad.h }, deviceScaleFactor: 1 });
    const html = path.join(TMP, ad.file.replace(/\.png$/, '.html'));
    fs.writeFileSync(html, page(ad));
    await p.goto('file:///' + html.split(path.sep).join('/'), { waitUntil: 'networkidle' });
    await p.evaluate(() => document.fonts.ready);
    await p.waitForTimeout(300);
    await p.screenshot({ path: path.join(OUT, ad.file) });
    await p.close();
    console.log('wrote', ad.file);
  }
  await b.close();
  fs.rmSync(TMP, { recursive: true, force: true });
})();
