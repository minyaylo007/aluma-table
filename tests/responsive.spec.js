// Верстка на всіх екранах: кожна сторінка he/en, ширини 320–1920, zoom 200 % і збільшений шрифт.
// Без порту: dist/ через page.route (tests/dist_route.js), API підмінено. Конфіг — playwright.responsive.config.js.
// Перевіряємо те, що на око пропускають:
//   - немає горизонтального скролу і жоден елемент не виходить за край (WCAG 1.4.10 reflow);
//   - текст не обрізано контейнером з overflow: hidden;
//   - кнопки й посилання не менші за 24×24 (WCAG 2.2, 2.5.8; інлайн-посилання в реченні — виняток стандарту);
//   - фокус видно на кожному елементі, до якого доходить Tab (2.4.7);
//   - липка кнопка на телефоні не закриває поля форми й банер cookies (2.4.11);
//   - в RTL розміри, телефон, ціни й стрілки стоять у <bdi>/dir="ltr" — інакше «160×90» читається як «90×160».
// Відомі дірки чужих зон — у KNOWN: друкуються списком, тест не червоніє; нове — червоне.
const { test, expect } = require('@playwright/test');
const { ORIGIN, pages, serveDist, built } = require('./dist_route');

const WIDTHS = [320, 360, 390, 768, 1024, 1280, 1920];
const HEIGHT = { 320: 640, 360: 740, 390: 844, 768: 1024, 1024: 768, 1280: 900, 1920: 1080 };

// Відомі дірки (21.10, master @ 5f69d04: банер cookies, 200 % тексту й .pill знято в #32). Поля: rule; where / detail — підрядки (необов'язкові);
// page — регулярний вираз шляху. Знято зоною-власником — рядок прибрати, інакше тест так і мовчатиме.
const KNOWN = [
  // розмір у тексті опису з каталогу без <bdi>
  { rule: 'bdi', where: 'p.pdp-desc', page: /^\/p\/tal\/$/, why: 'сесія 2: catalog tal.description «100×60» — обгорнути у build.py/каталозі' },
];

const isKnown = (page, p) => KNOWN.some((k) => k.rule === p.rule
  && (!k.where || p.where.includes(k.where)) && (!k.detail || p.detail.includes(k.detail)) && (!k.page || k.page.test(page)));

function report(page, title, problems) {
  const known = problems.filter((p) => isKnown(page, p));
  const fresh = problems.filter((p) => !isKnown(page, p));
  const fmt = (p) => `  ${p.rule}\t${p.where}\t${p.detail}`;
  if (known.length) console.log(`KNOWN ${title}\n` + known.map(fmt).join('\n'));
  if (fresh.length) console.log(`NEW ${title}\n` + fresh.map(fmt).join('\n'));
  return fresh.map((p) => `${p.rule} ${p.where} ${p.detail}`);
}

