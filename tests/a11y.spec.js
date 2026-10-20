// Доступність усіх сторінок (he і en) за axe-core: WCAG 2.0/2.1 A і AA — основа ת"י 5568 (תקנה 35).
// Без порту й без мережі: dist/ (python3 build.py) віддається через page.route на вигаданому origin,
// API підмінено, будь-який сторонній запит обривається. Конфіг — playwright.a11y.config.js.
// Падає на serious/critical; усі порушення (і moderate/minor) друкуються списком для сесії (1).
const path = require('path');
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const { ORIGIN, pages, serveDist, built } = require('./dist_route');
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const BLOCKING = new Set(['serious', 'critical']);

test.skip(!built(), 'спершу python3 build.py');

const VIEWPORTS = { mobile: { width: 390, height: 844 }, desktop: { width: 1280, height: 900 } };

for (const pagePath of pages()) {
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

// Стани, яких нема при завантаженні: axe бачить лише те, що на екрані. ת"י 5568 вимагає доступності й після дії —
// відкрите меню, панель доступності з усіма режимами (висока контрастність може зламати контраст), помилки форми.
async function axeBlocking(page) {
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const lines = result.violations.map((v) => `${v.impact}\t${v.id}\t${v.nodes.length}\t${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);
  if (lines.length) console.log(`AXE ${page.url()} (стан)\n` + lines.join('\n'));
  return result.violations.filter((v) => BLOCKING.has(v.impact)).map((v) => `${v.impact}: ${v.id} ×${v.nodes.length}`);
}

for (const pagePath of ['/', '/en/', '/p/tavor/', '/en/p/tavor/']) {
  test(`a11y стани ${pagePath}: меню, панель доступності, режими`, async ({ page }) => {
    await serveDist(page);
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.goto(ORIGIN + pagePath, { waitUntil: 'load' });
    await page.locator('.menu-btn').click();
    await expect(page.locator('.menu-btn')).toHaveAttribute('aria-expanded', 'true');
    expect(await axeBlocking(page), 'меню відкрите').toEqual([]);
    await page.locator('.menu-btn').click();
    await page.locator('.a11y-btn').click();
    await expect(page.locator('#a11y-panel')).toBeVisible();
    expect(await axeBlocking(page), 'панель відкрита').toEqual([]);
    for (const opt of ['font', 'contrast', 'links', 'still']) {
      await page.locator(`[data-a11y-opt="${opt}"]`).click();
      await expect(page.locator(`[data-a11y-opt="${opt}"]`)).toHaveAttribute('aria-pressed', 'true');
    }
    await page.setViewportSize(VIEWPORTS.desktop);
    expect(await axeBlocking(page), 'усі режими разом').toEqual([]);
  });

  test(`a11y стани ${pagePath}: порожня форма з помилками`, async ({ page }) => {
    await serveDist(page);
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.goto(ORIGIN + pagePath, { waitUntil: 'load' });
    const forms = page.locator('form[data-form]');
    const n = await forms.count();
    expect(n).toBeGreaterThan(0);
    for (let i = 0; i < n; i++) await forms.nth(i).locator('button[type="submit"]').click();
    await expect(page.locator('[aria-invalid="true"]').first()).toBeVisible();
    expect(await axeBlocking(page), 'помилки форми').toEqual([]);
  });
}
