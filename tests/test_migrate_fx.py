"""scripts/migrate_fx.py — переїзд трьох таблиць з DynamoDB у SQLite.

DynamoDB тут не потрібен: scan підмінено дублером, який віддає дві сторінки,
щоб було видно, що скрипт ходить по LastEvaluatedKey, а не бере перший
1-мегабайтний шматок. Решта — справжня: справжній store.py, справжній файл бази.

Запуск з кореня репозиторію:

    python -m unittest discover -s tests -p 'test_migrate_fx.py' -t .
"""

from __future__ import annotations

import contextlib
import decimal
import io
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# handler.py читає конфіг на імпорті: жоден тест не має права створити файл бази.
os.environ.setdefault("FX_DB_PATH", ":memory:")

sys.path.insert(0, str(ROOT / "scripts"))
import migrate_fx  # noqa: E402


def read(*parts) -> str:
    """Прочитати файл і закрити його — інакше тести сиплють ResourceWarning."""
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def lead(n: int) -> dict:
    """Заявка рівно тієї форми, яку кладе handler.put_lead() (без ttl, is_test булевий)."""
    return {
        "pk": "LEAD",
        "sk": f"2026-09-0{n}T10:00:0{n}Z#id{n}",
        "id": f"id{n}",
        "ts": f"2026-09-0{n}T10:00:0{n}Z",
        "name": f"тест {n}",
        "phone": f"+38050000000{n}",
        "status": "new",
        "consent": True,
        "is_test": True,
    }


def event(n: int) -> dict:
    return {
        "pk": "EV#2026-09-01",
        "sk": f"2026-09-01T10:00:0{n}Z#{n}",
        "event_name": "view",
        # boto3 віддає числа Decimal'ами — саме на цьому падав би json без _plain.
        "ttl": decimal.Decimal(1800000000 + n),
        "is_test": False,
    }


def session(n: int) -> dict:
    return {
        "session_id": f"s{n}",
        "first_seen": "2026-09-01T10:00:00Z",
        "ttl": decimal.Decimal(1800000000 + n),
        "is_test": True,
    }


