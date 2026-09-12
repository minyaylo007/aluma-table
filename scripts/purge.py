#!/usr/bin/env python3
"""Суточна чистка бази ALUMA: протухлі рядки + VACUUM.

ЧОМУ ЦЕ ІСНУЄ. У DynamoDB протухлі рядки прибирав сам сервіс (атрибут ttl,
infra/template.yaml). У SQLite не прибирає ніхто: api/store.py:292
purge_expired() написана й працює, але її не кличе НІХТО, крім тестів.
Без цього виклику вічними стають:

  * події         — ttl = зараз + EVENT_TTL_DAYS (180);
  * сесії         — ttl = зараз + SESSION_TTL_DAYS (400);
  * ведра лімітів — ttl = зараз + вікно + 60 секунд, тобто рядок, який мав
                    жити 61 секунду, лишається назавжди. Їх найбільше:
                    по рядку на кожен IP на кожну хвилину.

Запускається таймером (deploy/systemd/aluma-purge.timer), OnCalendar=daily.
Руками — так само:

    FX_DB_PATH=/opt/ihor/aluma-table/data/aluma.db python3 scripts/purge.py

Заявки (fx_leads) чистка не чіпає: у них ttl не ставиться, вони живуть вічно
за задумом. DELETE тут прибирає рівно те, у чого ttl < зараз.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import store  # noqa: E402

FX_DB_PATH = os.environ.get("FX_DB_PATH", "data/aluma.db")
EVENTS_TABLE = os.environ.get("EVENTS_TABLE", "fx_events")
LEADS_TABLE = os.environ.get("LEADS_TABLE", "fx_leads")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "fx_sessions")


def restrict_umask() -> None:
    """umask не ширший за 027: VACUUM перестворює файл бази з заявками.

    Строгіший (UMask=0077 юніта) лишається — біти лише додаються.
    """
    os.umask(os.umask(0o027) | 0o027)


def main() -> int:
    restrict_umask()
    if not os.path.exists(FX_DB_PATH):
        print(json.dumps({"event": "purge_skipped", "reason": "no_db", "db": FX_DB_PATH}))
        return 0

    started = time.time()
    events_t, leads_t, sessions_t = store.tables(
        FX_DB_PATH, EVENTS_TABLE, LEADS_TABLE, SESSIONS_TABLE
    )

    removed = {}
    # Усі три таблиці, а не дві: ttl у fx_leads не ставиться, тож виклик там
    # просто нічого не знайде — але якщо колись почнуть ставити, чистка вже є.
    for name, table in ((EVENTS_TABLE, events_t), (LEADS_TABLE, leads_t),
                        (SESSIONS_TABLE, sessions_t)):
        removed[name] = table.purge_expired()

    # VACUUM окремо і після DELETE: без нього файл не зменшується, а ведра
    # лімітів — це саме той випадок, коли рядків багато й вони всі йдуть геть.
    # store.execute() комітить кожен вираз, тож відкритої транзакції тут нема.
    events_t._store.execute("VACUUM")

    print(json.dumps({
        "event": "purge_done",
        "db": FX_DB_PATH,
        "removed": removed,
        "seconds": round(time.time() - started, 3),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
