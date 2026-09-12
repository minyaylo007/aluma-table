"""SQLite-шим, який заміняє boto3-таблиці в api/handler.py.

Хендлер користується рівно шістьма викликами Table: put_item, get_item, query,
update_item, scan і batch_writer(). Тут перевіряється кожен з них — і рівно в тій
формі, в якій його викликає handler.py, а не абстрактний DynamoDB.

Запуск з кореня репозиторію:

    python -m pytest tests/test_store_sqlite.py -q
"""

from __future__ import annotations

import os
import pathlib
import sys
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# handler.py читає конфіг на імпорті: жоден тест не має права створити файл бази.
os.environ["FX_DB_PATH"] = ":memory:"

from api import store  # noqa: E402

try:  # справжня умова boto3, якщо SDK встановлено
    from boto3.dynamodb.conditions import Key as Boto3Key
except Exception:  # pragma: no cover - на машині без boto3
    Boto3Key = None


class TupleKey:
    """Дублер Key(...) з tests/test_handler.py: .eq() віддає кортеж, не об'єкт boto3.

    Шим мусить розуміти обидві форми — інакше офлайн-набір тестів
    (той, що підміняє весь boto3) не зможе ходити в SQLite.
    """

    def __init__(self, name):
        self.name = name

    def eq(self, value):
        return ("eq", self.name, value)


def key_shapes():
    shapes = [("tuple", TupleKey)]
    if Boto3Key is not None:
        shapes.append(("boto3", Boto3Key))
    return shapes


# --------------------------------------------------------------------------- pk+sk


