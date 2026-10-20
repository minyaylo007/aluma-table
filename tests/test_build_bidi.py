"""Розміри в he-описах каталогу: U+2066 … U+2069 → <bdi dir="ltr"> після екранування, інакше «100×60» читається як «60×100»."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

SPEC = importlib.util.spec_from_file_location("aluma_build", pathlib.Path(__file__).resolve().parent.parent / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class EscBidiTests(unittest.TestCase):
    def test_isolate_marks_become_bdi(self):
        self.assertEqual(build.esc_bidi("שולחן ⁦100×60⁩ ס״מ"), 'שולחן <bdi dir="ltr">100×60</bdi> ס״מ')

    def test_text_inside_is_still_escaped(self):
        self.assertEqual(build.esc_bidi("⁦<b>&⁩"), '<bdi dir="ltr">&lt;b&gt;&amp;</bdi>')

    def test_plain_text_unchanged(self):
        self.assertEqual(build.esc_bidi("בלי סימנים"), "בלי סימנים")


if __name__ == "__main__":
    unittest.main()
