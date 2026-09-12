#!/usr/bin/env python3
"""Render -> photoreal lifestyle candidate via Bedrock Stability control-structure.

    python tools/imagegen/generate.py gen --render renders-master/hero-natural-closed.png \
        --scene apartment --seeds 11,12,13 --control 0.9

Writes night/imagegen/candidates/<scene>-<tone>-<state>-s<seed>.png and logs every call to
night/imagegen/CALLS.jsonl. The image is a *candidate* until graded:

    python tools/imagegen/generate.py grade night/imagegen/candidates/x.png accept "legs oak, beam black, no grommet"
    python tools/imagegen/generate.py grade night/imagegen/candidates/x.png reject "legs painted black"

Honesty gate (what a candidate must show before it may be accepted):
  - two A-frame trestles of solid oak in the SAME tone as the top (never black/metal/painted)
  - exactly one slim matte-black steel beam under the top, nothing else between the trestles
  - a 40 mm top with the chamfer on the underside only; no grommet, no hole, no apron, no stretcher
  - proportions of the render kept (160x90 closed / 220x90 open, 75 high)
  - no people, no text, no logos; props only as scene context
"""
import argparse, pathlib, sys
from PIL import Image, ImageChops

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C

PROMPT_VERSION = 2

TONE_WORDS = {
    "natural": "light natural oak",
    "smoked":  "smoked oak, a warm medium-dark brown oak",
    "white":   "whitewashed oak, very pale lime-washed oak",
}


def product(tone, state):
    """The product sentence is identical in every scene: it is the honesty gate written as a prompt."""
    t = TONE_WORDS[tone]
    length = "extended to 220 cm with the leaf in place" if state == "open" else "160 cm long"
    return (
        f"a rectangular dining table in {t}: the table top is {t} veneer with a solid oak edge, "
        f"40 mm thick, {length}, with a small chamfer on the underside of the edge; it stands on two "
        f"A-frame trestle legs made of solid {t} wood, the trestles are exactly the same wood and the "
        f"same colour as the top, square-section wooden legs; the two wooden trestles are joined under "
        f"the top by one thin horizontal bar of matte black powder-coated steel, the only black part of the "
        f"table; no apron, no stretcher, nothing else under the top"
    )


SCENES = {
    "apartment": dict(
        desc="bright Israeli apartment, plaster walls, pale terrazzo floor, afternoon window light",
        scene=("photographed in a bright modern Israeli apartment: smooth white plaster walls, a pale "
               "terrazzo tile floor, soft afternoon daylight coming from a large window on the left, "
               "a hint of a balcony door; a simple ceramic bowl on the table, a plant in the corner"),
    ),
    "nook": dict(
        desc="calm dining nook with a linen curtain",
        scene=("photographed in a calm dining nook: an off-white linen curtain softly lit from behind, "
               "warm white wall, light stone tile floor, diffused morning daylight, a small clay vase "
               "with dried grass on the table, quiet and minimal"),
    ),
    "kitchen": dict(
        desc="family kitchen-diner, table open at 220, plain wooden chairs",
        scene=("photographed in a family kitchen-diner: the edge of a plain white kitchen counter in the "
               "background, light grey porcelain tile floor, simple plain wooden dining chairs pushed "
               "under the long sides of the table, a fruit bowl, bright even daylight from a window"),
    ),
    "evening": dict(
        desc="evening scene with warm lamp light",
        scene=("photographed in the evening: a warm pendant lamp glowing above the table, dim room, "
               "warm amber light on the oak, dark window behind, a linen runner and two ceramic cups "
               "on the table, cosy, natural shadows"),
    ),
    # A3 "goren-home-daylight" (design brief): contemporary apartment dining area, restrained off-white
    # plaster, light stone / pale terrazzo floor, neutral daylight from camera-left; no villa, arches,
    # olive tree, lemons, travertine slabs or clutter. Props (a cup) are added later by inpaint.
    "daylight": dict(
        desc="contemporary apartment dining area, off-white plaster, pale terrazzo, neutral daylight from the left",
        scene=("photographed in a calm contemporary apartment dining area: smooth off-white lime plaster "
               "walls, a pale honed stone floor with a fine light terrazzo speckle, neutral soft daylight "
               "falling from a large window on the left just out of frame, quiet, minimal and uncluttered, "
               "bare walls, an empty clean table top, camera at about 1.15 m height"),
        neg_extra=("olive tree, lemons, fruit, arch, arches, travertine, villa, rustic, ornament, "
                   "decoration, clutter, rug, carpet, plant, flowers, wood floor, plank floor, "
                   "knot, stain, mark on the table top"),
    ),
}

STYLE = ("realistic interior photograph, 50 mm lens at seated eye level, natural colours, soft shadows, "
         "matte oil-waxed wood with visible oak grain, no gloss")

