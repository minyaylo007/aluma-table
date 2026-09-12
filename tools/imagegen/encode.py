#!/usr/bin/env python3
"""Accepted visualisations -> responsive WebP/AVIF + site/assets/photos/manifest.json.

    python tools/imagegen/encode.py            # encode every entry of FINALS
    python tools/imagegen/encode.py apartment  # only ids starting with this

Sources are the accepted finals in night/imagegen/final/<id>.png (copied there by hand from
candidates/ once they passed the honesty gate; see REPORT.md). For each id it writes
site/assets/photos/<id>-{800,1200,1600}.webp (+ .avif when pillow-avif is present) and rewrites
manifest.json with one entry per accepted image. Same encoder settings as tools/optimise_renders.py
(that file is untouched: it is the renders' pipeline, this is the visualisations').

Every caption says it is a visualisation (הדמיה) - these are AI-assisted images built on our own
renders, never photographs, and the page must label them as such.
"""
import json, pathlib, sys
from PIL import Image
try:
    import pillow_avif  # noqa: F401
    AVIF = True
except Exception:
    AVIF = False

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C

SRC = C.FINAL
DST = C.PHOTOS
WIDTHS = (800, 1200, 1600)
WEBP_Q = {800: 84, 1200: 84, 1600: 82}
AVIF_Q = {800: 64, 1200: 62, 1600: 60}

MODEL = "us.stability.stable-image-control-structure-v1:0 + stable-image-search-replace-v1:0 + stable-image-inpaint-v1:0"

# id -> metadata. Only images that passed the honesty gate belong here (REPORT.md has the grading).
FINALS = {
    "apartment-natural-closed": dict(
        scene="apartment", tone="natural", state="closed", seed=16, view="hero",
        alt_he="הדמיה: שולחן גורן סגור (160 ס\"מ) בגוון אלון טבעי בדירה מוארת, קערת לימונים ועץ זית בעציץ",
        alt_en="Visualisation: GOREN table closed (160 cm) in natural oak in a bright apartment, a bowl of lemons and a potted olive tree",
        caption_he="הדמיה. גוון אלון טבעי, מצב סגור 160 ס\"מ. שתי רגלי A מאלון מלא וקורת פלדה שחורה אחת.",
        caption_en="Visualisation. Natural oak, closed at 160 cm. Two solid-oak A-frame trestles and one black steel beam."),
    "nook-natural-closed": dict(
        scene="nook", tone="natural", state="closed", seed=16, view="hero",
        alt_he="הדמיה: שולחן גורן בגוון אלון טבעי בפינת אוכל שקטה מול וילון פשתן, אגרטל חימר קטן על השולחן",
        alt_en="Visualisation: GOREN table in natural oak in a calm dining nook in front of a linen curtain, a small clay vase on the top",
        caption_he="הדמיה. אלון טבעי בפינת אוכל עם וילון פשתן. פלטה בעובי 40 מ\"מ עם פאזה בצד התחתון.",
        caption_en="Visualisation. Natural oak in a dining nook with a linen curtain. 40 mm top with the chamfer underneath."),
    "evening-natural-closed": dict(
        scene="evening", tone="natural", state="closed", seed=16, view="hero",
        alt_he="הדמיה: שולחן גורן בגוון אלון טבעי בערב באור מנורה חם, שתי כוסות על השולחן",
        alt_en="Visualisation: GOREN table in natural oak in the evening under warm lamp light, two cups on the top",
        caption_he="הדמיה. ערב, אור מנורה חם על גימור שמן-שעווה מט.",
        caption_en="Visualisation. Evening, warm lamp light on the matte oil-wax finish."),
    "apartment-smoked-closed": dict(
        scene="apartment", tone="smoked", state="closed", seed=16, view="hero",
        alt_he="הדמיה: שולחן גורן בגוון אלון מעושן (חום כהה) בדירה, קערה עם אגסים על השולחן",
        alt_en="Visualisation: GOREN table in smoked (dark brown) oak in an apartment, a bowl of pears on the top",
        caption_he="הדמיה. גוון אלון מעושן: הרגליים והפלטה באותו גוון, הקורה שחורה.",
        caption_en="Visualisation. Smoked oak: legs and top in the same tone, the beam black."),
    "nook-white-closed": dict(
        scene="nook", tone="white", state="closed", seed=16, view="hero",
        alt_he="הדמיה: שולחן גורן בגוון אלון מולבן בפינת אוכל מול וילון פשתן, אגרטל חימר על השולחן",
        alt_en="Visualisation: GOREN table in whitewashed oak in a dining nook in front of a linen curtain, a clay vase on the top",
        caption_he="הדמיה. גוון אלון מולבן בפינת אוכל בהירה.",
        caption_en="Visualisation. Whitewashed oak in a bright dining nook."),
}


def encode(png: pathlib.Path):
    im = Image.open(png).convert("RGB")
    sizes = []
    for w in WIDTHS:
        if w > im.width:
            continue
        h = round(im.height * w / im.width)
        small = im.resize((w, h), Image.LANCZOS)
        webp = DST / f"{png.stem}-{w}.webp"
        small.save(webp, "WEBP", quality=WEBP_Q[w], method=6)
        entry = {"w": w, "h": h, "webp": webp.name, "webp_bytes": webp.stat().st_size}
        if AVIF:
            avif = DST / f"{png.stem}-{w}.avif"
            small.save(avif, "AVIF", quality=AVIF_Q[w], speed=4)
            entry.update(avif=avif.name, avif_bytes=avif.stat().st_size)
        sizes.append(entry)
    return im.size, sizes


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else ""
    DST.mkdir(parents=True, exist_ok=True)
    manifest = []
    for id_, meta in FINALS.items():
        src = SRC / f"{id_}.png"
        if not src.exists():
            sys.exit(f"missing final: {src}")
        if not id_.startswith(prefix):
            continue
        (W, H), sizes = encode(src)
        total = sum(s["webp_bytes"] for s in sizes)
        print(f"{id_:32s} {W}x{H}  webp total {total/1024:.0f} KB" + ("  +avif" if AVIF else ""))
    # the manifest always lists every final (a partial re-encode must not drop entries)
    for id_, meta in FINALS.items():
        src = SRC / f"{id_}.png"
        W, H = Image.open(src).size
        entry = {"id": id_, "scene": meta["scene"], "tone": meta["tone"], "state": meta["state"],
                 "seed": meta["seed"], "view": meta["view"], "model": MODEL, "width": W, "height": H,
                 "kind": "ai-visualisation", "source": "own 3D render (renders-master) -> Bedrock Stability control-structure",
                 "widths": [w for w in WIDTHS if w <= W], "formats": ["webp"] + (["avif"] if AVIF else []),
                 "alt_he": meta["alt_he"], "alt_en": meta["alt_en"],
                 "caption_he": meta["caption_he"], "caption_en": meta["caption_en"]}
        manifest.append(entry)
    (DST / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {len(manifest)} entries -> {DST / 'manifest.json'}")


if __name__ == "__main__":
    main()
