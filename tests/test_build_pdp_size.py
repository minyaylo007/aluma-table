"""№36: розмір за замовчуванням із каталогу, розклад і місця в плитці, таблиця «איזה גודל מתאים לכם» — усе з catalog/products.json."""

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
BY = {p["slug"]: p for p in PRODUCTS}


def checked(html: str) -> str:
    m = re.search(r'name="size" value="([^"]+)" data-price="\d+" checked', html)
    return m.group(1) if m else ""


class PdpSizeTests(unittest.TestCase):
    def test_tavor_defaults_to_200x100(self):
        self.assertEqual(build.default_size(BY["tavor"])["label"], "200×100")
        for loc in ("he", "en", "ru"):
            self.assertEqual(checked(build.configurator(BY["tavor"], loc)), "200×100")
        # «מ־» на картках каталогу — як і було, від найдешевшого
        self.assertEqual(BY["tavor"]["price_from_ils"], 4490)

    def test_default_falls_back_to_first(self):
        p = copy.deepcopy(BY["tavor"])
        for s in p["sizes"]:
            s.pop("default", None)
        self.assertEqual(checked(build.configurator(p, "he")), p["sizes"][0]["label"])
        self.assertEqual(checked(build.configurator(BY["ofek"], "he")), BY["ofek"]["sizes"][0]["label"])

    def test_pill_shows_extended_and_seats_from_catalog(self):
        html = build.configurator(BY["tavor"], "he")
        self.assertIn('{{t.facts_open}} <bdi dir="ltr">280</bdi>', html)
        self.assertIn('<bdi dir="ltr">8–12</bdi> {{t.unfold_seats}}', html)
        sahar = build.configurator(BY["sahar"], "ru")
        self.assertIn('<bdi dir="ltr">155</bdi>', sahar)
        self.assertIn('<bdi dir="ltr">4–6</bdi>', sahar)
        # інше розкладання в каталозі — інше число в плитці (не хардкод)
        p = copy.deepcopy(BY["tavor"])
        p["sizes"][-1]["extended_cm"] = 300
        self.assertIn('<bdi dir="ltr">300</bdi>', build.configurator(p, "he"))

    def test_seats_stay_inside_catalog_range(self):
        for p in PRODUCTS:
            seats = p.get("seats")
            for s in p["sizes"]:
                st = build.size_seats(p, s)
                if not seats or not s.get("extended_cm"):
                    self.assertIsNone(st)
                    continue
                self.assertTrue(seats["closed"][0] <= st[0] <= seats["closed"][-1], (p["slug"], s["label"]))
                self.assertTrue(seats["extended"][0] <= st[1] <= seats["extended"][-1], (p["slug"], s["label"]))

    def test_size_table_is_accessible_and_from_catalog(self):
        html = build.size_table(BY["tavor"], "he")
        # при шрифті 200 % на 390 таблиця гортається у власній рамці, не сторінка (responsive.spec.js); без tabindex — порядок Tab redesign.spec.js
        self.assertIn('<div class="sizes-scroll"><table class="sizes-tbl">', html)
        self.assertEqual(html.count('scope="col"'), 4)
        self.assertEqual(html.count('scope="row"'), len(BY["tavor"]["sizes"]))
        self.assertIn("200 → 280", html)
        self.assertIn("8 / 12", html)
        self.assertNotIn("₪", re.sub(r"<td><bdi dir=\"ltr\">₪[\d,]+</bdi></td>", "", html))
        # одна плитка (SAHAR) і товари без розкладки — без таблиці
        self.assertEqual(build.size_table(BY["sahar"], "he"), "")
        self.assertEqual(build.size_table(BY["ofek"], "he"), "")

    def test_plan_shows_default_size(self):
        html = build.plan(BY["tavor"], "he")
        self.assertRegex(html, r'data-plan-size="200×100">')
        self.assertRegex(html, r'data-plan-size="160×90" hidden>')


if __name__ == "__main__":
    unittest.main()
