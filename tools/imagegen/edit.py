#!/usr/bin/env python3
"""Edit helpers on top of Bedrock Stability image services, with the same call log / budget cap.

    python tools/imagegen/edit.py recolor  IMG --select "the table legs" --prompt "light natural oak wood" [--seed N] [--grow 3]
    python tools/imagegen/edit.py erase    IMG --rect x,y,w,h            # ellipse mask in a rectangle (image px)
    python tools/imagegen/edit.py erase    IMG --mask MASK.png           # white = erase
    python tools/imagegen/edit.py replace  IMG --search "the bowl" --prompt "..." [--seed N]
    python tools/imagegen/edit.py inpaint  IMG --mask MASK.png --prompt "..." [--seed N]
    python tools/imagegen/edit.py upscale  IMG [--creativity 0.3] [--prompt "..."]    # conservative 4x, input <= 1 MP
    python tools/imagegen/edit.py upscale-fast IMG                                     # fast 4x, input <= 1 MP
    python tools/imagegen/edit.py outpaint IMG --up 400 --down 500 [--prompt "..."] [--seed N] [--outpaint-creativity 0.5] [--out OUT.png]  # extend the canvas vertically only (never across the table)
    python tools/imagegen/edit.py mask     IMG --rect x,y,w,h [--square] --out MASK.png   # no Bedrock call
    python tools/imagegen/edit.py mask     IMG --poly x1,y1,... --exclude-render R.png --out MASK.png  # room-only mask
    python tools/imagegen/edit.py beam-mask IMG --render RENDER.png [--dilate 6] --out MASK.png  # no call: the render's black beam
    python tools/imagegen/edit.py beam-fix IMG --render RENDER.png [--seed N] [--out OUT.png]  # 1 call: replace beam -> steel, then local composite (gap + matte black)
    python tools/imagegen/edit.py gapfix   REPLACED --ref BASE --render RENDER.png --out OUT.png  # no call: the composite step alone
    python tools/imagegen/edit.py grade    IMG --warm 0.12 --gamma 1.25 --vignette 0.35 [--glow x,y,r] --out OUT.png  # no call: evening grade
    python tools/imagegen/edit.py clone    IMG --rect x,y,w,h --from dx,dy [--feather 6] [--match-rect x,y,w,h] --out OUT.png  # no call: patch a small blemish from a neighbour (match: scale the patch to that region's mean colour)
    python tools/imagegen/edit.py darken   IMG --ref ORIGINAL --out OUT.png             # no call: matte-black the recolored region
    python tools/imagegen/edit.py darken   IMG --render RENDER.png [--dilate 2] --out OUT.png  # no call: matte-black the render beam region

Outputs go next to the input as <stem>-<op>[-s<seed>].png (in night/imagegen/candidates/ when the
input lives there). Field names follow Stability's v2beta API, which the Bedrock wrappers mirror.
"""
import argparse, pathlib, sys
from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C

MAX_UPSCALE_INPUT_PX = 1_048_576  # Stability upscalers accept up to 1 MP input


def out_path(src, op, seed=None):
    p = pathlib.Path(src)
    suf = f"-{op}" + (f"-s{seed}" if seed is not None else "")
    out = p.with_name(p.stem + suf + ".png")
    i = 2
    while out.exists():
        out = p.with_name(f"{p.stem}{suf}-{i}.png")
        i += 1
    return out


def rect_mask(size, rect, ellipse=True):
    m = Image.new("L", size, 0)
    x, y, w, h = rect
    d = ImageDraw.Draw(m)
    (d.ellipse if ellipse else d.rectangle)([x, y, x + w, y + h], fill=255)
    return m


