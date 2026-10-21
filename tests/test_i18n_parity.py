"""i18n/<мова>.json: однакові ключі в тому самому порядку й однакові токени в кожному рядку для he, en, ru.

Сторінки будуються з одного шаблону: ключ, якого немає в одній мові, build.py мовчки замінить запасною мовою
(ru → en → he) — гість побачить чужу мову посеред сторінки. Токен {{X}}, загублений у перекладі, — загублене
число з каталогу. Нова мова — додати її в LOCALES і в build.py LOCALES.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ("he", "en", "ru")
TOKEN = re.compile(r"\{\{[^}]+\}\}")
# ключі, що за змістом різні в кожній мові (шрифти, посилання на сторінку своєї мови тощо) — токени можуть різнитись
OWN_PER_LANG = {"lang", "dir", "locale", "font_display", "font_body", "lang_name", "lang_label"}
# назви латиницею однакові в en і ru — це не пропущений переклад
LATIN_NAMES = {"brand_name"}


def load(loc: str) -> dict:
    return json.loads((ROOT / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))


class I18nParityTests(unittest.TestCase):
    def setUp(self):
        self.data = {loc: load(loc) for loc in LOCALES}

    def test_same_keys_same_order(self):
        he = list(self.data["he"])
        for loc in LOCALES[1:]:
            got = list(self.data[loc])
            self.assertEqual(sorted(set(he) - set(got)), [], f"{loc}: немає ключів")
            self.assertEqual(sorted(set(got) - set(he)), [], f"{loc}: зайві ключі")
            self.assertEqual(got, he, f"{loc}: порядок ключів")

    def test_same_tokens_in_every_string(self):
        for key, he in self.data["he"].items():
            if key in OWN_PER_LANG or not isinstance(he, str):
                continue
            want = sorted(TOKEN.findall(he))
            for loc in LOCALES[1:]:
                got = sorted(TOKEN.findall(self.data[loc][key]))
                # ru пише кількість тонів у прийменниковому відмінку «в {{FINISH_COUNT}} тонах» — лише так, з малої
                if loc == "ru":
                    got = [t.replace("{{FINISH_COUNT}}", "{{FINISH_COUNT_CAP}}") if "{{FINISH_COUNT_CAP}}" in want else t
                           for t in got]
                self.assertEqual(got, want, f"{loc}.{key}")

    def test_no_empty_strings(self):
        # порожній в усіх мовах — заглушка, яку build.py заповнює з legal.<мова>.json (напр. f_lead_notice)
        stubs = {k for k, v in self.data["he"].items() if v == "" and all(self.data[l].get(k) == "" for l in LOCALES)}
        for loc, d in self.data.items():
            for key, v in d.items():
                if isinstance(v, str) and key not in stubs:
                    self.assertTrue(v.strip(), f"{loc}.{key}")

    def test_lang_meta(self):
        self.assertEqual({loc: d["lang"] for loc, d in self.data.items()}, {loc: loc for loc in LOCALES})
        self.assertEqual(self.data["ru"]["dir"], "ltr")
        # російська сторінка не тягне латинські файли шрифтів: кирилиця з окремих woff2
        self.assertIn("cyrillic", self.data["ru"]["font_display"])
        self.assertIn("cyrillic", self.data["ru"]["font_body"])

    def test_ru_has_no_hebrew_or_untranslated_english(self):
        hebrew = re.compile(r"[א-ת]")
        for key, v in self.data["ru"].items():
            if not isinstance(v, str) or key.endswith("_html"):
                continue
            self.assertIsNone(hebrew.search(TOKEN.sub("", v)), f"ru.{key}")
            if key in LATIN_NAMES:
                continue
            if re.search(r"[A-Za-z]{4,}", TOKEN.sub("", re.sub(r"<[^>]+>", "", v))) and v == self.data["en"][key]:
                self.fail(f"ru.{key} збігається з en — не перекладено")


if __name__ == "__main__":
    unittest.main()
