#!/usr/bin/env python3
"""Bake the GOREN material maps from the CC0 Poly Haven scans in assets-src/.

    python tools/bake_textures.py            # everything
    python tools/bake_textures.py --hdr-only # just the small studio HDRI

One physical wood for all three tones. Smoked oak is fumed natural oak and whitewashed oak
is natural oak under a white-pigmented oil, so the three tones share the SAME grain
(normal / roughness / AO) and differ only in the albedo grade. That is also what makes the
tone cross-fade on the page look like a finish change and not a texture swap.

Source: oak_veneer_01_{Diffuse,nor_gl,Rough,AO}_2k.jpg (CC0, Poly Haven), grain runs along V.

Outputs
  renders-master/textures/<tone>-albedo-2048.jpg           render-harness masters (gitignored)
  renders-master/textures/endgrain-<tone>-1024.jpg         end-grain albedo (rail ends, leg ends), see endgrain()
  renders-master/textures/oak-normal-2048.jpg, oak-rough-2048.jpg
  site/assets/textures/<tone>-albedo-{1024,512}.jpg        viewer (deployed)
  site/assets/textures/endgrain-<tone>-512.jpg
  site/assets/textures/oak-normal-{1024,512}.jpg
  site/assets/textures/oak-rough-{1024,512}.jpg            R = ambient occlusion, G = roughness, B = 0
  site/assets/textures/studio-256.hdr                      brown_photostudio_02 down-sampled, RLE RGBE

The packed rough map follows three.js' channel convention (aoMap reads .r, roughnessMap .g,
metalnessMap .b) so the viewer downloads one file for the three grey maps.
"""
import io, pathlib, re, sys
import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "assets-src"
MASTER = ROOT / "renders-master" / "textures"
SITE = ROOT / "site" / "assets" / "textures"
BASE = "oak_veneer_01"

# albedo grades, applied in sRGB float space (0..1)
def grade_natural(a):
    # oiled natural oak: scan is a touch orange; pull 8% saturation, keep the honey
    lum = a @ np.array([0.299, 0.587, 0.114])
    a = a * 0.86 + lum[..., None] * 0.14
    return a * np.array([0.99, 0.985, 0.98])

def grade_smoked(a):
    # fumed (ammonia-smoked) oak: the tannins go dark grey-brown, LOWER chroma than natural oak —
    # not redder. Round 1's gamma 1.30 x (0.68, 0.60, 0.54) came out as walnut/teak (mean (95,61,34),
    # spread/mean 0.96 vs 0.51 for natural). This grade: 55 % towards luminance, gamma 1.12,
    # a cool-brown multiplier -> mean ~(86,72,58), spread/mean ~0.39 (below natural's 0.51).
    lum = a @ np.array([0.299, 0.587, 0.114])
    a = a * 0.45 + lum[..., None] * 0.55
    a = np.power(np.clip(a, 0, 1), 1.12)
    return a * np.array([0.64, 0.60, 0.565])

def grade_white(a):
    # whitewash: white pigment sits in the pores; lift, desaturate, grain still visible
    lum = a @ np.array([0.299, 0.587, 0.114])
    a = a * 0.62 + lum[..., None] * 0.38
    a = a * (1 - 0.48) + np.array([0.955, 0.94, 0.915]) * 0.48
    return a

GRADES = {"natural": grade_natural, "smoked": grade_smoked, "white": grade_white}


def load(name):
    return Image.open(SRC / f"{BASE}_{name}_2k.jpg")


