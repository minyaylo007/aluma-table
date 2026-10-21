"""deploy/caddy/aluma-site-body.caddyfile — сторінка 404 своєї мови: /en/* → /en/404.html, /ru/* → /ru/404.html.

build.py публікує 404 у кожну локаль (LOCALES); Caddy мусить віддавати саме її, а не івритську /404.html.
Перевірка лише текстом файлу: бінарник caddy в CI не обовʼязковий, запускати Caddy сесіям заборонено.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BODY = (ROOT / "deploy" / "caddy" / "aluma-site-body.caddyfile").read_text(encoding="utf-8")


def _errors_block(text: str) -> str:
    """Тіло handle_errors 403 404 { … } без коментарів — за балансом дужок."""
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    start = code.index("handle_errors 403 404 {")
    depth = 0
    for i in range(start, len(code)):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return code[start : i + 1]
    raise AssertionError("handle_errors без закриваючої дужки")


class Caddy404LocaleTests(unittest.TestCase):
    def setUp(self) -> None:
        import build

        self.locales = build.LOCALES
        self.block = _errors_block(BODY)

    def test_each_locale_prefix_has_own_404(self) -> None:
        prefixes = [p for p in self.locales.values() if p]
        self.assertTrue(prefixes, "у LOCALES мають бути локалі з префіксом")
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                self.assertRegex(self.block, rf"path {re.escape(prefix)}/\*\n")
                self.assertRegex(self.block, rf"rewrite \* {re.escape(prefix)}/404\.html\n")

    def test_root_fallback_is_hebrew_404(self) -> None:
        self.assertRegex(self.block, r"rewrite \* /404\.html\n")
        # Останній handle — без матчера: решта шляхів (корінь, he) іде в /404.html.
        self.assertRegex(self.block, r"handle \{\s*rewrite \* /404\.html")

    def test_branches_are_exclusive_and_keep_status_and_no_store(self) -> None:
        # Жодного rewrite на верхньому рівні handle_errors — лише всередині handle.
        top = re.sub(r"handle[^\n{]*\{[^{}]*(\{[^{}]*\}[^{}]*)*\}", "", self.block[self.block.index("{") + 1 :])
        self.assertNotIn("rewrite", top)
        self.assertIn('header Cache-Control "no-store"', top)
        branches = len([p for p in self.locales.values() if p]) + 1
        self.assertEqual(self.block.count("status 404"), branches)
        self.assertEqual(self.block.count("rewrite * "), branches)


if __name__ == "__main__":
    unittest.main()
