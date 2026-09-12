// QA screenshots of the local preview: node tools/shots.js [outDir] [--full]
// Hebrew + English at the brief's viewports; console errors, failed requests and overflow reported.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const OUT = path.resolve(process.argv[2] || 'renders-test/shots');
const FULL = process.argv.includes('--full');
const BASE = process.env.BASE_URL || 'http://127.0.0.1:4173';
const VIEWPORTS = [[1440, 900], [1920, 1080], [390, 844], [430, 932], [390, 700], [360, 667], [768, 1024], [1024, 768], [320, 640]];
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const report = [];
  for (const lang of ['he', 'en']) {
    for (const [w, h] of VIEWPORTS) {
      const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, locale: lang === 'he' ? 'he-IL' : 'en-IL' });
      const p = await ctx.newPage();
      const errors = [], failed = [];
      p.on('pageerror', e => errors.push(e.message));
      p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
      p.on('response', r => { if (r.status() >= 400) failed.push(r.status() + ' ' + r.url()); });
      await p.goto(BASE + (lang === 'he' ? '/' : '/en/'), { waitUntil: 'networkidle' });
      await p.evaluate(() => document.fonts.ready);
      const name = `${lang}-${w}x${h}`;
      await p.screenshot({ path: path.join(OUT, name + '-top.png') });
      const metrics = await p.evaluate(() => {
        const r = s => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return { top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left), width: Math.round(b.width), height: Math.round(b.height) }; };
        return { overflow: document.documentElement.scrollWidth - innerWidth, h1: r('h1'), heroImg: r('#hero-img'), price: r('.band .price'), cta: r('.band .btn--primary'), band: r('#band'), sticky: r('#sticky'), pageHeight: document.documentElement.scrollHeight };
      });
      if (FULL) {
        // scroll through so lazy images and reveals load, then a full-page capture
        await p.evaluate(async () => { for (let y = 0; y < document.documentElement.scrollHeight; y += 500) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); } window.scrollTo(0, 0); });
        await p.waitForTimeout(600);
        await p.screenshot({ path: path.join(OUT, name + '-full.png'), fullPage: true });
        for (const [id, sel] of [['configurator', '#table'], ['home', '[data-section="home"]'], ['materials', '[data-section="materials"]'], ['dimensions', '#dimensions'], ['offer', '[data-section="price"]'], ['faq', '#faq'], ['form', '#form'], ['footer', 'footer']]) {
          const el = await p.$(sel); if (!el) continue;
          await el.scrollIntoViewIfNeeded(); await p.waitForTimeout(250);
          await p.screenshot({ path: path.join(OUT, `${name}-${id}.png`) });
        }
      }
      report.push({ name, ...metrics, errors, failed });
      await ctx.close();
    }
  }
  await b.close();
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 1));
  for (const r of report) console.log(r.name, 'overflow', r.overflow, 'cta.bottom', r.cta && r.cta.bottom, 'hero', r.heroImg && [r.heroImg.top, r.heroImg.height], 'errors', r.errors.length, 'failed', r.failed.length, r.failed.slice(0, 2).join(' '), r.errors.slice(0, 2).join(' | '));
})();
