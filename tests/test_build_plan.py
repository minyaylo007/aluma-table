"""План «סגור / פתוח» і блок «איך נפתח השולחן»: місця лише в межах seats каталогу, без вигаданих блоків."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("aluma_build", ROOT / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


def products() -> list:
    data = json.loads((ROOT / "catalog" / "products.json").read_text(encoding="utf-8"))
    return data["products"] if isinstance(data, dict) else data


class PlanTests(unittest.TestCase):
    def test_seats_stay_inside_catalog_range(self):
        for p in products():
            seats = p.get("seats")
            if not seats:
                continue
            html = build.plan(p, "he")
            got = [int(n) for n in re.findall(r"· (\d+) \{\{t\.unfold_seats\}\}", html)]
            self.assertTrue(got, p["slug"])
            lo = min(seats["closed"][0], seats["extended"][0])
            hi = max(seats["closed"][-1], seats["extended"][-1])
            for n in got:
                self.assertTrue(lo <= n <= hi, (p["slug"], n))

    def test_drawn_chairs_match_caption(self):
        for p in products():
            for size in re.findall(r'<div class="plan-size".*?</div>', build.plan(p, "he")):
                for fig in re.findall(r"<figure.*?</figure>", size):
                    n = int(re.search(r"· (\d+) \{\{t\.unfold_seats\}\}", fig).group(1))
                    self.assertEqual(fig.count('class="plan-chair"'), n, p["slug"])

    def test_one_plan_per_extendable_size_first_visible(self):
        for p in products():
            ext = [s for s in p.get("sizes") or [] if s.get("extended_cm")]
            html = build.plan(p, "he")
            if not ext or not p.get("seats"):
                self.assertEqual(html, "", p["slug"])
                continue
            self.assertEqual(html.count("data-plan-size="), len(ext), p["slug"])
            self.assertEqual(html.count(" hidden>"), len(ext) - 1, p["slug"])

    def test_geometry(self):
        self.assertEqual(build.plan_seats(160, 90, False, [6, 8]), 6)
        self.assertEqual(build.plan_seats(180, 90, False, [6, 8]), 8)
        self.assertEqual(build.plan_seats(280, 90, False, [10, 12]), 12)
        self.assertEqual(build.plan_seats(115, 115, True, [4, 4]), 4)
        self.assertEqual(build.plan_seats(400, 90, False, [10, 12]), 12)  # затиснуто зверху

    def test_how_block_only_with_frames_or_plan(self):
        for p in products():
            html = build.how(p, "he")
            has_frames = sum(1 for i in p.get("images") or [] if i.get("view") == "mechanism") >= 2
            if has_frames:
                self.assertIn("how-steps", html, p["slug"])
                self.assertIn("{{t.viz_tag}}", html)
            else:
                self.assertNotIn("how-steps", html, p["slug"])
            if not has_frames and not build.plan(p, "he"):
                self.assertEqual(html, "", p["slug"])


class RussianPluralTests(unittest.TestCase):
    """ru після числа: 1/5–20 — сам ключ («6 размеров», «8 человек»), 2–4 крім 12–14 — «_few» («3 размера», «4 человека»)."""

    def test_few(self):
        for n in (2, 3, 4, 22, 34, 102):
            self.assertEqual(build.few("unfold_seats", n, "ru"), "unfold_seats_few", n)
        for n in (5, 6, 8, 10, 11, 12, 13, 14, 20, 112):
            self.assertEqual(build.few("unfold_seats", n, "ru"), "unfold_seats", n)
        for loc in ("he", "en"):
            self.assertEqual(build.few("inc_sizes", 3, loc), "inc_sizes", loc)

    def test_keys_exist_in_every_locale(self):
        for loc in ("he", "en", "ru"):
            t = json.loads((ROOT / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))
            for key in ("inc_sizes", "unfold_seats"):
                self.assertIn(key + "_few", t, loc)

    def test_ru_card_uses_the_right_form(self):
        for p in products():
            html = build.plan(p, "ru")
            for n, key in re.findall(r"· (\d+) \{\{t\.(unfold_seats(?:_few)?)\}\}", html):
                self.assertEqual(key, build.few("unfold_seats", int(n), "ru"), (p["slug"], n))


if __name__ == "__main__":
    unittest.main()