def endgrain(face: Image.Image, size: int = 1024, seed: int = 7, tone: str = "natural") -> Image.Image:
    """End-grain albedo for the cut ends of the solid parts (rail ends, leg ends).

    Oak end grain is ring-porous: a dark row of earlywood pores at every growth ring, lighter
    latewood between, ray flecks radiating from the pith. Built procedurally from the tone's own
    colour (the graded face's mean, 26 % darker — end grain drinks the oil and reads darker than
    the face; the whitewash keeps its warmth and only 12 % darker, the pigment sits in the open
    pores): rings are arcs about a pith ~9 cm below the sampled window (a flat-sawn head, so the
    arcs bulge upward with a visible curve across a 60-75 mm face), 4-6.5 mm apart with a slow
    random drift and a gentle waviness, plus fine and broad rays and noise. The tile covers 30 cm
    (TILE_END in goren3d.js) and is NOT periodic: the model samples each end face from a window
    around (0.5, 0.45-0.55) inside the tile (part-local UVs), never across its border.

    Round 2 had the rings starting at r = 1.0 tile from the pith, i.e. only the top 40 % of the
    tile; the part-local windows sat in the ringless fan below, so no ring ever reached a render."""
    base = np.asarray(face).astype(np.float32).reshape(-1, 3).mean(0) / 255.0
    lum = float(base @ np.array([0.299, 0.587, 0.114]))
    if tone == "white":
        base = (base * 0.94 + lum * 0.06) * 0.88
        pore_depth, late_lift = 0.30, 0.08
    else:
        base = (base * 0.88 + lum * 0.12) * 0.74
        pore_depth, late_lift = 0.50, 0.14
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / size          # tile units (1 = 30 cm); row 0 = v 1 (flipY)
    px, py = 0.5, 0.80                                                     # pith 9 cm below the window centre (yy 0.5): 8 mm sagitta over 75 mm
    ang = np.arctan2(xx - px, yy - py)
    r = np.hypot(xx - px, yy - py) * (1 + 0.003 * np.sin(ang * 17 + 1.0) + 0.0015 * np.sin(ang * 53))   # slightly wavy rings (more than this read as corrugation)
    # ring spacing 4-6.5 mm with a drift along r (random walk over the rings), rings from the pith outward
    n_rings = 120
    spacing = 0.0175 * (1 + 0.25 * np.cumsum(rng.normal(0, 0.35, n_rings)).clip(-1, 1))
    spacing = np.clip(spacing, 0.0133, 0.0217)
    edges = np.concatenate([[0.0], np.cumsum(spacing)])
    idx = np.clip(np.searchsorted(edges, r), 1, n_rings)                    # which ring
    frac = (r - edges[idx - 1]) / (edges[idx] - edges[idx - 1])            # 0..1 across the ring
    # earlywood pore row: dark, ~30 % of the ring, soft-edged; latewood: lightens towards the next ring
    pore = np.exp(-((frac - 0.16) / 0.17) ** 2)
    late = late_lift * np.clip((frac - 0.32) / 0.68, 0, 1)
    # dotted look inside the pore row: the vessels themselves
    dots = 0.5 + 0.5 * np.cos(ang * 2600 + rng.uniform(0, 6.28)) * np.cos(r * 5400)
    pore = pore * (0.75 + 0.35 * dots)
    # rays: fine light streaks radiating from the pith, some wider (oak's broad rays, the "flecks")
    ray = 0.5 + 0.5 * np.cos(ang * 520 + 3 * np.sin(ang * 137))
    ray = np.power(ray, 6) * (0.6 + 0.4 * np.cos(ang * 41))
    broad = np.power(0.5 + 0.5 * np.cos(ang * 160 + 1.3), 30) * (0.7 + 0.3 * np.cos(r * 90))
    noise = rng.normal(0, 0.03, (size, size)).astype(np.float32)
    shade = (1 - pore_depth * pore + late + 0.04 * ray + 0.12 * broad + noise)
    a = base[None, None, :] * shade[..., None]
    return Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8))


def save_jpg(im, path, q):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "JPEG", quality=q, optimize=True, progressive=False, subsampling=0 if q >= 90 else 2)
    return path.stat().st_size


def bake_maps():
    diff = np.asarray(load("Diffuse").convert("RGB")).astype(np.float32) / 255.0
    nor = load("nor_gl").convert("RGB")
    rough = np.asarray(load("Rough").convert("L"))
    ao = np.asarray(load("AO").convert("L"))
    # packed: R=AO, G=roughness, B=0 (metalness)
    packed = Image.fromarray(np.dstack([ao, rough, np.zeros_like(rough)]))

    sizes = {"master": (2048, MASTER, 92), "1024": (1024, SITE, 82), "512": (512, SITE, 80)}
    report = []
    for tone, fn in GRADES.items():
        graded = np.clip(fn(diff), 0, 1)
        im = Image.fromarray((graded * 255 + 0.5).astype(np.uint8))
        for key, (px, dst, q) in sizes.items():
            r = im if px == im.width else im.resize((px, px), Image.LANCZOS)
            suffix = "2048" if key == "master" else key
            size = save_jpg(r, dst / f"{tone}-albedo-{suffix}.jpg", q)
            report.append((f"{tone}-albedo-{suffix}.jpg", size, tuple(int(v) for v in (graded.reshape(-1, 3).mean(0) * 255))))
        eg = endgrain(im, 1024, seed=7, tone=tone)
        for px, dst, q in ((1024, MASTER, 88), (512, SITE, 80)):
            r = eg.resize((px, px), Image.LANCZOS)
            report.append((f"endgrain-{tone}-{px}.jpg", save_jpg(r, dst / f"endgrain-{tone}-{px}.jpg", q),
                           tuple(int(v) for v in np.asarray(r).reshape(-1, 3).mean(0))))
    for key, (px, dst, q) in sizes.items():
        suffix = "2048" if key == "master" else key
        n = nor if px == nor.width else nor.resize((px, px), Image.LANCZOS)
        p = packed if px == packed.width else packed.resize((px, px), Image.LANCZOS)
        report.append((f"oak-normal-{suffix}.jpg", save_jpg(n, dst / f"oak-normal-{suffix}.jpg", max(q, 88)), None))
        # roughness is high-frequency grey noise: cheap to encode at a lower quality, the eye
        # only sees it as sheen variation (viewer copies get q 70, master keeps q 90)
        report.append((f"oak-rough-{suffix}.jpg", save_jpg(p, dst / f"oak-rough-{suffix}.jpg", 90 if key == "master" else 70), None))
    for name, size, mean in report:
        print(f"{name:28s} {size/1024:6.0f} KB" + (f"  mean rgb {mean}" if mean else ""))


