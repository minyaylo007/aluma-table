"""Картка товару (24.10, слово власника): «עד 12 תשלומים» біля ціни і «התקשרו אלינו» зі зворотним дзвінком — без збірки.

Розстрочка: число лише в content.json (INSTALLMENTS), рядок з i18n трьома мовами, без «ללא ריבית»; сума платежу —
build.py (мінімальна конфігурація, вгору до шекеля) і aluma.js при зміні розміру. Дзвінок: номера на сайті нема —
кнопка відкриває міні-форму з телефоном (lead_source=callback), cta_call — лише в нашу аналітику.
Зібрані сторінки — tests/test_build_site.py (--pr), API — tests/test_shop_funnel.py, клік — tests/shop.spec.js.
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "site" / "pages" / "product.html").read_text(encoding="utf-8")
JS = (ROOT / "site" / "assets" / "aluma.js").read_text(encoding="utf-8")
CONTENT = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
KEYS = ("installments", "per_month", "call_cta", "callback_send", "callback_hours", "callback_thanks")


def i18n(lang):
    return json.loads((ROOT / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))


class InstallmentsTests(unittest.TestCase):
    def test_number_in_content_and_line_right_under_the_price(self):
        self.assertEqual(CONTENT["INSTALLMENTS"], "12")
        # поруч із ціною, а не окремим рядком: на 390 «השאירו פרטים» мусить лишитися над банером (redesign.spec.js)
        self.assertRegex(TEMPLATE, r'<bdi dir="ltr">\{\{P_PRICE\}\}</bdi></span>\n'
                                   r'      <span class="pdp-pay" data-installments="\{\{INSTALLMENTS\}\}">\{\{t\.installments\}\} · '
                                   r'<bdi dir="ltr" data-monthly>≈&nbsp;\{\{P_MONTHLY\}\}</bdi>\{\{t\.per_month\}\}</span>\n'
                                   r'      <span class="price-incl">\{\{P_PRICE_NOTE\}\}</span>\n    </div>')
        sticky = re.search(r'<div class="sticky-cta[^"]*" data-sticky hidden>(.*?)\n</div>', TEMPLATE, re.S).group(1)
        self.assertNotIn("installments", sticky, "у липкій смузі — ні")
        for page in ("cart", "checkout"):
            html = (ROOT / "site" / "pages" / f"{page}.html").read_text(encoding="utf-8")
            with self.subTest(page=page):
                self.assertRegex(html, r'data-(cart|co)-total></bdi></p>\s*<p class="price-incl">\{\{t\.price_incl\}\} · '
                                       r'\{\{t\.installments\}\}</p>')

    def test_strings_honest_in_three_languages(self):
        want = {"he": "עד {{INSTALLMENTS}} תשלומים באשראי", "en": "Up to {{INSTALLMENTS}} card payments",
                "ru": "До {{INSTALLMENTS}} платежей картой"}
        for lang, line in want.items():
            t = i18n(lang)
            with self.subTest(lang=lang):
                self.assertEqual(t["installments"], line)
                blob = " ".join(t[k] for k in KEYS)
                self.assertIsNone(re.search(r"ריבית|interest|процент|беспроцент|без переплат|\d|WhatsApp|הנחה|скидк|discount",
                                            blob.replace("{{INSTALLMENTS}}", ""), re.I), blob)

    def test_monthly_rounded_up_from_minimal_config_tavor(self):
        sys.path.insert(0, str(ROOT))
        import build
        tavor = next(p for p in json.loads((ROOT / "catalog" / "products.json").read_text(encoding="utf-8"))
                     if p["id"] == "tavor")
        first = tavor["sizes"][0]["price_ils"]
        self.assertEqual(first, 4490, "якщо ціна змінилась — оновити очікуване нижче")
        self.assertEqual((build.money(math.ceil(first / 12), "he"), build.money(math.ceil(first / 12), "ru")),
                         ("₪375", "375 ₪"), "4490 / 12 = 374.17 → вгору, не 374")
        src = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertRegex(src, r'"P_MONTHLY": money\(math\.ceil\(\(p\["sizes"\]\[0\]\["price_ils"\]')
        self.assertIn('/ int(CONTENT["INSTALLMENTS"])), loc)', src)

    def test_js_updates_monthly_with_the_size_price(self):
        block = JS[JS.index("var updatePrice"):]
        block = block[:block.index("};")]
        self.assertIn('monthly.textContent = "≈\\u00a0" + money(Math.ceil(Number(sz.getAttribute("data-price")) / payN))',
                      block)


class CallButtonTests(unittest.TestCase):
    def actions(self):
        return re.search(r'<div class="pdp-actions">(.*?)\n    </div>', TEMPLATE, re.S).group(1)

    def test_third_button_full_width_under_the_pair_then_mini_form(self):
        a = self.actions()
        self.assertRegex(a, r'\{\{t\.ask_hint\}\}</p>\s*<button class="btn btn--line btn--block pdp-call" type="button" '
                            r'data-call data-cta="pdp" aria-expanded="false" aria-controls="callback"><svg [^>]*aria-hidden="true"'
                            r'.*?</svg>\{\{t\.call_cta\}\}</button>\s*<form class="callback" id="callback" data-source="callback"')
        form = re.search(r'<form class="callback".*?</form>', a, re.S).group(0)
        self.assertIn(' hidden>', form.split("\n")[0])
        self.assertEqual(re.findall(r'name="(\w+)"', form), ["phone", "website", "consent"], "лише телефон + згода + приманка")
        for part in ('type="tel"', "{{t.callback_send}}", "{{t.callback_hours}}", 'role="status"', 'class="hp"'):
            self.assertIn(part, form)
        self.assertNotIn("tel:", TEMPLATE, "реального номера нема — жодного tel:")

    def test_sticky_icon_44_right_of_ask_with_label(self):
        sticky = re.search(r'<div class="sticky-cta[^"]*" data-sticky hidden>(.*?)\n</div>', TEMPLATE, re.S).group(1)
        # «праворуч від שאלה?» на івриті (RTL): іконка стоїть у розмітці перед нею
        self.assertRegex(sticky, r'<button class="btn btn--line sticky-call" type="button" data-call data-cta="sticky" '
                                 r'aria-label="\{\{t\.call_cta\}\}" aria-controls="callback"><svg[^\n]*</svg></button>\s*'
                                 r'<button class="btn btn--line sticky-ask" type="button" data-ask data-cta="sticky">')
        css = (ROOT / "site" / "assets" / "aluma.css").read_text(encoding="utf-8")
        self.assertIn(".sticky-cta--pdp .sticky-call { flex: none; width: 44px;", css)
        self.assertEqual(TEMPLATE.count("data-call "), 2)

    def test_click_goes_to_our_analytics_only_and_form_sends_callback(self):
        block = JS[JS.index('qsa("[data-call]")'):]
        block = block[:block.index("// «Інший розмір»")]
        self.assertIn('track("cta_call", { content_ids: [cur.id], cta: b.getAttribute("data-cta") || "" }, { pixel: false })',
                      block)
        self.assertIn("b.hidden = true", block, "форми нема — кнопок нема")
        self.assertIn('if (callback) data.lead_source = "callback";', JS)
        self.assertIn("if (!callback && data.name.length < 2)", JS)
        self.assertIn("if (cbForm) wireForm(cbForm);", JS)


if __name__ == "__main__":
    unittest.main()
