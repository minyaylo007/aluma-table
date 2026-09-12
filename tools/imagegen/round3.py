#!/usr/bin/env python3
"""Round 3 (2026-09-08, after JUDGE-2): attach the composited beam to the near trestle, anti-alias
its edges, straighten and darken the mirrored-wall gap fill, patch the leg-top slots. No Bedrock calls.

    python tools/imagegen/round3.py                 # all five finals
    python tools/imagegen/round3.py smoked          # ids containing this
    python tools/imagegen/round3.py --debug DIR     # also write 3x/4x grid crops to DIR

Inputs (per id, all in night/imagegen/candidates/): the round-2 final (copied to
`<id>-FINAL-r2.png` on first run so the step is reproducible), the structure base `<id>-s16-sk2.png`
and the search-replace output `<id>-s16-sk2-replace-s1.png` (evening: whichever of -s1/-s2 the
final's beam registers to). Output: night/imagegen/final/<id>.png.

Geometry (all five finals come from seed 16 at control 0.9, so the layout is the same to a few px):
  1. `dm` = the region search-replace repainted (diff of replaced vs base, closed 21 px) = what
     round 1 filled with the mirrored wall + the beam. Its upper boundary is a 21-px staircase.
  2. beam core = the near-black pixels inside dm; top and bottom edges are fitted as straight
     lines (the render's beam is straight in perspective) over the middle of the span.
  3. the near-left leg's right edge is found by the strongest horizontal gradient per row and
     fitted as a line; the beam polygon is extended left to that line (the beam disappears behind
     the front leg, as it does behind the bearer in the render) and drawn anti-aliased at 4x.
     Old 1-px staircase edge pixels are first replaced by the wall row 5 px outside the fitted line.
  4. the upper boundary of the gap fill is straightened to a fitted line (mirror the oak above /
     the wall below), then the strip between the top's underside and the beam is darkened only
     (never brightened) towards the wall luminance sampled just below the beam, 0.82 at the top
     underside -> 0.95 at the beam (occlusion gradient), texture kept.
  5. small clone patches at the near-left leg top (mortise-like slot, lap-joint facet).
Every step is checked at 3x/4x with a coordinate grid (see --debug) and then at the encoded 1600 px.
"""
import argparse, pathlib, shutil, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C
from edit import clone_patch

IDS = ["apartment-natural-closed", "nook-natural-closed", "evening-natural-closed",
       "apartment-smoked-closed", "nook-white-closed"]

# per-id tuning; everything else is measured from the image
PARAMS = {
    "apartment-natural-closed": dict(dark=70, patches=[([738, 476, 20, 44], [-22, 0], dict(feather=3))]),
    "nook-natural-closed":      dict(dark=70, patches=[([734, 476, 22, 44], [-24, 0], dict(feather=3))]),
    "evening-natural-closed":   dict(dark=85, replaced=None,
                                     patches=[([700, 470, 60, 60], [0, 40], dict(feather=6))]),
    "apartment-smoked-closed":  dict(dark=55, patches=[([738, 476, 20, 44], [-22, 0], dict(feather=3))]),
    "nook-white-closed":        dict(dark=75, patches=[]),
}
WIN = (700, 440, 1502, 640)          # x0, y0, x1, y1: the beam band at 2400x1500 (the far bearer starts at x~1500 in every seed-16 final)
GAP_SHADE = (0.82, 0.95)             # luminance factor vs the wall below the beam: at the top underside -> at the beam


def dm_mask(replaced, base, thresh=28):
    a = np.asarray(Image.open(replaced).convert("RGB")).astype(np.float32)
    b = np.asarray(Image.open(base).convert("RGB")).astype(np.float32)
    diff = np.abs(a - b).max(axis=2)
    m = Image.fromarray((diff > thresh).astype(np.uint8) * 255).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(5))
    m = m.filter(ImageFilter.MaxFilter(21)).filter(ImageFilter.MinFilter(21))
    return np.asarray(m) > 0


