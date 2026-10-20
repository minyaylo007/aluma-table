"""i18n/legal.he.json і legal.en.json: обов'язкові ізраїльські тексти (docs/COMPLIANCE-IL.md).

Доводить: обидві мови мають однакову структуру (сторінку будують з одного шаблону), плейсхолдери — лише відомі
й однакові в he/en, немає подвійних фігурних дужок (їх займає build.py), і в кожному тексті є те, що вимагає
закон: תקנה 35 (рівень, обмеження, дата, רכז נגישות), תיקון 13 (хто, що, навіщо, кому, скільки, права),
ס' 30א (окрема згода на рекламу, відмова), תקנון (передзапуск, без оплати, ціни з ПДВ попередні).
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDERS = {"brand", "company_name", "business_id", "address", "phone", "email", "a11y_name", "a11y_phone",
                "a11y_email", "court_city", "updated"}
DOCS = ("accessibility", "privacy", "terms")


def load(lang: str) -> dict:
    return json.loads((ROOT / f"i18n/legal.{lang}.json").read_text(encoding="utf-8"))


def shape(node):
    if isinstance(node, dict):
        return {k: shape(v) for k, v in node.items() if k != "_meta"}
    if isinstance(node, list):
        return [shape(v) for v in node]
    return "s"


def strings(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k != "_meta":
                yield from strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v)
    else:
        yield node


def text(doc: dict) -> str:
    return "\n".join(strings(doc))


class LegalTextsTests(unittest.TestCase):
    def setUp(self):
        self.he, self.en = load("he"), load("en")

    def test_same_structure_in_both_languages(self):
        self.assertEqual(shape(self.he), shape(self.en))
        for lang in (self.he, self.en):
            for s in strings(lang):
                self.assertIsInstance(s, str)
                self.assertTrue(s.strip(), "порожній рядок")

    def test_placeholders_known_identical_and_safe_for_build(self):
        for key in ("cookies", "marketing", "lead_notice", *DOCS):
            he = re.findall(r"\{(\w+)\}", text(self.he[key]))
            en = re.findall(r"\{(\w+)\}", text(self.en[key]))
            self.assertEqual(sorted(he), sorted(en), key)
            self.assertLessEqual(set(he), PLACEHOLDERS, key)
        for lang in ("he", "en"):
            raw = (ROOT / f"i18n/legal.{lang}.json").read_text(encoding="utf-8")
            self.assertNotIn("{{", raw)
            self.assertNotIn("\r", raw)

    def test_accessibility_statement_regulation_35(self):
        he = text(self.he["accessibility"])
        for must in ("תקנה 35", "5568", "AA", "מגבלות", "{updated}", "{a11y_name}", "{a11y_phone}", "{a11y_email}",
                     "הסדרי נגישות", "נציבות"):
            self.assertIn(must, he)
        self.assertIn("Regulation 35", text(self.en["accessibility"]))

    def test_privacy_policy_amendment_13(self):
        he, en = text(self.he["privacy"]), text(self.en["privacy"])
        for must in ("תיקון 13", "{company_name}", "{business_id}", "Meta Pixel", "Conversions API", "Clarity",
                     "Telegram", "SHA-256", "180", "400", "חייבים", "סעיף 13", "סעיף 14",
                     "17ו", "לרשות להגנת הפרטיות", "מחוץ לישראל"):
            self.assertIn(must, he)
        for must in ("Amendment 13", "Meta Pixel", "Clarity", "Telegram", "180", "outside Israel"):
            self.assertIn(must, en)

    def test_cookie_notice_offers_a_real_choice(self):
        for lang in (self.he, self.en):
            c = lang["cookies"]
            self.assertTrue(c["accept"] and c["decline"])
            self.assertNotEqual(c["accept"], c["decline"])
            self.assertIn("Meta Pixel", c["text"])
            self.assertIn("Clarity", c["text"])

    def test_marketing_consent_section_30a(self):
        he = self.he["marketing"]
        self.assertIn("{brand}", he["label"])
        self.assertIn("לא חובה", he["hint"])
        self.assertIn("הסרה", he["hint"])
        self.assertIn("Optional", self.en["marketing"]["hint"])

    def test_terms_pre_launch_no_payment_estimated_prices(self):
        he = text(self.he["terms"])
        for must in ("טרום השקה", "לא נגבה בו תשלום", "מע״מ", "מחיר משוער, טרם אושר", "הצעה כתובה",
                     "חוק הגנת הצרכן", "{business_id}", "{phone}", "{email}", "{court_city}", "הדמיה"):
            self.assertIn(must, he)
        en = text(self.en["terms"])
        for must in ("no payment", "VAT", "estimates, not yet confirmed", "written offer"):
            self.assertIn(must, en)

    def test_tracking_js_banner_copy_matches(self):
        js = (ROOT / "site/assets/tracking.js").read_text(encoding="utf-8")
        for lang in (self.he, self.en):
            for k in ("label", "text", "accept", "decline", "more"):
                self.assertIn(json.dumps(lang["cookies"][k], ensure_ascii=False), js, k)


if __name__ == "__main__":
    unittest.main()
