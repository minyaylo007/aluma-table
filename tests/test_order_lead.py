"""№41: форма замовлення на картці — заявка lead_source=order, події order_open / form_start / form_error.

API приймає order як заявку з оформлення: ім'я необов'язкове, телефон і згода обов'язкові; кошик з одного рядка
(розмір, тон, опора), сума й спосіб отримання — як у checkout. У Telegram — «בקשה לאישור הזמנה» і «источник: order».
Розмітку картки перевіряє test_build_site, поведінку в браузері — tests/shop.spec.js.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest
from unittest import mock

from tests.test_handler import body_json, h, lead_payload
from tests.test_shop_funnel import FAKE_LOCAL, Base, CheckoutLeadTests

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHOP = (ROOT / "site" / "assets" / "shop.js").read_text(encoding="utf-8")
ALUMA = (ROOT / "site" / "assets" / "aluma.js").read_text(encoding="utf-8")


def order_lead(**over):
    data = lead_payload(name="", lead_source="order", product_id="tavor", size_label="160×90",
                        finish_id="natural", base_id="oak", timeframe="", city="", contact_pref="call",
                        cart="tavor:160×90:natural:oak:1", order_total=4490, delivery="door",
                        event_id="lead.k1.order0001")
    data.update(over)
    return data


class OrderLeadTests(Base):
    post = CheckoutLeadTests.post

    def test_source_valid_and_stored_without_a_name(self):
        self.assertIn("order", h.VALID_LEAD_SOURCES)
        r = self.post(order_lead())
        self.assertEqual(r["statusCode"], 200, r["body"])
        item = self.all_leads()[0]
        self.assertEqual(item["lead_source"], "order")
        self.assertEqual(item["name"], "")
        self.assertEqual((item["product_id"], item["size_label"], item["finish_id"], item["base_id"]),
                         ("tavor", "160×90", "natural", "oak"))
        self.assertEqual((item["cart"], item["order_total"], item["delivery"]), ("tavor:160×90:natural:oak:1", 4490, "door"))
        self.assertEqual(item["contact_pref"], "call")

    def test_phone_and_consent_required_typed_name_checked(self):
        r = self.post(order_lead(phone="123", consent=False))
        self.assertEqual(set(body_json(r)["errors"]), {"phone", "consent"})
        r = self.post(order_lead(name="A"))
        self.assertEqual(set(body_json(r)["errors"]), {"name"})
        self.assertEqual(self.all_leads(), [])

    def test_delivery_optional(self):
        r = self.post(order_lead(delivery=""))
        self.assertEqual(r["statusCode"], 200, r["body"])
        self.assertEqual(self.all_leads()[0]["delivery"], "")

    def test_telegram_head_cart_and_source(self):
        with mock.patch.object(h, "TELEGRAM_BOT_TOKEN", "123:abc"), \
                mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "42"):
            self.post(order_lead())
        text = self.rec.calls[0]["json"]["text"]
        self.assertTrue(text.startswith("בקשה לאישור הזמנה — "), text[:60])
        for part in ("🛒 TAVOR 160×90", "₪4,490", "источник: order", "(без имени)"):
            self.assertIn(part, text)

    def test_admin_and_csv_show_the_order(self):
        self.post(order_lead(phone=FAKE_LOCAL))
        page = self.admin("/admin", {"range": "all"})["body"]
        self.assertIn("tavor:160×90:natural:oak:1", page)
        csv = self.admin("/admin/leads.csv", {"range": "all"})["body"]
        head, row = csv.splitlines()[:2]
        cols = head.split(",")
        self.assertEqual(row.split(",")[cols.index("lead_source")], "order")

    def test_x_test_stored_as_test_and_sends_nothing(self):
        with mock.patch.object(h, "TELEGRAM_BOT_TOKEN", "123:abc"), \
                mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "42"):
            r = self.post(order_lead(), {"x-test": "1"})
        self.assertEqual(r["statusCode"], 200, r["body"])
        self.assertTrue(self.all_leads()[0].get("is_test"))
        self.assertEqual(self.rec.calls, [])

    def test_no_phone_in_logs(self):
        self.post(order_lead(phone=FAKE_LOCAL))
        self.assertNotIn(FAKE_LOCAL[3:], self.out.getvalue())


class PreviewTests(unittest.TestCase):
    def test_preview_order(self):
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "preview_lead_message.py"), "--order"],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("источник: order", out)
        self.assertIn("🛒 TAVOR", out)


class JsTests(unittest.TestCase):
    def block(self):
        return SHOP[SHOP.index("function wireOrder("):SHOP.index("---- сторінка кошика")]

    def test_order_form_sends_order_lead_with_cart_line(self):
        b = self.block()
        for part in ('lead_source: "order"', "cart: cartString([l])", "order_total: l.price", "delivery: shipWay()",
                     'contact_pref: "call"', 'fetch("/api/fx/lead"'):
            self.assertIn(part, b)
        self.assertIn('if (res.body.id !== "hp")', b, "приманка для ботів — не конверсія")
        self.assertIn('track("Lead", lp)', b)

    def test_events_only_in_our_analytics(self):
        b = self.block()
        self.assertRegex(b, r'track\("order_open", \{[^}]*\}, \{ pixel: false \}\)')
        self.assertIn('track("form_error", { form: "order", code: code }, { pixel: false })', b)
        self.assertIn('track("form_start", { form: name', ALUMA)
        self.assertIn('track("form_error", p, { pixel: false })', ALUMA)

    def test_add_to_cart_navigation_is_native(self):
        add = SHOP[SHOP.index('qsa("[data-add-cart]")'):SHOP.index("wireOrder(pickedLine)")]
        self.assertNotIn("preventDefault", add)
        self.assertNotIn("go(", add.replace("(go() → location.href)", ""))
        # кошик записано до будь-якої роботи з подіями; події — у try, збій не тримає перехід
        self.assertLess(add.index("saveCart(lines)"), add.index('track("AddToCart"'))
        self.assertLess(add.index("try {"), add.index('track("AddToCart"'))

    def test_header_cart_hidden_when_empty(self):
        self.assertIn('el.setAttribute("data-empty", "")', SHOP)
        css = (ROOT / "site" / "assets" / "aluma.css").read_text(encoding="utf-8")
        self.assertIn(".top-cart[data-empty] { visibility: hidden; }", css)
        layout = (ROOT / "site" / "_layout.html").read_text(encoding="utf-8")
        self.assertIn('top-cart" data-empty href=', layout)


if __name__ == "__main__":
    unittest.main()
