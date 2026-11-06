#!/usr/bin/env python3
"""Воронка магазину текстом — ті самі цифри, що на /admin/funnel (specs/003-shop-funnel).

    FX_DB_PATH=/opt/ihor/aluma-table/data/aluma.db python3 tools/funnel_report.py            # 7 днів
    python3 tools/funnel_report.py --days 1          # сьогодні (Asia/Jerusalem)
    python3 tools/funnel_report.py --days 0 --json   # усе, машинний вигляд

Лише рахунок: сесії, кроки, slug товару, utm, ціни каталогу. Імен, телефонів, текстів заявок
скрипт не друкує — він їх навіть не читає в звіт (api/funnel.py бере тільки session_id і product_id).
Бази за FX_DB_PATH нема — вихід 2, порожню не створює. База відкрита лише на читання (SQLite mode=ro, №42):
звіт не створює таблиць, не перемикає журнал і не може нічого записати в бойову базу.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import funnel  # noqa: E402
from api import funnel_io  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Воронка магазину ALUMA (лише рахунок)")
    ap.add_argument("--days", type=int, default=7, help="календарні дні Asia/Jerusalem; 0 — усе")
    ap.add_argument("--include-test", action="store_true", help="рахувати й рядки з x-test: 1")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        tables = funnel_io.open_tables(funnel_io.FX_DB_PATH, readonly=True)
    except FileNotFoundError:
        print(f"no database at FX_DB_PATH={funnel_io.FX_DB_PATH}", file=sys.stderr)
        return 2
    events, leads = funnel_io.load(args.days, True, tables)
    rep = funnel.report(events, leads, args.days, include_test=args.include_test)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else funnel.text(rep), end="" if not args.json else "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
