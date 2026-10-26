// Магазин (specs/003-shop-funnel): картка → кошик → оформлення → екран оплати без поля карти → заявка.
// Без порту й без мережі: dist/ через page.route (tests/dist_route.js), /api/fx/* підмінено тут; підробний fbevents.js
// пише кожен виклик fbq у sessionStorage, тож Pixel-події видно й після переходу на наступну сторінку.
//   python3 build.py && npx playwright test --config playwright.tracking.config.js
const { test, expect } = require('@playwright/test');
const { ORIGIN, serveDist, built } = require('./dist_route');

const PIXEL = '123456789012345';
const CATALOG = require('../catalog/products.json');
const TAVOR = (CATALOG.products || CATALOG).find((p) => p.id === 'tavor');
const HE = require('../i18n/he.json');
const EN = require('../i18n/en.json');
const RU = require('../i18n/ru.json');
const CONTENT = require('../content.json');
// вигаданий номер складено з частин — сканер секретів шукає цілі номери
const PHONE = ['05', '2-98', '7-6543'].join('');
const DIGITS = PHONE.replace(/-/g, '');
const PII = ['Zzqx', DIGITS, DIGITS.slice(1), PHONE, DIGITS.slice(3)];

const FAKE_FBEVENTS = `(function(){var f=window.fbq;
f.callMethod=function(){var a=JSON.parse(JSON.stringify(Array.prototype.slice.call(arguments)));
var l=JSON.parse(sessionStorage.getItem('__fb')||'[]');l.push(a);sessionStorage.setItem('__fb',JSON.stringify(l))};
var q=f.queue||[];f.queue=[];q.forEach(function(a){f.callMethod.apply(f,Array.prototype.slice.call(a))});})();`;

test.skip(!built(), 'dist/ не зібрано: python3 build.py');

async function setup(page, { lead = { ok: true, id: 'lead-test-1' } } = {}) {
  const net = { events: [], leads: [], outside: [] };
  await serveDist(page);
  await page.route('https://connect.facebook.net/**', (route) =>
    route.fulfill({ status: 200, contentType: 'text/javascript', body: FAKE_FBEVENTS }));
  await page.route(`${ORIGIN}/api/fx/**`, (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    if (p === '/api/fx/config') return route.fulfill({ json: { pixel_id: PIXEL, clarity_id: null, contact: {} } });
    if (p === '/api/fx/event') { try { net.events.push(req.postDataJSON()); } catch (e) {} return route.fulfill({ json: { ok: true } }); }
    if (p === '/api/fx/lead') { net.leads.push(req.postDataJSON()); return route.fulfill({ json: lead }); }
    return route.fulfill({ status: 404, json: { ok: false } });
  });
  page.on('request', (req) => {
    const u = new URL(req.url());
    if (u.origin !== ORIGIN && u.hostname !== 'connect.facebook.net') net.outside.push(u.hostname);
  });
  await page.addInitScript(() => { try { localStorage.setItem('fx_notice_v1', '1'); } catch (e) {} });
  // page.route не бачить запитів, що пішли при pagehide (маяк). У тесті тіло маяка ще й лягає в localStorage
  // (__beacons) синхронно, і наступна сторінка його читає — так видно події, надіслані при переході.
  await page.addInitScript(() => {
    const B = window.Blob;
    window.Blob = function (parts, opts) {
      const b = new B(parts, opts);
      if (opts && opts.type === 'application/json') b.__text = parts.join('');
      return b;
    };
    window.Blob.prototype = B.prototype;
    const send = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = (url, data) => {
      try {
        if (String(url).includes('/api/fx/event') && data && data.__text) {
          const l = JSON.parse(localStorage.getItem('__beacons') || '[]'); l.push(JSON.parse(data.__text));
          localStorage.setItem('__beacons', JSON.stringify(l));
        }
      } catch (e) {}
      return send(url, data);
    };
  });
  return net;
}

