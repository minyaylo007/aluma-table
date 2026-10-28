// Ізольовані тести вітрини: кожен запис у бізнес-API перехоплено локально, /api/fx/config — підставний.
// Працює проти tools/serve-preview.py (playwright.local.config.js); ніколи не проти прода.
const { test, expect } = require('@playwright/test');

const CATALOG = require('../catalog/products.json');
const SHOWROOM = !!require('../content.json').OWNER_FACTS.SHOWROOM_AREA_HE;   // №30: плитка «לראות מקרוב» — лише з факту
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
// №15: на картці телефона банер чекає, доки пара кнопок і «התקשרו» піднімуться над його зоною — прокрутка на 400 px
const reveal = page => page.evaluate(() => { scrollTo(0, 400); dispatchEvent(new Event('scroll')); });

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
    // №32 (27.10): тижні — лише оцінкою «אספקה משוערת» у рядку під ціною і лише в товарів першої серії
    expect(await page.locator('.pdp-buy').evaluate((el) => { const c = el.cloneNode(true); c.querySelector('.pdp-sub').remove(); return c.innerText; }))
      .not.toContain('שבועות');
    const sub = await page.locator('.pdp-sub').innerText();
    if (sub.includes('שבועות')) expect(sub).toContain('אספקה משוערת');
    // 24.10, слово власника: позначки «הדמיה» на кадрах нема (застереження — у terms_html «תמונות»)
    await expect(page.locator('.viz-tag')).toHaveCount(0);
    expect(await page.locator('main').innerText()).not.toContain('הדמיה');
    if (!p.model3d) await expect(page.locator('.js-3d')).toHaveCount(0);
    expect(await noOverflow(page)).toBeLessThanOrEqual(0);
    expect(errors).toEqual([]);
  });
}

