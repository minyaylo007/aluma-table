"""scripts/journal_watch.py — сторож журналів: шум ≠ тривога, дедуп за годину, рядок без ПД.

Без мережі й без системи: journalctl, systemctl, gh, lead-say і health підмінені; база — тимчасовий файл.
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import journal_watch as jw  # noqa: E402

NOW = datetime(2026, 10, 23, 14, 0, tzinfo=timezone.utc)


def entry(msg, unit="ihor-aluma-api.service", prio=6, cursor="c1"):
    return {"MESSAGE": msg, "_SYSTEMD_USER_UNIT": unit, "PRIORITY": str(prio), "__CURSOR": cursor,
            "__REALTIME_TIMESTAMP": str(int(NOW.timestamp() * 1e6))}


class ClassifyTests(unittest.TestCase):
    def test_known_noise_is_not_an_alarm(self):
        for msg in ("[2026-10-23 08:54:01 +0300] [123] [INFO] Worker exiting (pid: 123)",
                    "[2026-10-23 08:54:02 +0300] [124] [INFO] Booting worker with pid: 124",
                    "[2026-10-23 08:54:01 +0300] [99] [ERROR] Worker (pid:123) was sent SIGTERM!",
                    "Starting ihor-aluma-backup.service - ALUMA — hourly backup...",
                    "Finished ihor-aluma-backup.service - ALUMA — hourly backup.",
                    "ihor-aluma-backup.service: Deactivated successfully.",
                    '{"event": "backup_done", "kept": 48}',
                    '{"event": "admin_login_failed"}'):
            self.assertIsNone(jw.classify(entry(msg)), msg)

    def test_alarms(self):
        cases = {
            '{"event": "notify_failed", "id": "x"}': "notify_failed",
            '{"event": "wsgi_unhandled"}': "wsgi_unhandled",
            '{"event": "ig_refresh_failed"}': "ig_refresh_failed",
            "[2026-10-23 08:54:01 +0300] [99] [CRITICAL] WORKER TIMEOUT (pid:7)": "gunicorn CRITICAL",
            "Traceback (most recent call last):": "traceback",
            "sqlite3.OperationalError: database is locked": "error",
        }
        for msg, kind in cases.items():
            self.assertEqual(jw.classify(entry(msg)), kind, msg)
        self.assertEqual(jw.classify(entry("ihor-aluma-purge.service: Main process exited", prio=4)), "priority 4")

    def test_fingerprint_ignores_digits_and_ids(self):
        a = jw.fingerprint_text("Worker 1234 timeout id 3f9a0c1b2d")
        self.assertEqual(a, jw.fingerprint_text("Worker 99 timeout id aa00bb11cc"))


class JournalTests(unittest.TestCase):
    def test_own_unit_skipped_and_cursor_advances(self):
        out = "\n".join(json.dumps(e) for e in (
            entry("Traceback (most recent call last):", cursor="c1"),
            entry("Traceback (most recent call last):", unit=jw.SELF_UNIT, cursor="c2")))
        with mock.patch.object(jw, "run", return_value=out) as run:
            found, last = jw.journal(None, "c0")
        self.assertEqual(last, "c2")
        self.assertEqual([f["src"] for f in found], ["ihor-aluma-api.service"])
        self.assertIn("--after-cursor", run.call_args[0][0])


class DedupTests(unittest.TestCase):
    def finding(self, n=1):
        return {"src": "ihor-aluma-api.service", "kind": "notify_failed", "n": n, "key": "k", "at": NOW,
                "hint": "journalctl --user -u ihor-aluma-api.service --since '{since}'"}

    def test_once_per_hour_with_accumulated_count(self):
        state = {}
        first = jw.plan([self.finding()], state, NOW)
        self.assertEqual(len(first), 1)
        self.assertIn("×1", first[0][1])
        state["seen"][first[0][0]].update(last_sent=NOW.timestamp(), pending=0)
        for minutes in (10, 20, 30):                     # три прогони в межах години — тиша
            self.assertEqual(jw.plan([self.finding()], state, NOW + timedelta(minutes=minutes)), [])
        later = jw.plan([], state, NOW + timedelta(minutes=61))
        self.assertEqual(len(later), 1)
        self.assertIn("×3", later[0][1])

    def test_message_shape_and_no_pd(self):
        msg = jw.message(self.finding(), 7, NOW - timedelta(minutes=40), NOW)
        self.assertTrue(msg.startswith("🔴 ALUMA журнал: ihor-aluma-api.service — notify_failed ×7 за 40 хв; лог: "))
        self.assertIn("journalctl --user -u ihor-aluma-api.service --since '", msg)
        self.assertNotIn("\n", msg)

    def test_main_never_puts_journal_text_in_message(self):
        phone = "+972" + "50" + "1234567"                # складено, щоб сканер секретів не бачив номера в дереві
        secret = "Traceback phone %s name Иван bot123456:AAtokentokentoken" % phone
        out = json.dumps(entry(secret, prio=3))
        sent = []

        def fake_run(cmd, timeout=30, env=None):
            return out if cmd[0] == "journalctl" and "json" in cmd else ""

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(jw, "run", side_effect=fake_run), \
                mock.patch.object(jw, "health", return_value=[]), \
                mock.patch.object(jw.subprocess, "run", side_effect=lambda cmd, **k: sent.append(cmd) or
                                  mock.Mock(returncode=0)), \
                redirect_stdout(io.StringIO()):
            jw.main(["--data-dir", d, "--db", ""])
            jw.main(["--data-dir", d, "--db", ""])       # другий прогін у ту ж хвилину — дубля нема
            state = (pathlib.Path(d) / "journal-watch-state.json").read_text()
            self.assertEqual(oct(os.stat(pathlib.Path(d) / "journal-watch-state.json").st_mode & 0o777), "0o600")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][:2], [jw.LEAD_SAY, "aluma"])
        for leak in (phone[1:], "Иван", "AAtoken", "phone"):
            self.assertNotIn(leak, sent[0][2])
            self.assertNotIn(leak, state)


class SourcesTests(unittest.TestCase):
    def test_not_found_repeats_from_db(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "a.db")
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE fx_events (hk TEXT, rk TEXT, doc TEXT, ttl INTEGER)")
            rows = [("/p/old-link/", False)] * 3 + [("/once/", False)] + [("/p/test/", True)] * 5
            for i, (page, test) in enumerate(rows):
                rk = (NOW - timedelta(minutes=5)).isoformat() + "#%d" % i
                con.execute("INSERT INTO fx_events VALUES (?, ?, ?, 0)", ("D#2026-10-23", rk, json.dumps(
                    {"event_name": "NotFound", "page": page, "is_test": test})))
            old = (NOW - timedelta(hours=2)).isoformat()
            con.execute("INSERT INTO fx_events VALUES ('D', ?, ?, 0)", (old, json.dumps(
                {"event_name": "NotFound", "page": "/once/"})))
            con.commit()
            con.close()
            found = jw.not_found(db, NOW)
        self.assertEqual([(f["src"], f["n"]) for f in found], [("404 /p/old-link/", 3)])

    def test_login_failures_threshold(self):
        line = '{"event": "admin_login_failed"}\n'
        with mock.patch.object(jw, "run", return_value=line * 4):
            self.assertEqual(jw.login_failures(), [])
        with mock.patch.object(jw, "run", return_value=line * 5):
            self.assertEqual(jw.login_failures()[0]["n"], 5)

    def test_stale_timer(self):
        out = ("Id=ihor-aluma-backup.timer\nActiveState=active\nLastTriggerUSec=Fri 2026-10-23 11:07:00 UTC\n\n"
               "Id=ihor-aluma-purge.timer\nActiveState=active\nLastTriggerUSec=Fri 2026-10-23 04:20:00 UTC\n\n"
               "Id=ihor-aluma-digest.timer\nActiveState=inactive\nLastTriggerUSec=\n")
        with mock.patch.object(jw, "run", return_value=out):
            found = jw.stale_timers(NOW)
        self.assertEqual([(f["src"], f["kind"]) for f in found],
                         [("ihor-aluma-backup.timer", "таймер мовчить 2 год"),
                          ("ihor-aluma-digest.timer", "таймер не активний")])

    def test_ci_missing_gh_is_silent(self):
        status = {}
        with mock.patch.object(jw, "run", return_value=None):
            self.assertEqual(jw.nightly_ci(status), [])
        self.assertEqual(status["ci"], "skipped")
        with mock.patch.object(jw, "run", return_value='[{"conclusion": "failure", "databaseId": 42}]'):
            self.assertEqual(jw.nightly_ci(status)[0]["kind"], "CI failure")


if __name__ == "__main__":
    unittest.main(verbosity=2)