const pixel = (page) => page.evaluate(() => JSON.parse(sessionStorage.getItem('__fb') || '[]'));
const fbNamed = async (page, name) => (await pixel(page)).filter((c) => (c[0] === 'track' || c[0] === 'trackCustom') && c[1] === name);
const firstParty = (net, name) => net.events.flatMap((b) => b.events || []).filter((e) => !name || e.name === name);
// маяки, перехоплені на попередніх сторінках, — у net.events без дублів (той самий event_id)
async function pullBeacons(page, net) {
  const seen = new Set(firstParty(net).map((e) => e.props && e.props.event_id));
  for (const b of await page.evaluate(() => JSON.parse(localStorage.getItem('__beacons') || '[]'))) {
    const fresh = (b.events || []).filter((e) => !seen.has(e.props && e.props.event_id));
    fresh.forEach((e) => seen.add(e.props && e.props.event_id));
    if (fresh.length) net.events.push({ ...b, events: fresh });
  }
}
const noOverflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

async function waitFb(page, name, n = 1) {
  await expect.poll(async () => (await fbNamed(page, name)).length, { timeout: 8000 }).toBeGreaterThanOrEqual(n);
  return fbNamed(page, name);
}

for (const [lang, pre, T] of [['he', '', HE], ['en', '/en', EN], ['ru', '/ru', RU]]) {
  for (const [w, h] of [[390, 844], [1440, 900]]) {
    test(`${lang} ${w}px: картка → кошик → оформлення → закрита оплата → заявка, події на кожному кроці`, async ({ page }) => {
      test.setTimeout(90000);
      await page.setViewportSize({ width: w, height: h });
      const net = await setup(page);
      const size = TAVOR.sizes.find((s) => s.label === '180×90');
      const fin = 'smoked';

      // 1. картка: ціна на виду, під нею ціна першої серії (хвиля 1, 22.10) — без «משוער / estimate» і «טרם אושר»;
      //    строк — «на підтвердженні замовлення»
      await page.goto(`${ORIGIN}${pre}/p/tavor/`);
      await waitFb(page, 'ViewContent');
      await expect(page.locator('.pdp-price')).toBeVisible();
      await expect(page.locator('.pdp-price .price-incl')).toHaveText(T.vat_incl + ' · ' + T.series_price_n.replace('{{SERIES_SIZE}}', CONTENT.SERIES_SIZE));   // №28: «כולל מע״מ ·» поруч
      await expect(page.locator('.pdp-price')).not.toContainText(lang === 'he' ? 'משוער' : /estimate|ориентировоч/i);
      await expect(page.locator('.pdp-price')).not.toContainText(lang === 'he' ? 'טרם אושר' : /not yet confirmed|не подтвержден/i);
      await expect(page.locator('.pdp-buy')).not.toContainText(lang === 'he' ? 'שבועות' : /weeks|(^|[^а-яё])недел/i);
      await expect(page.locator('.pdp-lead')).toHaveText(T.lead_exact);
      await page.locator(`label:has(input[name="size"][value="${size.label}"])`).first().click();
      await page.locator(`label:has(input[name="finish"][value="${fin}"])`).first().click();
      const [ss] = await waitFb(page, 'select_size');
      expect(ss[0]).toBe('trackCustom');
      expect(ss[2]).toMatchObject({ content_ids: ['tavor'], size: size.label });
      const [sf] = await waitFb(page, 'select_finish');
      expect(sf[2]).toMatchObject({ content_ids: ['tavor'], size: size.label, finish: fin });
      expect(await fbNamed(page, 'CustomizeProduct')).toEqual([]);
      expect(await noOverflow(page)).toBeLessThanOrEqual(0);
      const add = page.locator('.pdp-actions [data-add-cart]');
      await expect(add).toHaveText(T.add_to_cart);
      await add.click();

      // 2. кошик: позиція, бейдж, переживає перезавантаження, кількість, разом
      await page.waitForURL(`**${pre}/cart/`);
      // маяк до переходу (go → alumaFlush), а не з pagehide: AddToCart доходить у перехоплений POST /api/fx/event
      await expect.poll(() => firstParty(net, 'AddToCart').length, { timeout: 5000 }).toBe(1);
      const [atc] = await waitFb(page, 'AddToCart');
      expect(atc[2]).toMatchObject({ content_ids: ['tavor'], size: size.label, finish: fin, value: size.price_ils, currency: 'ILS', cta: 'pdp' });
      await expect(page.locator('.cart-line')).toHaveCount(1);
      await expect(page.locator('[data-cart-n]').first()).toHaveText('1');
      await page.reload();
      await expect(page.locator('.cart-line')).toHaveCount(1);
      await expect(page.locator('.cart-meta')).toContainText(size.label);
      await page.locator('button[data-act="more"]').click();
      await expect(page.locator('.qty-n')).toHaveText('2');
      // ru: «8 980 ₪» з нерозривними пробілами
      const money = (v) => { const n = v.toLocaleString('en-US'); return lang === 'ru' ? n.replace(/,/g, '\u00a0') + '\u00a0₪' : '₪' + n; };
      // хвиля 1: разом = товар + спосіб отримання; за замовчуванням до дверей (DELIVERY_ILS), самовивіз — PICKUP_ILS
      const door = Number(CONTENT.DELIVERY_ILS), pickup = Number(CONTENT.PICKUP_ILS);
      const sum = money(2 * size.price_ils + door);
      await expect(page.locator('[data-cart-total]')).toHaveText(sum);
      await expect(page.locator('[data-cart-sum]')).toContainText(T.price_incl);
      expect(await noOverflow(page)).toBeLessThanOrEqual(0);
      await waitFb(page, 'view_cart');
      const pay = page.locator('[data-cart-pay]');
      await expect(pay).toHaveText(T.cart_pay);
      await pay.click();

      // 3. оформлення: місто зі списку, «коли», ім'я й телефон необов'язкові
      await page.waitForURL(`**${pre}/checkout/`);
      await expect.poll(() => firstParty(net, 'InitiateCheckout').length, { timeout: 5000 }).toBe(1);
      const [ic] = await waitFb(page, 'InitiateCheckout');
      expect(ic[0]).toBe('track');
      expect(ic[2]).toMatchObject({ content_ids: ['tavor'], value: 2 * size.price_ils, currency: 'ILS', num_items: 2 });
      expect(ic[3].eventID).toMatch(/^ic\./);
      await expect(page.locator('[data-co-total]')).toHaveText(sum);
      // крок «משלוח»: самовивіз — разом перераховано без доставки
      await page.locator('[data-co-ship] label:has(input[name="ship"][value="pickup"])').click();
      await expect(page.locator('[data-co-total]')).toHaveText(money(2 * size.price_ils + pickup));
      await page.locator('[data-co-ship] button[type="submit"]').click();
      await expect(page.locator('#co-e-city')).toHaveText(T.js.e_city);
      await expect(page.locator('#co-e-when')).toHaveText(T.js.e_when);
      await expect(page.locator('[data-co-pay]')).toBeHidden();
      const city = T.cities[0];
      await page.locator('#co-city').selectOption(city.id);
      await page.locator('label:has(input[name="when"][value="now"])').click();
      await page.locator('[data-co-ship] button[type="submit"]').click();

      // 4. екран оплати: чесна закрита двері, поля карти нема
      await expect(page.locator('[data-co-pay]')).toBeVisible();
      await expect(page.locator('.pay-closed')).toContainText(T.pay_closed_h);
      // чесно: заголовок — підтвердження до оплати, кнопка — «לאישור ההזמנה», ім'я необов'язкове
      await expect(page.locator('[data-co-pay] h2')).toHaveText(T.pay_h);
      await expect(page.locator('.pay-closed')).toContainText(T.pay_closed_p);
      await expect(page.locator('[data-co-keep] button[type="submit"]')).toHaveText(T.pay_submit);
      // аудит 22.10 (б) №1: оплати на сайті нема — у кроках і кнопках воронки ні слова «оплата»
      const payWord = { he: 'תשלום', ru: 'оплат', en: 'pay' }[lang];
      for (const t of [await page.locator('.co-steps').innerText(), T.cart_pay, T.co_next, T.pay_submit]) {
        expect(t.toLowerCase()).not.toContain(payWord);
      }
      await expect(page.locator('#pay-name')).toBeVisible();
      expect(await page.locator('#pay-name').evaluate((i) => i.required)).toBe(false);
      expect(await page.locator('#pay-phone').evaluate((i) => i.required)).toBe(true);
      expect(page.url()).toMatch(/#pay$/);
      await expect(page.locator('input[autocomplete^="cc-"], input[name*="card" i], input[name*="cvv" i], input[name*="cvc" i]')).toHaveCount(0);
      expect(await noOverflow(page)).toBeLessThanOrEqual(0);
      const [cd] = await waitFb(page, 'checkout_details');
      expect(cd[2]).toMatchObject({ city: city.id, when: 'now', has_name: false, has_phone: false });
      await waitFb(page, 'reach_payment');
      const keep = page.locator('[data-co-keep]');
      await keep.locator('button[type="submit"]').click();
      await expect(page.locator('#pay-e-phone')).toBeVisible();
      await expect(page.locator('#pay-e-consent')).toBeVisible();
      expect(net.leads).toEqual([]);
      await page.locator('#pay-phone').fill(PHONE);
      await keep.locator('input[name="consent"]').check();
      await keep.locator('button[type="submit"]').click();
      await expect(page.locator('[data-co-thanks]')).toBeVisible();
      await expect(page.locator('[data-co-thanks]')).toContainText(T.pay_thx_h);
      const thx = page.locator('[data-co-thanks] .thanks-steps li');
      await expect(thx).toHaveText([T.pay_thx_1, T.pay_thx_2, T.pay_thx_3]);
      await expect(page.locator('[data-co-thanks]')).toContainText(T.cart_continue);

      // заявка: кошик і сума — з каталогу, джерело checkout
      expect(net.leads).toHaveLength(1);
      const lead = net.leads[0];
      expect(lead).toMatchObject({ lead_source: 'checkout', product_id: 'tavor', size_label: size.label, finish_id: fin,
        timeframe: 'now', city: city.name, order_total: 2 * size.price_ils, consent: true, ads_consent: true, lang, name: '',
        delivery: 'pickup' });
      expect(lead.cart).toBe(`tavor:${size.label}:${fin}:${TAVOR.bases[0].id}:2`);
      const [ld] = await waitFb(page, 'Lead');
      expect(ld[3].eventID).toBe(lead.event_id);
      expect(ld[2]).toMatchObject({ value: 2 * size.price_ils, currency: 'ILS' });

      // перша сторона: усі кроки є; scroll і leave — лише в нашій базі; ніде жодних особистих даних
      await expect.poll(() => firstParty(net, 'Lead').length, { timeout: 8000 }).toBe(1);
      await page.goto(`${ORIGIN}${pre}/`);
      await page.waitForLoadState('load');
      await pullBeacons(page, net);
      expect(firstParty(net, 'leave').map((e) => e.props.step)).toContain('payment');
      const names = new Set(firstParty(net).map((e) => e.name));
      for (const n of ['ViewContent', 'select_size', 'select_finish', 'AddToCart', 'view_cart', 'InitiateCheckout',
        'checkout_details', 'reach_payment', 'Lead', 'leave']) expect(names.has(n), n).toBe(true);
      expect(firstParty(net, 'InitiateCheckout')[0].props.event_id).toBe(ic[3].eventID);
      expect(firstParty(net, 'InitiateCheckout')[0].props.ads_consent).toBe(true);
      const steps = firstParty(net, 'leave').map((e) => e.props.step);
      for (const s of ['pdp', 'cart', 'payment']) expect(steps, s).toContain(s);
      expect(await fbNamed(page, 'leave')).toEqual([]);
      expect(await fbNamed(page, 'scroll')).toEqual([]);
      const blob = JSON.stringify(net.events) + JSON.stringify(await pixel(page));
      for (const s of PII) expect(blob.includes(s), s).toBe(false);
      expect(net.outside).toEqual([]);
    });
  }
}

test('порожній кошик: оформлення не показує форму, а веде в каталог', async ({ page }) => {
  await setup(page);
  await page.goto(`${ORIGIN}/checkout/`);
  await expect(page.locator('[data-co-empty]')).toBeVisible();
  await expect(page.locator('[data-co-ship]')).toBeHidden();
  await page.goto(`${ORIGIN}/en/cart/`);
  await expect(page.locator('[data-cart-empty]')).toBeVisible();
  await expect(page.locator('[data-cart-sum]')).toBeHidden();
});

// 23.10: м'який крок поруч із кошиком — «שאלה? נחזור אליכם» веде до форми з цим столом; cta_ask — лише наша аналітика
for (const [prefix, t] of [['', HE], ['/en', EN], ['/ru', RU]]) {
  test(`«${t.ask_cta}» на картці ${prefix}/p/tavor/: форма з TAVOR, фокус на імені, cta_ask без Meta`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const net = await setup(page);
    await page.goto(`${ORIGIN}${prefix}/p/tavor/`);
    const ask = page.locator('.pdp-actions [data-ask]');
    await expect(ask).toHaveText(t.ask_cta);
    await expect(page.locator('.pdp-ask-hint')).toHaveText(t.ask_hint);
    // десктоп: обидві кнопки в один ряд
    const [cart, a] = await Promise.all([page.locator('.pdp-actions [data-add-cart]').boundingBox(), ask.boundingBox()]);
    expect(Math.abs(cart.y - a.y)).toBeLessThan(2);
    await page.evaluate(() => { document.querySelector('#f-product').value = ''; });
    await ask.click();
    await expect(page.locator('#register')).toBeInViewport();
    await expect(page.locator('#f-name')).toBeFocused();
    await expect(page.locator('#f-product')).toHaveValue('tavor');
    await expect.poll(() => firstParty(net, 'cta_ask').length, { timeout: 8000 }).toBe(1);
    const [ev] = firstParty(net, 'cta_ask');
    expect(ev.props).toMatchObject({ content_ids: ['tavor'], content_type: 'product', cta: 'pdp' });
    expect(await fbNamed(page, 'cta_ask')).toHaveLength(0);
  });
}

