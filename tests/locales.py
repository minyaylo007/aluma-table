"""Мови вітрини для тестів — з build.LOCALES (одне джерело), без імпорту build.py (він читає дерево при імпорті).

    LOCALES  {"he": "", "en": "/en", …}   мова -> префікс шляху; перша — корінь сайту і x-default
    DIST_PREFIX  {"he": "", "en": "en/", …}   префікс відносного шляху в dist/
    DIRS     {"he": "rtl", "en": "ltr", …}  з i18n/<мова>.json
"""

from __future__ import annotations

import ast
import json
import pathlib

PROJECT = pathlib.Path(__file__).resolve().parent.parent


def _locales() -> dict:
    tree = ast.parse((PROJECT / "build.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(getattr(t, "id", "") == "LOCALES" for t in n.targets))
    return ast.literal_eval(node.value)


LOCALES: dict = _locales()
DIST_PREFIX = {loc: (prefix.lstrip("/") + "/" if prefix else "") for loc, prefix in LOCALES.items()}
DIRS = {loc: json.loads((PROJECT / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["dir"] for loc in LOCALES}


def lang_of(rel: str) -> str:
    """Мова сторінки за її шляхом у dist/ (найдовший збіжний префікс; корінь — перша мова)."""
    for loc, pre in sorted(DIST_PREFIX.items(), key=lambda kv: -len(kv[1])):
        if pre and rel.startswith(pre):
            return loc
    return next(iter(LOCALES))