// Усе вимірювання — в одній функції сторінки, щоб не ганяти сотні round-trip під навантаженням машини.
function audit(opts) {
  const out = [];
  const vw = document.documentElement.clientWidth;
  const desc = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    const cls = [...el.classList].slice(0, 2).join('.');
    if (cls) s += '.' + cls;
    const txt = (el.getAttribute('aria-label') || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 24);
    return txt ? `${s} «${txt}»` : s;
  };
  const shown = (el) => {
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) return false;
    if (el.closest('[hidden], [aria-hidden="true"], .sr-only, .visually-hidden')) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;              // 1×1 — текст лише для читача екрана (.sr)
  };
  // предок, що сам гортає або обрізає по горизонталі — тоді вихід за край не видно сторінці
  const clippedBy = (el) => {
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const ox = getComputedStyle(a).overflowX;
      if (ox !== 'visible') return a;
    }
    return null;
  };
  const fixedOffscreen = (el) => {
    for (let a = el; a; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if (cs.position === 'fixed' && cs.transform !== 'none') return true;  // липка кнопка до появи
    }
    return false;
  };

  const sw = document.documentElement.scrollWidth;
  if (sw > vw + 1) out.push({ rule: 'hscroll', where: 'html', detail: `scrollWidth ${sw} > ${vw}` });

  for (const el of document.body.querySelectorAll('*')) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'BR'].includes(el.tagName)) continue;
    if (!shown(el) || el.closest('svg') && el.tagName !== 'svg') continue;
    const r = el.getBoundingClientRect();
    if ((r.right > vw + 1 || r.left < -1) && !clippedBy(el) && !fixedOffscreen(el)) {
      out.push({ rule: 'edge', where: desc(el), detail: `x ${Math.round(r.left)}…${Math.round(r.right)} / ${vw}` });
    }
    // обрізаний текст: контейнер з власним текстом, overflow не visible, вміст ширший
    const cs = getComputedStyle(el);
    const ownText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (ownText && cs.overflowX !== 'visible' && cs.textOverflow !== 'ellipsis' && el.scrollWidth > el.clientWidth + 1
        && !['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) {
      out.push({ rule: 'clipped', where: desc(el), detail: `${el.scrollWidth} > ${el.clientWidth}` });
    }
  }

  // цілі натискання ≥ 24×24 (2.5.8): інлайн-посилання серед тексту — виняток; мала ціль без сусідів у колі 24 — теж
  const targets = [...document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, [role=button], summary')]
    .filter((el) => shown(el) && !fixedOffscreen(el));
  const rects = targets.map((el) => {
    // прапорець/радіо всередині label або з label[for] — ціль і є label
    if (el.matches('input[type=checkbox], input[type=radio]')) {
      const lab = el.closest('label') || (el.id && document.querySelector(`label[for="${el.id}"]`));
      if (lab) return lab.getBoundingClientRect();
    }
    return el.getBoundingClientRect();
  });
  targets.forEach((el, i) => {
    const r = rects[i];
    if (r.width >= 24 - 0.5 && r.height >= 24 - 0.5) return;
    if (el.tagName === 'A' && getComputedStyle(el).display === 'inline') {
      const block = el.parentElement;
      const txt = [...block.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
      if (txt.length > 0) return;                       // посилання в реченні
    }
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const near = rects.some((o, j) => j !== i && !targets[j].contains(el) && !el.contains(targets[j])
      && Math.max(o.left - cx, 0, cx - o.right) ** 2 + Math.max(o.top - cy, 0, cy - o.bottom) ** 2 < 12 * 12);
    if (near) out.push({ rule: 'target', where: desc(el), detail: `${Math.round(r.width)}×${Math.round(r.height)}` });
  });

  // RTL: розміри, телефон, ціни, стрілки поза <bdi>/dir=ltr
  if (opts.rtl) {
    const RISKY = /\d\s*[×x→←\/]\s*\d|\+\d{3}|\d{2,}-\d{3,}|₪\s*\d|\d\s*₪|Ø\s*\d/;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const p = n.parentElement;
      if (!p || p.closest('script, style, svg, bdi, [dir=ltr], [hidden], noscript')) continue;
      const m = n.textContent.match(RISKY);
      if (m && shown(p)) out.push({ rule: 'bdi', where: desc(p), detail: `«${m[0]}»` });
    }
  }
  return out;
}

async function settle(page) {
  await page.evaluate(() => document.fonts && document.fonts.ready);
  // №39: глави картки під спойлерами — міряємо їх відкритими, як їх бачить читач
  await page.evaluate(() => document.querySelectorAll('details[data-acc]').forEach((d) => { d.open = true; }));
  await page.waitForTimeout(150);
}

test.skip(!built(), 'спершу python3 build.py');

const dedupe = (ps) => [...new Map(ps.map((p) => [`${p.rule}|${p.where}`, p])).values()];