test('телефон 390: «שאלה?» у липкій панелі — висота та сама, клік веде до форми; основні кнопки — стовпчиком', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const net = await setup(page);
  await page.goto(`${ORIGIN}/p/tavor/`);
  const [cart, a] = await Promise.all([page.locator('.pdp-actions [data-add-cart]').boundingBox(),
    page.locator('.pdp-actions [data-ask]').boundingBox()]);
  expect(a.y).toBeGreaterThan(cart.y + cart.height - 1);
  await page.evaluate(() => scrollTo(0, document.querySelector('#spec').getBoundingClientRect().top + scrollY));
  const sticky = page.locator('[data-sticky]');
  await expect(sticky).toHaveClass(/is-on/);
  const s = sticky.locator('[data-ask]');
  await expect(s).toHaveText(HE.ask_cta_short);
  const [bar, btn, atc] = await Promise.all([sticky.boundingBox(), s.boundingBox(), sticky.locator('[data-add-cart]').boundingBox()]);
  expect(btn.height).toBeLessThanOrEqual(44.5);
  expect(bar.height).toBeLessThanOrEqual(58);
  expect(Math.abs(btn.y - atc.y)).toBeLessThan(2);
  expect(await noOverflow(page)).toBe(0);
  await s.click();
  await expect(page.locator('#register')).toBeInViewport();
  await expect.poll(() => firstParty(net, 'cta_ask').map((e) => e.props.cta), { timeout: 8000 }).toEqual(['sticky']);
});