test('material block: three facts, a close-up, every catalog finish, link to the materials on About', async ({ page }) => {
  const errors = watchErrors(page);
  await mockApi(page);
  for (const [pre, loc] of [['', 'he'], ['/en', 'en']]) {
    await page.goto(pre + '/');
    const sec = page.locator('section.material');
    await expect(sec.locator('.mat-facts > li')).toHaveCount(3);
    await expect(sec.locator('.viz-tag')).toHaveCount(0);
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

// №27: реклама «collection» веде в каталог, 86 % ішли без картки — на телефоні кожна картка каже, що це за річ,
// має видиму кнопку всередині посилання, фото першого екрана не «lazy», а другий кадр (hover) на тачі не вантажиться
for (const prefix of ['', '/ru']) {
  test(`catalog 390 ${prefix || 'he'}: every card names its kind and shows a button inside the link; first-screen photos are eager`, async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    const page = await ctx.newPage();
    await mockApi(page);
    await page.goto(`${prefix}/catalog/`);
    const r = await page.evaluate(() => [...document.querySelectorAll('.cards .card')].map(c => {
      const btn = c.querySelector('.card-link .card-cta'), b = btn && btn.getBoundingClientRect();
      return { kind: (c.querySelector('.card-kind') || {}).textContent || '', btn: btn ? btn.textContent.trim() : '', h: b ? b.height : 0,
        loading: c.querySelector('.card-media img').getAttribute('loading'),
        alt: c.querySelector('.card-alt') ? getComputedStyle(c.querySelector('.card-alt')).display : 'none' };
    }));
    expect(r.length).toBe(PRODUCTS.length);
    for (const c of r) {
      expect(c.kind.trim().length).toBeGreaterThan(0);
      expect(c.kind).not.toContain('{{');
      expect(c.btn.length).toBeGreaterThan(0);
      expect(c.h).toBeGreaterThanOrEqual(40);
      expect(c.alt).toBe('none');
    }
    expect(r.slice(0, 4).map(c => c.loading)).toEqual(['eager', 'eager', 'eager', 'eager']);
    expect(r.slice(4).every(c => c.loading === 'lazy')).toBe(true);
    await page.goto(prefix + '/');
    expect(await page.locator('.cards .card-cta').count()).toBe(0);       // головна — як була, без кнопок
    await ctx.close();
  });
}

// №33: уся плитка каталогу — одне посилання: точка в порожньому куті картки (поруч із типом виробу, з протилежного
// боку від тексту) належить <a> і веде на /p/<slug>/; ціна — діапазон розмірів з каталогу; розкладний стіл — «до N»
const priceText = (p, ru) => {
  const ps = [...new Set(p.sizes.map(s => s.price_ils))].sort((a, b) => a - b);
  const f = n => ru ? String(n).replace(/\B(?=(\d{3})+$)/g, ' ') : n.toLocaleString('en-US');
  const lo = ps[0], hi = ps[ps.length - 1];
  if (lo === hi) return ru ? `${f(lo)} ₪` : `₪${f(lo)}`;
  return ru ? `${f(lo)}–${f(hi)} ₪` : `₪${f(lo)}–${f(hi)}`;
};
for (const prefix of ['', '/ru']) {
  test(`catalog 390 ${prefix || 'he'}: the whole tile is one link, price is the size range, extending tables show "up to"`, async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    const page = await ctx.newPage();
    await mockApi(page);
    await page.goto(`${prefix}/catalog/`);
    const r = await page.evaluate(() => [...document.querySelectorAll('.cards .card')].map(c => {
      c.scrollIntoView({ block: 'center', behavior: 'instant' });                              // elementFromPoint бачить лише вікно
      const a = c.querySelector('a.card-link'), box = a.getBoundingClientRect(), k = c.querySelector('.card-kind').getBoundingClientRect();
      const y = k.top + k.height / 2, rtl = document.dir === 'rtl';
      const x = rtl ? box.left + 3 : box.right - 3;                       // порожній бік рядка типу виробу
      const hit = document.elementFromPoint(x, y);
      return { href: a.getAttribute('href'), corner: !!(hit && hit.closest('a.card-link') === a), x, y,
        price: c.querySelector('.card-price').textContent.trim(), open: (c.querySelector('.card-open') || {}).textContent || '' };
    }));
    expect(r.map(c => c.href)[0]).toBe(`${prefix}/p/tavor/`);             // TAVOR — перший
    for (const [i, c] of r.entries()) {
      const p = PRODUCTS[i];
      expect(c.href).toBe(`${prefix}/p/${p.slug}/`);
      expect(c.corner).toBe(true);
      expect(c.price).toBe(priceText(p, prefix === '/ru'));
      const ext = Math.max(0, ...p.sizes.map(s => s.extended_cm || 0));
      if (ext && p.seats && p.seats.extended) {
        expect(c.open).toContain(String(ext));
        expect(c.open).toContain(String(p.seats.extended[p.seats.extended.length - 1]));
      } else expect(c.open).toBe('');
    }
    await page.evaluate(() => document.querySelectorAll('.cards .card')[1].scrollIntoView({ block: 'center', behavior: 'instant' }));
    const second = await page.evaluate(() => {
      const c = document.querySelectorAll('.cards .card')[1], a = c.querySelector('a.card-link').getBoundingClientRect();
      const k = c.querySelector('.card-kind').getBoundingClientRect();
      return { href: c.querySelector('a.card-link').getAttribute('href'), x: document.dir === 'rtl' ? a.left + 3 : a.right - 3, y: k.top + k.height / 2 };
    });
    await page.mouse.click(second.x, second.y);
    await expect(page).toHaveURL(new RegExp(`${second.href}$`));
    await ctx.close();
  });
}

// №33: перший екран головної — стіл: назва, діапазон ціни, факти й кнопка на /p/tavor/ видно на 390×650 без прокрутки
for (const [prefix, ru] of [['', false], ['/ru', true], ['/en', false]]) {
  test(`home 390×650 ${prefix || 'he'}: hero shows TAVOR with its price range and links to /p/tavor/ above the fold`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 650 });
    await mockApi(page);
    await page.goto(prefix + '/');
    await page.evaluate(() => document.fonts.ready);
    const tavor = PRODUCTS.find(p => p.slug === 'tavor');
    const cta = page.locator('.hero a[data-cta="hero-tavor"]');
    await expect(cta).toHaveAttribute('href', `${prefix}/p/tavor/`);
    await expect(page.locator('.hero .hero-price')).toHaveText(priceText(tavor, ru));
    await expect(page.locator('.hero .hero-facts')).toContainText('280');
    await expect(page.locator('.hero a[data-cta="hero-catalog"]')).toHaveAttribute('href', `${prefix}/catalog/`);
    await expect(page.locator('.hero a[href="#register"]')).toHaveCount(0);
    const bottom = await page.evaluate(() => Math.max(...[...document.querySelectorAll('.hero .actions .btn, .hero-price, .hero-facts')]
      .map(e => e.getBoundingClientRect().bottom)));
    expect(bottom).toBeLessThanOrEqual(650);
    expect(await noOverflow(page)).toBeLessThanOrEqual(0);
  });
}

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
  // не розмір за замовчуванням (№36: TAVOR відкривається на 200×100) — інакше ціна не зміниться
  const last = p.sizes.filter(s => s.default !== true && s.price_ils !== (p.sizes.find(z => z.default === true) || p.sizes[0]).price_ils).pop();
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
  await page.locator('#unfold summary').click();   // №39: глава під спойлером
  // видно план розміру за замовчуванням (№36: позначка default у каталозі, інакше перший)
  const def = p.sizes.find(s => s.default === true) || p.sizes[0];
  await expect(page.locator(`[data-plan-size="${def.label}"]`)).toBeVisible();
  await expect(page.locator('[data-plan-size]:visible')).toHaveCount(1);
  const last = p.sizes.find(s => s.label !== def.label && s.extended_cm);
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
    await expect(steps.locator('.viz-tag')).toHaveCount(0);
  }
  expect(await noOverflow(page)).toBeLessThanOrEqual(0);
  expect(errors).toEqual([]);
});