for (const pagePath of pages()) {
  const rtl = !/^\/(en|ru)\//.test(pagePath);           // ltr-мови мають свій префікс

  test(`ширини ${pagePath}`, async ({ page }) => {
    await serveDist(page);
    const all = [];
    for (const w of WIDTHS) {
      await page.setViewportSize({ width: w, height: HEIGHT[w] });
      if (w === WIDTHS[0]) await page.goto(ORIGIN + pagePath, { waitUntil: 'load' });
      await settle(page);
      for (const p of await page.evaluate(audit, { rtl: rtl && w === 390 })) all.push({ ...p, detail: `${p.detail} @${w}` });
    }
    expect(report(pagePath, `ширини ${pagePath}`, dedupe(all)), pagePath).toEqual([]);
  });

  // zoom 200 % на ноутбуці 1280 = вікно 640 CSS px; і 200 % тексту (1.4.4) на телефоні 390
  test(`zoom 200 % і шрифт ${pagePath}`, async ({ page }) => {
    await serveDist(page);
    const all = [];
    await page.setViewportSize({ width: 640, height: 450 });
    await page.goto(ORIGIN + pagePath, { waitUntil: 'load' });
    await settle(page);
    for (const p of await page.evaluate(audit, { rtl: false })) all.push({ ...p, detail: `${p.detail} @zoom200` });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.addStyleTag({ content: 'html { font-size: 200% !important; }' });
    await settle(page);
    for (const p of await page.evaluate(audit, { rtl: false })) {
      if (p.rule !== 'target') all.push({ ...p, detail: `${p.detail} @font200` });
    }
    expect(report(pagePath, `zoom ${pagePath}`, dedupe(all)), pagePath).toEqual([]);
  });

  // фокус: Tab по всій сторінці на телефоні, у кожного елемента видимий індикатор
  test(`фокус ${pagePath}`, async ({ page }) => {
    await serveDist(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(ORIGIN + pagePath, { waitUntil: 'load' });
    await settle(page);
    await page.evaluate(() => { const n = document.getElementById('notice'); if (n) n.hidden = true; });
    const total = await page.evaluate(() => document.querySelectorAll('a[href], button, input, select, textarea, summary, [tabindex]').length);
    const problems = [];
    const seen = new Set();
    for (let i = 0; i < Math.min(total + 5, 150); i++) {
      await page.keyboard.press('Tab');
      const probe = () => page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body) return { body: true };
        const cs = getComputedStyle(el);
        const outline = cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0;
        const ring = cs.boxShadow && cs.boxShadow !== 'none';
        const r = el.getBoundingClientRect();
        const id = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + ([...el.classList][0] ? '.' + [...el.classList][0] : '')
          + ' «' + (el.getAttribute('aria-label') || el.textContent || el.name || '').trim().replace(/\s+/g, ' ').slice(0, 24) + '»';
        return { id, visible: outline || ring, inView: r.bottom > 0 && r.top < innerHeight && r.width > 0 };
      });
      let f = await probe();
      if (!f.body && !f.inView) { await page.waitForTimeout(600); f = await probe(); }   // плавна прокрутка до елемента
      if (f.body) break;                               // після останнього елемента фокус іде з документа — коло скінчилось
      if (seen.has(f.id) && i > 3) break;               // коло замкнулось
      seen.add(f.id);
      if (!f.visible) problems.push({ rule: 'focus', where: f.id, detail: 'немає outline/box-shadow' });
      else if (!f.inView) problems.push({ rule: 'focus-offscreen', where: f.id, detail: 'фокус поза екраном' });
    }
    expect(report(pagePath, `фокус ${pagePath}`, dedupe(problems)), pagePath).toEqual([]);
  });
}

