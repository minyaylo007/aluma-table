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
                            r'.*?</svg>\{\{t\.call_cta\}\}</button>\s*<p class="pdp-call-hint muted small">\{\{t\.call_hint\}\}</p>\s*'
                            r'<form class="callback" id="callback" data-source="callback"')
        form = re.search(r'<form class="callback".*?</form>', a, re.S).group(0)
        self.assertIn(' hidden>', form.split("\n")[0])
        # №20: «що вам зручно» (три чипи) + телефон, e-mail для «деталей», зручний час; згода й приманка як були
        self.assertEqual(re.findall(r'name="(\w+)"', form),
                         ["contact_pref"] * 3 + ["phone", "email", "preferred_time", "website", "consent"])
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
        self.assertIn('data.lead_source = "callback";', JS)
        self.assertIn("if (!callback && data.name.length < 2)", JS)
        self.assertIn("if (cbForm) wireForm(cbForm);", JS)


class ContactPrefTests(unittest.TestCase):
    """№20 (слово 25.10): «התקשרו אלינו» — дзвінок, відеодзвінок або «надішліть деталі», зручний час."""

    def form(self):
        return re.search(r'<form class="callback".*?</form>', TEMPLATE, re.S).group(0)

    def test_three_choices_first_checked_each_described(self):
        form = self.form()
        chips = re.findall(r'<input type="radio" name="contact_pref" value="(\w+)"( checked)? aria-describedby="cb-h-(\w+)">', form)
        self.assertEqual(chips, [("call", " checked", "call"), ("video", "", "video"), ("info", "", "info")])
        self.assertRegex(form, r'<fieldset class="f f-choice">\s*<legend>\{\{t\.cb_pref\}\}</legend>')
        for v in ("call", "video", "info"):
            self.assertRegex(form, rf'<p class="muted small" id="cb-h-{v}" data-pref-hint="{v}"( hidden)?>'
                                   rf'\{{\{{t\.cb_hint_{v}\}}\}}</p>')

    def test_email_and_time_fields_labelled_and_bounded(self):
        form = self.form()
        self.assertRegex(form, r'<div class="f" data-cb-email hidden><label for="cb-email">\{\{t\.f_email\}\}.*?</label>'
                               r'<input id="cb-email" name="email" type="email" inputmode="email" autocomplete="email" dir="ltr" '
                               r'maxlength="120" aria-describedby="cb-e-email"><p class="f-err" id="cb-e-email" hidden></p></div>')
        self.assertRegex(form, r'<label for="cb-time">\{\{t\.cb_time\}\} <span class="opt-l">\{\{t\.f_optional\}\}</span>'
                               r'</label><input id="cb-time" name="preferred_time" type="text" maxlength="80"')

    def test_js_info_needs_phone_or_email_others_phone(self):
        block = JS[JS.index('data.lead_source = "callback";'):]
        block = block[:block.index("if (!data.consent)")]
        for part in ('data.contact_pref = data.contact_pref || "call";',
                     'data.preferred_time = fv("preferred_time").slice(0, 80);',
                     'if (data.contact_pref === "info") data.email = fv("email").slice(0, 120);',
                     'if (!data.phone && !data.email) { setErr("phone", S.e_contact);',
                     'if (data.email && !EMAIL_OK.test(data.email)) { setErr("email", S.e_email);',
                     '} else if (!phoneOk(data.phone)) { setErr("phone", S.e_phone);'):
            self.assertIn(part, block)
        sync = JS[JS.index("var cbSync"):JS.index("cbSync();")]
        self.assertIn("if (em) em.hidden = !info;", sync)

    def test_strings_three_languages_honest(self):
        want = {"he": "טלפון, שיחת וידאו או פרטים במייל — לפי הנוחות שלכם",
                "en": "Phone, video call or details by email — whatever suits you",
                "ru": "Телефон, видеозвонок или детали на почту — как вам удобнее"}
        keys = ("call_hint", "cb_pref", "cb_pref_call", "cb_pref_video", "cb_pref_info", "cb_hint_call", "cb_hint_video",
                "cb_hint_info", "cb_or_email", "cb_or_phone", "f_email", "cb_time", "cb_time_ph", "callback_thanks")
        for lang, line in want.items():
            t = i18n(lang)
            with self.subTest(lang=lang):
                self.assertEqual(t["call_hint"], line)
                self.assertTrue(t["js"]["e_contact"] and t["js"]["e_email"])
                blob = " ".join(t[k] for k in keys)
                # без шоуруму, «наживо», зразка в Ізраїлі, номерів і знижок — цього нема
                self.assertIsNone(re.search(r"\d|showroom|шоурум|אולם תצוגה|in person|вживую|наживо|sample|образец|דוגמה|"
                                            r"הנחה|скидк|discount|\+972", blob, re.I), blob)


if __name__ == "__main__":
    unittest.main()
