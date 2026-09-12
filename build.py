#!/usr/bin/env python3
"""Render furniture/site/ -> furniture/dist/.

    python build.py                 preview build (missing owner facts become visible markers)
    python build.py --production    refuses to build while a required owner fact or asset is missing

Jobs:
  1. substitute {{TOKENS}} from content.json and {{t.key}} strings from i18n/<loc>.json, so every
     name, number and sentence lives in exactly one place and the English twin is the same template;
  2. draw the technical drawings from the SAME numbers (1 SVG unit = 1 cm, non-scaling strokes);
  3. read the product asset manifest (site/assets/product/manifest*.json) and emit every <picture>,
     preload and the JS asset map from it — the page never references a file by convention;
  4. publish only what is referenced (explicit inventory), content-hash every asset filename and
     rewrite the references, so immutable caching is honest and HTML stays revalidating;
  5. print a readiness report: preview vs production.

No dependencies beyond the standard library; Pillow is used only to read legacy image sizes.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).parent
SITE = ROOT / "site"
DIST = ROOT / "dist"
I18N = ROOT / "i18n"
PRODUCT = SITE / "assets" / "product"
RENDERS = SITE / "assets" / "renders"
EDITORIAL = SITE / "assets" / "editorial"

PRODUCTION = "--production" in sys.argv

# --------------------------------------------------------------------------- facts (one source)
CONTENT = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
L_CLOSED = float(CONTENT["LEN_CLOSED"])
L_LEAF = float(CONTENT["LEAF_CM"])
L_OPEN = float(CONTENT["LEN_OPEN"])
W = float(CONTENT["WIDTH"])
H = float(CONTENT["HEIGHT"])
TOP_T = float(CONTENT["TOP_MM"]) / 10.0
SEATS_CLOSED = int(CONTENT["SEATS_CLOSED"])
SEATS_OPEN = int(CONTENT["SEATS_OPEN"])
assert abs(L_CLOSED + L_LEAF - L_OPEN) < 1e-6, "content.json: LEN_CLOSED + LEAF_CM must equal LEN_OPEN"
# drawing-only geometry, provisional (goren3d.js spec; no manufacturer drawing exists)
FRAME_INSET = 26.0    # A-frame centre, measured from the end of the closed top
FOOT_W = 60.0         # foot spread across the width
STOCK_X = 7.5         # trestle stock along the length
SLIDE = L_LEAF / 2    # each half moves 30 cm outward when the table opens

PAPER = "#f4f1ea"     # page ground = render ground


def fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def path(*pts) -> str:
    head = f"M{fmt(pts[0][0])} {fmt(pts[0][1])}"
    rest = "".join(f"L{fmt(x)} {fmt(y)}" for x, y in pts[1:])
    return head + rest + "Z"


NS = 'vector-effect="non-scaling-stroke"'


def overlay(items, vw: float, vh: float, cls_base: str = "dim-num") -> str:
    """Dimension numerals / labels as HTML positioned over the drawing: real text in the page font,
    readable on every screen. Percentages, physical left/top — drawings never mirror."""
    out = []
    for x, y, text, cls in items:
        out.append(f'<span class="{cls_base} {cls}" style="left:{x / vw * 100:.2f}%;top:{y / vh * 100:.2f}%">{text}</span>')
    return "".join(out)


def grid_defs(uid: str) -> str:
    return (f'<defs><pattern id="grid{uid}" width="10" height="10" patternUnits="userSpaceOnUse">'
            f'<path class="gridline" d="M10 0H0V10" fill="none" {NS}/></pattern></defs>')


# --------------------------------------------------------------------------- elevation


def elevation_svg() -> str:
    """Front view on a 10 cm grid. The two halves slide outward and the leaf, drawn dashed inside
    the closed table (hidden-line convention), rises into the gap and turns solid."""
    vw, vh = 260.0, 100.0
    base = 80.0
    top_y = base - H
    cx = vw / 2
    half = L_CLOSED / 2
    frame_cx = L_CLOSED / 2 - FRAME_INSET
    rail, foot, thick = 34.0, 56.0, 5.0
    leg_top = top_y + TOP_T
    ch = 1.6

    def a_frame(sign: int) -> str:
        c = cx + sign * frame_cx
        outline = path(
            (c - rail / 2, leg_top), (c + rail / 2, leg_top),
            (c + foot / 2, base), (c + foot / 2 - thick, base),
            (c + rail / 2 - thick, leg_top + thick),
            (c - rail / 2 + thick, leg_top + thick),
            (c - foot / 2 + thick, base), (c - foot / 2, base),
        )
        return f'<path class="oak-leg" d="{outline}" {NS}/>'

    def slab(x0: float, x1: float, chamfer_left: bool, chamfer_right: bool) -> str:
        bl = x0 + (ch if chamfer_left else 0)
        br = x1 - (ch if chamfer_right else 0)
        yb = top_y + TOP_T
        d = path((x0, top_y), (x1, top_y), (x1, yb - (ch if chamfer_right else 0)),
                 (br, yb), (bl, yb), (x0, yb - (ch if chamfer_left else 0)))
        return f'<path class="oak-top" d="{d}" {NS}/>'

    beam_h, beam_y = 9.0, leg_top + 6.0
    leaf_hidden_y = top_y + TOP_T + 1.0
    dim_y = base + 12.0

    def dim_line(length_cm: float, cls: str) -> str:
        w = length_cm / 2
        return (
            f'<g class="dim {cls}">'
            f'<line x1="{fmt(cx - w)}" y1="{fmt(dim_y)}" x2="{fmt(cx + w)}" y2="{fmt(dim_y)}" {NS}/>'
            f'<path d="M{fmt(cx - w + 3)} {fmt(dim_y - 1.6)}L{fmt(cx - w)} {fmt(dim_y)}L{fmt(cx - w + 3)} {fmt(dim_y + 1.6)}" {NS}/>'
            f'<path d="M{fmt(cx + w - 3)} {fmt(dim_y - 1.6)}L{fmt(cx + w)} {fmt(dim_y)}L{fmt(cx + w - 3)} {fmt(dim_y + 1.6)}" {NS}/>'
            f'<line x1="{fmt(cx - w)}" y1="{fmt(dim_y - 3)}" x2="{fmt(cx - w)}" y2="{fmt(dim_y + 3)}" {NS}/>'
            f'<line x1="{fmt(cx + w)}" y1="{fmt(dim_y - 3)}" x2="{fmt(cx + w)}" y2="{fmt(dim_y + 3)}" {NS}/>'
            "</g>"
        )

    svg = f'''<svg class="draw draw--elev" viewBox="0 0 {fmt(vw)} {fmt(vh)}" role="img"
     aria-labelledby="elevTitle elevDesc" preserveAspectRatio="xMidYMid meet">
  <title id="elevTitle">{{{{t.draw_elev_t}}}}</title>
  <desc id="elevDesc">{{{{t.draw_elev_d}}}}</desc>
  {grid_defs("E")}
  <rect class="gridfill" x="0" y="0" width="{fmt(vw)}" height="{fmt(base)}" fill="url(#gridE)"/>
  <g class="slide-r">{a_frame(-1)}</g>
  <g class="slide-l">{a_frame(1)}</g>
  <g class="beam-grp"><rect class="steel" x="{fmt(cx - frame_cx)}" y="{fmt(beam_y)}"
     width="{fmt(frame_cx * 2)}" height="{fmt(beam_h)}"/></g>
  <g class="leaf-grp"><rect class="leaf" x="{fmt(cx - L_LEAF / 2)}" y="{fmt(leaf_hidden_y)}" width="{fmt(L_LEAF)}" height="{fmt(TOP_T)}" {NS}/></g>
  <g class="slide-r">{slab(cx - half, cx, True, False)}</g>
  <g class="slide-l">{slab(cx, cx + half, False, True)}</g>
  <line class="floor" x1="10" y1="{fmt(base)}" x2="{fmt(vw - 10)}" y2="{fmt(base)}" {NS}/>
  {dim_line(L_CLOSED, "only-160")}
  {dim_line(L_OPEN, "only-220")}
  <g class="dim"><line x1="{fmt(vw - 12)}" y1="{fmt(top_y)}" x2="{fmt(vw - 12)}" y2="{fmt(base)}" {NS}/><path d="M{fmt(vw - 13.6)} {fmt(top_y + 3)}L{fmt(vw - 12)} {fmt(top_y)}L{fmt(vw - 10.4)} {fmt(top_y + 3)}" {NS}/><path d="M{fmt(vw - 13.6)} {fmt(base - 3)}L{fmt(vw - 12)} {fmt(base)}L{fmt(vw - 10.4)} {fmt(base - 3)}" {NS}/><line x1="{fmt(vw - 15)}" y1="{fmt(top_y)}" x2="{fmt(vw - 9)}" y2="{fmt(top_y)}" {NS}/></g>
</svg>'''
    nums = overlay([(cx, dim_y, f'<span id="dim-len" data-bind="len">{fmt(L_CLOSED)}</span>', "dim-num--mid"),
                    (vw - 12, base - H / 2, fmt(H), "dim-num--side")], vw, vh)
    return f'<div class="draw-wrap draw-wrap--elev">{svg}{nums}</div>'


# --------------------------------------------------------------------------- plan


def chair(cx_: float, cy: float, rot: int) -> str:
    w, d = 44.0, 42.0
    back_t = 5.0
    seat_w, seat_d = 40.0, 34.0
    return (
        f'<g class="chair" transform="translate({fmt(cx_)} {fmt(cy)}) rotate({rot})">'
        f'<rect class="chair-back" x="{fmt(-w/2)}" y="{fmt(-d/2)}" width="{fmt(w)}" height="{fmt(back_t)}"/>'
        f'<rect class="chair-seat" x="{fmt(-seat_w/2)}" y="{fmt(-d/2 + back_t + 2)}" width="{fmt(seat_w)}" height="{fmt(seat_d)}" {NS}/>'
        "</g>"
    )


def plan_svg() -> str:
    """Top view, to scale, with illustrative chairs and the trestle footprints."""
    hw = W / 2
    gap = 13.0
    chair_d = 42.0  # глибина стільця; ширина на кресленні не потрібна
    vw = L_OPEN + 2 * (gap + chair_d) + 14
    vh = 2 * (hw + gap + chair_d) + 14
    cx, cy = vw / 2, vh / 2
    chair_off = hw + gap + chair_d / 2

    def side_chairs(length_cm: float, per_side: int) -> str:
        step = length_cm / per_side
        out = []
        for i in range(per_side):
            x = cx - length_cm / 2 + step * (i + 0.5)
            out.append(chair(x, cy - chair_off, 0))
            out.append(chair(x, cy + chair_off, 180))
        return "".join(out)

    def end_chairs(length_cm: float) -> str:
        off = length_cm / 2 + gap + chair_d / 2
        return chair(cx - off, cy, 90) + chair(cx + off, cy, 270)

    half = L_CLOSED / 2
    per_side_closed = SEATS_CLOSED // 2
    per_side_open = (SEATS_OPEN - 2) // 2

    def slab(x0: float, x1: float) -> str:
        return (f'<rect class="oak-top" x="{fmt(x0)}" y="{fmt(cy - hw)}" '
                f'width="{fmt(x1 - x0)}" height="{fmt(hw * 2)}" {NS}/>')

    def foot(sign: int) -> str:
        x = cx + sign * (L_CLOSED / 2 - FRAME_INSET)
        return (f'<rect class="foot-print" x="{fmt(x - STOCK_X / 2)}" y="{fmt(cy - FOOT_W / 2)}" '
                f'width="{fmt(STOCK_X)}" height="{fmt(FOOT_W)}" {NS}/>')

    return f'''<svg class="draw draw--plan" viewBox="0 0 {fmt(vw)} {fmt(vh)}" role="img"
     aria-labelledby="planTitle planDesc" preserveAspectRatio="xMidYMid meet">
  <title id="planTitle">{{{{t.draw_plan_t}}}}</title>
  <desc id="planDesc">{{{{t.draw_plan_d}}}}</desc>
  <g class="only-160">{side_chairs(L_CLOSED, per_side_closed)}</g>
  <g class="only-220">{side_chairs(L_OPEN, per_side_open)}{end_chairs(L_OPEN)}</g>
  <g class="leaf-grp"><rect class="leaf leaf--plan" x="{fmt(cx - L_LEAF / 2)}" y="{fmt(cy - hw)}" width="{fmt(L_LEAF)}" height="{fmt(hw * 2)}" {NS}/></g>
  <g class="slide-r">{slab(cx - half, cx + 0.5)}{foot(-1)}</g>
  <g class="slide-l">{slab(cx - 0.5, cx + half)}{foot(1)}</g>
</svg>'''


# --------------------------------------------------------------------------- edge section (labelled diagram)


def edge_svg() -> str:
    """Schematic section through the edge of the top, 1 unit = 1 mm, with HTML labels: plywood core,
    oak veneer on both faces, the solid-oak lip with its underside chamfer. Labelled as schematic."""
    vw, vh = 400.0, 110.0
    y0, y1 = 34.0, 74.0        # the 40 mm top sits between y0 and y1
    lip = 40.0
    svg = f'''<svg class="draw draw--edge" viewBox="0 0 {fmt(vw)} {fmt(vh)}" role="img"
     aria-labelledby="edgeTitle edgeDesc" preserveAspectRatio="xMidYMid meet">
  <title id="edgeTitle">{{{{t.dg_title}}}}</title>
  <desc id="edgeDesc">{{{{t.dg_desc}}}}</desc>
  <path class="oak-face-fill" d="M0 {fmt(y0)}H{fmt(vw)}V{fmt(y1)}H0Z"/>
  <rect class="ply" x="{fmt(lip)}" y="{fmt(y0 + 4)}" width="{fmt(vw - lip)}" height="32"/>
  <g class="grain">
    <line x1="{fmt(lip)}" y1="{fmt(y0 + 9)}" x2="{fmt(vw)}" y2="{fmt(y0 + 9)}" {NS}/><line x1="{fmt(lip)}" y1="{fmt(y0 + 14)}" x2="{fmt(vw)}" y2="{fmt(y0 + 14)}" {NS}/>
    <line x1="{fmt(lip)}" y1="{fmt(y0 + 19)}" x2="{fmt(vw)}" y2="{fmt(y0 + 19)}" {NS}/><line x1="{fmt(lip)}" y1="{fmt(y0 + 24)}" x2="{fmt(vw)}" y2="{fmt(y0 + 24)}" {NS}/>
    <line x1="{fmt(lip)}" y1="{fmt(y0 + 29)}" x2="{fmt(vw)}" y2="{fmt(y0 + 29)}" {NS}/>
  </g>
  <path class="lip" d="M0 {fmt(y0)}H{fmt(lip)}V{fmt(y1)}H16L0 {fmt(y1 - 14)}Z" {NS}/>
  <line class="veneer" x1="{fmt(lip)}" y1="{fmt(y0 + 3)}" x2="{fmt(vw)}" y2="{fmt(y0 + 3)}" {NS}/>
  <line class="veneer" x1="{fmt(lip)}" y1="{fmt(y1 - 3)}" x2="{fmt(vw)}" y2="{fmt(y1 - 3)}" {NS}/>
  <path class="dg-line" d="M230 {fmt(y0 + 3)}V18" {NS}/>
  <path class="dg-line" d="M24 {fmt(y0)}V18" {NS}/>
  <path class="dg-line" d="M10 {fmt(y1 - 8)}V92" {NS}/>
</svg>'''
    labels = overlay([
        (230, 12, "{{t.dg_veneer}}", ""),
        (230, 55, "{{t.dg_core}}", ""),
        (64, 12, "{{t.dg_lip}}", ""),
        (52, 98, "{{t.dg_chamfer}}", ""),
    ], vw, vh, cls_base="dg-label")
    return f'<div class="draw-wrap draw-wrap--edge">{svg}{labels}<p class="dg-title">{{{{t.dg_title}}}}</p></div>'


# --------------------------------------------------------------------------- logo lockups


def svg_paths(file: pathlib.Path) -> dict:
    text = file.read_text(encoding="utf-8")
    return dict(re.findall(r'<path id="([\w-]+)" d="([^"]+)"', text))


def lockup(file: pathlib.Path, ids: list, viewbox: str, cls: str, title: str, uid: str) -> str:
    paths = svg_paths(file)
    body = "".join(f'<path d="{paths[i]}"/>' for i in ids if i in paths)
    return (f'<svg class="{cls}" viewBox="{viewbox}" role="img" aria-labelledby="{uid}" fill="currentColor" '
            f'preserveAspectRatio="xMidYMid meet"><title id="{uid}">{title}</title>{body}</svg>')


def logo_tokens() -> dict:
    """One lockup per placement: the same wordmark appears in the masthead and in the footer, and an
    SVG <title id> must be unique on the page."""
    a = SITE / "assets"
    spec = {
        "he": (a / "logo.svg", ["wordmark-he", "mark"], "0 -740 3703 740", "logo logo--he", "אלומה"),
        "en": (a / "logo-en.svg", ["mark", "wordmark-en", "wordmark-he"], "0 -740 4496 1334", "logo logo--en", "ALUMA אלומה"),
    }
    out = {}
    for loc, (f, ids, vb, cls, title) in spec.items():
        out[loc] = {"logo": lockup(f, ids, vb, cls, title, "logoTitle"),
                    "logo_foot": lockup(f, ids, vb, cls, title, "logoTitleFoot")}
    return out


# --------------------------------------------------------------------------- product asset manifest

WIDTHS_LEGACY = (800, 1200, 1600)
FALLBACKS_USED: list = []
PROVISIONAL: list = []


def image_size(f: pathlib.Path, default=(2400, 1500)) -> tuple:
    try:
        from PIL import Image
        with Image.open(f) as im:
            return im.size
    except Exception:
        return default


def load_manifest() -> dict:
    """id -> asset. Every manifest*.json in site/assets/product/ is merged (the render set and the
    home scene are produced by different pipelines and write separate files)."""
    assets = {}
    if not PRODUCT.is_dir():
        return assets
    for f in sorted(PRODUCT.glob("manifest*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  warning: {f.name} unreadable ({e}); skipped")
            continue
        for a in data.get("assets", []):
            aid = a.get("id")
            if not aid:
                continue
            files = a.get("files") or {}
            ok = all((PRODUCT / v["path"]).exists() for m in files.values() for v in m.values())
            if not files or not ok:
                print(f"  warning: manifest asset {aid} lists missing files; ignored")
                continue
            a["base"] = "/assets/product/"
            assets[aid] = a
            if a.get("status") != "verified":
                PROVISIONAL.append(aid)
    return assets


def legacy_asset(aid: str, stem: str, folder: pathlib.Path, base: str, widths=WIDTHS_LEGACY) -> dict | None:
    files = {"avif": {}, "webp": {}}
    for w in widths:
        for ext in ("avif", "webp"):
            f = folder / f"{stem}-{w}.{ext}"
            if f.exists():
                files[ext][str(w)] = {"path": f.name, "bytes": f.stat().st_size}
    if not files["webp"]:
        return None
    biggest = max(int(k) for k in files["webp"])
    wpx, hpx = image_size(folder / f"{stem}-{biggest}.webp")
    return {"id": aid, "width": wpx, "height": hpx, "files": files, "base": base, "status": "fallback-legacy", "source": f"{folder.relative_to(ROOT).as_posix()}/{stem}-*"}


def asset(assets: dict, aid: str, fallback: tuple | None) -> dict | None:
    a = assets.get(aid)
    if a:
        return a
    if fallback:
        stem, folder, base = fallback
        la = legacy_asset(aid, stem, folder, base)
        if la:
            FALLBACKS_USED.append(f"{aid} <- {folder.relative_to(ROOT).as_posix()}/{stem}")
            return la
    return None


def srcset(a: dict, ext: str) -> str:
    m = (a.get("files") or {}).get(ext) or {}
    return ", ".join(f"{a['base']}{v['path']} {w}w" for w, v in sorted(m.items(), key=lambda kv: int(kv[0])))


def pick(a: dict, ext: str, prefer: int) -> str:
    m = (a.get("files") or {}).get(ext) or {}
    if not m:
        return ""
    ws = sorted(int(w) for w in m)
    w = prefer if prefer in ws else max(x for x in ws if x <= prefer) if any(x <= prefer for x in ws) else ws[0]
    return a["base"] + m[str(w)]["path"]


def picture(a: dict, alt: str, sizes: str, *, mobile: dict | None = None, mobile_sizes: str = "100vw",
            pic_id: str = "", img_id: str = "", loading: str = "lazy", fetchpriority: str = "", prefer: int = 1200) -> str:
    """<picture> from a manifest asset: AVIF then WebP, optional art-directed mobile asset first."""
    def sources(x: dict, sz: str, media: str = "") -> str:
        out = []
        for ext in ("avif", "webp"):
            ss = srcset(x, ext)
            if ss:
                out.append(f'<source{media} type="image/{ext}" srcset="{ss}" sizes="{sz}" width="{x["width"]}" height="{x["height"]}">')
        return "".join(out)
    parts = [f'<picture{" id=" + chr(34) + pic_id + chr(34) if pic_id else ""}>']
    if mobile:
        parts.append(sources(mobile, mobile_sizes, f' media="{HERO_MEDIA_M}"'))
    parts.append(sources(a, sizes))
    attrs = [f'src="{pick(a, "webp", prefer)}"', f'width="{a["width"]}"', f'height="{a["height"]}"', f'alt="{alt}"', 'decoding="async"']
    if img_id:
        attrs.insert(0, f'id="{img_id}"')
    if loading:
        attrs.append(f'loading="{loading}"')
    if fetchpriority:
        attrs.append(f'fetchpriority="{fetchpriority}"')
    parts.append(f'<img {" ".join(attrs)}>')
    parts.append("</picture>")
    return "".join(parts)


def preload(a: dict, sizes: str, media: str) -> str:
    ss = srcset(a, "avif") or srcset(a, "webp")
    typ = "image/avif" if srcset(a, "avif") else "image/webp"
    return f'<link rel="preload" as="image" type="{typ}" media="{media}" imagesrcset="{ss}" imagesizes="{sizes}" fetchpriority="high">'


def finish_img(assets: dict, tone_: str) -> str:
    a = assets.get(f"goren-finish-{tone_}")
    if a:
        ss = srcset(a, "webp")
        return (f'<img class="finish-img" src="{pick(a, "webp", 160)}" srcset="{ss}" sizes="{FINISH_SIZES}" '
                f'width="{a["width"]}" height="{a["height"]}" alt="" loading="lazy" decoding="async">')
    f = RENDERS / f"top-{tone_}-closed-800.webp"
    if f.exists():
        FALLBACKS_USED.append(f"goren-finish-{tone_} <- renders/top-{tone_}-closed-800 (css crop)")
        return f'<img class="finish-img finish-img--legacy" src="/assets/renders/{f.name}" width="800" height="560" alt="" loading="lazy" decoding="async">'
    return '<span class="finish-img" aria-hidden="true"></span>'


# --------------------------------------------------------------------------- build


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:10]


# The build must not depend on the OS it runs on. Text-mode writes turn "\n" into "\r\n" on Windows,
# and a Windows checkout (core.autocrlf) hands copytree CRLF sources — prod of 09.09 was built there
# and differed from a Linux build in every page and in every CSS/JS/SVG content hash. So every text
# file is written with an explicit LF and UTF-8, and copied text sources are normalised to LF.
TEXT_SUFFIXES = (".html", ".css", ".js", ".svg", ".xml", ".txt", ".webmanifest", ".json")


def write_text_lf(f: pathlib.Path, text: str) -> None:
    f.write_text(text, encoding="utf-8", newline="\n")


def normalise_eol(root: pathlib.Path) -> None:
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES:
            data = f.read_bytes()
            if b"\r" in data:
                f.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def load_locales() -> dict:
    locales = {}
    for f in sorted(I18N.glob("*.json")):
        locales[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    base = set(locales.get("he", {}))
    for name, strings in locales.items():
        missing = base - set(strings)
        extra = set(strings) - base
        if missing:
            raise SystemExit(f"i18n/{name}.json is missing keys: {sorted(missing)[:8]}")
        if extra:
            raise SystemExit(f"i18n/{name}.json has keys he.json lacks: {sorted(extra)[:8]}")
    return locales


def render_faq(items: list) -> str:
    return "".join(
        f'<details><summary>{it["q"]}</summary><div class="answer"><p>{it["a"]}</p></div></details>'
        for it in items
    )


# Fields only the owner can supply. Rendered as a visible marker in the reader's own language:
# inventing a company is worse, a raw {{TOKEN}} is worse still, and --production refuses to build.
OWNER_FIELDS = {
    "COMPANY_NAME": ("שם העוסק — להשלמה", "operator name — to be supplied"),
    "COMPANY_ID": ("מס׳ עוסק — להשלמה", "registration number — to be supplied"),
    "ADDRESS": ("כתובת — להשלמה", "address — to be supplied"),
    "CONTACT_EMAIL": ("כתובת דוא״ל — להשלמה", "e-mail — to be supplied"),
    "PHONE": ("טלפון — להשלמה", "phone — to be supplied"),
    "ACCESSIBILITY_CONTACT": ("שם האחראי — להשלמה", "accessibility contact — to be supplied"),
    "COURT_CITY": ("עיר — להשלמה", "city — to be supplied"),
}

JS_KEYS = ("f_name", "f_phone", "e_name", "e_phone", "e_phone_invalid", "e_consent", "e_consent_short", "s_missing",
           "s_sending", "s_invalid", "s_offline", "wa_prefill", "f_note", "thanks_href", "cmp_alt",
           "fit_hint", "fit_hint_bad", "fit_open_ok", "fit_open_exact", "fit_open_no",
           "fit_closed_ok", "fit_closed_exact", "fit_closed_no", "fit_bar_alt", "gallery_title")

# These must describe what the stylesheet actually renders: --stage and --gut are the CSS tokens.
STAGE_PX = 1120          # styles-next.css --stage
GUT_MAX = 64             # styles-next.css --gut upper clamp
HERO_SIZES = f"(min-width: {STAGE_PX}px) {STAGE_PX}px, 100vw"
COMPARE_SIZES = "(min-width: 62rem) min(1000px, calc(100vw - 2 * 64px - 48px - 26vw)), calc(100vw - 2 * 20px)"
HOME_SIZES = f"(min-width: {STAGE_PX + 2 * GUT_MAX}px) {STAGE_PX}px, calc(100vw - 2 * clamp(20px, 4.4vw, {GUT_MAX}px))"
EDGE_SIZES = "(min-width: 62rem) 40vw, calc(100vw - 40px)"
FRAME_SIZES = "(min-width: 62rem) 52vw, calc(100vw - 40px)"
FINISH_SIZES = "(min-width: 62rem) 96px, min(120px, calc((100vw - 2 * 20px - 28px) / 3))"
# one breakpoint for the art-directed hero, written as a range so the two halves partition exactly
HERO_MEDIA_M = "(width < 48rem)"
HERO_MEDIA_D = "(width >= 48rem)"


def main() -> None:
    content = CONTENT
    locales = load_locales()
    if DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)
    shutil.copytree(SITE, DIST, dirs_exist_ok=True)

    LOCALISED = {"index.html": "index.html", "thanks.html": "thanks.html", "404.html": "404.html"}
    for loc in locales:
        if loc == "he":
            continue
        (DIST / loc).mkdir(exist_ok=True)
        for src, dst in LOCALISED.items():
            if (SITE / src).exists():
                shutil.copyfile(SITE / src, DIST / loc / dst)
    normalise_eol(DIST)

    tokens = dict(content)
    tokens["PLAN_SVG"] = plan_svg()
    tokens["ELEVATION_SVG"] = elevation_svg()
    tokens["EDGE_SVG"] = edge_svg()

    # ---- product assets from the manifest (legacy renders as a labelled fallback in preview)
    assets = load_manifest()
    hero = asset(assets, "goren-studio-hero-natural-closed", ("hero-natural-closed", RENDERS, "/assets/renders/"))
    hero_m = asset(assets, "goren-studio-hero-m-natural-closed", None) or hero
    compare = {}
    for t in ("natural", "smoked", "white"):
        for s in ("closed", "open"):
            compare[(t, s)] = asset(assets, f"goren-compare-{t}-{s}", (f"hero-{t}-{s}", RENDERS, "/assets/renders/"))
    home = asset(assets, "goren-home-daylight", ("goren-daylight", EDITORIAL, "/assets/editorial/"))
    home_m = asset(assets, "goren-home-daylight-m", None) or home
    edge = asset(assets, "goren-edge-detail-natural", ("detail-natural-closed", RENDERS, "/assets/renders/"))
    frame = asset(assets, "goren-frame-detail-natural", ("detail-natural-closed", RENDERS, "/assets/renders/"))
    if not (hero and compare[("natural", "closed")] and home and edge and frame):
        raise SystemExit("product assets missing and no legacy fallback available; run the render pipeline")

    def L(loc: str, key: str) -> str:   # a locale string as a token placeholder, resolved in the t pass
        return "{{t." + key + "}}"

    tokens["HERO_PRELOAD"] = (preload(hero_m, "100vw", HERO_MEDIA_M) + "\n" +
                              preload(hero, HERO_SIZES, HERO_MEDIA_D))
    tokens["PIC_HERO"] = picture(hero, "{{t.hero_alt}}", HERO_SIZES, mobile=hero_m if hero_m is not hero else None,
                                 img_id="hero-img", loading="eager", fetchpriority="high", prefer=1600)
    cmp0 = compare[("natural", "closed")]
    tokens["PIC_COMPARE"] = picture(cmp0, "{{t.cmp_alt_default}}", COMPARE_SIZES, pic_id="compare-pic", img_id="compare-img", loading="lazy")
    tokens["COMPARE_W"], tokens["COMPARE_H"] = str(cmp0["width"]), str(cmp0["height"])
    tokens["PIC_HOME"] = picture(home, "{{t.home_alt}}", HOME_SIZES, mobile=home_m if home_m is not home else None, mobile_sizes="100vw")
    tokens["PIC_EDGE"] = picture(edge, "{{t.mat_edge_alt}}", EDGE_SIZES, prefer=1000)
    tokens["PIC_FRAME"] = picture(frame, "{{t.mat_frame_alt}}", FRAME_SIZES, prefer=1000)
    for t in ("natural", "smoked", "white"):
        tokens[f"FINISH_{t.upper()}"] = finish_img(assets, t)
    tokens["JSONLD_IMAGE"] = pick(hero, "webp", 1600)
    tokens["CSS_V"] = tokens["JS_V"] = "hashed"

    wa = (content.get("WA_NUMBER") or "").strip()
    tokens["WA_HIDDEN"] = "" if wa else " hidden"
    tokens["WA_CLASS"] = "" if wa else " is-off"
    tokens["NO_WA_CLASS"] = " is-off" if wa else ""

    company = str(content.get("COMPANY_NAME", "")).strip()
    tokens["SELLER_JSONLD"] = (',"seller":{"@type":"Organization","name":' + json.dumps(company, ensure_ascii=False) + "}") if company else ""

    unfilled = [k for k in OWNER_FIELDS if not str(content.get(k, "")).strip()]
    owner_markers = {
        loc: {k: f'<span class="todo">{OWNER_FIELDS[k][0 if loc == "he" else 1]}</span>' for k in unfilled}
        for loc in locales
    }

    logos = logo_tokens()
    missing = set()

    def js_assets() -> dict:
        out = {}
        for (t, s), a in compare.items():
            if not a:
                continue
            out[f"goren-compare-{t}-{s}"] = {
                "w": a["width"], "h": a["height"],
                "avif": {w: a["base"] + v["path"] for w, v in (a["files"].get("avif") or {}).items()},
                "webp": {w: a["base"] + v["path"] for w, v in (a["files"].get("webp") or {}).items()},
            }
        return out

    def js_strings(strings: dict, loc: str) -> str:
        blob = {k: strings.get(k, "") for k in JS_KEYS}
        blob["s_rate"] = strings.get("s_rate_wa" if wa else "s_rate", "")
        blob["s_fail"] = strings.get("s_fail_wa" if wa else "s_fail", "")
        blob["toneLong"] = {"natural": strings.get("tone_natural_long"), "smoked": strings.get("tone_smoked_long"), "white": strings.get("tone_white_long")}
        blob["stateWord"] = {"closed": strings.get("state_closed"), "open": strings.get("state_open")}
        blob["sizes"] = {content["LEN_CLOSED"]: "closed", content["LEN_OPEN"]: "open"}
        blob["lenClosed"], blob["lenOpen"] = content["LEN_CLOSED"], content["LEN_OPEN"]
        blob["assets"] = js_assets()
        blob["cfg"] = {"wa": wa, "pixel": content.get("META_PIXEL_ID", ""),
                       "clarity": content.get("CLARITY_ID", ""), "brand": content["BRAND_HE"],
                       "model": content["MODEL_HE"], "price": int(content["PRICE_PLAIN"]),
                       "consentVersion": content.get("CONSENT_VERSION", "v1"), "ground": PAPER, "lang": loc}
        return json.dumps(blob, ensure_ascii=False)

    def render(text: str, strings: dict, loc: str) -> str:
        def sub(m):
            key = m.group(1)
            marked = owner_markers.get(loc, owner_markers["he"])
            if key in marked:
                return marked[key]
            if key not in tokens:
                missing.add(key)
                return ""
            return str(tokens[key])

        def sub_t(m):
            key = m.group(1)
            if key == "faq" and isinstance(strings.get("faq"), list):
                return render_faq(strings["faq"])
            if key == "js_strings":
                return js_strings(strings, loc)
            if key == "cmp_alt_default":
                return (strings.get("cmp_alt", "").replace("{{tone}}", strings.get("tone_natural_long", ""))
                        .replace("{{state}}", strings.get("state_closed", "")).replace("{{len}}", content["LEN_CLOSED"]))
            if key in logos.get(loc, logos["he"]):
                return logos.get(loc, logos["he"])[key]
            if key not in strings:
                missing.add("t." + key)
                return ""
            return str(strings[key])

        text = re.sub(r"\{\{([A-Z][A-Z0-9_]*)\}\}", sub, text)
        text = re.sub(r"\{\{t\.(\w+)\}\}", sub_t, text)
        text = re.sub(r"\{\{t\.(\w+)\}\}", sub_t, text)
        return re.sub(r"\{\{([A-Z][A-Z0-9_]*)\}\}", sub, text)

    for f in sorted(DIST.rglob("*")):
        if not f.is_file():
            continue
        if f.name.startswith("_"):
            f.unlink()
            continue
        if f.suffix.lower() in (".html", ".css", ".js", ".webmanifest", ".xml", ".txt"):
            rel = f.relative_to(DIST)
            loc = rel.parts[0] if len(rel.parts) > 1 and rel.parts[0] in locales else "he"
            text = f.read_text(encoding="utf-8")
            if f.name == "styles-next.css":
                text = text.replace('@import "/assets/fonts/fonts.css";', (SITE / "assets" / "fonts" / "fonts.css").read_text(encoding="utf-8"))
            write_text_lf(f, render(text, locales[loc], loc))

    if missing:
        raise SystemExit(f"unknown tokens in templates: {sorted(missing)}")

    # ---- publication inventory: only what the rendered pages and the sheet reference
    REF = re.compile(r"/assets/[\w\-./]+?\.(?:avif|webp|png|jpg|svg|woff2|css|js)")
    # Seed with the documents a visitor can actually reach, then follow references transitively: a
    # stylesheet nobody links to must not keep its own dependencies alive in the publication set.
    frontier = [f for f in DIST.rglob("*") if f.is_file() and f.suffix.lower() in (".html", ".xml", ".txt", ".webmanifest")]
    referenced, seen = set(), set()
    while frontier:
        f = frontier.pop()
        if f in seen or not f.is_file():
            continue
        seen.add(f)
        for ref in REF.findall(f.read_text(encoding="utf-8")):
            referenced.add(ref)
            target = DIST / ref.lstrip("/")
            if target.suffix.lower() in (".css", ".js") and target.exists():
                frontier.append(target)
    absent = sorted(p for p in referenced if not (DIST / p.lstrip("/")).exists())
    if absent:
        raise SystemExit(f"referenced assets missing from site/: {absent[:10]}")
    removed = 0
    for f in sorted((DIST / "assets").rglob("*")):
        if f.is_file() and ("/" + f.relative_to(DIST).as_posix()) not in referenced:
            f.unlink(); removed += 1
    for d in sorted((DIST / "assets").rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()

    # ---- content-hashed filenames, rewritten everywhere (leaf assets, then the sheet, then the script)
    def current_text_files() -> list:
        return [f for f in DIST.rglob("*") if f.is_file() and f.suffix.lower() in (".html", ".css", ".js")]

    def rewrite_all(old: str, new: str) -> None:
        pat = re.compile(re.escape(old) + r"(?![\w.\-/])")
        for f in current_text_files():
            t = f.read_text(encoding="utf-8")
            if old in t:
                write_text_lf(f, pat.sub(new, t))

    hashed = {}
    files_now = sorted(f for f in (DIST / "assets").rglob("*") if f.is_file())
    order = [f for f in files_now if f.suffix not in (".css", ".js")] + [f for f in files_now if f.suffix == ".css"] + [f for f in files_now if f.suffix == ".js"]
    for f in order:
        h = digest_bytes(f.read_bytes())
        new = f.with_name(f"{f.stem}.{h}{f.suffix}")
        f.rename(new)
        old_url = "/" + f.relative_to(DIST).as_posix()
        new_url = "/" + new.relative_to(DIST).as_posix()
        hashed[old_url] = new_url
        rewrite_all(old_url, new_url)

    shutil.copyfile(DIST / "index.html", DIST / "next")
    for d in [DIST] + [DIST / loc for loc in locales if (DIST / loc).is_dir()]:
        for name in ("privacy", "terms", "accessibility", "thanks", "404", "next"):
            src = d / f"{name}.html"
            if src.exists():
                shutil.copyfile(src, d / name)

    (ROOT / ".build").mkdir(exist_ok=True)
    write_text_lf(ROOT / ".build" / "asset-map.json", json.dumps(hashed, indent=1))   # build record, not published

    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"built {DIST}  ({total/1024:.0f} KB, {sum(1 for f in DIST.rglob('*') if f.is_file())} files; {len(hashed)} hashed assets, {removed} unreferenced source files not published)")
    print(f"  hero {hero['width']}x{hero['height']} ({'manifest' if hero.get('base') == '/assets/product/' else 'FALLBACK'}); compare {cmp0['width']}x{cmp0['height']}; home {home['width']}x{home['height']}")

    # ---- readiness
    print("readiness:")
    if FALLBACKS_USED:
        print("  ASSETS ON LEGACY FALLBACK (preview only):")
        for x in FALLBACKS_USED:
            print(f"    - {x}")
    if PROVISIONAL:
        print(f"  provisional (unverified against a physical unit) product assets in use: {len(PROVISIONAL)}")
    if not wa:
        print("  WA_NUMBER empty -> every WhatsApp control is hidden, the callback button carries the page (optional)")
    if unfilled:
        print("  OWNER MUST SUPPLY (rendered as a visible 'להשלמה' marker):")
        for k in unfilled:
            print(f"    - {k} ({OWNER_FIELDS[k][1].split(' — ')[0]})")
    blockers = [f"owner field {k}" for k in unfilled] + [f"legacy fallback: {x}" for x in FALLBACKS_USED]
    if PRODUCTION and blockers:
        # leave nothing behind for a naive `build; upload` sequence to pick up
        shutil.rmtree(DIST, ignore_errors=True)
        raise SystemExit("NOT PRODUCTION-READY (dist/ removed):\n  " + "\n  ".join(blockers))
    print("  status: " + ("production build" if PRODUCTION else "PREVIEW build (not launch-ready while blockers remain)" if blockers else "preview build, no blockers found by the build"))


if __name__ == "__main__":
    main()
