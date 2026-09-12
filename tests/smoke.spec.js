// Smoke suite for a FULL stack — static pages plus a live api/handler.py behind them.
//
// ⚠️ NOT for prod and NOT for table-new. This suite WRITES to storage: a real is_test lead
// via route.fetch, a page_view without X-Test on every goto, events via route.continue.
// Run it only against a throwaway stack (CLAUDE.md §6, §8):
//
//     python3 build.py
//     PREVIEW_PORT=8007 python3 tools/serve-local-stack.py &        # one-off SQLite, no Telegram
//     PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright \
//     BASE_URL=http://127.0.0.1:8007 npx playwright test tests/smoke.spec.js
//
// Every lead it creates is marked is_test via the X-Test header, so the admin funnel
// stays clean and no notification is sent.
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8007';
// The origin under test, taken from BASE rather than hardcoded: the same assertions must
// hold for the local stack (http://127.0.0.1:8007) and for a public name over HTTPS.
const ORIGIN = new URL(BASE).origin;
const HOST = new URL(BASE).host;
const IS_LOCAL = ['127.0.0.1', 'localhost'].includes(new URL(BASE).hostname);
const MOBILE = { width: 390, height: 844 };
const SMALL = { width: 360, height: 800 };

async function noHorizontalScroll(page) {
  return page.evaluate(() => {
    const d = document.documentElement;
    return { scroll: d.scrollWidth, client: d.clientWidth };
  });
}

test.describe('page delivery', () => {
  test('serves over HTTPS with Hebrew RTL markup', async ({ page }) => {
    const res = await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    expect(res.status()).toBe(200);
    // No silent redirect to somewhere else, whichever origin is under test…
    expect(res.url().startsWith(ORIGIN)).toBeTruthy();
    // …and a public name still has to be HTTPS. The local stack is plain http by design:
    // it listens on 127.0.0.1 only and never holds a certificate.
    if (!IS_LOCAL) expect(res.url().startsWith('https://')).toBeTruthy();

    const html = page.locator('html');
    await expect(html).toHaveAttribute('lang', 'he');
    await expect(html).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('h1')).toBeVisible();
    await expect(page).toHaveTitle(/אלומה/);
  });

  test('legal pages resolve on clean URLs', async ({ page }) => {
    for (const path of ['/privacy', '/terms', '/accessibility', '/thanks']) {
      const res = await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
      expect(res.status(), path).toBe(200);
      await expect(page.locator('h1'), path).toBeVisible();
    }
  });

  test('a missing page returns 404, not the landing page', async ({ page }) => {
    const res = await page.goto(BASE + '/no-such-page-xyz', { waitUntil: 'domcontentloaded' });
    expect(res.status()).toBe(404);
  });

  test('admin is not reachable without signing in', async ({ page }) => {
    await page.goto(BASE + '/admin', { waitUntil: 'domcontentloaded' });
    expect(page.url()).toContain('/admin/login');
  });
});

test.describe('layout', () => {
  for (const [name, size] of [['360x800', SMALL], ['390x844', MOBILE], ['1280x900', { width: 1280, height: 900 }]]) {
    test(`no horizontal scroll at ${name}`, async ({ page }) => {
      await page.setViewportSize(size);
      await page.goto(BASE, { waitUntil: 'networkidle' });
      const { scroll, client } = await noHorizontalScroll(page);
      expect(scroll, `${name}: scrollWidth ${scroll} > clientWidth ${client}`).toBeLessThanOrEqual(client + 1);
    });
  }

  test('sticky bar appears only after the hero scrolls away', async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto(BASE, { waitUntil: 'networkidle' });
    const bar = page.locator('#sticky');
    await expect(bar).not.toHaveClass(/is-on/);
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
    await expect(bar).toHaveClass(/is-on/, { timeout: 4000 });
  });
});

