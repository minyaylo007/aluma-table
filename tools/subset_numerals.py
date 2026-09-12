#!/usr/bin/env python3
"""Cut a numerals-and-punctuation face out of each Latin subset so the Hebrew page stops downloading it.

The Hebrew page is Hebrew except for its numbers: the price, the dimensions, the lead time. Those
glyphs (digits, comma, period, en dash, multiplication sign, plus) live only in the Latin subset
faces, which are ~19 KB each — so a Hebrew visitor was pulling 39 KB of Latin letters to render
"5,990". This writes PlexSansHebrew-<w>-num.woff2 (a couple of KB) from the existing Latin woff2
with pyftsubset, and fonts.css declares it AFTER the Latin face for the same family/weight: with
overlapping unicode-ranges the last matching @font-face wins, so the numerals come from the small
file and the full Latin face is fetched only when actual Latin letters appear.

    python tools/subset_numerals.py         # rewrites site/assets/fonts/*-num.woff2

Requires fontTools (pyftsubset). Source: the already-subsetted Latin faces in site/assets/fonts.
"""
import pathlib
import subprocess
import sys

FONTS = pathlib.Path(__file__).resolve().parents[1] / "site" / "assets" / "fonts"
WEIGHTS = ("400", "600", "700")
# What a Hebrew page borrows from the Latin subset: digits and the punctuation that sits between
# them or between Hebrew words. Measured from the rendered page, per weight — the middle dot and the
# question mark alone were pulling a 20 KB Latin face onto every Hebrew visit — and so, all
# along, did the plain space: U+0020 is in the Latin range and in no Hebrew subset.
UNICODES = ("U+0020,U+0021,U+0025,U+0028-0029,U+002B-002F,U+0030-0039,U+003A-003B,U+003F,"
            "U+00A0,U+00A9,U+00B7,U+00D7,U+2013-2014")


def main() -> None:
    for w in WEIGHTS:
        src = FONTS / f"PlexSansHebrew-{w}-latin.woff2"
        dst = FONTS / f"PlexSansHebrew-{w}-num.woff2"
        if not src.exists():
            sys.exit(f"missing {src}")
        subprocess.run([sys.executable, "-m", "fontTools.subset", str(src),
                        f"--unicodes={UNICODES}", "--flavor=woff2", "--layout-features=*",
                        f"--output-file={dst}"], check=True)
        print(f"{dst.name}: {dst.stat().st_size} B  (from {src.name}: {src.stat().st_size} B)")


if __name__ == "__main__":
    main()
