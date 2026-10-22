#!/usr/bin/env python3
"""Дайджест воронки власнику в Telegram — двічі на день (ihor-aluma-digest.timer, 09:00 і 20:00 Asia/Jerusalem).

ЧОМУ ЦЕ ІСНУЄ. Воронку видно лише в /admin/funnel або командою tools/funnel_report.py на сервері,
а власник дивиться результат реклами з телефона. Тут — ті самі цифри (api/funnel.py, ті самі
кроки STEPS і вікно календарних днів Єрусалима) коротким текстом у той самий чат, куди йдуть заявки.

Лише рахунок: сесії, кроки, slug товару, utm_source. Імен, телефонів, текстів заявок у тексті
нема — api/funnel.py бере із заявки тільки session_id і product_id. Тестові рядки (x-test) не рахуються.

    FX_DB_PATH=/opt/ihor/aluma-table/data/aluma.db python3 scripts/funnel_digest.py --dry-run  # текст у stdout
    systemctl --user start ihor-aluma-digest.service                                           # те саме, що таймер

Вивід (крім --dry-run) — один JSON-рядок без тексту, даних і токена:
    {"event": "digest_sent", "chars": N}
    {"event": "digest_failed", "reason": "..."}     → код виходу 1; бази нема → 2
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import quote

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import funnel  # noqa: E402
from scripts import daily_report  # noqa: E402

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OWNER_TELEGRAM_CHAT_ID = os.environ.get("OWNER_TELEGRAM_CHAT_ID", "")
TELEGRAM_TIMEOUT_SECONDS = 5   # як у api/handler.py
TEXT_MAX = 1500                # екран телефона, а не звіт

# Підписи кроків для власника — за ключем funnel.STEPS; checkout/payment — кроки «משלוח» і «אישור» на сайті.
LABEL = {"sessions": "визиты", "product": "карточка", "cart": "корзина",
         "checkout": "доставка", "payment": "подтверждение", "lead": "заявок"}
MAX_PRODUCTS = 8
MAX_SOURCES = 6


class DigestError(Exception):
    """Відмова з коротким кодом причини — без токена, тексту й даних."""


def _n(steps: list, key: str) -> int:
    return next((s["n"] for s in steps if s["key"] == key), 0)


def steps_line(rep: dict) -> str:
    if not _n(rep["steps"], "sessions") and not rep["lead_rows"]:
        return "визитов 0"
    parts = [f"{LABEL[s['key']]} {s['n']}" for s in rep["steps"] if s["key"] != "lead"]
    return " → ".join(parts + [f"{LABEL['lead']} {rep['lead_rows']}"])


def products_line(rep: dict) -> str:
    rows = [(r["key"], _n(r["steps"], "product"), _n(r["steps"], "lead")) for r in rep["by_product"]]
    rows = sorted((r for r in rows if r[1] > 0), key=lambda r: (-r[1], -r[2], r[0]))
    if not rows:
        return "нет просмотров карточек"
    head = [f"{k.upper()} {lead}/{cards}" for k, cards, lead in rows[:MAX_PRODUCTS]]
    return " · ".join(head) + (" · …" if len(rows) > MAX_PRODUCTS else "")


def sources_line(rep: dict) -> str:
    # by_source — «<utm_source> / <utm_campaign>»; власнику досить джерела, кампанії складаємо.
    # Заявки тут — і з події Lead, і з рядка fx_leads: funnel.compute() відносить заявку до джерела сесії або її utm.
    visits, leads = Counter(), Counter()
    for r in rep["by_source"]:
        src = r["key"].split(" / ", 1)[0]
        src = "прямые" if src == "direct" else src[:20]
        visits[src] += _n(r["steps"], "sessions")
        leads[src] += _n(r["steps"], "lead")
    if not visits:
        return "нет визитов"
    order = sorted(visits, key=lambda k: (-leads[k], -visits[k], k))
    head = [f"{k} {visits[k]}" + (f" ({leads[k]} заяв.)" if leads[k] else "") for k in order[:MAX_SOURCES]]
    return " · ".join(head) + (" · …" if len(order) > MAX_SOURCES else "")


def dropped_line(rep: dict) -> str:
    parts = [f"после «{LABEL[d['step']]}» {d['n']}" for d in rep["dropped_after"] if d["n"]]
    return ", ".join(parts) or "никто"


def digest_text(events, leads, now: datetime | None = None) -> str:
    """Текст дайджесту за «сьогодні» і «7 днів» із сирих рядків таблиць (тестові відкидає funnel.report)."""
    now = now or datetime.now(timezone.utc)
    today = funnel.report(events, leads, 1, now=now)
    week = funnel.report(events, leads, 7, now=now)
    lines = [
        f"ALUMA · воронка · {now.astimezone(funnel.TZ).strftime('%d.%m %H:%M')}",
        "Сегодня: " + steps_line(today),
        "7 дней: " + steps_line(week),
        "По товарам (7 дн., заявки/карточки): " + products_line(week),
        "По источнику (7 дн., визиты): " + sources_line(week),
    ]
    if _n(today["steps"], "sessions"):
        lines.append("Где ушли сегодня: " + dropped_line(today))
    text = "\n".join(lines)
    return text if len(text) <= TEXT_MAX else text[:TEXT_MAX - 1] + "…"


def _redact(text: str) -> str:
    """Як api/handler.py: токен живе в URL, а requests кладе URL у текст винятку."""
    text = str(text)
    if TELEGRAM_BOT_TOKEN:
        for form in (TELEGRAM_BOT_TOKEN, quote(TELEGRAM_BOT_TOKEN, safe="")):
            text = text.replace(form, "<token>")
    return text


def send(text: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and OWNER_TELEGRAM_CHAT_ID):
        raise DigestError("no_telegram_config")
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": OWNER_TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True},
            timeout=TELEGRAM_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        # Лише клас винятку: у його тексті URL із токеном (і _redact — про запас).
        raise DigestError(_redact("telegram_" + type(exc).__name__)) from None
    if r.status_code >= 400:
        raise DigestError(f"telegram_{r.status_code}")


def load_rows(db_path: str):
    """Сирі події за 7 днів і заявки (з тестовими — їх відкидає funnel.report). Нема бази — FileNotFoundError."""
    tables = daily_report.open_tables(db_path)
    return daily_report.load(7, True, tables)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Дайджест воронки ALUMA власнику в Telegram (лише рахунок)")
    ap.add_argument("--dry-run", action="store_true", help="надрукувати текст і нічого не слати")
    args = ap.parse_args(argv)

    def out(event: str, **kw) -> None:
        print(json.dumps({"event": event, **kw}), flush=True)

    try:
        events, leads = load_rows(daily_report.FX_DB_PATH)
    except FileNotFoundError:
        out("digest_failed", reason="no_db")
        return 2
    except Exception as exc:
        out("digest_failed", reason="db_" + type(exc).__name__)
        return 1
    text = digest_text(events, leads)
    if args.dry_run:
        print(text)
        out("digest_dry_run", chars=len(text))
        return 0
    try:
        send(text)
    except DigestError as exc:
        out("digest_failed", reason=str(exc))
        return 1
    out("digest_sent", chars=len(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
