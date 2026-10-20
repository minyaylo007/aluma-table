"""Строк виготовлення, кількість і назви тонувань у текстах беруться з каталогу (аудит чесності 21.10, рядки 15–16)."""

from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("aluma_build", ROOT / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)
PRODUCTS = json.loads((ROOT / "catalog" / "products.json").read_text(encoding="utf-8"))


class CatalogFactsTests(unittest.TestCase):
    def test_lead_time_follows_the_catalog(self):
        ps = copy.deepcopy(PRODUCTS)
        for p in ps:
            p["lead_time_weeks"] = [8, 9]
        ps[0]["lead_time_weeks"] = [9, 14]
        self.assertEqual(build.catalog_facts(ps, "he")["LEAD_WEEKS"], "8–14")

    def test_finish_count_and_names_follow_the_catalog(self):
        ps = copy.deepcopy(PRODUCTS)
        for p in ps:
            p["finishes"] = p["finishes"][:3]
        he, en = build.catalog_facts(ps, "he"), build.catalog_facts(ps, "en")
        self.assertEqual((he["FINISH_COUNT"], en["FINISH_COUNT"], en["FINISH_COUNT_CAP"]), ("שלושה", "three", "Three"))
        self.assertEqual(he["FINISH_NAMES"].count(","), 1)
        self.assertIn(" ו", he["FINISH_NAMES"])
        self.assertIn(" and ", en["FINISH_NAMES"])

    def test_count_outside_the_words_is_digits(self):
        self.assertEqual(build.num_word(12, "he"), "־12")
        self.assertEqual(build.num_word(12, "en"), "12")

    def test_every_model_has_every_finish(self):
        # тексти кажуть «усі моделі в N тонуваннях» — це правда, лише поки набір тонувань у всіх однаковий
        sets = {p["slug"]: {f["id"] for f in p["finishes"]} for p in PRODUCTS}
        union = set().union(*sets.values())
        self.assertEqual({k for k, v in sets.items() if v != union}, set(), "зміни catalog_lede / v2_p, якщо так задумано")

    def test_i18n_holds_no_lead_time_or_finish_count(self):
        for loc in ("he", "en"):
            raw = (ROOT / "i18n" / f"{loc}.json").read_text(encoding="utf-8")
            self.assertNotRegex(raw, r"\d+\s*[–-]\s*\d+\s*(שבועות|weeks)", loc)
            self.assertIsNone(re.search(r"(חמישה|[Ff]ive) (גוונים|finishes)", raw), loc)


if __name__ == "__main__":
    unittest.main()
