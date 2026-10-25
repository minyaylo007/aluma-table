"""Зібрані сторінки «наступного видання» (№22): /p/tavor-fluted/ і /p/tavor-oval/ трьома мовами.

Одна збірка в тимчасовій копії дерева (як test_build_site). Сторінка є, в sitemap, без noindex, з чесним статусом,
ціною TAVOR і однією кнопкою; каталог, головна, кошик і дані кошика (DATA.products) варіантів не містять.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import tempfile
import unittest

from tests.locales import DIST_PREFIX
from tests.test_build_eol import make_tree, run_build

SLUGS = ("tavor-fluted", "tavor-oval")
STATUS = {"he": "מהדורה הבאה — בבדיקה. אם יש מספיק עניין, נכנסת לייצור.",
          "en": "Next edition — in testing.", "ru": "Следующее издание — на проверке."}
CTA = {"he": "אני רוצה כזה", "en": "I want this one", "ru": "Хочу такой"}


class BuiltNextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-build-next-"))
        tree = cls.tmp / "t"
        tree.mkdir()
        make_tree(tree, crlf_sources=False)
        cls.dist = run_build(tree, as_windows=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def page(self, rel):
        return (self.dist / rel / "index.html").read_text(encoding="utf-8")

    def test_pages_in_three_languages(self):
        for lang, prefix in DIST_PREFIX.items():
            for slug in SLUGS:
                html = self.page(f"{prefix}p/{slug}/")
                with self.subTest(lang=lang, slug=slug):
                    self.assertIn(f'<html lang="{lang}"', html)
                    self.assertEqual(len(re.findall(r"<h1[\s>]", html)), 1)
                    self.assertIn(STATUS[lang], html)
                    self.assertIn(f">{CTA[lang]}</button>", html)
                    self.assertIn(f'data-next data-product="{slug}"', html)
                    self.assertIn(f'<input type="hidden" name="product_id" value="{slug}">', html)
                    self.assertNotIn("noindex", html)
                    self.assertNotIn("data-add-cart", html)
                    self.assertRegex(html, r'<span class="price"><bdi dir="ltr">(₪4,490|4\xa0490\xa0₪)</bdi>')
                    self.assertRegex(html, r'<img src="/assets/next/' + slug + r'/life-1600\.[0-9a-f]{8,}\.webp"')

    def test_sitemap_has_them_catalog_and_cart_do_not(self):
        sitemap = (self.dist / "sitemap.xml").read_text(encoding="utf-8")
        for slug in SLUGS:
            self.assertEqual(sitemap.count(f"/p/{slug}/</loc>"), 3)
        for prefix in DIST_PREFIX.values():
            for rel in ("", "catalog/", "cart/", "checkout/", "p/tavor/"):
                html = self.page(prefix + rel)
                with self.subTest(page=prefix + rel):
                    data = json.loads(re.search(r'id="aluma-data"[^>]*>(.*?)</script>', html, re.S).group(1)
                                      .replace("<\\/", "</")) if 'id="aluma-data"' in html else {}
                    self.assertFalse({p.get("id") for p in data.get("products", [])} & set(SLUGS), "кошик їх не знає")
                    if rel != "p/tavor/":
                        self.assertNotIn("tavor-fluted", html)
                        self.assertNotIn("tavor-oval", html)


if __name__ == "__main__":
    unittest.main()
