// Події для тесту в Meta: що бачить піксель і що йде в /api/fx/event та /api/fx/lead.
// Без порту й без мережі: dist/ через page.route (tests/dist_route.js), /api/fx/* підмінено тут,
// connect.facebook.net віддає підробний fbevents.js, який лише записує виклики fbq у window.__fb.
// Будь-який інший запит назовні (facebook.com/tr, clarity.ms…) обривається й рахується в `outside`.
//   python3 build.py && npx playwright test --config playwright.tracking.config.js
const { test, expect } = require('@playwright/test');
const { ORIGIN, serveDist, built } = require('./dist_route');

const PIXEL = '123456789012345';
const WA = '972500000000';
// Вигадані дані форми: шукаємо їх у кожній події — у відкритому вигляді їх не має бути ніде.
const NAME = 'Zzqx Testovy';
const PHONE = '052-987-6543';
const PII = ['Zzqx', 'Testovy', '0529876543', '529876543', '052-987-6543', '9876543', '@'];

// Підробка fbevents.js: справжній сніпет кладе виклики в fbq.queue, доки скрипт не завантажився.
const FAKE_FBEVENTS = `(function(){var f=window.fbq;window.__fb=window.__fb||[];
f.callMethod=function(){window.__fb.push(JSON.parse(JSON.stringify(Array.prototype.slice.call(arguments))))};
var q=f.queue||[];f.queue=[];q.forEach(function(a){f.callMethod.apply(f,Array.prototype.slice.call(a))});})();`;

test.skip(!built(), 'dist/ не зібрано: python3 build.py');

async function open(page, path, { consent = null, config = {}, lead = { ok: true, id: 'lead-test-1' } } = {}) {
  const net = { outside: [], fbevents: 0, events: [], leads: [] };
  await serveDist(page);
  // Пізніше зареєстрований route має пріоритет — підміняємо API й Meta поверх serveDist.
  await page.route('https://connect.facebook.net/**', (route) => {
    net.fbevents += 1;
    return route.fulfill({ status: 200, contentType: 'text/javascript', body: FAKE_FBEVENTS });
  });
  await page.route(`${ORIGIN}/api/fx/**`, (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    if (p === '/api/fx/config') {
      return route.fulfill({ json: { pixel_id: PIXEL, clarity_id: null, prelaunch: true, contact: {}, ...config } });
    }
    if (p === '/api/fx/event') { net.events.push(req.postDataJSON()); return route.fulfill({ json: { ok: true } }); }
    if (p === '/api/fx/lead') { net.leads.push(req.postDataJSON()); return route.fulfill({ json: lead }); }
    return route.fulfill({ status: 404, json: { ok: false } });
  });
  page.on('request', (req) => {
    const u = new URL(req.url());
    if (u.origin !== ORIGIN && u.hostname !== 'connect.facebook.net') net.outside.push(u.hostname + u.pathname);
  });
  if (consent !== null) {
    await page.addInitScript((v) => { try { localStorage.setItem('fx_notice_v1', v); } catch (e) {} }, consent);
  }
  await page.goto(ORIGIN + path);
  await page.waitForLoadState('load');
  return net;
}

const fbCalls = (page) => page.evaluate(() => window.__fb || []);
const tracked = async (page, name) => (await fbCalls(page)).filter((c) => c[0] === 'track' && c[1] === name);
// Перша сторона копить події 2,5 с; pagehide шле решту. Чекаємо, доки потрібна подія дійде.
const firstParty = (net, name) => net.events.flatMap((b) => b.events || []).filter((e) => e.name === name);

async function waitFb(page, name, n = 1) {
  await expect.poll(async () => (await tracked(page, name)).length, { timeout: 8000 }).toBeGreaterThanOrEqual(n);
  return tracked(page, name);
}

