"""Превью посилання (og:image) — тільки своє site/assets/og/<name>.jpg; запасного og.png GOREN нема (№44).

Нема картинки для сторінки — збірка падає з назвою файлу, а не мовчки роздає чуже чи порожнє превью.
"""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

PROJECT = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("aluma_build_og", PROJECT / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class OgImageRequiredTests(unittest.TestCase):
    def test_existing_picture_is_its_own_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = pathlib.Path(tmp)
            (site / "assets" / "og").mkdir(parents=True)
            (site / "assets" / "og" / "tavor.jpg").write_bytes(b"x")
            with mock.patch.object(build, "SITE", site):
                self.assertEqual(build.og_image("tavor"), "/assets/og/tavor.jpg")

    def test_missing_picture_stops_the_build_with_its_name(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(build, "SITE", pathlib.Path(tmp)):
            with self.assertRaises(SystemExit) as cm:
                build.og_image("tavor")
        self.assertIn("site/assets/og/tavor.jpg", str(cm.exception))
        self.assertIn("make-og-products.js", str(cm.exception))

    def test_no_fallback_to_old_goren_card(self):
        self.assertNotIn("/assets/og.png", (PROJECT / "build.py").read_text(encoding="utf-8"))
        self.assertFalse((PROJECT / "site" / "assets" / "og.png").exists())


if __name__ == "__main__":
    unittest.main()