test.describe('switchers', () => {
  test('size toggle changes state and the visible numbers', async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto(BASE, { waitUntil: 'networkidle' });

    await expect(page.locator('html')).toHaveAttribute('data-size', '160');
    await page.locator('input[name="size"][value="220"]').check();
    await expect(page.locator('html')).toHaveAttribute('data-size', '220');
    await expect(page.locator('.state-line [data-bind="len"]')).toHaveText('220');
    // The seat count left the state line in the page rebuild (8296742): app-next.js binds
    // len / state / oak only, and the state word is what now moves with the size.
    await expect(page.locator('.state-line [data-bind="state"]')).toHaveText('פתוח');
  });

  test('colour switcher changes the oak tone', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await page.locator('input[name="oak"][value="smoked"]').check();
    await expect(page.locator('html')).toHaveAttribute('data-oak', 'smoked');
    await expect(page.locator('.state-line [data-bind="oak"]')).toHaveText('אלון מעושן');

    // Since the rebuild (8296742) the hero is a FIXED product portrait and the tone preview
    // lives in the compare block: app-next.js setTone() → paintCompare(), and it never
    // touches #hero-img. Assert the picture that actually carries the tone.
    await expect(page.locator('#compare-img')).toHaveAttribute('data-variant', /^smoked-/);
    await expect(page.locator('#compare-img')).toHaveAttribute('src', /smoked-/);
  });

  test('switch choices reach the analytics endpoint', async ({ page }) => {
    const posted = [];
    await page.route('**/api/fx/event', async (route) => {
      posted.push(JSON.parse(route.request().postData() || '{}'));
      await route.continue();
    });
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await page.locator('input[name="oak"][value="white"]').check();
    await page.locator('input[name="size"][value="220"]').check();
    await page.waitForTimeout(3500);

    const names = posted.flatMap((p) => (p.events || []).map((e) => e.name));
    expect(names).toContain('page_view');
    expect(names).toContain('color_select');
    expect(names).toContain('size_toggle');
  });
});

test.describe('room fit', () => {
  test('gives a verdict and reports it', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    // The tool is a collapsed <details id="fit"> since the rebuild (8296742) — #roomlen is
    // in the DOM but not fillable until the disclosure is open. Same step as redesign.spec.js.
    await page.locator('#fit summary').click();
    const verdict = page.locator('#verdict');

    // Verdicts are no / closed / open now, against the two real lengths (160 and 220),
    // instead of the old tight / ok / no: app-next.js paintFit().
    await page.locator('#roomlen').fill('120');
    await expect(verdict).toHaveAttribute('data-v', 'no');

    await page.locator('#roomlen').fill('200');
    await expect(verdict).toHaveAttribute('data-v', 'closed');

    await page.locator('#roomlen').fill('460');
    await expect(verdict).toHaveAttribute('data-v', 'open');
  });
});

test.describe('lead form', () => {
  test('rejects an empty submission with readable Hebrew errors', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await page.locator('#f-submit').click();

    await expect(page.locator('#e-name')).toBeVisible();
    await expect(page.locator('#e-phone')).toBeVisible();
    await expect(page.locator('#e-consent')).toBeVisible();
    await expect(page.locator('#e-phone')).toContainText('טלפון');
    // the status line names what is missing, and the first bad field is brought on screen
    await expect(page.locator('#f-status')).toContainText('חסר');
    await expect(page.locator('#f-name')).toBeInViewport({ timeout: 4000 });
    expect(page.url()).not.toContain('/thanks');
  });

  test('rejects a non-Israeli phone number', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await page.locator('#f-name').fill('בדיקה');
    await page.locator('#f-phone').fill('12345');
    await page.locator('#f-consent').check();
    await page.locator('#f-submit').click();
    await expect(page.locator('#e-phone')).toBeVisible();
  });

  test('a valid submission is stored and lands on the thank-you screen', async ({ page }) => {
    // mark everything this run creates as test data
    await page.setExtraHTTPHeaders({ 'X-Test': '1' });
    await page.goto(BASE, { waitUntil: 'networkidle' });

    await page.locator('input[name="oak"][value="smoked"]').check();
    await page.locator('#f-name').fill('בדיקה אוטומטית');
    await page.locator('#f-phone').fill('050-123-4567');
    await page.locator('#f-city').fill('חיפה');
    await page.locator('#f-comment').fill('playwright smoke');
    await page.locator('#f-consent').check();

    // The page redirects the instant the fetch resolves, so Chromium discards the
    // response body before it can be read. Intercept and read it in the proxy.
    let captured = null;
    await page.route('**/api/fx/lead', async (route) => {
      const response = await route.fetch();
      const text = await response.text();
      captured = { status: response.status(), json: JSON.parse(text) };
      await route.fulfill({ response, body: text });
    });

    await page.locator('#f-submit').click();
    await expect.poll(() => captured, { timeout: 12000 }).not.toBeNull();
    expect(captured.status).toBe(200);
    expect(captured.json.ok).toBeTruthy();
    expect(captured.json.id).toMatch(/^[0-9a-f]{12}$/);

    await page.waitForURL('**/thanks', { timeout: 10000 });
    await expect(page.locator('h1')).toContainText('קיבלנו');
  });

  test('the honeypot swallows a bot without storing a lead', async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Test': '1' });
    await page.goto(BASE, { waitUntil: 'networkidle' });
    const res = await page.evaluate(async () => {
      const r = await fetch('/api/fx/lead', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ name: 'bot', phone: '0501234567', consent: true, website: 'x' }),
      });
      return { status: r.status, body: await r.json() };
    });
    expect(res.status).toBe(200);
    expect(res.body.id).toBe('hp');
  });
});

