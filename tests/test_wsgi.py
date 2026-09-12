"""WSGI-адаптер: зворотний бік aparts/backend/wsgi_adapter.py.

Там Flask-застосунок прикидався лямбдою. Тут лямбда прикидається WSGI-застосунком,
щоб той самий handler.py крутився під gunicorn на власному сервері.

Перевіряємо форму event (rawPath, requestContext.http.method, headers, body,
cookies) — бо саме її читає handler.py, і саме на ній усе тримається.

    python -m pytest tests/test_wsgi.py -q
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# handler.py читає конфіг на імпорті: жоден тест не має права створити файл бази.
os.environ["FX_DB_PATH"] = ":memory:"

from werkzeug.test import Client  # noqa: E402

# handler.py робить `import boto3` на імпорті. Імпорт test_handler ставить
# фейковий boto3 у sys.modules, якщо SDK немає, — інакше
# `python -m unittest tests.test_wsgi` наодинці падає на машині без boto3, а
# всім набором виживає лише тому, що test_handler іде раніше за абеткою.
import tests.test_handler  # noqa: F401,E402

import api.handler as h  # noqa: E402
from api import wsgi  # noqa: E402


class WsgiTestCase(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(h, "EDGE_SECRET", ""),
            mock.patch.object(h, "FX_STORAGE", "sqlite"),
            mock.patch.object(h, "FX_DB_PATH", ":memory:"),
            mock.patch.object(h, "TELEGRAM_BOT_TOKEN", ""),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        h._reset_tables()
        self.addCleanup(h._reset_tables)
        self.client = Client(wsgi.application)

    def capture(self, response=None):
        """Підмінити lambda_handler і запам'ятати event, який йому дали."""
        seen = {}

        def fake(event, context):
            seen["event"] = event
            seen["context"] = context
            return response if response is not None else h.resp(200, {"ok": True})

        patch = mock.patch.object(h, "lambda_handler", fake)
        patch.start()
        self.addCleanup(patch.stop)
        return seen