// 24.10 (слово власника): «עד 12 תשלומים» під ціною, сума платежу йде за розміром; «התקשרו אלינו» → міні-форма
// з телефоном → заявка lead_source=callback; cta_call — лише наша аналітика
for (const [prefix, t] of [['', HE], ['/en', EN], ['/ru', RU]]) {
  test(`${prefix || '/'} 390: תשלומים під ціною, «${t.call_cta}» → зворотний дзвінок, cta_call без Meta`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const net = await setup(page);
    await page.goto(`${ORIGIN}${prefix}/p/tavor/`);
    const pay = page.locator('.pdp-pay');
    await expect(pay).toContainText(t.installments.replace('{{INSTALLMENTS}}', CONTENT.INSTALLMENTS));
    const monthly = (n) => Math.ceil(n / Number(CONTENT.INSTALLMENTS)).toLocaleString('en-US');
    await expect(pay.locator('[data-monthly]')).toContainText(monthly(TAVOR.sizes[0].price_ils));
    const last = TAVOR.sizes[TAVOR.sizes.length - 1];
    await page.locator(`label:has(input[name="size"][value="${last.label}"])`).first().click();
    await expect(pay.locator('[data-monthly]')).toContainText(monthly(last.price_ils).replace(/,/g, prefix === '/ru' ? ' ' : ','));

    const call = page.locator('.pdp-actions [data-call]');
    await expect(call).toHaveText(t.call_cta);
    const [ask, c] = await Promise.all([page.locator('.pdp-actions [data-ask]').boundingBox(), call.boundingBox()]);
    expect(c.y).toBeGreaterThan(ask.y + ask.height - 1);
    const form = page.locator('#callback');
    await expect(form).toBeHidden();
    await call.click();
    await expect(form).toBeVisible();
    await expect(call).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('#cb-phone')).toBeFocused();
    await expect(form).toContainText(t.callback_hours);
    await expect.poll(() => firstParty(net, 'cta_call').length, { timeout: 8000 }).toBe(1);
    expect(firstParty(net, 'cta_call')[0].props).toMatchObject({ content_ids: ['tavor'], cta: 'pdp' });
    expect(await fbNamed(page, 'cta_call')).toHaveLength(0);
    expect(await noOverflow(page)).toBe(0);

    await form.locator('button[type="submit"]').click();
    await expect(page.locator('#cb-e-phone')).toBeVisible();
    expect(net.leads).toHaveLength(0);
    await page.locator('#cb-phone').fill(PHONE);
    await form.locator('input[name="consent"]').check();
    await form.locator('button[type="submit"]').click();
    await expect(page.locator('[data-callback-thanks]')).toBeVisible();
    await expect(form).toBeHidden();
    expect(net.leads).toHaveLength(1);
    expect(net.leads[0]).toMatchObject({ lead_source: 'callback', name: '', phone: PHONE, consent: true, product_id: 'tavor',
      size_label: last.label });
    await waitFb(page, 'Lead');
    await expect(page.locator('body')).not.toHaveClass(/is-registered/);
  });
}