def load_mask(a, size):
    m = None
    if a.mask:
        m = Image.open(a.mask).convert("L").resize(size)
    elif a.rect:
        m = rect_mask(size, [int(v) for v in a.rect.split(",")], ellipse=not a.square)
    elif getattr(a, "poly", None):
        pts = [int(v) for v in a.poly.split(",")]
        m = Image.new("L", size, 0)
        ImageDraw.Draw(m).polygon(list(zip(pts[::2], pts[1::2])), fill=255)
    if m is not None and getattr(a, "exclude_render", None):
        m = exclude_table(m, a.exclude_render, a.exclude_dilate)
    return m


def exclude_table(mask, render, dilate=14):
    """Zero the mask wherever the render shows the table (dilated), so an inpaint touches only the room."""
    import numpy as np
    from PIL import ImageChops, ImageFilter
    r = Image.open(render).convert("RGB").resize(mask.size, Image.LANCZOS)
    bg = Image.new("RGB", r.size, r.getpixel((2, 2)))
    sil = ImageChops.difference(r, bg).convert("L").point(lambda v: 255 if v > 6 else 0)
    sil = sil.filter(ImageFilter.MaxFilter(dilate * 2 + 1))
    out = np.asarray(mask).copy()
    out[np.asarray(sil) > 0] = 0
    return Image.fromarray(out)


