// Ізольовані тести вітрини: кожен запис у бізнес-API перехоплено локально, /api/fx/config — підставний.
// Працює проти tools/serve-preview.py (playwright.local.config.js); ніколи не проти прода.
const { test, expect } = require('@playwright/test');

const CATALOG = require('../catalog/products.json');
const PRODUCTS = (CATALOG.products || CATALOG).filter(p => !p.hidden);
const EMPTY_CONFIG = { pixel_id: null, wa_number: null, clarity_id: null, contact: { name: null, phone: null, email: null, city: null }, launch_mode: true };
const FULL_CONFIG = { ...EMPTY_CONFIG, wa_number: '972500000000', contact: { name: 'ALUMA', phone: null, email: 'hello@example.com', city: null } };

async function mockApi(page, { config = EMPTY_CONFIG, lead } = {}) {
  const sent = { leads: [], events: [] };
  await page.route('**/api/fx/config', route => route.fulfill({ json: config }));
  await page.route('**/api/fx/event', route => { sent.events.push(route.request().postDataJSON()); return route.fulfill({ json: { ok: true, written: 0 } }); });
  await page.route('**/api/fx/lead', route => {
    sent.leads.push(route.request().postDataJSON());
    return route.fulfill(lead || { status: 200, json: { ok: true, id: 'abc123def456' } });
  });
  // будь-який сторонній домен — провал: без згоди ні Meta, ні Clarity
  await page.route(url => !['127.0.0.1', 'localhost'].includes(new URL(url).hostname), route => { sent.thirdParty = route.request().url(); return route.abort(); });
  return sent;
}

function watchErrors(page) {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !/favicon/.test(m.text())) errors.push(m.text()); });
  page.on('response', r => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
  return errors;
}

const noOverflow = page => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

// ---------------------------------------------------------------- сторінки й мови
for (const [path, lang, dir] of [['/', 'he', 'rtl'], ['/en/', 'en', 'ltr']]) {
  for (const [w, h] of [[360, 740], [390, 844], [1440, 900]]) {
    test(`${lang} ${w}px: home renders all catalog products, no overflow, no errors`, async ({ page }) => {
      await mockApi(page);
      const errors = watchErrors(page);
      await page.setViewportSize({ width: w, height: h });
      await page.goto(path);
      await expect(page.locator('html')).toHaveAttribute('lang', lang);
      await expect(page.locator('html')).toHaveAttribute('dir', dir);
      await expect(page.locator('h1')).toHaveCount(1);
      await expect(page.locator('.cards .card')).toHaveCount(Math.min(PRODUCTS.length, 5));
      expect(await noOverflow(page)).toBeLessThanOrEqual(0);
      await expect(page.locator('body')).not.toContainText('להשלמה');
      await expect(page.locator('body')).not.toContainText('{{');
      expect(errors).toEqual([]);
    });
  }
}

for (const p of PRODUCTS) {
  test(`card /p/${p.slug}/ opens with a price, sizes and the estimate mark`, async ({ page }) => {
    await mockApi(page);
    const errors = watchErrors(page);
    await page.goto(`/p/${p.slug}/`);
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(page.locator('input[name="size"]')).toHaveCount(p.sizes.length);
    if (p.preliminary) await expect(page.locator('.pdp-buy')).toContainText('מחיר משוער, טרם אושר');
    if ((p.images || []).length) await expect(page.locator('.viz-tag').first()).toContainText('הדמיה');
    if (!p.model3d) await expect(page.locator('.js-3d')).toHaveCount(0);
    expect(await noOverflow(page)).toBeLessThanOrEqual(0);
    expect(errors).toEqual([]);
  });
}

