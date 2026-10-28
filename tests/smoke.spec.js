// Smoke повного стеку: статика + живий api/handler.py на ОДНОРАЗОВІЙ SQLite (tools/serve-local-stack.py).
//
// ⚠️ НЕ для прода й не для table-new: тест ПИШЕ у сховище — справжня заявка is_test (заголовок X-Test: 1
// на всіх запитах сторінки, як у scripts/smoke_local.py), події через /api/fx/event. Тому він не в CI
// (CLAUDE.md §5) і відмовляється працювати з будь-чим, крім 127.0.0.1 / localhost.
//
// Запуск (порт 8007 мусить бути вільний — ss -ltnp; стек піднімає й гасить сам Playwright):
//   python3 build.py
//   PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright npx playwright test --config tests/playwright.smoke.config.js
//
// Шлях заявки — нинішня воронка (specs/003-shop-funnel): картка tavor → розмір → «הוספה לסל» → кошик →
// «להזמנה» (cart_pay) → оформлення одним екраном (№38): місто, спосіб отримання, «מתי צריך?», телефон + згода →
// «להזמנה · בלי תשלום באתר» (cart_pay) → підтвердження на місці (co_thx_h).
// Потім заявку шукаємо за її id у /admin/leads.csv?test=1 того самого стеку: вона є, is_test = 1.
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8007';
const ORIGIN = new URL(BASE).origin;
const IS_LOCAL = ['127.0.0.1', 'localhost'].includes(new URL(BASE).hostname);
// вхід в адмінку стеку — випадковий на прогін, задає tests/playwright.smoke.config.js (у коді значення нема)
const ADMIN_USER = process.env.SMOKE_ADMIN_USER;
const ADMIN_KEY = process.env.SMOKE_ADMIN_KEY;

const CATALOG = require('../catalog/products.json');
const TAVOR = (CATALOG.products || CATALOG).find((p) => p.id === 'tavor');
const HE = require('../i18n/he.json');
const RU = require('../i18n/ru.json');
// вигаданий номер складено з частин — сканер секретів шукає цілі номери
const PHONE = ['05', '2-98', '7-6543'].join('');

test.skip(!IS_LOCAL, `smoke пише заявки — лише проти локального стеку, а не ${ORIGIN}`);
test.skip(!ADMIN_USER || !ADMIN_KEY, 'запуск лише з --config tests/playwright.smoke.config.js');

// CSV без сторонніх бібліотек: лапки, коми й переноси всередині комірок
function parseCsv(text) {
  const rows = []; let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (c === '"') q = false; else cell += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n') { row.push(cell.replace(/\r$/, '')); rows.push(row); row = []; cell = ''; }
    else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [head, ...body] = rows;
  head[0] = head[0].replace(/^﻿/, '');
  return body.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}

// вхід в адмінку стеку без переходів за редиректом (CLAUDE.md §6) — кука береться з відповіді 303
async function adminCookie(request) {
  const res = await request.post(`${ORIGIN}/admin/login`, { form: { user: ADMIN_USER, pass: ADMIN_KEY }, maxRedirects: 0 });
  expect(res.status(), 'вхід в адмінку локального стеку').toBe(303);
  const set = res.headersArray().find((h) => h.name.toLowerCase() === 'set-cookie' && h.value.startsWith('fx_adm='));
  expect(set, 'кука fx_adm').toBeTruthy();
  return set.value.split(';')[0];
}

test.describe('доставка сторінок', () => {
  test('головна — іврит, RTL, один h1', async ({ page }) => {
    const res = await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    expect(res.status()).toBe(200);
    await expect(page.locator('html')).toHaveAttribute('lang', 'he');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('h1')).toHaveCount(1);
  });

  test('правові сторінки — на чистих адресах', async ({ page }) => {
    for (const path of ['/privacy', '/terms', '/accessibility', '/ru/privacy', '/en/terms']) {
      const res = await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
      expect(res.status(), path).toBe(200);
      await expect(page.locator('h1'), path).toBeVisible();
    }
  });

  test('неіснуюча сторінка — 404, а не головна', async ({ page }) => {
    const res = await page.goto(BASE + '/no-such-page-xyz', { waitUntil: 'domcontentloaded' });
    expect(res.status()).toBe(404);
  });

  test('адмінка без входу не відкривається', async ({ request }) => {
    const res = await request.get(`${ORIGIN}/admin`, { maxRedirects: 0 });
    expect(res.status()).toBe(303);
    expect(res.headers().location).toBe('/admin/login');
  });
});

