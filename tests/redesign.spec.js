// Isolated frontend tests for the redesign: every business API write is intercepted locally.
// Runs against tools/serve-preview.py (playwright.local.config.js); never against production.
const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.route('**/api/fx/event', route => route.fulfill({ json: { ok: true, written: 0 } }));
  await page.route('**/api/fx/lead', route => route.fulfill({ status: 503, json: { ok: false, error: 'preview_only' } }));
});

const imgLoaded = img => img.evaluate(el => el.complete && el.naturalWidth > 0);

for (const lang of ['he', 'en']) {
  const path = lang === 'he' ? '/' : '/en/';

  for (const [width, height] of [[390, 844], [430, 932], [390, 700], [360, 667], [320, 640], [768, 1024], [1024, 768], [1440, 900], [1920, 1080]]) {
    test(`${lang}: ${width}x${height} renders the whole page without overflow, errors or missing assets`, async ({ page }) => {
      const errors = [], missing = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
      page.on('response', response => { if (response.status() >= 400) missing.push(response.url()); });
      await page.setViewportSize({ width, height });
      await page.goto(path);
      await expect(page.locator('html')).toHaveAttribute('dir', lang === 'he' ? 'rtl' : 'ltr');
      await expect(page.locator('html')).toHaveAttribute('lang', lang);
      await expect(page.locator('h1')).toHaveCount(1);
      await expect(page.locator('#hero-img')).toBeVisible();
      await expect.poll(() => imgLoaded(page.locator('#hero-img'))).toBeTruthy();
      // the first screen: the complete table, the price and the callback action
      const hero = await page.locator('#hero-img').boundingBox();
      expect(hero.x).toBeGreaterThanOrEqual(-1);
      expect(hero.x + hero.width).toBeLessThanOrEqual(width + 1);
      await expect(page.locator('.band .price')).toBeInViewport();
      if (width <= 430) {
        const cta = await page.locator('.band .btn--primary').boundingBox();
        expect(cta.y + cta.height, 'primary action fully visible by 620 px').toBeLessThanOrEqual(620);
        expect(cta.height).toBeGreaterThanOrEqual(48);
      } else {
        await expect(page.locator('.band .btn--primary')).toBeInViewport();
      }
      // every image loads at its real scroll position (lazy sections included)
      const pictures = page.locator('img');
      for (let i = 0; i < await pictures.count(); i++) {
        const img = pictures.nth(i);
        if (await img.isVisible() && await img.evaluate(el => !!(el.getAttribute('src') || el.getAttribute('srcset')))) {
          await img.scrollIntoViewIfNeeded();
          await expect.poll(() => imgLoaded(img)).toBeTruthy();
        }
      }
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      expect(overflow).toBeLessThanOrEqual(1);
      expect(errors).toEqual([]);
      expect(missing).toEqual([]);
    });
  }

  test(`${lang}: six finish/state combinations swap the compare picture and persist`, async ({ page }) => {
    await page.goto(path);
    for (const tone of ['natural', 'smoked', 'white']) {
      for (const size of ['160', '220']) {
        await page.locator(`input[name="oak"][value="${tone}"]`).check({ force: true });
        await page.locator(`input[name="size"][value="${size}"]`).check({ force: true });
        await expect(page.locator('html')).toHaveAttribute('data-oak', tone);
        await expect(page.locator('html')).toHaveAttribute('data-size', size);
        const state = size === '160' ? 'closed' : 'open';
        await expect(page.locator('#compare-img')).toHaveAttribute('data-variant', `${tone}-${state}`);
        await expect(page.locator('#compare-img')).toHaveAttribute('src', new RegExp(`compare-${tone}-${state}|hero-${tone}-${state}`));
        await expect.poll(() => imgLoaded(page.locator('#compare-img'))).toBeTruthy();
        await expect(page.locator('.state-line [data-bind="len"]')).toHaveText(size);
        await expect(page.locator('.form-selection [data-bind="len"]')).toHaveText(size);
      }
    }
    // the open table is physically longer in the same frame: compare the widths of the non-ground pixels
    const widths = await page.evaluate(async () => {
      const measure = async (src) => {
        const im = new Image(); im.src = src; await im.decode();
        const c = document.createElement('canvas'); c.width = im.naturalWidth; c.height = im.naturalHeight;
        const g = c.getContext('2d'); g.drawImage(im, 0, 0);
        const d = g.getImageData(0, 0, c.width, c.height).data;
        let min = c.width, max = 0;
        for (let y = 0; y < c.height; y += 4) for (let x = 0; x < c.width; x += 2) {
          const i = (y * c.width + x) * 4;
          if (Math.abs(d[i] - 244) + Math.abs(d[i + 1] - 241) + Math.abs(d[i + 2] - 234) > 24) { if (x < min) min = x; if (x > max) max = x; }
        }
        return max - min;
      };
      const a = window.FX.assets;
      if (!a['goren-compare-natural-closed'] || !a['goren-compare-natural-closed'].webp['800']) return null;
      return [await measure(a['goren-compare-natural-closed'].webp['800']), await measure(a['goren-compare-natural-open'].webp['800'])];
    });
    if (widths) expect(widths[1]).toBeGreaterThan(widths[0] * 1.15);
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-oak', 'white');
    await expect(page.locator('html')).toHaveAttribute('data-size', '220');
    await expect(page.locator('#compare-img')).toHaveAttribute('data-variant', 'white-open');
  });

  test(`${lang}: the dimensions buttons and the room-length estimate stay on the page`, async ({ page }) => {
    await page.goto(path);
    await page.evaluate(() => { window.previewIdentity = 'same-document'; });
    await page.locator('[data-set-size="220"]').click();
    await expect(page.locator('html')).toHaveAttribute('data-size', '220');
    await expect(page.locator('[data-set-size="220"]')).toHaveAttribute('aria-pressed', 'true');
    await page.locator('#fit summary').click();
    for (const [length, verdict] of [['150', 'no'], ['200', 'closed'], ['220', 'open'], ['340', 'open'], ['3.4', 'open']]) {
      await page.locator('#roomlen').fill(length);
      await expect(page.locator('#verdict')).toHaveAttribute('data-v', verdict);
    }
    await expect(page.locator('#verdict')).toContainText('60');   // (340 - 220) / 2 at each end, a number not a promise
    await page.locator('#roomlen').press('Enter');
    await expect(page.locator('#verdict')).toHaveAttribute('data-v', 'open');
    await page.locator('#roomlen').fill('');
    await expect(page.locator('#verdict')).not.toHaveAttribute('data-v', /.+/);
    expect(await page.evaluate(() => window.previewIdentity)).toBe('same-document');
  });

  test(`${lang}: form validation, then a mocked accepted enquiry with attribution, size and lang`, async ({ page }) => {
    await page.goto(path + '?utm_source=preview&utm_campaign=redesign&fbclid=abc123');
    await page.locator('input[name="size"][value="220"]').check({ force: true });
    await page.locator('input[name="oak"][value="smoked"]').check({ force: true });
    await page.locator('#f-submit').click();
    for (const field of ['name', 'phone', 'consent']) await expect(page.locator(`#e-${field}`)).toBeVisible();
    await expect(page.locator('#f-name')).toHaveAttribute('aria-invalid', 'true');
    await fillLead(page);
    await page.locator('#f-phone').fill('12345');
    await page.locator('#f-submit').click();
    await expect(page.locator('#e-phone')).toBeVisible();
    for (const good of ['00972501234567', '+972-050-1234567', '050-123-4567']) {
      await page.locator('#f-phone').fill(good);
      await page.locator('#f-submit').click();
      await expect(page.locator('#e-phone')).toBeHidden();
      await expect(page.locator('#f-status')).toHaveAttribute('data-s', 'err');   // the preview API refuses; the input is intact
      await expect(page.locator('#f-submit')).toBeEnabled();
    }
    let captured, calls = 0;
    await page.route('**/api/fx/lead', async route => {
      calls++; captured = route.request().postDataJSON();
      await new Promise(r => setTimeout(r, 300));
      await route.fulfill({ json: { ok: true, id: 'local-mock-only' } });
    });
    await page.locator('#f-submit').click();
    await page.locator('#f-submit').click({ force: true });   // a second click while in flight must not send twice
    await page.waitForURL(lang === 'he' ? '**/thanks' : '**/en/thanks');
    expect(calls).toBe(1);
    expect(captured).toMatchObject({ name: 'Preview test', consent: true, consent_marketing: false, utm_source: 'preview', utm_campaign: 'redesign', fbclid: 'abc123', lang, size: '220', color: 'smoked' });
    expect(captured.consent_text_version).toBeTruthy();
    expect(captured.session_id).toBeTruthy();
    await expect(page.locator('h1')).toBeVisible();
  });
}

