"""Латиниця Plex на he: лише latin-he (A–Z, a–z, Ø, лапки), повні *-latin — тільки en/ru. Без збірки.

22.10: he-картка після #109 ще качала PlexSansHebrew-400-latin (19 КБ) і 600-latin (20 КБ) заради кількох латинських
слів («Meta Pixel», «WhatsApp», «English»). Сторінка мови вбудовує aluma.css + fonts-<мова>.css (site/_layout.html,
build.py), тож перевіряємо саме цю пару: he не згадує повних *-latin, en згадує; діапазони облич Plex однієї ваги на he
не перетинаються (кожен знак — один файл); жоден видимий латинський знак he-текстів не лишився без обличчя.
Що dist/p/tavor/ без *-latin, а dist/en/p/tavor/ з ними, — tests/test_build_site.py (зі збіркою, набір --pr).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import unittest

PROJECT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = PROJECT / "site" / "assets"
FACE = re.compile(r"@font-face\s*\{([^}]*)\}")


def _tool():
    spec = importlib.util.spec_from_file_location("subset_locale_fonts", PROJECT / "tools" / "subset_locale_fonts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def codepoints(rng: str) -> set:
    out = set()
    for part in rng.replace(" ", "").split(","):
        lo, _, hi = part[2:].partition("-")
        out |= set(range(int(lo, 16), int(hi or lo, 16) + 1))
    return out


def faces(loc: str) -> list:
    """(родина, вага, файл, кодові точки) усіх облич, що їх вбудовує сторінка мови, у порядку оголошення."""
    css = (ASSETS / "aluma.css").read_text(encoding="utf-8") + (ASSETS / f"fonts-{loc}.css").read_text(encoding="utf-8")
    out = []
    for body in FACE.findall(css):
        fam = re.search(r'font-family:\s*"([^"]+)"', body).group(1)
        src = re.search(r"url\(/assets/fonts/([\w\-.]+)\)", body)
        rng = re.search(r"unicode-range:\s*([^;]+);", body)
        weight = re.search(r"font-weight:\s*([\d ]+);", body)
        if src and rng:
            out.append((fam, weight.group(1) if weight else "", src.group(1), codepoints(rng.group(1))))
    return out


class HebrewPlexLatinTests(unittest.TestCase):
    def test_he_embeds_latin_he_not_full_latin(self):
        he = {f for _, _, f, _ in faces("he")}
        en = {f for _, _, f, _ in faces("en")}
        for w in (400, 600, 700):
            self.assertNotIn(f"PlexSansHebrew-{w}-latin.woff2", he)
            self.assertIn(f"PlexSansHebrew-{w}-latin-he.woff2", he)
            self.assertIn(f"PlexSansHebrew-{w}-latin.woff2", en)
            self.assertNotIn(f"PlexSansHebrew-{w}-latin-he.woff2", en)
        ru = {f for _, _, f, _ in faces("ru")}
        self.assertTrue({f"PlexSansHebrew-{w}-latin.woff2" for w in (400, 600)} <= ru)

    def test_plex_faces_on_he_do_not_overlap(self):
        # кожен знак на he — рівно одне обличчя Plex своєї ваги: latin-he не дублює num чи івритське
        by_weight = {}
        for fam, w, f, cps in faces("he"):
            if fam == "IBM Plex Sans Hebrew":
                by_weight.setdefault(w, []).append((f, cps))
        self.assertEqual(set(by_weight), {"400", "600", "700"})
        for w, lst in by_weight.items():
            for i, (fa, a) in enumerate(lst):
                for fb, b in lst[i + 1:]:
                    with self.subTest(weight=w, a=fa, b=fb):
                        self.assertEqual(sorted(a & b), [])

    def test_latin_he_range_is_the_cut_list_and_has_no_digits(self):
        tool = _tool()
        css = (ASSETS / "fonts-he.css").read_text(encoding="utf-8")
        for w in (400, 600, 700):
            m = re.search(rf"PlexSansHebrew-{w}-latin-he\.woff2\)[^}}]*?unicode-range: ([^;]+);", css)
            self.assertIsNotNone(m, w)
            self.assertEqual(m.group(1), tool.PLEX_HE_LATIN_UNICODES)
            self.assertTrue((ASSETS / "fonts" / f"PlexSansHebrew-{w}-latin-he.woff2").is_file())
        cps = codepoints(tool.PLEX_HE_LATIN_UNICODES)
        self.assertTrue(set(range(0x41, 0x5B)) | set(range(0x61, 0x7B)) <= cps, "A–Z, a–z")
        self.assertFalse(cps & set(range(0x30, 0x3A)), "цифри — у num")

    def test_every_visible_latin_char_of_he_text_has_a_face(self):
        # видимий текст he (i18n/he.json без розмітки й {плейсхолдерів}): кожен знак із колишнього
        # діапазону повного latin малює одне з he-облич Plex 400 — інакше він упав би на системний Arial
        full_latin = codepoints((ASSETS / "fonts-en.css").read_text(encoding="utf-8").split(
            "PlexSansHebrew-400-latin.woff2", 1)[1].split("unicode-range:", 1)[1].split(";", 1)[0])
        covered = set()
        for fam, w, _, cps in faces("he"):
            if fam == "IBM Plex Sans Hebrew" and w == "400":
                covered |= cps

        def strings(o):
            if isinstance(o, str):
                yield o
            elif isinstance(o, dict):
                for v in o.values():
                    yield from strings(v)
            elif isinstance(o, list):
                for v in o:
                    yield from strings(v)

        he = json.loads((PROJECT / "i18n" / "he.json").read_text(encoding="utf-8"))
        for key in ("_comment", "lang", "dir", "locale", "font_display", "font_body"):   # службові, не текст сторінки
            he.pop(key, None)
        seen = set()
        for s in strings(he):
            s = re.sub(r"<[^>]*>", "", s)
            s = re.sub(r"\{\{?[\w.]+\}?\}", "", s)
            s = re.sub(r"&\w+;|&#\d+;", "", s)
            seen |= {ord(c) for c in s}
        missing = sorted(c for c in seen & full_latin if c not in covered and c not in (0x0A, 0x0D, 0x09))
        self.assertEqual([f"U+{c:04X} {chr(c)!r}" for c in missing], [])


if __name__ == "__main__":
    unittest.main()