def fit_for_upscale(im):
    px = im.width * im.height
    if px <= MAX_UPSCALE_INPUT_PX:
        return im
    k = (MAX_UPSCALE_INPUT_PX / px) ** 0.5
    w, h = int(im.width * k) // 8 * 8, int(im.height * k) // 8 * 8
    return im.resize((w, h), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("op", choices=["recolor", "erase", "replace", "inpaint", "upscale", "upscale-fast", "outpaint", "mask", "beam-mask", "darken", "beam-fix", "gapfix", "grade", "clone"])
    ap.add_argument("image")
    ap.add_argument("--select", help="recolor: what to find")
    ap.add_argument("--search", help="replace: what to find")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--negative", default="")
    ap.add_argument("--mask")
    ap.add_argument("--rect", help="x,y,w,h in image pixels -> ellipse mask (or --square)")
    ap.add_argument("--square", action="store_true")
    ap.add_argument("--grow", type=int, default=None, help="grow_mask px (recolor/erase/replace/inpaint)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--creativity", type=float, default=0.3, help="conservative upscale 0.2..0.5")
    ap.add_argument("--up", type=int, default=0, help="outpaint: pixels to add above (0..2000)")
    ap.add_argument("--down", type=int, default=0, help="outpaint: pixels to add below (0..2000)")
    ap.add_argument("--outpaint-creativity", type=float, default=None, help="outpaint: 0..1 (API default 0.5); omitted unless given")
    ap.add_argument("--out")
    ap.add_argument("--render", help="beam-mask: the render the image was generated from")
    ap.add_argument("--dilate", type=int, default=6)
    ap.add_argument("--ref", help="darken/gapfix: the image before replace/recolor")
    ap.add_argument("--bg", help="gapfix: take pixels from this image (base after scene inpainting) instead of --ref")
    ap.add_argument("--exclude-render", help="mask: subtract the render's table silhouette (dilated --exclude-dilate px) from the mask")
    ap.add_argument("--exclude-dilate", type=int, default=14)
    ap.add_argument("--poly", help="mask: polygon x1,y1,x2,y2,... in image pixels (instead of --rect)")
    ap.add_argument("--level", type=float, default=0.22)
    ap.add_argument("--glow", help="grade: x,y,r of a lamp glow to add (image px)")
    ap.add_argument("--from", dest="src", help="clone: dx,dy offset of the source patch")
    ap.add_argument("--feather", type=int, default=6, help="clone: feathered border in px (use 2-4 for patches under 20 px)")
    ap.add_argument("--match-rect", help="clone: x,y,w,h of a region whose mean colour the source patch is scaled to (for a patch taken from outside a shadow)")
    ap.add_argument("--warm", type=float, default=0.12, help="grade: warm shift 0..0.3")
    ap.add_argument("--gamma", type=float, default=1.25, help="grade: >1 darkens")
    ap.add_argument("--vignette", type=float, default=0.35, help="grade: edge darkening 0..1")
    ap.add_argument("--format", choices=["png", "jpeg"], default=None,
                    help="output_format (default png; upscalers default to jpeg: a 4x PNG exceeds Bedrock's 16 MB response cap)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    im = Image.open(a.image).convert("RGB")
    if a.op == "mask":
        m = load_mask(a, im.size)
        out = a.out or out_path(a.image, "mask")
        m.save(out)
        print("mask ->", out)
        return
    if a.op == "beam-mask":
        m = beam_mask_from_render(a.render, im.size, a.dilate)
        out = a.out or out_path(a.image, "beammask")
        m.save(out)
        print("beam mask ->", out)
        return
    if a.op == "darken":
        out = a.out or out_path(a.image, "beam")
        if a.mask or (a.render and not a.ref):
            m = Image.open(a.mask).convert("L") if a.mask else beam_mask_from_render(a.render, im.size, a.dilate)
            cov = darken_with_mask(a.image, m, out, level=a.level)
        else:
            cov = darken_from_diff(a.image, a.ref, out, level=a.level, render=a.render)
        print(f"darkened {cov*100:.2f}% of pixels -> {out}")
        return

    if a.op == "grade":
        out = a.out or out_path(a.image, "grade")
        glow = [float(v) for v in a.glow.split(",")] if a.glow else None
        grade_evening(a.image, out, warm=a.warm, gamma=a.gamma, vignette=a.vignette, glow=glow)
        print("graded ->", out)
        return
    if a.op == "clone":
        if not (a.rect and a.src):
            sys.exit("--rect and --from required")
        out = a.out or out_path(a.image, "clone")
        mr = [int(v) for v in a.match_rect.split(",")] if a.match_rect else None
        clone_patch(a.image, [int(v) for v in a.rect.split(",")], [int(v) for v in a.src.split(",")], out, feather=a.feather, match_rect=mr)
        print("cloned ->", out)
        return

    if a.op == "gapfix":
        if not (a.ref and a.render):
            sys.exit("--ref BASE and --render RENDER required")
        out = a.out or out_path(a.image, "beam")
        cov = beam_composite(a.image, a.ref, a.render, out, level=a.level if a.level != 0.22 else 0.35, bg=a.bg)
        print(f"gapfix: beam {cov*100:.2f}% of pixels -> {out}")
        return

    if a.op == "beam-fix":
        # the production beam fix: search-and-replace the (oak-painted) beam with a steel beam (1 call),
        # then push the repainted region to matte black locally through its own diff mask (0 calls)
        tmp = out_path(a.image, "replace", a.seed)
        body = {"output_format": "png", "image": C.img_to_b64(im), "seed": a.seed,
                "search_prompt": "the horizontal wooden beam between the two trestle legs under the table top",
                "prompt": a.prompt or "a slim matte black powder-coated steel beam, pitch black",
                "negative_prompt": a.negative or "wood, oak, grey, silver, shiny"}
        C.invoke("replace", body, tmp, note=f"beam-fix step 1 of {pathlib.Path(a.image).name}", dry_run=a.dry_run)
        if a.dry_run:
            return
        out = pathlib.Path(a.out) if a.out else out_path(a.image, "beam")
        lvl = a.level if a.level != 0.22 else 0.35
        if a.render:
            cov = beam_composite(tmp, a.image, a.render, out, level=lvl)
        else:
            cov = darken_from_diff(tmp, a.image, out, level=lvl)
        print(f"beam-fix: beam {cov*100:.2f}% -> {out}")
        return

    fmt = a.format or ("jpeg" if a.op in ("upscale", "upscale-fast") else "png")
    body = {"output_format": fmt}
    if a.op == "recolor":
        if not a.select:
            sys.exit("--select required")
        body.update(image=C.img_to_b64(im), prompt=a.prompt, select_prompt=a.select, seed=a.seed)
        if a.negative:
            body["negative_prompt"] = a.negative
        if a.grow is not None:
            body["grow_mask"] = a.grow
        key = "recolor"
    elif a.op == "erase":
        m = load_mask(a, im.size)
        if m is None:
            sys.exit("--mask or --rect required")
        body.update(image=C.img_to_b64(im), mask=C.img_to_b64(m), seed=a.seed)
        if a.grow is not None:
            body["grow_mask"] = a.grow
        key = "erase"
    elif a.op == "replace":
        if not a.search:
            sys.exit("--search required")
        body.update(image=C.img_to_b64(im), prompt=a.prompt, search_prompt=a.search, seed=a.seed)
        if a.negative:
            body["negative_prompt"] = a.negative
        if a.grow is not None:
            body["grow_mask"] = a.grow
        key = "replace"
    elif a.op == "inpaint":
        m = load_mask(a, im.size)
        if m is None:
            sys.exit("--mask or --rect required")
        body.update(image=C.img_to_b64(im), mask=C.img_to_b64(m), prompt=a.prompt, seed=a.seed)
        if a.negative:
            body["negative_prompt"] = a.negative
        if a.grow is not None:
            body["grow_mask"] = a.grow
        key = "inpaint"
    elif a.op == "upscale":
        small = fit_for_upscale(im)
        body.update(image=C.img_to_b64(small), prompt=a.prompt or "the same photograph, sharper",
                    seed=a.seed, creativity=a.creativity)
        if a.negative:
            body["negative_prompt"] = a.negative
        key = "upscale"
    elif a.op == "outpaint":
        # vertical only by design: the mobile 4:5 is derived from the approved desktop image by adding
        # wall above and floor below; extending sideways would regenerate across the table's ends
        if a.up <= 0 and a.down <= 0:
            sys.exit("--up and/or --down (> 0) required")
        body.update(image=C.img_to_b64(im), seed=a.seed)
        if a.up > 0:
            body["up"] = a.up
        if a.down > 0:
            body["down"] = a.down
        if a.prompt:
            body["prompt"] = a.prompt
        if a.outpaint_creativity is not None:
            body["creativity"] = a.outpaint_creativity
        key = "outpaint"
    else:  # upscale-fast
        small = fit_for_upscale(im)
        body.update(image=C.img_to_b64(small))
        key = "upscale-fast"

    out = pathlib.Path(a.out) if a.out else out_path(a.image, a.op, a.seed if a.op not in ("upscale-fast",) else None)
    if fmt == "jpeg":
        out = out.with_suffix(".jpg")
    note = f"{a.op} of {pathlib.Path(a.image).name}" + (f" rect={a.rect}" if a.rect else "") + (f" select={a.select}" if a.select else "") + (f" up={a.up} down={a.down} in={im.width}x{im.height}" if a.op == "outpaint" else "")
    C.invoke(key, body, out, note=note, dry_run=a.dry_run)



# ---- local (no Bedrock) helpers -------------------------------------------------------------
def beam_mask_from_render(render, size, dilate=6):
    """The beam is the only near-black thing in our renders; control-structure keeps geometry, so
    its pixels are an aligned mask for inpainting the beam in the generated image."""
    import numpy as np
    from PIL import ImageFilter
    r = np.asarray(Image.open(render).convert("RGB").resize(size, Image.LANCZOS))
    m = (r.max(axis=2) < 45).astype(np.uint8) * 255
    im = Image.fromarray(m).filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MaxFilter(7))  # drop dark specks/edges
    if dilate:
        im = im.filter(ImageFilter.MaxFilter(dilate * 2 + 1))
    return im


def register(core, target, radius=64, step=4):
    """Best (dx, dy) translation of boolean mask `core` onto `target`, by overlap fraction of core."""
    import numpy as np
    c = core[::step, ::step]
    t = target[::step, ::step]
    best = (0, 0, 0.0)
    n = max(1, c.sum())
    r = radius // step
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            s = np.roll(np.roll(c, dy, axis=0), dx, axis=1)
            ov = (s & t).sum() / n
            if ov > best[2]:
                best = (dx * step, dy * step, float(ov))
    return best


def darken_with_mask(image, mask, out, level=0.22, feather=1.0):
    """Remap the masked region of `image` to matte black keeping its shading (no Bedrock call).
    `mask` is an L image (white = beam), e.g. from beam_mask_from_render()."""
    import numpy as np
    from PIL import ImageFilter
    a = np.asarray(Image.open(image).convert("RGB")).astype(np.float32)
    m = mask if isinstance(mask, Image.Image) else Image.open(mask).convert("L")
    if feather:
        m = m.filter(ImageFilter.GaussianBlur(feather))
    alpha = (np.asarray(m).astype(np.float32) / 255.0)[..., None]
    lum = a.mean(axis=2, keepdims=True)
    black = np.clip(lum * level + 6.0, 0, 255)
    black = np.repeat(black, 3, axis=2) * np.array([0.98, 0.98, 1.0])
    res = a * (1 - alpha) + black * alpha
    Image.fromarray(res.clip(0, 255).astype(np.uint8)).save(out)
    return float(alpha.mean())


def darken_from_diff(recolored, original, out, level=0.22, thresh=28, smooth=10, close=21, render=None, render_dilate=10):
    """Where `recolored` differs from `original` (= what search-recolor repainted), remap the
    region to matte black keeping its shading. Used because the recolor model paints the steel
    beam grey instead of black; this makes the mask *exactly* the region the model selected."""
    import numpy as np
    from PIL import ImageFilter
    a = np.asarray(Image.open(recolored).convert("RGB")).astype(np.float32)
    b = np.asarray(Image.open(original).convert("RGB")).astype(np.float32)
    diff = np.abs(a - b).max(axis=2)
    m = Image.fromarray((diff > thresh).astype(np.uint8) * 255)
    m = m.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(5))
    if close:  # fill small holes / stripes the replace model left inside the band
        m = m.filter(ImageFilter.MaxFilter(close)).filter(ImageFilter.MinFilter(close))
    if render:
        # the render's beam geometry is exact and aligned to a few px at control 0.9: use it as the
        # core of the mask (fills holes/notches the replace model left), let the diff add the model's
        # own edges, and never paint outside the dilated envelope (kills stray brackets)
        # ...but control-structure shifts the whole table by up to ~60 px between seeds, so first
        # register the render mask to the diff mask with a small translation search.
        core = np.asarray(beam_mask_from_render(render, m.size, 3)) > 0
        dm = np.asarray(m) > 0
        dx, dy, score = register(core, dm)
        if score >= 0.6:
            core = np.roll(np.roll(core, dy, axis=0), dx, axis=1)
            env = np.roll(np.roll(np.asarray(beam_mask_from_render(render, m.size, render_dilate)) > 0, dy, axis=0), dx, axis=1)
            mm = np.minimum(np.maximum(dm, core), env)
            m = Image.fromarray(mm.astype(np.uint8) * 255)
        print(f"  render mask registration dx={dx} dy={dy} overlap={score:.2f} ({'used' if score >= 0.6 else 'ignored'})")
    m = m.filter(ImageFilter.GaussianBlur(1.2))
    alpha = (np.asarray(m).astype(np.float32) / 255.0)[..., None]
    lum = a.mean(axis=2)
    if smooth:
        # the replace model leaves ghost stripes in the repainted band; a heavy blur keeps only the
        # large-scale shading (near end darker / far end lighter) so the steel reads as one surface
        lum = np.asarray(Image.fromarray(lum.astype(np.uint8)).filter(ImageFilter.GaussianBlur(smooth))).astype(np.float32)
    lum = lum[..., None]
    black = np.clip(lum * level + 6.0, 0, 255)          # matte black with the original shading
    black = np.repeat(black, 3, axis=2) * np.array([0.98, 0.98, 1.0])
    res = a * (1 - alpha) + black * alpha
    Image.fromarray(res.clip(0, 255).astype(np.uint8)).save(out)
    return float(alpha.mean())


