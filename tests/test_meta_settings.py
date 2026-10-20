"""Налаштування власника, публічний конфіг і Meta Conversions API (specs/002-meta-settings).

Без мережі: requests.post підмінено записувачем; налаштування — SQLite у пам'яті на кожен тест;
три таблиці заявок/подій — FakeTable з tests/test_handler.py. Головне, що тут доводиться:
токен CAPI не виходить ні в одну відповідь і ні в один рядок журналу, а заявка зберігається
навіть тоді, коли Meta лежить.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import types
import unittest
from unittest import mock
from urllib.parse import urlencode

from tests.test_handler import FakeTable, body_json, h, lead_payload, request

TOKEN = "EAAtesttoken" + "x" * 60          # синтетика, не справжній маркер
PIXEL = "123456789012345"
# Синтетичні номери склеєні з частин, щоб secret-scan не приймав їх за справжні ПД.
LOCAL = "050-123-" + "4567"
WA_RAW = "+972 50 123 " + "4567"
E164 = "+97250" + "1234567"
E164_B = "+97252" + "1234567"
E164_C = "+97253" + "1234567"
GOOD_FORM = {
    "contact_name": "ALUMA", "contact_phone": LOCAL, "contact_email": "Hello@example.com",
    "contact_city": "תל אביב", "wa_number": WA_RAW, "pixel_id": PIXEL,
    "capi_token": TOKEN, "test_event_code": "TEST12345", "clarity_id": "abcdef1234", "launch_mode": "on",
}


class Recorder:
    """Дублер requests.post: пише виклики, відповідає заданим кодом або падає."""

    def __init__(self, status=200, fail=False):
        self.calls, self.status, self.fail = [], status, fail

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.fail:
            raise RuntimeError(f"connection refused for {url} token={TOKEN}")
        return types.SimpleNamespace(status_code=self.status, text='{"error":{"message":"secret body"}}')


class Base(unittest.TestCase):
    def setUp(self):
        self.events_t, self.leads_t, self.sessions_t = FakeTable(), FakeTable(), FakeTable()
        self.settings_t = h.store.SqliteStore(":memory:").table("fx_settings", ("pk", "sk"))
        self.rec = Recorder()
        for p in (
            mock.patch.object(h, "_tables", return_value=(self.events_t, self.leads_t, self.sessions_t)),
            mock.patch.object(h, "_settings_table", return_value=self.settings_t),
            mock.patch.object(h, "EDGE_SECRET", ""),
            mock.patch.object(h, "TELEGRAM_BOT_TOKEN", ""),
            mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", ""),
            mock.patch.object(h, "ADMIN_USER", "owner"),
            mock.patch.object(h, "ADMIN_PASS", "pw-for-tests"),
            mock.patch.object(h, "scan_events", return_value=[]),
            mock.patch.object(h, "load_leads", return_value=[]),
            mock.patch.object(h.requests, "post", self.rec),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.out = io.StringIO()
        stack = contextlib.ExitStack()
        stack.enter_context(contextlib.redirect_stdout(self.out))
        self.addCleanup(stack.close)

    def admin(self, method, path, form=None, headers=None, query=None, auth=True):
        hdrs = {"content-type": "application/x-www-form-urlencoded", "host": "table.example"}
        if auth:
            hdrs["cookie"] = "fx_adm=" + h.make_token()
        hdrs.update(headers or {})
        ev = request(method, path, headers=hdrs, raw_body=urlencode(form or {}))
        ev["queryStringParameters"] = query or {}
        return h.lambda_handler(ev, None)

    def save(self, **overrides):
        form = dict(GOOD_FORM, **overrides)
        return self.admin("POST", "/admin/settings", form)

    def assert_no_token(self, *texts):
        for text in texts + (self.out.getvalue(),):
            self.assertNotIn(TOKEN, text)
            self.assertNotIn("EAAtesttoken", text)


class SettingsPageTests(Base):
    def test_requires_login(self):
        for method, path in (("GET", "/admin/settings"), ("POST", "/admin/settings"),
                             ("POST", "/admin/settings/test"), ("GET", "/admin/leads.csv")):
            r = self.admin(method, path, GOOD_FORM, auth=False)
            self.assertEqual(r["statusCode"], 303, path)
            self.assertEqual(r["headers"]["location"], "/admin/login")
        self.assertIsNone(self.settings_t.get_item(Key={"pk": "SETTINGS", "sk": "current"}).get("Item"))

    def test_save_normalises_and_redirects(self):
        r = self.save()
        self.assertEqual(r["statusCode"], 303)
        self.assertEqual(r["headers"]["location"], "/admin/settings?m=saved")
        s = h.load_settings()
        self.assertEqual(s["contact_phone"], E164)
        self.assertEqual(s["wa_number"], "972501234567")
        self.assertEqual(s["contact_email"], "hello@example.com")
        self.assertEqual(s["pixel_id"], PIXEL)
        self.assertEqual(s["capi_token"], TOKEN)
        self.assertTrue(s["launch_mode"])

    def test_token_is_never_shown_back(self):
        self.save()
        r = self.admin("GET", "/admin/settings")
        self.assertEqual(r["statusCode"], 200)
        self.assertIn("задан", r["body"])
        self.assert_no_token(r["body"])
        # і в сторінці з помилкою теж
        r = self.save(wa_number="abc", capi_token="")
        self.assertEqual(r["statusCode"], 422)
        self.assert_no_token(r["body"])

    def test_blank_token_keeps_and_clear_flag_erases(self):
        self.save()
        self.save(capi_token="", contact_city="חיפה")
        self.assertEqual(h.load_settings()["capi_token"], TOKEN)
        self.save(capi_token="", capi_token_clear="1")
        self.assertEqual(h.load_settings()["capi_token"], "")

    def test_any_error_saves_nothing(self):
        self.save()
        for field, bad in (("wa_number", "12345"), ("wa_number", "phone me"), ("pixel_id", "12ab"),
                           ("contact_email", "nope"), ("clarity_id", "x!"), ("test_event_code", "a b"),
                           ("capi_token", "short"), ("contact_phone", "123")):
            r = self.save(**{field: bad, "contact_city": "changed"})
            self.assertEqual(r["statusCode"], 422, (field, bad))
            self.assertIn("Не сохранено", r["body"])
            self.assertEqual(h.load_settings()["contact_city"], "תל אביב", field)

    def test_launch_mode_defaults_on_and_can_be_turned_off(self):
        self.assertTrue(h.load_settings()["launch_mode"])
        form = dict(GOOD_FORM)
        form.pop("launch_mode")
        self.admin("POST", "/admin/settings", form)
        self.assertFalse(h.load_settings()["launch_mode"])

    def test_audit_has_who_when_field_but_no_values(self):
        self.save()
        self.save(capi_token="", capi_token_clear="1", contact_city="")
        rows = h.load_audit(50)
        fields = {(r["field"], r["action"]) for r in rows}
        self.assertIn(("capi_token", "set"), fields)
        self.assertIn(("capi_token", "cleared"), fields)
        self.assertIn(("contact_city", "cleared"), fields)
        for r in rows:
            self.assertEqual(r["who"], "owner")
            self.assertTrue(r["ts"])
            blob = json.dumps(r, ensure_ascii=False)
            self.assertNotIn(TOKEN, blob)
            self.assertNotIn("501234567", blob)
        page = self.admin("GET", "/admin/settings")["body"]
        self.assertIn("Журнал изменений", page)

    def test_unchanged_save_writes_no_audit(self):
        self.save()
        n = len(h.load_audit(50))
        r = self.save(capi_token="")
        self.assertEqual(r["headers"]["location"], "/admin/settings?m=nochange")
        self.assertEqual(len(h.load_audit(50)), n)

    def test_cross_site_post_is_refused(self):
        r = self.admin("POST", "/admin/settings", GOOD_FORM, headers={"origin": "https://evil.example"})
        self.assertEqual(r["statusCode"], 403)
        self.assertEqual(h.load_settings()["pixel_id"], "")
        r = self.admin("POST", "/admin/settings/test", headers={"origin": "null"})
        self.assertEqual(r["statusCode"], 403)
        r = self.admin("POST", "/admin/settings", GOOD_FORM, headers={"origin": "https://table.example"})
        self.assertEqual(r["statusCode"], 303)

    def test_html_in_fields_is_escaped(self):
        self.save(contact_name='<script>alert(1)</script>"')
        body = self.admin("GET", "/admin/settings")["body"]
        self.assertNotIn("<script>alert", body)
        self.assertIn("&lt;script&gt;", body)

    def test_page_has_russian_instructions_and_checklist(self):
        body = self.admin("GET", "/admin/settings")["body"]
        for text in ("Events Manager", "Сгенерировать маркер доступа", "WhatsApp Business", "Готовность к тесту",
                     "Проверить"):
            self.assertIn(text, body)
        self.assertEqual(body.count("✗"), 9)   # пусто — усе ✗
        self.save()
        body = self.admin("GET", "/admin/settings")["body"]
        self.assertEqual(body.count("✓"), 5)   # піксель, токен, WhatsApp, контакти, נגישות (із контактів)

    def test_checklist_reads_own_events_and_leads_without_data(self):
        events = [{"event_name": "PageView", "ts": "2026-10-21T05:00:00Z"},
                  {"event_name": "lead_success", "ts": "2026-10-21T05:10:00Z"},
                  {"event_name": "PageView", "ts": "2026-10-21T06:00:00Z", "is_test": True}]
        leads = [{"ts": "2026-10-21T05:10:01Z", "name": "דנה לוי", "phone": E164}]
        with mock.patch.object(h, "scan_events", return_value=events), \
                mock.patch.object(h, "load_leads", return_value=leads):
            body = self.admin("GET", "/admin/settings")["body"]
        self.assertIn("2026-10-21 05:00 UTC", body)
        self.assertIn("2026-10-21 05:10 UTC", body)
        self.assertNotIn("06:00", body)
        self.assertNotIn("דנה", body)
        self.assertNotIn("501234567", body)


class PublicConfigTests(Base):
    def test_defaults_when_nothing_saved(self):
        r = h.lambda_handler(request("GET", "/api/fx/config"), None)
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(r["headers"]["cache-control"], "public, max-age=60")
        self.assertEqual(body_json(r), {
            "pixel_id": None, "wa_number": None, "clarity_id": None,
            "contact": {"name": None, "phone": None, "email": None, "city": None, "business_id": None},
            "accessibility_contact": {"name": None, "phone": None, "email": None}, "launch_mode": True})

    def test_contract_after_save_and_no_secrets(self):
        self.save()
        r = h.lambda_handler(request("GET", "/api/fx/config"), None)
        b = body_json(r)
        self.assertEqual(set(b), {"pixel_id", "wa_number", "clarity_id", "contact", "accessibility_contact", "launch_mode"})
        self.assertEqual(b["pixel_id"], PIXEL)
        self.assertEqual(b["wa_number"], "972501234567")
        self.assertEqual(b["contact"]["phone"], E164)
        self.assertNotIn("TEST12345", r["body"])
        self.assert_no_token(r["body"])

    def test_accessibility_contact_falls_back_to_site_contact(self):
        self.save()
        a = body_json(h.lambda_handler(request("GET", "/api/fx/config"), None))["accessibility_contact"]
        self.assertEqual(a, {"name": "ALUMA", "phone": E164, "email": "hello@example.com"})
        self.save(a11y_name="רכז נגישות", a11y_email="a11y@example.com", business_id="51-234567-8")
        b = body_json(h.lambda_handler(request("GET", "/api/fx/config"), None))
        self.assertEqual(b["accessibility_contact"], {"name": "רכז נגישות", "phone": E164, "email": "a11y@example.com"})
        self.assertEqual(b["contact"]["business_id"], "512345678")

    def test_accessibility_and_business_id_are_validated(self):
        for field, bad in (("a11y_phone", "123"), ("a11y_email", "nope"), ("business_id", "1234")):
            r = self.save(**{field: bad})
            self.assertEqual(r["statusCode"], 422, field)
        body = self.admin("GET", "/admin/settings")["body"]
        self.assertIn("רכז/ת נגישות", body)
        self.assertIn("תקנה 35", body)

    def test_broken_storage_still_answers_defaults(self):
        broken = mock.Mock()
        broken.get_item.side_effect = RuntimeError("db locked")
        with mock.patch.object(h, "_settings_table", return_value=broken):
            r = h.lambda_handler(request("GET", "/api/fx/config"), None)
        self.assertEqual(r["statusCode"], 200)
        self.assertIsNone(body_json(r)["pixel_id"])


class LeadFieldsTests(Base):
    def post(self, headers=None, **fields):
        return h.lambda_handler(request("POST", "/api/fx/lead", lead_payload(**fields), headers), None)

    def test_new_fields_are_stored(self):
        r = self.post(product_id="extending-table", size_label="180×90", finish_id="natural", base_id="steel-black",
                      timeframe="1-3m", contact_pref="whatsapp", email="A@B.co", event_id="lead.abc123.def")
        self.assertEqual(r["statusCode"], 200)
        item = self.leads_t.items[0]
        self.assertEqual(item["product_id"], "extending-table")
        self.assertEqual(item["size_label"], "180×90")
        self.assertEqual(item["timeframe"], "1-3m")
        self.assertEqual(item["contact_pref"], "whatsapp")
        self.assertEqual(item["email"], "a@b.co")
        self.assertEqual(item["event_id"], "lead.abc123.def")

    def test_unknown_values_become_empty_and_never_refuse(self):
        r = self.post(product_id="<b>", size_label="x" * 80, finish_id="Bad Id", timeframe="tomorrow",
                      contact_pref="pigeon", email="nope", event_id="!")
        self.assertEqual(r["statusCode"], 200)
        item = self.leads_t.items[0]
        for key in ("product_id", "finish_id", "timeframe", "contact_pref", "email"):
            self.assertEqual(item[key], "", key)
        self.assertEqual(item["size_label"], "x" * 40)   # вільний текст обрізається, не відкидається
        self.assertRegex(item["event_id"], r"^lead\.[0-9a-f]{16}$")

    def test_marketing_consent_is_explicit_and_timed(self):
        for value, expected in ((True, True), ("true", True), ("on", True), (False, False), ("false", False),
                                ("0", False), (None, False), ("yes please", False)):
            self.leads_t.items.clear()
            self.post(marketing_consent=value)
            item = self.leads_t.items[0]
            self.assertIs(item["consent_marketing"], expected, value)
            self.assertEqual(bool(item["consent_marketing_at"]), expected, value)
            if expected:
                self.assertEqual(item["consent_marketing_at"], item["ts"])
        self.leads_t.items.clear()
        self.post(consent_marketing=True)                  # стара назва поля з app.js
        self.assertTrue(self.leads_t.items[0]["consent_marketing"])
        self.leads_t.items.clear()
        r = self.post(marketing_consent=False)             # без згоди на рекламу заявка все одно приймається
        self.assertEqual(r["statusCode"], 200)

    def test_old_checks_unchanged(self):
        r = self.post(name="A", phone="123", consent=False, product_id="extending-table")
        self.assertEqual(r["statusCode"], 422)
        self.assertEqual(set(body_json(r)["errors"]), {"name", "phone", "consent"})
        self.assertEqual(self.leads_t.items, [])

    def test_telegram_message_carries_product_choice(self):
        with mock.patch.object(h, "TELEGRAM_BOT_TOKEN", "123:abc"), \
                mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "42"):
            self.post(product_id="console", size_label="130", finish_id="walnut", base_id="wood",
                      timeframe="now", contact_pref="call")
        text = self.rec.calls[0]["json"]["text"]
        for part in ("console", "130", "walnut", "wood", "now", "call"):
            self.assertIn(part, text)


class CapiTests(Base):
    def configure(self, **overrides):
        self.save(**overrides)
        self.rec.calls.clear()

    def post(self, headers=None, cookies="", **fields):
        hdrs = {"user-agent": "Mozilla/5.0 (iPhone)", "x-forwarded-for": "198.51.100.9"}
        if cookies:
            hdrs["cookie"] = cookies
        hdrs.update(headers or {})
        return h.lambda_handler(request("POST", "/api/fx/lead", lead_payload(**fields), hdrs), None)

    def test_no_request_when_not_configured(self):
        self.post()
        self.save(pixel_id="", capi_token="")
        self.rec.calls.clear()
        self.post()
        self.assertEqual(self.rec.calls, [])

    def test_real_lead_sends_one_deduplicated_lead_with_hashes(self):
        self.configure()
        self.post(event_id="lead.k1.abcdef", product_id="round-table", email="Dana@example.com",
                  cookies="_fbp=fb.1.1700000000000.123; _fbc=fb.1.1700000000000.AbC")
        self.assertEqual(len(self.rec.calls), 1)
        call = self.rec.calls[0]
        self.assertEqual(call["url"], f"https://graph.facebook.com/{h.META_GRAPH_VERSION}/{PIXEL}/events")
        self.assertNotIn(TOKEN, call["url"])
        payload = call["json"]
        self.assertEqual(payload["access_token"], TOKEN)
        self.assertNotIn("test_event_code", payload)   # справжня заявка — без тестового коду
        ev = payload["data"][0]
        self.assertEqual(ev["event_name"], "Lead")
        self.assertEqual(ev["event_id"], "lead.k1.abcdef")
        self.assertEqual(ev["action_source"], "website")
        self.assertEqual(ev["event_source_url"], "https://table.central-aparts.store/")
        ud = ev["user_data"]
        sha = lambda v: hashlib.sha256(v.encode()).hexdigest()  # noqa: E731
        self.assertEqual(ud["ph"], [sha("972501234567")])
        self.assertEqual(ud["em"], [sha("dana@example.com")])
        self.assertEqual(ud["country"], [sha("il")])
        self.assertEqual(ud["fn"], [sha("דנה")])
        self.assertEqual(ud["fbp"], "fb.1.1700000000000.123")
        self.assertEqual(ud["fbc"], "fb.1.1700000000000.AbC")
        self.assertEqual(ud["client_ip_address"], "198.51.100.9")
        self.assertEqual(ud["client_user_agent"], "Mozilla/5.0 (iPhone)")
        blob = json.dumps(ev, ensure_ascii=False)
        self.assertNotIn("501234567", blob)
        self.assertNotIn("Dana", blob)
        self.assertNotIn("dana@", blob)
        self.assertEqual(ev["custom_data"]["content_ids"], ["round-table"])
        status = self.settings_t.get_item(Key={"pk": "CAPI", "sk": "status"})["Item"]
        self.assertTrue(status["ok"])
        self.assertEqual(status["source"], "lead")

    def test_test_traffic_sends_nothing(self):
        self.configure()
        self.post(headers={"x-test": "1"})
        self.assertEqual(self.rec.calls, [])

    def test_meta_down_lead_still_saved_and_log_has_no_token(self):
        self.configure()
        self.rec.fail = True
        r = self.post()
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(len(self.leads_t.items), 1)
        lines = [json.loads(x) for x in self.out.getvalue().splitlines() if x.startswith("{")]
        failed = [x for x in lines if x.get("event") == "capi_failed"]
        self.assertEqual(len(failed), 1)
        self.assert_no_token(r["body"])

    def test_meta_4xx_logs_status_without_body(self):
        self.configure()
        self.rec.status = 400
        self.post()
        log = self.out.getvalue()
        self.assertIn('"capi_failed"', log)
        self.assertIn('"status": 400', log)
        self.assertNotIn("secret body", log)
        self.assert_no_token()
        status = self.settings_t.get_item(Key={"pk": "CAPI", "sk": "status"})["Item"]
        self.assertFalse(status["ok"])
        self.assertEqual(status["status"], 400)

    def test_check_button_uses_test_code_and_reports(self):
        self.configure()
        r = self.admin("POST", "/admin/settings/test")
        self.assertEqual(r["headers"]["location"], "/admin/settings?m=ok")
        payload = self.rec.calls[0]["json"]
        self.assertEqual(payload["test_event_code"], "TEST12345")
        self.assertNotIn("ph", payload["data"][0]["user_data"])
        self.rec.status = 401
        r = self.admin("POST", "/admin/settings/test")
        self.assertEqual(r["headers"]["location"], "/admin/settings?m=fail")
        page = self.admin("GET", "/admin/settings", query={"m": "fail"})["body"]
        self.assertIn("HTTP 401", page)
        self.assertNotIn("secret body", page)
        self.assert_no_token(page)

    def test_check_button_without_config(self):
        r = self.admin("POST", "/admin/settings/test")
        self.assertEqual(r["headers"]["location"], "/admin/settings?m=noconf")
        self.assertEqual(self.rec.calls, [])


class AdminLeadsTests(Base):
    LEADS = [
        {"pk": "LEAD", "sk": "b", "ts": "2026-10-21T05:00:00+00:00", "id": "b1", "name": "=HYPERLINK(1)",
         "phone": E164, "product_id": "console", "size_label": "130", "timeframe": "now",
         "status": "new", "is_test": False},
        {"pk": "LEAD", "sk": "a", "ts": "2026-10-21T04:00:00+00:00", "id": "a1", "name": "דנה",
         "phone": E164_B, "product_id": "round-table", "status": "new", "is_test": False},
        {"pk": "LEAD", "sk": "t", "ts": "2026-10-21T03:00:00+00:00", "id": "t1", "name": "test",
         "phone": E164_C, "product_id": "console", "status": "new", "is_test": True},
    ]

    def setUp(self):
        super().setUp()
        p = mock.patch.object(h, "load_leads", return_value=[dict(x) for x in self.LEADS])
        p.start()
        self.addCleanup(p.stop)

    def test_dashboard_shows_new_fields_and_filters_by_product(self):
        body = self.admin("GET", "/admin", query={"range": "all"})["body"]
        self.assertIn("round-table", body)
        self.assertIn("עכשיו", body)
        self.assertIn("/admin/settings", body)
        self.assertIn("leads.csv", body)
        body = self.admin("GET", "/admin", query={"range": "all", "product": "console"})["body"]
        self.assertIn(E164, body)
        self.assertNotIn(E164_B, body)

    def test_csv_export(self):
        r = self.admin("GET", "/admin/leads.csv", query={"range": "all", "product": "console"})
        self.assertEqual(r["statusCode"], 200)
        self.assertTrue(r["headers"]["content-type"].startswith("text/csv"))
        self.assertIn("attachment", r["headers"]["content-disposition"])
        rows = r["body"].lstrip("﻿").splitlines()
        self.assertEqual(rows[0].split(",")[:3], ["ts", "id", "status"])
        self.assertEqual(len(rows), 2)            # заголовок + одна не тестова заявка console
        self.assertIn("'=HYPERLINK(1)", rows[1])  # формула знешкоджена
        r = self.admin("GET", "/admin/leads.csv", query={"range": "all", "test": "1"})
        self.assertEqual(len(r["body"].splitlines()), 4)


if __name__ == "__main__":
    unittest.main()