// №20 (слово 25.10): «що вам зручно» — дзвінок, відеодзвінок або «надішліть деталі» (e-mail або телефон), зручний час
for (const [prefix, t] of [['', HE], ['/en', EN], ['/ru', RU]]) {
  test(`${prefix || '/'} 390: міні-форма — ${t.cb_pref_call} / ${t.cb_pref_video} / ${t.cb_pref_info}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const net = await setup(page);
    await page.goto(`${ORIGIN}${prefix}/p/tavor/`);
    await expect(page.locator('.pdp-call-hint')).toHaveText(t.call_hint);
    await page.locator('.pdp-actions [data-call]').click();
    const form = page.locator('#callback');
    await expect(form).toBeVisible();
    const chip = (v) => form.locator(`input[name="contact_pref"][value="${v}"]`);
    await expect(chip('call')).toBeChecked();
    await expect(form.locator('[data-pref-hint="call"]')).toBeVisible();
    await expect(form.locator('[data-cb-email]')).toBeHidden();
    // «деталі»: з'являється e-mail, підказка змінюється; без жодного контакту — помилка, лід не йде
    await form.locator('label.chip:has(input[value="info"])').click();
    await expect(chip('info')).toBeChecked();
    await expect(form.locator('[data-pref-hint="info"]')).toBeVisible();
    await expect(form.locator('[data-pref-hint="call"]')).toBeHidden();
    await expect(page.locator('#cb-email')).toBeVisible();
    expect(await noOverflow(page)).toBe(0);
    await form.locator('input[name="consent"]').check();
    await form.locator('button[type="submit"]').click();
    await expect(page.locator('#cb-e-phone')).toHaveText(t.js.e_contact);
    await page.locator('#cb-email').fill('not-an-email');
    await form.locator('button[type="submit"]').click();
    await expect(page.locator('#cb-e-email')).toHaveText(t.js.e_email);
    expect(net.leads).toHaveLength(0);
    await page.locator('#cb-email').fill('dana.test@example.org');
    await page.locator('#cb-time').fill('x'.repeat(100));
    await expect(page.locator('#cb-time')).toHaveValue('x'.repeat(80));
    await form.locator('button[type="submit"]').click();
    await expect(page.locator('[data-callback-thanks]')).toBeVisible();
    expect(net.leads).toHaveLength(1);
    expect(net.leads[0]).toMatchObject({ lead_source: 'callback', contact_pref: 'info', email: 'dana.test@example.org',
      phone: '', preferred_time: 'x'.repeat(80), product_id: 'tavor' });
  });

  test(`${prefix || '/'} 390: ${t.cb_pref_video} — телефон обов'язковий, e-mail не йде`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const net = await setup(page);
    await page.goto(`${ORIGIN}${prefix}/p/tavor/`);
    await page.locator('.pdp-actions [data-call]').click();
    const form = page.locator('#callback');
    await form.locator('label.chip:has(input[value="video"])').click();
    await expect(form.locator('[data-pref-hint="video"]')).toHaveText(t.cb_hint_video);
    await expect(page.locator('#cb-email')).toBeHidden();
    await form.locator('input[name="consent"]').check();
    await form.locator('button[type="submit"]').click();
    await expect(page.locator('#cb-e-phone')).toBeVisible();
    await page.locator('#cb-phone').fill(PHONE);
    await form.locator('button[type="submit"]').click();
    await expect(page.locator('[data-callback-thanks]')).toBeVisible();
    expect(net.leads).toHaveLength(1);
    expect(net.leads[0]).toMatchObject({ lead_source: 'callback', contact_pref: 'video', phone: PHONE });
    expect(net.leads[0].email || '').toBe('');
  });
}

