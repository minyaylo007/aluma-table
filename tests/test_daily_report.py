"""scripts/daily_report.py — звіт читає SQLite коробки, а не DynamoDB.

Справжній api/store.py, справжній файл бази в тимчасовій теці; boto3 не потрібен
і не імпортується. Модель не кличеться: скрізь --no-ai або порожній ключ.

Запуск з кореня репозиторію:

    python -m unittest discover -s tests -p 'test_daily_report.py' -t .
"""

from __future__ import annotations

import contextlib
import importlib.util
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

from api import store  # noqa: E402


def import_report(blocked=()):
    """Свіжий модуль scripts/daily_report.py; імена з blocked імпортувати не можна."""
    spec = importlib.util.spec_from_file_location("daily_report_under_test",
                                                  ROOT / "scripts" / "daily_report.py")
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {name: None for name in blocked}):
        spec.loader.exec_module(mod)
    return mod


report = import_report()


def iso(dt: datetime) -> str:
    return dt.isoformat()


def day_pk(dt: datetime) -> str:
    return "D#" + dt.strftime("%Y-%m-%d")


@contextlib.contextmanager
def frozen(at: datetime):
    """datetime.now() у scripts/daily_report.py повертає at — час тесту не залежить від годинника."""
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return at.astimezone(tz) if tz else at.replace(tzinfo=None)

    with mock.patch.object(report, "datetime", Frozen):
        yield


class Box:
    """Тимчасова база з тією самою розкладкою, що пише handler.py."""

    def __init__(self, path: str):
        self.path = path
        self.events, self.leads, _ = store.tables(path)
        self.n = 0

    def event(self, name: str, when: datetime, session="s1", is_test=False, **props):
        self.n += 1
        item = {"pk": day_pk(when), "sk": f"{iso(when)}#{self.n:010d}", "session_id": session,
                "ts": iso(when), "event_name": name, "props_json": json.dumps(props),
                "device": "mobile", "utm_source": "", "utm_campaign": "",
                "ttl": int(when.timestamp()) + 180 * 86400}
        if is_test:
            item["is_test"] = True
        self.events.put_item(Item=item)

    def lead(self, when: datetime, is_test=False, **extra):
        self.n += 1
        item = {"pk": "LEAD", "sk": f"{iso(when)}#{self.n:012d}", "id": f"{self.n:012d}",
                "ts": iso(when), "city": "X", "color": "natural", "size": "220", "lang": "he",
                "comment": "", "status": "new", **extra}
        if is_test:
            item["is_test"] = True
        self.leads.put_item(Item=item)


class DailyReportSqliteTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "aluma.db")
        self.box = Box(self.db)
        self.now = datetime.now(timezone.utc)

    def tables(self):
        return report.open_tables(self.db)

    # ------------------------------------------------------------ load()

    def _window_and_test_rows(self, now: datetime):
        # Час заморожено, а «вчора» — остання хвилина попередньої доби Єрусалима, не now−24 год:
        # 25.10.2026 (кінець літнього часу) доба Єрусалима — 25 год, і now−24 год о 23:53 лишався «сьогодні»;
        # а живий now() у setUp і в load() о 23:59:59 міг потрапити в різні доби. Обидва — флак CI біля півночі.
        b = self.box
        # північ Єрусалима — рахуємо тут, а не window_start(), який перевіряємо
        local = now.astimezone(report.shop.TZ)
        today = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        b.event("page_view", now, session="a")
        b.event("page_view", today, session="first")                    # перша мить сьогодні — у вікні
        b.event("page_view", today - timedelta(minutes=1), session="b")  # 23:59 учора — лише у 7 днях
        b.event("page_view", now - timedelta(days=10), session="old")   # поза вікном 7 днів
        b.event("page_view", now, session="t", is_test=True)
        b.lead(max(now - timedelta(hours=1), today))
        b.lead(now - timedelta(days=10))                                 # поза вікном
        b.lead(max(now - timedelta(hours=2), today), is_test=True)

        with frozen(now):
            events, leads = report.load(7, False, self.tables())
            self.assertEqual(sorted(e["session_id"] for e in events), ["a", "b", "first"])
            self.assertEqual(len(leads), 1)
            self.assertFalse(leads[0].get("is_test"))

            events, leads = report.load(7, True, self.tables())
            self.assertEqual(sorted(e["session_id"] for e in events), ["a", "b", "first", "t"])
            self.assertEqual(len(leads), 2)

            events, _ = report.load(1, False, self.tables())
            self.assertEqual(sorted(e["session_id"] for e in events), ["a", "first"])

    def test_window_and_test_rows(self):
        self._window_and_test_rows(datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc))

    def test_window_at_2359_and_0001_jerusalem(self):
        """Кордон доби Asia/Jerusalem, зима й літо: о 23:59 і о 00:01 «сьогодні» — від півночі, 23:59 учора — ні."""
        tz = report.shop.TZ
        for at in (datetime(2026, 10, 20, 23, 59, 59, tzinfo=tz), datetime(2026, 10, 21, 0, 1, tzinfo=tz),
                   datetime(2026, 7, 1, 23, 59, tzinfo=tz), datetime(2026, 7, 2, 0, 1, tzinfo=tz)):
            with self.subTest(at=at.isoformat()):
                self.setUp()
                self._window_and_test_rows(at.astimezone(timezone.utc))

    def test_window_on_dst_end_day(self):
        """25.10.2026 21:53 UTC = 23:53 Єрусалима, доба в 25 год — саме тут CI впав у PR №143."""
        self._window_and_test_rows(datetime(2026, 10, 25, 21, 53, tzinfo=timezone.utc))

    def test_pages_through_more_than_one_query_page(self):
        # 1000 подій і 500 заявок на сторінку — беремо більше, щоб пройти по LastEvaluatedKey.
        # База — після півночі Asia/Jerusalem сьогодні: load(1) — це календарний день Єрусалима.
        base = max(self.now - timedelta(hours=1), report.shop.window_start(1, self.now) + timedelta(seconds=1))
        for i in range(1003):
            self.box.event("page_view", base + timedelta(microseconds=i), session=f"s{i}")
        for i in range(503):
            self.box.lead(base + timedelta(microseconds=i))
        events, leads = report.load(1, False, self.tables())
        self.assertEqual(len(events), 1003)
        self.assertEqual(len({e["session_id"] for e in events}), 1003)
        self.assertEqual(len(leads), 503)
        # заявки — від нових до старих, як query(ScanIndexForward=False) у DynamoDB
        self.assertEqual([l["ts"] for l in leads], sorted((l["ts"] for l in leads), reverse=True))

    def _newest_first_oldest_first(self, at: datetime):
        # Час заморожено: з живим now() о 00:00–00:30 UTC «now−30 хв» падає у вчорашню партицію D#<дата>,
        # і load(1) її не читав — тест падав щоночі. load(2) бере і сьогодні, і вчора.
        b = self.box
        t0 = at - timedelta(minutes=30)
        for i in range(3):
            b.event("page_view", t0 + timedelta(minutes=i), session=f"s{i}")
            b.lead(t0 + timedelta(minutes=i), comment=str(i))
        with frozen(at):
            events, leads = report.load(2, False, self.tables())
        self.assertEqual([e["session_id"] for e in events], ["s0", "s1", "s2"])
        self.assertEqual([l["comment"] for l in leads], ["2", "1", "0"])

    def test_leads_newest_first_and_events_oldest_first(self):
        self._newest_first_oldest_first(self.now.replace(hour=12, minute=0, second=0, microsecond=0))

    def test_leads_and_events_order_just_after_midnight_utc(self):
        """00:10 UTC: події за 30 хв до того — у вчорашній партиції; колишній флейк, тепер стабільно."""
        at = self.now.replace(hour=0, minute=10, second=0, microsecond=0)
        self.assertNotEqual((at - timedelta(minutes=30)).date(), at.date())
        self._newest_first_oldest_first(at)

    # ------------------------------------------------------------ без DynamoDB

    def test_module_imports_and_runs_without_boto3(self):
        mod = import_report(blocked=("boto3", "boto3.dynamodb", "boto3.dynamodb.conditions"))
        self.box.event("page_view", self.now, session="a")
        events, _ = mod.load(7, False, mod.open_tables(self.db))
        self.assertEqual(len(events), 1)
        code = (ROOT / "scripts" / "daily_report.py").read_text(encoding="utf-8").splitlines()
        self.assertEqual([l for l in code if l.lstrip().startswith(("import boto3", "from boto3"))], [])

    def test_missing_database_exits_2_and_creates_nothing(self):
        missing = os.path.join(self.tmp.name, "nope", "aluma.db")
        reports = pathlib.Path(self.tmp.name, "reports")
        err = io.StringIO()
        with mock.patch.object(report, "FX_DB_PATH", missing), \
                mock.patch.object(report, "REPORTS", reports), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = report.main(["--no-ai"])
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(missing))
        self.assertFalse(os.path.exists(os.path.dirname(missing)))
        self.assertFalse(reports.exists())
        self.assertIn("FX_DB_PATH", err.getvalue())

    # ------------------------------------------------------------ main()

    def test_main_writes_the_same_report_from_sqlite(self):
        b, now = self.box, self.now
        b.event("page_view", now, session="a")
        b.event("section_view", now, session="a", section="price")
        b.event("form_start", now, session="a")
        b.event("lead_success", now, session="a")
        b.event("page_view", now, session="b")
        b.event("whatsapp_click", now, session="b")
        b.lead(now - timedelta(minutes=5), utm_source="fb")
        reports = pathlib.Path(self.tmp.name, "reports")
        out = io.StringIO()
        with mock.patch.object(report, "FX_DB_PATH", self.db), \
                mock.patch.object(report, "REPORTS", reports), \
                mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}), \
                contextlib.redirect_stdout(out):
            rc = report.main(["--no-ai"])
        self.assertEqual(rc, 0)
        self.assertIn("visits=2 leads=1 whatsapp=1", out.getvalue())
        files = list(reports.glob("REPORT-*.md"))
        self.assertEqual(len(files), 1)
        text = files[0].read_text(encoding="utf-8")
        self.assertIn("Window: last 7 days (calendar, Asia/Jerusalem) · 6 events · 1 leads", text)
        self.assertIn("## Shop funnel (Asia/Jerusalem days)", text)
        self.assertIn("| visits | 2 | 100% |", text)
        self.assertIn("| saw the price | 1 | 50% |", text)
        self.assertIn("| left a lead | 1 | 50% |", text)
        self.assertIn("## AI analysis", text)   # --no-ai: промпт вбудовано, моделі не кликали
        raw = json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])
        self.assertEqual(raw["leads"][0]["source"], "fb")
        self.assertEqual(raw["lead_status_counts"], {"new": 1})

    def test_default_table_names_follow_env_like_handler(self):
        self.assertEqual((report.EVENTS_TABLE, report.LEADS_TABLE), ("fx_events", "fx_leads"))
        with mock.patch.dict(os.environ, {"EVENTS_TABLE": "ev2", "LEADS_TABLE": "ld2",
                                          "FX_DB_PATH": self.db}):
            mod = import_report()
        self.assertEqual((mod.EVENTS_TABLE, mod.LEADS_TABLE, mod.FX_DB_PATH), ("ev2", "ld2", self.db))
        events_t, leads_t = mod.open_tables(self.db)
        self.assertEqual((events_t.name, leads_t.name), ("ev2", "ld2"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