test.describe('accessibility basics', () => {
  test('skip link, labels, and a single h1', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    expect(await page.locator('h1').count()).toBe(1);
    await expect(page.locator('a.skip')).toHaveAttribute('href', '#main');

    for (const id of ['f-name', 'f-phone', 'f-city', 'f-comment', 'roomlen']) {
      const labelled = await page.locator(`label[for="${id}"], label:has(#${id})`).count();
      expect(labelled, `no label for #${id}`).toBeGreaterThan(0);
    }
  });

  test('keyboard focus is visible on the primary CTA', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    // :focus-visible only engages for keyboard focus, so tab there for real.
    // The WhatsApp button is hidden while WA_NUMBER is unset, so target a visible one.
    const cta = page.locator('.hero-actions .btn:visible').first();
    await page.locator('a.skip').focus();
    for (let i = 0; i < 25 && !(await cta.evaluate((el) => el === document.activeElement)); i++) {
      await page.keyboard.press('Tab');
    }
    await expect(cta).toBeFocused();
    const outline = await cta.evaluate((el) => getComputedStyle(el).outlineStyle);
    expect(outline).not.toBe('none');
  });

  test('every drawing carries a text alternative', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    const bad = await page.evaluate(() =>
      [...document.querySelectorAll('svg[role="img"]')]
        .filter((s) => !s.querySelector('title') || !s.getAttribute('aria-labelledby'))
        .map((s) => s.getAttribute('class'))
    );
    expect(bad).toEqual([]);
  });
});

test.describe('honesty guardrails', () => {
  test('no fabricated social proof anywhere on the page', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    const text = await page.locator('body').innerText();
    const banned = ['ביקורות', 'לקוחות מרוצים', 'נותרו', 'מבצע', 'הנחה', '★', 'כוכבים', 'במלאי'];
    for (const word of banned) {
      expect(text, `page must not claim "${word}"`).not.toContain(word);
    }
  });

  test('the pre-launch status is stated in the footer', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await expect(page.locator('.prelaunch')).toContainText('לפני השקה');
  });

  test('no third-party request fires before the notice is accepted', async ({ page }) => {
    const external = [];
    page.on('request', (r) => {
      // Compared against the origin under test, not a hardcoded domain: on the local stack
      // every request is 127.0.0.1:8007, and the point of the test is "nothing but us".
      const host = new URL(r.url()).host;
      if (host !== HOST) external.push(host);
    });
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    expect([...new Set(external)]).toEqual([]);
  });
});

