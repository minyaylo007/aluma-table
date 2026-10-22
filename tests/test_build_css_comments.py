"""Коментарі CSS не їдуть у вбудований <style> (замір 22.10: 12,9 КБ українських пояснень у кожній сторінці).

build.strip_css_comments — проста регулярка /\\*[\\s\\S]*?\\*/. Вона безпечна, доки в наших CSS нема «/*» чи «*/»
усередині рядка ("…", '…') або url(…): тоді вона з'їла б шматок правила. Цей модуль стереже обидва боки.
Сторінки зібраного сайту (без «/*» узагалі) — tests/test_build_site.py.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("aluma_build_css", ROOT / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)

INLINED = ["aluma.css"] + [f"fonts-{loc}.css" for loc in build.LOCALES]
STRING_OR_URL = re.compile(r"\"[^\"\n]*\"|'[^'\n]*'|url\([^)]*\)")


class StripCssCommentsTests(unittest.TestCase):
    def test_removes_line_block_and_inline_comments(self):
        css = "/* шапка\n   на два рядки */\na { color: red; } /* поруч */\n\n/* сам */\nb{x:1/* усередині */;}\n"
        self.assertEqual(build.strip_css_comments(css), "a { color: red; }\nb{x:1;}")

    def test_keeps_everything_else_byte_for_byte(self):
        css = 'a::before { content: "→ x"; }\n@media (min-width: 9px) {\n  .b { background: url(/assets/a.svg); }\n}'
        self.assertEqual(build.strip_css_comments(css), css)

    def test_non_greedy_between_two_comments(self):
        self.assertEqual(build.strip_css_comments("/*1*/a{}/*2*/"), "a{}")


class SourceCssGuardTests(unittest.TestCase):
    def test_no_comment_markers_inside_strings_or_urls(self):
        for name in INLINED:
            css = (ROOT / "site" / "assets" / name).read_text(encoding="utf-8")
            for m in STRING_OR_URL.finditer(build.CSS_COMMENT.sub("", css)):
                self.assertNotIn("/*", m.group(0), f"{name}: {m.group(0)[:60]}")
                self.assertNotIn("*/", m.group(0), f"{name}: {m.group(0)[:60]}")

    def test_comments_are_balanced(self):
        for name in INLINED:
            out = build.strip_css_comments((ROOT / "site" / "assets" / name).read_text(encoding="utf-8"))
            self.assertNotIn("/*", out, name)
            self.assertNotIn("*/", out, name)

    def test_rules_survive(self):
        # жодне правило не зникло разом із коментарем: дужок стільки ж, скільки в джерелі без коментарів
        for name in INLINED:
            css = (ROOT / "site" / "assets" / name).read_text(encoding="utf-8")
            out = build.strip_css_comments(css)
            no_comments = build.CSS_COMMENT.sub("", css)
            self.assertEqual(out.count("{"), no_comments.count("{"), name)
            self.assertEqual(out.count("}"), out.count("{"), name)
            self.assertGreater(out.count("{"), 0, name)


if __name__ == "__main__":
    unittest.main()