# ---- Radiance RGBE (.hdr) --------------------------------------------------
def read_hdr(path):
    data = path.read_bytes()
    m = re.search(rb"\n\n-Y (\d+) \+X (\d+)\n", data)
    if not m:
        raise SystemExit(f"unsupported HDR layout in {path}")
    h, w = int(m.group(1)), int(m.group(2))
    pos = m.end()
    out = np.empty((h, w, 4), np.uint8)
    mv = memoryview(data)
    for y in range(h):
        if data[pos] == 2 and data[pos + 1] == 2 and (data[pos + 2] << 8 | data[pos + 3]) == w:
            pos += 4
            line = np.empty((4, w), np.uint8)
            for c in range(4):
                x = 0
                while x < w:
                    n = data[pos]; pos += 1
                    if n > 128:
                        n -= 128; line[c, x:x + n] = data[pos]; pos += 1
                    else:
                        line[c, x:x + n] = np.frombuffer(mv[pos:pos + n], np.uint8); pos += n
                    x += n
            out[y] = line.T
        else:  # flat scanline
            out[y] = np.frombuffer(mv[pos:pos + w * 4], np.uint8).reshape(w, 4); pos += w * 4
    e = out[..., 3].astype(np.int32)
    scale = np.where(e > 0, np.ldexp(1.0, e - 136), 0.0).astype(np.float32)
    return out[..., :3].astype(np.float32) * scale[..., None]


def write_hdr(path, rgb):
    h, w, _ = rgb.shape
    mx = rgb.max(axis=2)
    e = np.zeros_like(mx, np.int32)
    mant = np.zeros_like(mx)
    nz = mx > 1e-32
    mant[nz], e[nz] = np.frexp(mx[nz])
    scale = np.where(nz, mant * 256.0 / np.where(nz, mx, 1), 0.0)
    rgbe = np.zeros((h, w, 4), np.uint8)
    rgbe[..., :3] = np.clip(rgb * scale[..., None], 0, 255).astype(np.uint8)
    rgbe[..., 3] = np.where(nz, e + 128, 0).astype(np.uint8)
    buf = io.BytesIO()
    buf.write(b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n" + f"-Y {h} +X {w}\n".encode())
    for y in range(h):
        buf.write(bytes([2, 2, w >> 8, w & 255]))
        for c in range(4):
            line = rgbe[y, :, c].tobytes()
            x = 0
            while x < w:
                # run of identical bytes?
                run = 1
                while x + run < w and run < 127 and line[x + run] == line[x]:
                    run += 1
                if run >= 4:
                    buf.write(bytes([128 + run, line[x]])); x += run; continue
                # literal chunk up to the next run of >= 4 (max 128)
                end = x + 1
                while end < w and end - x < 128:
                    if end + 3 < w and line[end] == line[end + 1] == line[end + 2] == line[end + 3]:
                        break
                    end += 1
                buf.write(bytes([end - x]) + line[x:end]); x = end
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())
    return path.stat().st_size


def bake_hdr(out_w=256):
    src = SRC / "brown_photostudio_02_1k.hdr"
    img = read_hdr(src)
    h, w, _ = img.shape
    f = w // out_w
    small = img.reshape(h // f, f, w // f, f, 3).mean(axis=(1, 3))
    # mild clamp of the hottest pixels so the 8-bit-mantissa file does not band in the lamp
    small = np.minimum(small, 80.0)
    dst = SITE / f"studio-{out_w}.hdr"
    size = write_hdr(dst, small.astype(np.float32))
    back = read_hdr(dst)
    err = float(np.abs(back - small).max() / max(small.max(), 1e-6))
    print(f"{dst.name:28s} {size/1024:6.0f} KB  {small.shape[1]}x{small.shape[0]}  "
          f"mean {small.mean():.3f}  round-trip max err {err*100:.2f}%")


if __name__ == "__main__":
    if "--hdr-only" not in sys.argv:
        bake_maps()
    bake_hdr(256)
