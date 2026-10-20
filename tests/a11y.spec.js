// Доступність усіх сторінок (he і en) за axe-core: WCAG 2.0/2.1 A і AA — основа ת"י 5568 (תקנה 35).
// Без порту й без мережі: dist/ (python3 build.py) віддається через page.route на вигаданому origin,
// API підмінено, будь-який сторонній запит обривається. Конфіг — playwright.a11y.config.js.
// Падає на serious/critical; усі порушення (і moderate/minor) друкуються списком для сесії (1).
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const DIST = path.resolve(__dirname, '..', 'dist');
const ORIGIN = 'https://aluma.test';
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const BLOCKING = new Set(['serious', 'critical']);
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
  '.webp': 'image/webp', '.avif': 'image/avif', '.png': 'image/png', '.jpg': 'image/jpeg', '.woff2': 'font/woff2',
  '.json': 'application/json', '.glb': 'model/gltf-binary', '.webmanifest': 'application/manifest+json',
  '.xml': 'application/xml', '.txt': 'text/plain', '.ico': 'image/x-icon',
};

// Кожна .html у dist/ — сторінка: index.html → /, en/index.html → /en/, privacy.html → /privacy.
// (Файли без розширення поруч — копії .html для чистих адрес; віддаються як text/html.)
function pages() {
  const out = [];
  (function walk(dir) {
    for (const name of fs.readdirSync(dir).sort()) {
      const full = path.join(dir, name);
      if (fs.statSync(full).isDirectory()) { if (name !== 'assets') walk(full); continue; }
      if (!name.endsWith('.html')) continue;
      const rel = path.relative(DIST, full).split(path.sep).join('/');
      out.push(rel.endsWith('index.html') ? '/' + rel.slice(0, -'index.html'.length) : '/' + rel.slice(0, -5));
    }
  })(DIST);
  return out;
}

function fileFor(urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0]);
  const candidates = clean.endsWith('/') ? [clean + 'index.html'] : [clean, clean + '.html', clean + '/index.html'];
  for (const c of candidates) {
    const full = path.join(DIST, c);
    if (full.startsWith(DIST) && fs.existsSync(full) && fs.statSync(full).isFile()) return full;
  }
  return null;
}

async function serveDist(page) {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== ORIGIN) return route.abort();
    if (url.pathname === '/api/fx/config') {
      // з пікселем — щоб банер згоди (tracking.js або вітрини) теж пройшов перевірку
      return route.fulfill({ json: { pixel_id: '123456789012345', clarity_id: null, prelaunch: true, contact: {} } });
    }
    if (url.pathname.startsWith('/api/')) return route.fulfill({ json: { ok: true } });
    const file = fileFor(url.pathname);
    if (!file) return route.fulfill({ status: 404, contentType: 'text/html', body: fs.readFileSync(path.join(DIST, '404.html')) });
    return route.fulfill({ status: 200, contentType: TYPES[path.extname(file) || '.html'] || 'application/octet-stream', body: fs.readFileSync(file) });
  });
}

test.skip(!fs.existsSync(path.join(DIST, 'index.html')), 'спершу python3 build.py');

const VIEWPORTS = { mobile: { width: 390, height: 844 }, desktop: { width: 1280, height: 900 } };

for (const pagePath of fs.existsSync(DIST) ? pages() : []) {
  for (const [label, viewport] of Object.entries(VIEWPORTS)) {
    test(`a11y ${pagePath} (${label})`, async ({ page }, info) => {
      await serveDist(page);
      await page.setViewportSize(viewport);
      await page.goto(ORIGIN + pagePath, { waitUntil: 'load' });
      await page.waitForTimeout(300);                    // конфіг і банер згоди приходять асинхронно
      const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      const lines = result.violations.map((v) =>
        `${v.impact}\t${v.id}\t${v.nodes.length}\t${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}\t${v.helpUrl}`);
      if (lines.length) console.log(`AXE ${pagePath} ${label}\n` + lines.join('\n'));
      await info.attach('axe.json', { body: JSON.stringify(result.violations, null, 2), contentType: 'application/json' });
      const blocking = result.violations.filter((v) => BLOCKING.has(v.impact)).map((v) => `${v.impact}: ${v.id} ×${v.nodes.length}`);
      expect(blocking, `serious/critical на ${pagePath} (${label})`).toEqual([]);
    });
  }
}

// Власний банер згоди tracking.js (показується, коли вітрина не має свого #notice): кнопки, контраст, мова.
for (const pagePath of ['/', '/en/']) {
  test(`a11y банер tracking.js ${pagePath}`, async ({ page }) => {
    await serveDist(page);
    await page.goto(ORIGIN + pagePath, { waitUntil: 'load' });
    await page.evaluate(() => {
      const n = document.getElementById('notice'); if (n) n.remove();
      try { localStorage.removeItem('fx_notice_v1'); } catch (e) {}
      delete window.alumaTrack;
    });
    await page.addScriptTag({ path: path.resolve(__dirname, '..', 'site', 'assets', 'tracking.js') });
    const banner = page.locator('#aluma-notice');
    await expect(banner).toBeVisible();
    await expect(banner.getByRole('button')).toHaveCount(2);
    const result = await new AxeBuilder({ page }).include('#aluma-notice').withTags(TAGS).analyze();
    expect(result.violations.map((v) => `${v.impact}: ${v.id}`)).toEqual([]);
    await banner.getByRole('button').nth(1).click();          // «רק הכרחיות» / «Essential only»
    await expect(banner).toHaveCount(0);
    expect(await page.evaluate(() => window.alumaConsentState())).toBe('denied');
  });
}