class FakeTable:
    """scan() двома сторінками — інакше пагінацію в скрипті нічим не піймати."""

    def __init__(self, items):
        self.items = items
        self.scans = 0

    def scan(self, **kwargs):
        self.scans += 1
        half = max(1, len(self.items) // 2)
        if not kwargs.get("ExclusiveStartKey"):
            page = self.items[:half]
            return {"Items": page, "LastEvaluatedKey": {"marker": half}} if len(self.items) > half \
                else {"Items": page}
        return {"Items": self.items[kwargs["ExclusiveStartKey"]["marker"]:]}


class FakeResource:
    def __init__(self, by_name):
        self.by_name = by_name

    def Table(self, name):
        return self.by_name[name]


class MigrateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dump_dir = os.path.join(self.tmp.name, "dump")
        self.db = os.path.join(self.tmp.name, "data", "aluma.db")
        self.events = [event(n) for n in range(1, 5)]
        self.leads = [lead(n) for n in range(1, 4)]
        self.sessions = [session(n) for n in range(1, 3)]
        self.fakes = {
            "fx_events": FakeTable(self.events),
            "fx_leads": FakeTable(self.leads),
            "fx_sessions": FakeTable(self.sessions),
        }
        from api import handler
        self.handler = handler
        self._saved = (handler.FX_STORAGE, handler.FX_DB_PATH,
                       os.environ.get("FX_STORAGE"), os.environ.get("FX_DB_PATH"))

    def tearDown(self):
        # verify перемикає handler на тимчасову базу — повертаємо як було,
        # інакше наступний тестовий файл дістане мертвий шлях.
        storage, path, env_storage, env_path = self._saved
        self.handler.FX_STORAGE, self.handler.FX_DB_PATH = storage, path
        for name, value in (("FX_STORAGE", env_storage), ("FX_DB_PATH", env_path)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.handler._reset_tables()
        self.tmp.cleanup()

    def run_phase(self, phase: str, db: str | None = None, extra=()) -> tuple[int, str]:
        argv = ["--phase", phase, "--dump-dir", self.dump_dir, "--db", db or self.db, *extra]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            if phase == "dump":
                with mock.patch("boto3.resource", return_value=FakeResource(self.fakes)):
                    code = migrate_fx.main(argv)
            else:
                code = migrate_fx.main(argv)
        return code, out.getvalue()

    def dump_and_load(self):
        self.assertEqual(self.run_phase("dump")[0], 0)
        self.assertEqual(self.run_phase("load")[0], 0)

    def resnap(self, **shrunk):
        """Другий (фінальний) знімок: TTL з'їв частину рядків, база лишилася як була.

        Дамп пише в ту саму теку через rename, тож знімок узгоджений сам із собою —
        рівно те, що станеться у вікні переїзду. load навмисно НЕ повторюємо.
        """
        for name, items in shrunk.items():
            self.fakes[name] = FakeTable(items)
        self.assertEqual(self.run_phase("dump")[0], 0)

    def doc_of(self, table: str, hk: str) -> str:
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(f'SELECT doc FROM "{table}" WHERE hk = ?', (hk,)).fetchone()[0]
        finally:
            conn.close()

    def counts(self, db: str | None = None) -> dict:
        conn = sqlite3.connect(db or self.db)
        try:
            return {
                name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                for name in ("fx_events", "fx_leads", "fx_sessions")
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------ dump

    def test_dump_walks_all_pages(self):
        self.run_phase("dump")
        self.assertGreater(self.fakes["fx_events"].scans, 1)
        manifest = json.loads(read(self.dump_dir, "manifest.json"))
        self.assertEqual(manifest["tables"]["fx_events"]["count"], len(self.events))
        self.assertEqual(manifest["total"], len(self.events) + len(self.leads) + len(self.sessions))

    def test_dump_keeps_ttl_number_and_is_test_boolean(self):
        self.run_phase("dump")
        rows = [json.loads(l) for l in read(self.dump_dir, "fx_events.jsonl").splitlines()]
        self.assertTrue(all(isinstance(r["ttl"], int) for r in rows))
        # is_test="True" виглядало б у JSON майже так само — саме тому перевіряємо тип.
        self.assertTrue(all(r["is_test"] is False for r in rows))
        raw = read(self.dump_dir, "fx_leads.jsonl")
        self.assertIn('"is_test": true', raw)
        self.assertNotIn('"is_test": "True"', raw)

    def test_dump_and_load_closed_to_others(self):
        """Типовий umask 0002 — а знімок і база однаково не ширші за 0640/0750."""
        self.addCleanup(os.umask, os.umask(0o002))
        self.dump_and_load()
        paths = [self.dump_dir, os.path.dirname(self.db), self.db]
        paths += [os.path.join(self.dump_dir, f) for f in os.listdir(self.dump_dir)]
        for path in paths:
            with self.subTest(path=os.path.basename(path)):
                self.assertEqual(os.stat(path).st_mode & 0o027, 0, oct(os.stat(path).st_mode))

    def test_dump_is_repeatable(self):
        self.run_phase("dump")
        first = read(self.dump_dir, "fx_leads.jsonl")
        self.run_phase("dump")
        self.assertEqual(first, read(self.dump_dir, "fx_leads.jsonl"))

    # ------------------------------------------------------------------ load

    def test_load_twice_does_not_duplicate(self):
        self.dump_and_load()
        first = self.counts()
        self.assertEqual(self.run_phase("load")[0], 0)
        self.assertEqual(self.counts(), first)
        self.assertEqual(first, {"fx_events": 4, "fx_leads": 3, "fx_sessions": 2})

    def test_load_fills_ttl_column(self):
        self.dump_and_load()
        conn = sqlite3.connect(self.db)
        try:
            rows = conn.execute("SELECT ttl, typeof(ttl) FROM fx_sessions").fetchall()
        finally:
            conn.close()
        self.assertTrue(rows and all(t == "integer" for _, t in rows))

    def test_load_complains_about_a_truncated_dump(self):
        self.assertEqual(self.run_phase("dump")[0], 0)
        path = os.path.join(self.dump_dir, "fx_leads.jsonl")
        lines = read(path).splitlines(keepends=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(lines[:-1])
        code, text = self.run_phase("load")
        self.assertEqual(code, 1)
        self.assertIn("УВАГА", text)

    def test_load_needs_a_dump(self):
        with self.assertRaises(SystemExit):
            self.run_phase("load")

    # ------------------------------------------------------------------ verify

    def test_verify_green_after_load(self):
        self.dump_and_load()
        code, text = self.run_phase("verify")
        self.assertEqual(code, 0, text)
        self.assertNotIn("[FAIL]", text)
        self.assertIn("ЗЕЛЕНО", text)

    def test_verify_green_after_second_load(self):
        self.dump_and_load()
        self.run_phase("load")
        self.assertEqual(self.run_phase("verify")[0], 0)

    def test_verify_red_when_a_row_is_missing(self):
        self.dump_and_load()
        conn = sqlite3.connect(self.db)
        conn.execute("DELETE FROM fx_sessions WHERE hk = 's1'")
        conn.commit()
        conn.close()
        code, text = self.run_phase("verify")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL]", text)

    def test_verify_red_when_a_key_is_swapped(self):
        """Кількість та сама, ключ інший — це має ловити саме контрольна сума."""
        self.dump_and_load()
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE fx_sessions SET hk = 'підміна' WHERE hk = 's1'")
        conn.commit()
        conn.close()
        code, text = self.run_phase("verify")
        self.assertEqual(code, 1)
        self.assertIn("sha256", text)

    def test_verify_reads_leads_through_handler(self):
        self.dump_and_load()
        code, text = self.run_phase("verify")
        self.assertEqual(code, 0, text)
        self.assertIn("load_leads()", text)
        self.assertEqual(len(migrate_fx.read_leads_through_handler(self.db)), len(self.leads))

    # -------------------------------------------------- verify --second-pass

    def test_second_pass_green_when_ttl_ate_events_and_sessions(self):
        """Головний випадок вікна: у базі законно БІЛЬШЕ рядків, ніж у фінальному знімку."""
        self.dump_and_load()
        self.resnap(fx_events=self.events[:-2], fx_sessions=self.sessions[:-1])
        code, text = self.run_phase("verify", extra=["--second-pass"])
        self.assertEqual(code, 0, text)
        self.assertIn("ЗЕЛЕНО", text)
        # Мовчазне «ок» тут марне — у звіті мусить бути видно, скільки й де розійшлося.
        self.assertIn("fx_events: кожен ключ знімка є в базі — не доїхало 0, понад знімок 2", text)
        self.assertIn("fx_sessions (TTL): зі знімка не доїхало 0, у базі понад знімок 1", text)

    def test_without_flag_the_same_snapshot_stays_red(self):
        """Без прапорця поведінка колишня: строга рівність і ЧЕРВОНО."""
        self.dump_and_load()
        self.resnap(fx_events=self.events[:-2])
        code, text = self.run_phase("verify")
        self.assertEqual(code, 1)
        self.assertIn("fx_events: рядків у SQLite — 4 проти 2", text)
        self.assertIn("sha256", text)
        self.assertNotIn("ДРУГИЙ ПРОХІД", text)

    def put_lead_in_db(self, doc: dict) -> None:
        """Заявка прямо в базу, повз знімок — як smoke або гість після переключення."""
        _, leads_t, _ = migrate_fx.store.tables(self.db, "fx_events", "fx_leads", "fx_sessions")
        leads_t.put_item(Item=doc)

    def extra_lead(self, ts: str, is_test: bool) -> dict:
        return dict(lead(9), sk=f"{ts}#id9", ts=ts, is_test=is_test)

    def test_second_pass_red_when_a_real_lead_vanished_from_snapshot(self):
        """Справжня заявка є в базі, а в DynamoDB зникла — ts до знімка нічого не пояснює."""
        self.leads[-1]["is_test"] = False
        self.dump_and_load()
        self.resnap(fx_leads=self.leads[:-1])
        code, text = self.run_phase("verify", extra=["--second-pass"])
        self.assertEqual(code, 1, text)
        self.assertIn("тестові 0, прийшли після знімка 0, непояснених 1", text)
        self.assertIn("ЧЕРВОНО", text)

    def test_second_pass_red_when_a_lead_is_missing_from_db(self):
        """Пропажа: заявка є у знімку, у базу не доїхала."""
        self.dump_and_load()
        conn = sqlite3.connect(self.db)
        conn.execute("DELETE FROM fx_leads WHERE rk = ?", (self.leads[0]["sk"],))
        conn.commit()
        conn.close()
        code, text = self.run_phase("verify", extra=["--second-pass"])
        self.assertEqual(code, 1, text)
        self.assertIn("fx_leads: кожна заявка знімка є в базі — не доїхало 1", text)

    def test_second_pass_red_when_a_lead_changed_content(self):
        """Той самий ключ, інший статус — ловить звірка вмісту, а не ключів."""
        self.dump_and_load()
        doc = json.loads(self.doc_of("fx_leads", "LEAD"))
        doc["status"] = "deposit"
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE fx_leads SET doc = ? WHERE rk = ?",
                     (json.dumps(doc, ensure_ascii=False), doc["sk"]))
        conn.commit()
        conn.close()
        code, text = self.run_phase("verify", extra=["--second-pass"])
        self.assertEqual(code, 1, text)
        self.assertIn("fx_leads: вміст рядків знімка збігається з базою — розбіжностей 1", text)

    def test_second_pass_green_with_an_extra_test_lead(self):
        """Smoke пише заявку з is_test у живу базу — це не втрата і не підміна."""
        self.dump_and_load()
        self.put_lead_in_db(self.extra_lead("2026-09-01T00:00:00Z", is_test=True))
        code, text = self.run_phase("verify", extra=["--second-pass"])
        self.assertEqual(code, 0, text)
        self.assertIn("тестові 1, прийшли після знімка 0, непояснених 0", text)

    def test_second_pass_green_with_a_real_lead_after_snapshot(self):
        """Гість написав уже на коробку, після знімка — у DynamoDB її бути не може."""
        self.dump_and_load()
        self.put_lead_in_db(self.extra_lead("2099-01-01T00:00:00+00:00", is_test=False))
        code, text = self.run_phase("verify", extra=["--second-pass"])
        self.assertEqual(code, 0, text)
        self.assertIn("тестові 0, прийшли після знімка 1, непояснених 0", text)

    def test_second_pass_red_with_a_real_lead_before_snapshot(self):
        """Нетестова заявка старша за знімок мала б бути в DynamoDB — непояснено, червоне."""
        self.dump_and_load()
        self.put_lead_in_db(self.extra_lead("2026-09-01T00:00:00Z", is_test=False))
        code, text = self.run_phase("verify", extra=["--second-pass"])
        self.assertEqual(code, 1, text)
        self.assertIn("непояснених 1", text)

    def test_leads_since_covers_box_leads_older_than_the_final_snapshot(self):
        """Вікно: гість написав на коробку ПІСЛЯ першого знімка, але ДО фінального."""
        self.dump_and_load()
        self.put_lead_in_db(self.extra_lead("2026-09-05T00:00:00Z", is_test=False))
        self.assertEqual(self.run_phase("verify", extra=["--second-pass"])[0], 1)
        code, text = self.run_phase(
            "verify", extra=["--second-pass", "--leads-since", "2026-09-04T00:00:00Z"])
        self.assertEqual(code, 0, text)
        self.assertIn("тестові 0, прийшли після --leads-since 1, непояснених 0", text)
        # Старша за поріг — однаково червоне: поріг не вимикає перевірку.
        code, text = self.run_phase(
            "verify", extra=["--second-pass", "--leads-since", "2026-09-06T00:00:00Z"])
        self.assertEqual(code, 1, text)
        self.assertIn("непояснених 1", text)

    def test_leads_since_must_be_iso(self):
        self.dump_and_load()
        with self.assertRaises(SystemExit):
            self.run_phase("verify", extra=["--second-pass", "--leads-since", "вчора"])

    def test_first_pass_still_strict_about_an_extra_test_lead(self):
        """Без прапорця — як було: будь-яка зайва заявка дає ЧЕРВОНО."""
        self.dump_and_load()
        self.put_lead_in_db(self.extra_lead("2026-09-01T00:00:00Z", is_test=True))
        code, text = self.run_phase("verify")
        self.assertEqual(code, 1, text)
        self.assertIn("fx_leads: рядків у SQLite — 4 проти 3", text)

    def test_classify_extra_leads_unparsable_ts_is_unexplained(self):
        taken = "2026-09-11T11:02:12.816423+00:00"
        docs = [{"id": "a", "is_test": True}, {"id": "b", "is_test": False, "ts": "nonsense"},
                {"id": "c", "is_test": False, "ts": "2026-09-11T11:02:13+00:00"},
                {"id": "d", "is_test": False, "ts": "2026-09-11T11:02:12Z"}]
        self.assertEqual(migrate_fx.classify_extra_leads(docs, taken), (1, 1, 2, {"a", "c"}))

    def test_second_pass_red_when_a_key_is_missing_from_db(self):
        """Зворотний бік: рядок є у знімку, а в базу не доїхав. Це не TTL, це втрата."""
        self.dump_and_load()
        conn = sqlite3.connect(self.db)
        conn.execute("DELETE FROM fx_events WHERE rk = ?", ("2026-09-01T10:00:01Z#1",))
        conn.commit()
        conn.close()
        code, text = self.run_phase("verify", extra=["--second-pass"])
        self.assertEqual(code, 1, text)
        self.assertIn("не доїхало 1", text)

    def test_second_pass_red_when_a_row_changed_content(self):
        """Послаблення торкається кількості, а не вмісту: підмінений doc мусить червоніти."""
        self.dump_and_load()
        doc = json.loads(self.doc_of("fx_sessions", "s1"))
        doc["first_seen"] = "1999-01-01T00:00:00Z"
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE fx_sessions SET doc = ? WHERE hk = ?",
                     (json.dumps(doc, ensure_ascii=False), "s1"))
        conn.commit()
        conn.close()
        code, text = self.run_phase("verify", extra=["--second-pass"])
        self.assertEqual(code, 1, text)
        self.assertIn("вміст рядків знімка збігається з базою — розбіжностей 1", text)

    def test_second_pass_does_not_break_an_honest_pair(self):
        """Знімок = база: з прапорцем і без нього однаково ЗЕЛЕНО."""
        self.dump_and_load()
        self.assertEqual(self.run_phase("verify")[0], 0)
        code, text = self.run_phase("verify", extra=["--second-pass"])
        self.assertEqual(code, 0, text)
        self.assertIn("fx_leads: зі знімка не доїхало 0; зайві в базі — тестові 0,"
                      " прийшли після знімка 0, непояснених 0", text)

    def test_relaxed_only_with_flag_and_only_for_ttl_tables(self):
        for name in ("fx_events", "fx_sessions"):
            self.assertTrue(migrate_fx.relaxed_for_ttl(name, True))
            self.assertFalse(migrate_fx.relaxed_for_ttl(name, False))
        self.assertFalse(migrate_fx.relaxed_for_ttl("fx_leads", True))

    # ------------------------------------------------------------------ дрібниці

    def test_key_of_sessions_has_empty_range_key(self):
        self.assertEqual(migrate_fx.key_of({"session_id": "s1"}, ("session_id",)), ("s1", ""))
        self.assertEqual(migrate_fx.key_of({"pk": "LEAD", "sk": "x"}, ("pk", "sk")), ("LEAD", "x"))

    def test_checksum_ignores_order_but_not_content(self):
        a = [("b", ""), ("a", "")]
        self.assertEqual(migrate_fx.checksum(a), migrate_fx.checksum(reversed(a)))
        self.assertNotEqual(migrate_fx.checksum(a), migrate_fx.checksum([("a", ""), ("c", "")]))

    def test_region_precedence(self):
        with mock.patch.dict(os.environ, {"AWS_REGION": "eu-west-1"}, clear=False):
            self.assertEqual(migrate_fx.region_of(None), "eu-west-1")
            self.assertEqual(migrate_fx.region_of("us-east-1"), "us-east-1")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(migrate_fx.region_of(None), migrate_fx.DEFAULT_REGION)


if __name__ == "__main__":
    unittest.main()