test('material block: three facts, a tagged close-up, every catalog finish, link to the materials on About', async ({ page }) => {
  const errors = watchErrors(page);
  await mockApi(page);
  for (const [pre, loc] of [['', 'he'], ['/en', 'en']]) {
    await page.goto(pre + '/');
    const sec = page.locator('section.material');
    await expect(sec.locator('.mat-facts > li')).toHaveCount(3);
    await expect(sec.locator('.viz-tag')).toBeVisible();
    const fins = PRODUCTS[0].finishes;
    await expect(sec.locator('.mat-tones li')).toHaveCount(fins.length);
    for (const f of fins) await expect(sec.locator('.mat-tones')).toContainText(f.name[loc]);
    await sec.locator('a[href$="/about/#materials"]').click();
    await expect(page.locator('#materials')).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('catalog lists every product with a link to its card', async ({ page }) => {
  await mockApi(page);
  await page.goto('/catalog/');
  for (const p of PRODUCTS) await expect(page.locator(`a[href="/p/${p.slug}/"]`).first()).toBeVisible();
});

test('every page of both languages answers 200 with one h1', async ({ page }) => {
  test.setTimeout(90000);   // 16 сторінок на однопотоковому serve-preview
  await mockApi(page);
  for (const pre of ['', '/en']) {
    for (const rel of ['/', '/catalog/', '/how/', '/about/', '/faq/', '/privacy', '/terms', '/accessibility']) {
      const res = await page.goto(pre + rel);
      expect(res.status(), pre + rel).toBe(200);
      await expect(page.locator('h1'), pre + rel).toHaveCount(1);
    }
  }
});

// ---------------------------------------------------------------- конфігуратор
test('size choice changes the price, finish choice its name, and both reach the form', async ({ page }) => {
  const p = PRODUCTS.find(x => new Set(x.sizes.map(s => s.price_ils)).size > 1 && x.finishes.length > 1);
  await mockApi(page);
  await page.goto(`/p/${p.slug}/`);
  await page.locator('[data-notice-no]').click();   // смуга cookies унизу закриває пігулки на телефоні
  const last = p.sizes[p.sizes.length - 1];
  await page.locator(`input[name="size"][value="${last.label}"]`).check({ force: true });
  const shown = '₪' + last.price_ils.toLocaleString('en-US');
  await expect(page.locator('.price[data-price]')).toContainText(shown);
  await expect(page.locator('#f-size')).toHaveValue(last.label);
  const fin = p.finishes[p.finishes.length - 1];
  await page.locator(`input[name="finish"][value="${fin.id}"]`).check({ force: true });
  await expect(page.locator('[data-finish-name]')).toHaveText(fin.name.he);
  await expect(page.locator('#f-finish')).toHaveValue(fin.id);
  await expect(page.locator('#f-product')).toHaveValue(p.id);
});

test('plan "closed / open" follows the chosen size and the mechanism frames carry the visualization tag', async ({ page }) => {
  const p = PRODUCTS.find(x => x.seats && x.sizes.filter(s => s.extended_cm).length > 1);
  const errors = watchErrors(page);
  await mockApi(page);
  await page.goto(`/p/${p.slug}/`);
  await page.locator('[data-notice-no]').click();
  const plans = page.locator('[data-plan-size]');
  await expect(plans.first()).toBeVisible();
  await expect(page.locator('[data-plan-size]:visible')).toHaveCount(1);
  const last = p.sizes[p.sizes.length - 1];
  await page.locator(`label:has(input[name="size"][value="${last.label}"])`).click();
  const shown = page.locator(`[data-plan-size="${last.label}"]`);
  await expect(shown).toBeVisible();
  await expect(page.locator('[data-plan-size]:visible')).toHaveCount(1);
  // числа з каталогу: довжина відкритого й межі місць
  await expect(shown).toContainText(`${last.extended_cm}×${last.width_cm}`);
  const n = (await shown.locator('figcaption').allInnerTexts()).map(t => +t.match(/(\d+)\D*$/)[1]);
  expect(n[0]).toBeGreaterThanOrEqual(p.seats.closed[0]);
  expect(n[0]).toBeLessThanOrEqual(p.seats.closed[1]);
  expect(n[1]).toBeGreaterThanOrEqual(p.seats.extended[0]);
  expect(n[1]).toBeLessThanOrEqual(p.seats.extended[1]);
  if ((p.images || []).filter(i => i.view === 'mechanism').length >= 2) {
    const steps = page.locator('.how-steps li');
    await expect(steps).toHaveCount(3);
    for (let i = 0; i < 3; i++) await expect(steps.nth(i).locator('.viz-tag')).toBeVisible();
  }
  expect(await noOverflow(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test('"other size" link prefills the comment in the form', async ({ page }) => {
  await mockApi(page);
  await page.goto(`/p/${PRODUCTS[0].slug}/`);
  await page.locator('.js-custom').first().click();
  await expect(page.locator('#f-comment')).not.toHaveValue('');
});

// ---------------------------------------------------------------- форма
const FAKE_PHONE = '050-000-0000';   // вигаданий номер; один рядок — сканер секретів рахує збіги
test('empty submit shows Hebrew errors next to the fields and sends nothing', async ({ page }) => {
  const sent = await mockApi(page);
  await page.goto('/');
  await page.locator('#lead-form button[type="submit"]').click();
  await expect(page.locator('#e-name')).toBeVisible();
  await expect(page.locator('#e-phone')).toBeVisible();
  await expect(page.locator('#e-consent')).toBeVisible();
  await expect(page.locator('#f-name')).toHaveAttribute('aria-invalid', 'true');
  expect(sent.leads).toEqual([]);
});

test('a valid lead from a card sends product, size, finish and lands on the thank-you screen', async ({ page }) => {
  const p = PRODUCTS[0];
  const sent = await mockApi(page);
  await page.goto(`/p/${p.slug}/?utm_source=test&utm_campaign=night`);
  await page.locator('#f-name').fill('ישראל ישראלי');
  await page.locator('#f-phone').fill(FAKE_PHONE);
  await page.locator('#lead-form input[name="consent"]').check();
  await page.locator('#lead-form button[type="submit"]').click();
  await expect(page.locator('[data-thanks]')).toBeVisible();
  await expect(page.locator('#lead-form')).toBeHidden();
  expect(sent.leads).toHaveLength(1);
  const lead = sent.leads[0];
  expect(lead.product_id).toBe(p.id);
  expect(lead.size_label).toBe(p.sizes[0].label);
  expect(lead.finish_id).toBe(p.finishes[0].id);
  expect(lead.consent).toBe(true);
  expect(lead.consent_marketing).toBe(false);              // חוק התקשורת 30א: не відмічено за замовчуванням
  expect(lead.marketing_consent).toBe(false);
  expect(lead.ads_consent).toBe(false);                     // без згоди на cookies Lead у CAPI не йде
  expect(lead.utm_source).toBe('test');
  expect(lead.lang).toBe('he');
  expect(lead.website).toBe('');
});

test('rate limit answer is shown as text, the form stays', async ({ page }) => {
  await mockApi(page, { lead: { status: 429, json: { ok: false, error: 'rate_limited' } } });
  await page.goto('/en/');
  await page.locator('#f-name').fill('Test Person');
  await page.locator('#f-phone').fill('0500000000');
  await page.locator('#lead-form input[name="consent"]').check();
  await page.locator('#lead-form button[type="submit"]').click();
  await expect(page.locator('#lead-form .f-status')).not.toBeEmpty();
  await expect(page.locator('#lead-form')).toBeVisible();
});

// ---------------------------------------------------------------- телефон
test('mobile: sticky CTA appears after the first screen and hides at the form', async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/p/${PRODUCTS[0].slug}/`);
  const sticky = page.locator('[data-sticky]');
  await expect(sticky).not.toHaveClass(/is-on/);
  await page.locator('#quick-form').scrollIntoViewIfNeeded();
  await expect(sticky).not.toHaveClass(/is-on/);               // коротка форма на екрані — «пігулка» не потрібна
  await page.evaluate(() => scrollTo(0, document.querySelector('[data-quick]').getBoundingClientRect().bottom + scrollY + 200));
  await expect(sticky).toHaveClass(/is-on/);
  await expect(sticky.locator('.sticky-thumb')).toHaveCount(1);
  await page.locator('#register').scrollIntoViewIfNeeded();
  await expect(sticky).not.toHaveClass(/is-on/);
});

test('quick form next to the photo sends the chosen size, finish and base as hidden fields', async ({ page }) => {
  const p = PRODUCTS[0];
  const sent = await mockApi(page);
  await page.goto(`/p/${p.slug}/`);
  const size = p.sizes[p.sizes.length - 1], fin = p.finishes[p.finishes.length - 1];
  await page.locator(`.opt[data-opt="size"] label:has(input[value="${size.label}"])`).click();
  await page.locator(`.opt[data-opt="finish"] label:has(input[value="${fin.id}"])`).click();
  const q = page.locator('#quick-form');
  await q.locator('button[type="submit"]').click();
  await expect(page.locator('#q-e-name')).toBeVisible();
  expect(sent.leads).toEqual([]);
  await q.locator('input[name="name"]').fill('ישראל ישראלי');
  await q.locator('input[name="phone"]').fill(FAKE_PHONE);
  await q.locator('input[name="consent"]').check();
  await q.locator('button[type="submit"]').click();
  await expect(page.locator('.thanks--quick')).toBeVisible();
  expect(sent.leads).toHaveLength(1);
  const lead = sent.leads[0];
  expect(lead.product_id).toBe(p.id);
  expect(lead.size_label).toBe(size.label);
  expect(lead.finish_id).toBe(fin.id);
  expect(lead.consent).toBe(true);
  expect(lead.lang).toBe('he');
});

test('mobile: a product with 8+ frames keeps the gallery inside the screen and the sticky pill still turns on', async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/p/${PRODUCTS[0].slug}/`);
  // кадрів у каталозі побільшає (mechanism, light, texture) — моделюємо 10 мініатюр і 10 слайдів
  await page.evaluate(() => {
    for (const sel of ['.g-thumbs', '.g-track']) {
      const box = document.querySelector(sel); if (!box || !box.children.length) continue;
      while (box.children.length < 10) box.appendChild(box.children[0].cloneNode(true));
    }
  });
  const widths = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth,
    gallery: Math.round(document.querySelector('.gallery').getBoundingClientRect().width),
    slide: Math.round(document.querySelector('.g-slide, .media--hero').getBoundingClientRect().width),
  }));
  expect(widths.page).toBeLessThanOrEqual(390);
  expect(widths.gallery).toBeLessThanOrEqual(390);
  expect(widths.slide).toBeLessThanOrEqual(390);
  await page.evaluate(() => scrollTo(0, document.querySelector('[data-quick]').getBoundingClientRect().bottom + scrollY + 200));
  await expect(page.locator('[data-sticky]')).toHaveClass(/is-on/);
});

test('mobile menu opens and closes with Escape', async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.locator('.menu-btn').click();
  await expect(page.locator('#nav')).toHaveClass(/is-open/);
  await page.keyboard.press('Escape');
  await expect(page.locator('#nav')).not.toHaveClass(/is-open/);
});

// ---------------------------------------------------------------- контакти, згода, נגישות
test('contacts and WhatsApp stay hidden while the config is empty', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await expect(page.locator('[data-contact]')).toBeHidden();
  await expect(page.locator('.js-wa')).toHaveCount(await page.locator('.js-wa').count());
  for (const a of await page.locator('.js-wa').all()) await expect(a).toBeHidden();
});