for (const [prefix, t] of [['', HE], ['/en', EN], ['/ru', RU]]) {
  test(`${prefix || '/'} 390: іконка дзвінка 44×44 у липкій смузі поруч із «${t.ask_cta_short}», смуга не ламається`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const net = await setup(page);
    await page.goto(`${ORIGIN}${prefix}/p/tavor/`);
    await page.evaluate(() => scrollTo(0, document.querySelector('#spec').getBoundingClientRect().top + scrollY));
    const sticky = page.locator('[data-sticky]');
    await expect(sticky).toHaveClass(/is-on/);
    const icon = sticky.locator('[data-call]');
    await expect(icon).toHaveAttribute('aria-label', t.call_cta);
    const [bar, ask, ic, atc, price] = await Promise.all([sticky.boundingBox(), sticky.locator('[data-ask]').boundingBox(),
      icon.boundingBox(), sticky.locator('[data-add-cart]').boundingBox(), sticky.locator('.sticky-price').boundingBox()]);
    expect(Math.round(ic.width)).toBe(44);
    expect(Math.round(ic.height)).toBe(44);
    expect(bar.height).toBeLessThanOrEqual(58);
    for (const b of [ask, ic, atc, price]) {
      expect(b.x).toBeGreaterThanOrEqual(bar.x - 0.5);
      expect(b.x + b.width).toBeLessThanOrEqual(bar.x + bar.width + 0.5);
      expect(Math.abs(b.y + b.height / 2 - (ic.y + ic.height / 2))).toBeLessThan(2);
    }
    // на івриті — праворуч від «שאלה?»; en/ru (LTR) — та сама розмітка, тож ліворуч від неї
    if (prefix === '') expect(ic.x).toBeGreaterThanOrEqual(ask.x + ask.width - 0.5);
    else expect(ic.x + ic.width).toBeLessThanOrEqual(ask.x + 0.5);
    // текст кнопок не обрізано
    const clipped = await sticky.evaluate((el) => [...el.querySelectorAll('.btn')].filter((b) => b.scrollWidth > b.clientWidth + 1).length);
    expect(clipped).toBe(0);
    expect(await noOverflow(page)).toBe(0);
    await icon.click();
    await expect(page.locator('#callback')).toBeVisible();
    await expect(page.locator('#callback')).toBeInViewport();
    await expect.poll(() => firstParty(net, 'cta_call').map((e) => e.props.cta), { timeout: 8000 }).toEqual(['sticky']);
  });
}

