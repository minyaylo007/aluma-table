#!/usr/bin/env python3
"""Assemble the goren-home-daylight desktop master from the graded candidates. No Bedrock calls.

    python assets-src/product/imagegen/assemble_home.py [--debug DIR]

Inputs (assets-src/product/imagegen/candidates/, all from CALLS.jsonl #1, #4, #7):
  daylight-natural-closed-s16.png              structure base (accepted)
  daylight-natural-closed-s16-replace-s1.png   search-replace of the oak apron -> steel: mask source only
  daylight-natural-closed-s16-inpaint-s1-cup.png  cup inpaint on the base (ellipse mask _mask-cup.png)
Output: assets-src/product/imagegen/final/goren-home-daylight-1500.png (2400x1500, 8:5; the 3:2 master
is made from it by edit.py outpaint --down 100 and pasted back over, see HOME-SCENE-LOG.md).

Steps (the round-3 recipe of tools/imagegen/round3.py applied to this base):
  1. scene = base with the cup region (the inpaint's ellipse mask, dilated + feathered) taken from
     the cup inpaint; every other pixel, product included, stays the structure base's.
  2. gapfix = edit.beam_composite(replaced, base, render, bg=scene): the render's slim beam with the
     gap under the top, painted matte black, the apron remainder filled with wall from below.
  3. round3.measure/apply: fit the beam's edges as straight lines, extend it to the near-left leg
     (it disappears behind the leg like behind the bearer in the render), anti-alias at 4x,
     straighten the fill boundary and darken the gap strip towards the shadowed wall.
  4. clone patches: the near-left leg's side face (dark notch), the near-edge notch at x~1078 and the
     lighter sheen streak on the top at y~410 (both artefacts of the structure model).
"""
import argparse, pathlib, shutil, sys
import numpy as np
from PIL import Image, ImageFilter

HERE = pathlib.Path(__file__).resolve().parent                 # assets-src/product/imagegen
ROOT = HERE.parents[2]                                         # furniture/
sys.path.insert(0, str(ROOT / "tools" / "imagegen"))
from edit import beam_composite, clone_patch                   # noqa: E402
import round3                                                  # noqa: E402

CAND = HERE / "candidates"
FINAL = HERE / "final"
RENDER = ROOT / "renders-master" / "hero-natural-closed.png"
BASE = CAND / "daylight-natural-closed-s16.png"
REPLACED = CAND / "daylight-natural-closed-s16-replace-s1.png"
CUP = CAND / "daylight-natural-closed-s16-inpaint-s1-cup.png"
CUP_MASK = CAND / "_mask-cup.png"
OUT = FINAL / "goren-home-daylight-1500.png"

DARK = 70                     # near-black threshold for the beam core (round3 PARAMS)
GAP_SHADE = (0.70, 0.88)      # gap strip luminance vs the wall below the beam (round3 default 0.82..0.95 left a pale strip)
PATCHES = [                   # (rect x,y,w,h, offset dx,dy, kwargs)  -- all at 2400x1500
    ([736, 478, 24, 48], [0, 50], dict(feather=3)),      # leg side face: dark notch <- same face 50 px lower
    ([1068, 484, 20, 28], [26, 0], dict(feather=3)),     # near-edge notch at x~1078 <- edge band to the right
    ([1095, 402, 75, 22], [0, 28], dict(feather=4)),     # sheen streak on the top <- veneer just below
]


def merge_cup():
    base = np.asarray(Image.open(BASE).convert("RGB")).astype(np.float32)
    cup = np.asarray(Image.open(CUP).convert("RGB")).astype(np.float32)
    m = Image.open(CUP_MASK).convert("L").filter(ImageFilter.MaxFilter(25)).filter(ImageFilter.GaussianBlur(4))
    a = np.asarray(m).astype(np.float32)[..., None] / 255.0
    out = base * (1 - a) + cup * a
    p = CAND / "daylight-natural-closed-s16-scene.png"
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(p)
    changed = float((a[..., 0] > 0.01).mean())
    print(f"1. scene: cup merged over {changed*100:.2f}% of pixels -> {p.name}")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", help="write 3x grid crops of the beam ends to this dir")
    a = ap.parse_args()
    FINAL.mkdir(parents=True, exist_ok=True)
    scene = merge_cup()
    gap = CAND / "daylight-natural-closed-s16-gap.png"
    cov = beam_composite(str(REPLACED), str(BASE), str(RENDER), str(gap), level=0.35, bg=str(scene))
    print(f"2. gapfix: beam core {cov*100:.2f}% of pixels -> {gap.name}")
    F = np.asarray(Image.open(gap).convert("RGB"))
    dm = round3.dm_mask(str(REPLACED), str(BASE))
    round3.GAP_SHADE = GAP_SHADE
    M = round3.measure(F.astype(np.float32), dm, DARK)
    ta, tb = M["top"]; ba, bb = M["bot"]; sa, sb = M["stair"]; la, lb = M["leg"]
    print(f"3. round3: beam x {M['cx0']}..{M['x_end']}  top y@800={ta*800+tb:.1f} slope={ta:.4f}  bot y@800={ba*800+bb:.1f} "
          f"height@800={(ba-ta)*800+bb-tb:.1f}  stair y@800={sa*800+sb:.1f}  leg x@500={la*500+lb:.1f} dx/dy={la:.3f}  resid={M['resid']}")
    r3 = CAND / "daylight-natural-closed-s16-r3.png"
    Image.fromarray(round3.apply(F, dm, M)).save(r3)
    cur = r3
    for i, (rect, off, kw) in enumerate(PATCHES, 1):
        nxt = CAND / f"daylight-natural-closed-s16-p{i}.png"
        clone_patch(str(cur), rect, off, str(nxt), **kw)
        cur = nxt
    shutil.copy(cur, OUT)
    for i in range(1, len(PATCHES)):
        (CAND / f"daylight-natural-closed-s16-p{i}.png").unlink(missing_ok=True)
    (CAND / f"daylight-natural-closed-s16-p{len(PATCHES)}.png").unlink(missing_ok=True)
    print(f"4. patches x{len(PATCHES)} -> {OUT}")
    if a.debug:
        d = pathlib.Path(a.debug); d.mkdir(parents=True, exist_ok=True)
        round3.debug_crops(np.asarray(Image.open(OUT).convert("RGB")), M, d, "home")
        round3.debug_crops(F, M, d, "home-before")


if __name__ == "__main__":
    main()