NEGATIVES = {
    # v1: kills black legs reliably, but the beam comes out oak too (needs a beam fix afterwards)
    1: ("black legs, dark legs, metal legs, steel legs, painted legs, grey legs, chrome, "
        "grommet, hole in the table top, cable port, socket, cutout, apron, stretcher, extra bar, "
        "cross brace, shelf under the table, drawer, "
        "concrete floor, grey concrete, people, hands, text, letters, watermark, logo, "
        "glossy varnish, blurry, deformed, extra legs"),
    # v2: no colour words about the legs in the negative; the beam is described as black steel in the prompt
    2: ("metal legs, steel legs, chrome legs, wooden beam, oak beam, "
        "grommet, hole in the table top, cable port, socket, cutout, apron, stretcher, extra bar, "
        "cross brace, foot rail, shelf under the table, drawer, "
        "concrete floor, grey concrete, people, hands, text, letters, watermark, logo, "
        "glossy varnish, blurry, deformed, extra legs"),
}
NEGATIVE = NEGATIVES[max(NEGATIVES)]


def build_prompt(scene, tone, state, extra=""):
    p = f"{product(tone, state)}; {SCENES[scene]['scene']}; {STYLE}"
    if extra:
        p += "; " + extra
    return p


def autocrop(im, margin):
    """Crop the flat paper background to the table's bbox + margin (same idea as optimise_renders)."""
    bg = Image.new("RGB", im.size, im.getpixel((2, 2)))
    diff = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 6 else 0)
    box = diff.getbbox()
    if not box:
        return im
    l, t, r, b = box
    mw, mh = int((r - l) * margin), int((b - t) * margin)
    return im.crop((max(0, l - mw), max(0, t - mh), min(im.width, r + mw), min(im.height, b + mh)))


def table_bbox(im):
    bg = Image.new("RGB", im.size, im.getpixel((2, 2)))
    diff = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 6 else 0)
    return diff.getbbox()