class CompositeKeyTableTests(unittest.TestCase):
    """Таблиці fx_events / fx_leads: HASH pk + RANGE sk."""

    def setUp(self):
        self.st = store.SqliteStore(":memory:")
        self.t = self.st.table("fx_leads", ("pk", "sk"))

    def lead(self, sk: str, **extra):
        item = {"pk": "LEAD", "sk": sk, "id": sk[-4:], "name": "דנה", "status": "new"}
        item.update(extra)
        return item

    def test_put_then_get_roundtrip(self):
        item = self.lead("2026-09-10T10:00:00+00:00#aaaa", consent=True, ttl=17)
        self.t.put_item(Item=item)
        got = self.t.get_item(Key={"pk": "LEAD", "sk": item["sk"]})
        self.assertEqual(got["Item"], item)

    def test_put_item_overwrites_the_same_key(self):
        self.t.put_item(Item=self.lead("s1", status="new"))
        self.t.put_item(Item=self.lead("s1", status="called"))
        got = self.t.get_item(Key={"pk": "LEAD", "sk": "s1"})
        self.assertEqual(got["Item"]["status"], "called")
        self.assertEqual(len(self.t.scan()["Items"]), 1)

    def test_get_item_missing_returns_a_response_without_item(self):
        got = self.t.get_item(Key={"pk": "LEAD", "sk": "nope"})
        self.assertNotIn("Item", got)

    def test_query_returns_one_partition_sorted_by_sk(self):
        for sk in ("s3", "s1", "s2"):
            self.t.put_item(Item=self.lead(sk))
        self.t.put_item(Item={"pk": "OTHER", "sk": "s9"})
        for label, KeyCls in key_shapes():
            with self.subTest(key=label):
                r = self.t.query(KeyConditionExpression=KeyCls("pk").eq("LEAD"))
                self.assertEqual([i["sk"] for i in r["Items"]], ["s1", "s2", "s3"])
                self.assertNotIn("LastEvaluatedKey", r)

    def test_query_scan_index_forward_false_is_newest_first(self):
        for sk in ("s1", "s2", "s3"):
            self.t.put_item(Item=self.lead(sk))
        r = self.t.query(
            KeyConditionExpression=TupleKey("pk").eq("LEAD"),
            ScanIndexForward=False,
            Limit=500,
        )
        self.assertEqual([i["sk"] for i in r["Items"]], ["s3", "s2", "s1"])

    def test_query_limit_paginates_through_exclusive_start_key(self):
        for i in range(5):
            self.t.put_item(Item=self.lead(f"s{i}"))
        seen, last, rounds = [], None, 0
        while True:
            kwargs = {"KeyConditionExpression": TupleKey("pk").eq("LEAD"), "Limit": 2}
            if last:
                kwargs["ExclusiveStartKey"] = last
            r = self.t.query(**kwargs)
            seen.extend(i["sk"] for i in r["Items"])
            last = r.get("LastEvaluatedKey")
            rounds += 1
            if not last or rounds > 10:
                break
        self.assertEqual(seen, ["s0", "s1", "s2", "s3", "s4"])
        self.assertEqual(rounds, 3)  # 2 + 2 + 1, і останній без LastEvaluatedKey

    def test_query_descending_paginates_too(self):
        for i in range(3):
            self.t.put_item(Item=self.lead(f"s{i}"))
        first = self.t.query(
            KeyConditionExpression=TupleKey("pk").eq("LEAD"), ScanIndexForward=False, Limit=2
        )
        self.assertEqual([i["sk"] for i in first["Items"]], ["s2", "s1"])
        second = self.t.query(
            KeyConditionExpression=TupleKey("pk").eq("LEAD"),
            ScanIndexForward=False,
            Limit=2,
            ExclusiveStartKey=first["LastEvaluatedKey"],
        )
        self.assertEqual([i["sk"] for i in second["Items"]], ["s0"])

    def test_query_of_an_empty_partition_is_an_empty_list(self):
        r = self.t.query(KeyConditionExpression=TupleKey("pk").eq("D#2026-01-01"))
        self.assertEqual(r["Items"], [])

    def test_query_rejects_conditions_the_handler_never_uses(self):
        # Це шим, а не емулятор DynamoDB: усе поза eq() на ключі має падати гучно.
        with self.assertRaises(ValueError):
            self.t.query(KeyConditionExpression=TupleKey("status").eq("new"))
        with self.assertRaises(ValueError):
            self.t.query(KeyConditionExpression=("begins_with", "pk", "LEAD"))

    def test_update_item_set_with_name_placeholders(self):
        """admin_status(): SET #s = :s, status_changed_at = :t."""
        self.t.put_item(Item=self.lead("s1", status="new"))
        self.t.update_item(
            Key={"pk": "LEAD", "sk": "s1"},
            UpdateExpression="SET #s = :s, status_changed_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "called", ":t": "2026-09-10T00:00:00+00:00"},
        )
        item = self.t.get_item(Key={"pk": "LEAD", "sk": "s1"})["Item"]
        self.assertEqual(item["status"], "called")
        self.assertEqual(item["status_changed_at"], "2026-09-10T00:00:00+00:00")
        self.assertEqual(item["name"], "דנה")  # решта полів недоторкана

    def test_scan_returns_every_row_of_the_table(self):
        for sk in ("s1", "s2"):
            self.t.put_item(Item=self.lead(sk))
        self.t.put_item(Item={"pk": "OTHER", "sk": "s9"})
        r = self.t.scan()
        self.assertEqual(len(r["Items"]), 3)
        self.assertEqual({i["pk"] for i in r["Items"]}, {"LEAD", "OTHER"})

    def test_scan_paginates_with_limit(self):
        for i in range(3):
            self.t.put_item(Item=self.lead(f"s{i}"))
        first = self.t.scan(Limit=2)
        self.assertEqual(len(first["Items"]), 2)
        second = self.t.scan(Limit=2, ExclusiveStartKey=first["LastEvaluatedKey"])
        self.assertEqual(len(second["Items"]), 1)
        self.assertNotIn("LastEvaluatedKey", second)

    def test_batch_writer_writes_every_item(self):
        with self.t.batch_writer() as batch:
            for i in range(30):
                batch.put_item(Item=self.lead(f"s{i:02d}"))
        self.assertEqual(len(self.t.scan()["Items"]), 30)

    def test_batch_writer_does_not_swallow_an_error(self):
        with self.assertRaises(RuntimeError):
            with self.t.batch_writer() as batch:
                batch.put_item(Item=self.lead("s1"))
                raise RuntimeError("boom")

    def test_put_item_requires_the_key_attributes(self):
        with self.assertRaises(ValueError):
            self.t.put_item(Item={"sk": "s1", "name": "no pk"})

    def test_decimals_from_dynamodb_are_stored_as_plain_numbers(self):
        """Задача 1.3 читатиме з DynamoDB, а boto3 віддає числа як Decimal."""
        from decimal import Decimal

        self.t.put_item(Item={"pk": "LEAD", "sk": "s1", "ttl": Decimal("1789000000"),
                              "score": Decimal("1.5")})
        item = self.t.get_item(Key={"pk": "LEAD", "sk": "s1"})["Item"]
        self.assertEqual(item["ttl"], 1789000000)
        self.assertIsInstance(item["ttl"], int)
        self.assertEqual(item["score"], 1.5)

    def test_a_decimal_ttl_still_expires(self):
        from decimal import Decimal

        self.t.put_item(Item={"pk": "LEAD", "sk": "old", "ttl": Decimal("100")})
        self.assertEqual(self.t.purge_expired(now=200), 1)


# --------------------------------------------------------------------------- sessions


