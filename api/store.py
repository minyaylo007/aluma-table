"""SQLite-двійник трьох таблиць DynamoDB, якими користується api/handler.py.

Це НЕ емулятор DynamoDB. Тут реалізовано рівно ті виклики, що є в handler.py —
put_item, get_item, query, update_item, scan і batch_writer() — і рівно в тих
формах, у яких їх роблять. Усе інше падає з ValueError: краще гучна помилка на
машині розробника, ніж тихо проігнорований вираз у проді.

Розкладка рядка: (hk, rk, doc) — ключі окремими колонками заради індексу,
решта атрибутів одним JSON. Схема ключів приходить ззовні (див. tables()), бо
вона задана в infra/template.yaml: fx_events/fx_leads = pk+sk, fx_sessions = session_id.

Одне з'єднання під RLock замість з'єднання-на-потік: gunicorn --threads 4 на
лендінгу з 20 лідами не впирається в блокування, зате ":memory:" лишається
однією базою для всіх потоків, а не окремою в кожного. WAL і busy_timeout
все одно вмикаємо — база одночасно відкрита скриптом міграції та бекапом.
"""

from __future__ import annotations

import decimal
import json
import os
import re
import sqlite3
import threading
import time

__all__ = ["SqliteStore", "SqliteTable", "tables"]

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_]+$")

# "a = :v" або "a = if_not_exists(a, :v)"
_ASSIGN = re.compile(
    r"(#?[A-Za-z_][\w.]*)\s*=\s*"
    r"(?:if_not_exists\(\s*(#?[A-Za-z_][\w.]*)\s*,\s*(:\w+)\s*\)|(:\w+))"
)
# "#n :one"
_ADD = re.compile(r"(#?[A-Za-z_][\w.]*)\s+(:\w+)")
_CLAUSE = re.compile(r"\b(SET|ADD|REMOVE|DELETE)\b", re.I)


def _plain(value):
    """Decimal → int/float. boto3 віддає числа Decimal'ами, а json їх не вміє;
    без цього скрипт міграції (задача 1.3) впаде на першому ж рядку з ttl."""
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(f"{type(value).__name__} не серіалізується в JSON: {value!r}")


def _eq_condition(cond):
    """Витягти (атрибут, значення) з Key("pk").eq(...).

    Дві форми: справжня умова boto3 і кортеж ("eq", name, value) — саме такий
    віддає дублер Key у tests/test_handler.py, коли boto3 не встановлено.
    """
    if isinstance(cond, tuple):
        if len(cond) == 3 and cond[0] == "eq":
            return cond[1], cond[2]
        raise ValueError(f"шим розуміє лише Key(...).eq(...), а не {cond!r}")
    expression = getattr(cond, "get_expression", None)
    if expression is None:
        raise ValueError(f"шим розуміє лише Key(...).eq(...), а не {cond!r}")
    expr = expression()
    if expr.get("operator") != "=":
        raise ValueError(f"шим розуміє лише eq(), а не {expr.get('operator')!r}")
    left, right = expr["values"]
    return getattr(left, "name", left), right


def _parse_update(expression: str, names: dict, values: dict):
    """UpdateExpression → ([(атрибут, значення, only_if_missing)], [(атрибут, дельта)])."""

    def attr(token: str) -> str:
        if token.startswith("#"):
            if token not in names:
                raise ValueError(f"{token} немає в ExpressionAttributeNames")
            return names[token]
        return token

    def value(token: str):
        if token not in values:
            raise ValueError(f"{token} немає в ExpressionAttributeValues")
        return values[token]

    def scan_clause(body: str, pattern, build):
        out, pos = [], 0
        for m in pattern.finditer(body):
            if body[pos:m.start()].strip(" ,\t\n"):
                raise ValueError(f"невідомий фрагмент виразу: {body[pos:m.start()]!r}")
            out.append(build(m))
            pos = m.end()
        if body[pos:].strip(" ,\t\n"):
            raise ValueError(f"невідомий фрагмент виразу: {body[pos:]!r}")
        if not out:
            raise ValueError(f"порожня частина виразу: {body!r}")
        return out

    parts = _CLAUSE.split(expression)
    if parts[0].strip():
        raise ValueError(f"вираз має починатися з SET або ADD: {expression!r}")
    sets, adds = [], []
    for keyword, body in zip(parts[1::2], parts[2::2]):
        keyword = keyword.upper()
        if keyword == "SET":
            sets += scan_clause(
                body, _ASSIGN,
                lambda m: (attr(m.group(1)), value(m.group(3) or m.group(4)), m.group(2) is not None),
            )
        elif keyword == "ADD":
            adds += scan_clause(body, _ADD, lambda m: (attr(m.group(1)), value(m.group(2))))
        else:
            raise ValueError(f"{keyword} не підтримується — handler.py його не використовує")
    if not sets and not adds:
        raise ValueError(f"вираз без SET і ADD: {expression!r}")
    return sets, adds