async function fillLead(page) {
  await page.locator('#f-name').fill('Preview test');
  await page.locator('#f-phone').fill('050-123-4567');
  await page.locator('#f-consent').check();
}

for (const failure of ['rate', 'server', 'offline', 'fields']) {
  test(`lead ${failure} response reports an error, keeps the input and allows retry`, async ({ page }) => {
    await page.goto('/en/');
    await fillLead(page);
    await page.locator('#f-comment').fill('keep me');
    await page.route('**/api/fx/lead', route => failure === 'offline'
      ? route.abort('failed')
      : failure === 'fields'
        ? route.fulfill({ status: 422, json: { ok: false, errors: { phone: 'invalid' } } })
        : route.fulfill({ status: failure === 'rate' ? 429 : 500, json: { ok: false } }));
    await page.locator('#f-submit').click();
    await expect(page.locator('#f-status')).toHaveAttribute('data-s', 'err');
    await expect(page.locator('#f-status')).not.toBeEmpty();
    await expect(page.locator('#f-submit')).toBeEnabled();
    await expect(page.locator('#f-comment')).toHaveValue('keep me');
    if (failure === 'fields') await expect(page.locator('#e-phone')).toBeVisible();
    expect(page.url()).not.toContain('thanks');
  });
}

test('the honeypot decoy is not counted as a conversion', async ({ page }) => {
  const events = [];
  // sendBeacon bodies arrive as a Blob; WebKit gives no parsed JSON, so read the raw text
  const eventNames = req => { try { return (JSON.parse(req.postData() || '{}').events || []).map(e => e.name); } catch (e) { return []; } };
  await page.route('**/api/fx/event', route => { events.push(...eventNames(route.request())); route.fulfill({ json: { ok: true } }); });
  await page.goto('/en/');
  await fillLead(page);
  await page.evaluate(() => { document.querySelector('#f-website').value = 'bot'; });
  await page.route('**/api/fx/lead', route => route.fulfill({ json: { ok: true, id: 'hp' } }));
  await page.locator('#f-submit').click();
  await page.waitForURL('**/en/thanks');
  expect(events).toContain('form_submit');
  expect(events).not.toContain('lead_success');
});