# Room structure sketched into the render so control-structure has something to build the room
# from (a flat paper background becomes a flat wall no matter what the prompt says). Shapes are
# plain blocks/outlines in paper-like tones; they are structure hints, not the product.
def sketch_scene(im, scene, state):
    from PIL import ImageDraw
    W, H = im.size
    box = table_bbox(im)
    if not box:
        return im
    l, t, r, b = box
    h = b - t
    y_floor = int(b - 0.32 * h)                 # wall/floor line ~ at the far feet
    table = im.copy()                           # pasted back on top at the end: the room is behind the table
    im = im.copy()
    d = ImageDraw.Draw(im)
    paper = im.getpixel((2, 2))
    dark = tuple(max(0, c - 150) for c in paper)      # strong: the structure map needs real contrast
    light = tuple(min(255, c + 22) for c in paper)
    mid = tuple(max(0, c - 70) for c in paper)
    glass = (150, 165, 175)                            # window pane: darker than the wall, cool

    def window(x0, x1, y0, y1, mullions=1):
        d.rectangle([x0, y0, x1, y1], fill=glass, outline=dark, width=14)
        for i in range(1, mullions + 1):
            x = x0 + (x1 - x0) * i / (mullions + 1)
            d.line([x, y0, x, y1], fill=dark, width=10)
        d.line([x0, (y0 + y1) // 2, x1, (y0 + y1) // 2], fill=dark, width=10)

    def chair(cx, y_seat, w, back_h):
        # a plain chair seen from the front: back + two front legs, drawn behind the table top
        d.rectangle([cx - w // 2, y_seat - back_h, cx + w // 2, y_seat], fill=mid, outline=dark, width=6)
        d.rectangle([cx - w // 2 + 10, y_seat - back_h + 12, cx + w // 2 - 10, y_seat - back_h // 2], fill=paper)
        d.line([cx - w // 2 + 8, y_seat - back_h + 10, cx - w // 2 + 8, y_seat], fill=dark, width=8)
        d.line([cx + w // 2 - 8, y_seat - back_h + 10, cx + w // 2 - 8, y_seat], fill=dark, width=8)

    if scene in ("apartment", "kitchen", "nook", "evening", "daylight"):
        d.line([0, y_floor, W, y_floor], fill=mid, width=8)                # skirting / floor line
    if scene in ("apartment", "daylight"):
        # the same hints as "apartment" so seed 16 keeps the geometry that passed the gate there
        window(int(0.03 * W), int(0.24 * W), int(0.10 * H), y_floor + int(0.04 * H), mullions=1)  # balcony door, left
    if scene == "nook":
        # a curtain: tall soft panel behind the table, left of centre
        x0, x1 = int(0.30 * W), int(0.62 * W)
        d.rectangle([x0, 0, x1, y_floor], fill=light, outline=mid, width=6)
        for i in range(1, 7):
            x = x0 + (x1 - x0) * i / 7
            d.line([x, 0, x, y_floor], fill=mid, width=7)
        window(int(0.34 * W), int(0.58 * W), int(0.08 * H), y_floor - int(0.03 * H), mullions=1)  # window behind the curtain
    if scene == "kitchen":
        # counter block, right background
        d.rectangle([int(0.70 * W), y_floor - int(0.26 * H), W, y_floor], fill=mid, outline=dark, width=8)
        d.line([int(0.70 * W), y_floor - int(0.26 * H) + 16, W, y_floor - int(0.26 * H) + 16], fill=dark, width=14)
        d.line([int(0.85 * W), y_floor - int(0.26 * H) + 16, int(0.85 * W), y_floor], fill=dark, width=6)
        # two plain chairs behind the far long side
        y_top = t + int(0.12 * h)
        span = r - l
        for fx in (0.36, 0.62):
            chair(int(l + span * fx), y_top + int(0.05 * h), int(0.075 * span), int(0.20 * h))
    if scene == "evening":
        cx = (l + r) // 2
        d.line([cx, 0, cx, int(0.10 * H)], fill=dark, width=5)             # cord
        d.polygon([(cx - int(0.06 * W), int(0.19 * H)), (cx + int(0.06 * W), int(0.19 * H)), (cx + int(0.02 * W), int(0.10 * H)), (cx - int(0.02 * W), int(0.10 * H))], fill=dark)
        window(int(0.66 * W), int(0.90 * W), int(0.08 * H), y_floor - int(0.02 * H), mullions=2)
    bg = Image.new("RGB", table.size, paper)
    mask = ImageChops.difference(table, bg).convert("L").point(lambda v: 255 if v > 6 else 0)
    im.paste(table, (0, 0), mask)
    return im


def prepare_input(render, crop_margin=None, width=2400, scene=None, state=None, sketch=False):
    im = Image.open(render).convert("RGB")
    if crop_margin is not None:
        im = autocrop(im, crop_margin)
    if im.width != width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    if sketch and scene:
        im = sketch_scene(im, scene, state)
    return im


def unique(path):
    p = pathlib.Path(path)
    if not p.exists():
        return p
    i = 2
    while True:
        q = p.with_name(f"{p.stem}-{i}{p.suffix}")
        if not q.exists():
            return q
        i += 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser("gen")
    g.add_argument("--render", required=True)
    g.add_argument("--scene", required=True, choices=sorted(SCENES))
    g.add_argument("--seeds", default="11", help="comma list")
    g.add_argument("--control", type=float, default=0.9)
    g.add_argument("--tone", choices=sorted(TONE_WORDS))
    g.add_argument("--state", choices=["closed", "open"])
    g.add_argument("--crop", type=float, default=None, help="autocrop margin fraction, e.g. 0.18 (default: no crop)")
    g.add_argument("--extra", default="", help="appended to the prompt")
    g.add_argument("--negative-extra", default="")
    g.add_argument("--neg", type=int, default=max(NEGATIVES), help="negative prompt version")
    g.add_argument("--tag", default="", help="suffix in the output name")
    g.add_argument("--sketch", action="store_true", help="sketch room structure into the input (see sketch_scene)")
    g.add_argument("--save-input", action="store_true", help="write the prepared input next to the candidates (no call)")
    g.add_argument("--dry-run", action="store_true")
    gr = sub.add_parser("grade")
    gr.add_argument("file")
    gr.add_argument("verdict", choices=["accept", "reject"])
    gr.add_argument("reason")
    ap.add_argument("--list-scenes", action="store_true")
    a = ap.parse_args()

    if a.list_scenes or a.cmd is None:
        for k, v in SCENES.items():
            print(f"{k:10s} {v['desc']}")
        return
    if a.cmd == "grade":
        C.grade(a.file, a.verdict, a.reason)
        print("graded", a.file, a.verdict)
        return

    view, tone, state = C.parse_tone_state(a.render)
    tone = a.tone or tone
    state = a.state or state
    im = prepare_input(a.render, a.crop, scene=a.scene, state=state, sketch=a.sketch)
    if a.save_input:
        C.CANDIDATES.mkdir(parents=True, exist_ok=True)
        p = C.CANDIDATES / f"_input-{a.scene}-{view}-{tone}-{state}{'-sketch' if a.sketch else ''}.png"
        im.save(p)
        print("input ->", p)
        if a.dry_run:
            return
    b64 = C.img_to_b64(im)
    prompt = build_prompt(a.scene, tone, state, a.extra)
    negative = NEGATIVES[a.neg]
    for extra_neg in (SCENES[a.scene].get("neg_extra", ""), a.negative_extra):
        if extra_neg:
            negative += ", " + extra_neg
    for s in [int(x) for x in a.seeds.split(",") if x.strip()]:
        body = {"prompt": prompt, "negative_prompt": negative, "image": b64,
                "control_strength": a.control, "output_format": "png", "seed": s}
        name = f"{a.scene}-{tone}-{state}-s{s}{('-' + a.tag) if a.tag else ''}.png"
        out = unique(C.CANDIDATES / name)
        note = f"v{PROMPT_VERSION} neg{a.neg} {view}{' sketch' if a.sketch else ''} cs={a.control} crop={a.crop} in={im.width}x{im.height}"
        C.invoke("structure", body, out, note=note, dry_run=a.dry_run)


if __name__ == "__main__":
    main()
