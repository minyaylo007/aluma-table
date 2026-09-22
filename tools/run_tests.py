#!/usr/bin/env python3
r"""Два режими прогону тестів ALUMA — одна команда на кожен.

    tools/run_tests.py          критичний набір зі tests/CRITICAL.txt
    tools/run_tests.py --full   весь набір (unittest discover -s tests -t .)

Критичний набір — модулі, падіння яких щось змінює для гостя, грошей або власника
(правило відбору — у шапці tests/CRITICAL.txt). Повний набір ганяємо перед злиттям.

Рамка прогону (правило флоту, інцидент 14.09) — CLAUDE.md §8:

    TMPDIR=/tmp timeout 30m systemd-run --user --scope -q \
      --slice='app-ihor\x2dconductor.slice' -p MemoryMax=2G tools/run_tests.py

TMPDIR усередині дерева репозиторію валить test_serve_local_stack — тимчасова тека
тільки поза деревом.

Код повернення — як у unittest: 0, якщо зелено, 1 — інакше.
"""

from __future__ import annotations

import argparse
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRITICAL_LIST = ROOT / "tests" / "CRITICAL.txt"


def read_critical(path: Path) -> list[str]:
    """Імена модулів зі списку: без коментарів (# до кінця рядка) і порожніх рядків."""
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.split("#", 1)[0].strip()
        if name:
            names.append(name)
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--full", action="store_true",
                        help="весь набір замість критичного")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="ім'я кожного тесту")
    args = parser.parse_args(argv)

    # Корінь репозиторію в sys.path: тести імпортують api/, scripts/, tools/ від нього.
    sys.path.insert(0, str(ROOT))

    loader = unittest.TestLoader()
    if args.full:
        mode = "повний"
        suite = loader.discover(start_dir=str(ROOT / "tests"), top_level_dir=str(ROOT))
    else:
        mode = "критичний"
        if not CRITICAL_LIST.exists():
            print(f"немає списку критичного набору: {CRITICAL_LIST}", file=sys.stderr)
            return 2
        names = read_critical(CRITICAL_LIST)
        if not names:
            print(f"список критичного набору порожній: {CRITICAL_LIST}", file=sys.stderr)
            return 2
        suite = loader.loadTestsFromNames(names)

    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    seconds = time.monotonic() - started

    status = "OK" if result.wasSuccessful() else "ЧЕРВОНО"
    print(f"набір: {mode} | тестів: {result.testsRun} | {seconds:.1f} с | {status}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
