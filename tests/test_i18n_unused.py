"""tools/i18n_unused.py: у i18n/<мова>.json нема ключів без посилань у site/ і build.py (№23).

Мертвий ключ — переклад, який ніхто не бачить і всі три мови тягнуть далі (pt_2 після №19). Новий рядок
без місця на сторінці — червоний тест; свідомо лишений — у KEEP із причиною.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
import unittest

from tools import i18n_unused

PROJECT = pathlib.Path(__file__).resolve().parent.parent


class I18nUnusedTests(unittest.TestCase):
    def test_no_unused_keys(self):
        self.assertEqual(i18n_unused.unused(), [])

    def test_finds_a_key_without_reference_and_respects_dynamic_names(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-i18n-unused-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / "site").mkdir()
        (tmp / "i18n").mkdir()
        (tmp / "site" / "page.html").write_text("<p>{{t.used}}</p>", encoding="utf-8")
        (tmp / "build.py").write_text('x = f"{{{{t.inside_{k}}}}}" + few("inc_sizes", n, loc)\n', encoding="utf-8")
        keys = {"_comment": "", "used": "", "dead": "", "inside_legs": "", "inc_sizes": "", "inc_sizes_few": "", "viz_tag": ""}
        for loc in i18n_unused.LOCALES:
            (tmp / "i18n" / f"{loc}.json").write_text(json.dumps(keys), encoding="utf-8")
        self.assertEqual(i18n_unused.unused(tmp), ["dead"])


if __name__ == "__main__":
    unittest.main()
