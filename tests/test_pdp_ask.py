"""Картка товару: м'який крок «שאלה? נחזור אליכם» поруч із «הוספה לסל» (23.10) — без збірки.

Воронка 22–23.10: з реклами 105 карток → 2 кошики, 0 оформлень; єдина заявка прийшла формою #register.
Тут — шаблон і рядки (швидкий набір): друга кнопка біля кошика й у липкій панелі, рядок «בלי התחייבות»
лише під основною, тексти з i18n трьома мовами, без знижок і WhatsApp; aluma.js шле cta_ask лише в нашу
аналітику. Зібрані сторінки трьома мовами — tests/test_build_site.py (--pr), клік — tests/shop.spec.js.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "site" / "pages" / "product.html").read_text(encoding="utf-8")
JS = (ROOT / "site" / "assets" / "aluma.js").read_text(encoding="utf-8")
KEYS = ("ask_cta", "ask_cta_short", "ask_hint", "lead_cta")


class PdpAskTemplateTests(unittest.TestCase):
    def test_second_button_next_to_cart_with_hint_and_short_one_in_sticky_bar(self):
        actions = re.search(r'<div class="pdp-actions">(.*?)\n    </div>', TEMPLATE, re.S).group(1)
        self.assertRegex(actions, r'data-add-cart data-cta="pdp">\{\{t\.add_to_cart\}\}</button>\s*'
                                  r'<button class="btn btn--line" type="button" data-ask data-cta="pdp">\{\{t\.ask_cta\}\}</button>')
        self.assertIn('<p class="pdp-ask-hint muted small">{{t.ask_hint}}</p>', actions)
        sticky = re.search(r'<div class="sticky-cta[^"]*" data-sticky hidden>(.*?)</div>', TEMPLATE, re.S).group(1)
        self.assertRegex(sticky, r'type="button" data-ask data-cta="sticky">\{\{t\.ask_cta_short\}\}</button>')
        self.assertNotIn("ask_hint", sticky)
        self.assertEqual(TEMPLATE.count("data-ask"), 2)
        self.assertEqual(TEMPLATE.count("{{t.ask_hint}}"), 1)
        self.assertIn("{{PART_FORM}}", TEMPLATE, "кнопки ведуть до #register — форма на картці є")

    def test_strings_in_three_languages_without_discounts_or_whatsapp(self):
        for lang in ("he", "en", "ru"):
            t = json.loads((ROOT / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
            with self.subTest(lang=lang):
                for k in KEYS:
                    self.assertTrue(str(t.get(k) or "").strip(), k)
                blob = " ".join(t[k] for k in KEYS)
                self.assertIsNone(re.search(r"%|₪|\d|WhatsApp|וואטסאפ|הנחה|скидк|discount", blob, re.I), blob)
                self.assertLess(len(t["ask_cta_short"]), 12, "липка панель: коротко, висота 44 px")

    def test_click_goes_to_our_analytics_only(self):
        block = JS[JS.index("[data-ask], .pdp-ask"):]
        block = block[:block.index("// «Інший розмір»")]
        self.assertRegex(block, r'track\("cta_ask", \{ content_ids: \[cur\.id\], content_type: "product", '
                                r'cta: b\.getAttribute\("data-cta"\) \|\| "" \}, \{ pixel: false \}\)')
        self.assertIn('qs("#register")', JS)
        self.assertIn("b.hidden = true", block, "форми нема — кнопок нема")
        self.assertNotIn("timeframe", block)


if __name__ == "__main__":
    unittest.main()
