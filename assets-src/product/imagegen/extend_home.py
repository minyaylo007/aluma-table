#!/usr/bin/env python3
"""Canvas extensions for goren-home-daylight (the local halves of the outpaint steps; no Bedrock calls).

    python assets-src/product/imagegen/extend_home.py prep-mobile      # crop + scale the master -> candidates/goren-home-daylight-m-input.png
    python assets-src/product/imagegen/extend_home.py paste-desktop OUTPAINTED.png   # -> final/goren-home-daylight.png (2400x1600)
    python assets-src/product/imagegen/extend_home.py paste-mobile  OUTPAINTED.png   # -> final/goren-home-daylight-m.png (1600x1999)
    python assets-src/product/imagegen/extend_home.py tone-match                     # both finals: match the generated floor strip to the original floor, pad the mobile to 1600x2000

The outpaint model re-encodes the whole picture, so after each call the original pixels are pasted
back over their region (feathered over FEATHER px at the new strips) and only the generated wall /
floor strips are kept. The product therefore stays byte-identical to the approved master.

Mobile crop (at 2400x1500): the table spans x 369..2110 (render silhouette without the floor shadow),
so the crop is x 279..2200 (= table + ~5 % margin each side) at full height, scaled to 1600 px wide
(1600x1250); 4:5 needs 2000 px -> outpaint up 330 / down 420. Never sideways.
"""
import pathlib, sys
import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
CAND, FINAL = HERE / "candidates", HERE / "final"
MASTER = FINAL / "goren-home-daylight-1500.png"
DESKTOP = FINAL / "goren-home-daylight.png"
M_INPUT = CAND / "goren-home-daylight-m-input.png"
MOBILE = FINAL / "goren-home-daylight-m.png"
CROP = (279, 0, 2200, 1500)
M_W = 1600
UP, DOWN = 330, 420
FEATHER = 12


def paste_back(outpainted, original, ox, oy, out):
    """Paste `original` at (ox, oy) over `outpainted`, feathering only the edges that meet new pixels."""
    O = np.asarray(Image.open(outpainted).convert("RGB")).astype(np.float32)
    A = np.asarray(Image.open(original).convert("RGB")).astype(np.float32)
    H, W = O.shape[:2]; h, w = A.shape[:2]
    a = np.ones((h, w), np.float32)
    ramp = np.linspace(0, 1, FEATHER)
    if oy > 0:
        a[:FEATHER] *= ramp[:, None]
    if oy + h < H:
        a[-FEATHER:] *= ramp[::-1][:, None]
    if ox > 0:
        a[:, :FEATHER] *= ramp[None, :]
    if ox + w < W:
        a[:, -FEATHER:] *= ramp[::-1][None, :]
    res = O.copy()
    reg = O[oy:oy + h, ox:ox + w]
    diff = np.abs(reg - A).max(axis=2)
    res[oy:oy + h, ox:ox + w] = reg * (1 - a[..., None]) + A * a[..., None]
    Image.fromarray(res.clip(0, 255).astype(np.uint8)).save(out)
    print(f"{out.name}: {W}x{H}; outpaint had changed the original region by mean {diff.mean():.2f}, max {diff.max():.0f} (now restored)")


def tone_match(path, y_seam, band=24, gap=14, fade_end=0.6, smooth=101, pad_to=None):
    """Shift the generated floor strip (rows >= y_seam) so its first rows match the original's last rows
    per column (smoothed), fading to `fade_end` of the shift at the bottom edge. Scene pixels only.
    `pad_to`: edge-extend the last row to this height (the mobile outpaint came out 1 px short of 4:5)."""
    A = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    H, W = A.shape[:2]
    ref = A[y_seam - gap - band:y_seam - gap].mean(axis=0)          # (W, 3) original
    gen = A[y_seam + gap:y_seam + gap + band].mean(axis=0)          # (W, 3) generated
    delta = ref - gen
    k = np.ones(smooth) / smooth
    delta = np.stack([np.convolve(np.pad(delta[:, c], smooth // 2, mode="edge"), k, mode="valid") for c in range(3)], axis=1)
    y0 = y_seam - FEATHER
    for y in range(y0, H):
        if y < y_seam:
            w = (y - y0) / FEATHER
        else:
            w = 1 - (1 - fade_end) * (y - y_seam) / max(1, H - 1 - y_seam)
        A[y] += delta * w
    if pad_to and pad_to > H:
        A = np.concatenate([A, np.repeat(A[-1:], pad_to - H, axis=0)], axis=0)
    Image.fromarray(A.clip(0, 255).astype(np.uint8)).save(path)
    print(f"{pathlib.Path(path).name}: seam {y_seam} shift mean rgb {delta.mean(axis=0).round(1)} (fade to {fade_end} at the edge); size {A.shape[1]}x{A.shape[0]}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "tone-match":
        tone_match(DESKTOP, 1500)                                    # 100 generated rows at the bottom
        tone_match(MOBILE, UP + 1249, pad_to=2000)                  # 420 generated rows at the bottom, + 1 row to 4:5
    elif cmd == "prep-mobile":
        im = Image.open(MASTER).convert("RGB").crop(CROP)
        h = round(im.height * M_W / im.width)
        im = im.resize((M_W, h), Image.LANCZOS)
        im.save(M_INPUT)
        print(f"{M_INPUT.name}: {im.size}; 4:5 target {M_W}x{M_W * 5 // 4} -> outpaint up {UP} down {DOWN}")
    elif cmd == "paste-desktop":
        paste_back(pathlib.Path(sys.argv[2]), MASTER, 0, 0, DESKTOP)
    elif cmd == "paste-mobile":
        paste_back(pathlib.Path(sys.argv[2]), M_INPUT, 0, UP, MOBILE)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