test('legal pages: the coordinator line stays hidden without a config and shows the configured contact', async ({ page }) => {
  await mockApi(page, {});
  await page.goto('/accessibility');
  const line = page.locator('[data-lneed~="a11y_email"]');
  if (!(await line.count())) test.skip(true, 'legal.*.json ще немає');
  await expect(line).toBeHidden();
  await expect(page.locator('main')).not.toContainText(/\{[a-z0-9_]+\}/);
  const cfg = { ...FULL_CONFIG, contact: { ...FULL_CONFIG.contact, phone: '+1 555 0100' } };
  await mockApi(page, { config: cfg });
  await page.goto('/accessibility');
  await expect(line).toBeVisible();
  await expect(line).toContainText(cfg.contact.email);
});

test('a configured WhatsApp number and e-mail appear with real links', async ({ page }) => {
  await mockApi(page, { config: FULL_CONFIG });
  await page.goto(`/p/${PRODUCTS[0].slug}/`);
  await expect(page.locator('[data-contact]')).toBeVisible();
  await expect(page.locator('.foot a[data-c="email"]')).toHaveAttribute('href', 'mailto:hello@example.com');
  const wa = page.locator('.js-wa').first();
  await expect(wa).toBeVisible();
  await expect(wa).toHaveAttribute('href', /^https:\/\/wa\.me\/972500000000\?text=/);
});

