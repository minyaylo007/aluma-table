"""№43 (06.11): довга форма #register коротша — на виду ім'я, телефон, згода й кнопка, решта під «הוספת פרטים».

Без збірки: шаблони site/pages/_form.html і cart.html, aluma.js, aluma.css, i18n. Висота й клік — tests/redesign.spec.js.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORM = (ROOT / "site" / "pages" / "_form.html").read_text(encoding="utf-8")
CART = (ROOT / "site" / "pages" / "cart.html").read_text(encoding="utf-8")
JS = (ROOT / "site" / "assets" / "aluma.js").read_text(encoding="utf-8")
CSS = (ROOT / "site" / "assets" / "aluma.css").read_text(encoding="utf-8")


def i18n(lang):
    return json.loads((ROOT / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))


def lead_form():
    return re.search(r'<form class="lead-form" id="lead-form".*?</form>', FORM, re.S).group(0)


def extra():
    return re.search(r'<div class="f-extra" id="f-extra" data-extra hidden>(.*?)\n        </div>\n', lead_form(), re.S).group(1)


class RegisterShortTests(unittest.TestCase):
    def test_visible_part_is_name_phone_consent_and_submit(self):
        form, ext = lead_form(), extra()
        head = form[:form.index('class="f-more"')]
        for name in ('name="name"', 'name="phone"', 'name="consent" required'):
            self.assertIn(name, head)
        self.assertNotIn('class="f-extra"', head)
        # згорнуте: місто, виріб і конфігурація, строк, спосіб зв'язку, коментар, маркетингова згода — нічого обов'язкового
        for name in ('name="city"', 'name="product_id"', 'name="size_label"', 'name="finish_id"', 'name="base_id"',
                     'name="timeframe"', 'name="contact_pref"', 'name="comment"', 'name="consent_marketing"'):
            self.assertIn(name, ext)
        self.assertNotIn("required", ext)
        tail = form[form.index('class="f-extra"'):]
        self.assertIn('<button class="btn btn--dark btn--block" type="submit">{{t.f_submit}}</button>',
                      tail[tail.index("\n        </div>\n"):])

    def test_toggle_is_a_button_with_aria_expanded(self):
        self.assertIn('<button class="f-more" type="button" data-more aria-expanded="false" aria-controls="f-extra">{{t.f_more}}</button>',
                      lead_form())
        self.assertIn('moreBtn.setAttribute("aria-expanded", on ? "true" : "false")', JS)
        # «Інший розмір» пише в коментар — блок розкривається, щоб коментар було видно
        custom = JS[JS.index('qsa(".js-custom")'):]
        self.assertLess(custom.index("openExtra(true)"), custom.index("#f-comment"))
        self.assertRegex(CSS, r"\.f-more:focus-visible \{ outline")

    def test_contact_pref_defaults_to_call_whatsapp_is_only_a_wish(self):
        ext = extra()
        self.assertIn('<input type="radio" name="contact_pref" value="call" checked>', ext)
        self.assertRegex(ext, r'<input type="radio" name="contact_pref" value="whatsapp">')
        self.assertNotRegex(ext, r'value="whatsapp"[^>]*checked')
        # жодного номера чи посилання wa.me у формі
        self.assertNotRegex(FORM, r"wa\.me|api\.whatsapp|\+972|05\d-?\d{7}")

    def test_toggle_text_three_languages(self):
        for lang, opt in (("he", "לא חובה"), ("en", "optional"), ("ru", "необязательно")):
            t = i18n(lang)["f_more"]
            with self.subTest(lang=lang):
                self.assertIn(opt, t)
                self.assertNotRegex(t.lower(), r"\d|whats|ווטס|ватс|הדמיה")

    def test_cart_pay_button_sticks_to_the_bottom_on_a_phone(self):
        self.assertRegex(CART, r'<div class="cart-go"><a class="btn btn--dark btn--block" href="\{\{PREFIX\}\}/checkout/" '
                               r'data-cart-pay data-cta="cart">\{\{t\.cart_pay\}\}</a></div>')
        # варіанти отримання й довіра — у DOM перед кнопкою, як і були (Tab = екран)
        self.assertLess(CART.index("{{SHIP_CHOICE}}"), CART.index("data-cart-pay"))
        self.assertRegex(CSS, r"@media \(max-width: 899px\) \{\n  \.cart-go \{ position: sticky; bottom: 0;")


if __name__ == "__main__":
    unittest.main()
