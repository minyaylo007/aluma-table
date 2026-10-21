"""docs/META-TEST.md §4a «Группа C — русский»: посилання ведуть на /ru/-сторінки, що є, ціни — з каталогу,
текст — за тими ж заборонами, що й на сайті (без знижок, дефіциту, відгуків, «массив» лише про кромки й фасади)."""

from __future__ import annotations

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "META-TEST.md"
CATALOG = ROOT / "catalog" / "products.json"

FORBIDDEN_RU = [r"скидк", r"акци", r"%", r"осталось", r"последн", r"ограничен", r"в наличии", r"отзыв",
                r"довольн", r"бесплатн", r"только сегодня", r"★", r"недел"]


class MetaRussianGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        doc = DOC.read_text(encoding="utf-8")
        cls.section = doc.split("## 4a.", 1)[1].split("\n## ", 1)[0]
        cls.catalog = {p["id"]: p for p in json.loads(CATALOG.read_text(encoding="utf-8"))}
        # текст оголошень: блоки ```text``` і рядки з позначкою «(ru)»
        blocks = re.findall(r"```text\n(.*?)```", cls.section, re.S)
        lines = [ln.split(":**", 1)[1] for ln in cls.section.splitlines() if "(ru):**" in ln]
        cls.ads = blocks + lines

    def test_section_sits_between_utm_and_kpi(self):
        doc = DOC.read_text(encoding="utf-8")
        self.assertLess(doc.index("## 4. "), doc.index("## 4a."))
        self.assertLess(doc.index("## 4a."), doc.index("## 5. "))

    def test_links_lead_to_existing_ru_pages(self):
        line = re.search(r"\*\*Ссылки группы C:\*\*(.*)", self.section).group(1)
        links = re.findall(r"`(/[^`]*)`", line)
        self.assertEqual(len(links), 3, line)
        for link in links:
            self.assertTrue(link.startswith("/ru/"), link)
            m = re.fullmatch(r"/ru/p/([a-z]+)/", link)
            if m:
                self.assertIn(m.group(1), self.catalog, link)
            else:
                self.assertEqual(link, "/ru/catalog/", link)

    def test_ad_names_have_ru_suffix(self):
        names = re.findall(r"`([a-z]+-(?:\d+x\d+|…|video)[^`]*)`", self.section)
        self.assertTrue(names)
        for n in names:
            self.assertTrue(n.endswith("-ru"), n)

    def test_prices_come_from_catalog(self):
        for text in self.ads:
            for m in re.finditer(r"от (\d[\d\u00a0 ]*) ₪", text):
                price = int(re.sub(r"\D", "", m.group(1)))
                lows = {min(s["price_ils"] for s in p["sizes"]) for p in self.catalog.values()}
                self.assertIn(price, lows, m.group(0))

    def test_honest_text(self):
        self.assertGreaterEqual(len(self.ads), 10)
        for text in self.ads:
            low = text.lower()
            for pat in FORBIDDEN_RU:
                self.assertIsNone(re.search(pat, low), f"{pat}: {text}")
            for m in re.finditer(r"массив\w*", low):
                near = low[max(0, m.start() - 20): m.end() + 20]
                self.assertTrue("кромк" in near or "фасад" in near, near)

    def test_every_text_says_how_payment_works(self):
        blocks = re.findall(r"```text\n(.*?)```", self.section, re.S)
        self.assertEqual(len(blocks), 3)
        for b in blocks:
            self.assertIn("ориентировочн", b.lower())
            self.assertRegex(b, r"Оплата[^\n]*(не на сайте|только после)")


if __name__ == "__main__":
    unittest.main()