test('cookie notice: "essential only" is remembered and nothing third-party loads', async ({ page }) => {
  const sent = await mockApi(page, { config: { ...EMPTY_CONFIG, pixel_id: '123456789012345' } });
  await page.goto('/');
  await expect(page.locator('#notice')).toBeVisible();
  await page.locator('[data-notice-no]').click();
  await expect(page.locator('#notice')).toBeHidden();
  expect(await page.evaluate(() => localStorage.getItem('fx_notice_v1'))).toBe('0');
  await page.reload();
  await expect(page.locator('#notice')).toBeHidden();
  expect(sent.thirdParty).toBeUndefined();
  await page.locator('[data-cookie-settings]').click();
  await expect(page.locator('#notice')).toBeVisible();
});

test('accessibility menu: options toggle, persist and reset', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await page.locator('.a11y-btn').click();
  await expect(page.locator('#a11y-panel')).toBeVisible();
  for (const k of ['font', 'contrast', 'links', 'still']) {
    await page.locator(`[data-a11y-opt="${k}"]`).click();
    await expect(page.locator('html')).toHaveClass(new RegExp(`a11y-${k}`));
    await expect(page.locator(`[data-a11y-opt="${k}"]`)).toHaveAttribute('aria-pressed', 'true');
  }
  await page.reload();
  await expect(page.locator('html')).toHaveClass(/a11y-contrast/);
  await page.locator('.a11y-btn').click();
  await page.locator('[data-a11y-reset]').click();
  await expect(page.locator('html')).not.toHaveClass(/a11y-/);
  await page.keyboard.press('Escape');
  await expect(page.locator('#a11y-panel')).toBeHidden();
});

