#!/usr/bin/env python3
"""PNG renders -> responsive WebP (+ AVIF where the plugin exists).

    python tools/optimise_renders.py                # all masters
    python tools/optimise_renders.py hero-natural   # only masters whose name starts with this
    options: --grain=0.5   film-grain sigma in 8-bit levels (default 0.5, 0 = off; 1.2 showed a dot pattern in WebP on the flat ground)
             --crop        legacy autocrop (off by default, see below)

For every renders-master/*.png writes site/assets/renders/<name>-{800,1200,1600}.webp (and
.avif). The PNG masters are not deployed; the page references only the encoded variants.

Framing: since tools/render3d.js fits the model to the frame deterministically
(Goren.frame), the encoded variants keep the master's full frame. The former autocrop is
kept behind --crop for old masters, but it is a no-op for the current ones: the still and
the live viewer must share the same framing for the picture-to-viewer swap on the page,
and every tone of a view must be pixel-aligned for the tone cross-fade.
"""
import pathlib, sys
import numpy as np
from PIL import Image
try:
    import pillow_avif  # noqa: F401
    AVIF = True
except Exception:
    AVIF = False

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "renders-master"
DST = ROOT / "site" / "assets" / "renders"
WIDTHS = (800, 1200, 1600)
# quality per width: the big variant is what a desktop sees, keep it under ~180 KB for the hero
WEBP_Q = {800: 88, 1200: 90, 1600: 90}
AVIF_Q = {800: 64, 1200: 62, 1600: 60}

args = sys.argv[1:]
opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in args if a.startswith("--"))
prefix = next((a for a in args if not a.startswith("--")), "")
GRAIN = float(opts.get("grain", 0.5))
CROP = "crop" in opts


def autocrop(im: Image.Image, margin: float = 0.06) -> Image.Image:
    """Legacy: trim the flat background to the table's bounding box plus a margin."""
    from PIL import ImageChops
    bg = Image.new("RGB", im.size, im.getpixel((2, 2)))
    diff = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 6 else 0)
    box = diff.getbbox()
    if not box:
        return im
    l, t, r, b = box
    mw, mh = int((r - l) * margin), int((b - t) * margin)
    return im.crop((max(0, l - mw), max(0, t - mh), min(im.width, r + mw), min(im.height, b + mh)))


def grain(im: Image.Image, sigma: float, seed: int) -> Image.Image:
    """A whisper of luminance noise so the flat CG paper and the wood stop reading as vector.
    Deterministic per file name so every tone of a view carries the same grain (cross-fade safe)."""
    if sigma <= 0:
        return im
    a = np.asarray(im).astype(np.float32)
    n = np.random.default_rng(seed).normal(0.0, sigma, a.shape[:2]).astype(np.float32)
    a += n[..., None]
    return Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8))


total = 0
VIEWS = ("hero", "hero2", "front", "end", "top", "detail")               # only the product views; renders-master/ also holds viewer-perf-*.png screenshots
files = sorted(p for p in SRC.glob("*.png") if p.stem.startswith(prefix) and p.stem.split("-")[0] in VIEWS)
if not files:
    sys.exit(f"no masters in {SRC} matching '{prefix}'")
for png in files:
    im = Image.open(png).convert("RGB")
    if CROP:
        im = autocrop(im)
    view = png.stem.split("-")[0]                       # same grain seed for every tone/state of a view
    seed = sum(ord(c) for c in view)
    DST.mkdir(parents=True, exist_ok=True)
    sizes = []
    for w in WIDTHS:
        if w > im.width:
            continue
        h = round(im.height * w / im.width)
        r = grain(im.resize((w, h), Image.LANCZOS), GRAIN, seed + w)
        out = DST / f"{png.stem}-{w}.webp"
        r.save(out, "WEBP", quality=WEBP_Q[w], method=6)
        total += out.stat().st_size
        sizes.append(f"{w}: {out.stat().st_size // 1024} KB webp")
        if AVIF:
            outa = DST / f"{png.stem}-{w}.avif"
            r.save(outa, "AVIF", quality=AVIF_Q[w], speed=4)
            total += outa.stat().st_size
            sizes[-1] += f" / {outa.stat().st_size // 1024} KB avif"
    print(f"{png.name}: {im.width}x{im.height} -> " + ", ".join(sizes))
print(f"encoded variants total: {total/1024:.0f} KB  (avif={'yes' if AVIF else 'no'}, grain={GRAIN}, crop={'on' if CROP else 'off'})")