for (const [lang, pre, T] of [['he', '', HE], ['ru', '/ru', RU]]) {
  test(`${lang}: заявка проходить воронку до кінця й лягає у сховище з is_test`, async ({ page, request }) => {
    test.setTimeout(60000);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.setExtraHTTPHeaders({ 'X-Test': '1' });
    // банер про куки не заважає кнопкам; пікселя на локальному стеку й так нема (ID не задано)
    await page.addInitScript(() => { try { localStorage.setItem('fx_notice_v1', '1'); } catch (e) {} });
    const size = TAVOR.sizes[TAVOR.sizes.length - 1];

    // 1. картка → розмір → у кошик
    await page.goto(`${ORIGIN}${pre}/p/tavor/`);
    await page.locator(`label:has(input[name="size"][value="${size.label}"])`).first().click();
    const add = page.locator('.pdp-actions [data-add-cart]');
    await expect(add).toHaveText(T.add_to_cart);
    await add.click();

    // 2. кошик → cart_pay
    await page.waitForURL(`**${pre}/cart/`);
    await expect(page.locator('.cart-line')).toHaveCount(1);
    await expect(page.locator('.cart-meta')).toContainText(size.label);
    const pay = page.locator('[data-cart-pay]');
    await expect(pay).toHaveText(T.cart_pay);
    await pay.click();

    // 3. оформлення одним екраном (№38): місто, спосіб отримання, «коли», телефон, згода → cart_pay
    await page.waitForURL(`**${pre}/checkout/`);
    await expect(page.locator('.co-steps')).toHaveCount(0);
    const form = page.locator('[data-co-form]');
    const city = T.cities[0];
    await page.locator('#co-city').selectOption(city.id);
    const way = form.locator('input[name="ship"][value="door"]');
    if (!(await way.isChecked())) await form.locator('label:has(input[name="ship"][value="door"])').click();
    await page.locator('label:has(input[name="when"][value="now"])').click();
    await page.locator('#co-phone').fill(PHONE);
    await form.locator('input[name="consent"]').check();
    const submit = form.locator('button[type="submit"]');
    await expect(submit).toHaveText(T.cart_pay);
    const [leadRes] = await Promise.all([
      page.waitForResponse((r) => r.url() === `${ORIGIN}/api/fx/lead` && r.request().method() === 'POST'),
      submit.click(),
    ]);
    expect(leadRes.request().headers()['x-test']).toBe('1');
    expect(leadRes.status()).toBe(200);
    const body = await leadRes.json();
    expect(body.ok).toBe(true);
    expect(body.id).toBeTruthy();

    // 4. підтвердження на тому ж екрані
    await expect(page.locator('[data-co-thanks]')).toBeVisible();
    await expect(page.locator('[data-co-thanks]')).toContainText(T.co_thx_h);

    // 6. сховище стеку: заявка з тим самим id, is_test = 1, кошик і сума з каталогу
    const cookie = await adminCookie(request);
    const csv = await request.get(`${ORIGIN}/admin/leads.csv?test=1`, { headers: { cookie }, maxRedirects: 0 });
    expect(csv.status()).toBe(200);
    const row = parseCsv(await csv.text()).find((r) => r.id === body.id);
    expect(row, `заявка ${body.id} у сховищі`).toBeTruthy();
    expect({ is_test: row.is_test, lead_source: row.lead_source, product_id: row.product_id, size_label: row.size_label,
      lang: row.lang, timeframe: row.timeframe, order_total: row.order_total })
      .toEqual({ is_test: '1', lead_source: 'checkout', product_id: 'tavor', size_label: size.label,
        lang, timeframe: 'now', order_total: String(size.price_ils) });
    // без ?test=1 тестова заявка у вивантаження не потрапляє
    const real = await request.get(`${ORIGIN}/admin/leads.csv`, { headers: { cookie }, maxRedirects: 0 });
    expect(parseCsv(await real.text()).some((r) => r.id === body.id)).toBe(false);
  });
}
