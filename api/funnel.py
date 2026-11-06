"""Воронка магазину (specs/003-shop-funnel): одне вікно і одні кроки для /admin/funnel,
tools/funnel_report.py і scripts/daily_report.py.

Вікно — календарні дні Asia/Jerusalem: days=1 — сьогодні, 7 — сьогодні і шість днів до, 0 — усе.
День події — за серверним часом запису (початок sk), а не за годинником браузера.
Тут лише рахунок: жодного імені, телефону чи тексту заявки на виході.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

# міні-форма «התקשרו אלינו» (№20): як людина хоче — дзвінок, відео, деталі (той самий список, що в handler.py)
CALLBACK_PREFS = ("call", "video", "info")

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        TZ = ZoneInfo("Asia/Jerusalem")
    except ZoneInfoNotFoundError:  # Windows без tzdata: без літнього часу, на годину біля півночі
        TZ = timezone(timedelta(hours=2))
except ImportError:  # pragma: no cover
    TZ = timezone(timedelta(hours=2))

ALL_DAYS_SPAN = 120   # «усе» = стільки днів назад; події живуть 180 днів, звіт довше не потрібен

# (ключ, подія, підпис he, підпис ru) — порядок кроків воронки
STEPS = (
    ("sessions", None, "ביקורים", "сессии"),
    ("product", "ViewContent", "כרטיס מוצר", "карточка"),
    ("cart", "AddToCart", "הוספה לסל", "корзина"),
    ("checkout", "InitiateCheckout", "לחצו „לתשלום”", "«לתשלום»"),
    ("payment", "reach_payment", "מסך תשלום", "экран оплаты"),
    ("lead", "Lead", "השאירו טלפון", "Lead"),
)
STEP_KEYS = tuple(s[0] for s in STEPS)
STEP_OF_EVENT = {s[1]: s[0] for s in STEPS if s[1]}
# №42: крок «корзина» — лише AddToCart. Захід на сторінку кошика (view_cart) рахується окремо, «з товаром / порожня»:
# раніше він ішов у крок, і 14 сесій, що відкрили лише порожній кошик через кнопку «סל» у шапці, роздували крок удвічі.
TIMED = ("leave", "pulse")             # події з часом на сторінці: уход і пульс кожні 15 с (shop.js)
PRELOAD_SECONDS = (28, 34)             # пік без прокрутки — схоже на передзавантаження застосунком Facebook (зріз 06.11)
ENGAGED_SECONDS, ENGAGED_SCREENS = 20, 0.5   # «залучені»: від 20 с і від половини екрана, як у зрізі
ORDER_SOURCE = "order"                 # №41: форма замовлення на картці
LANGS = ("he", "en", "ru")             # мова сторінки (<html lang>); решта — «?»

# Реклама Meta (хвиля 1, 22.10): після запуску кампанії 22.10 14:19 за годину прийшло 44 «сесії» з utm_source=facebook
# без браузера застосунку — це перевірка оголошень роботами Meta, не люди. Людина з реклами приходить із fbclid
# у посиланні (tracking.js шле fbclid_present 1/0 — сам ідентифікатор лише за згоди) або з браузера застосунку.
AD_SOURCES = ("facebook", "instagram", "fb", "ig", "meta")
APP_UA = re.compile(r"FBAN|FBAV|Instagram")
# (ключ, підпис ru) — розріз рекламних сесій; «оцінка» — події до прапорця fbclid_present (до хвилі 1): лише за UA
AUDIENCE = (
    ("ads_people", "реклама: люди"),
    ("ads_meta", "реклама: проверка Meta"),
    ("ads_meta_est", "реклама: проверка Meta (оценка)"),
)
AUDIENCE_RU = dict(AUDIENCE)


def lang_of(row: dict) -> str:
    lang = str(row.get("lang") or "")[:2].lower()
    return lang if lang in LANGS else "?"


# --------------------------------------------------------------------------- вікно


def window_start(days: int, now: datetime | None = None) -> datetime | None:
    """Початок вікна (aware, UTC) — північ Asia/Jerusalem (days−1) днів тому. days≤0 — None (усе)."""
    if days <= 0:
        return None
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(TZ)
    first = (local - timedelta(days=days - 1)).date()
    midnight = datetime(first.year, first.month, first.day, tzinfo=TZ)
    return midnight.astimezone(timezone.utc)


def utc_partitions(days: int, now: datetime | None = None) -> list[str]:
    """UTC-дні (D#<день>), які покривають вікно, від старшого до сьогодні."""
    now = now or datetime.now(timezone.utc)
    start = window_start(days, now)
    first = start.date() if start else (now - timedelta(days=ALL_DAYS_SPAN - 1)).date()
    last = now.astimezone(timezone.utc).date()
    out, d = [], first
    while d <= last:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def _parse(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(ts or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def server_time(row: dict) -> datetime | None:
    """Серверний час рядка події: sk = '<iso>#<id>'; старі рядки без sk — ts."""
    sk = str(row.get("sk") or "")
    return _parse(sk.split("#", 1)[0]) if sk else _parse(row.get("ts"))


def in_window(dt: datetime | None, start: datetime | None) -> bool:
    return dt is not None and (start is None or dt >= start)


def local_day(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%Y-%m-%d")


def events_in_window(rows, days: int, now: datetime | None = None):
    start = window_start(days, now)
    return [r for r in rows if in_window(server_time(r), start)]


def leads_in_window(rows, days: int, now: datetime | None = None):
    start = window_start(days, now)
    return [r for r in rows if in_window(_parse(r.get("ts")), start)]


# --------------------------------------------------------------------------- розрахунок


def props(e: dict) -> dict:
    try:
        p = json.loads(e.get("props_json") or "{}")
        return p if isinstance(p, dict) else {}
    except Exception:
        return {}


def _ids(p: dict) -> list[str]:
    ids = p.get("content_ids")
    if isinstance(ids, str):
        ids = [ids]
    return [str(i)[:40] for i in ids or [] if i] if isinstance(ids, (list, tuple, str)) else []


def _num(v) -> int | None:
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 1_000_000 else None


def _steps(sessions_by_step: dict) -> list[dict]:
    """Список кроків з % від попереднього і від першого."""
    out, first, prev = [], None, None
    for key, _ev, he, ru in STEPS:
        n = len(sessions_by_step.get(key, ()))
        first = n if first is None else first
        out.append({"key": key, "he": he, "ru": ru, "n": n,
                    "of_prev": _pct(n, prev), "of_first": _pct(n, first)})
        prev = n
    return out


def _pct(a: int, b: int | None) -> int | None:
    return round(100.0 * a / b) if b else None


def _quant(v: list, q: float) -> float:
    """Квантиль за найближчим рангом (без інтерполяції) — той самий спосіб, що й медіана секунд."""
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * q))]


def depth(values: list) -> dict | None:
    """Глибина в екранах (scroll_px / vh): медіана, q75, n — округлено до 0,1. Порожньо → None."""
    if not values:
        return None
    return {"median": round(_quant(values, .5), 1), "q75": round(_quant(values, .75), 1), "n": len(values)}


def _flag(v) -> int | None:
    """fbclid_present із події: 1 / 0, None — подія старша за прапорець (до хвилі 1)."""
    if v is None or v == "":
        return None
    return 1 if v in (1, True, "1", "true") else 0


def audience(events, leads=()) -> dict:
    """Сесія рекламного джерела → ads_people / ads_meta / ads_meta_est. Інші сесії сюди не потрапляють.

    Людина: fbclid у посиланні (fbclid_present=1 або збережений fbclid), браузер застосунку (FBAN/FBAV/Instagram)
    або заявка. Решта — перевірка Meta; якщо жодна подія сесії не несла прапорця — це оцінка лише за UA."""
    src, people, flagged = {}, set(), set()
    for e in sorted(events, key=lambda e: str(e.get("sk") or e.get("ts") or "")):
        sid = e.get("session_id") or ""
        if not sid or sid == "anon":
            continue
        src.setdefault(sid, str(e.get("utm_source") or "").lower())
        f = _flag(e.get("fbclid_present"))
        if f is not None:
            flagged.add(sid)
        if f == 1 or e.get("fbclid") or APP_UA.search(str(e.get("user_agent") or "")) or e.get("event_name") == "Lead":
            people.add(sid)
    people |= {l.get("session_id") for l in leads if l.get("session_id")}
    return {sid: "ads_people" if sid in people else "ads_meta" if sid in flagged else "ads_meta_est"
            for sid, s in src.items() if s in AD_SOURCES}


def compute(events, leads) -> dict:
    """Воронка за вже відібраними (вікно, без тестових) подіями й заявками. Лише лічильники."""
    events = sorted(events, key=lambda e: str(e.get("sk") or e.get("ts") or ""))
    total = defaultdict(set)
    by_product = defaultdict(lambda: defaultdict(set))
    by_source = defaultdict(lambda: defaultdict(set))
    by_day = defaultdict(lambda: defaultdict(set))
    by_lang = defaultdict(lambda: defaultdict(set))   # мова — за першою подією сесії, як і джерело
    source_of, lang_by_sid, last_step = {}, {}, {}
    price_points = defaultdict(lambda: defaultdict(set))   # (slug, size, ₪) → крок → сесії
    cart_price = {}                                          # сесія → (slug, size, ₪) останнього AddToCart
    leaves = Counter()
    asks = defaultdict(set)                                  # м'який крок картки: cta → сесії з cta_ask
    calls = defaultdict(set)                                 # «התקשרו אלינו» (24.10): cta → сесії з cta_call
    seen = {"see_price_block": set(), "see_sizes": set()}     # №32: хто дійшов до «מה כלול במחיר» і плиток розмірів
    visits = defaultdict(set)                                # №30 «לראות מקרוב»: cta → сесії з cta_visit
    cart_views = {}                                          # №42: сесія → чи бачила кошик із товаром (num_items > 0)
    views = {}                                               # №42: (сесія, крок, товар) → найбільші секунди / px, vh, пристрій
    order_open = set()                                       # №41: відкрили форму замовлення на картці
    form_start = defaultdict(set)                            # №41: форма → сесії, що почали заповнювати
    form_error = Counter()                                   # №41: (форма, код) → помилок

    for e in events:
        sid = e.get("session_id") or ""
        if not sid or sid == "anon":
            continue
        if sid not in source_of:
            source_of[sid] = f"{e.get('utm_source') or 'direct'} / {e.get('utm_campaign') or '—'}"
        src = source_of[sid]
        lang = lang_by_sid.setdefault(sid, lang_of(e))
        dt = server_time(e)
        day = local_day(dt) if dt else "?"
        name = e.get("event_name") or ""
        p = props(e)
        for bucket in (total, by_source[src], by_day[day], by_lang[lang]):
            bucket["sessions"].add(sid)
        step = STEP_OF_EVENT.get(name)
        if name == "leave":
            leaves[str(p.get("step") or "other")[:20]] += 1
        if name in TIMED:
            # №42: час перегляду — найбільший із уходу й пульсів; вбудований браузер iOS уходу не шле, пульс — так
            st = str(p.get("step") or "other")[:20]
            key = (sid, st, str(p.get("product") or "")[:40] if st in ("pdp", "next") else "")
            v = views.setdefault(key, {"s": None, "px": 0, "vh": 0, "dev": "mobile", "leave": False})
            s, px, vh = _num(p.get("seconds")), _num(p.get("scroll_px")), _num(p.get("vh"))
            if s is not None and (v["s"] is None or s > v["s"]):
                v["s"] = s
            # №15: scroll_px — найглибша позиція в px, vh — висота екрана
            v["px"] = max(v["px"], px or 0)
            v["vh"] = vh or v["vh"]
            v["dev"] = "desktop" if e.get("device") == "desktop" else v["dev"]
            v["leave"] = v["leave"] or name == "leave"
        if name == "view_cart":
            cart_views[sid] = cart_views.get(sid, False) or (_num(p.get("num_items")) or 0) > 0
        if name == "order_open":
            order_open.add(sid)
        if name == "form_start":
            form_start[str(p.get("form") or "other")[:20]].add(sid)
        if name == "form_error":
            form_error[(str(p.get("form") or "other")[:20], str(p.get("code") or "?")[:30])] += 1
        if name == "cta_ask":
            asks[str(p.get("cta") or "other")[:20]].add(sid)
        if name == "cta_call":
            calls[str(p.get("cta") or "other")[:20]].add(sid)
        if name in seen:
            seen[name].add(sid)
        if name == "cta_visit":
            visits[str(p.get("cta") or "other")[:20]].add(sid)
        if not step:
            continue
        for bucket in (total, by_source[src], by_day[day], by_lang[lang]):
            bucket[step].add(sid)
        for pid in _ids(p):
            by_product[pid][step].add(sid)
        if STEP_KEYS.index(step) > STEP_KEYS.index(last_step.get(sid, "sessions")):
            last_step[sid] = step
        if name == "AddToCart":
            ids = _ids(p)
            price = _num(p.get("price") if p.get("price") is not None else p.get("value"))
            if ids and price is not None:
                cart_price[sid] = (ids[0], str(p.get("size") or "")[:40], price)
        if sid in cart_price and step in ("cart", "checkout", "payment", "lead"):
            price_points[cart_price[sid]][step].add(sid)

    # Заявка без події Lead у браузері (блокувальник, обірвана сторінка) — теж Lead своєї сесії.
    lead_rows = callbacks = visit_leads = order_leads = 0
    votes = Counter()                                        # №22: «אני רוצה כזה» — голоси за варіанти наступного видання
    call_prefs = Counter({k: 0 for k in CALLBACK_PREFS})
    for l in leads:
        lead_rows += 1
        if l.get("lead_source") == "callback":
            callbacks += 1
            # №20: як людина хоче — заявки до 25.10 без поля рахуються як дзвінок
            call_prefs[l.get("contact_pref") if l.get("contact_pref") in CALLBACK_PREFS else "call"] += 1
        if l.get("lead_source") == "visit":
            visit_leads += 1
        if l.get("lead_source") == ORDER_SOURCE:
            order_leads += 1
        if l.get("lead_source") == "vote":
            votes[str(l.get("product_id") or "?")[:40]] += 1
        sid = l.get("session_id") or ""
        if not sid:
            continue
        lang = lang_by_sid.get(sid) or lang_of(l)
        # джерело — сесії, якщо її події є; інакше utm самої заявки. Множини sid: з подією Lead — не двічі
        src = source_of.get(sid) or f"{l.get('utm_source') or 'direct'} / {l.get('utm_campaign') or '—'}"
        for bucket in (total, by_lang[lang], by_source[src]):
            bucket["lead"].add(sid)
            bucket["sessions"].add(sid)
        last_step[sid] = "lead"
        if l.get("product_id"):
            by_product[str(l["product_id"])[:40]]["lead"].add(sid)
        if sid in cart_price:
            price_points[cart_price[sid]]["lead"].add(sid)

    for pid, steps in by_product.items():   # у розрізі товару «сесії» = ті, хто бачив товар
        steps["sessions"] = set().union(*steps.values())

    def table(groups, order=None):
        keys = order or sorted(groups, key=lambda k: -len(groups[k]["sessions"]))
        return [{"key": k, "steps": _steps(groups[k])} for k in keys]

    # №42: час — по переглядах (сесія, крок, товар); пік 28–34 с без прокрутки на картці — не в медіані
    seconds = defaultdict(list)
    card_seconds = defaultdict(list)                         # №22: товар → секунди на картці (pdp / next)
    pdp_depth = defaultdict(list)                            # mobile/desktop → глибина картки в екранах
    pdp_timed, preload, engaged, pulse_only = set(), set(), set(), set()
    for (sid, st, product), v in views.items():
        s = v["s"]
        screens = v["px"] / v["vh"] if v["px"] > 0 and v["vh"] > 0 else 0.0
        if st == "pdp" and screens > 0:
            pdp_depth[v["dev"]].append(screens)
        if s is None:
            continue
        if st == "pdp":
            pdp_timed.add(sid)
            if not v["leave"]:
                pulse_only.add(sid)
            if screens >= ENGAGED_SCREENS and s >= ENGAGED_SECONDS:
                engaged.add(sid)
            if PRELOAD_SECONDS[0] <= s <= PRELOAD_SECONDS[1] and v["px"] == 0:
                preload.add((sid, product))
                continue
        seconds[st].append(s)
        if st in ("pdp", "next") and product:
            card_seconds[product].append(s)
    pdp_s = sorted(seconds["pdp"])

    dropped = Counter(last_step.get(sid, "sessions") for sid in total["sessions"]
                      if last_step.get(sid) not in (None, "lead"))
    return {
        "steps": _steps(total),
        "lead_rows": lead_rows,
        "by_product": table(by_product),
        "by_source": table(by_source),
        "by_day": table(by_day, order=sorted(by_day)),
        "by_lang": table(by_lang, order=[k for k in (*LANGS, "?") if k in by_lang]),
        "dropped_after": [{"step": k, "n": dropped.get(k, 0)} for k in STEP_KEYS[1:-1]],
        "leave_by_step": dict(leaves.most_common()),
        # «вопрос с карточки» поруч із кошиком: не крок воронки (шлях не обов'язковий), а окремий лічильник сесій
        "ask": {"sessions": len(set().union(*asks.values())) if asks else 0,
                "by_cta": {k: len(v) for k, v in sorted(asks.items(), key=lambda kv: (-len(kv[1]), kv[0]))}},
        # кнопка дзвінка: сесії з натисканням і заявки з міні-форми (lead_source=callback)
        "call": {"sessions": len(set().union(*calls.values())) if calls else 0,
                 "by_cta": {k: len(v) for k, v in sorted(calls.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
                 "leads": callbacks, "by_pref": {k: call_prefs[k] for k in CALLBACK_PREFS}},
        # №32: видимість блоків картки — сесії, що дійшли до «מה כלול במחיר» (3,4 екрана нижче ціни; сама ціна —
        # на першому екрані в усіх) і до плиток розмірів, проти сесій картки. Ключ "price" — історичний, це блок
        "seen": {"price": len(seen["see_price_block"]), "sizes": len(seen["see_sizes"]), "product": len(total["product"])},
        # №42: захід на сторінку кошика — окремо від кроку «корзина» (AddToCart)
        "cart_view": {"sessions": len(cart_views), "with_items": sum(1 for v in cart_views.values() if v),
                      "empty": sum(1 for v in cart_views.values() if not v),
                      "no_add": sum(1 for sid, v in cart_views.items() if v and sid not in total["cart"])},
        # №42: час на картці. timed — сесії картки з часом (уход або пульс), pulse_only — лише з пульсом,
        # preload — перегляди 28–34 с без прокрутки (не в медіані), engaged — від 20 с і від пів екрана
        "pdp_time": {"product": len(total["product"]), "timed": len(pdp_timed), "pulse_only": len(pulse_only),
                     "no_time": len(total["product"] - pdp_timed), "preload": len(preload),
                     "engaged": len(engaged), "median": pdp_s[len(pdp_s) // 2] if pdp_s else None, "n": len(pdp_s)},
        # №41: форма замовлення на картці — відкрили, почали заповнювати (за формами), помилки (форма, код), заявки
        "order": {"open": len(order_open), "leads": order_leads,
                  "form_start": {k: len(v) for k, v in sorted(form_start.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
                  "form_error": {f"{f}:{c}": n for (f, c), n in sorted(form_error.items(), key=lambda kv: (-kv[1], kv[0]))}},
        # №30: хочуть подивитись живцем — сесії з натисканням плитки і заявки lead_source=visit
        "visit": {"sessions": len(set().union(*visits.values())) if visits else 0,
                  "by_cta": {k: len(v) for k, v in sorted(visits.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
                  "leads": visit_leads},
        # голоси — окремим рядком, не замовлення: заявки lead_source=vote за товаром
        "vote": {"leads": sum(votes.values()), "by_product": dict(sorted(votes.items(), key=lambda kv: (-kv[1], kv[0])))},
        "median_seconds": {k: sorted(v)[len(v) // 2] for k, v in seconds.items() if v},
        # час на картці кожного товару (варіанти наступного видання проти TAVOR): медіана секунд і n
        "card_seconds": {k: {"median": sorted(v)[len(v) // 2], "n": len(v)} for k, v in sorted(card_seconds.items())},
        # глибина картки товару в екранах: лише агрегати (медіана, q75, n), без сесій
        "pdp_depth": {d: depth(pdp_depth.get(d)) for d in ("mobile", "desktop")},
        "price_points": [
            {"product": k[0], "size": k[1], "price": k[2],
             **{s: len(price_points[k].get(s, ())) for s in ("cart", "checkout", "payment", "lead")}}
            for k in sorted(price_points, key=lambda k: (k[0], k[2], k[1]))
        ],
    }


def report(events, leads, days: int, *, include_test: bool = False, now: datetime | None = None,
           people_only: bool = False) -> dict:
    """Вікно + фільтр тестових + compute(). events/leads — сирі рядки з таблиць.
    people_only — кроки й розрізи лише людей: сесії перевірки Meta відкинуто, їх число лишається в by_audience."""
    if not include_test:
        events = [e for e in events if not e.get("is_test")]
        leads = [l for l in leads if not l.get("is_test")]
    events, leads = events_in_window(events, days, now), leads_in_window(leads, days, now)
    aud = audience(events, leads)
    kept = [e for e in events if aud.get(e.get("session_id") or "") not in ("ads_meta", "ads_meta_est")] \
        if people_only else events
    out = compute(kept, leads)
    out["by_audience"] = [{"key": k, "ru": ru, "n": sum(1 for v in aud.values() if v == k)} for k, ru in AUDIENCE]
    out["people_only"] = people_only
    start = window_start(days, now)
    out["window"] = {"days": days, "tz": "Asia/Jerusalem",
                     "from": start.astimezone(TZ).isoformat(timespec="minutes") if start else "",
                     "include_test": include_test}
    return out


def text(rep: dict) -> str:
    """Той самий звіт простим текстом (tools/funnel_report.py)."""
    w = rep["window"]
    lines = [f"Воронка ALUMA · окно {w['days'] or 'всё'} дн. (Asia/Jerusalem"
             f"{', с ' + w['from'] if w['from'] else ''}){' · с тестовыми' if w['include_test'] else ''}", ""]

    def steps_line(steps):
        return " → ".join(f"{s['ru']} {s['n']}" + (f" ({s['of_prev']}%)" if s["of_prev"] is not None
                                                   and s["key"] != "sessions" else "") for s in steps)

    lines.append("Всего:  " + steps_line(rep["steps"]))
    lines.append(f"Заявок в таблице: {rep['lead_rows']}")
    ask = rep.get("ask") or {}
    cart = next((s["n"] for s in rep["steps"] if s["key"] == "cart"), 0)
    lines.append(f"Вопрос с карточки: {ask.get('sessions', 0)} (корзина {cart})"
                 + (" · " + ", ".join(f"{k} {v}" for k, v in ask["by_cta"].items()) if ask.get("by_cta") else ""))
    seen = rep.get("seen") or {}
    lines.append(f"Дошли до «что входит в цену»/выбора размера: {seen.get('price', 0)}/{seen.get('sizes', 0)}"
                 f" из {seen.get('product', 0)} сессий карточки")
    call = rep.get("call") or {}
    lines.append(f"«Позвоните нам»: {call.get('sessions', 0)}, заявок на звонок {call.get('leads', 0)}"
                 + (" · " + ", ".join(f"{k} {v}" for k, v in call["by_cta"].items()) if call.get("by_cta") else ""))
    if call.get("leads"):
        words = {"call": "звонок", "video": "видео", "info": "детали"}
        lines.append("  как: " + ", ".join(f"{words.get(k, k)} {v}" for k, v in (call.get("by_pref") or {}).items()))
    visit = rep.get("visit") or {}
    lines.append(f"Визит: cta_visit {visit.get('sessions', 0)}, заявок visit {visit.get('leads', 0)}"
                 + (" · " + ", ".join(f"{k} {v}" for k, v in visit["by_cta"].items()) if visit.get("by_cta") else ""))
    vote = rep.get("vote") or {}
    lines.append(f"Голоса «אני רוצה כזה» (следующее издание): {vote.get('leads', 0)}"
                 + (" · " + ", ".join(f"{k} {v}" for k, v in vote["by_product"].items()) if vote.get("by_product") else ""))
    lines.append("Реклама Meta, сессии: " + " · ".join(f"{a['ru']} {a['n']}" for a in rep.get("by_audience") or [])
                 + (" (шаги выше — только люди)" if rep.get("people_only") else ""))
    if any(a["key"] == "ads_meta_est" and a["n"] for a in rep.get("by_audience") or []):
        lines.append("  (оценка — события до флага fbclid_present, только по UA; всплеск проверки Meta — 22.10 14:00–15:30)")
    cv = rep.get("cart_view") or {}
    lines.append(f"Заходили на страницу корзины: {cv.get('sessions', 0)} (с товаром {cv.get('with_items', 0)}, "
                 f"только пустая {cv.get('empty', 0)}; с товаром, но без добавления в этой сессии {cv.get('no_add', 0)})"
                 " — не шаг «корзина»")
    order = rep.get("order") or {}
    lines.append(f"Форма заказа на карточке: открыли {order.get('open', 0)}, заявок order {order.get('leads', 0)}"
                 + (" · начали: " + ", ".join(f"{k} {v}" for k, v in order["form_start"].items()) if order.get("form_start") else "")
                 + (" · ошибки: " + ", ".join(f"{k} {v}" for k, v in order["form_error"].items()) if order.get("form_error") else ""))
    pt = rep.get("pdp_time") or {}
    lines.append(f"Время на карточке: медиана {pt.get('median') if pt.get('median') is not None else '—'} с (n={pt.get('n', 0)}) · "
                 f"вовлечённые (от 20 с и от ½ экрана) {pt.get('engaged', 0)} · с временем {pt.get('timed', 0)} из "
                 f"{pt.get('product', 0)} (только пульс {pt.get('pulse_only', 0)}, без времени {pt.get('no_time', 0)})")
    lines.append(f"  похоже на предзагрузку (28–34 с без прокрутки, не в медиане): {pt.get('preload', 0)}")
    for title, key in (("По товарам", "by_product"), ("По источнику", "by_source"), ("По языку", "by_lang"),
                       ("По дням", "by_day")):
        lines += ["", title + ":"]
        rows = rep.get(key) or []
        lines += [f"  {r['key']}: " + steps_line(r["steps"]) for r in rows] or ["  нет данных"]
    lines += ["", "Где ушли (последний шаг сессии):"]
    lines += [f"  после «{dict((k, ru) for k, _e, _h, ru in STEPS)[d['step']]}»: {d['n']}" for d in rep["dropped_after"]]
    if rep["leave_by_step"]:
        lines += ["", "Уходы со страницы по шагу: " + ", ".join(f"{k} {v}" for k, v in rep["leave_by_step"].items())]
    if rep["median_seconds"]:
        lines.append("Медиана секунд на шаге: " + ", ".join(f"{k} {v}" for k, v in rep["median_seconds"].items()))
    if rep.get("card_seconds"):
        lines.append("Секунд на карточке (медиана, n): " + ", ".join(
            f"{k} {v['median']} (n={v['n']})" for k, v in rep["card_seconds"].items()))
    dep = rep.get("pdp_depth") or {}
    if any(dep.values()):
        lines.append("Глубина на карточке (экранов): " + " · ".join(
            f"{label} мед. {d['median']} · q75 {d['q75']} (n={d['n']})" if d else f"{label} нет данных"
            for label, d in (("моб.", dep.get("mobile")), ("деск.", dep.get("desktop")))))
    lines += ["", "Цена в корзине → дошли:"]
    lines += [f"  {p['product']} {p['size']} ₪{p['price']}: корзина {p['cart']}, «לתשלום» {p['checkout']}, "
              f"оплата {p['payment']}, Lead {p['lead']}" for p in rep["price_points"]] or ["  нет данных"]
    return "\n".join(lines) + "\n"
