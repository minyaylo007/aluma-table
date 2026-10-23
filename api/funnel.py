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
STEP_OF_EVENT["view_cart"] = "cart"   # корзина з минулого візиту — теж крок «корзина»
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
    seconds = defaultdict(list)
    asks = defaultdict(set)                                  # м'який крок картки: cta → сесії з cta_ask

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
            s = _num(p.get("seconds"))
            if s is not None:
                seconds[str(p.get("step") or "other")[:20]].append(s)
        if name == "cta_ask":
            asks[str(p.get("cta") or "other")[:20]].add(sid)
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
    lead_rows = 0
    for l in leads:
        lead_rows += 1
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
        "median_seconds": {k: sorted(v)[len(v) // 2] for k, v in seconds.items() if v},
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
    lines.append("Реклама Meta, сессии: " + " · ".join(f"{a['ru']} {a['n']}" for a in rep.get("by_audience") or [])
                 + (" (шаги выше — только люди)" if rep.get("people_only") else ""))
    if any(a["key"] == "ads_meta_est" and a["n"] for a in rep.get("by_audience") or []):
        lines.append("  (оценка — события до флага fbclid_present, только по UA; всплеск проверки Meta — 22.10 14:00–15:30)")
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
    lines += ["", "Цена в корзине → дошли:"]
    lines += [f"  {p['product']} {p['size']} ₪{p['price']}: корзина {p['cart']}, «לתשלום» {p['checkout']}, "
              f"оплата {p['payment']}, Lead {p['lead']}" for p in rep["price_points"]] or ["  нет данных"]
    return "\n".join(lines) + "\n"
