"""Блок «עץ אמיתי, בלי סיפורים»: фанера названа фанерою, «עץ אלון מלא» — лише про крайки й фасади."""

from __future__ import annotations

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def strings(loc: str) -> dict:
    d = json.loads((ROOT / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
    return {k: v for k, v in d.items() if k.startswith("matb_")}


class MaterialBlockTests(unittest.TestCase):
    def test_veneer_is_called_veneer(self):
        self.assertIn("פורניר אלון טבעי", strings("he")["matb_1_h"])
        self.assertIn("natural oak veneer", strings("en")["matb_1_h"].lower())

    def test_solid_oak_only_about_edges_and_fronts(self):
        for k, v in strings("he").items():
            if "אלון מלא" in v:
                self.assertTrue(k.startswith("matb_2_"), k)
        for k, v in strings("en").items():
            if "solid oak" in v.lower() and "not solid" not in v.lower():
                self.assertTrue(k.startswith("matb_2_"), k)

    def test_no_sales_or_discount_words(self):
        for v in strings("he").values():
            for bad in ("קנה", "מחיר השקה", "הנחה"):
                self.assertNotIn(bad, v)

    def test_finish_count_from_catalog_not_digits(self):
        for loc in ("he", "en"):
            self.assertIn("{{FINISH_COUNT_CAP}}", strings(loc)["matb_3_h"])


if __name__ == "__main__":
    unittest.main()