def fit_line(xs, ys, passes=3, k=2.0):
    """y = a*x + b, least squares with outlier rejection."""
    xs = np.asarray(xs, float); ys = np.asarray(ys, float)
    keep = np.ones(len(xs), bool)
    for _ in range(passes):
        a, b = np.polyfit(xs[keep], ys[keep], 1)
        r = ys - (a * xs + b)
        s = max(1.0, np.std(r[keep]))
        keep = np.abs(r) < k * s
    return a, b, (float(np.abs(r[keep]).max()), int((~keep).sum()), len(xs))


def measure(F, dm, dark):
    """Beam top/bottom lines, right end, stair (upper dm boundary) line, leg line."""
    x0, y0, x1, y1 = WIN
    lum = F.mean(axis=2)
    win = np.zeros(dm.shape, bool); win[y0:y1, x0:x1] = True
    near = np.asarray(Image.fromarray(dm.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(41))) > 0
    core = (F.max(axis=2) < dark) & near & win       # dm has holes where the model's legs cross the beam
    colsum = core.sum(axis=0)
    runs, cur = [], None                             # column runs (gaps <= 40 px); the beam is the heaviest one
    for x in np.where(colsum > 20)[0]:
        if cur and x - cur[1] <= 40:
            cur[1] = x
        else:
            cur = [int(x), int(x)]; runs.append(cur)
    cx0, cx1 = max(runs, key=lambda r: colsum[r[0]:r[1] + 1].sum())
    xs = np.arange(cx0 + 25, cx1 - 25)
    top = np.array([np.where(core[:, x])[0].min() for x in xs])
    bot = np.array([np.where(core[:, x])[0].max() for x in xs])
    ta, tb, tr = fit_line(xs, top)
    ba, bb, br = fit_line(xs, bot)
    # right end: last column with a full core column
    x_end = int(cx1)
    # stair: upper boundary of dm above the beam
    sx, sy = [], []
    for x in range(cx0 + 10, x_end - 5):
        ys_ = np.where(dm[y0:y1, x])[0]
        if len(ys_):
            sx.append(x); sy.append(ys_.min() + y0)
    sa, sb, sr = fit_line(sx, sy)
    # leg edge: strongest horizontal gradient per row in x 745..795, rows around the beam's left end
    g = np.asarray(Image.fromarray(lum.astype(np.uint8)).filter(ImageFilter.GaussianBlur(1))).astype(np.float32)
    rb = (F[..., 0] - F[..., 2])
    rb = np.asarray(Image.fromarray(np.clip(rb + 128, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1))).astype(np.float32)
    lx, ly = [], []
    yt = int(ta * 770 + tb) + 3; yb = int(ba * 770 + bb) - 2      # only the rows the beam will cover
    for y in range(yt, yb):
        seg = np.abs(np.diff(g[y, 745:796])) + np.abs(np.diff(rb[y, 745:796]))
        lx.append(745 + int(np.argmax(seg)) + 0.5); ly.append(y)
    la, lb, lr = fit_line(ly, lx)          # x = la*y + lb
    return dict(core=core, cx0=int(cx0), x_end=x_end, top=(ta, tb), bot=(ba, bb), stair=(sa, sb), leg=(la, lb),
                resid=dict(top=tr, bot=br, stair=sr, leg=lr),   # (max |r| of kept points, rejected, n)
                stair_pts=(np.array(sx), np.array(sy)), leg_pts=(np.array(lx), np.array(ly)))


