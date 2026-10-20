"""catalog/products.json — схема каталогу і правила чесності.

Файл читає build.py вітрини; тут перевіряється контракт ночі 20→21.10.2026: поля кожного товару,
ціни (price_from_ils — найменша з сітки, preliminary: true, поки фабрика не підтвердила), строк 10–12
тижнів, тонування 4–6, і що кожна картинка — візуалізація з підписом «הדמיה» / «visualization», а файл
існує. Окремо — слова: «עץ אלון מלא» / «solid oak» лише про кромки й фасади (решта — шпон), і жодних
«купити»: грошей не беремо.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

PROJECT = pathlib.Path(__file__).resolve().parent.parent
CATALOG = PROJECT / "catalog" / "products.json"
ASSETS = PROJECT / "site"

LOCALES = ("he", "en")
CATEGORIES = {"dining_table", "coffee_table", "media_unit", "console"}
HEBREW = re.compile(r"[א-ת]")
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
# Масив дозволено називати лише про те, що справді масив: кромки й фасади.
SOLID_EN = re.compile(r"solid[- ]oak\s+(\w+)", re.IGNORECASE)
SOLID_EN_OK = {"edge", "edges", "front", "fronts"}
SOLID_HE = "אלון מלא"
SOLID_HE_OK = ("קנט", "חזית")
FORBIDDEN = ("קנו עכשיו", "קנה עכשיו", "במלאי", "buy now", "in stock", "add to cart")


def _load():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def _texts(product):
    """Усі рядки товару, які бачить гість, — з локаллю."""
    for key in ("name", "tagline", "description", "material"):
        for loc in LOCALES:
            yield loc, product[key][loc]
    for group in ("finishes", "bases"):
        for item in product[group]:
            for loc in LOCALES:
                yield loc, item["name"][loc]
    for badge in product["badges"]:
        for loc in LOCALES:
            yield loc, badge["label"][loc]
    for image in product["images"]:
        for loc in LOCALES:
            yield loc, image["alt"][loc]


def _false_solid_claim(loc, text):
    """True, якщо текст називає масивом щось, крім кромок і фасадів."""
    if loc == "en":
        return any(w.lower() not in SOLID_EN_OK for w in SOLID_EN.findall(text))
    start = text.find(SOLID_HE)
    while start != -1:
        if not any(w in text[max(0, start - 20):start] for w in SOLID_HE_OK):
            return True
        start = text.find(SOLID_HE, start + 1)
    return False


class CatalogSchemaTest(unittest.TestCase):
    def setUp(self):
        self.products = _load()

    def test_four_to_five_products_unique(self):
        self.assertIsInstance(self.products, list)
        self.assertTrue(4 <= len(self.products) <= 5, len(self.products))
        ids = [p["id"] for p in self.products]
        slugs = [p["slug"] for p in self.products]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(slugs), len(set(slugs)))
        for slug in slugs:
            self.assertRegex(slug, SLUG)

    def test_bilingual_fields(self):
        for p in self.products:
            for key in ("name", "tagline", "description", "material"):
                with self.subTest(product=p["id"], key=key):
                    self.assertEqual(set(p[key]), set(LOCALES))
                    self.assertRegex(p[key]["he"], HEBREW)
                    self.assertTrue(p[key]["en"].strip())
                    self.assertIsNone(HEBREW.search(p[key]["en"]))

    def test_category(self):
        for p in self.products:
            self.assertIn(p["category"], CATEGORIES, p["id"])

    def test_sizes_and_prices(self):
        for p in self.products:
            with self.subTest(product=p["id"]):
                sizes = p["sizes"]
                self.assertTrue(sizes)
                labels = [s["label"] for s in sizes]
                self.assertEqual(len(labels), len(set(labels)))
                for s in sizes:
                    for dim in ("length_cm", "width_cm", "height_cm", "price_ils"):
                        self.assertIsInstance(s[dim], int)
                        self.assertGreater(s[dim], 0)
                    if "extended_cm" in s:
                        self.assertGreater(s["extended_cm"], s["length_cm"])
                self.assertEqual(p["price_from_ils"], min(s["price_ils"] for s in sizes))

    def test_extendable_has_extended_size(self):
        for p in self.products:
            badges = {b["id"] for b in p["badges"]}
            extended = ["extended_cm" in s for s in p["sizes"]]
            self.assertEqual("extendable" in badges, all(extended), p["id"])
            if "extendable" not in badges:
                self.assertFalse(any(extended), p["id"])

    def test_prices_marked_preliminary(self):
        # Поправка головного 20.10 22:45: ціна й строк без підтвердження фабрики — «מחיר משוער».
        for p in self.products:
            self.assertIs(p["preliminary"], True, p["id"])

    def test_lead_time(self):
        for p in self.products:
            self.assertEqual(p["lead_time_weeks"], [10, 12], p["id"])

    def test_finishes_and_bases(self):
        for p in self.products:
            with self.subTest(product=p["id"]):
                self.assertTrue(4 <= len(p["finishes"]) <= 6)
                ids = [f["id"] for f in p["finishes"]]
                self.assertEqual(len(ids), len(set(ids)))
                for f in p["finishes"]:
                    self.assertRegex(f["hex"], HEX)
                    self.assertEqual(set(f["name"]), set(LOCALES))
                for b in p["bases"]:
                    self.assertEqual(set(b), {"id", "name"})
                    self.assertEqual(set(b["name"]), set(LOCALES))

    def test_images_are_labelled_visualizations(self):
        for p in self.products:
            for image in p["images"]:
                with self.subTest(product=p["id"], src=image["src"]):
                    self.assertEqual(image["kind"], "visualization")
                    self.assertTrue(image["src"].startswith("assets/products/"), image["src"])
                    self.assertTrue((ASSETS / image["src"]).is_file(), image["src"])
                    self.assertIn("הדמיה", image["alt"]["he"])
                    self.assertIn("visualization", image["alt"]["en"].lower())
                    self.assertIn(image["source"], {"ai", "render"})

    def test_image_variants_exist_and_hero_is_light(self):
        # Вітрина ставить <picture>: AVIF і WebP 800/1600 мають існувати; герой AVIF ≤ 180 КБ (контракт ночі).
        for p in self.products:
            if not p["images"]:
                continue
            with self.subTest(product=p["id"]):
                self.assertEqual(p["images"][0]["view"], "hero")
                for image in p["images"]:
                    for fmt in ("avif", "webp"):
                        for entry in image["srcset"][fmt].split(", "):
                            self.assertTrue((ASSETS / entry.split(" ")[0]).is_file(), entry)
                self.assertLessEqual((ASSETS / p["images"][0]["avif"]).stat().st_size, 180 * 1024)

    def test_model3d_exists(self):
        for p in self.products:
            if p.get("model3d"):
                self.assertTrue(p["model3d"].startswith("assets/products/"), p["id"])
                self.assertTrue((ASSETS / p["model3d"]).is_file(), p["model3d"])

    def test_solid_oak_only_for_edges_and_fronts(self):
        for p in self.products:
            for loc, text in _texts(p):
                self.assertFalse(_false_solid_claim(loc, text), (p["id"], loc, text))

    def test_no_buy_language(self):
        for p in self.products:
            for loc, text in _texts(p):
                for phrase in FORBIDDEN:
                    self.assertNotIn(phrase, text.lower(), (p["id"], loc))

    def test_rule_catches_solid_oak_claim(self):
        # Перевірка правила на зламаних даних — у пам'яті, не на диску.
        bad = dict(self.products[0])
        bad["description"] = {"he": "שולחן מעץ אלון מלא", "en": "A solid oak table"}
        failures = sorted({loc for loc, text in _texts(bad) if _false_solid_claim(loc, text)})
        self.assertEqual(failures, ["en", "he"])


if __name__ == "__main__":
    unittest.main()