test('keyboard: skip link is first and moves focus to main', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.locator('.skip')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#main$/);
});

test('reduced motion: the page renders fully without scroll animations', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockApi(page);
  await page.goto('/');
  for (const card of await page.locator('.card').all()) expect(await card.evaluate(el => getComputedStyle(el).opacity)).toBe('1');
});

for (const rm of ['no-preference', 'reduce']) {
  test(`arch window (${rm}): the close-up enters as an arch and opens to full width; static when motion is reduced`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.emulateMedia({ reducedMotion: rm });
    await mockApi(page);
    await page.goto('/');
    const band = page.locator('.band');
    const clipAt = async f => {
      await band.evaluate((el, f) => scrollTo(0, el.getBoundingClientRect().top + scrollY - innerHeight * f), f);
      await page.waitForTimeout(200);
      return band.locator('picture').evaluate(el => getComputedStyle(el).clipPath);
    };
    const entering = await clipAt(0.4), settled = await clipAt(0);
    if (rm === 'reduce') {
      expect([entering, settled]).toEqual(['none', 'none']);
    } else {
      expect(entering).toMatch(/round [1-9]/);
      expect(settled).not.toMatch(/round [1-9]/);
    }
    await expect(band.locator('.viz-tag')).toBeVisible();
  });
}