test('sticky shortcut: appears after the hero action, hides over the form and while typing, keeps focus visible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.locator('#sticky')).toBeHidden();
  await page.locator('#dimensions').scrollIntoViewIfNeeded();
  await expect(page.locator('#sticky')).toHaveClass(/is-on/);
  const cta = page.locator('#sticky .js-anchor');
  await cta.focus();
  expect(await cta.evaluate(el => getComputedStyle(el).outlineStyle)).not.toBe('none');
  await expect.poll(() => cta.evaluate(el => { const r = el.getBoundingClientRect(); return el.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)); })).toBeTruthy();
  await page.locator('#fit summary').click();
  await page.locator('#roomlen').focus();
  await expect(page.locator('#sticky')).toBeHidden();          // never over a focused field
  await page.locator('#roomlen').blur();
  await cta.click();
  await expect(page).toHaveURL(/#form$/);
  await expect(page.locator('#f-name')).toBeInViewport();
  await expect(page.locator('#sticky')).toBeHidden();          // redundant next to the form
});

test('WhatsApp controls are absent while no number is configured', async ({ page }) => {
  await page.goto('/');
  expect(await page.locator('.js-wa:visible').count()).toBe(0);
  const wa = await page.evaluate(() => window.FX.cfg.wa);
  expect(wa).toBe('');
});

test('reduced motion keeps the product and the configurator usable', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await page.locator('input[name="size"][value="220"]').check({ force: true });
  await expect(page.locator('#compare-img')).toHaveAttribute('data-variant', 'natural-open');
  await expect(page.locator('.hero-actions')).toBeVisible();
  for (const el of await page.locator('.reveal').all()) await expect(el).toHaveClass(/is-in|will-reveal/);
});

test('enlargement dialog opens on request, closes on Escape and returns focus', async ({ page }) => {
  await page.goto('/en/');
  await page.locator('#compare-zoom').click();
  await expect(page.locator('#image-dialog')).toHaveAttribute('open', '');
  await expect(page.locator('#image-large')).toHaveAttribute('src', /compare-natural-closed|hero-natural-closed/);
  await page.keyboard.press('Escape');
  await expect(page.locator('#image-dialog')).not.toHaveAttribute('open', '');
  await expect(page.locator('#compare-zoom')).toBeFocused();
});

