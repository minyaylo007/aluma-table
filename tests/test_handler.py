"""Unit tests for api/handler.py — stdlib unittest only. No network, no AWS.

Run from the repo root (~/repos/aluma-table):

    python -m unittest tests.test_handler -v

How AWS is kept out:
  * If boto3 is not installed, a fake ``boto3`` module tree is injected into
    ``sys.modules`` BEFORE ``api.handler`` is imported, so the import never
    needs credentials or the SDK.
  * ``api.handler._tables`` is patched to return three in-memory FakeTable
    objects. Nothing here can reach the real fx_* tables.
  * Notifications now go to Telegram, not SES: ``api.handler.requests.post`` is
    patched to a recorder, so nothing leaves the machine either way.

The SQLite store behind ``_tables()`` has its own file: tests/test_store_sqlite.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_fake_boto3() -> None:
    """Satisfy ``import boto3`` and ``from boto3.dynamodb.conditions import Key``."""
    boto3_mod = types.ModuleType("boto3")
    dynamodb_mod = types.ModuleType("boto3.dynamodb")
    conditions_mod = types.ModuleType("boto3.dynamodb.conditions")

    class Key:  # minimal stand-in; the admin queries are not under test
        def __init__(self, name):
            self.name = name

        def eq(self, value):
            return ("eq", self.name, value)

    def _unavailable(*args, **kwargs):
        raise RuntimeError("boto3 is faked in tests; AWS must never be reached")

    conditions_mod.Key = Key
    dynamodb_mod.conditions = conditions_mod
    boto3_mod.dynamodb = dynamodb_mod
    boto3_mod.resource = _unavailable
    boto3_mod.client = _unavailable
    sys.modules["boto3"] = boto3_mod
    sys.modules["boto3.dynamodb"] = dynamodb_mod
    sys.modules["boto3.dynamodb.conditions"] = conditions_mod


if importlib.util.find_spec("boto3") is None:
    _install_fake_boto3()

# The handler reads its config at import time. Make the developer's shell
# irrelevant: no edge-secret gate, no notifications, and never a real db file.
for _var in ("EDGE_SECRET", "TELEGRAM_BOT_TOKEN", "OWNER_TELEGRAM_CHAT_ID", "FX_DB_PATH"):
    os.environ.pop(_var, None)
os.environ["FX_DB_PATH"] = ":memory:"

import api.handler as h  # noqa: E402  (must follow the boto3 shim)


# --------------------------------------------------------------------------- fakes


class FakeTable:
    """Just enough DynamoDB Table surface for put_lead / rate_ok."""

    def __init__(self, counter: int = 1):
        self.items = []
        self.updates = []
        self.counter = counter  # what the ADD-counter "returns" to rate_ok

    def put_item(self, Item):
        self.items.append(Item)
        return {}

    def update_item(self, **kwargs):
        self.updates.append(kwargs)
        return {"Attributes": {"n": self.counter}}


class TelegramRecorder:
    """Дублер ``requests.post``. Жодна мережа звідси не виходить."""

    def __init__(self, fail: bool = False, status: int = 200):
        self.calls = []
        self.fail = fail
        self.status = status

    def __call__(self, url, **kwargs):
        if self.fail:
            raise RuntimeError("Telegram is down")
        self.calls.append({"url": url, **kwargs})
        return types.SimpleNamespace(status_code=self.status, text="{}")

    @property
    def texts(self):
        return [c["json"]["text"] for c in self.calls]


def request(method: str, path: str, body=None, headers=None, raw_body=None) -> dict:
    """Build an HTTP API payload-v2.0 event the way API Gateway would."""
    hdrs = {"user-agent": "Mozilla/5.0 (unit test)", "content-type": "application/json"}
    if headers:
        hdrs.update(headers)
    if raw_body is None:
        raw_body = json.dumps(body, ensure_ascii=False) if body is not None else ""
    return {
        "requestContext": {"http": {"method": method, "path": path, "sourceIp": "203.0.113.7"}},
        "headers": hdrs,
        "body": raw_body,
        "isBase64Encoded": False,
    }


def lead_payload(**overrides) -> dict:
    data = {
        "name": "דנה לוי",
        "phone": "050-123-4567",
        "city": "תל אביב",
        "color": "natural",
        "size": "220",
        "lang": "he",
        "comment": "",
        "consent": True,
        "consent_marketing": False,
        "consent_text_version": "v2",
        "session_id": "s-1",
        "page": "/",
        "referrer": "",
        "device": "mobile",
        "utm_source": "fb",
        "utm_medium": "cpc",
        "utm_campaign": "c1",
        "utm_content": "",
        "utm_term": "",
        "fbclid": "",
        "website": "",  # honeypot, empty for humans
    }
    data.update(overrides)
    return data


def body_json(response: dict) -> dict:
    return json.loads(response["body"])


# --------------------------------------------------------------------------- phone


# Single source of truth for the accepted-format table; the frontend mirrors it.
PHONE_TABLE = [
    ("050-123-4567", "+972501234567", True),
    ("0501234567", "+972501234567", True),
    ("+972 50-123-4567", "+972501234567", True),
    ("972501234567", "+972501234567", True),
    ("00972501234567", "+972501234567", True),
    ("+972-050-1234567", "+972501234567", True),  # leading zero after country code
    ("03-1234567", "+97231234567", True),  # landline
    ("072-1234567", "+972721234567", True),  # 07x
    ("12345", "+12345", False),
    ("+1 212 555 0100", "+12125550100", False),  # foreign
    ("05012345678", "+9725012345678", False),  # too long
    ("501234567", "+501234567", False),  # no leading zero
    ("", "", False),
]


class NormalizePhoneTests(unittest.TestCase):
    def test_accepted_format_table(self):
        for raw, e164, plausible in PHONE_TABLE:
            with self.subTest(raw=raw):
                self.assertEqual(h.normalize_phone(raw), (e164, plausible))

    def test_plausible_output_is_always_e164_israel(self):
        for raw, e164, plausible in PHONE_TABLE:
            if plausible:
                with self.subTest(raw=raw):
                    self.assertRegex(e164, r"^\+972(5\d{8}|[23489]\d{7}|7[2-9]\d{7})$")

    def test_absurd_length_rejected_early(self):
        raw = "0" * 16
        self.assertEqual(h.normalize_phone(raw), ("+" + raw, False))
        # 15 digits is still processed by the normal rules (and fails them)
        self.assertEqual(h.normalize_phone("9" * 15)[1], False)

    def test_noise_characters_are_ignored(self):
        # RTL/LTR marks, parentheses, dots, NBSP
        self.assertEqual(h.normalize_phone("‏(050) 123.4567‎"), ("+972501234567", True))
        self.assertEqual(h.normalize_phone(" +972 50 123 4567"), ("+972501234567", True))

    def test_non_ascii_digits_are_out_of_scope(self):
        # Arabic-Indic digits are dropped, not converted -> nothing left -> not plausible
        self.assertEqual(h.normalize_phone("٠٥٠١٢٣٤٥٦٧"), ("", False))

    def test_only_one_international_prefix_is_stripped(self):
        self.assertEqual(h.normalize_phone("000972501234567")[1], False)

    def test_none_and_non_string_do_not_crash(self):
        self.assertEqual(h.normalize_phone(None), ("", False))
        self.assertEqual(h.normalize_phone(501234567), ("+501234567", False))


# --------------------------------------------------------------------------- handler


class HandlerTestCase(unittest.TestCase):
    def setUp(self):
        self.events_t, self.leads_t, self.sessions_t = FakeTable(), FakeTable(), FakeTable()
        for p in (
            mock.patch.object(h, "_tables", return_value=(self.events_t, self.leads_t, self.sessions_t)),
            mock.patch.object(h, "EDGE_SECRET", ""),
            mock.patch.object(h, "TELEGRAM_BOT_TOKEN", ""),
            mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", ""),
        ):
            p.start()
            self.addCleanup(p.stop)

    def post_lead(self, payload=None, headers=None, raw_body=None):
        return h.lambda_handler(request("POST", "/api/fx/lead", payload, headers, raw_body), None)


class HealthTests(HandlerTestCase):
    def test_health_smoke(self):
        r = h.lambda_handler(request("GET", "/api/fx/health"), None)
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(r["headers"]["content-type"], "application/json; charset=utf-8")
        b = body_json(r)
        self.assertTrue(b["ok"])
        self.assertIn("version", b)
        self.assertIn("ts", b)


class PutLeadTests(HandlerTestCase):
    def test_valid_lead_is_stored_and_acknowledged(self):
        r = self.post_lead(lead_payload())
        self.assertEqual(r["statusCode"], 200)
        b = body_json(r)
        self.assertTrue(b["ok"])
        self.assertRegex(b["id"], r"^[0-9a-f]{12}$")

        self.assertEqual(len(self.leads_t.items), 1)
        item = self.leads_t.items[0]
        self.assertEqual(item["id"], b["id"])
        self.assertEqual(item["pk"], "LEAD")
        self.assertTrue(item["sk"].endswith("#" + b["id"]))
        self.assertEqual(item["phone"], "+972501234567")
        self.assertEqual(item["phone_raw"], "050-123-4567")
        self.assertEqual(item["lang"], "he")
        self.assertEqual(item["size"], "220")
        self.assertEqual(item["color"], "natural")
        self.assertEqual(item["status"], "new")
        self.assertFalse(item["is_test"])
        self.assertEqual(item["consent_text_version"], "v2")

    def test_invalid_phone_name_consent_return_422_with_error_keys(self):
        r = self.post_lead(lead_payload(name="A", phone="12345", consent=False))
        self.assertEqual(r["statusCode"], 422)
        b = body_json(r)
        self.assertFalse(b["ok"])
        self.assertEqual(set(b["errors"]), {"name", "phone", "consent"})
        self.assertEqual(b["errors"]["phone"], "invalid")
        self.assertEqual(b["errors"]["name"], "required")
        self.assertEqual(b["errors"]["consent"], "required")
        self.assertEqual(self.leads_t.items, [])

    def test_invalid_phone_alone_is_422(self):
        for bad in ("501234567", "+1 212 555 0100", "05012345678", ""):
            with self.subTest(phone=bad):
                r = self.post_lead(lead_payload(phone=bad))
                self.assertEqual(r["statusCode"], 422)
                self.assertEqual(list(body_json(r)["errors"]), ["phone"])
        self.assertEqual(self.leads_t.items, [])

    def test_honeypot_returns_hp_and_stores_nothing(self):
        r = self.post_lead(lead_payload(website="http://spam.example"))
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(body_json(r), {"ok": True, "id": "hp"})
        self.assertEqual(self.leads_t.items, [])
        # the honeypot short-circuits before the rate counter is touched
        self.assertEqual(self.sessions_t.updates, [])

    def test_unknown_lang_is_stored_as_empty(self):
        r = self.post_lead(lead_payload(lang="xx"))
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(self.leads_t.items[0]["lang"], "")

    def test_unknown_size_is_stored_as_empty(self):
        r = self.post_lead(lead_payload(size="999"))
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(self.leads_t.items[0]["size"], "")

    def test_valid_en_160_lead(self):
        r = self.post_lead(lead_payload(lang="en", size="160", page="/en/"))
        self.assertEqual(r["statusCode"], 200)
        item = self.leads_t.items[0]
        self.assertEqual((item["lang"], item["size"], item["page"]), ("en", "160", "/en/"))

    def test_numeric_size_is_accepted_as_string(self):
        r = self.post_lead(lead_payload(size=220))
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(self.leads_t.items[0]["size"], "220")

    def test_unknown_color_is_stored_as_empty(self):
        r = self.post_lead(lead_payload(color="pink"))
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(self.leads_t.items[0]["color"], "")

    def test_missing_lang_and_size_do_not_crash(self):
        payload = lead_payload()
        del payload["lang"]
        del payload["size"]
        r = self.post_lead(payload)
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual((self.leads_t.items[0]["lang"], self.leads_t.items[0]["size"]), ("", ""))

    def test_rate_limited_returns_429(self):
        self.sessions_t.counter = h.LEADS_PER_IP_PER_HOUR + 1
        r = self.post_lead(lead_payload())
        self.assertEqual(r["statusCode"], 429)
        self.assertEqual(body_json(r), {"ok": False, "error": "rate", "field": "form"})
        self.assertEqual(self.leads_t.items, [])

    def test_rate_counter_fails_open(self):
        self.sessions_t.update_item = mock.Mock(side_effect=RuntimeError("ddb down"))
        r = self.post_lead(lead_payload())
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(len(self.leads_t.items), 1)

    def test_x_test_header_uses_own_bucket_and_marks_row(self):
        r = self.post_lead(lead_payload(), headers={"x-test": "1"})
        self.assertEqual(r["statusCode"], 200)
        self.assertTrue(self.leads_t.items[0]["is_test"])
        bucket = self.sessions_t.updates[0]["Key"]["session_id"]
        self.assertTrue(bucket.startswith("RLL#T#"), bucket)

    def test_non_dict_json_body_cannot_crash(self):
        for raw in ("[1, 2, 3]", '"just a string"', "42", "null", "not json at all", ""):
            with self.subTest(raw=raw):
                r = self.post_lead(raw_body=raw)
                self.assertEqual(r["statusCode"], 422)  # empty form, not a 500
                self.assertEqual(set(body_json(r)["errors"]), {"name", "phone", "consent"})
        self.assertEqual(self.leads_t.items, [])

    def test_base64_body_is_decoded(self):
        import base64

        ev = request("POST", "/api/fx/lead")
        ev["body"] = base64.b64encode(json.dumps(lead_payload()).encode("utf-8")).decode("ascii")
        ev["isBase64Encoded"] = True
        r = h.lambda_handler(ev, None)
        self.assertEqual(r["statusCode"], 200)

    def test_name_city_comment_are_clipped(self):
        r = self.post_lead(lead_payload(name="n" * 200, city="c" * 200, comment="x" * 2000))
        self.assertEqual(r["statusCode"], 200)
        item = self.leads_t.items[0]
        self.assertEqual(len(item["name"]), 80)
        self.assertEqual(len(item["city"]), 80)
        self.assertEqual(len(item["comment"]), 1000)

    def test_phone_raw_is_clipped_to_40(self):
        r = self.post_lead(lead_payload(phone="1" * 100))
        self.assertEqual(r["statusCode"], 422)  # 40 digits -> absurd length -> invalid

    def test_stored_item_keys_are_unchanged_plus_lang_and_attribution_time(self):
        self.post_lead(lead_payload())
        expected = {
            "pk", "sk", "id", "ts", "name", "phone", "phone_raw", "city", "color", "size", "lang",
            "comment", "consent", "consent_marketing", "consent_text_version", "session_id",
            "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid",
            "attributed_at", "page", "referrer", "device", "ip_hash", "status", "is_test",
        }
        self.assertEqual(set(self.leads_t.items[0]), expected)

    def test_attribution_timestamp_is_stored_and_clipped(self):
        self.post_lead(lead_payload(attributed_at="2026-09-09T10:00:00.000Z"))
        self.assertEqual(self.leads_t.items[0]["attributed_at"], "2026-09-09T10:00:00.000Z")
        self.leads_t.items.clear()
        self.post_lead(lead_payload(attributed_at="x" * 200))
        self.assertEqual(len(self.leads_t.items[0]["attributed_at"]), 40)
        self.leads_t.items.clear()
        payload = lead_payload()
        payload.pop("attributed_at", None)
        self.post_lead(payload)
        self.assertEqual(self.leads_t.items[0]["attributed_at"], "")

    def test_unhandled_exception_is_a_json_500(self):
        self.leads_t.put_item = mock.Mock(side_effect=RuntimeError("boom"))
        r = self.post_lead(lead_payload())
        self.assertEqual(r["statusCode"], 500)
        self.assertEqual(body_json(r), {"ok": False, "error": "internal"})


class NotifyTests(HandlerTestCase):
    def sample_item(self, **overrides):
        item = {
            "id": "abc123def456",
            "ts": "2026-09-09T10:00:00+00:00",
            "name": "דנה לוי",
            "phone": "+972501234567",
            "city": "חיפה",
            "color": "smoked",
            "size": "220",
            "lang": "he",
            "page": "/",
            "comment": "אחרי 18:00",
            "consent_marketing": True,
            "utm_source": "fb",
            "utm_campaign": "c1",
        }
        item.update(overrides)
        return item

    def configured(self, rec):
        """Увімкнути телеграм-сповіщення і підмінити requests.post дублером."""
        return (
            mock.patch.object(h, "TELEGRAM_BOT_TOKEN", "123:AAH-fake"),
            mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "555000"),
            mock.patch.object(h.requests, "post", rec),
        )

    def notify_once(self, rec, item):
        a, b, c = self.configured(rec)
        with a, b, c:
            return h.notify(item)

    def test_one_lead_sends_exactly_one_telegram_message(self):
        rec = TelegramRecorder()
        self.notify_once(rec, self.sample_item())
        self.assertEqual(len(rec.calls), 1)
        call = rec.calls[0]
        self.assertEqual(call["url"], "https://api.telegram.org/bot123:AAH-fake/sendMessage")
        self.assertEqual(call["json"]["chat_id"], "555000")
        self.assertIn("timeout", call)

    def test_message_carries_the_configuration_context(self):
        rec = TelegramRecorder()
        self.notify_once(rec, self.sample_item())
        text = rec.texts[0]
        self.assertIn("דנה לוי", text)
        self.assertIn("+972501234567", text)
        self.assertRegex(text, r"(?m)^Size:\s+220$")
        self.assertRegex(text, r"(?m)^Lang:\s+he$")
        self.assertRegex(text, r"(?m)^Page:\s+/$")
        self.assertIn("consent_marketing=yes", text)
        self.assertIn("abc123def456", text)
        self.assertIn(h.SITE_DOMAIN, text)

    def test_marketing_flag_no(self):
        rec = TelegramRecorder()
        self.notify_once(rec, self.sample_item(consent_marketing=False, lang="en", page="/en/"))
        text = rec.texts[0]
        self.assertIn("consent_marketing=no", text)
        self.assertRegex(text, r"(?m)^Lang:\s+en$")
        self.assertRegex(text, r"(?m)^Page:\s+/en/$")

    def test_never_raises_when_telegram_is_down(self):
        self.assertIsNone(self.notify_once(TelegramRecorder(fail=True), self.sample_item()))

    def test_never_raises_when_telegram_answers_4xx(self):
        rec = TelegramRecorder(status=403)
        self.assertIsNone(self.notify_once(rec, self.sample_item()))
        self.assertEqual(len(rec.calls), 1)

    def test_a_failed_notification_is_reported_on_stdout_not_swallowed(self):
        """Тихе падіння тут = лід, про який ніхто не дізнався. Хоч у лог, але скажи."""
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.notify_once(TelegramRecorder(fail=True), self.sample_item())
        line = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertEqual(line["event"], "notify_failed")
        self.assertEqual(line["id"], "abc123def456")

    def test_the_bot_token_never_reaches_the_log(self):
        """requests кладе URL (а в ньому .../bot<token>/...) у текст винятку.

        Справжній requests.post, але з'єднання падає ще до сокета — мережі нема.
        """
        import contextlib
        import io

        import urllib3.connection
        from urllib3.exceptions import NewConnectionError

        def refuse(conn):
            raise NewConnectionError(conn, "no network in tests")

        token = "123456:AAH-fake-token-that-must-not-be-logged"
        out = io.StringIO()
        with mock.patch.object(urllib3.connection.HTTPConnection, "_new_conn", refuse), \
                mock.patch.object(urllib3.connection.HTTPSConnection, "_new_conn", refuse), \
                mock.patch.object(h, "TELEGRAM_BOT_TOKEN", token), \
                mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "555000"), \
                contextlib.redirect_stdout(out):
            self.assertIsNone(h.notify(self.sample_item()))
        logged = out.getvalue()
        self.assertIn("notify_failed", logged)
        self.assertIn("/bot<token>/", logged)  # URL лишився — токена в ньому нема
        self.assertNotIn(token, logged)
        self.assertNotIn("fake-token-that-must", logged)

    def test_a_4xx_body_echoing_the_url_is_redacted_too(self):
        import contextlib
        import io

        token = "123456:AAH-fake-token-that-must-not-be-logged"

        def echo(url, **kwargs):
            # 250 + пробіл + ".../bot" = 279: без вирізання clip(300) лишив би 21 символ токена
            return types.SimpleNamespace(status_code=404, text="x" * 250 + " " + url)

        out = io.StringIO()
        with mock.patch.object(h, "TELEGRAM_BOT_TOKEN", token), \
                mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "555000"), \
                mock.patch.object(h.requests, "post", echo), contextlib.redirect_stdout(out):
            h.notify(self.sample_item())
        logged = out.getvalue()
        self.assertIn('"status": 404', logged)
        self.assertNotIn("AAH-fake", logged)  # і не обрізок: спершу вирізаємо, потім clip

    def test_never_raises_when_requests_is_missing(self):
        with mock.patch.object(h, "TELEGRAM_BOT_TOKEN", "123:AAH-fake"), \
                mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "555000"), \
                mock.patch.object(h, "requests", None):
            self.assertIsNone(h.notify(self.sample_item()))

    def test_a_lead_is_stored_even_when_the_notification_explodes(self):
        """Втратити лід через телеграм гірше, ніж втратити сповіщення."""
        a, b, _ = self.configured(None)
        with a, b, mock.patch.object(h.requests, "post", TelegramRecorder(fail=True)):
            r = self.post_lead(lead_payload())
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(len(self.leads_t.items), 1)

    def test_handler_notifies_real_leads_but_not_test_traffic(self):
        rec = TelegramRecorder()
        a, b, c = self.configured(rec)
        with a, b, c:
            self.assertEqual(self.post_lead(lead_payload(size="160", lang="en"))["statusCode"], 200)
            self.assertEqual(len(rec.calls), 1)
            text = rec.texts[0]
            self.assertRegex(text, r"(?m)^Size:\s+160$")
            self.assertRegex(text, r"(?m)^Lang:\s+en$")

            self.assertEqual(self.post_lead(lead_payload(), headers={"x-test": "1"})["statusCode"], 200)
            self.assertEqual(len(rec.calls), 1)  # тестовий трафік власника не турбує

    def test_handler_stays_quiet_when_unconfigured(self):
        rec = TelegramRecorder()
        with mock.patch.object(h.requests, "post", rec):  # токен порожній із setUp
            self.post_lead(lead_payload())
        self.assertEqual(rec.calls, [])

    def test_no_aws_client_is_ever_built_for_a_notification(self):
        rec = TelegramRecorder()
        a, b, c = self.configured(rec)
        with a, b, c, mock.patch.object(h.boto3, "client", side_effect=AssertionError("SES!")):
            self.post_lead(lead_payload())
        self.assertEqual(len(rec.calls), 1)


class DailyReportShapeTests(unittest.TestCase):
    """The report must carry lang for every lead without touching boto3."""

    def test_lead_rows_include_lang_and_existing_fields(self):
        spec = importlib.util.spec_from_file_location("daily_report", ROOT / "scripts" / "daily_report.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        leads = [
            {"ts": "2026-09-09T10:00:00+00:00", "city": "חיפה", "color": "smoked", "size": "220",
             "lang": "he", "comment": "", "status": "new", "utm_source": "fb", "consent_marketing": True},
            {"ts": "2026-09-09T11:00:00+00:00"},  # legacy row written before lang existed
        ]
        data = mod.analyse([], leads, 7)
        self.assertEqual(len(data["leads"]), 2)
        first, legacy = data["leads"]
        self.assertEqual(
            set(first),
            {"ts", "city", "colour", "size", "lang", "comment", "status", "source", "marketing_opt_in"},
        )
        self.assertEqual(first["lang"], "he")
        self.assertEqual(first["size"], "220")
        self.assertEqual(legacy["lang"], "")
        self.assertEqual(legacy["size"], "")
        self.assertEqual(legacy["source"], "direct")


if __name__ == "__main__":
    unittest.main(verbosity=2)
