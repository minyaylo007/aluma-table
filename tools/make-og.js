// Renders tools/og.html to site/assets/og.png at 1200x630 (the WhatsApp/Meta card).
// The logo lockup is inlined from site/assets/logo.svg so the card never depends on an external <use>.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
(async () => {
  const logo = fs.readFileSync(path.resolve(__dirname, '../site/assets/logo.svg'), 'utf8');
  const paths = Object.fromEntries([...logo.matchAll(/<path id="([\w-]+)" d="([^"]+)"/g)].map((m) => [m[1], m[2]]));
  const svg = `<svg class="logo" viewBox="0 -740 3703 740" fill="currentColor" aria-hidden="true"><path d="${paths['wordmark-he']}"/><path d="${paths.mark}"/></svg>`;
  const html = fs.readFileSync(path.resolve(__dirname, 'og.html'), 'utf8').replace('<!--LOGO-->', svg);
  const tmp = path.resolve(__dirname, '_og.tmp.html');
  fs.writeFileSync(tmp, html);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await p.goto('file://' + tmp, { waitUntil: 'networkidle' });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(500);
  await p.screenshot({ path: path.resolve(__dirname, '../site/assets/og.png') });
  await b.close();
  fs.unlinkSync(tmp);
  console.log('site/assets/og.png written');
})();