test('keyboard journey reaches every control in a coherent order', async ({ page, browserName }) => {
  await page.goto('/');
  const order = [];
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press('Tab');
    const id = await page.evaluate(() => { const a = document.activeElement; return a.id || a.getAttribute('name') || a.className.split(' ')[0] || a.tagName; });
    order.push(id);
    if (id === 'f-submit') break;
  }
  // WebKit only tabs between form controls unless full keyboard access is on, so links are skipped there
  if (browserName !== 'webkit') expect(order[0]).toBe('skip');
  for (const control of ['size', 'oak', 'f-name', 'f-phone', 'f-consent', 'f-marketing', 'f-submit']) expect(order).toContain(control);
  expect(order.indexOf('size')).toBeLessThan(order.indexOf('f-name'));
  expect(order.indexOf('f-consent')).toBeLessThan(order.indexOf('f-submit'));
});

test('no 3D, video or third-party payload loads on a normal visit', async ({ page, baseURL }) => {
  const urls = [];
  page.on('request', r => urls.push(r.url()));
  await page.goto('/');
  await page.evaluate(async () => { for (let y = 0; y < document.documentElement.scrollHeight; y += 600) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 80)); } });
  await page.waitForTimeout(500);
  expect(urls.filter(u => !u.startsWith(new URL(baseURL).origin))).toEqual([]);
  expect(urls.filter(u => /three|goren3d|\.mp4|\.hdr|textures\//.test(u))).toEqual([]);
});

test('page metadata, one preload per hero variant, hashed immutable asset names', async ({ page }) => {
  await page.goto('/');
  const meta = await page.evaluate(() => ({
    canonical: document.querySelector('link[rel="canonical"]').href,
    hreflang: [...document.querySelectorAll('link[rel="alternate"][hreflang]')].map(l => l.hreflang),
    preloads: [...document.querySelectorAll('link[rel="preload"][as="image"]')].map(l => l.media),
    og: document.querySelector('meta[property="og:image"]').content,
    assets: [...document.querySelectorAll('link[rel="stylesheet"], script[src]')].map(e => e.href || e.src),
    unresolved: /\{\{[\w.]+\}\}/.test(document.body.innerText) || /\{\{[A-Z][\w]*\}\}|\{\{t\.[\w]+\}\}/.test(document.documentElement.outerHTML),
    jsonld: JSON.parse(document.querySelector('script[type="application/ld+json"]').textContent),
  }));
  expect(meta.canonical).toBe('https://table.central-aparts.store/');
  expect(meta.hreflang.sort()).toEqual(['en', 'he', 'x-default']);
  expect(meta.preloads.length).toBe(2);
  expect(meta.og).toMatch(/og\.[0-9a-f]{10}\.png$/);
  for (const a of meta.assets) expect(a).toMatch(/\.[0-9a-f]{10}\.(css|js)$/);
  expect(meta.unresolved).toBe(false);
  expect(meta.jsonld.offers.availability).toBe('https://schema.org/PreOrder');
  expect(meta.jsonld.aggregateRating).toBeUndefined();
});

test('thanks, 404 and legal routes render in both locales', async ({ page }) => {
  for (const [url, h1] of [['/thanks.html', /קיבלנו/], ['/en/thanks.html', /Got it/], ['/privacy.html', /פרטיות/], ['/en/terms.html', /Terms/], ['/accessibility.html', /נגישות/], ['/404.html', /לא קיים/]]) {
    const res = await page.goto(url);
    expect(res.status(), url).toBe(200);
    await expect(page.locator('h1')).toHaveText(h1);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test('preview server explicitly refuses real lead submissions', async ({ request }) => {
  const response = await request.post('/api/fx/lead', { data: { name: 'Preview test' } });
  expect(response.status()).toBe(503);
  expect(await response.json()).toMatchObject({ ok: false, error: 'preview_only' });
});

test('storage failure does not break the page', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });
    Object.defineProperty(window, 'sessionStorage', { get() { throw new Error('blocked'); } });
  });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await page.locator('input[name="oak"][value="white"]').check({ force: true });
  await expect(page.locator('html')).toHaveAttribute('data-oak', 'white');
  expect(errors).toEqual([]);
});