test('morning / evening switch swaps the light layer, no tag, hides the inactive picture from screen readers', async ({ page }) => {
  const p = PRODUCTS.find(x => (x.images || []).filter(i => i.view === 'light').length >= 2);
  const errors = watchErrors(page);
  await mockApi(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`/p/${p.slug}/`);
  await page.locator('[data-notice-no]').click();
  await page.locator('#light summary').click();   // №39: глава під спойлером
  const fig = page.locator('[data-light-fig]');
  await expect(fig).toHaveAttribute('data-on', 'morning');
  await expect(fig.locator('.viz-tag')).toHaveCount(0);
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
  expect(lead.size_label).toBe((p.sizes.find(s => s.default === true) || p.sizes[0]).label);   // №36: розмір за замовчуванням
  expect(lead.finish_id).toBe(p.finishes[0].id);
  expect(lead.consent).toBe(true);
  expect(lead.consent_marketing).toBe(false);              // חוק התקשורת 30א: не відмічено за замовчуванням
  expect(lead.marketing_consent).toBe(false);
  expect(lead.ads_consent).toBe(true);                      // opt-out (власник 24.10): без вибору — не відмова, Lead у CAPI йде
  expect(lead.utm_source).toBe('test');
  expect(lead.lang).toBe('he');
  expect(lead.website).toBe('');
});

