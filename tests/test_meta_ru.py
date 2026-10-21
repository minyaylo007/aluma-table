"""docs/META-TEST.md §4а «Группа C — русский»: ціни в текстах — з каталогу, у кожному основному тексті — що ціна
орієнтовна і як влаштована оплата (не на сайті, спершу дзвінок і письмове підтвердження). Посилання, назви й заборони
перевіряє tests/test_quality_creatives.py — тут їх не дублюємо."""

from __future__ import annotations

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "META-TEST.md"
CATALOG = ROOT / "catalog" / "products.json"


class MetaRussianGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        doc = DOC.read_text(encoding="utf-8")
        cls.section = doc.split("## 4а.", 1)[1].split("\n## ", 1)[0]
        cls.blocks = re.findall(r"```text\n(.*?)```", cls.section, re.S)
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_prices_come_from_catalog(self):
        prices = {s["price_ils"] for p in self.catalog for s in p["sizes"]}
        found = [m for b in self.blocks for m in re.findall(r"(\d[\d  ]*) ₪", b)]
        self.assertTrue(found)
        for raw in found:
            self.assertIn(int(re.sub(r"\D", "", raw)), prices, raw)

    def test_every_text_says_how_payment_works(self):
        self.assertEqual(len(self.blocks), 4)
        for b in self.blocks:
            self.assertIn("ориентировочн", b.lower(), b)
            self.assertRegex(b, r"Оплата[^\n]*(не на сайте|только после)", b)

    def test_funnel_by_language_is_mentioned(self):
        self.assertIn("/admin/funnel", self.section)
        self.assertIn("по языку he / en / ru", self.section)


if __name__ == "__main__":
    unittest.main()