// Липка кнопка (телефон): не накриває поле форми у фокусі і банер cookies
for (const pagePath of ['/', '/en/', '/ru/', '/p/tavor/', '/en/p/tavor/', '/ru/p/tavor/']) {
  for (const w of [320, 390]) {
    test(`липка кнопка ${pagePath} @${w}`, async ({ page }) => {
      await serveDist(page);
      await page.setViewportSize({ width: w, height: HEIGHT[w] });
      await page.goto(ORIGIN + pagePath, { waitUntil: 'load' });
      await settle(page);
      await page.mouse.wheel(0, 900);
      await page.waitForTimeout(400);
      const problems = await page.evaluate(() => {
        const out = [];
        const bar = document.querySelector('[data-sticky]');
        const notice = document.getElementById('notice');
        const on = (el) => el && !el.hidden && getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().top < innerHeight - 1;
        const hit = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
        if (on(bar) && on(notice) && hit(bar.getBoundingClientRect(), notice.getBoundingClientRect())) {
          out.push({ rule: 'sticky-notice', where: 'div.notice', detail: 'липка кнопка під/над банером cookies' });
        }
        return out;
      });
      // кожне поле форми: фокус → не під липкою кнопкою й не під банером
      const fields = page.locator('#lead-form input:not([type=hidden]):not([name=website]), #lead-form select, #lead-form textarea, #lead-form button[type=submit]');
      const n = await fields.count();
      for (let i = 0; i < n; i++) {
        await fields.nth(i).focus();
        await page.waitForTimeout(350);
        const measure = () => fields.nth(i).evaluate((el) => {
          const box = (el.matches('input[type=checkbox]') && el.closest('label') || el).getBoundingClientRect();
          const covers = [];
          for (const sel of ['[data-sticky]', '#notice']) {
            const o = document.querySelector(sel);
            if (!o || o.hidden || getComputedStyle(o).display === 'none') continue;
            const b = o.getBoundingClientRect();
            if (b.top >= innerHeight - 1) continue;
            const overlap = Math.min(box.bottom, b.bottom) - Math.max(box.top, b.top);
            if (overlap > 2 && box.left < b.right && b.left < box.right) covers.push(`${sel} ${Math.round(overlap)}px`);
          }
          return { name: el.name || el.type, covers };
        });
        let r = await measure();
        // липка кнопка ховається, коли форма на екрані (кадр + transition .3s) — під навантаженням чекаємо довше
        if (r.covers.length) { await page.waitForTimeout(900); r = await measure(); }
        for (const c of r.covers) problems.push({ rule: c.startsWith('#notice') ? 'notice-field' : 'sticky-field', where: `поле ${r.name}`, detail: c });
      }
      expect(report(pagePath, `липка ${pagePath} @${w}`, dedupe(problems)), pagePath).toEqual([]);
    });
  }
}

// №23: пара кнопок картки («у кошик» + «є питання? передзвонимо») — рівно на 390/768/1440 у he/en/ru:
// текст не вилазить за кнопку, кнопка — за колонку покупки, у ряд — одна висота й один верх, стовпчиком — одна ширина
for (const pagePath of ['/p/tavor/', '/en/p/tavor/', '/ru/p/tavor/']) {
  for (const w of [390, 768, 1440]) {
    test(`пара кнопок ${pagePath} @${w}`, async ({ page }) => {
      await serveDist(page);
      await page.setViewportSize({ width: w, height: 900 });
      await page.goto(ORIGIN + pagePath, { waitUntil: 'load' });
      await settle(page);
      const problems = await page.evaluate(() => {
        const out = [];
        const col = document.querySelector('.pdp-buy').getBoundingClientRect();
        const btns = [...document.querySelectorAll('.pdp-pair .btn')];
        if (btns.length !== 2) out.push({ rule: 'pair', where: '.pdp-pair', detail: `кнопок ${btns.length}` });
        const rs = btns.map((b) => b.getBoundingClientRect());
        btns.forEach((b, i) => {
          const t = (b.textContent || '').trim().slice(0, 24);
          if (b.scrollWidth > b.clientWidth + 1) out.push({ rule: 'pair-text', where: t, detail: `${b.scrollWidth} > ${b.clientWidth}` });
          if (rs[i].left < col.left - 1 || rs[i].right > col.right + 1) {
            out.push({ rule: 'pair-col', where: t, detail: `x ${Math.round(rs[i].left)}…${Math.round(rs[i].right)} / ${Math.round(col.left)}…${Math.round(col.right)}` });
          }
        });
        if (rs.length === 2) {
          const row = Math.abs(rs[0].top - rs[1].top) < 1;
          if (row && Math.abs(rs[0].height - rs[1].height) > 1) out.push({ rule: 'pair-level', where: '.pdp-pair', detail: `висоти ${Math.round(rs[0].height)} / ${Math.round(rs[1].height)}` });
          if (!row && Math.abs(rs[0].width - rs[1].width) > 1) out.push({ rule: 'pair-level', where: '.pdp-pair', detail: `ширини ${Math.round(rs[0].width)} / ${Math.round(rs[1].width)}` });
        }
        return out;
      });
      expect(report(pagePath, `пара ${pagePath} @${w}`, problems), pagePath).toEqual([]);
    });
  }
}
