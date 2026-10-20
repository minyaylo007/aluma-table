"""Креативи Meta (tools/creatives/, docs/creatives/): чесність тексту й межі зображень.

Сам знімок робить Playwright (node tools/creatives/build.js) і вже перевіряє текст ≤ 20 %, контраст ≥ 4.5:1,
позначку «הדמיה» і ≤ 500 КБ. Тут — те, що можна зламати правкою JSON без браузера: тексти не обіцяють
знижок, залишків і відгуків, товари є в каталозі, а викладені в docs/creatives/ файли відповідають звіту.

    python -m unittest tests.test_quality_creatives -v
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = ROOT / "tools" / "creatives" / "creatives.json"
TEMPLATE = ROOT / "tools" / "creatives" / "template.html"
CATALOG = ROOT / "catalog" / "products.json"
OUT = ROOT / "docs" / "creatives"

# Закон про захист споживача + правила власника: ні знижок, ні дефіциту, ні відгуків, ні «в наявності», ні «купи».
FORBIDDEN = [
    r"הנחה", r"מבצע", r"%", r"נותר", r"אחרונ", r"מוגבל", r"במלאי", r"ביקורות", r"לקוחות מרוצים",
    r"★", r"קנ[הו]\b", r"רק היום", r"חינם", r"עץ אלון מלא",
    r"(?<!\w)מאלון(?!\w)",  # шпон: «פורניר אלון», як на сайті, а не «з дуба» — читається як масив
]


def texts(cfg: dict) -> list[str]:
    out = [cfg["mark"], cfg["cta"], cfg["price_note"], cfg["price_note_many"], cfg["includes"], cfg["brand"]]
    for v in cfg["variants"]:
        out += [v["headline"], v["sub"], v["price"]]
    return out


class CreativeConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.catalog = {p["id"]: p for p in json.loads(CATALOG.read_text(encoding="utf-8"))}

    def test_three_variants_three_formats(self):
        self.assertEqual(len(self.cfg["variants"]), 3)
        self.assertEqual({(f["width"], f["height"]) for f in self.cfg["formats"]},
                         {(1080, 1080), (1080, 1350), (1080, 1920)})

    def test_products_exist_in_catalog(self):
        for v in self.cfg["variants"]:
            for pid in v["products"]:
                self.assertIn(pid, self.catalog, v["id"])

    def test_honest_text(self):
        """Позначка візуалізації, ціна — орієнтир із «טרם אושר», жодної обіцянки, якої нема."""
        self.assertEqual(self.cfg["mark"], "הדמיה")
        self.assertIn("משוער", self.cfg["price_note"])
        self.assertIn("טרם אושר", self.cfg["price_note"])
        self.assertIn("טרם אושרו", self.cfg["price_note_many"])
        for t in texts(self.cfg) + [self.catalog[p]["tagline"]["he"] for v in self.cfg["variants"] for p in v["products"]]:
            for pat in FORBIDDEN:
                self.assertIsNone(re.search(pat, t), f"«{pat}» у «{t}»")

    def test_prices_come_from_catalog_not_config(self):
        """Одне джерело цифр: у creatives.json жодної ціни чи розміру — лише {price}/{length}/{extended}."""
        for v in self.cfg["variants"]:
            self.assertNotRegex(v["price"] + v["sub"], r"\d{3}", v["id"])
            self.assertIn("{price}", v["price"])

    def test_template_marks_every_text_for_the_checks(self):
        """Кожен текстовий плейсхолдер стоїть в елементі з data-text — інакше 20 % і контраст його не бачать."""
        html = TEMPLATE.read_text(encoding="utf-8")
        for key in ("MARK", "BRAND", "HEADLINE", "SUB", "PRICE", "PRICE_NOTE", "CTA"):
            self.assertRegex(html, r"data-text>[^<]*\{\{" + key + r"\}\}", key)


@unittest.skipUnless((OUT / "report.json").exists(), "docs/creatives/ ще не зібрано")
class PublishedCreativesTests(unittest.TestCase):
    def test_report_matches_files_and_limits(self):
        report = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
        items = report["creatives"]
        self.assertEqual(len(items), 9)
        for it in items:
            f = OUT / it["file"]
            self.assertTrue(f.is_file(), it["file"])
            self.assertLessEqual(f.stat().st_size, 500 * 1024, it["file"])
            self.assertEqual(f.stat().st_size, it["bytes"], it["file"])
            self.assertLessEqual(it["text_share"], 0.20, it["file"])
            self.assertGreaterEqual(it["min_contrast"], 4.5, it["file"])
            for img in it["images"]:
                self.assertTrue(img.startswith("site/assets/products/"), f"{it['file']}: кадр не з каталогу — {img}")
        self.assertTrue((OUT / "preview.html").is_file())
        self.assertLessEqual((OUT / "preview.jpg").stat().st_size, 500 * 1024)


if __name__ == "__main__":
    unittest.main()
