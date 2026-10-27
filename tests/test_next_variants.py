"""«Наступне видання» (№22): два варіанти TAVOR на перевірку попиту — голос «אני רוצה כזה», не замовлення.

catalog/next.json — поза каталогом: кошик, каталог і checkout варіантів не бачать. Голос — заявка в ту саму таблицю з
lead_source=vote і product_id варіанта, досить телефону або e-mail; у Telegram — «Голос за: …». Воронка рахує варіант
окремим товаром (ViewContent/Lead з його id), голоси — окремим рядком, час на картці — за товаром.
Зібрані сторінки — tests/test_next_build.py (--pr).
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest
from unittest import mock

from tests.test_handler import body_json, h, lead_payload
from tests.test_shop_funnel import FAKE_LOCAL, Base, CheckoutLeadTests, ev

ROOT = pathlib.Path(__file__).resolve().parents[1]
NEXT = json.loads((ROOT / "catalog" / "next.json").read_text(encoding="utf-8"))["items"]
PRODUCTS = json.loads((ROOT / "catalog" / "products.json").read_text(encoding="utf-8"))
TEMPLATE = (ROOT / "site" / "pages" / "next.html").read_text(encoding="utf-8")
JS = (ROOT / "site" / "assets" / "aluma.js").read_text(encoding="utf-8")
SHOP = (ROOT / "site" / "assets" / "shop.js").read_text(encoding="utf-8")
funnel = h.funnel
T = "2026-10-26T08:00:00+00:00"


def vote_lead(**over):
    data = lead_payload(name="", lead_source="vote", product_id="tavor-fluted", event_id="lead.k1.vote0001")
    data.update(over)
    return data


class CatalogTests(unittest.TestCase):
    def test_two_variants_outside_catalog_price_from_tavor(self):
        self.assertEqual([n["id"] for n in NEXT], ["tavor-fluted", "tavor-oval"])
        ids = {p["id"] for p in PRODUCTS}
        for n in NEXT:
            with self.subTest(n=n["id"]):
                self.assertNotIn(n["id"], ids, "не звичайний товар: у products.json його нема")
                self.assertEqual(n["like"], "tavor")
                self.assertNotIn("price_ils", n, "своєї ціни нема — лише TAVOR того ж розміру")
                self.assertEqual(set(n["name"]), {"he", "en", "ru"})
                self.assertEqual(len([i for i in n["images"] if i["view"] in ("life", "front")]), 2)
                for im in n["images"]:
                    for src in [im["src"]] + [e.split()[0] for e in im["srcset"].split(",") + im["srcset_avif"].split(",")]:
                        self.assertTrue((ROOT / "site" / src.lstrip("/")).is_file(), src)

    def test_build_reads_next_apart_and_price_is_tavor(self):
        import build
        products = build.load_catalog()
        items = build.load_next(products)
        self.assertNotIn("tavor-fluted", {p["slug"] for p in products})
        tavor = next(p for p in products if p["slug"] == "tavor")
        prices = {z["label"]: z["price_ils"] for z in tavor["sizes"]}
        self.assertEqual({n["slug"]: n["price_ils"] for n in items},
                         {"tavor-fluted": prices["160×90"], "tavor-oval": prices["160×100"]})


class TemplateTests(unittest.TestCase):
    def test_one_button_no_cart_no_scarcity(self):
        self.assertEqual(len(re.findall(r"<button\b", TEMPLATE)), 2, "кнопка «אני רוצה כזה» + «שליחה» у її формі")
        self.assertIn('data-vote aria-expanded="false" aria-controls="vote">{{t.next_cta}}</button>', TEMPLATE)
        for bad in ("data-add-cart", "data-pdp", "/cart/", "/checkout/", "data-ask", "data-call", "noindex"):
            self.assertNotIn(bad, TEMPLATE)
        form = re.search(r'<form class="callback" id="vote".*?</form>', TEMPLATE, re.S).group(0)
        self.assertIn('data-source="vote"', form)
        self.assertEqual(re.findall(r'name="(\w+)"', form), ["product_id", "phone", "email", "website", "consent"])

    def test_strings_honest_in_three_languages(self):
        want = {"he": ("מהדורה הבאה — בבדיקה. אם יש מספיק עניין, נכנסת לייצור.", "אני רוצה כזה")}
        for lang in ("he", "en", "ru"):
            t = json.loads((ROOT / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
            blob = " ".join(v for k, v in t.items() if k.startswith("next_"))
            with self.subTest(lang=lang):
                if lang in want:
                    self.assertEqual((t["next_status"], t["next_cta"]), want[lang])
                self.assertIn("{like}", t["next_price_note"])
                self.assertIsNone(re.search(r"\d|הנחה|скидк|discount|נשאר|остал|left|WhatsApp", blob, re.I), blob)

    def test_js_vote_form_and_view_content(self):
        self.assertIn('var vote = form.getAttribute("data-source") === "vote"', JS)
        self.assertIn('if (vote) { data.lead_source = "vote"; data.contact_pref = "info"; data.email = fv("email").slice(0, 120); }', JS)
        self.assertIn("if (vote || (callback && data.contact_pref === \"info\" && !asked)) {", JS)   # №32: «питання» — лише телефон
        block = JS[JS.index('var nextCard = qs("[data-next]")'):]
        self.assertIn('track("ViewContent", { content_ids: [nid], content_type: "product"', block)
        self.assertIn('track("cta_vote", { content_ids: [nid] }, { pixel: false })', block)
        self.assertIn('nextCard ? "next"', SHOP, "час на картці варіанта — свій крок leave")


class VoteLeadTests(Base):
    post = CheckoutLeadTests.post

    def test_phone_only_or_email_only(self):
        r = self.post(vote_lead())
        self.assertEqual(r["statusCode"], 200, r["body"])
        r = self.post(vote_lead(phone="", email="dana@example.com", product_id="tavor-oval", event_id="lead.k1.vote0002"))
        self.assertEqual(r["statusCode"], 200, r["body"])
        got = sorted((x["lead_source"], x["product_id"], x["name"], bool(x["email"])) for x in self.all_leads())
        self.assertEqual(got, [("vote", "tavor-fluted", "", False), ("vote", "tavor-oval", "", True)])

    def test_no_contact_or_consent_refused(self):
        r = self.post(vote_lead(phone="", email="", consent=False))
        self.assertEqual(set(body_json(r)["errors"]), {"phone", "consent"})
        r = self.post(vote_lead(phone="", email="not-mail"))
        self.assertEqual(set(body_json(r)["errors"]), {"email"})
        self.assertEqual(self.all_leads(), [])

    def test_telegram_vote_line(self):
        with mock.patch.object(h, "TELEGRAM_BOT_TOKEN", "123:abc"), \
                mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "42"):
            self.post(vote_lead())
        text = self.rec.calls[0]["json"]["text"]
        self.assertTrue(text.startswith("הצבעה — מהדורה הבאה — "), text[:40])
        self.assertIn("🗳 Голос за: TAVOR · Рифлёная колонна (tavor-fluted)", text)
        self.assertIn("источник: vote", text)
        self.assertNotIn("Итого", text)
        self.assertNotIn("🛒", text)

    def test_admin_funnel_shows_votes_apart(self):
        self.send([ev("PageView"), ev("ViewContent", content_ids=["tavor-oval"], content_type="product")], session="sv")
        self.post(vote_lead(product_id="tavor-oval", session_id="sv", phone=FAKE_LOCAL))
        page = self.admin("/admin/funnel", {"range": "1"})["body"]
        self.assertIn("<tr><td>голоса (lead_source=vote)</td><td class='n'>1</td></tr>"
                      "<tr><td class='mono'>tavor-oval</td><td class='n'>1</td></tr>", page)
        self.assertNotIn(FAKE_LOCAL, page)


class FunnelTests(unittest.TestCase):
    def test_variants_are_own_products_votes_own_line_seconds_by_product(self):
        def row(name, sid, **p):
            return {"event_name": name, "session_id": sid, "sk": T + "#x", "props_json": json.dumps(p)}
        events = [row("ViewContent", "a", content_ids=["tavor-fluted"]), row("ViewContent", "b", content_ids=["tavor-oval"]),
                  row("ViewContent", "c", content_ids=["tavor"]),
                  row("leave", "a", step="next", seconds=40, product="tavor-fluted"),
                  row("leave", "c", step="pdp", seconds=25, product="tavor")]
        leads = [{"session_id": "a", "ts": T, "lead_source": "vote", "product_id": "tavor-fluted"},
                 {"session_id": "b", "ts": T, "lead_source": "vote", "product_id": "tavor-oval"},
                 {"session_id": "x", "ts": T, "lead_source": "vote", "product_id": "tavor-fluted"},
                 {"session_id": "c", "ts": T, "product_id": "tavor"}]
        rep = funnel.compute(events, leads)
        prod = {r["key"]: {s["key"]: s["n"] for s in r["steps"]} for r in rep["by_product"]}
        self.assertEqual((prod["tavor-fluted"]["product"], prod["tavor-fluted"]["lead"]), (1, 2))
        self.assertEqual(prod["tavor-oval"]["lead"], 1)
        self.assertEqual(rep["vote"], {"leads": 3, "by_product": {"tavor-fluted": 2, "tavor-oval": 1}})
        self.assertEqual(rep["card_seconds"], {"tavor": {"median": 25, "n": 1}, "tavor-fluted": {"median": 40, "n": 1}})
        text = funnel.text(funnel.report(events, leads, 0))
        self.assertIn("Голоса «אני רוצה כזה» (следующее издание): 3 · tavor-fluted 2, tavor-oval 1", text)
        self.assertIn("Секунд на карточке (медиана, n): tavor 25 (n=1), tavor-fluted 40 (n=1)", text)


if __name__ == "__main__":
    unittest.main()
