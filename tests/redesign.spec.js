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
// < 900 px банер cookies з'являється після першої прокрутки або через 6 с (24.10) — у тестах будимо його подією scroll
const nudge = page => page.evaluate(() => dispatchEvent(new Event('scroll')));

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
  test(`card /p/${p.slug}/ opens with a price, sizes and "add to cart", no weeks, the launch-series caption under the price`, async ({ page }) => {
    await mockApi(page);
    const errors = watchErrors(page);
    await page.goto(`/p/${p.slug}/`);
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(page.locator('input[name="size"]')).toHaveCount(p.sizes.length);
    await expect(page.locator('.pdp-actions [data-add-cart]')).toHaveText('הוספה לסל');
    // хвиля 1 (22.10): ціна тверда — під нею «מחיר השקה לסדרה הראשונה», слова «משוער» біля ціни нема
    await expect(page.locator('.pdp-price')).toContainText('מחיר השקה לסדרה הראשונה');
    await expect(page.locator('.pdp-price')).not.toContainText('משוער');
    await expect(page.locator('.pdp-price')).not.toContainText('טרם אושר');
    await expect(page.locator('.pdp-buy')).not.toContainText('שבועות');
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

// кнопка נגישות на телефоні прибита до шапки — «סל» не може лягти під неї (так було на виході магазину)
test('header: cart button, accessibility button and menu do not overlap on phone and tablet widths', async ({ page }) => {
  await mockApi(page);
  for (const pre of ['', '/en']) {
    for (const w of [320, 360, 390, 768, 900]) {
      await page.setViewportSize({ width: w, height: 800 });
      await page.goto(pre + '/');
      const boxes = await page.evaluate(() => ['.top-cart', '.a11y-btn', '.menu-btn', '.logo'].map(s => {
        const r = document.querySelector(s).getBoundingClientRect();
        return { s, l: r.left, r: r.right, t: r.top, b: r.bottom };
      }));
      for (let i = 0; i < boxes.length; i++) {
        for (let j = i + 1; j < boxes.length; j++) {
          const a = boxes[i], b = boxes[j];
          const cross = a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b;
          expect(cross, `${pre || '/he'} ${w}px: ${a.s} × ${b.s}`).toBe(false);
        }
      }
    }
  }
});

test('catalog lists every product with a link to its card', async ({ page }) => {
  await mockApi(page);
  await page.goto('/catalog/');
  for (const p of PRODUCTS) await expect(page.locator(`a[href="/p/${p.slug}/"]`).first()).toBeVisible();
});

test('every page of both languages answers 200 with one h1', async ({ page }) => {
  test.setTimeout(120000);  // 20 сторінок на однопотоковому serve-preview
  await mockApi(page);
  for (const pre of ['', '/en']) {
    for (const rel of ['/', '/catalog/', '/cart/', '/checkout/', '/how/', '/about/', '/faq/', '/privacy', '/terms', '/accessibility']) {
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

test('morning / evening switch swaps the light layer, keeps the tag and hides the inactive picture from screen readers', async ({ page }) => {
  const p = PRODUCTS.find(x => (x.images || []).filter(i => i.view === 'light').length >= 2);
  const errors = watchErrors(page);
  await mockApi(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`/p/${p.slug}/`);
  await page.locator('[data-notice-no]').click();
  const fig = page.locator('[data-light-fig]');
  await expect(fig).toHaveAttribute('data-on', 'morning');
  await expect(fig.locator('.viz-tag')).toBeVisible();
  await expect(fig.locator('[data-l="evening"]')).toHaveAttribute('aria-hidden', 'true');
  await page.locator('[data-light="evening"]').click();
  await expect(fig).toHaveAttribute('data-on', 'evening');
  await expect(page.locator('[data-light="evening"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('[data-light="morning"]')).toHaveAttribute('aria-pressed', 'false');
  await expect(fig.locator('[data-l="morning"]')).toHaveAttribute('aria-hidden', 'true');
  await expect(fig.locator('[data-l="evening"]')).toHaveAttribute('aria-hidden', 'false');
  await expect(fig.locator('[data-l="evening"]')).toHaveCSS('opacity', '1');
  // без пари кадрів блоку немає
  const other = PRODUCTS.find(x => !(x.images || []).some(i => i.view === 'light'));
  await page.goto(`/p/${other.slug}/`);
  await expect(page.locator('[data-light-fig]')).toHaveCount(0);
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
// аудит 22.10, (б) 5: смуга — лише коли «הוספה לסל» пішла за верх екрана і банер cookies закритий
test('mobile: sticky CTA shows only after the add-to-cart button scrolls above the screen, never with the notice open', async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/p/${PRODUCTS[0].slug}/`);
  const sticky = page.locator('[data-sticky]');
  await nudge(page);
  await expect(page.locator('#notice')).toBeVisible();
  await expect(sticky).not.toHaveClass(/is-on/);               // перший екран — кадр, назва, ціна й розміри, смуги нема
  await page.evaluate(() => scrollTo(0, document.querySelector('.pdp-actions').getBoundingClientRect().bottom + scrollY + 200));
  await page.waitForTimeout(200);
  await expect(sticky).not.toHaveClass(/is-on/);               // кнопка вже вище, але банер відкритий — смуги нема
  await page.locator('[data-notice-no]').click();
  await expect(sticky).toHaveClass(/is-on/);                   // банер закрито — смуга є без прокрутки
  await page.evaluate(() => scrollTo(0, 0));
  await expect(sticky).not.toHaveClass(/is-on/);               // кнопка ще нижче екрана — смуги нема
  await page.evaluate(() => scrollTo(0, document.querySelector('.pdp-actions').getBoundingClientRect().top + scrollY - 300));
  await expect(sticky).not.toHaveClass(/is-on/);               // кнопка на екрані — дубль не потрібен
  await page.evaluate(() => scrollTo(0, document.querySelector('.pdp-actions').getBoundingClientRect().bottom + scrollY + 200));
  await expect(sticky).toHaveClass(/is-on/);
  await expect(sticky.locator('[data-add-cart]')).toHaveText('הוספה לסל');
  await expect(sticky.locator('.sticky-thumb')).toHaveCount(1);
  await expect(sticky.locator('.sticky-thumb')).toHaveAttribute('alt', /^הדמיה: \S/);
  await page.locator('#register').scrollIntoViewIfNeeded();
  await expect(sticky).not.toHaveClass(/is-on/);
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
  await nudge(page);
  await page.locator('[data-notice-no]').click();             // з відкритим банером смуги нема (аудит 22.10)
  await page.evaluate(() => scrollTo(0, document.querySelector('.pdp-actions').getBoundingClientRect().bottom + scrollY + 200));
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
  await nudge(page);
  await expect(page.locator('#notice')).toBeVisible();
  await page.locator('[data-notice-no]').click();
  await expect(page.locator('#notice')).toBeHidden();
  expect(await page.evaluate(() => localStorage.getItem('fx_notice_v1'))).toBe('0');
  await page.reload();
  await expect(page.locator('#notice')).toBeHidden();
  expect(sent.thirdParty).toBeUndefined();
  await page.locator('[data-cookie-settings]').click();
  await nudge(page);
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

// pagereveal-слухач із init-скрипта реєструється раніше за наш, тому знімок — у наступному кадрі
async function watchReveal(page) {
  await page.addInitScript(() => addEventListener('pagereveal', e => requestAnimationFrame(() => {
    const g = document.querySelector('.gallery .media');
    sessionStorage.setItem('rev', JSON.stringify({ vt: !!e.viewTransition, gal: g ? g.style.viewTransitionName : null,
      card: !!document.querySelector('.card-media[style*="p-img"]') }));
  })));
}

for (const rm of ['no-preference', 'reduce']) {
  test(`view transitions (${rm}): card photo flies into the gallery and back only when motion is allowed`, async ({ page }) => {
    const errors = watchErrors(page);
    await page.emulateMedia({ reducedMotion: rm });
    await mockApi(page);
    await watchReveal(page);
    await page.goto('/catalog/');
    await page.locator('.card-link').first().click();
    await page.waitForURL(/\/p\/[^/]+\/$/);
    // запис зі сторінки товару (там галерея є завжди) — до того в сховищі ще запис каталогу з gal: null
    const rev = async () => JSON.parse(await page.evaluate(() => sessionStorage.getItem('rev')));
    await expect.poll(async () => (await rev()).gal).not.toBe(null);
    const there = await rev();
    await page.goBack();
    await page.waitForURL(/\/catalog\/$/);
    await expect.poll(async () => (await rev()).gal).toBe(null);
    const back = await rev();
    const on = rm === 'no-preference';
    expect(there).toEqual({ vt: on, gal: on ? 'p-img' : '', card: false });
    expect(back).toEqual({ vt: on, gal: null, card: on });
    expect(errors).toEqual([]);
  });
}

test('gallery thumbs are filled edge to edge and morning/evening has no empty column on desktop', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockApi(page);
  await page.goto('/p/tavor/');
  for (const t of await page.locator('.g-thumb').all()) {
    const [box, img] = await t.evaluate(el => [el.clientHeight, el.querySelector('img').getBoundingClientRect().height]);
    expect(Math.abs(box - img)).toBeLessThanOrEqual(1);
  }
  const [wrap, fig] = await page.locator('section.light').evaluate(s => [s.querySelector('.wrap'), s.querySelector('.light-media')]
    .map(el => { const r = el.getBoundingClientRect(), c = getComputedStyle(el); return [r.left + parseFloat(c.paddingLeft), r.right - parseFloat(c.paddingRight)]; }));
  // RTL: кадр притиснутий до лівого краю контейнера, текст — праворуч
  expect(Math.abs(fig[0] - wrap[0])).toBeLessThanOrEqual(2);
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

for (const rm of ['no-preference', 'reduce']) {
  test(`oak rings (${rm}): line rings draw in on scroll from the pith outwards; drawn at once when motion is reduced`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.emulateMedia({ reducedMotion: rm });
    await mockApi(page);
    await page.goto('/');
    const rings = page.locator('.material .rings');
    // знак декоративний і легкий: прихований від читачів екрана, розмітка менша за 3 КБ
    expect(await rings.getAttribute('aria-hidden')).toBe('true');
    expect((await rings.evaluate(el => el.outerHTML)).length).toBeLessThan(3000);
    const offsets = async f => {
      await page.locator('.material').evaluate((el, f) => scrollTo(0, el.getBoundingClientRect().top + scrollY - innerHeight * (1 - f)), f);
      await page.waitForTimeout(150);
      return rings.evaluate(el => [...el.querySelectorAll('path')].map(p => +parseFloat(getComputedStyle(p).strokeDashoffset).toFixed(2)));
    };
    const early = await offsets(0.35), done = await offsets(1.2);
    expect(done.every(v => v === 0)).toBe(true);
    if (rm === 'reduce') expect(early.every(v => v === 0)).toBe(true);
    else {
      expect(early[early.length - 1]).toBeGreaterThan(0);
      expect(early[0]).toBeLessThan(early[early.length - 1]);
    }
  });
}

for (const rm of ['no-preference', 'reduce']) {
  test(`oak dusk (${rm}): the workshop darkens from light oak to dark oak; text shows only on a dark ground (AA)`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await page.emulateMedia({ reducedMotion: rm });
    await mockApi(page);
    await page.goto('/');
    const ws = page.locator('.workshop');
    // f — яка частка висоти вікна вже зайнята секцією знизу
    const at = async f => {
      await ws.evaluate((el, f) => scrollTo(0, el.getBoundingClientRect().top + scrollY - innerHeight * (1 - f)), f);
      await page.waitForTimeout(150);
      return ws.evaluate(el => {
        const lum = c => { const v = c.match(/[\d.]+/g).slice(0, 3).map(n => { n /= 255; return n <= .03928 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4; });
          return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]; };
        const bg = getComputedStyle(el).backgroundColor, p = el.querySelector('p:not(.eyebrow)');
        const [a, b] = [lum(bg), lum(getComputedStyle(p).color)].sort((x, y) => y - x);
        return { bg, op: +getComputedStyle(el.querySelector('.workshop-grid')).opacity, ratio: (a + .05) / (b + .05) };
      });
    };
    const steps = [];
    for (const f of [0.02, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8]) steps.push(await at(f));
    for (const s of steps) if (s.op > 0) expect(s.ratio).toBeGreaterThanOrEqual(4.5);
    const last = steps[steps.length - 1];
    expect(last).toMatchObject({ bg: 'rgb(31, 26, 21)', op: 1 });
    if (rm === 'reduce') expect(steps[0]).toMatchObject({ bg: 'rgb(31, 26, 21)', op: 1 });
    else expect(steps[0].bg).not.toBe('rgb(31, 26, 21)');
  });
}

// трафік із Meta приходить на телефон із банером cookies: дія має бути в першому екрані, не під банером
for (const [path, lang] of [['/', 'he'], ['/en/', 'en']]) {
  test(`first screen 390×844 (${lang}): the hero button sits above the cookie notice`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page);
    await page.goto(path);
    await nudge(page);
    await expect(page.locator('#notice')).toBeVisible();
    const top = await page.locator('#notice').evaluate(el => el.getBoundingClientRect().top);
    const btn = await page.locator('.hero .actions .btn').first().boundingBox();
    expect(btn.y).toBeGreaterThanOrEqual(0);
    expect(btn.y + btn.height).toBeLessThanOrEqual(top);
    // абзац лише візуально під кнопками: у DOM він, як і був, перед ними
    expect(await page.evaluate(() => !!(document.querySelector('.hero .lede').compareDocumentPosition(document.querySelector('.hero .actions')) & 4))).toBe(true);
  });
}

// аудит 22.10, (б) 5: перший екран картки з банером — без смуги; смуга з'являється лише після «הוספה לסל»
// і закритого банера — і тоді її ціна й кнопка в межах екрана
test('first screen 390×844 of a card: no sticky bar with the notice open; after the notice and the button, the bar is on screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto(`/p/${PRODUCTS[0].slug}/`);
  await nudge(page);
  await expect(page.locator('#notice')).toBeVisible();
  const sticky = page.locator('[data-sticky]');
  await page.waitForTimeout(300);
  await expect(sticky).not.toHaveClass(/is-on/);
  await page.locator('[data-notice-no]').click();
  await page.evaluate(() => scrollTo(0, document.querySelector('.pdp-actions').getBoundingClientRect().bottom + scrollY + 200));
  await expect(sticky).toHaveClass(/is-on/);
  // смуга виїжджає transform .3s: міряти після виїзду, а не посередині (CI 21.10: 863 > 844)
  await sticky.evaluate(el => Promise.all(el.getAnimations().map(a => a.finished)));
  const r = await page.evaluate(() => {
    const s = document.querySelector('[data-sticky]');
    const box = el => el.getBoundingClientRect();
    return { btn: box(s.querySelector('.btn')), price: box(s.querySelector('[data-price-mini]')), h: innerHeight };
  });
  for (const b of [r.btn, r.price]) { expect(b.top).toBeGreaterThanOrEqual(0); expect(b.bottom).toBeLessThanOrEqual(r.h); }
});

// 24.10: реклама веде на картку з телефона. Без прокрутки (банер ще не показано) — кадр, назва, гасло, ціна з підписом
// серії, умови, рядок довіри й ОБИДВІ кнопки «הוספה לסל» + «שאלה?»; «השאירו פרטים» — під ними, плитки розмірів — нижче.
// На 390 і банер (після першої прокрутки) не накриває «הוספה לסל». Смуги на першому екрані нема; 3D — чип на кадрі
for (const [w, h] of [[390, 844], [360, 780]]) {
  for (const [prefix, lang] of [['', 'he'], ['/en', 'en'], ['/ru', 'ru']]) {
    for (const slug of ['tavor', 'sahar', 'tal']) {
      test(`first screen ${w}×${h} of ${prefix}/p/${slug}/ (${lang}): photo, name, price, trust row and both buttons without scrolling`, async ({ page }) => {
        await page.setViewportSize({ width: w, height: h });
        await mockApi(page);
        await page.goto(`${prefix}/p/${slug}/`);
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        await expect(page.locator('#notice')).toBeHidden();
        await expect(page.locator('[data-sticky]')).not.toHaveClass(/is-on/);
        const measure = () => page.evaluate(() => {
          const box = s => document.querySelector(s).getBoundingClientRect();
          const n = document.getElementById('notice');
          return { y: scrollY, vh: innerHeight, notice: n.hidden ? innerHeight : box('#notice').top,
            img: box('.g-track'), chip: box('.g-3d'), h1: box('.pdp-h1'), tag: box('.pdp-tag'), price: box('.pdp-price'),
            incl: box('.pdp-price .price-incl'), trust: box('.pdp-trust'), cart: box('.pdp-pair [data-add-cart]'),
            ask: box('.pdp-pair [data-ask]'), lead: box('.pdp-ask'), tile: box('label.pill:has(input[name="size"])'),
            inclLH: parseFloat(getComputedStyle(document.querySelector('.pdp-price .price-incl')).lineHeight) };
        });
        const r = await measure();
        expect(r.y).toBe(0);
        for (const b of [r.img, r.h1, r.tag, r.price, r.incl, r.trust, r.cart, r.ask]) {
          expect(b.top).toBeGreaterThan(0); expect(b.bottom).toBeLessThanOrEqual(r.vh);
        }
        expect(r.incl.height).toBeLessThan(r.inclLH * 1.5);            // підпис серії — один рядок
        // порядок на екрані: ціна → довіра → кошик → питання → «השאירו פרטים» → плитки розмірів
        expect(r.trust.top).toBeGreaterThanOrEqual(r.price.bottom - 1);
        expect(r.cart.top).toBeGreaterThan(r.trust.bottom);
        expect(r.ask.top).toBeGreaterThan(r.cart.bottom - 1);
        expect(r.lead.top).toBeGreaterThan(r.ask.bottom);
        expect(r.tile.top).toBeGreaterThan(r.lead.bottom);
        expect(r.chip.top).toBeGreaterThanOrEqual(r.img.top);         // чип 3D лежить на кадрі
        expect(r.chip.bottom).toBeLessThanOrEqual(r.img.bottom);
        expect(r.chip.width).toBeLessThan(r.img.width / 2);
        if (w === 390) {
          await nudge(page);
          await expect(page.locator('#notice')).toBeVisible();
          const n = await measure();
          expect(n.cart.bottom).toBeLessThanOrEqual(n.notice);
        }
      });
    }
  }
}

// 24.10: на телефоні банер не при завантаженні, а після першої прокрутки або через 6 с; на десктопі — як був
test('cookie notice on a phone: hidden at load, shows on the first scroll; without a scroll — after 6 s; desktop — at once', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/p/tavor/');
  await page.waitForTimeout(2000);
  await expect(page.locator('#notice')).toBeHidden();
  await page.mouse.wheel(0, 300);
  await expect(page.locator('#notice')).toBeVisible();
  await page.goto('/catalog/');
  await page.waitForTimeout(4000);
  await expect(page.locator('#notice')).toBeHidden();
  await expect(page.locator('#notice')).toBeVisible({ timeout: 4000 });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/p/tavor/');
  await expect(page.locator('#notice')).toBeVisible({ timeout: 2500 });
});

// 24.10: каталог на телефоні — дві колонки, фото 1:1, під ним назва й ціна; після заголовка видно ≥ 4 картки з цінами
for (const [w, h] of [[390, 844], [360, 780]]) {
  for (const prefix of ['', '/ru']) {
    test(`catalog ${w}×${h} ${prefix || 'he'}: two columns, square photos, at least four prices on the first screen`, async ({ page }) => {
      await page.setViewportSize({ width: w, height: h });
      await mockApi(page);
      await page.goto(`${prefix}/catalog/`);
      await page.evaluate(() => document.fonts.ready);
      const r = await page.evaluate(() => {
        const cards = [...document.querySelectorAll('.cards .card')].map(c => {
          const m = c.querySelector('.media').getBoundingClientRect(), p = c.querySelector('.card-price').getBoundingClientRect();
          const n = c.querySelector('.card-name').getBoundingClientRect();
          return { top: Math.round(m.top), left: Math.round(m.left), w: m.width, h: m.height, name: n, price: p };
        });
        return { cards, vh: innerHeight, over: document.documentElement.scrollWidth - innerWidth };
      });
      expect(r.over).toBeLessThanOrEqual(0);
      expect(r.cards[0].top).toBe(r.cards[1].top);                     // дві в ряд
      expect(r.cards[0].left).not.toBe(r.cards[1].left);
      for (const c of r.cards) {
        expect(Math.abs(c.w - c.h)).toBeLessThanOrEqual(1);              // 1:1
        expect(c.name.top).toBeGreaterThanOrEqual(c.top + c.h - 1);       // назва й ціна — під фото
        expect(c.price.top).toBeGreaterThanOrEqual(c.name.bottom - 1);
      }
      expect(r.cards.filter(c => c.price.bottom <= r.vh).length).toBeGreaterThanOrEqual(4);
    });
  }
}

test('catalog on desktop keeps three columns and 4:5 photos', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await page.goto('/catalog/');
  const r = await page.evaluate(() => [...document.querySelectorAll('.cards .card .media')].slice(0, 3).map(m => {
    const b = m.getBoundingClientRect(); return [Math.round(b.top), b.width / b.height]; }));
  expect(new Set(r.map(x => x[0])).size).toBe(1);
  for (const [, ratio] of r) expect(Math.abs(ratio - 0.8)).toBeLessThan(0.02);
});

test('cookie notice on 390: two lines of Hebrew text with the policy link, and both choices look the same', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/');
  const n = page.locator('#notice');
  await nudge(page);
  await expect(n).toBeVisible();
  await expect(n.locator('p a[href$="/privacy"]')).toBeVisible();
  const r = await n.evaluate(el => {
    const p = el.querySelector('p'), lines = Math.round(p.getBoundingClientRect().height / parseFloat(getComputedStyle(p).lineHeight));
    const look = b => { const s = getComputedStyle(b); return [s.backgroundColor, s.color, s.borderColor, s.fontWeight, Math.round(b.getBoundingClientRect().width)].join('|'); };
    return { lines, ok: look(el.querySelector('[data-notice-ok]')), no: look(el.querySelector('[data-notice-no]')) };
  });
  expect(r.lines).toBeLessThanOrEqual(2);
  expect(r.ok).toBe(r.no);                                     // без темних патернів: «אישור» не виділено проти «רק הכרחיות»
});

// 22.10: банер — не третина екрана: ≤ 80 px, дві кнопки в один ряд, обидві ≥ 24 px (WCAG 2.5.8)
for (const path of ['/', '/en/', '/p/tavor/', '/en/p/tavor/']) {
  test(`cookie notice on 390 at ${path}: at most 80 px high, the two buttons side by side`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page);
    await page.goto(path);
    const n = page.locator('#notice');
    await nudge(page);
    await expect(n).toBeVisible();
    const r = await n.evaluate(el => ({ h: el.getBoundingClientRect().height,
      ok: el.querySelector('[data-notice-ok]').getBoundingClientRect(), no: el.querySelector('[data-notice-no]').getBoundingClientRect() }));
    expect(r.h).toBeLessThanOrEqual(80);
    expect(Math.abs(r.ok.top - r.no.top)).toBeLessThan(1);
    for (const b of [r.ok, r.no]) expect(b.height).toBeGreaterThanOrEqual(24);
  });
}

for (const [w, h] of [[390, 844], [1440, 900]]) {
  test(`chapters ${w}px: the card's chapter bar sticks under the header, every link has a target, aria-current follows the scroll`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h });
    await mockApi(page);
    const errors = watchErrors(page);
    await page.goto(`/p/${PRODUCTS[0].slug}/`);
    const nav = page.locator('nav.chapters');
    await expect(nav).toHaveAttribute('aria-label', /\S/);
    const ids = await nav.locator('a').evaluateAll(as => as.map(a => a.hash.slice(1)));
    expect(ids.length).toBeGreaterThanOrEqual(3);
    for (const id of ids) await expect(page.locator(`#${id}`)).toHaveCount(1);
    for (const id of [ids[ids.length - 1], ids[1], ids[0]]) {
      await page.evaluate(i => document.getElementById(i).scrollIntoView({ behavior: 'instant' }), id);
      await expect(nav.locator('[aria-current="location"]')).toHaveAttribute('href', `#${id}`);
      await expect(nav.locator('[aria-current]')).toHaveCount(1);
      const r = await page.evaluate(i => ({ nav: document.querySelector('nav.chapters').getBoundingClientRect(), top: document.querySelector('.top').getBoundingClientRect(),
        sec: document.getElementById(i).getBoundingClientRect().top, pill: document.querySelector('nav.chapters [aria-current]').getBoundingClientRect() }), id);
      expect(Math.abs(r.nav.top - r.top.bottom)).toBeLessThan(1);          // рівно під шапкою, без щілини й без накладки
      expect(r.sec).toBeGreaterThanOrEqual(r.nav.bottom - 1);              // якір не ховається під смугою
      // активна пігулка доїжджає в поле зору плавно — чекаємо, а не міряємо миттєво
      await expect.poll(() => page.evaluate(() => { const b = document.querySelector('nav.chapters [aria-current]').getBoundingClientRect(); return b.left >= 0 && b.right <= innerWidth; })).toBe(true);
      expect(r.pill.height).toBeGreaterThanOrEqual(44);                   // ціль дотику
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect(nav.locator('[aria-current]')).toHaveCount(0);           // над першою главою — жодна не поточна
    expect(await noOverflow(page)).toBe(0);
    expect(errors).toEqual([]);
  });
}

test('hero first: every card opens its gallery on the whole piece; the oak close-up of the console and the TV unit comes second', async ({ page }) => {
  // 21.10: крупний план першим кадром скасовано — з реклами на 390 видно лише кут дошки, не виріб;
  // перший — жилий кадр home (виріб цілком у квартирі, власник 21.10), за ним крупний план дуба.
  // TAL — виняток (дирижер 21.10): першим колишній hero у вітальні, він живіший; home — другим.
  await mockApi(page);
  for (const p of PRODUCTS) {
    await page.goto(`/p/${p.slug}/`);
    const srcs = await page.locator('.gallery .g-slide img').evaluateAll(is => is.map(i => i.getAttribute('src')));
    const first = p.slug === 'tal' ? 'hero' : 'home';
    expect(p.images[0].view, p.slug).toBe('hero');
    expect(srcs[0], p.slug).toContain(`/products/${p.slug}/${first}-`);
    if (p.images.some(i => i.view === 'texture')) expect(srcs[1], p.slug).toContain(`/products/${p.slug}/texture-`);
  }
});

// ---------------------------------------------------------------- 3D: клік → живе полотно (21.10: кнопка мовчала)
// Ловить саме ту поломку: відносний шлях (404), неопублікований файл, модуль не того вигляду — у кожному
// випадку полотна немає, а в мережі 404 або в консолі помилка. Сторонніх запитів (CDN) теж немає.
for (const [prefix, lang] of [['', 'he'], ['/en', 'en']]) {
  test(`3D view on ${prefix}/p/tavor/ (${lang}): a canvas with a size, no 404, no console errors, nothing third-party`, async ({ page }) => {
    const sent = await mockApi(page);
    const errors = watchErrors(page);
    await page.goto(`${prefix}/p/tavor/`);
    const btn = page.locator('.js-3d');
    await expect(btn).toHaveCount(1);
    await btn.click();
    const box = page.locator('.viewer3d');
    await expect(box).toBeVisible();
    const canvas = box.locator('canvas');
    await expect(canvas).toHaveCount(1, { timeout: 15000 });
    const r = await canvas.evaluate(c => ({ w: c.width, h: c.height, cw: c.clientWidth, ch: c.clientHeight }));
    expect(r.w * r.h * r.cw * r.ch).toBeGreaterThan(0);
    await expect(box.locator('.v3d-msg')).toBeHidden();
    await expect(box.locator('.viz-tag')).toHaveText(lang === 'he' ? 'הדמיה' : 'Visualisation');
    // розкласти стіл і закрити: полотно прибрано, кнопка повернулась
    await box.locator('.v3d-st[data-state="open"]').click();
    await expect(box.locator('.v3d-st[data-state="open"]')).toHaveAttribute('aria-pressed', 'true');
    await box.locator('.v3d-close').click();
    await expect(box).toBeHidden();
    await expect(canvas).toHaveCount(0);
    await expect(btn).toBeVisible();
    expect(errors).toEqual([]);
    expect(sent.thirdParty).toBeUndefined();
  });
}

test('3D view without WebGL: a short text inside the viewer, not a silent button', async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => { HTMLCanvasElement.prototype.getContext = () => null; });
  await page.goto('/p/tal/');
  await page.locator('.js-3d').click();
  const msg = page.locator('.viewer3d .v3d-msg');
  await expect(msg).toBeVisible();
  await expect(msg).toContainText('תלת־ממד');
  await expect(page.locator('.viewer3d canvas')).toHaveCount(0);
});