class SqliteStore:
    """Один файл бази (або ":memory:") і одне з'єднання під замком."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        if path != ":memory:":
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path, timeout=10.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=10000")
            self._conn.execute("PRAGMA synchronous=NORMAL")

    def table(self, name: str, key_schema) -> "SqliteTable":
        return SqliteTable(self, name, tuple(key_schema))

    def execute(self, sql: str, args=()):
        with self._lock:
            cur = self._conn.execute(sql, args)
            self._conn.commit()
            return cur

    def rows(self, sql: str, args=()):
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def close(self):
        with self._lock:
            self._conn.close()


class SqliteTable:
    """Поверхня boto3 dynamodb.Table, яку насправді викликає handler.py."""

    def __init__(self, store: SqliteStore, name: str, key_schema):
        if not _SAFE_NAME.match(name):
            raise ValueError(f"недопустиме ім'я таблиці: {name!r}")
        if len(key_schema) not in (1, 2):
            raise ValueError(f"схема ключа має бути (hash,) або (hash, range): {key_schema!r}")
        self._store = store
        self.name = name
        self.key_schema = tuple(key_schema)
        store.execute(
            f'CREATE TABLE IF NOT EXISTS "{name}" ('
            " hk TEXT NOT NULL, rk TEXT NOT NULL DEFAULT '',"
            " doc TEXT NOT NULL, ttl INTEGER,"
            " PRIMARY KEY (hk, rk))"
        )

    # ------------------------------------------------------------------ ключі

    def _key_of(self, item: dict, what: str = "Item"):
        out = []
        for attribute in self.key_schema:
            if item.get(attribute) is None:
                raise ValueError(f"{what} без ключового атрибута {attribute!r}: {item!r}")
            out.append(str(item[attribute]))
        return out[0], (out[1] if len(out) > 1 else "")

    def _key_dict(self, hk: str, rk: str) -> dict:
        if len(self.key_schema) == 1:
            return {self.key_schema[0]: hk}
        return {self.key_schema[0]: hk, self.key_schema[1]: rk}

    @staticmethod
    def _ttl_of(item: dict):
        ttl = item.get("ttl")
        if isinstance(ttl, decimal.Decimal):
            ttl = int(ttl)
        return ttl if isinstance(ttl, int) and not isinstance(ttl, bool) else None

    def _write(self, item: dict):
        hk, rk = self._key_of(item)
        self._store.execute(
            f'INSERT OR REPLACE INTO "{self.name}" (hk, rk, doc, ttl) VALUES (?, ?, ?, ?)',
            (hk, rk, json.dumps(item, ensure_ascii=False, default=_plain), self._ttl_of(item)),
        )

    # ------------------------------------------------------------------ API

    def put_item(self, Item=None, **_ignored):
        self._write(dict(Item or {}))
        return {}

    def get_item(self, Key=None, **_ignored):
        hk, rk = self._key_of(dict(Key or {}), what="Key")
        rows = self._store.rows(
            f'SELECT doc FROM "{self.name}" WHERE hk = ? AND rk = ?', (hk, rk)
        )
        return {"Item": json.loads(rows[0]["doc"])} if rows else {}

    def query(self, **kwargs):
        condition = kwargs.get("KeyConditionExpression")
        if condition is None:
            raise ValueError("query() без KeyConditionExpression")
        attribute, hk = _eq_condition(condition)
        if attribute != self.key_schema[0]:
            raise ValueError(
                f"query() лише за ключем розділу {self.key_schema[0]!r}, а не {attribute!r}"
            )
        forward = kwargs.get("ScanIndexForward", True)
        sql = f'SELECT hk, rk, doc FROM "{self.name}" WHERE hk = ?'
        args = [str(hk)]
        start = kwargs.get("ExclusiveStartKey")
        if start:
            if len(self.key_schema) == 1:
                # Розділ без ключа сортування = рівно один рядок. Другої сторінки
                # тут не буває, тож ExclusiveStartKey означає помилку виклику.
                raise ValueError(f"{self.name}: query() без ключа сортування не має сторінок")
            sql += " AND rk > ?" if forward else " AND rk < ?"
            args.append(str(start[self.key_schema[1]]))
        sql += " ORDER BY rk " + ("ASC" if forward else "DESC")
        return self._page(sql, args, kwargs.get("Limit"))

    def scan(self, **kwargs):
        sql = f'SELECT hk, rk, doc FROM "{self.name}"'
        args = []
        start = kwargs.get("ExclusiveStartKey")
        if start:
            sql += " WHERE (hk, rk) > (?, ?)"
            args = list(self._key_of(dict(start), what="ExclusiveStartKey"))
        sql += " ORDER BY hk ASC, rk ASC"
        return self._page(sql, args, kwargs.get("Limit"))

    def _page(self, sql: str, args, limit):
        """Читаємо на один рядок більше за ліміт — так видно, чи є наступна сторінка."""
        limit = int(limit) if limit else 0
        if limit:
            sql += " LIMIT ?"
            args = list(args) + [limit + 1]
        rows = self._store.rows(sql, tuple(args))
        page = rows[:limit] if limit else rows
        out = {"Items": [json.loads(r["doc"]) for r in page]}
        if limit and len(rows) > limit:
            out["LastEvaluatedKey"] = self._key_dict(page[-1]["hk"], page[-1]["rk"])
        return out

    def update_item(self, **kwargs):
        key = dict(kwargs.get("Key") or {})
        hk, rk = self._key_of(key, what="Key")
        sets, adds = _parse_update(
            kwargs.get("UpdateExpression") or "",
            kwargs.get("ExpressionAttributeNames") or {},
            kwargs.get("ExpressionAttributeValues") or {},
        )
        # DynamoDB створює рядок, якщо його не було, — rate_ok() на це розраховує.
        item = self.get_item(Key=key).get("Item") or dict(key)
        changed = {}
        for attribute, value, only_if_missing in sets:
            if only_if_missing and item.get(attribute) is not None:
                changed[attribute] = item[attribute]
                continue
            item[attribute] = value
            changed[attribute] = value
        for attribute, delta in adds:
            current = item.get(attribute, 0)
            if not isinstance(current, (int, float)) or not isinstance(delta, (int, float)):
                raise ValueError(f"ADD працює лише з числами: {attribute}")
            item[attribute] = current + delta
            changed[attribute] = item[attribute]
        self._write(item)
        return {"Attributes": changed} if kwargs.get("ReturnValues") == "UPDATED_NEW" else {}

    def batch_writer(self):
        return _BatchWriter(self)

    # ------------------------------------------------------------------ TTL

    def purge_expired(self, now: int | None = None) -> int:
        """DynamoDB TTL прибирав протухлі рядки сам; SQLite — ні. Кличеться з таймера."""
        cur = self._store.execute(
            f'DELETE FROM "{self.name}" WHERE ttl IS NOT NULL AND ttl < ?',
            (int(now if now is not None else time.time()),),
        )
        return cur.rowcount


class _BatchWriter:
    """boto3-подібний контекст. Пише одразу: 40 подій на запит — не той обсяг,
    заради якого варто ризикувати втратою буфера при винятку."""

    def __init__(self, table: SqliteTable):
        self._table = table

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def put_item(self, Item=None, **_ignored):
        return self._table.put_item(Item=Item)


def tables(db_path: str, events: str = "fx_events", leads: str = "fx_leads",
           sessions: str = "fx_sessions"):
    """Три таблиці в тому ж порядку, що й у handler._tables().

    Схема ключів продубльована з infra/template.yaml — це єдине місце, де вона
    записана на боці SQLite, тож тримайте їх однаковими.
    """
    store = SqliteStore(db_path)
    return (
        store.table(events, ("pk", "sk")),
        store.table(leads, ("pk", "sk")),
        store.table(sessions, ("session_id",)),
    )
