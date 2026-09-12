#!/usr/bin/env python3
"""Round 2 (2026-09-08, after the image audit): the local, call-free repair of nook-white-closed.

    python tools/imagegen/round2.py            # rebuilds night/imagegen/final/nook-white-closed.png from the round-1 final

Input:  night/imagegen/candidates/nook-white-closed-FINAL-r1.png (the round-1 final, kept as is)
Output: night/imagegen/final/nook-white-closed.png (then `encode.py nook-white` for the site files)

Four clone patches, all at 2400x1500 px coordinates, each checked at 1:1 / 4x with a coordinate grid:
  1. the step in the near edge at x~760 (the model's leaf-seam remnant on a CLOSED top): the edge
     line is continued from the clean stretch 100 px to the right (edge slope ~0.09 -> dy 9);
  2. the dark slot at the top of the near-left leg (reads as a mortise): the same shadowed oak next to it;
  3. the tan tab sticking out left of that leg top (round 1's bearer ghost, the "pale rectangle"):
     wall from the left, scaled to the mean of the wall just below (a plain clone from outside the
     shadow gave a whiter ghost; a clone from below kept the tab, because the tab extends down);
  4. the last dark notch at the leg shoulder.
What this does NOT do: it does not paint the trestle bearer the render has and the model dropped
(the beam still starts ~40 px right of the leg), and the pale mirrored-wall strip above the beam
is untouched. Both are in REPORT.md "Round 2" as open issues.
"""
import pathlib, shutil, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C
from edit import clone_patch

SRC = C.CANDIDATES / "nook-white-closed-FINAL-r1.png"
DST = C.FINAL / "nook-white-closed.png"
TMP = C.CANDIDATES / "nook-white-closed-r2.png"


def main():
    if not SRC.exists():
        sys.exit(f"missing round-1 final: {SRC}")
    steps = [
        ([728, 428, 84, 58], [100, 9], dict(feather=10)),                      # near-edge step
        ([716, 478, 22, 44], [24, 0], dict(feather=3)),                        # slot in the leg top
        ([640, 464, 38, 16], [-44, 0], dict(feather=3, match_rect=[642, 482, 34, 14])),  # tan tab
        ([716, 475, 20, 12], [26, 0], dict(feather=2)),                        # shoulder notch
    ]
    cur = SRC
    for i, (rect, off, kw) in enumerate(steps):
        out = TMP if i == len(steps) - 1 else TMP.with_name(f"_r2-step{i + 1}.png")
        clone_patch(cur, rect, off, out, **kw)
        cur = out
    for i in range(1, len(steps)):
        TMP.with_name(f"_r2-step{i}.png").unlink(missing_ok=True)
    shutil.copy(TMP, DST)
    print("->", DST)


if __name__ == "__main__":
    main()