def clone_patch(image, rect, offset, out, feather=6, match_rect=None):
    """Copy the patch at rect+offset over rect with feathered edges (no Bedrock call). For the
    small blemishes the models leave on the top edge (a notch at the leaf seam, a dot).
    The feathered core is rect inset by `feather`, so a patch under ~3*feather px barely applies:
    use feather 2-4 for small rects. `match_rect` scales the source patch so its mean colour equals
    that region's mean (take wall from outside a shadow, match it to the wall next to the blemish);
    a mismatched source reads as a pale/dark ghost rectangle, which is exactly what round 1 left."""
    import numpy as np
    from PIL import ImageFilter
    im = Image.open(image).convert("RGB")
    A = np.asarray(im).astype(np.float32)
    x, y, w, h = rect
    dx, dy = offset
    src = A[y + dy:y + dy + h, x + dx:x + dx + w].copy()
    if match_rect:
        rx, ry, rw, rh = match_rect
        ref = A[ry:ry + rh, rx:rx + rw].reshape(-1, 3).mean(axis=0)
        src = src * (ref / src.reshape(-1, 3).mean(axis=0))
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rectangle([x + feather, y + feather, x + w - feather, y + h - feather], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(feather / 2))
    patched = A.copy()
    patched[y:y + h, x:x + w] = src
    a = np.asarray(m).astype(np.float32)[..., None] / 255.0
    res = A * (1 - a) + patched * a
    Image.fromarray(res.clip(0, 255).astype(np.uint8)).save(out)