test.describe('без згоди на рекламу', () => {
  test('/ — банер є, fbq немає, до Meta нічого не йде', async ({ page }) => {
    const net = await open(page, '/?fbclid=FBCLIDTEST&utm_source=facebook');
    await expect(page.locator('#notice')).toBeVisible();
    await page.waitForTimeout(3200);                    // довше за чергу першої сторони (2,5 с)
    expect(net.fbevents, 'fbevents.js завантажено без згоди').toBe(0);
    expect(await page.evaluate(() => typeof window.fbq)).toBe('undefined');
    expect(net.outside, 'запит назовні').toEqual([]);
    // перша сторона пише PageView, але без рекламного ідентифікатора
    const pv = firstParty(net, 'PageView');
    expect(pv.length).toBe(1);
    for (const b of net.events) expect(b.ctx.fbclid, 'fbclid без згоди').toBe('');
  });

  test('«лише необхідні» — і після перезавантаження нічого', async ({ page }) => {
    const net = await open(page, '/');
    await page.locator('[data-notice-no]').click();
    await expect(page.locator('#notice')).toBeHidden();
    await page.reload();
    await page.waitForLoadState('load');
    await page.waitForTimeout(1500);
    await expect(page.locator('#notice')).toBeHidden();
    expect(net.fbevents).toBe(0);
    expect(await page.evaluate(() => typeof window.fbq)).toBe('undefined');
    expect(net.outside).toEqual([]);
  });

  test('заявка без згоди: ads_consent = false, Lead у Meta не йде', async ({ page }) => {
    const net = await open(page, '/p/tavor/', { consent: '0' });
    await fillAndSend(page);
    await expect.poll(() => net.leads.length).toBe(1);
    expect(net.leads[0].ads_consent).toBe(false);
    await expect(page.locator('[data-thanks]')).toBeVisible();
    expect(net.fbevents).toBe(0);
    expect(net.outside).toEqual([]);
  });
});

