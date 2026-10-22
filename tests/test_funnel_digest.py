"""scripts/funnel_digest.py: текст воронки для телефона і відправка в Telegram без даних і токена в журналі.

Справжній api/store.py на тимчасовій базі (TMPDIR — поза деревом), мережі нема: requests.post запатчено.

    python -m unittest tests.test_funnel_digest -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import funnel, store  # noqa: E402
from scripts import funnel_digest as fd  # noqa: E402

NAME = "Testname Ivanova"
PHONE = "050-000-PHONEMARK"   # не номер: сканер секретів шукає справжні формати телефонів
TOKEN = "123456:SECRET-token_value"


class Box:
    """Тимчасова база з розкладкою handler.py (як tests/test_daily_report.py)."""

    def __init__(self, path: str):
        self.events, self.leads, _ = store.tables(path)
        self.n = 0

    def event(self, name, when, session, is_test=False, utm_source="", user_agent="", fbclid_present=None,
              **props):
        self.n += 1
        item = {"pk": "D#" + when.strftime("%Y-%m-%d"), "sk": f"{when.isoformat()}#{self.n:010d}",
                "session_id": session, "ts": when.isoformat(), "event_name": name,
                "props_json": json.dumps(props), "utm_source": utm_source, "utm_campaign": "c1",
                "user_agent": user_agent, "fbclid_present": fbclid_present}
        if is_test:
            item["is_test"] = True
        self.events.put_item(Item=item)

    def lead(self, when, session, is_test=False, **extra):
        self.n += 1
        item = {"pk": "LEAD", "sk": f"{when.isoformat()}#{self.n:012d}", "id": f"{self.n:012d}",
                "ts": when.isoformat(), "session_id": session, "name": NAME, "phone": PHONE,
                "product_id": "tavor", "lang": "he", "status": "new", **extra}
        if is_test:
            item["is_test"] = True
        self.leads.put_item(Item=item)


class DigestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "aluma.db")
        self.box = Box(self.db)
        now = datetime.now(timezone.utc)
        # Після півночі Єрусалима сьогодні: «сьогодні» не залежить від години прогону.
        self.t = max(now - timedelta(minutes=5), funnel.window_start(1, now) + timedelta(seconds=1))

    def fill(self):
        b, t = self.box, self.t
        b.event("page_view", t, "a", utm_source="fb")
        b.event("ViewContent", t, "a", utm_source="fb", content_ids=["tavor"])
        b.event("AddToCart", t, "a", utm_source="fb", content_ids=["tavor"], price=4900)
        # Джерело заявки — з браузерної події Lead (рядок fx_leads funnel.compute до джерела не відносить).
        b.event("Lead", t, "a", utm_source="fb", content_ids=["tavor"])
        b.event("page_view", t, "b")
        b.event("ViewContent", t, "b", content_ids=["ofek"])
        b.event("page_view", t, "t", is_test=True)
        b.lead(t, "a")
        b.lead(t, "t", is_test=True)

    def text(self):
        events, leads = fd.load_rows(self.db)
        return fd.digest_text(events, leads)

    def run_main(self, *argv, post=None):
        buf = io.StringIO()
        post = post or mock.Mock(return_value=mock.Mock(status_code=200))
        with mock.patch.object(fd.daily_report, "FX_DB_PATH", self.db), \
                mock.patch.object(fd, "TELEGRAM_BOT_TOKEN", TOKEN), \
                mock.patch.object(fd, "OWNER_TELEGRAM_CHAT_ID", "42"), \
                mock.patch.object(fd.requests, "post", post), contextlib.redirect_stdout(buf):
            code = fd.main(list(argv))
        return code, buf.getvalue(), post

    def test_text_has_steps_and_numbers_without_personal_data(self):
        self.fill()
        text = self.text()
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("ALUMA · воронка · "))
        # Тестова сесія «t» і тестова заявка не рахуються.
        self.assertEqual(lines[1], "Сегодня: визиты 2 → карточка 2 → корзина 1 → доставка 0 → "
                                   "подтверждение 0 → заявок 1")
        self.assertTrue(lines[2].startswith("7 дней: визиты 2 → "))
        self.assertIn("TAVOR 1/1", text)
        self.assertIn("OFEK 0/1", text)
        self.assertIn("fb 1 (1 заяв.)", text)
        self.assertIn("прямые 1", text)
        self.assertIn("после «карточка» 1", text)
        for word in (NAME, "Testname", PHONE, "PHONEMARK"):
            self.assertNotIn(word, text)
        self.assertLessEqual(len(text), fd.TEXT_MAX)

    def test_meta_check_is_a_separate_line_not_in_steps(self):
        # хвиля 1: 3 «сесії» перевірки Meta (одна з прапорцем 0, дві старі без прапорця) — не в кроках і не в джерелах
        self.fill()
        b, t = self.box, self.t
        b.event("page_view", t, "m0", utm_source="facebook", user_agent="Mozilla/5.0 (X11)", fbclid_present=0)
        for sid in ("m1", "m2"):
            b.event("page_view", t, sid, utm_source="facebook", user_agent="Mozilla/5.0 (X11)")
        b.event("page_view", t, "p1", utm_source="facebook", user_agent="Mozilla/5.0 [FBAN/FBIOS;FBAV/450.0]")
        text = self.text()
        lines = text.splitlines()
        self.assertTrue(lines[1].startswith("Сегодня: визиты 3 → "), lines[1])
        self.assertIn("facebook 1", text)
        self.assertIn("Реклама Meta (7 дн.): люди 2 · проверка Meta, не люди: 3, из них 2 оценка по UA", text)
        self.assertLessEqual(len(text), fd.TEXT_MAX)

    def test_no_ads_no_ads_line(self):
        self.box.event("page_view", self.t, "b")
        self.assertNotIn("Реклама Meta", self.text())

    def test_empty_base_still_says_zero(self):
        text = self.text()
        self.assertIn("Сегодня: визитов 0", text)
        self.assertIn("7 дней: визитов 0", text)

    def test_text_is_capped(self):
        for i in range(60):
            self.box.event("ViewContent", self.t, f"s{i}", utm_source=f"src{i}", content_ids=[f"p{i:02d}" * 6])
        self.assertLessEqual(len(self.text()), fd.TEXT_MAX)

    def test_dry_run_prints_and_sends_nothing(self):
        self.fill()
        code, out, post = self.run_main("--dry-run")
        self.assertEqual(code, 0)
        post.assert_not_called()
        self.assertIn("Сегодня: визиты 2", out)
        self.assertEqual(json.loads(out.splitlines()[-1])["event"], "digest_dry_run")

    def test_sent_plain_text_one_json_line(self):
        self.fill()
        code, out, post = self.run_main()
        self.assertEqual(code, 0)
        post.assert_called_once()
        args, kw = post.call_args
        self.assertTrue(args[0].endswith("/sendMessage"))
        self.assertEqual(kw["timeout"], 5)
        self.assertEqual(kw["json"]["chat_id"], "42")
        self.assertTrue(kw["json"]["disable_web_page_preview"])
        self.assertNotIn("parse_mode", kw["json"])
        self.assertEqual(out.count("\n"), 1)
        line = json.loads(out)
        self.assertEqual(line, {"event": "digest_sent", "chars": len(kw["json"]["text"])})

    def test_telegram_error_status(self):
        code, out, _ = self.run_main(post=mock.Mock(return_value=mock.Mock(status_code=401, text=TOKEN)))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out), {"event": "digest_failed", "reason": "telegram_401"})
        self.assertNotIn(TOKEN, out)

    def test_telegram_exception_hides_token(self):
        boom = mock.Mock(side_effect=ConnectionError(f"Max retries exceeded with url: /bot{TOKEN}/sendMessage"))
        code, out, _ = self.run_main(post=boom)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["event"], "digest_failed")
        self.assertNotIn(TOKEN, out)
        self.assertNotIn("SECRET", out)

    def test_no_telegram_config(self):
        buf = io.StringIO()
        with mock.patch.object(fd.daily_report, "FX_DB_PATH", self.db), mock.patch.object(fd, "TELEGRAM_BOT_TOKEN", ""), \
                mock.patch.object(fd.requests, "post") as post, contextlib.redirect_stdout(buf):
            self.assertEqual(fd.main([]), 1)
        post.assert_not_called()
        self.assertEqual(json.loads(buf.getvalue())["reason"], "no_telegram_config")

    def test_no_db_exit_2_without_trace(self):
        missing = os.path.join(self.tmp.name, "nope.db")
        buf, err = io.StringIO(), io.StringIO()
        with mock.patch.object(fd.daily_report, "FX_DB_PATH", missing), \
                contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            self.assertEqual(fd.main([]), 2)
        self.assertEqual(json.loads(buf.getvalue()), {"event": "digest_failed", "reason": "no_db"})
        self.assertEqual(err.getvalue(), "")
        self.assertFalse(os.path.exists(missing))


if __name__ == "__main__":
    unittest.main()