// №22: «наступне видання» — не товар: без кошика, одна кнопка, голос — lead_source=vote, досить телефону
for (const slug of ['tavor-fluted', 'tavor-oval']) {
  test(`next edition /p/${slug}/: one button, no cart, a vote with a phone only`, async ({ page }) => {
    const errors = watchErrors(page);
    const sent = await mockApi(page);
    await page.goto(`/p/${slug}/?utm_campaign=stage2-lead&utm_content=${slug}`);
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(page.locator('[data-add-cart]')).toHaveCount(0);
    await expect(page.locator('a[href*="/checkout/"]')).toHaveCount(0);
    await expect(page.locator('#vote')).toBeHidden();
    await page.locator('[data-vote]').click();
    await expect(page.locator('#vote')).toBeVisible();
    await expect(page.locator('[data-vote]')).toHaveAttribute('aria-expanded', 'true');
    await page.locator('#vote button[type="submit"]').click();
    await expect(page.locator('#vote [aria-invalid="true"]').first()).toBeVisible();
    expect(sent.leads).toHaveLength(0);
    await page.locator('#v-phone').fill(FAKE_PHONE);
    await page.locator('#vote input[name="consent"]').check();
    await page.locator('#vote button[type="submit"]').click();
    await expect(page.locator('[data-vote-thanks]')).toBeVisible();
    expect(sent.leads).toHaveLength(1);
    const lead = sent.leads[0];
    expect(lead.lead_source).toBe('vote');
    expect(lead.product_id).toBe(slug);
    expect(lead.utm_content).toBe(slug);
    expect(lead.name || '').toBe('');
    await expect.poll(() => sent.events.flatMap(b => b.events || []).filter(e => e.name === 'cta_vote').length,
      { timeout: 8000 }).toBe(1);
    expect(await noOverflow(page)).toBeLessThanOrEqual(0);
    expect(errors).toEqual([]);
  });
}

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
  await reveal(page);
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
  await expect(sticky.locator('.sticky-thumb')).toHaveAttribute('alt', PRODUCTS[0].name.he);
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
  await reveal(page);
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
  // opt-out (власник 24.10): до вибору піксель уже вантажиться, банер про це каже
  await expect.poll(() => sent.thirdParty || '').toContain('connect.facebook.net');
  await page.locator('[data-notice-no]').click();
  await expect(page.locator('#notice')).toBeHidden();
  expect(await page.evaluate(() => localStorage.getItem('fx_notice_v1'))).toBe('0');
  delete sent.thirdParty;
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
    await expect(band.locator('.viz-tag')).toHaveCount(0);
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
  await reveal(page);
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
// серії, умови й ОБИДВІ кнопки «הוספה לסל» + «שאלה?»; «השאירו פרטים» — під ними, плитки розмірів — нижче.
// Банер (№15) — лише коли не накриває пари й «התקשרו», на 360 і на 390. Смуги на першому екрані нема; 3D — чип на кадрі.
// №28 (26.10): чверть мобільних заходів — вікно ≤ 650 px (вбудований браузер Instagram), половина йшла без прокрутки:
// на 650 теж видно кадр, назву, рядок фактів, ціну, рядок доставки й пару «הוספה לסל» + «שאלה?» в один ряд
// №32 (27.10): + рядок «строк · гарантія» під ціною; доставка — трьома числами; пара кнопок однаково в межах 650
for (const [w, h] of [[390, 844], [360, 780], [390, 650], [360, 650]]) {
  for (const [prefix, lang] of [['', 'he'], ['/en', 'en'], ['/ru', 'ru']]) {
    for (const slug of ['tavor', 'sahar', 'tal']) {
      test(`first screen ${w}×${h} of ${prefix}/p/${slug}/ (${lang}): photo, name, price, terms and both buttons without scrolling`, async ({ page }) => {
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
            incl: box('.pdp-price .price-incl'), facts: box('.pdp-facts'), sub: box('.pdp-sub'), ship: box('.pdp-ship'), trust: box('.trust-strip'), cart: box('.pdp-pair [data-add-cart]'),
            ask: box('.pdp-pair [data-ask]'), call: box('.pdp-actions [data-call]'), lead: box('.pdp-ask'), tile: box('label.pill:has(input[name="size"])'),
            inclLH: parseFloat(getComputedStyle(document.querySelector('.pdp-price .price-incl')).lineHeight) };
        });
        const r = await measure();
        expect(r.y).toBe(0);
        for (const b of [r.img, r.h1, r.tag, r.facts, r.price, r.incl, r.sub, r.ship, r.cart, r.ask]) {
          expect(b.top).toBeGreaterThan(0); expect(b.bottom).toBeLessThanOrEqual(r.vh);
        }
        expect(r.incl.height).toBeLessThan(r.inclLH * 1.5);            // підпис серії — один рядок
        // порядок на екрані (№28): факти → ціна → доставка → кошик і питання в один ряд → «התקשרו» → плитки розмірів →
        // смуга довіри (№19) → «השאירו פרטים»
        expect(r.price.top).toBeGreaterThan(r.facts.bottom - 1);
        expect(r.sub.top).toBeGreaterThan(r.price.top);               // №32: строк і гарантія під ціною, далі доставка числами
        expect(r.ship.top).toBeGreaterThan(r.sub.bottom - 1);
        expect(r.cart.top).toBeGreaterThan(r.ship.bottom);
        expect(Math.abs(r.ask.top - r.cart.top)).toBeLessThan(2);
        expect(r.call.top).toBeGreaterThan(r.ask.bottom);
        expect(r.tile.top).toBeGreaterThan(r.call.bottom);
        expect(r.trust.top).toBeGreaterThan(r.tile.bottom);
        expect(r.lead.top).toBeGreaterThan(r.trust.bottom);
        expect(r.chip.top).toBeGreaterThanOrEqual(r.img.top);         // чип 3D лежить на кадрі
        expect(r.chip.bottom).toBeLessThanOrEqual(r.img.bottom);
        expect(r.chip.width).toBeLessThan(r.img.width / 2);
        // №15: банер з'являється лише тоді, коли не накриває жодної з трьох кнопок — крок прокрутки 40 px, як пальцем
        await nudge(page);
        await page.waitForTimeout(100);
        // на місці накрив би «התקשרו» — лише коли та в зоні банера (130 px знизу); №28: на 844 трійка вже над нею — банер одразу
        if (r.call.bottom > r.vh - 130) await expect(page.locator('#notice')).toBeHidden();
        for (let i = 0; i < 25 && await page.locator('#notice').isHidden(); i++) {
          await page.mouse.wheel(0, 40);
          await page.waitForTimeout(60);
        }
        await expect(page.locator('#notice')).toBeVisible();
        await page.waitForTimeout(150);
        const n = await measure();
        for (const b of [n.cart, n.ask, n.call]) expect(b.bottom).toBeLessThanOrEqual(n.notice);
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

// №15: на 360 таймера нема — без прокрутки банер не з'являється й через 7 с, після прокрутки — так
test('cookie notice on 360: no 6 s timer, only after a scroll (catalog and card)', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await mockApi(page);
  await page.goto('/catalog/');
  await page.waitForTimeout(7000);
  await expect(page.locator('#notice')).toBeHidden();
  await page.mouse.wheel(0, 300);
  await expect(page.locator('#notice')).toBeVisible();
  await page.evaluate(() => localStorage.removeItem('fx_notice_v1'));
  await page.goto('/ru/p/tavor/');
  await page.waitForTimeout(7000);
  await expect(page.locator('#notice')).toBeHidden();
  await reveal(page);
  await expect(page.locator('#notice')).toBeVisible();
});

// №15: Tab іде так, як видно — DOM картки = екран, без CSS order: ціна → кошик → «שאלה?» → «התקשרו» → тон/розмір (№28) → смуга → «השאירו פרטים»
for (const [w, h] of [[390, 844], [1280, 800]]) {
  test(`focus order on a card at ${w}px follows the screen: actions, the config, the trust strip, then the lead link`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h });
    await mockApi(page);
    await page.goto('/p/tavor/');
    await page.evaluate(() => document.fonts.ready);
    const tops = await page.evaluate(() => {
      const els = [...document.querySelectorAll('.pdp-buy a[href], .pdp-buy button, .pdp-buy input:checked, .pdp-buy summary')]
        .filter(e => e.getClientRects().length && !e.closest('[hidden]'));
      return els.map(e => { const b = (e.matches('input') ? e.closest('label') || e : e).getBoundingClientRect(); return b.top + scrollY; });
    });
    expect(tops.length).toBeGreaterThan(5);
    for (let i = 1; i < tops.length; i++) expect(tops[i]).toBeGreaterThanOrEqual(tops[i - 1] - 2);   // DOM-порядок = зверху вниз
    await page.locator('.pdp-pair [data-add-cart]').focus();
    const seq = [];
    for (let i = 0; i < 14; i++) {
      await page.keyboard.press('Tab');
      seq.push(await page.evaluate(() => { const a = document.activeElement;
        return a.matches('[data-ask]') ? 'ask' : a.matches('[data-video]') ? 'video' : a.matches('[data-call]') ? 'call' : a.matches('.pdp-ask') ? 'lead'
          : a.closest('.trust-strip') ? 'strip' : a.closest('.pdp-config') ? 'config' : a.tagName; }));
    }
    // №19: смуга довіри — перед «השאירו פרטים»: 4 заголовки + PDF збирання (у tavor він є); №28: тон/розмір — одразу під діями;
    // №30: з фактом району — ще плитка «לראות מקרוב»
    const strip = Array(SHOWROOM ? 6 : 5).fill('strip');
    expect(seq.slice(0, 8 + strip.length)).toEqual(['ask', 'video', 'call', 'config', 'config', 'config', 'config', ...strip, 'lead']);
  });
}

