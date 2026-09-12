#!/usr/bin/env python3
"""Product-context visualisations -> site/assets/product/<id>-<w>.{avif,webp} + manifest-home.json.

    python tools/imagegen/encode_product.py assets-src/product/imagegen/final/manifest-home.spec.json

The spec lists the accepted finals with their metadata (no alt/caption text: the page supplies the
localized strings). For each asset it writes one AVIF and one WebP per width (same encoder settings
as encode.py / optimise_renders.py) and then writes site/assets/product/manifest-home.json:

    {"version": 1, "generated": ISO, "assets": [ {id, role, tone, state, aspect, width, height, widths,
      formats, files: {avif: {"800": {path, bytes}, ...}, webp: {...}}, source, pipeline, kind, status,
      camera, table_width_fraction, checks, notes} ]}

encode.py is untouched: it owns site/assets/photos/manifest.json (the gallery visualisations); this
script owns site/assets/product/manifest-home.json only.

Spec entry (JSON):
    {"id": "goren-home-daylight", "png": "assets-src/product/imagegen/final/goren-home-daylight.png",
     "widths": [800, 1200, 1600], "role": "home", "tone": "natural", "state": "closed", "aspect": "3:2",
     "source": "...", "pipeline": "...", "status": "provisional", "camera": {...},
     "table_width_fraction": 0.7, "checks": {...}, "notes": "..."}
"""
import datetime, json, pathlib, sys
from PIL import Image
try:
    import pillow_avif  # noqa: F401
    AVIF = True
except Exception:
    AVIF = False

ROOT = pathlib.Path(__file__).resolve().parents[2]            # furniture/
DST = ROOT / "site" / "assets" / "product"
MANIFEST = DST / "manifest-home.json"

WEBP_Q = {640: 84, 800: 84, 1080: 84, 1200: 84, 1600: 82}
AVIF_Q = {640: 64, 800: 64, 1080: 62, 1200: 62, 1600: 60}


def encode_one(png: pathlib.Path, id_: str, widths):
    im = Image.open(png).convert("RGB")
    files = {"avif": {}, "webp": {}}
    for w in widths:
        if w > im.width:
            raise SystemExit(f"{id_}: width {w} exceeds the master ({im.width} px)")
        h = round(im.height * w / im.width)
        small = im.resize((w, h), Image.LANCZOS)
        webp = DST / f"{id_}-{w}.webp"
        small.save(webp, "WEBP", quality=WEBP_Q.get(w, 84), method=6)
        files["webp"][str(w)] = {"path": webp.name, "bytes": webp.stat().st_size}
        if AVIF:
            avif = DST / f"{id_}-{w}.avif"
            small.save(avif, "AVIF", quality=AVIF_Q.get(w, 62), speed=4)
            files["avif"][str(w)] = {"path": avif.name, "bytes": avif.stat().st_size}
    if not AVIF:
        del files["avif"]
    return im.size, files


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    spec_path = pathlib.Path(sys.argv[1])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    DST.mkdir(parents=True, exist_ok=True)
    assets = []
    for e in spec["assets"]:
        png = ROOT / e["png"]
        if not png.exists():
            sys.exit(f"missing final: {png}")
        (W, H), files = encode_one(png, e["id"], e["widths"])
        entry = {
            "id": e["id"], "role": e.get("role", "home"), "tone": e["tone"], "state": e["state"],
            "aspect": e["aspect"], "width": W, "height": H, "widths": list(e["widths"]),
            "formats": list(files.keys()), "files": files,
            "source": e["source"], "pipeline": e["pipeline"], "kind": "ai-visualisation",
            "status": e.get("status", "provisional"), "camera": e["camera"],
            "table_width_fraction": e["table_width_fraction"], "checks": e["checks"], "notes": e["notes"],
        }
        assets.append(entry)
        tot = {f: sum(v["bytes"] for v in files[f].values()) for f in files}
        print(f"{e['id']:26s} {W}x{H}  " + "  ".join(f"{f} {tot[f]/1024:.0f} KB" for f in tot))
        for f in files:
            for w, v in files[f].items():
                print(f"   {v['path']:40s} {v['bytes']/1024:7.1f} KB")
    out = {"version": 1, "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "assets": assets}
    MANIFEST.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {len(assets)} entries -> {MANIFEST}")


if __name__ == "__main__":
    main()
