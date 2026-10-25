#!/usr/bin/env python3
"""Ключі i18n/<мова>.json, на які нема посилань у site/ і build.py (№23, 25.10).

Ключ використаний, якщо його ім'я стоїть словом у site/** чи build.py, або підпадає під динамічне ім'я з build.py:
префікс перед «{» у f-рядку (`t.trust_strip_{k}_p`, `inside_{k}` → усе, що починається з «trust_strip_», «inside_»)
і форма «_few» для ru (`few("inc_sizes", …)` → «inc_sizes_few»). Помилка в бік «використаний» — безпечна; хибне
«не використаний» ловить сама збірка: невідомий {{t.key}} валить build.py («unknown tokens in templates»).
Вкладені обʼєкти (`js`, `faq`, `cities`) рахуються цілком за своїм іменем; `_comment` і `_*` — не ключі.

  python3 tools/i18n_unused.py            # список, код 1, якщо щось знайшлося
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCALES = ("he", "en", "ru")
TEXT = {".html", ".js", ".css", ".json", ".svg", ".txt", ".xml", ".webmanifest"}
# Свідомо лишені без посилань у site/: viz_tag — слово «הדמיה» для креативів (рівність ru-креативів і /ru/ —
# tests/test_quality_creatives.py), рішення диригента 25.10
KEEP = {"viz_tag"}


def corpus(root: pathlib.Path) -> str:
    parts = [(root / "build.py").read_text(encoding="utf-8")]
    for f in sorted((root / "site").rglob("*")):
        if f.is_file() and f.suffix in TEXT and "vendor" not in f.parts:
            parts.append(f.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def dynamic_prefixes(build_src: str) -> set[str]:
    # «inside_{k}», «trust_strip_{k}_p», «unfold_{state}» — ім'я, що закінчується «_» просто перед «{»
    return set(re.findall(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)*_)\{", build_src))


def unused(root: pathlib.Path = ROOT) -> list[str]:
    text = corpus(root)
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))
    prefixes = dynamic_prefixes((root / "build.py").read_text(encoding="utf-8"))
    keys: set[str] = set()
    for loc in LOCALES:
        keys |= {k for k in json.loads((root / "i18n" / f"{loc}.json").read_text(encoding="utf-8")) if not k.startswith("_")}

    def used(k: str) -> bool:
        if k in words or k in KEEP:
            return True
        if k.endswith("_few") and k[:-4] in words:
            return True
        return any(k.startswith(p) for p in prefixes)

    return sorted(k for k in keys if not used(k))


def main() -> int:
    found = unused()
    for k in found:
        print(k)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