// №15: каталог на телефоні — дві колонки, тож sizes «46vw», а не «92vw»: на 390 px × DPR 3 браузер бере 800w, не 1200w
test('catalog photos on a 390 px phone (DPR 3) load the half-width file; the home page keeps the full-width one', async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 });
  const page = await ctx.newPage();
  await mockApi(page);
  await page.goto('/catalog/');
  const img = page.locator('.cards .card-media img').first();
  await img.evaluate(el => el.decode().catch(() => {}));
  const r = await img.evaluate(el => {
    const set = el.closest('picture').querySelector('source').getAttribute('srcset').split(',').map(s => s.trim().split(' '));
    const cur = set.find(([u]) => el.currentSrc.endsWith(u));
    return { sizes: el.getAttribute('sizes'), w: cur ? parseInt(cur[1], 10) : 0, all: set.map(s => parseInt(s[1], 10)),
      slot: el.getBoundingClientRect().width * devicePixelRatio };
  });
  expect(r.sizes).toBe('(min-width: 1000px) 30vw, 46vw');
  expect(r.w).toBeGreaterThan(0);
  expect(r.w).toBe(Math.min(...r.all.filter(x => x >= 0.46 * 390 * 3)));   // найменший файл, що покриває пів-ширини
  expect(r.w).toBeLessThanOrEqual(r.slot * 1.6);
  await page.goto('/');
  expect(await page.locator('.cards .card-media img').first().getAttribute('sizes')).toBe('(min-width: 1000px) 30vw, (min-width: 600px) 46vw, 92vw');
  await ctx.close();
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
    await (path.includes("/p/") ? reveal(page) : nudge(page));
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
    // №39: глави під спойлерами; читач, що гортає главами, їх відкрив — тоді поточна глава стежить за прокруткою
    await page.evaluate(() => document.querySelectorAll('details[data-acc]').forEach(d => { d.open = true; }));
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