def apply(F, dm, M):
    H, W = F.shape[:2]
    out = F.astype(np.float32).copy()
    ta, tb = M["top"]; ba, bb = M["bot"]; sa, sb = M["stair"]; la, lb = M["leg"]
    x_end = M["x_end"]
    xleg_top = la * (ta * 760 + tb) + lb
    xl = int(round(xleg_top))
    # 1. straighten the upper boundary of the fill: mirror oak down / wall up to the fitted line
    sx, sy = M["stair_pts"]
    stair = dict(zip(sx.tolist(), sy.tolist()))
    for x in range(xl, x_end + 1):
        L = int(round(sa * x + sb))
        s = stair.get(x)
        if s is None:
            continue
        if s < L:                              # fill starts too high (pale bump into the top) -> oak from above
            for y in range(s, L):
                out[y, x] = F[2 * s - 1 - y, x]
        elif s > L:                            # oak sags below the line -> wall from below
            for y in range(L, s):
                out[y, x] = F[2 * s - y, x]
    # 2. beam colour per column (median of the core interior), extended left
    colour = np.zeros((W, 3), np.float32); have = np.zeros(W, bool)
    for x in range(M["cx0"], x_end + 1):
        t = int(round(ta * x + tb)) + 3; b = int(round(ba * x + bb)) - 3
        if b > t:
            colour[x] = np.median(F[t:b, x], axis=0); have[x] = True
    first = np.where(have)[0].min() + 6
    colour[:first] = colour[first:first + 12].mean(axis=0)
    for x in range(first, x_end + 1):
        if not have[x]:
            colour[x] = colour[x - 1]
    k = 15
    sm = colour.copy()
    for x in range(xl, x_end + 1):
        sm[x] = colour[max(0, x - k):x + k + 1].mean(axis=0)
    # erase the old staircase edges: rows within 4 px of the fitted lines <- wall 5 px outside
    for x in range(xl, x_end + 1):
        t = int(round(ta * x + tb)); b = int(round(ba * x + bb))
        out[t - 4:t + 5, x] = out[t - 5, x]
        out[b - 4:b + 5, x] = out[b + 5, x]
    # the old beam's left end (x < first core column) is inside the new polygon; nothing to erase there
    # 3. anti-aliased beam polygon at 4x
    S = 4
    yt0 = ta * xl + tb; yb0 = ba * xl + bb
    xlt = la * yt0 + lb; xlb = la * yb0 + lb
    poly = [(xlt, ta * xlt + tb), (x_end + 1, ta * (x_end + 1) + tb), (x_end + 1, ba * (x_end + 1) + bb), (xlb, ba * xlb + bb)]
    bx0, by0 = xl - 4, int(yt0) - 4
    bw, bh = x_end + 8 - bx0, int(yb0) + 8 - by0
    m = Image.new("L", (bw * S, bh * S), 0)
    ImageDraw.Draw(m).polygon([((px - bx0) * S, (py - by0) * S) for px, py in poly], fill=255)
    alpha = np.asarray(m.resize((bw, bh), Image.BOX)).astype(np.float32) / 255.0
    ys, xs = np.mgrid[by0:by0 + bh, bx0:bx0 + bw]
    col = sm[xs]                                  # (bh, bw, 3)
    out[by0:by0 + bh, bx0:bx0 + bw] = out[by0:by0 + bh, bx0:bx0 + bw] * (1 - alpha[..., None]) + col * alpha[..., None]
    # 4. darken the gap strip (between the straightened top underside and the beam top) towards the wall below the beam
    lum = out.mean(axis=2)
    lum_s = np.asarray(Image.fromarray(np.clip(lum, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3))).astype(np.float32)
    target = np.zeros(W, np.float32)
    for x in range(xl - 25, x_end + 26):
        b = int(round(ba * x + bb))
        target[x] = lum[b + 6:b + 18, x].mean()
    tsm = target.copy()
    for x in range(xl, x_end + 1):
        tsm[x] = target[x - 20:x + 21].mean()
    g0, g1 = GAP_SHADE
    for x in range(xl, x_end + 1):
        L = sa * x + sb; T = ta * x + tb
        if T - L < 2:
            continue
        for y in range(int(np.floor(L)) - 1, int(np.ceil(T)) + 1):
            w = np.clip(y - L + 1.0, 0, 1)        # 2-px ramp at the top underside
            if y > T:
                w *= np.clip(T + 1.0 - y, 0, 1)
            if w <= 0:
                continue
            frac = np.clip((y - L) / max(1.0, T - L), 0, 1)
            gain = g0 + (g1 - g0) * frac
            f = np.clip(tsm[x] * gain / max(1.0, lum_s[y, x]), 0.5, 1.0)
            out[y, x] *= 1 - w * (1 - f)
    return np.clip(out, 0, 255).astype(np.uint8)