// Regression tests for the two defects the buyer-perspective critique found.
// Both were invisible to the original suite: it asserted behaviour, not appearance.
test.describe('critique regressions', () => {
  test('the cookie notice exists only when a third-party id is configured', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    const configured = await page.evaluate(() => {
      const s = [...document.scripts].map((x) => x.src).find((x) => x.includes('app.js'));
      return fetch(s).then((r) => r.text()).then((js) => /pixel: "[^"]+"|clarity: "[^"]+"/.test(js));
    });
    const notice = page.locator('#notice');
    if (!configured) {
      // nothing third-party loads, so there is nothing to consent to — no bar at all
      await expect(notice).toHaveCount(0);
      return;
    }
    await expect(notice).toBeVisible();
    await page.locator('#notice-ok').click();
    await expect(notice).toBeHidden();
    await page.reload({ waitUntil: 'networkidle' });
    await expect(notice).toBeHidden();
  });

  test('the sticky CTA is reachable, not covered by the notice', async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto(BASE, { waitUntil: 'networkidle' });
    const ok = page.locator('#notice-ok');
    if (await ok.count()) await ok.click();
    await page.evaluate(() => window.scrollTo(0, 1400));
    await expect(page.locator('#sticky')).toHaveClass(/is-on/);

    const covered = await page.evaluate(() => {
      const btn = [...document.querySelectorAll('#sticky .btn')].find((b) => b.offsetParent !== null);
      if (!btn) return 'no visible sticky button';
      const r = btn.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return btn.contains(hit) || hit === btn ? null : (hit && hit.className) || 'nothing';
    });
    expect(covered, `sticky CTA is covered by: ${covered}`).toBeNull();

    await page.locator('#sticky .btn:visible').first().click();
    await expect(page).toHaveURL(/#form$/);
  });

  test('price and primary CTA are above the fold on a phone', async ({ page }) => {
    await page.setViewportSize(SMALL); // 360x800, the harder case
    await page.goto(BASE, { waitUntil: 'networkidle' });
    for (const sel of ['.hero-actions', '.hero .price']) {
      const top = await page.locator(sel).first().evaluate((el) => el.getBoundingClientRect().top);
      expect(top, `${sel} starts at ${Math.round(top)}px`).toBeLessThan(700);
    }
  });

  test('the room-fit tool is self-consistent and clears', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await page.locator('#fit summary').click();      // collapsed <details> since 8296742
    const input = page.locator('#roomlen');
    const verdict = page.locator('#verdict');

    // a 3.4 m wall is an ordinary Israeli living room and must not be rejected
    await input.fill('340');
    await expect(verdict).toHaveAttribute('data-v', 'open');   // was 'ok' before the rebuild

    await input.fill('150');
    await expect(verdict).toHaveAttribute('data-v', 'no');

    // 399 and 400 used to print the same clearance with opposite verdicts.
    // Read the .num span, not the first digits in the sentence — the sentence
    // opens with the literal 220.
    //
    // innerText() is a single read with no auto-retry, and app-next.js settles the tool on a
    // 450 ms timer, so the number has to be waited for: without the wait below both reads
    // returned 10 — the leftover clearance from the fill('150') above, not this answer at all.
    // The scale drawing carries the wall length it was drawn for, which is exactly that signal.
    async function clearanceFor(wall) {
      await input.fill(String(wall));
      await expect(verdict.locator('.fitbar')).toHaveAttribute('aria-label', new RegExp(`\\b${wall}\\b`));
      return Number(await verdict.locator('p .num').first().innerText());
    }
    const a = await clearanceFor(399);
    const b = await clearanceFor(400);
    expect(a).toBeLessThan(b);

    // clearing the field must clear the answer, not leave the last one standing
    await input.fill('');
    await expect(verdict).not.toHaveAttribute('data-v', /.+/);
    // The cleared state now empties #verdict outright and the standing invitation lives in
    // #fit-hint (app-next.js readFit), instead of a <strong> inside the verdict box.
    await expect(verdict).toBeEmpty();
    await expect(page.locator('#fit-hint')).toContainText('חישוב אורך בלבד');
  });

  test('no dead contact links: a WhatsApp button is either real or absent', async ({ page }) => {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    const dead = await page.evaluate(() =>
      [...document.querySelectorAll('a.js-wa')]
        .filter((a) => a.offsetParent !== null)
        .filter((a) => !(a.getAttribute('href') || '').startsWith('https://wa.me/'))
        .length
    );
    expect(dead, 'a visible WhatsApp button points at href="#"').toBe(0);
  });
});


// The English twin: same template, mirrored, with hreflang both ways.
test.describe('english page', () => {
  test('/en/ serves the LTR twin with hreflang links', async ({ page }) => {
    const res = await page.goto(BASE + '/en/', { waitUntil: 'domcontentloaded' });
    expect(res.status()).toBe(200);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
    // English h1 was rewritten in the rebuild (8296742): the model name moved to the
    // identity line above it, and the headline is the promise. i18n/en.json → hero_h1.
    await expect(page.locator('h1')).toContainText('Room for every day');
    // …so the "what is this" line above it is what now has to name the product.
    await expect(page.locator('p.identity').first()).toContainText('extending dining table');
    expect(await page.locator('link[rel="alternate"][hreflang="he"]').count()).toBe(1);
    expect(await page.locator('link[rel="alternate"][hreflang="en"]').count()).toBe(1);
    await expect(page.locator('.masthead .lang')).toHaveAttribute('href', '/');
  });

  test('/en/ legal pages exist and point back to the binding Hebrew', async ({ page }) => {
    for (const path of ['/en/privacy', '/en/terms', '/en/accessibility']) {
      const res = await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
      expect(res.status(), path).toBe(200);
      await expect(page.locator('.legal-note a[hreflang="he"]'), path).toHaveCount(1);
    }
  });

  test('the configurator swaps the compare render in English too', async ({ page }) => {
    await page.goto(BASE + '/en/', { waitUntil: 'networkidle' });
    // Same rebuild as the Hebrew twin (8296742): the tone and state preview is #compare-img,
    // the hero is a fixed portrait. data-variant is the switcher's own record of what it drew.
    await page.locator('input[name="oak"][value="white"]').check();
    await expect(page.locator('#compare-img')).toHaveAttribute('data-variant', 'white-closed');
    await page.locator('input[name="size"][value="220"]').check();
    await expect(page.locator('#compare-img')).toHaveAttribute('data-variant', 'white-open');
    await expect(page.locator('#compare-img')).toHaveAttribute('src', /white-open/);
    await expect(page.locator('.state-line [data-bind="oak"]')).toHaveText('whitewashed oak');
  });
});