class SingleKeyTableTests(unittest.TestCase):
    """fx_sessions: лише HASH session_id — сюди ходять rate_ok() і touch_session()."""

    def setUp(self):
        self.st = store.SqliteStore(":memory:")
        self.t = self.st.table("fx_sessions", ("session_id",))

    def add_one(self, bucket="RLL#R#abc#480000", window=3600):
        return self.t.update_item(
            Key={"session_id": bucket},
            UpdateExpression="ADD #n :one SET #t = if_not_exists(#t, :ttl)",
            ExpressionAttributeNames={"#n": "n", "#t": "ttl"},
            ExpressionAttributeValues={":one": 1, ":ttl": int(time.time()) + window + 60},
            ReturnValues="UPDATED_NEW",
        )

    def test_add_counter_creates_the_row_and_returns_one(self):
        r = self.add_one()
        self.assertEqual(int(r["Attributes"]["n"]), 1)

    def test_add_counter_increments_and_keeps_the_first_ttl(self):
        first = self.add_one()
        ttl = self.t.get_item(Key={"session_id": "RLL#R#abc#480000"})["Item"]["ttl"]
        for expected in (2, 3, 4):
            r = self.add_one()
            self.assertEqual(int(r["Attributes"]["n"]), expected)
        self.assertEqual(int(first["Attributes"]["n"]), 1)
        self.assertEqual(self.t.get_item(Key={"session_id": "RLL#R#abc#480000"})["Item"]["ttl"], ttl)

    def test_counters_of_different_buckets_are_independent(self):
        self.add_one("A")
        self.add_one("A")
        r = self.add_one("B")
        self.assertEqual(int(r["Attributes"]["n"]), 1)

    def test_touch_session_if_not_exists_keeps_the_first_value(self):
        """touch_session(): first_seen фіксується один раз, last_seen — щоразу."""
        expr = (
            "SET first_seen = if_not_exists(first_seen, :now), last_seen = :now, "
            "utm_source = if_not_exists(utm_source, :us), device = :dev, #t = :ttl"
        )
        self.t.update_item(
            Key={"session_id": "s-1"},
            UpdateExpression=expr,
            ExpressionAttributeNames={"#t": "ttl"},
            ExpressionAttributeValues={":now": "T1", ":us": "fb", ":dev": "mobile", ":ttl": 1},
        )
        self.t.update_item(
            Key={"session_id": "s-1"},
            UpdateExpression=expr,
            ExpressionAttributeNames={"#t": "ttl"},
            ExpressionAttributeValues={":now": "T2", ":us": "google", ":dev": "desktop", ":ttl": 2},
        )
        item = self.t.get_item(Key={"session_id": "s-1"})["Item"]
        self.assertEqual(item["first_seen"], "T1")
        self.assertEqual(item["last_seen"], "T2")
        self.assertEqual(item["utm_source"], "fb")
        self.assertEqual(item["device"], "desktop")
        self.assertEqual(item["ttl"], 2)
        self.assertEqual(item["session_id"], "s-1")

    def test_update_item_rejects_an_expression_the_handler_never_writes(self):
        with self.assertRaises(ValueError):
            self.t.update_item(
                Key={"session_id": "s-1"},
                UpdateExpression="REMOVE utm_source",
                ExpressionAttributeValues={},
            )

    def test_query_rejects_pagination_that_cannot_mean_anything(self):
        """Розділ із одним ключем містить рівно один рядок — другої сторінки не буває."""
        with self.assertRaises(ValueError):
            self.t.query(
                KeyConditionExpression=TupleKey("session_id").eq("s-1"),
                ExclusiveStartKey={"session_id": "s-1"},
            )

    def test_purge_expired_drops_only_rows_past_their_ttl(self):
        now = int(time.time())
        self.t.put_item(Item={"session_id": "old", "ttl": now - 10})
        self.t.put_item(Item={"session_id": "fresh", "ttl": now + 600})
        self.t.put_item(Item={"session_id": "no-ttl"})
        removed = self.t.purge_expired(now=now)
        self.assertEqual(removed, 1)
        self.assertEqual({i["session_id"] for i in self.t.scan()["Items"]}, {"fresh", "no-ttl"})


# --------------------------------------------------------------------------- інфраструктура


