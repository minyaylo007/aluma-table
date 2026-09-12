"""Шлях Lambda (FX_STORAGE=dynamodb) на moto — без мережі, без AWS, без Telegram.

Навіщо цей файл. Бекенд master можуть викотити на ІСНУЮЧУ Lambda fx-table-api
лише `sam deploy`, не чіпаючи статики. Тоді живий фронт (site/assets/app-next.js,
на 2026-09-11 байт-у-байт той самий файл, що
https://table.central-aparts.store/assets/app-next.ba26d2a9fb.js, якщо не зважати на CR)
говоритиме з новим handler.py. Тут доведено, що ця розмова не ламається:

  * тіло заявки рівно такої форми, яку будує прод-фронт, -> put_lead master
    -> 200 + id, лід у fx_leads, notify викликано рівно раз;
  * відповіді, які фронт уміє показати (422 з errors, 429), лишились тими самими;
  * невідомі size/lang (стара вкладка) не дають 400/422 — пишуться як "";
  * подія /api/fx/event, адмінка (вхід -> сторінка -> статус) і EDGE_SECRET;
  * правило телефону клієнта (JS) і сервера збігаються рядок у рядок — через node.

Потрібні boto3 і moto (`pip install boto3 moto`) і requests. Без них файл пропускається.
Облікові дані AWS підмінені на фіктивні, а moto перехоплює кожен виклик botocore:
справжні таблиці fx_* звідси недосяжні.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import types
import unittest
from unittest import mock
from urllib.parse import urlencode

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if importlib.util.find_spec("moto") is None or importlib.util.find_spec("boto3") is None:
    raise unittest.SkipTest("moto/boto3 не встановлені — шлях DynamoDB не перевіряється")

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

import api.handler as h  # noqa: E402

if h.requests is None:
    raise unittest.SkipTest("requests не встановлено — notify() не підмінити")

APP_JS = ROOT / "site" / "assets" / "app-next.js"
REGION = "eu-central-1"
EDGE = "edge-test-value"

# Схема ключів — з infra/template.yaml (і api/store.py.tables()): тримати однаковою.
TABLES = {
    "fx_events": [("pk", "HASH"), ("sk", "RANGE")],
    "fx_leads": [("pk", "HASH"), ("sk", "RANGE")],
    "fx_sessions": [("session_id", "HASH")],
}

FAKE_AWS_ENV = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "AWS_DEFAULT_REGION": REGION,
    "AWS_REGION": REGION,
    # жоден профіль із ~/.aws не має права підмішатись
    "AWS_CONFIG_FILE": "/nonexistent/aluma-test-aws-config",
    "AWS_SHARED_CREDENTIALS_FILE": "/nonexistent/aluma-test-aws-credentials",
}


# --------------------------------------------------------------------------- прод-фронт


def front_payload_keys() -> list[str]:
    """Ключі об'єкта `var data = {...}` із обробника submit у site/assets/app-next.js."""
    src = APP_JS.read_text(encoding="utf-8")
    m = re.search(r"var data = \{(.*?)\};", src, re.S)
    if not m:
        raise AssertionError("у app-next.js не знайдено `var data = {...};` — форма змінилась")
    return re.findall(r"(?:^|[{,])\s*(\w+):", m.group(1))


def prod_front_body(**overrides) -> dict:
    """Тіло POST /api/fx/lead рівно так, як його будує прод-фронт.

    JSON.stringify викидає undefined, тож без UTM у URL (органічний візит) ключів
    utm_*, fbclid і attributed_at у тілі просто НЕМА. color/size — атрибути
    data-oak/data-size на <html> (типово natural/160), lang — <html lang>,
    consent_text_version — CFG.consentVersion ("v2" на обох мовах проду).
    """
    data = {
        "name": "דנה לוי",
        "phone": "050-123-4567",
        "city": "",
        "comment": "",
        "website": "",
        "color": "natural",
        "size": "160",
        "consent": True,
        "consent_marketing": False,
        "consent_text_version": "v2",
        "session_id": "k9x2m4q8r1t7",
        "page": "/",
        "referrer": "",
        "device": "mobile",
        "lang": "he",
    }
    data.update(overrides)
    return data


AD_CLICK = {
    "utm_source": "facebook",
    "utm_medium": "paid",
    "utm_campaign": "aluma-oct",
    "utm_content": "reel-1",
    "utm_term": "table",
    "fbclid": "IwAR0fakeclid",
    "attributed_at": "2026-10-05T08:00:00.000Z",
}