def grade_evening(image, out, warm=0.12, gamma=1.25, vignette=0.35, glow=None):
    """Warm, dimmer, vignetted version of a daylight candidate (no Bedrock call). The structure
    model gives every scene the same flat daylight; this is the cheapest honest way to an evening mood."""
    import numpy as np
    a = np.asarray(Image.open(image).convert("RGB")).astype(np.float32) / 255.0
    a = np.power(a, gamma)
    a *= np.array([1 + warm, 1 + warm * 0.35, 1 - warm * 0.9])
    H, W = a.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    cx, cy = W * 0.52, H * 0.42                     # lamp / table centre stays bright
    r = np.sqrt(((xx - cx) / (W * 0.62)) ** 2 + ((yy - cy) / (H * 0.75)) ** 2)
    v = 1 - vignette * np.clip(r - 0.35, 0, 1.2) / 1.2
    a *= v[..., None]
    if glow:                                          # a warm pool of light under the lamp
        gx, gy, gr = glow
        g = np.exp(-(((xx - gx) / gr) ** 2 + ((yy - gy) / (gr * 0.6)) ** 2))
        a += g[..., None] * np.array([0.22, 0.16, 0.06])
    Image.fromarray((a.clip(0, 1) * 255 + 0.5).astype(np.uint8)).save(out)


