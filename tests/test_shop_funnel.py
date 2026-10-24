"""Воронка магазину (specs/003-shop-funnel): події кроків, CAPI InitiateCheckout, заявка з кошика,
вікно Asia/Jerusalem, /admin/funnel і tools/funnel_report.py.

Справжній api/store.py у пам'яті (ліміти — справжні лічильники), requests.post — дублер; мережі нема.

    python -m unittest tests.test_shop_funnel
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from urllib.parse import urlencode

from tests.test_handler import body_json, h, lead_payload, request
from tests.test_meta_settings import GOOD_FORM, PIXEL, TOKEN, Recorder

# вигаданий номер складено з частин — інакше secret_scan бачить «телефон» у дереві
FAKE_LOCAL = "050" + "1234567"
FAKE_E164 = "+972" + FAKE_LOCAL[1:]

ROOT = pathlib.Path(__file__).resolve().parents[1]
funnel = h.funnel

FBP = "fb.1.1700000000000.123"
UA = "Mozilla/5.0 (iPhone; unit test)"


def ev(name, **props):
    return {"name": name, "props": props, "page": "/cart/"}


class Base(unittest.TestCase):
    def setUp(self):
        self.events_t, self.leads_t, self.sessions_t = h.store.tables(":memory:")
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
            mock.patch.object(h.requests, "post", self.rec),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.out = io.StringIO()
        stack = contextlib.ExitStack()
        stack.enter_context(contextlib.redirect_stdout(self.out))
        self.addCleanup(stack.close)

    def configure(self):
        hdrs = {"content-type": "application/x-www-form-urlencoded", "host": "table.example",
                "cookie": "fx_adm=" + h.make_token()}
        h.lambda_handler(request("POST", "/admin/settings", headers=hdrs, raw_body=urlencode(GOOD_FORM)), None)
        self.rec.calls.clear()

    def send(self, events, session="s-1", cookies="", headers=None, ctx=None):
        hdrs = {"user-agent": UA, "x-forwarded-for": "198.51.100.9"}
        if cookies:
            hdrs["cookie"] = cookies
        hdrs.update(headers or {})
        body = {"session_id": session, "ctx": ctx or {"page": "/cart/", "utm_source": "fb", "utm_campaign": "c1"},
                "events": events}
        return h.lambda_handler(request("POST", "/api/fx/event", body, hdrs), None)

    def all_events(self):
        return self.events_t.scan().get("Items", [])

    def all_leads(self):
        return self.leads_t.query(KeyConditionExpression=("eq", "pk", "LEAD")).get("Items", [])

    def admin(self, path, query=None, auth=True):
        hdrs = {"host": "table.example"}
        if auth:
            hdrs["cookie"] = "fx_adm=" + h.make_token()
        e = request("GET", path, headers=hdrs)
        e["queryStringParameters"] = query or {}
        return h.lambda_handler(e, None)


CHECKOUT = dict(event_id="ic.k1.abcdef12", ads_consent=True, content_ids=["tavor"], content_type="product",
                value=4490, currency="ILS", num_items=1, size="160×90", finish="natural", base="oak")


# --------------------------------------------------------------------------- події кроків


class StepEventsTests(Base):
    def test_every_step_event_is_stored_with_its_params(self):
        steps = [ev("ViewContent", content_ids=["tavor"], value=4490, currency="ILS"),
                 ev("select_size", content_ids=["tavor"], size="180×90"),
                 ev("select_finish", content_ids=["tavor"], finish="smoked"),
                 ev("AddToCart", content_ids=["tavor"], size="180×90", finish="smoked", price=4890, value=4890),
                 ev("view_cart", num_items=1, value=4890),
                 ev("InitiateCheckout", **CHECKOUT),
                 ev("checkout_details", city="חיפה", when="1-3m", has_name=False, has_phone=True),
                 ev("reach_payment", value=4890), ev("Lead", value=4890),
                 ev("scroll", depth=50), ev("leave", step="payment", seconds=40, scroll=90)]
        r = self.send(steps)
        self.assertEqual(body_json(r), {"ok": True, "written": len(steps)})
        rows = self.all_events()
        self.assertEqual(sorted(e["event_name"] for e in rows), sorted(s["name"] for s in steps))
        add = next(e for e in rows if e["event_name"] == "AddToCart")
        self.assertEqual(json.loads(add["props_json"])["price"], 4890)
        self.assertEqual(add["utm_source"], "fb")

    def test_limits_of_the_event_endpoint_are_not_loosened(self):
        self.assertEqual(h.MAX_EVENTS_PER_REQUEST, 40)
        self.assertEqual(h.EVENTS_PER_IP_PER_MINUTE, 120)
        self.assertEqual(h.MAX_PROPS_BYTES, 2000)
        self.assertEqual((h.LEADS_PER_IP_PER_HOUR, h.LEADS_PER_IP_PER_HOUR_TEST), (5, 60))
        r = self.send([ev("view_cart")] * 55)
        self.assertEqual(body_json(r)["written"], 40)
        for _ in range(120 - 1):
            self.send([ev("scroll", depth=50)])
        self.assertEqual(self.send([ev("scroll")])["statusCode"], 429)

    def test_fbclid_present_is_stored_as_a_flag_without_the_value(self):
        # хвиля 1: 1/0 від tracking.js; старий клієнт без прапорця — None (звіт тоді оцінює лише за UA)
        base = {"page": "/", "utm_source": "facebook", "utm_campaign": "c1"}
        for sid, extra, want in (("p1", {"fbclid_present": 1}, 1), ("p0", {"fbclid_present": 0}, 0),
                                 ("ps", {"fbclid_present": "1"}, 1), ("old", {}, None)):
            self.send([ev("PageView")], session=sid, ctx=dict(base, **extra))
        got = {e["session_id"]: e for e in self.all_events()}
        self.assertEqual({s: e.get("fbclid_present") for s, e in got.items()},
                         {"p1": 1, "p0": 0, "ps": 1, "old": None})
        self.assertFalse(any(e.get("fbclid") for e in got.values()), "без згоди значення fbclid не зберігається")

    def test_bots_and_owner_are_still_skipped(self):
        r = self.send([ev("AddToCart")], headers={"user-agent": "Googlebot/2.1"})
        self.assertEqual(body_json(r)["skipped"], "bot_ua")
        r = self.send([ev("AddToCart")], cookies="fx_me=1")
        self.assertEqual(body_json(r)["skipped"], "self")
        self.assertEqual(self.all_events(), [])


# --------------------------------------------------------------------------- CAPI InitiateCheckout


class CheckoutCapiTests(Base):
    def test_sends_one_deduplicated_initiate_checkout_without_personal_data(self):
        self.configure()
        r = self.send([ev("view_cart"), ev("InitiateCheckout", **CHECKOUT), ev("InitiateCheckout", **CHECKOUT)],
                      cookies=f"_fbp={FBP}; _fbc=fb.1.1700000000000.AbC")
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(len(self.rec.calls), 1, "не більше одного виклику CAPI на запит")
        call = self.rec.calls[0]
        self.assertEqual(call["url"], f"https://graph.facebook.com/{h.META_GRAPH_VERSION}/{PIXEL}/events")
        self.assertNotIn(TOKEN, call["url"])
        e = call["json"]["data"][0]
        self.assertEqual(e["event_name"], "InitiateCheckout")
        self.assertEqual(e["event_id"], "ic.k1.abcdef12")
        self.assertEqual(e["event_source_url"], "https://table.central-aparts.store/cart/")
        self.assertEqual(e["custom_data"], {"currency": "ILS", "content_type": "product", "content_ids": ["tavor"],
                                            "value": 4490, "num_items": 1, "size": "160×90",
                                            "finish": "natural", "base": "oak"})
        ud = e["user_data"]
        self.assertEqual(set(ud), {"country", "fbp", "fbc", "client_ip_address", "client_user_agent"})
        self.assertEqual(ud["client_ip_address"], "198.51.100.9")
        self.assertNotIn("test_event_code", call["json"])
        status = self.settings_t.get_item(Key={"pk": "CAPI", "sk": "status"})["Item"]
        self.assertEqual(status["source"], "checkout")

    def test_no_consent_no_event_id_test_traffic_or_no_config_send_nothing(self):
        self.send([ev("InitiateCheckout", **CHECKOUT)])           # CAPI не налаштовано
        self.configure()
        self.send([ev("InitiateCheckout", **dict(CHECKOUT, ads_consent=False))])
        self.send([ev("InitiateCheckout", **dict(CHECKOUT, event_id=""))], cookies=f"_fbp={FBP}")
        self.send([ev("InitiateCheckout", **dict(CHECKOUT, event_id="<x>"))], cookies=f"_fbp={FBP}")
        self.send([ev("InitiateCheckout", **CHECKOUT)], headers={"x-test": "1"})
        self.assertEqual(self.rec.calls, [])
        self.assertEqual(len(self.all_events()), 5, "подія зберігається завжди")
        self.send([ev("InitiateCheckout", **dict(CHECKOUT, ads_consent=None))], cookies=f"_fbp={FBP}")
        self.assertEqual(len(self.rec.calls), 1, "_fbp ставить лише піксель після згоди")

    def test_junk_params_never_reach_meta(self):
        self.configure()
        self.send([ev("InitiateCheckout", **dict(CHECKOUT, content_ids=["tavor", "<script>", 5], value="9e9",
                                                 num_items=500, size="x" * 90, phone=FAKE_LOCAL))])
        cd = self.rec.calls[0]["json"]["data"][0]["custom_data"]
        self.assertEqual(cd, {"currency": "ILS", "content_type": "product", "content_ids": ["tavor"],
                              "finish": "natural", "base": "oak"})
        self.assertNotIn(FAKE_LOCAL, json.dumps(self.rec.calls[0]["json"]))

    def test_capi_checkout_has_its_own_small_rate_cap(self):
        self.configure()
        for _ in range(10):
            self.send([ev("InitiateCheckout", **CHECKOUT)])
        self.assertEqual(len(self.rec.calls), h.CAPI_CHECKOUTS_PER_IP_PER_MINUTE)
        self.assertEqual(len(self.all_events()), 10)

    def test_meta_down_event_still_stored(self):
        self.configure()
        self.rec.fail = True
        r = self.send([ev("InitiateCheckout", **CHECKOUT)])
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(len(self.all_events()), 1)
        self.assertNotIn(TOKEN, self.out.getvalue())


# --------------------------------------------------------------------------- заявка «לאישור ההזמנה» (крок оплати)


def checkout_lead(**over):
    data = lead_payload(name="", lead_source="checkout", product_id="tavor", size_label="160×90",
                        finish_id="natural", base_id="oak", timeframe="browsing", city="חיפה",
                        cart="tavor:160×90:natural:oak:1;saf:120:smoked::2", order_total=9470,
                        event_id="lead.k1.abcdef12")
    data.update(over)
    return data


class CheckoutLeadTests(Base):
    def post(self, payload, headers=None):
        hdrs = {"user-agent": UA}
        hdrs.update(headers or {})
        return h.lambda_handler(request("POST", "/api/fx/lead", payload, hdrs), None)

    def test_saves_cart_total_and_browsing_without_a_name(self):
        r = self.post(checkout_lead())
        self.assertEqual(r["statusCode"], 200, r["body"])
        item = self.all_leads()[0]
        self.assertEqual(item["cart"], "tavor:160×90:natural:oak:1;saf:120:smoked::2")
        self.assertEqual(item["order_total"], 9470)
        self.assertEqual(item["lead_source"], "checkout")
        self.assertEqual(item["timeframe"], "browsing")
        self.assertEqual(item["name"], "")
        self.assertEqual((item["product_id"], item["size_label"]), ("tavor", "160×90"))

    def test_phone_and_consent_still_required_and_name_elsewhere(self):
        r = self.post(checkout_lead(phone="123", consent=False))
        self.assertEqual(set(body_json(r)["errors"]), {"phone", "consent"})
        r = self.post(checkout_lead(lead_source="form"))
        self.assertEqual(set(body_json(r)["errors"]), {"name"})
        r = self.post(checkout_lead(name="A"))           # введене ім'я з однієї літери — помилка й тут
        self.assertEqual(set(body_json(r)["errors"]), {"name"})
        self.assertEqual(self.all_leads(), [])

    def test_bad_cart_or_total_is_dropped_not_refused(self):
        for cart, total in (("tavor:160:natural:oak:0", -5), ("<b>:1:x:y:1", "abc"), ("a:b:c:d:1;" * 40, 10**9),
                            (["tavor"], True)):
            r = self.post(checkout_lead(cart=cart, order_total=total))
            self.assertEqual(r["statusCode"], 200)
        for item in self.all_leads():
            self.assertEqual((item["cart"], item["order_total"]), ("", 0))

    def test_telegram_and_csv_carry_cart_and_total(self):
        with mock.patch.object(h, "TELEGRAM_BOT_TOKEN", "123:abc"), \
                mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "42"):
            self.post(checkout_lead())
        text = self.rec.calls[0]["json"]["text"]
        self.assertTrue(text.startswith("בקשה לאישור הזמנה — "))
        for part in ("🛒 TAVOR 160×90 → 240 · אלון טבעי · רגלי אלון × 1 — ₪4,490",
                     "🛒 SAF 120 · אלון מעושן × 2 — ₪4,980", "Итого: ₪9,470", "источник: checkout",
                     "Когда: просто смотрит", "(без имени)"):
            self.assertIn(part, text)
        for col in ("cart", "order_total", "lead_source"):
            self.assertIn(col, h.CSV_COLUMNS)
        self.assertEqual(h.TIMEFRAME_LABELS["browsing"], "רק בודק/ת")


def callback_lead(**over):
    data = lead_payload(name="", lead_source="callback", product_id="tavor", size_label="160×90",
                        event_id="lead.k1.callme01")
    data.update(over)
    return data


class CallbackLeadTests(Base):
    """«התקשרו אלינו» на картці (24.10): міні-форма лише з телефоном → lead_source=callback."""

    post = CheckoutLeadTests.post

    def test_phone_only_is_enough_and_source_kept(self):
        r = self.post(callback_lead())
        self.assertEqual(r["statusCode"], 200, r["body"])
        item = self.all_leads()[0]
        self.assertEqual((item["lead_source"], item["name"], item["product_id"]), ("callback", "", "tavor"))

    def test_phone_and_consent_still_validated(self):
        r = self.post(callback_lead(phone="123", consent=False))
        self.assertEqual(set(body_json(r)["errors"]), {"phone", "consent"})
        self.assertEqual(self.all_leads(), [])

    def test_telegram_starts_with_callback_line(self):
        with mock.patch.object(h, "TELEGRAM_BOT_TOKEN", "123:abc"), \
                mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "42"):
            self.post(callback_lead())
            self.post(checkout_lead(phone=FAKE_LOCAL[:-1] + "9", event_id="lead.k1.other002"))
        texts = [c["json"]["text"] for c in self.rec.calls]
        self.assertTrue(texts[0].startswith("📞 Обратный звонок — позвонить\nליד חדש — "), texts[0][:60])
        self.assertIn("источник: callback", texts[0])
        self.assertNotIn("Обратный звонок", texts[1], "інші заявки — без рядка дзвінка")

    def test_x_test_stored_as_test_and_sends_nothing(self):
        with mock.patch.object(h, "TELEGRAM_BOT_TOKEN", "123:abc"), \
                mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "42"):
            r = self.post(callback_lead(), {"x-test": "1"})
        self.assertEqual(r["statusCode"], 200, r["body"])
        self.assertTrue(self.all_leads()[0].get("is_test"))
        self.assertEqual(self.rec.calls, [])


# --------------------------------------------------------------------------- вікно Asia/Jerusalem


class WindowTests(unittest.TestCase):
    def test_today_starts_at_jerusalem_midnight_summer_and_winter(self):
        summer = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)      # IDT, UTC+3
        self.assertEqual(funnel.window_start(1, summer), datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc))
        self.assertEqual(funnel.utc_partitions(1, summer), ["2026-10-20", "2026-10-21"])
        winter = datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)       # IST, UTC+2
        self.assertEqual(funnel.window_start(7, winter), datetime(2026, 11, 24, 22, 0, tzinfo=timezone.utc))
        late = datetime(2026, 10, 20, 22, 30, tzinfo=timezone.utc)       # 01:30 21.10 за Єрусалимом
        self.assertEqual(funnel.window_start(1, late), datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc))
        self.assertEqual(funnel.utc_partitions(1, late), ["2026-10-20"])
        self.assertIsNone(funnel.window_start(0, late))
        self.assertEqual(len(funnel.utc_partitions(0, late)), funnel.ALL_DAYS_SPAN)

    def test_events_by_server_time_and_leads_by_ts_in_one_window(self):
        now = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
        inside, outside = "2026-10-20T21:30:00+00:00", "2026-10-20T20:30:00+00:00"
        events = [{"sk": inside + "#a", "ts": outside}, {"sk": outside + "#b", "ts": inside}]
        self.assertEqual(funnel.events_in_window(events, 1, now), [events[0]])   # годинник браузера не рахується
        leads = [{"ts": inside}, {"ts": outside}]
        self.assertEqual(funnel.leads_in_window(leads, 1, now), [leads[0]])


# --------------------------------------------------------------------------- розрахунок воронки


def row(name, session, when, utm="", **props):
    return {"pk": "D#" + when[:10], "sk": when + "#" + name + session, "session_id": session, "ts": when,
            "event_name": name, "props_json": json.dumps(props), "utm_source": utm,
            "utm_campaign": "c1" if utm else ""}


T = "2026-10-21T08:00:00+00:00"
EVENTS = [
    row("PageView", "s1", T, "fb"), row("ViewContent", "s1", T, "fb", content_ids=["tavor"]),
    row("AddToCart", "s1", T, "fb", content_ids=["tavor"], size="160×90", price=4490, value=4490),
    row("view_cart", "s1", T, "fb"), row("InitiateCheckout", "s1", T, "fb", content_ids=["tavor"]),
    row("reach_payment", "s1", T, "fb", content_ids=["tavor"]), row("Lead", "s1", T, "fb", content_ids=["tavor"]),
    row("PageView", "s2", T), row("ViewContent", "s2", T, content_ids=["saf"]),
    row("AddToCart", "s2", T, content_ids=["saf"], size="120", price=2490, value=2490),
    row("leave", "s2", T, step="cart", seconds=31),
    row("PageView", "s3", T, "fb"), row("leave", "s3", T, "fb", step="other", seconds=4),
    row("PageView", "s4", "2026-10-20T08:00:00+00:00"), row("ViewContent", "s4", "2026-10-20T08:00:00+00:00",
                                                            content_ids=["tal"]),
]


def ad(name, session, when, ua="Mozilla/5.0 (iPhone)", flag=None, utm="facebook"):
    return dict(row(name, session, when, utm), user_agent=ua, fbclid_present=flag)


APP = "Mozilla/5.0 (iPhone) [FBAN/FBIOS;FBAV/450.0]"


class AudienceTests(unittest.TestCase):
    """Реклама Meta: люди проти перевірки Meta (хвиля 1, 22.10)."""

    def test_flagged_sessions_people_and_meta_check(self):
        aud = funnel.audience([ad("PageView", "f1", T, flag=1), ad("PageView", "f0", T, flag=0),
                               ad("PageView", "own", T, utm="")])
        self.assertEqual(aud, {"f1": "ads_people", "f0": "ads_meta"}, "не реклама — поза розрізом")

    def test_old_events_without_flag_fall_back_to_user_agent(self):
        aud = funnel.audience([ad("PageView", "app", T, ua=APP), ad("PageView", "ig", T, ua="Instagram 300.0"),
                               ad("PageView", "web", T), ad("PageView", "lead", T), ad("Lead", "lead", T),
                               ad("PageView", "row", T)],
                              [{"session_id": "row"}])
        self.assertEqual(aud, {"app": "ads_people", "ig": "ads_people", "web": "ads_meta_est",
                               "lead": "ads_people", "row": "ads_people"})

    def test_people_only_report_drops_meta_check_from_steps_but_counts_it(self):
        now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
        events = [ad("PageView", "f1", T, flag=1), ad("ViewContent", "f1", T, flag=1),
                  ad("PageView", "b1", T, flag=0), ad("ViewContent", "b1", T, flag=0),
                  ad("PageView", "b2", T), row("PageView", "own", T)]
        full = funnel.report(events, [], 1, now=now)
        people = funnel.report(events, [], 1, now=now, people_only=True)
        self.assertEqual(full["steps"][0]["n"], 4)
        self.assertEqual(people["steps"][0]["n"], 2)
        aud = {a["key"]: a["n"] for a in people["by_audience"]}
        self.assertEqual(aud, {"ads_people": 1, "ads_meta": 1, "ads_meta_est": 1})
        text = funnel.text(people)
        self.assertIn("Реклама Meta, сессии: реклама: люди 1 · реклама: проверка Meta 1", text)
        self.assertIn("22.10 14:00–15:30", text, "оцінка позначена")
        self.assertNotIn("22.10 14:00", funnel.text(funnel.report(events[:4], [], 1, now=now)),
                         "з прапорцем — без позначки оцінки")


class ComputeTests(unittest.TestCase):
    def setUp(self):
        self.rep = funnel.compute(EVENTS, [{"session_id": "s4", "product_id": "tal", "ts": T, "name": "Dana",
                                            "phone": FAKE_E164}])

    def test_total_steps_and_percentages(self):
        n = {s["key"]: s["n"] for s in self.rep["steps"]}
        self.assertEqual(n, {"sessions": 4, "product": 3, "cart": 2, "checkout": 1, "payment": 1, "lead": 2})
        cart = next(s for s in self.rep["steps"] if s["key"] == "cart")
        self.assertEqual((cart["of_prev"], cart["of_first"]), (67, 50))

    def test_by_product_source_day(self):
        prod = {r["key"]: {s["key"]: s["n"] for s in r["steps"]} for r in self.rep["by_product"]}
        self.assertEqual(prod["tavor"]["lead"], 1)
        self.assertEqual((prod["saf"]["cart"], prod["saf"]["checkout"]), (1, 0))
        self.assertEqual(prod["tal"]["lead"], 1, "заявка без події Lead теж рахується товару")
        src = {r["key"]: r["steps"][0]["n"] for r in self.rep["by_source"]}
        self.assertEqual(src, {"fb / c1": 2, "direct / —": 2})
        days = [r["key"] for r in self.rep["by_day"]]
        self.assertEqual(days, ["2026-10-20", "2026-10-21"])

    def test_lead_row_counts_by_source_once(self):
        # заявка без події Lead — у «По источнику»: за сесією (s2 → direct) або за utm самої заявки (s9);
        # заявка s1 з подією Lead не рахується двічі
        leads = [{"session_id": "s1", "ts": T, "utm_source": "fb", "utm_campaign": "c1"},
                 {"session_id": "s2", "ts": T, "utm_source": "ig", "utm_campaign": "x"},
                 {"session_id": "s9", "ts": T, "utm_source": "fb", "utm_campaign": "c2"}]
        rep = funnel.compute(EVENTS, leads)
        src = {r["key"]: {s["key"]: s["n"] for s in r["steps"]} for r in rep["by_source"]}
        self.assertEqual((src["fb / c1"]["sessions"], src["fb / c1"]["lead"]), (2, 1))
        self.assertEqual((src["direct / —"]["sessions"], src["direct / —"]["lead"]), (2, 1))
        self.assertEqual((src["fb / c2"]["sessions"], src["fb / c2"]["lead"]), (1, 1))
        self.assertNotIn("ig / x", src)
        self.assertEqual(sum(r["lead"] for r in src.values()), 3)

    def test_by_lang_first_event_and_lead_fallback(self):
        # мова сесії — з першої її події; заявка без подій — з власного поля lang; невідоме — «?»
        events = [dict(e, lang="ru" if e["session_id"] == "s1" else "he") for e in EVENTS]
        events[1] = dict(events[1], lang="en")           # друга подія s1 іншою мовою — сесія лишається ru
        events.append(row("PageView", "s5", T))          # без lang
        leads = [{"session_id": "s9", "lang": "ru", "ts": T}, {"session_id": "s4", "lang": "en", "ts": T}]
        rep = funnel.compute(events, leads)
        langs = {r["key"]: {s["key"]: s["n"] for s in r["steps"]} for r in rep["by_lang"]}
        self.assertEqual([r["key"] for r in rep["by_lang"]], ["he", "ru", "?"])
        self.assertEqual((langs["ru"]["sessions"], langs["ru"]["lead"]), (2, 2))
        self.assertEqual((langs["he"]["sessions"], langs["he"]["product"], langs["he"]["lead"]), (3, 2, 1))
        self.assertEqual(langs["?"]["sessions"], 1)
        self.assertIn("По языку:", funnel.text(funnel.report(events, leads, 0)))

    def test_where_they_left_and_at_what_price(self):
        dropped = {d["step"]: d["n"] for d in self.rep["dropped_after"]}
        self.assertEqual(dropped, {"product": 0, "cart": 1, "checkout": 0, "payment": 0})
        self.assertEqual(self.rep["leave_by_step"], {"cart": 1, "other": 1})
        self.assertEqual(self.rep["median_seconds"], {"cart": 31, "other": 4})
        self.assertEqual(self.rep["price_points"], [
            {"product": "saf", "size": "120", "price": 2490, "cart": 1, "checkout": 0, "payment": 0, "lead": 0},
            {"product": "tavor", "size": "160×90", "price": 4490, "cart": 1, "checkout": 1, "payment": 1,
             "lead": 1}])

    def test_ask_from_card_counted_next_to_cart_not_as_a_step(self):
        # 23.10: «שאלה? נחזור אליכם» (cta_ask) — сесії за кнопкою; кроки воронки й «де пішли» не змінюються
        events = EVENTS + [row("cta_ask", "s3", T, content_ids=["saf"], cta="pdp"),
                           row("cta_ask", "s3", T, content_ids=["saf"], cta="sticky"),
                           row("cta_ask", "s2", T, content_ids=["tavor"], cta="pdp")]
        rep = funnel.compute(events, [])
        self.assertEqual(rep["ask"], {"sessions": 2, "by_cta": {"pdp": 2, "sticky": 1}})
        self.assertEqual(rep["steps"], funnel.compute(EVENTS, [])["steps"])
        self.assertEqual(funnel.compute(EVENTS, [])["ask"], {"sessions": 0, "by_cta": {}})
        self.assertIn("Вопрос с карточки: 2 (корзина 2) · pdp 2, sticky 1", funnel.text(funnel.report(events, [], 0)))

    def test_call_button_and_callback_leads_counted_aside(self):
        # 24.10: «התקשרו אלינו» (cta_call) — сесії за кнопкою + заявки lead_source=callback; кроки не змінюються
        events = EVENTS + [row("cta_call", "s3", T, content_ids=["saf"], cta="pdp"),
                           row("cta_call", "s3", T, content_ids=["saf"], cta="sticky"),
                           row("cta_call", "s1", T, content_ids=["tavor"], cta="pdp")]
        leads = [{"session_id": "s3", "ts": T, "lead_source": "callback"}, {"session_id": "s1", "ts": T}]
        rep = funnel.compute(events, leads)
        self.assertEqual(rep["call"], {"sessions": 2, "by_cta": {"pdp": 2, "sticky": 1}, "leads": 1})
        self.assertEqual(rep["ask"], funnel.compute(EVENTS, leads)["ask"])
        self.assertEqual(funnel.compute(EVENTS, [])["call"], {"sessions": 0, "by_cta": {}, "leads": 0})
        self.assertIn("«Позвоните нам»: 2, заявок на звонок 1 · pdp 2, sticky 1",
                      funnel.text(funnel.report(events, leads, 0)))

    def test_no_personal_data_in_the_report(self):
        blob = json.dumps(self.rep, ensure_ascii=False) + funnel.text(
            funnel.report(EVENTS, [], 0))
        for pii in ("Dana", "501234567", "s1", "s2"):
            self.assertNotIn(pii, blob)


class AdminFunnelTests(Base):
    def test_requires_login(self):
        r = self.admin("/admin/funnel", auth=False)
        self.assertEqual((r["statusCode"], r["headers"]["location"]), (303, "/admin/login"))

    def test_page_shows_counts_and_no_personal_data(self):
        self.send([ev("PageView"), ev("ViewContent", content_ids=["tavor"]),
                   ev("AddToCart", content_ids=["tavor"], size="160×90", price=4490),
                   ev("cta_ask", content_ids=["tavor"], content_type="product", cta="sticky")], session="sx")
        h.lambda_handler(request("POST", "/api/fx/lead", checkout_lead(name="דנה לוי", session_id="sx"),
                                 {"user-agent": UA}), None)
        self.send([ev("PageView")], session="test-s", headers={"x-test": "1"})
        r = self.admin("/admin/funnel", {"range": "1"})
        self.assertEqual(r["statusCode"], 200)
        page = r["body"]
        self.assertIn("משפך קנייה", page)
        self.assertIn("tavor", page)
        self.assertIn("₪4490", page)
        self.assertRegex(page, r"вопрос с карточки \(cta_ask\)</h2><table><tr><td>сессии</td><td class='n'>1</td></tr>"
                               r"<tr><td class='mono'>sticky</td><td class='n'>1</td></tr>")
        for pii in ("דנה", "050", "501234567", "sx"):
            self.assertNotIn(pii, page)
        self.assertRegex(page, r"\(cta_call\)</h2><table><tr><td>сессии</td><td class='n'>0</td></tr>"
                               r"<tr><td>заявки callback</td><td class='n'>0</td></tr>")

    def test_page_shows_call_button_and_callback_leads(self):
        self.send([ev("PageView"), ev("cta_call", content_ids=["tavor"], content_type="product", cta="pdp")],
                  session="sc")
        h.lambda_handler(request("POST", "/api/fx/lead", callback_lead(session_id="sc"), {"user-agent": UA}), None)
        page = self.admin("/admin/funnel", {"range": "1"})["body"]
        self.assertRegex(page, r"\(cta_call\)</h2><table><tr><td>сессии</td><td class='n'>1</td></tr>"
                               r"<tr><td class='mono'>pdp</td><td class='n'>1</td></tr>"
                               r"<tr><td>заявки callback</td><td class='n'>1</td></tr>")
        main = self.admin("/admin", {"range": "7"})["body"]
        self.assertIn("/admin/funnel", main)


class FunnelReportScriptTests(unittest.TestCase):
    def test_prints_counts_only_and_exits_2_without_db(self):
        from tools import funnel_report

        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "aluma.db")
            events_t, leads_t, _ = h.store.tables(db)
            now = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=5)
            for i, e in enumerate(EVENTS[:7]):
                e = dict(e, pk="D#" + now.strftime("%Y-%m-%d"), sk=f"{now.isoformat()}#{i:04d}")
                events_t.put_item(Item=e)
            leads_t.put_item(Item={"pk": "LEAD", "sk": now.isoformat() + "#1", "ts": now.isoformat(),
                                   "session_id": "s1", "name": "Dana", "phone": FAKE_E164})
            out = io.StringIO()
            with mock.patch.object(funnel_report.daily_report, "FX_DB_PATH", db), contextlib.redirect_stdout(out):
                self.assertEqual(funnel_report.main(["--days", "1"]), 0)
            text = out.getvalue()
            self.assertIn("Всего:  сессии 1 → карточка 1 (100%)", text)
            self.assertIn("tavor 160×90 ₪4490", text)
            self.assertIn("Реклама Meta, сессии: реклама: люди 1 · реклама: проверка Meta 0", text)
            self.assertNotIn("Dana", text)
            self.assertNotIn("501234567", text)
            with mock.patch.object(funnel_report.daily_report, "FX_DB_PATH", os.path.join(tmp, "nope.db")), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(funnel_report.main([]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