test('life first: every card opens its gallery on the piece at home, then the clean frontal; the oak close-up of the console and the TV unit comes third', async ({ page }) => {
  // 21.10: крупний план першим кадром скасовано — з реклами на 390 видно лише кут дошки, не виріб.
  // 24.10 (слово власника, «як фото»): першим — кадр life у квартирі для всіх п'яти (TAL більше не виняток),
  // за ним чистий фронтальний hero, потім крупний план дуба, де він є.
  await mockApi(page);
  for (const p of PRODUCTS) {
    await page.goto(`/p/${p.slug}/`);
    const srcs = await page.locator('.gallery .g-slide img').evaluateAll(is => is.map(i => i.getAttribute('src')));
    expect(p.images[0].view, p.slug).toBe('hero');
    expect(srcs[0], p.slug).toContain(`/products/${p.slug}/life-`);
    expect(srcs[1], p.slug).toContain(`/products/${p.slug}/hero-`);
    if (p.images.some(i => i.view === 'texture')) expect(srcs[2], p.slug).toContain(`/products/${p.slug}/texture-`);
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
    await expect(box.locator('.viz-tag')).toHaveCount(0);
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

// ---------------------------------------------------------------- №39: коротка картка, відеодзвінок, липка смуга
test('card 390 he /p/tavor/: no taller than 7 000 px — chapters sit under closed spoilers', async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 650 });
  await page.goto('/p/tavor/');
  expect(await page.evaluate(() => document.body.scrollHeight)).toBeLessThanOrEqual(7000);
});

test('spec chapter is closed with its heading visible and opens by mouse, keyboard and the chapter link', async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/p/tavor/');
  const acc = page.locator('#spec details.pdp-acc');
  const isOpen = () => acc.evaluate(d => d.open);
  expect(await isOpen()).toBe(false);
  await expect(page.locator('#spec-h')).toBeVisible();
  await expect(page.locator('#spec .pdp-acc-body')).toBeHidden();
  await page.locator('#spec summary').click();
  await expect.poll(isOpen).toBe(true);
  await expect(page.locator('#spec .pdp-acc-body')).toBeVisible();
  await page.locator('#spec summary').focus();
  await page.keyboard.press('Enter');
  await expect.poll(isOpen).toBe(false);
  await page.keyboard.press('Space');
  await expect.poll(isOpen).toBe(true);
  // посилання глави відкриває свій спойлер
  const how = page.locator('#how details.pdp-acc');
  expect(await how.evaluate(d => d.open)).toBe(false);
  await page.evaluate(() => { location.hash = '#how'; });
  await expect.poll(() => how.evaluate(d => d.open)).toBe(true);
});

for (const [prefix, lang] of [['', 'he'], ['/ru', 'ru']]) {
  test(`card 390×650 ${lang}: the video button is on the first screen and opens the mini-form with video chosen`, async ({ page }) => {
    await mockApi(page);
    await page.setViewportSize({ width: 390, height: 650 });
    await page.goto(`${prefix}/p/tavor/`);
    const btn = page.locator('.pdp-buy [data-video]');
    await expect(btn).toBeVisible();
    const box = await btn.boundingBox();
    expect(box.y + box.height).toBeLessThanOrEqual(650);
    await expect(btn).toHaveAttribute('aria-expanded', 'false');
    await btn.click();
    await expect(page.locator('#callback')).toBeVisible();
    await expect(btn).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('#callback input[name="contact_pref"][value="video"]')).toBeChecked();
  });
}

test('card 390×650: the sticky bar is off at load without a scroll', async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 650 });
  await page.goto('/p/tavor/');
  await nudge(page);
  await page.waitForTimeout(200);
  await expect(page.locator('[data-sticky]')).not.toHaveClass(/is-on/);
});