def edge_request(method, path, body=None, headers=None, raw_body=None, cookies=None, qs=None):
    """Подія HTTP API v2.0 так, як її віддає API Gateway за CloudFront."""
    hdrs = {
        "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)",
        "content-type": "application/json",
        "x-forwarded-for": "198.51.100.23, 130.176.0.1",
        "cloudfront-viewer-country": "IL",
        "x-fx-edge": EDGE,
    }
    hdrs.update(headers or {})
    if raw_body is None:
        raw_body = json.dumps(body, ensure_ascii=False) if body is not None else ""
    event = {
        "requestContext": {"http": {"method": method, "path": path, "sourceIp": "130.176.0.1"}},
        "headers": {k: v for k, v in hdrs.items() if v is not None},
        "body": raw_body,
        "isBase64Encoded": False,
    }
    if cookies:
        event["cookies"] = cookies
    if qs:
        event["queryStringParameters"] = qs
    return event


class TelegramRecorder:
    """Дублер requests.post: записує виклик, у мережу не ходить."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return types.SimpleNamespace(status_code=200, text='{"ok":true}')


# --------------------------------------------------------------------------- база


class DynamoPathTestCase(unittest.TestCase):
    """Handler master з FX_STORAGE=dynamodb поверх moto."""

    def setUp(self):
        env = mock.patch.dict(os.environ, FAKE_AWS_ENV)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("AWS_PROFILE", None)

        aws = mock_aws()
        aws.start()
        self.addCleanup(aws.stop)

        ddb = boto3.resource("dynamodb", region_name=REGION)
        for name, schema in TABLES.items():
            ddb.create_table(
                TableName=name,
                BillingMode="PAY_PER_REQUEST",
                AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a, _ in schema],
                KeySchema=[{"AttributeName": a, "KeyType": t} for a, t in schema],
            )
        self.ddb = ddb

        self.telegram = TelegramRecorder()
        for p in (
            mock.patch.object(h, "FX_STORAGE", "dynamodb"),
            mock.patch.object(h, "EVENTS_TABLE", "fx_events"),
            mock.patch.object(h, "LEADS_TABLE", "fx_leads"),
            mock.patch.object(h, "SESSIONS_TABLE", "fx_sessions"),
            mock.patch.object(h, "EDGE_SECRET", EDGE),
            mock.patch.object(h, "ADMIN_USER", "owner"),
            mock.patch.object(h, "ADMIN_PASS", "admin-pass-test"),
            mock.patch.object(h, "IP_SALT", "salt-test"),
            mock.patch.object(h, "APP_VERSION", "0.4.0-test"),
            mock.patch.object(h, "TELEGRAM_BOT_TOKEN", "123:AAH-fake"),
            mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "555000"),
            mock.patch.object(h.requests, "post", self.telegram),
        ):
            p.start()
            self.addCleanup(p.stop)
        # кеш _ddb/_sqlite_tables міг лишитись від інших тестів або від минулого moto
        h._reset_tables()
        self.addCleanup(h._reset_tables)

    def call(self, *args, **kwargs):
        return h.lambda_handler(edge_request(*args, **kwargs), None)

    def leads(self):
        return self.ddb.Table("fx_leads").scan()["Items"]


# --------------------------------------------------------------------------- тести


class ProdFrontContractTests(DynamoPathTestCase):
    def test_builder_matches_the_shipped_form_exactly(self):
        """Якщо фронт почне слати інше поле — цей тест має впасти першим."""
        shipped = front_payload_keys()
        self.assertEqual(len(shipped), len(set(shipped)))
        self.assertEqual(set(shipped), set(prod_front_body()) | set(AD_CLICK))

    def test_organic_hebrew_lead_is_200_stored_and_notified_once(self):
        r = self.call("POST", "/api/fx/lead", prod_front_body())
        self.assertEqual(r["statusCode"], 200)
        body = json.loads(r["body"])
        self.assertEqual(set(body), {"ok", "id"})  # саме це читає фронт перед /thanks
        self.assertIs(body["ok"], True)
        self.assertRegex(body["id"], r"^[0-9a-f]{12}$")

        [item] = self.leads()
        self.assertEqual(item["id"], body["id"])
        self.assertEqual(item["pk"], "LEAD")
        self.assertEqual(item["phone"], "+972501234567")
        self.assertEqual((item["color"], item["size"], item["lang"]), ("natural", "160", "he"))
        self.assertEqual(item["consent_text_version"], "v2")
        self.assertIs(item["is_test"], False)
        self.assertEqual(item["status"], "new")
        self.assertEqual(item["utm_source"], "")

        self.assertEqual(len(self.telegram.calls), 1)
        call = self.telegram.calls[0]
        self.assertEqual(call["url"], "https://api.telegram.org/bot123:AAH-fake/sendMessage")
        self.assertEqual(call["json"]["chat_id"], "555000")
        self.assertIn("דנה לוי", call["json"]["text"])
        self.assertIn(body["id"], call["json"]["text"])

    def test_english_ad_click_lead_carries_attribution(self):
        payload = prod_front_body(
            name="Dana Levi", phone="+972 50-123-4567", city="Haifa", comment="after 18:00",
            color="smoked", size="220", lang="en", page="/en/", device="desktop",
            consent_marketing=True, **AD_CLICK,
        )
        r = self.call("POST", "/api/fx/lead", payload)
        self.assertEqual(r["statusCode"], 200)
        [item] = self.leads()
        self.assertEqual((item["color"], item["size"], item["lang"]), ("smoked", "220", "en"))
        self.assertEqual(item["utm_campaign"], "aluma-oct")
        self.assertEqual(item["attributed_at"], AD_CLICK["attributed_at"])
        text = self.telegram.calls[0]["json"]["text"]
        self.assertRegex(text, r"(?m)^Size:\s+220$")
        self.assertIn("utm_campaign=aluma-oct", text)

    def test_unknown_size_or_lang_from_a_stale_tab_is_still_200(self):
        """Конфігурація ніколи не причина відмовити: пишемо "" і приймаємо."""
        for extra in ({"size": "180"}, {"lang": "he-IL"}, {"size": None, "lang": None}, {"color": "oak"}):
            with self.subTest(extra=extra):
                payload = prod_front_body(**extra)
                for k, v in extra.items():
                    if v is None:
                        payload.pop(k)
                r = self.call("POST", "/api/fx/lead", payload,
                              headers={"x-forwarded-for": f"198.51.100.{len(self.leads()) + 50}"})
                self.assertEqual(r["statusCode"], 200, r["body"])

    def test_validation_errors_keep_the_shape_the_front_renders(self):
        r = self.call("POST", "/api/fx/lead", prod_front_body(phone="12345", consent=False, name="D"))
        self.assertEqual(r["statusCode"], 422)
        self.assertEqual(json.loads(r["body"]),
                         {"ok": False, "errors": {"name": "required", "phone": "invalid",
                                                  "consent": "required"}})
        self.assertEqual(self.leads(), [])
        self.assertEqual(self.telegram.calls, [])

    def test_sixth_real_lead_per_ip_hour_is_429_rate(self):
        codes = [self.call("POST", "/api/fx/lead", prod_front_body())["statusCode"] for _ in range(6)]
        self.assertEqual(codes, [200] * 5 + [429])
        last = self.call("POST", "/api/fx/lead", prod_front_body())
        self.assertEqual(json.loads(last["body"]), {"ok": False, "error": "rate", "field": "form"})
        self.assertEqual(len(self.telegram.calls), 5)

    def test_test_traffic_is_stored_but_does_not_ping_the_owner(self):
        """x-test: 1 -> лід із is_test=true і БЕЗ повідомлення в Telegram."""
        r = self.call("POST", "/api/fx/lead", prod_front_body(), headers={"x-test": "1"})
        self.assertEqual(r["statusCode"], 200)
        [item] = self.leads()
        self.assertIs(item["is_test"], True)
        self.assertEqual(self.telegram.calls, [])

    def test_without_the_edge_header_the_origin_says_403(self):
        r = self.call("POST", "/api/fx/lead", prod_front_body(), headers={"x-fx-edge": None})
        self.assertEqual(r["statusCode"], 403)
        self.assertEqual(self.leads(), [])


class EventAndAdminTests(DynamoPathTestCase):
    def test_event_batch_is_written_and_the_session_touched(self):
        payload = {
            "session_id": "k9x2m4q8r1t7",
            "ctx": {"page": "/", "landing_url": "/?utm_source=facebook", "referrer": "",
                    "device": "mobile", "viewport": "390x844", "lang": "he",
                    "utm_source": "facebook", "attributed_at": "2026-10-05T08:00:00.000Z"},
            "events": [{"name": "page_view", "props": {}, "ts": "2026-10-05T08:00:01.000Z", "page": "/"},
                       {"name": "size_toggle", "props": {"size": "220"}, "ts": "2026-10-05T08:00:09.000Z", "page": "/"}],
        }
        r = self.call("POST", "/api/fx/event", payload)
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(json.loads(r["body"]), {"ok": True, "written": 2})
        events = self.ddb.Table("fx_events").scan()["Items"]
        self.assertEqual(sorted(e["event_name"] for e in events), ["page_view", "size_toggle"])
        self.assertTrue(all(e["attributed_at"] == "2026-10-05T08:00:00.000Z" for e in events))
        session = self.ddb.Table("fx_sessions").get_item(Key={"session_id": "k9x2m4q8r1t7"})["Item"]
        self.assertEqual(session["utm_source"], "facebook")
        self.assertEqual(session["country"], "IL")

    def test_admin_login_dashboard_and_status_change(self):
        self.assertEqual(self.call("POST", "/api/fx/lead", prod_front_body())["statusCode"], 200)
        [lead] = self.leads()

        self.assertEqual(self.call("GET", "/admin")["statusCode"], 303)  # без куки — на вхід

        form = {"content-type": "application/x-www-form-urlencoded"}
        login = self.call("POST", "/admin/login", headers=form,
                          raw_body=urlencode({"user": "owner", "pass": "admin-pass-test"}))
        self.assertEqual(login["statusCode"], 303)
        cookie = login["cookies"][0].split(";", 1)[0]
        self.assertTrue(cookie.startswith("fx_adm="))

        page = self.call("GET", "/admin", cookies=[cookie], qs={"range": "7"})
        self.assertEqual(page["statusCode"], 200)
        self.assertIn("דנה לוי", page["body"])
        self.assertIn("v0.4.0-test", page["body"])
        self.assertNotIn("תלת־ממד", page["body"])  # рядка 3D-переглядача без історичних подій нема

        status = self.call("POST", "/admin/status", headers=form, cookies=[cookie],
                           raw_body=urlencode({"sk": lead["sk"], "status": "called", "range": "7"}))
        self.assertEqual(status["statusCode"], 303)
        stored = self.ddb.Table("fx_leads").get_item(Key={"pk": "LEAD", "sk": lead["sk"]})["Item"]
        self.assertEqual(stored["status"], "called")

    def test_health_reports_the_parameter_version(self):
        r = self.call("GET", "/api/fx/health")
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(json.loads(r["body"])["version"], "0.4.0-test")


# --------------------------------------------------------------------------- телефон: клієнт = сервер


PHONE_CORPUS = [
    "050-123-4567", "0501234567", "+972 50-123-4567", "972501234567", "00972501234567",
    "+972-050-1234567", "03-1234567", "072-1234567", "02-1234567", "08 123 4567",
    "071-1234567", "+972 (0)50 123 4567", "‏(050) 123.4567‎", " +972 50 123 4567",
    "12345", "+1 212 555 0100", "05012345678", "501234567", "", "0" * 16, "9" * 15,
    "000972501234567", "٠٥٠١٢٣٤٥٦٧", "05٠1234567", "０５０１２３４５６７",
    "050 123 4567 ext 12", "+972 2 123 4567", "0551234567", "+44 20 7946 0958",
]


@unittest.skipIf(shutil.which("node") is None, "node не встановлено")
class ClientServerPhoneParityTests(unittest.TestCase):
    """normalizePhone з app-next.js і normalize_phone з handler.py — одне правило."""

    def test_same_verdict_and_same_e164_for_every_input(self):
        src = APP_JS.read_text(encoding="utf-8")
        start = src.index("var PHONE_NATIONAL")
        end = src.index('var form = qs("#leadform")')
        script = (
            src[start:end]
            + "\nlet raw='';process.stdin.on('data',d=>raw+=d).on('end',()=>{"
            "process.stdout.write(JSON.stringify(JSON.parse(raw).map(normalizePhone)));});"
        )
        out = subprocess.run(["node", "-e", script], input=json.dumps(PHONE_CORPUS),
                             capture_output=True, text=True, timeout=30, check=True).stdout
        for raw, js in zip(PHONE_CORPUS, json.loads(out)):
            with self.subTest(raw=raw):
                self.assertEqual((js["e164"], js["ok"]), h.normalize_phone(raw))


if __name__ == "__main__":
    unittest.main()