test.describe('після згоди', () => {
  test('/ — натиснув «אישור»: піксель вантажиться, PageView з тим самим event_id, що в першої сторони', async ({ page }) => {
    const net = await open(page, '/');
    await page.locator('[data-notice-ok]').click();
    const [pv] = await waitFb(page, 'PageView');
    expect(net.fbevents).toBe(1);
    const calls = await fbCalls(page);
    const init = calls.find((c) => c[0] === 'init');
    // init лише з id — без advanced matching (em/ph) у браузері
    expect(init).toEqual(['init', PIXEL]);
    const at = (name) => calls.findIndex((c) => c[0] === name || c[1] === name);
    expect(at('init'), 'init раніше за PageView').toBeLessThan(at('PageView'));
    expect(pv[3].eventID).toMatch(/^pv\./);
    await expect.poll(() => firstParty(net, 'PageView').length, { timeout: 8000 }).toBe(1);
    expect(firstParty(net, 'PageView')[0].props.event_id).toBe(pv[3].eventID);
    expect(net.outside).toEqual([]);
  });

  test('/en/ — повторний візит зі згодою: PageView без кліку', async ({ page }) => {
    const net = await open(page, '/en/', { consent: '1' });
    await waitFb(page, 'PageView');
    await expect(page.locator('#notice')).toBeHidden();
    expect(net.fbevents).toBe(1);
  });

  test('/p/tavor/ — ViewContent з content_ids і value в ILS', async ({ page }) => {
    await open(page, '/p/tavor/', { consent: '1' });
    const [vc] = await waitFb(page, 'ViewContent');
    const first = Number(await page.locator('input[name="size"]').first().getAttribute('data-price'));
    expect(vc[2]).toMatchObject({ content_ids: ['tavor'], content_type: 'product', currency: 'ILS', value: first });
    expect(typeof vc[2].value).toBe('number');
    expect(vc[2].value).toBeGreaterThan(0);
    expect(vc[3].eventID).toBeTruthy();
    // PageView теж є, ViewContent — один
    expect((await tracked(page, 'PageView')).length).toBe(1);
    expect((await tracked(page, 'ViewContent')).length).toBe(1);
  });

  test('/p/tavor/ — розмір і тонування: CustomizeProduct', async ({ page }) => {
    await open(page, '/p/tavor/', { consent: '1' });
    await waitFb(page, 'ViewContent');
    await page.locator('label.pill:has(input[name="size"][value="180×90"])').click();
    let [c1] = await waitFb(page, 'CustomizeProduct', 1);
    expect(c1[2]).toMatchObject({ content_ids: ['tavor'], content_type: 'product', size: '180×90' });
    const finish = page.locator('input[name="finish"][value="smoked"]');
    await page.locator('label:has(input[name="finish"][value="smoked"])').first().click();
    await expect(finish).toBeChecked();
    const all = await waitFb(page, 'CustomizeProduct', 2);
    expect(all[1][2]).toMatchObject({ content_ids: ['tavor'], size: '180×90', finish: 'smoked' });
    expect(new Set(all.map((c) => c[3].eventID)).size).toBe(2);
  });

  test('WhatsApp є в конфігу — клік дає Contact', async ({ page }) => {
    await open(page, '/p/tavor/', { consent: '1', config: { wa_number: WA } });
    await waitFb(page, 'PageView');
    const wa = page.locator('.js-wa').first();
    await expect(wa).toBeVisible();
    expect(await wa.getAttribute('href')).toContain('https://wa.me/' + WA);
    // не відкриваємо wa.me: скасовуємо перехід, обробник вітрини на document усе одно спрацьовує
    await page.evaluate(() => window.addEventListener('click', (e) => {
      if (e.target.closest && e.target.closest('.js-wa')) e.preventDefault();
    }, true));
    await wa.click();
    const [ct] = await waitFb(page, 'Contact');
    expect(ct[2]).toMatchObject({ method: 'whatsapp', content_ids: ['tavor'] });
  });

  test('WhatsApp немає в конфігу — посилання сховане', async ({ page }) => {
    await open(page, '/p/tavor/', { consent: '1' });
    await waitFb(page, 'PageView');
    for (const a of await page.locator('.js-wa').all()) await expect(a).toBeHidden();
  });

  test('успішна форма — Lead з event_id як у POST /api/fx/lead, ads_consent = true, без ПД', async ({ page }) => {
    const net = await open(page, '/p/tavor/', { consent: '1' });
    await waitFb(page, 'ViewContent');
    await fillAndSend(page);
    const [lead] = await waitFb(page, 'Lead');
    expect(net.leads.length).toBe(1);
    const body = net.leads[0];
    expect(body.event_id, 'event_id у заявці').toMatch(/^lead\./);
    expect(lead[3].eventID, 'дедуплікація з CAPI').toBe(body.event_id);
    expect(body.ads_consent).toBe(true);
    expect(lead[2]).toMatchObject({ content_ids: ['tavor'], content_type: 'product', currency: 'ILS' });
    // перша сторона — той самий event_id
    await expect.poll(() => firstParty(net, 'Lead').length, { timeout: 8000 }).toBe(1);
    expect(firstParty(net, 'Lead')[0].props.event_id).toBe(body.event_id);
    // ПД — лише в самій заявці, ніде більше
    expect(body.name).toBe(NAME);
    const leak = JSON.stringify({ fb: await fbCalls(page), events: net.events, outside: net.outside });
    for (const s of PII) expect(leak, `«${s}» у подіях`).not.toContain(s);
    expect(net.outside).toEqual([]);
  });

  test('приманка для ботів (id hp) — Lead не рахується', async ({ page }) => {
    const net = await open(page, '/p/tavor/', { consent: '1', lead: { ok: true, id: 'hp' } });
    await waitFb(page, 'ViewContent');
    await fillAndSend(page);
    await expect.poll(() => net.leads.length).toBe(1);
    await page.waitForTimeout(800);
    expect((await tracked(page, 'Lead')).length).toBe(0);
  });
});

async function fillAndSend(page) {
  const form = page.locator('#lead-form');
  await form.locator('#f-name').fill(NAME);
  await form.locator('#f-phone').fill(PHONE);
  await form.locator('input[name="consent"]').check();
  await form.locator('button[type="submit"]').click();
}
