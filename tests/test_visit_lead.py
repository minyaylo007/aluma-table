"""№30 «לראות מקרוב»: плитка в смузі довіри → форма #register; cta_visit у нашій аналітиці, заявка lead_source=visit.

API приймає visit як звичайну заявку форми (ім'я обов'язкове), у Telegram — рядок «посмотреть вживую»;
воронка (/admin/funnel і tools/funnel_report.py) рахує натискання й заявки окремим рядком «Визит». Збірка — test_build_showroom.
"""

from __future__ import annotations

import json
import pathlib
import unittest
from unittest import mock

from tests.test_handler import body_json, h, lead_payload
from tests.test_shop_funnel import FAKE_LOCAL, Base, CheckoutLeadTests, ev

ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = (ROOT / "site" / "assets" / "aluma.js").read_text(encoding="utf-8")
funnel = h.funnel
T = "2026-10-27T08:00:00+00:00"


def visit_lead(**over):
    data = lead_payload(lead_source="visit", product_id="tavor", event_id="lead.k1.visit0001")
    data.update(over)
    return data


class JsTests(unittest.TestCase):
    def test_tile_tracks_and_marks_main_form(self):
        block = JS[JS.index('var visits = qsa("[data-visit]")'):JS.index("картка: «התקשרו אלינו»")]
        self.assertIn('track("cta_visit", {', block)
        self.assertIn("{ pixel: false }", block, "лише в нашу аналітику, Meta не потрібна")
        self.assertIn("visitIntent = true;", block)
        self.assertIn('reg0.scrollIntoView(', block)
        self.assertIn('if (visitIntent && form.id === "lead-form") data.lead_source = "visit";', JS)


class VisitLeadTests(Base):
    post = CheckoutLeadTests.post

    def test_accepted_stored_name_required(self):
        r = self.post(visit_lead())
        self.assertEqual(r["statusCode"], 200, r["body"])
        self.assertEqual([x["lead_source"] for x in self.all_leads()], ["visit"])
        r = self.post(visit_lead(name="", event_id="lead.k1.visit0002"))
        self.assertIn("name", body_json(r)["errors"])

    def test_telegram_head(self):
        with mock.patch.object(h, "TELEGRAM_BOT_TOKEN", "123:abc"), \
                mock.patch.object(h, "OWNER_TELEGRAM_CHAT_ID", "42"):
            self.post(visit_lead())
        text = self.rec.calls[0]["json"]["text"]
        self.assertTrue(text.startswith(h.VISIT_HEAD), text[:60])
        self.assertIn("источник: visit", text)

    def test_admin_funnel_visit_card(self):
        self.send([ev("PageView"), ev("cta_visit", content_ids=["tavor"], cta="trust")], session="sv")
        self.post(visit_lead(session_id="sv", phone=FAKE_LOCAL))
        page = self.admin("/admin/funnel", {"range": "1"})["body"]
        self.assertIn("<tr><td>сессии</td><td class='n'>1</td></tr><tr><td class='mono'>trust</td><td class='n'>1</td></tr>"
                      "<tr><td>заявки visit</td><td class='n'>1</td></tr>", page)
        self.assertNotIn(FAKE_LOCAL, page)


class FunnelTests(unittest.TestCase):
    def test_visit_line(self):
        def row(name, sid, **p):
            return {"event_name": name, "session_id": sid, "sk": T + "#x", "props_json": json.dumps(p)}
        events = [row("cta_visit", "a", cta="trust"), row("cta_visit", "b", cta="trust"), row("cta_visit", "a", cta="trust")]
        leads = [{"session_id": "a", "ts": T, "lead_source": "visit", "product_id": "tavor"},
                 {"session_id": "c", "ts": T, "lead_source": "form", "product_id": "tavor"}]
        rep = funnel.compute(events, leads)
        self.assertEqual(rep["visit"], {"sessions": 2, "by_cta": {"trust": 2}, "leads": 1})
        rep = funnel.report(events, leads, 0)
        self.assertIn("Визит: cta_visit 2, заявок visit 1 · trust 2", funnel.text(rep))


if __name__ == "__main__":
    unittest.main()