class StoreWiringTests(unittest.TestCase):
    def test_tables_factory_returns_events_leads_sessions(self):
        events, leads, sessions = store.tables(":memory:")
        self.assertEqual(events.key_schema, ("pk", "sk"))
        self.assertEqual(leads.key_schema, ("pk", "sk"))
        self.assertEqual(sessions.key_schema, ("session_id",))
        self.assertEqual({events.name, leads.name, sessions.name},
                         {"fx_events", "fx_leads", "fx_sessions"})

    def test_tables_factory_honours_custom_table_names(self):
        events, leads, sessions = store.tables(":memory:", "e", "l", "s")
        self.assertEqual([events.name, leads.name, sessions.name], ["e", "l", "s"])

    def test_three_tables_share_one_database_but_not_their_rows(self):
        events, leads, sessions = store.tables(":memory:")
        events.put_item(Item={"pk": "D#2026-09-10", "sk": "a", "event_name": "view"})
        leads.put_item(Item={"pk": "LEAD", "sk": "a", "name": "דנה"})
        sessions.put_item(Item={"session_id": "s-1"})
        self.assertEqual(len(events.scan()["Items"]), 1)
        self.assertEqual(len(leads.scan()["Items"]), 1)
        self.assertEqual(leads.scan()["Items"][0]["name"], "דנה")

    def file_store(self, path):
        st = store.SqliteStore(str(path))
        self.addCleanup(st.close)  # Windows не дає стерти теку з відкритим файлом
        return st

    def test_a_file_database_is_created_with_its_parent_directory(self):
        import tempfile

        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        path = pathlib.Path(tmp) / "nested" / "aluma.db"

        leads = self.file_store(path).table("fx_leads", ("pk", "sk"))
        leads.put_item(Item={"pk": "LEAD", "sk": "s1", "name": "דנה"})
        self.assertTrue(path.exists())

        # інший воркер відкриває той самий файл і бачить той самий рядок
        leads2 = self.file_store(path).table("fx_leads", ("pk", "sk"))
        self.assertEqual(len(leads2.scan()["Items"]), 1)
        self.assertEqual(leads2.scan()["Items"][0]["name"], "דנה")

    def test_concurrent_writers_do_not_lock_the_database(self):
        """gunicorn --threads 4: SQLite має витримати паралельний запис (ADR-3)."""
        import tempfile

        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        leads = self.file_store(pathlib.Path(tmp) / "aluma.db").table("fx_leads", ("pk", "sk"))
        errors = []

        def worker(n):
            try:
                for i in range(25):
                    leads.put_item(Item={"pk": "LEAD", "sk": f"{n}-{i:02d}", "n": n})
            except Exception as exc:  # sqlite3.OperationalError: database is locked
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [], errors)
        self.assertEqual(len(leads.scan()["Items"]), 200)


class HandlerSelectsTheStoreTests(unittest.TestCase):
    """_tables() — єдина функція handler.py, яку змінює задача 1.1."""

    def setUp(self):
        import api.handler as h

        self.h = h
        h._reset_tables()
        self.addCleanup(h._reset_tables)

    def test_sqlite_is_the_default(self):
        self.assertEqual(self.h.FX_STORAGE, "sqlite")

    def test_sqlite_mode_returns_shim_tables_and_never_touches_boto3(self):
        with mock.patch.object(self.h, "FX_STORAGE", "sqlite"), \
                mock.patch.object(self.h, "FX_DB_PATH", ":memory:"), \
                mock.patch.object(self.h.boto3, "resource", side_effect=AssertionError("AWS!")):
            events, leads, sessions = self.h._tables()
        self.assertIsInstance(leads, store.SqliteTable)
        self.assertEqual(sessions.key_schema, ("session_id",))

    def test_sqlite_tables_are_built_once_and_reused(self):
        with mock.patch.object(self.h, "FX_STORAGE", "sqlite"), \
                mock.patch.object(self.h, "FX_DB_PATH", ":memory:"):
            first = self.h._tables()
            second = self.h._tables()
        self.assertIs(first[1], second[1])

    def test_dynamodb_mode_still_goes_to_boto3(self):
        fake_resource = mock.Mock()
        with mock.patch.object(self.h, "FX_STORAGE", "dynamodb"), \
                mock.patch.object(self.h.boto3, "resource", return_value=fake_resource) as res:
            events, leads, sessions = self.h._tables()
        res.assert_called_once_with("dynamodb")
        self.assertEqual(fake_resource.Table.call_count, 3)

    def test_a_lead_survives_a_full_round_trip_through_sqlite(self):
        """Наскрізна перевірка: POST /api/fx/lead → рядок у SQLite → його видно в load_leads()."""
        import json

        with mock.patch.object(self.h, "FX_STORAGE", "sqlite"), \
                mock.patch.object(self.h, "FX_DB_PATH", ":memory:"), \
                mock.patch.object(self.h, "TELEGRAM_BOT_TOKEN", ""):
            event = {
                "requestContext": {"http": {"method": "POST", "path": "/api/fx/lead",
                                            "sourceIp": "203.0.113.7"}},
                "headers": {"user-agent": "Mozilla/5.0 (unit test)"},
                "body": json.dumps({"name": "דנה לוי", "phone": "050-123-4567",
                                    "consent": True, "lang": "he", "size": "220"}),
                "isBase64Encoded": False,
            }
            r = self.h.lambda_handler(event, None)
            self.assertEqual(r["statusCode"], 200)
            lead_id = json.loads(r["body"])["id"]
            leads = self.h.load_leads()

        self.assertEqual([l["id"] for l in leads], [lead_id])
        self.assertEqual(leads[0]["phone"], "+972501234567")


if __name__ == "__main__":
    unittest.main()