def beam_composite(replaced, base, render, out, level=0.35, thresh=28, gap_extra=3, dilate=1, bg=None, compress=0.35):
    """Rebuild the slim beam WITH the gap under the top (no Bedrock call).

    control-structure merges our beam and the gap above it into one oak apron flush under the top;
    search-replace then repaints that whole apron as steel. Painting the apron black gives a beam
    that is ~1.6x too tall and flush with the top. This step instead:
      1. takes the apron region = what search-replace changed (diff of `replaced` vs `base`);
      2. registers the render's beam mask to it horizontally, then aligns the beam's BOTTOM edge
         with the apron's bottom edge (the apron = gap + beam, so the bottoms coincide);
      3. paints only the beam core matte black (shading from the replaced image, blurred);
      4. fills the rest of the apron (the gap) with the wall mirrored from just below the beam.
    Result: the beam has the render's height and sits below the top like the real part.
    `bg`: optional image to take the pixels from (e.g. the base after scene inpainting outside the
    table); the mask geometry still comes from diff(replaced, base). `compress` flattens the steel
    shading towards its median so the beam reads as one matte surface."""
    import numpy as np
    from PIL import ImageFilter
    a = np.asarray(Image.open(replaced).convert("RGB")).astype(np.float32)
    b = np.asarray(Image.open(base).convert("RGB")).astype(np.float32)
    src_img = np.asarray(Image.open(bg).convert("RGB")).astype(np.float32) if bg else b
    H, W = a.shape[:2]
    diff = np.abs(a - b).max(axis=2)
    m = Image.fromarray((diff > thresh).astype(np.uint8) * 255).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(5))
    m = m.filter(ImageFilter.MaxFilter(21)).filter(ImageFilter.MinFilter(21))
    dm = np.asarray(m) > 0
    core0 = np.asarray(beam_mask_from_render(render, (W, H), 0)) > 0
    dx, dy, score = register(core0, dm)
    core = np.roll(np.roll(core0, dy, axis=0), dx, axis=1)
    cols = np.where(core.any(axis=0) & dm.any(axis=0))[0]
    if score < 0.5 or len(cols) < 50:
        raise SystemExit(f"beam_composite: render beam does not register to the repainted region (overlap {score:.2f})")
    cb = np.array([np.where(core[:, x])[0].max() for x in cols])
    db = np.array([np.where(dm[:, x])[0].max() for x in cols])
    dy2 = max(-6, min(40, int(np.median(db - cb))))
    core = np.roll(core, dy2, axis=0)
    if dilate:
        core = np.asarray(Image.fromarray(core.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(dilate * 2 + 1))) > 0
    print(f"  register dx={dx} dy={dy} overlap={score:.2f}; bottom-align dy2={dy2}")
    lum = np.asarray(Image.fromarray(a.mean(axis=2).astype(np.uint8)).filter(ImageFilter.GaussianBlur(10))).astype(np.float32)
    med = float(np.median(lum[core])) if core.any() else 60.0
    lum = med + (lum - med) * compress
    black = np.clip(lum * level + 6.0, 0, 255)[..., None] * np.array([0.98, 0.98, 1.0])
    b = src_img
    res = b.copy()
    beam_top = np.full(W, -1); beam_bot = np.full(W, -1); fill_bot = np.full(W, -1)
    for x in np.where(core.any(axis=0))[0]:
        r = np.where(core[:, x])[0]; beam_top[x], beam_bot[x] = r.min(), r.max()
    for x in np.where(dm.any(axis=0))[0]:
        fill_bot[x] = np.where(dm[:, x])[0].max()
    ys, xs = np.where(dm & ~core)
    src = np.empty_like(ys)
    for i, (y, x) in enumerate(zip(ys, xs)):
        bb = max(beam_bot[x], fill_bot[x])
        if beam_top[x] < 0:
            src[i] = 2 * fill_bot[x] - y + gap_extra
        elif y < beam_top[x]:
            src[i] = bb + gap_extra + (beam_top[x] - y)
        else:
            src[i] = bb + gap_extra + (y - beam_bot[x])
    src = np.clip(src, 0, H - 1)
    res[ys, xs] = b[src, xs]
    res[core] = black[core]
    al = np.asarray(Image.fromarray((dm | core).astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(0.8))).astype(np.float32)[..., None] / 255.0
    Image.fromarray((b * (1 - al) + res * al).clip(0, 255).astype(np.uint8)).save(out)
    return float(core.mean())


if __name__ == "__main__":
    main()
