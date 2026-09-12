#!/usr/bin/env python3
"""Product render set: renders-master/product/<id>.png -> site/assets/product/<id>-<w>.{avif,webp}
+ site/assets/product/manifest.json (+ renders-master/product/_contact.png).

    python tools/product_assets.py                 # every master present
    python tools/product_assets.py goren-compare   # only ids starting with this (the manifest is rewritten
                                                   # from every encoded asset on disk, so partial runs are safe)
    options: --grain=0.5   film-grain sigma in 8-bit levels (default 0.5, 0 = off)
             --no-avif     WebP only
             --no-contact  skip the contact sheet

Modelled on tools/optimise_renders.py: LANCZOS downscale, one faint deterministic grain per asset
family (the same noise for every tone of a view, so a tone cross-fade never shimmers), WebP q88-90,
AVIF q60-64 speed 4. Masters come from `node tools/render3d.js --product` (bg f4f1ea) with a .json
sidecar per id carrying the fitted camera; nothing here re-frames or crops except the finish swatches.

Checks, measured from the master's pixels against the flat ground (244,241,234):
  table_width_fraction   width of everything > 6/255 off the ground / image width  (the brief's definition;
                         it includes the key's cast-shadow tail — the geometry-only width, > 40/255, is in notes)
  ends_inside / feet_inside   the geometry bbox (> 40) keeps >= 1 % of the width/height from the frame edges
  shadow_inside          the faint bbox (> 6) keeps >= 1 % from every edge (contact blobs + cast-shadow tail)
  ground_ok              master corners == ground; every WebP/AVIF corner within +-3 per channel (lossy drift)
Close-ups (edge, frame) crop the geometry by design: their geometry checks are null, ground_ok is
measured on the corners that are ground in the master.
"""
import datetime, json, pathlib, sys
import numpy as np
from PIL import Image, ImageDraw
try:
    import pillow_avif  # noqa: F401
    AVIF = True
except Exception:
    AVIF = False

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "renders-master" / "product"
DST = ROOT / "site" / "assets" / "product"
BG_HEX = "#F4F1EA"
BG = np.array([244, 241, 234], dtype=np.int16)
TONES = ("natural", "smoked", "white")
STATES = ("closed", "open")


def wq(w):  # WebP quality per width (optimise_renders.py: 88 at 800, 90 above)
    return 88 if w <= 800 else 90


def aq(w):  # AVIF quality per width (64 / 62 / 60)
    return 64 if w <= 800 else 62 if w <= 1200 else 60


ASSETS = [
    dict(id="goren-studio-hero-natural-closed", role="hero", tone="natural", state="closed", aspect="2.2:1",
         size=(2400, 1091), widths=(1200, 1600, 2000), view="studio", budget={("avif", 2000): 250_000}),
    dict(id="goren-studio-hero-m-natural-closed", role="hero-mobile", tone="natural", state="closed", aspect="3:2",
         size=(2000, 1333), widths=(640, 800, 1000), view="studioM", budget={("avif", 1000): 150_000}),
]
for t in TONES:
    for s in STATES:
        ASSETS.append(dict(id=f"goren-compare-{t}-{s}", role="compare", tone=t, state=s, aspect="3:2",
                           size=(2400, 1600), widths=(800, 1200, 1600), view="compare", budget={("avif", 1600): 200_000}))
for t in TONES:
    ASSETS.append(dict(id=f"goren-edge-detail-{t}", role="edge", tone=t, state="closed", aspect="1:1",
                       size=(1600, 1600), widths=(640, 800, 1000), view="edge", closeup=True))
for t in TONES:
    ASSETS.append(dict(id=f"goren-frame-detail-{t}", role="frame", tone=t, state="closed", aspect="4:3",
                       size=(1600, 1200), widths=(640, 800, 1000), view="frame", closeup=True))
# finish swatches: one region of the tabletop face, cut from each compare-<tone>-closed master (same
# camera, same exposure), so the three tiles are comparable. Region = (left, top, side) in 1x master
# pixels; the cut is taken from the 2x supersampled frame (renders-master/product/ss2/) when it exists —
# from that low camera the top face is only ~70 px tall at 1x, so at 1x the 240 px tile would be a 3x upscale.
FINISH_REGION = (1360, 397, 62)   # largest square between the far and near arrises (measured; both slope up to the right)
for t in TONES:
    ASSETS.append(dict(id=f"goren-finish-{t}", role="finish", tone=t, state=None, aspect="1:1",
                       size=(240, 240), widths=(160, 240), kind="render-crop", crop_from=f"goren-compare-{t}-closed"))

args = sys.argv[1:]
opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in args if a.startswith("--"))
prefix = next((a for a in args if not a.startswith("--")), "")
GRAIN = float(opts.get("grain", 0.5))
AVIF = AVIF and "no-avif" not in opts


