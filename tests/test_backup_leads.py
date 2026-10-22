"""scripts/backup_leads.py: консистентна копія бази заявок, перевірка і ротація (лише свої імена).

Тимчасова база в TemporaryDirectory (TMPDIR — поза деревом, tests/README-python-tests.md), без мережі.

    python -m unittest tests.test_backup_leads -v
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sqlite3
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import backup_leads as bl  # noqa: E402

NOW = dt.datetime(2026, 10, 22, 5, 7)


def make_db(path: str, rows: int = 3) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute('CREATE TABLE "fx_leads" (pk TEXT, sk TEXT, data TEXT, PRIMARY KEY (pk, sk))')
    conn.executemany('INSERT INTO "fx_leads" VALUES (?, ?, ?)',
                     [(f"LEAD#{i}", "v", "{}") for i in range(rows)])
    conn.commit()
    return conn


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.db = os.path.join(self.dir, "aluma.db")
        self.bk = os.path.join(self.dir, "backups")
        # Зʼєднання лишається відкритим, як у живого gunicorn: частина записів може бути лише в -wal.
        self.conn = make_db(self.db)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_copy_is_consistent_and_private(self):
        result = bl.run(self.db, self.bk, "fx_leads", NOW)
        self.assertEqual(result["event"], "backup_ok")
        self.assertEqual(result["rows"], 3)
        self.assertEqual(result["kept"], 1)
        copy = os.path.join(self.bk, "aluma-20261022-0507.db")
        self.assertEqual(result["bytes"], os.path.getsize(copy))
        self.assertEqual(stat.S_IMODE(os.stat(self.bk).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(copy).st_mode), 0o600)
        # Один файл: ні -wal/-shm, ні тимчасового.
        self.assertEqual(os.listdir(self.bk), ["aluma-20261022-0507.db"])
        c = sqlite3.connect(copy)
        try:
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
            self.assertEqual(c.execute("SELECT COUNT(*) FROM fx_leads").fetchone()[0], 3)
            self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        finally:
            c.close()

    def test_new_lead_shows_in_next_copy(self):
        bl.run(self.db, self.bk, "fx_leads", NOW)
        self.conn.execute("INSERT INTO fx_leads VALUES ('LEAD#9', 'v', '{}')")
        self.conn.commit()
        result = bl.run(self.db, self.bk, "fx_leads", NOW + dt.timedelta(hours=1))
        self.assertEqual((result["rows"], result["kept"]), (4, 2))

    def test_backup_dir_tightened_if_it_exists_wide(self):
        os.mkdir(self.bk)
        os.chmod(self.bk, 0o755)
        self.assertEqual(bl.run(self.db, self.bk, "fx_leads", NOW)["event"], "backup_ok")
        self.assertEqual(stat.S_IMODE(os.stat(self.bk).st_mode), 0o700)

    def test_missing_db_fails_without_creating_it(self):
        missing = os.path.join(self.dir, "nope.db")
        self.assertEqual(bl.run(missing, self.bk, "fx_leads", NOW),
                         {"event": "backup_failed", "reason": "no_db"})
        self.assertFalse(os.path.exists(missing))

    def test_missing_leads_table_fails_and_leaves_nothing(self):
        result = bl.run(self.db, self.bk, "fx_other", NOW)
        self.assertEqual(result, {"event": "backup_failed", "reason": "no_leads_table"})
        self.assertEqual(os.listdir(self.bk), [])

    def test_integrity_failure_keeps_no_file(self):
        with mock.patch.object(bl, "_integrity_ok", return_value=False):
            result = bl.run(self.db, self.bk, "fx_leads", NOW)
        self.assertEqual(result, {"event": "backup_failed", "reason": "integrity"})
        self.assertEqual(os.listdir(self.bk), [])

    def test_rows_mismatch_keeps_no_file(self):
        real = bl._count
        calls = []

        def count(conn, table):
            calls.append(table)
            return real(conn, table) + (1 if len(calls) == 2 else 0)

        with mock.patch.object(bl, "_count", side_effect=count):
            result = bl.run(self.db, self.bk, "fx_leads", NOW)
        self.assertEqual(result, {"event": "backup_failed", "reason": "rows_mismatch"})
        self.assertEqual(os.listdir(self.bk), [])

    def test_main_prints_one_json_line_and_exit_code(self):
        out = StringIO()
        with mock.patch.multiple(bl, FX_DB_PATH=self.db, BACKUP_DIR=self.bk), redirect_stdout(out):
            self.assertEqual(bl.main(), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(set(json.loads(lines[0])), {"event", "rows", "bytes", "kept"})
        # Жодних даних заявок і шляхів у виводі.
        self.assertNotIn("LEAD#", lines[0])
        self.assertNotIn(self.dir, lines[0])

        out = StringIO()
        with mock.patch.multiple(bl, FX_DB_PATH=self.db + ".missing", BACKUP_DIR=self.bk), \
                redirect_stdout(out):
            self.assertEqual(bl.main(), 1)
        self.assertEqual(json.loads(out.getvalue()), {"event": "backup_failed", "reason": "no_db"})


class RotationTests(unittest.TestCase):
    def hourly(self, hours: int) -> list:
        return [bl.backup_name(NOW - dt.timedelta(hours=h)) for h in range(hours)]

    def test_keeps_72_recent_plus_one_per_day_for_30_days(self):
        names = self.hourly(24 * 40)  # 40 діб почасово
        keep = bl.select_keep(names, NOW)
        self.assertTrue(set(names[:72]) <= keep)
        stamps = sorted(bl._stamp(n) for n in keep - set(names[:72]))
        # По одній на добу, лише в межах 30 діб, і це найсвіжіша копія своєї доби (23:07).
        self.assertEqual(len({s.date() for s in stamps}), len(stamps))
        self.assertTrue(all(s >= NOW - dt.timedelta(days=30) for s in stamps))
        self.assertTrue(all(s.hour == 23 for s in stamps))
        self.assertEqual(len(keep), 72 + 27)  # 3 доби почасово (з них 4 дати) + ще 27 діб по одній

    def test_rotate_touches_only_our_names(self):
        with tempfile.TemporaryDirectory() as d:
            ours = self.hourly(24 * 40)
            foreign = ["aluma.db.pre-switch-20260911", "notes.txt", "aluma-2026-10-01.db",
                       "aluma-20261022-0507.db.bak", "other-20261022-0507.db", ".aluma-backup-1.tmp"]
            for n in ours + foreign:
                pathlib.Path(d, n).write_text("x")
            os.mkdir(os.path.join(d, "aluma-20200101-0000.db"))  # тека з нашим іменем — не файл
            kept = bl.rotate(d, NOW)
            left = set(os.listdir(d))
            self.assertTrue(set(foreign) <= left)
            self.assertIn("aluma-20200101-0000.db", left)
            expected = bl.select_keep(ours, NOW)
            self.assertEqual(left - set(foreign) - {"aluma-20200101-0000.db"}, expected)
            self.assertEqual(kept, len(expected))
            self.assertLess(kept, len(ours))

    def test_name_pattern(self):
        self.assertEqual(bl.backup_name(NOW), "aluma-20261022-0507.db")
        self.assertIsNone(bl._stamp("aluma-20261399-0507.db"))
        self.assertIsNone(bl._stamp(".aluma-backup-1.tmp"))


if __name__ == "__main__":
    unittest.main()
