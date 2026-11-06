"""Рядки воронки з SQLite коробки — для tools/funnel_report.py і scripts/funnel_digest.py.

Той самий файл бази і ті самі імена таблиць, що в api/handler.py у режимі FX_STORAGE=sqlite
(FX_DB_PATH, EVENTS_TABLE, LEADS_TABLE, SESSIONS_TABLE), через api/store.py; boto3 не потрібен.
Бази за FX_DB_PATH нема — FileNotFoundError: порожню базу модуль не створює.
Перенесено з scripts/daily_report.py, коли той видалили (№44).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

try:  # з кореня репозиторію (тести, tools/, scripts/)
    from api import funnel as shop, store
except ImportError:  # у бандлі лямбди api/ САМЕ і є коренем
    import funnel as shop
    import store

FX_DB_PATH = os.environ.get("FX_DB_PATH", "data/aluma.db")
EVENTS_TABLE = os.environ.get("EVENTS_TABLE", "fx_events")
LEADS_TABLE = os.environ.get("LEADS_TABLE", "fx_leads")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "fx_sessions")


def key_eq(name: str, value: str):
    """Умова Key(name).eq(value) у формі, яку api/store.py розуміє без boto3."""
    return ("eq", name, value)


def open_tables(db_path: str, readonly: bool = False):
    """(fx_events, fx_leads) з файлу бази. Нема файлу — FileNotFoundError, а не порожня база.
    readonly — з'єднання SQLite mode=ro (tools/funnel_report.py, №42): писати в базу звіт не може."""
    if db_path != ":memory:" and not os.path.exists(db_path):
        raise FileNotFoundError(db_path)
    events_t, leads_t, _sessions = store.tables(db_path, EVENTS_TABLE, LEADS_TABLE, SESSIONS_TABLE, readonly=readonly)
    return events_t, leads_t


def load(days: int, include_test: bool, tables=None):
    """Події й заявки за одне вікно — календарні дні Asia/Jerusalem (api/funnel.py, як /admin/funnel).

    Раніше події бралися UTC-днями, а заявки — ковзними 24 год × N: одна ніч давала різні вікна.
    """
    events_t, leads_t = tables or open_tables(FX_DB_PATH)
    now = datetime.now(timezone.utc)

    events = []
    for day in shop.utc_partitions(days, now):
        last = None
        while True:
            kw = {"KeyConditionExpression": key_eq("pk", f"D#{day}"), "Limit": 1000}
            if last:
                kw["ExclusiveStartKey"] = last
            r = events_t.query(**kw)
            events.extend(r.get("Items", []))
            last = r.get("LastEvaluatedKey")
            if not last:
                break

    leads, last = [], None
    while True:
        kw = {"KeyConditionExpression": key_eq("pk", "LEAD"), "ScanIndexForward": False, "Limit": 500}
        if last:
            kw["ExclusiveStartKey"] = last
        r = leads_t.query(**kw)
        leads.extend(r.get("Items", []))
        last = r.get("LastEvaluatedKey")
        if not last or len(leads) >= 2000:
            break

    if not include_test:
        events = [e for e in events if not e.get("is_test")]
        leads = [l for l in leads if not l.get("is_test")]

    return shop.events_in_window(events, days, now), shop.leads_in_window(leads, days, now)