test('липка смуга на телефоні кладе в кошик вибраний розмір', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.goto(`${ORIGIN}/p/tavor/`);
  const last = TAVOR.sizes[TAVOR.sizes.length - 1];
  await page.locator(`label:has(input[name="size"][value="${last.label}"])`).first().click();
  await page.evaluate(() => scrollTo(0, document.querySelector('#spec').getBoundingClientRect().top + scrollY));
  const sticky = page.locator('[data-sticky]');
  await expect(sticky).toHaveClass(/is-on/);
  await sticky.locator('[data-add-cart]').click();
  await page.waitForURL('**/cart/');
  await expect(page.locator('.cart-meta')).toContainText(last.label);
  const [atc] = await waitFb(page, 'AddToCart');
  expect(atc[2].cta).toBe('sticky');
});

// 24.10: leave.scroll був 0 у 45 із 49 мобільних сесій — замір прокрутки: % і px, екран і висота сторінки, лише перша сторона
test('телефон 390: прокрутка на екран → leave зі scroll > 0, scroll_px, vh, ph; у Meta не йде', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const net = await setup(page);
  await page.goto(`${ORIGIN}/p/tavor/`);
  await page.mouse.wheel(0, 844);
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(400);
  await page.goto(`${ORIGIN}/catalog/`);
  await page.waitForLoadState('load');
  await pullBeacons(page, net);
  const leave = firstParty(net, 'leave').find((e) => e.props.step === 'pdp');
  expect(leave).toBeTruthy();
  expect(leave.props.scroll).toBeGreaterThan(0);
  expect(leave.props.scroll_px).toBeGreaterThan(400);
  expect(leave.props.vh).toBe(844);
  expect(leave.props.ph).toBeGreaterThan(leave.props.scroll_px);
  expect(await fbNamed(page, 'leave')).toEqual([]);
});