def debug_crops(img, M, dst, tag):
    from PIL import ImageDraw as D
    for name, box, scale in (("leg", (640, 440, 1000, 600), 3), ("right", (1360, 480, 1620, 620), 3), ("band", (600, 420, 1700, 640), 1)):
        im = Image.fromarray(img).crop(box)
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST if scale > 1 else Image.LANCZOS)
        if scale > 1:
            d = D.Draw(im)
            for gx in range((box[0] // 20 + 1) * 20, box[2], 20):
                X = (gx - box[0]) * scale; d.line([(X, 0), (X, im.height)], fill=(255, 0, 255)); d.text((X + 2, 2), str(gx), fill=(255, 0, 255))
            for gy in range((box[1] // 20 + 1) * 20, box[3], 20):
                Y = (gy - box[1]) * scale; d.line([(0, Y), (im.width, Y)], fill=(0, 200, 255)); d.text((2, Y + 2), str(gy), fill=(0, 200, 255))
        im.save(pathlib.Path(dst) / f"{tag}-{name}.png")


def run(id_, debug=None):
    p = PARAMS[id_]
    src_r2 = C.CANDIDATES / f"{id_}-FINAL-r2.png"
    final = C.FINAL / f"{id_}.png"
    if not src_r2.exists():
        shutil.copy(final, src_r2)
    base = C.CANDIDATES / f"{id_}-s16-sk2.png"
    F = np.asarray(Image.open(src_r2).convert("RGB"))
    reps = [C.CANDIDATES / f"{id_}-s16-sk2-replace-s{i}.png" for i in (1, 2)]
    reps = [r for r in reps if r.exists()]
    best = None
    for r in reps:                                 # pick the replace output whose region holds the final's beam
        dm = dm_mask(r, base)
        core = (F.max(axis=2) < p["dark"]) & dm
        core[:WIN[1]] = False; core[WIN[3]:] = False
        n = int(core.sum())
        if best is None or n > best[0]:
            best = (n, r, dm)
    n, rep, dm = best
    M = measure(F.astype(np.float32), dm, p["dark"])
    ta, tb = M["top"]; ba, bb = M["bot"]; sa, sb = M["stair"]; la, lb = M["leg"]
    print(f"{id_}: replaced={rep.name} core_px={n} beam x {M['cx0']}..{M['x_end']}  "
          f"top y@800={ta*800+tb:.1f} slope={ta:.4f}  bot y@800={ba*800+bb:.1f} slope={ba:.4f}  "
          f"height@800={(ba-ta)*800+bb-tb:.1f}  stair y@800={sa*800+sb:.1f} slope={sa:.4f}  "
          f"leg x@500={la*500+lb:.1f} dx/dy={la:.3f}  resid={M['resid']}")
    out = apply(F, dm, M)
    tmp = C.CANDIDATES / f"{id_}-r3-beam.png"
    Image.fromarray(out).save(tmp)
    cur = tmp
    for i, (rect, off, kw) in enumerate(p["patches"]):
        nxt = C.CANDIDATES / f"{id_}-r3-p{i + 1}.png"
        clone_patch(cur, rect, off, nxt, **kw)
        cur = nxt
    shutil.copy(cur, final)
    for i in range(1, len(p["patches"])):
        (C.CANDIDATES / f"{id_}-r3-p{i}.png").unlink(missing_ok=True)
    keep = C.CANDIDATES / f"{id_}-r3.png"
    keep.unlink(missing_ok=True)
    if p["patches"]:
        tmp.unlink(missing_ok=True)
        (C.CANDIDATES / f"{id_}-r3-p{len(p['patches'])}.png").rename(keep)
    else:
        tmp.rename(keep)
    print("  ->", final)
    if debug:
        debug_crops(np.asarray(Image.open(final).convert("RGB")), M, debug, id_)
        debug_crops(F, M, debug, id_ + "-before")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("filter", nargs="?", default="")
    ap.add_argument("--debug")
    a = ap.parse_args()
    if a.debug:
        pathlib.Path(a.debug).mkdir(parents=True, exist_ok=True)
    for id_ in IDS:
        if a.filter in id_:
            run(id_, a.debug)


if __name__ == "__main__":
    main()