def grain(im, sigma, seed):
    """A whisper of luminance noise so the flat CG paper and the wood stop reading as vector.
    Deterministic per asset family so every tone of a view carries the same grain (cross-fade safe)."""
    if sigma <= 0:
        return im
    a = np.asarray(im).astype(np.float32)
    n = np.random.default_rng(seed).normal(0.0, sigma, a.shape[:2]).astype(np.float32)
    a += n[..., None]
    return Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8))


def family(asset_id):
    """Grain seed family: the id without its tone, so goren-compare-{natural,smoked,white}-open share noise."""
    parts = [p for p in asset_id.split("-") if p not in TONES]
    return "-".join(parts)


def bbox(mask):
    ys, xs = np.where(mask)
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def corners(im):
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    h, w = a.shape[:2]
    return [a[y, x] for y, x in ((1, 1), (1, w - 2), (h - 2, 1), (h - 2, w - 2))]


def measure(master, closeup=False):
    """Pixel checks on the master (exact ground): faint (> 6) and geometry (> 40) bounding boxes."""
    a = np.asarray(master.convert("RGB")).astype(np.int16)
    H, W = a.shape[:2]
    d = np.abs(a - BG).max(axis=2)
    faint, strong = bbox(d > 6), bbox(d > 40)
    ground_corners = [bool(np.abs(c - BG).max() <= 1) for c in corners(master)]
    m = dict(width=W, height=H, ground_corners=ground_corners)
    if faint:
        l, t, r, b = faint
        m["table_width_fraction"] = round((r - l + 1) / W, 3)
        m["faint_gaps"] = dict(left=round(l / W, 3), right=round((W - 1 - r) / W, 3), top=round(t / H, 3), bottom=round((H - 1 - b) / H, 3))
    if strong:
        l, t, r, b = strong
        m["geometry_width_fraction"] = round((r - l + 1) / W, 3)
        m["geometry_gaps"] = dict(left=round(l / W, 3), right=round((W - 1 - r) / W, 3), top=round(t / H, 3), bottom=round((H - 1 - b) / H, 3))
    if closeup or not faint or not strong:
        m["checks"] = dict(ends_inside=None, feet_inside=None, shadow_inside=None)
    else:
        g, f = m["geometry_gaps"], m["faint_gaps"]
        m["checks"] = dict(ends_inside=g["left"] >= 0.01 and g["right"] >= 0.01,
                           feet_inside=g["bottom"] >= 0.01 and g["top"] >= 0.01,
                           shadow_inside=min(f.values()) >= 0.01)
    return m


def encode(asset, im, out_paths):
    """Resize + grain + WebP/AVIF for every width; returns files{format}{width} = {path, bytes}."""
    files = {"avif": {}, "webp": {}} if AVIF else {"webp": {}}
    seed = sum(ord(c) for c in family(asset["id"]))
    for w in asset["widths"]:
        h = round(im.height * w / im.width)
        r = im.resize((w, h), Image.LANCZOS) if (w, h) != im.size else im
        r = grain(r, GRAIN, seed + w)
        out = DST / f"{asset['id']}-{w}.webp"
        r.save(out, "WEBP", quality=wq(w), method=6)
        files["webp"][str(w)] = {"path": out.name, "bytes": out.stat().st_size}
        out_paths.append(out)
        if AVIF:
            outa = DST / f"{asset['id']}-{w}.avif"
            r.save(outa, "AVIF", quality=aq(w), speed=4)
            files["avif"][str(w)] = {"path": outa.name, "bytes": outa.stat().st_size}
            out_paths.append(outa)
    return files


def variants_ground_ok(paths, ground_corners):
    """Every encoded variant: the corners that are ground in the master stay within +-3 of the ground."""
    worst = 0
    for p in paths:
        for c, is_ground in zip(corners(Image.open(p)), ground_corners):
            if is_ground:
                worst = max(worst, int(np.abs(c - BG).max()))
    return worst


def git_sha():
    """HEAD's short sha, plus '+dirty' while site/assets/goren3d.js has uncommitted changes (the VIEWS the
    masters were rendered with are then not the ones at that sha — commit and re-run to clear it)."""
    import subprocess
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "site/assets/goren3d.js"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
        return sha + ("+dirty" if dirty else "")
    except Exception:
        return "unknown"