class ApplicationShapeTests(WsgiTestCase):
    def test_gunicorn_entrypoint_is_a_callable_named_application(self):
        self.assertTrue(callable(wsgi.application))

    def test_health_answers_through_the_real_handler(self):
        r = self.client.get("/api/fx/health")
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.get_data(as_text=True))
        self.assertTrue(body["ok"])
        self.assertEqual(r.headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(r.headers["cache-control"], "no-store")

    def test_unknown_path_is_the_handlers_own_404(self):
        r = self.client.get("/api/fx/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(json.loads(r.get_data(as_text=True))["error"], "not found")


class EventShapeTests(WsgiTestCase):
    def test_method_and_raw_path(self):
        seen = self.capture()
        self.client.get("/admin/login")
        event = seen["event"]
        self.assertEqual(event["rawPath"], "/admin/login")
        self.assertEqual(event["requestContext"]["http"]["method"], "GET")
        self.assertEqual(event["requestContext"]["http"]["path"], "/admin/login")

    def test_method_is_upper_case_for_every_verb(self):
        for method, call in (("POST", self.client.post), ("OPTIONS", self.client.open)):
            seen = self.capture()
            if method == "OPTIONS":
                call("/api/fx/lead", method="OPTIONS")
            else:
                call("/api/fx/lead", json={})
            self.assertEqual(seen["event"]["requestContext"]["http"]["method"], method)

    def test_query_string_is_both_raw_and_parsed(self):
        seen = self.capture()
        self.client.get("/admin?range=30&q=%D7%93%D7%A0%D7%94")
        event = seen["event"]
        self.assertEqual(event["rawQueryString"], "range=30&q=%D7%93%D7%A0%D7%94")
        self.assertEqual(event["queryStringParameters"], {"range": "30", "q": "דנה"})

    def test_no_query_string_is_an_empty_string_not_none(self):
        seen = self.capture()
        self.client.get("/admin")
        self.assertEqual(seen["event"]["rawQueryString"], "")
        self.assertEqual(seen["event"]["queryStringParameters"], {})

    def test_headers_are_lower_cased_like_api_gateway(self):
        seen = self.capture()
        self.client.get("/admin", headers={"X-Test": "1", "User-Agent": "Mozilla/5.0"})
        headers = seen["event"]["headers"]
        self.assertEqual(headers["x-test"], "1")
        self.assertEqual(headers["user-agent"], "Mozilla/5.0")
        self.assertNotIn("X-Test", headers)

    def test_content_type_and_length_reach_the_headers_dict(self):
        seen = self.capture()
        self.client.post("/api/fx/lead", json={"name": "דנה"})
        headers = seen["event"]["headers"]
        self.assertTrue(headers["content-type"].startswith("application/json"))
        self.assertIn("content-length", headers)

    def test_json_body_arrives_as_text_and_is_not_base64(self):
        seen = self.capture()
        self.client.post("/api/fx/lead", json={"name": "דנה לוי", "consent": True})
        event = seen["event"]
        self.assertFalse(event["isBase64Encoded"])
        self.assertEqual(json.loads(event["body"])["name"], "דנה לוי")

    def test_form_body_arrives_verbatim_for_form_of(self):
        seen = self.capture()
        self.client.post("/admin/status", data={"sk": "s1", "status": "called"})
        self.assertEqual(h.form_of(seen["event"]), {"sk": "s1", "status": "called"})

    def test_get_without_body_is_an_empty_string(self):
        seen = self.capture()
        self.client.get("/admin")
        self.assertEqual(seen["event"]["body"], "")

    def test_cookies_are_a_list_the_way_payload_v2_sends_them(self):
        seen = self.capture()
        self.client.set_cookie("fx_adm", "tok.en", domain="localhost")
        self.client.set_cookie("fx_me", "1", domain="localhost")
        self.client.get("/admin")
        event = seen["event"]
        self.assertIn("fx_adm=tok.en", event["cookies"])
        self.assertEqual(h.cookies_of(event)["fx_me"], "1")

    def test_no_cookies_is_an_empty_list(self):
        seen = self.capture()
        self.client.get("/admin")
        self.assertEqual(seen["event"]["cookies"], [])

    def test_source_ip_comes_from_the_connection(self):
        seen = self.capture()
        self.client.get("/admin", environ_overrides={"REMOTE_ADDR": "203.0.113.7"})
        self.assertEqual(seen["event"]["requestContext"]["http"]["sourceIp"], "203.0.113.7")

    def test_x_forwarded_for_is_passed_through_for_client_ip(self):
        """nginx ставить X-Forwarded-For; client_ip() читає саме його."""
        seen = self.capture()
        self.client.get("/admin", headers={"X-Forwarded-For": "198.51.100.9, 10.0.0.1"})
        self.assertEqual(h.client_ip(seen["event"]), "198.51.100.9")

    def test_context_is_none(self):
        seen = self.capture()
        self.client.get("/admin")
        self.assertIsNone(seen["context"])


class ResponseShapeTests(WsgiTestCase):
    def test_status_headers_and_body_come_back(self):
        self.capture(response={"statusCode": 418, "headers": {"x-a": "b"}, "body": "hi"})
        r = self.client.get("/admin")
        self.assertEqual(r.status_code, 418)
        self.assertEqual(r.headers["x-a"], "b")
        self.assertEqual(r.get_data(as_text=True), "hi")

    def test_cookies_list_becomes_set_cookie_headers(self):
        self.capture(response={
            "statusCode": 303,
            "headers": {"location": "/admin"},
            "cookies": ["fx_adm=t; Path=/admin; HttpOnly", "other=1; Path=/"],
            "body": "",
        })
        r = self.client.get("/admin/login")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/admin")
        self.assertEqual(
            sorted(r.headers.getlist("Set-Cookie")),
            ["fx_adm=t; Path=/admin; HttpOnly", "other=1; Path=/"],
        )

    def test_hebrew_body_is_utf8_and_content_length_matches(self):
        text = "ליד חדש"
        self.capture(response={"statusCode": 200,
                               "headers": {"content-type": "text/html; charset=utf-8"},
                               "body": text})
        r = self.client.get("/admin")
        self.assertEqual(r.get_data(), text.encode("utf-8"))
        self.assertEqual(int(r.headers["content-length"]), len(text.encode("utf-8")))

    def test_base64_response_is_decoded(self):
        import base64

        self.capture(response={
            "statusCode": 200,
            "headers": {"content-type": "image/png"},
            "body": base64.b64encode(b"\x89PNG\r\n").decode(),
            "isBase64Encoded": True,
        })
        r = self.client.get("/admin")
        self.assertEqual(r.get_data(), b"\x89PNG\r\n")

    def call_validated(self, path="/api/fx/health"):
        """Прогнати запит через wsgiref.validate — werkzeug пробачає, gunicorn ні."""
        from wsgiref.util import setup_testing_defaults
        from wsgiref.validate import validator

        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": path,
                   "SCRIPT_NAME": "", "QUERY_STRING": ""}
        setup_testing_defaults(environ)
        seen = {}

        def start_response(status, headers, exc_info=None):
            seen["status"] = status
            seen["headers"] = headers
            return lambda chunk: None

        result = validator(wsgi.application)(environ, start_response)
        try:
            seen["body"] = b"".join(result)
        finally:
            close = getattr(result, "close", None)
            if close:
                close()
        return seen

    def test_the_app_passes_the_wsgi_validator(self):
        seen = self.call_validated()
        self.assertTrue(json.loads(seen["body"].decode("utf-8"))["ok"])

    def test_status_line_carries_a_reason_phrase(self):
        self.assertEqual(self.call_validated()["status"], "200 OK")

    def test_status_line_of_an_unusual_code_still_has_a_phrase(self):
        self.capture(response={"statusCode": 303,
                               "headers": {"location": "/admin", "content-type": "text/plain"},
                               "body": ""})
        self.assertEqual(self.call_validated("/admin/login")["status"], "303 See Other")

    def test_a_crashing_handler_is_a_500_and_not_a_stack_trace(self):
        def boom(event, context):
            raise RuntimeError("secret internal detail")

        with mock.patch.object(h, "lambda_handler", boom):
            r = self.client.get("/admin")
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secret internal detail", r.get_data(as_text=True))


class EndToEndThroughSqliteTests(WsgiTestCase):
    def test_a_lead_posted_over_wsgi_is_readable_from_the_admin_query(self):
        r = self.client.post(
            "/api/fx/lead",
            json={"name": "דנה לוי", "phone": "050-123-4567", "consent": True,
                  "lang": "he", "size": "220", "color": "natural"},
            headers={"User-Agent": "Mozilla/5.0 (integration)"},
        )
        self.assertEqual(r.status_code, 200)
        lead_id = json.loads(r.get_data(as_text=True))["id"]

        leads = h.load_leads()
        self.assertEqual([lead["id"] for lead in leads], [lead_id])
        self.assertEqual(leads[0]["name"], "דנה לוי")
        self.assertEqual(leads[0]["status"], "new")

    def test_events_posted_over_wsgi_are_stored(self):
        r = self.client.post(
            "/api/fx/event",
            json={"session_id": "s-1", "ctx": {"page": "/"},
                  "events": [{"name": "view"}, {"name": "scroll"}]},
            headers={"User-Agent": "Mozilla/5.0 (integration)"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(json.loads(r.get_data(as_text=True))["written"], 2)
        self.assertEqual(len(h.scan_events(1)), 2)


if __name__ == "__main__":
    unittest.main()