test('сервер не прийняв заявку (429) — текст помилки, форма лишається, Lead не йде', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const net = await setup(page, { lead: { ok: false, error: 'rate_limited' } });
  await page.route(`${ORIGIN}/api/fx/lead`, (route) => { net.leads.push(1); return route.fulfill({ status: 429, json: { ok: false, error: 'rate_limited' } }); });
  await page.addInitScript((size) => {
    localStorage.setItem('fx_cart_v1', JSON.stringify({ v: 1, items: [{ id: 'tavor', size, finish: 'natural', base: 'oak', qty: 1 }] }));
    sessionStorage.setItem('fx_checkout_v1', JSON.stringify({ city: 'tel-aviv', when: '1-3m', name: '', phone: '' }));
  }, TAVOR.sizes[0].label);
  await page.goto(`${ORIGIN}/checkout/#pay`);
  const cityOk = await page.locator('#co-city option[value="tel-aviv"]').count();
  test.skip(!cityOk, 'у списку міст нема tel-aviv');
  await expect(page.locator('[data-co-pay]')).toBeVisible();
  await page.locator('#pay-phone').fill(PHONE);
  await page.locator('[data-co-keep] input[name="consent"]').check();
  await page.locator('[data-co-keep] button[type="submit"]').click();
  await expect(page.locator('[data-co-keep] .f-status')).toHaveText(HE.js.rate);
  await expect(page.locator('[data-co-keep]')).toBeVisible();
  expect(net.leads).toHaveLength(1);
  expect(await fbNamed(page, 'Lead')).toEqual([]);
});