def contact_sheet(entries):
    """All masters side by side (scaled to 480 px wide), labelled, for a consistency read."""
    cols, cell_w, cell_h, pad = 4, 480, 340, 28
    rows = (len(entries) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell_w + pad) + pad, rows * (cell_h + pad) + pad), (244, 241, 234))
    draw = ImageDraw.Draw(sheet)
    for i, (asset_id, im) in enumerate(entries):
        x, y = pad + (i % cols) * (cell_w + pad), pad + (i // cols) * (cell_h + pad)
        s = min(cell_w / im.width, (cell_h - 18) / im.height)
        th = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        sheet.paste(th, (x, y))
        draw.rectangle([x - 1, y - 1, x + th.width, y + th.height], outline=(200, 196, 188))
        draw.text((x, y + th.height + 4), asset_id, fill=(37, 39, 32))
    out = SRC / "_contact.png"
    sheet.save(out)
    return out


def main():
    DST.mkdir(parents=True, exist_ok=True)
    sha = git_sha()
    manifest_assets, sheet_entries, over_budget, drift_bad, missing = [], [], [], [], []
    for asset in ASSETS:
        aid = asset["id"]
        if asset.get("crop_from"):
            src_png = SRC / f"{asset['crop_from']}.png"
        else:
            src_png = SRC / f"{aid}.png"
        if not src_png.exists():
            missing.append(aid)
            continue
        if prefix and not aid.startswith(prefix):
            # not re-encoded this run; still listed if its files exist (manifest = everything on disk)
            existing = DST / f"{aid}-{asset['widths'][0]}.webp"
            if not existing.exists():
                continue
        master = Image.open(src_png).convert("RGB")
        side = {}
        side_path = SRC / f"{asset.get('crop_from', aid)}.json"
        if side_path.exists():
            side = json.loads(side_path.read_text(encoding="utf-8"))
        frame = side.get("frame", {})
        if asset.get("crop_from"):
            l, t, s = FINISH_REGION
            ss_png = SRC / "ss2" / f"{asset['crop_from']}.png"
            ss = 2 if ss_png.exists() else 1
            src_im = Image.open(ss_png).convert("RGB") if ss == 2 else master
            im = src_im.crop((l * ss, t * ss, (l + s) * ss, (t + s) * ss)).resize(asset["size"], Image.LANCZOS)
            kind = "render-crop"
            source = f"renders-master/product/{'ss2/' if ss == 2 else ''}{asset['crop_from']}.png"
            pipeline = f"tools/product_assets.py crop {asset['crop_from']} region=({l},{t},{s})@1x from the {ss}x frame -> {asset['size'][0]} px"
            m = dict(width=im.width, height=im.height, checks=dict(ends_inside=None, feet_inside=None, shadow_inside=None))
            m["table_width_fraction"] = 1.0
            ground_corners = [False] * 4
        else:
            im = master
            if im.size != tuple(asset["size"]):
                print(f"WARNING {aid}: master is {im.size}, expected {asset['size']}")
            kind, source = "render", f"renders-master/product/{aid}.png"
            pipeline = side.get("pipeline", f"tools/render3d.js --product {aid}")
            m = measure(master, asset.get("closeup", False))
            ground_corners = m["ground_corners"]
        paths = []
        if not prefix or aid.startswith(prefix):
            files = encode(asset, im, paths)
        else:
            files = {}
            for fmt in (("avif", "webp") if AVIF else ("webp",)):
                files[fmt] = {}
                for w in asset["widths"]:
                    p = DST / f"{aid}-{w}.{fmt}"
                    if p.exists():
                        files[fmt][str(w)] = {"path": p.name, "bytes": p.stat().st_size}
                        paths.append(p)
        drift = variants_ground_ok(paths, ground_corners) if any(ground_corners) else None
        ground_ok = None if drift is None else (drift <= 3 and all(ground_corners) if not asset.get("closeup") else drift <= 3)
        if ground_ok is False:
            drift_bad.append((aid, drift, ground_corners))
        for (fmt, w), limit in asset.get("budget", {}).items():
            got = files.get(fmt, {}).get(str(w), {}).get("bytes")
            if got is not None and got > limit:
                over_budget.append((aid, fmt, w, got, limit))
        cam = None
        if frame:
            cam = dict(az=round(frame["az"], 1), el=round(frame["el"], 1), fov_v=round(frame["fov"], 1),
                       position_m=[round(v, 3) for v in frame["position"]], target_m=[round(v, 3) for v in frame["target"]],
                       height_m=round(frame["height"], 3), distance_m=round(frame["distance"], 3))
        notes = []
        if asset["role"] in ("hero", "hero-mobile", "compare"):
            notes.append(f"geometry-only width (>40/255) {m.get('geometry_width_fraction')}; the >6/255 figure includes the key's cast-shadow tail to the right; "
                         f"gaps L/R/T/B faint {m['faint_gaps']} geometry {m['geometry_gaps']}")
        if asset["role"] == "hero":
            notes.append("2.2:1 is bound vertically from eye level (silhouette ~1.8:1): 80-86 % of the width would need >100 % of the height, so el 12.5 / camera 1.07 m was kept and the width is what fits")
        if asset["role"] == "compare":
            notes.append(f"camera locked: fitted once on the OPEN bounds (fit={frame.get('fit')}), identical position/target/fov/light/exposure for all six")
        if asset["role"] == "edge":
            notes.append(f"close-up of the +x/+z outer corner of the top; raking key {frame.get('key')} at {frame.get('keyIntensity')}; geometry crops by design")
        if asset["role"] == "frame":
            notes.append(f"near trestle from 20 cm below the top plane; fill {frame.get('fill')} + floor bounce 0.9 so the beam reads as matte steel; geometry crops by design")
        if asset["role"] == "finish":
            notes.append(f"{FINISH_REGION[2]} px (at 1x) square of the tabletop face at ({FINISH_REGION[0]},{FINISH_REGION[1]}) of the compare-closed master, cut from the 2x frame ({FINISH_REGION[2] * 2} px) and LANCZOS to 160/240; same region, camera and exposure for the three tones; the face is foreshortened from that low camera, so the grain reads as fine streaks")
        if drift is not None:
            notes.append(f"worst corner drift in the encoded variants: {drift}/255")
        notes.append("render/visualisation of provisional procedural geometry (no manufacturer CAD); not a photograph")
        entry = {
            "id": aid, "role": asset["role"], "tone": asset["tone"], "state": asset["state"], "aspect": asset["aspect"],
            "width": im.width, "height": im.height, "widths": list(asset["widths"]),
            "formats": ["avif", "webp"] if AVIF else ["webp"], "files": files,
            "source": source, "pipeline": pipeline,
            "reference_version": f"goren3d.js {sha} VIEWS.{asset.get('view', side.get('view', 'compare'))}",
            "kind": kind, "status": "provisional",
            "camera": cam,
            "table_width_fraction": m.get("table_width_fraction"),
            "checks": dict(m["checks"], ground_ok=ground_ok),
            "notes": " | ".join(notes),
        }
        manifest_assets.append(entry)
        sheet_entries.append((aid, im))
        sizes = ", ".join(f"{w}: " + " / ".join(f"{files[f][str(w)]['bytes'] // 1024} KB {f}" for f in files if str(w) in files[f]) for w in asset["widths"])
        print(f"{aid}: {im.width}x{im.height} width={m.get('table_width_fraction')} geo={m.get('geometry_width_fraction')} checks={entry['checks']} -> {sizes}")

    # social card: not encoded here (tools/make-og.js), listed so the build sees the whole set
    og = ROOT / "site" / "assets" / "og.png"
    if og.exists():
        ogim = Image.open(og).convert("RGB")
        og_ok = all(int(np.abs(c - BG).max()) <= 1 for c in corners(ogim))
        manifest_assets.append({
            "id": "goren-social", "role": "social", "tone": "natural", "state": "closed", "aspect": "1.91:1",
            "width": ogim.width, "height": ogim.height, "widths": [ogim.width], "formats": ["png"],
            "files": {"png": {str(ogim.width): {"path": "../og.png", "bytes": og.stat().st_size}}},
            "source": "renders-master/product/goren-studio-hero-natural-closed.png + tools/og.html",
            "pipeline": "node tools/make-og.js (tools/og.html: hero master, inlined logo lockup, IBM Plex Sans Hebrew, ground #F4F1EA)",
            "reference_version": f"goren3d.js {sha} VIEWS.studio", "kind": "composite", "status": "provisional",
            "camera": next((e["camera"] for e in manifest_assets if e["id"] == "goren-studio-hero-natural-closed"), None),
            "table_width_fraction": None,
            "checks": dict(ends_inside=None, feet_inside=None, shadow_inside=None, ground_ok=og_ok),
            "notes": "1200x630 social preview; Hebrew title + 160/220 line only, no price; the hero render composited on the page ground",
        })
        sheet_entries.append(("goren-social (og.png)", ogim))

    manifest = {"version": 1, "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "background": BG_HEX, "assets": manifest_assets}
    (DST / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(f["bytes"] for e in manifest_assets for fmt in e["files"].values() for f in fmt.values() if e["role"] != "social")
    print(f"\nmanifest: {len(manifest_assets)} assets, encoded variants total {total / 1024:.0f} KB (avif={'yes' if AVIF else 'no'}, grain={GRAIN})")
    if missing:
        print("MISSING masters:", ", ".join(missing))
    for aid, fmt, w, got, limit in over_budget:
        print(f"OVER BUDGET: {aid} {fmt} {w}w {got // 1024} KB > {limit // 1024} KB")
    for aid, drift, gc in drift_bad:
        print(f"GROUND DRIFT: {aid} worst {drift}/255 (master corners on ground: {gc})")
    if "no-contact" not in opts and sheet_entries:
        print("contact sheet:", contact_sheet(sheet_entries))
    return 1 if (over_budget or drift_bad) else 0


if __name__ == "__main__":
    sys.exit(main())
