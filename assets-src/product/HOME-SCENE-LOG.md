# goren-home-daylight — home-context visualisation (asset A3), log

Date: 2026-09-09. Pipeline: `tools/imagegen/` with `IMAGEGEN_DIR` = `assets-src/product/imagegen/`
(new default) and `IMAGEGEN_BUDGET=24`. Log: `assets-src/product/imagegen/CALLS.jsonl`.
Finals: `assets-src/product/imagegen/final/` → encoded by `tools/imagegen/encode_product.py` to
`site/assets/product/goren-home-daylight-*` and `goren-home-daylight-m-*` + `manifest-home.json`.

## Budget

| | calls | est. USD |
|---|---|---|
| control-structure seeds 16 / 31 / 32 (scene `daylight`, control 0.9, sketch) | 3 | 0.30 |
| beam-fix step 1 (search-replace, mask source only) | 1 | 0.10 |
| inpaint: window ×2 (both rejected), cup ×1 | 3 | 0.30 |
| outpaint: desktop 3:2 (down 100), mobile 4:5 (up 330 / down 420) | 2 | 0.20 |
| **total** | **9 / 24** | **≈ 0.90** |

15 calls unspent. No failed calls. Rate: every call 19–77 s.

## What was made

**Desktop `goren-home-daylight`** — 2400×1600, exactly 3:2 (the pipeline's native 2400×1500 = 8:5
master plus 100 px of outpainted floor at the bottom). Table = 1741 px of 2400 = **72.5 %** of the
frame width. Widths 800 / 1200 / 1600, AVIF + WebP (1600 AVIF 60 KB, WebP 67 KB).

**Mobile `goren-home-daylight-m`** — 1600×2000, exactly 4:5. Crop of the 8:5 master at
x 279..2200 (table extent 369..2110 from the render silhouette + ~5 % margin each side), full
height, scaled to 1600×1249, outpainted **vertically only** (wall 330 px above, floor 420 px below),
the crop pasted back byte-identical, one floor row edge-extended to reach 2000. The complete table
(both ends, all four feet) is inside; table = **90.6 %** of the width. Widths 640 / 800 / 1080.

Both are `kind: ai-visualisation`, `status: provisional`, no alt/caption text in the manifest.

## Calls, seeds, verdicts (CALLS.jsonl)

| # | model | seed | verdict | why |
|---|---|---|---|---|
| 1 | control-structure | 16 | **accept (base)** | off-white speckled plaster wall, pale honed stone floor, legs oak in the top's tone, geometry exact; beam painted as an oak apron flush under the top (expected, → beam-fix); a faint veneer tone boundary at x≈1080 and a light sheen streak at ≈1120,410 on the top; the usual dark notch at the near-left leg top |
| 2 | control-structure | 31 | reject | flat grey studio backdrop, no wall/floor; two leaf-seam lines across the closed top |
| 3 | control-structure | 32 | reject | flat grey studio backdrop; one leaf-seam line across the closed top |
| 4 | search-replace | 1 | accept (intermediate) | apron repainted as a steel plate with bolt heads — used only as the apron mask for the local beam composite; none of its pixels reach the final |
| 5 | inpaint (window, mask x 30–330) | 1 | reject | painted a narrow oak-framed frosted panel hung on the wall: reads as a mirror/cabinet, not a window; the oak frame competes with the product |
| 6 | inpaint (window, mask x 0–340 to the floor line) | 2 | reject | painted a blown-out white doorway/void with a plaster wall return, not a window |
| 7 | inpaint (cup, ellipse 130×110 at 1390,370) | 1 | **accept** | one white coffee cup ≈100 px (≈9 cm) on the far half of the top, soft shadow, away from edges |
| 8 | outpaint (desktop, down 100) | 1 | **accept** | 100 px of floor below the master; a straight slab joint at the seam, +5 lum step → tone-matched locally |
| 9 | outpaint (mobile, up 330 / down 420) | 1 | **accept** | wall above / floor below the crop; floor step +12 lum → tone-matched; generated floor smoother than the veined original |

After #6 the room was **simplified to the plain plaster wall** (brief: "if the tool cannot preserve
the product, simplify the room rather than accept drift" — here the tool could not produce a
credible window at the frame edge either). Daylight from camera-left is carried by the render's
key light on the product and the floor gradient, not by a visible window. **No chairs** (the
inpaint model could not add furniture in the previous round; zero chairs is within the brief).

### Prompts

Structure (scene `daylight`, `generate.py SCENES`, product sentence unchanged = the honesty gate):
> …; photographed in a calm contemporary apartment dining area: smooth off-white lime plaster
> walls, a pale honed stone floor with a fine light terrazzo speckle, neutral soft daylight falling
> from a large window on the left just out of frame, quiet, minimal and uncluttered, bare walls, an
> empty clean table top, camera at about 1.15 m height; realistic interior photograph, 50 mm lens
> at seated eye level, natural colours, soft shadows, matte oil-waxed wood with visible oak grain,
> no gloss

Negative = v2 + `neg_extra`: olive tree, lemons, fruit, arch, arches, travertine, villa, rustic,
ornament, decoration, clutter, rug, carpet, plant, flowers, wood floor, plank floor, knot, stain,
mark on the table top. Structure input = the render with the "apartment" sketch hints (floor line +
left window block) so seed 16 keeps the geometry that passed the gate in the previous round; the
window hint was ignored again (as documented in the README).

Cup (#7): "one small plain white ceramic coffee cup standing on the light oak table top, soft
neutral daylight from the left, a small soft shadow beside it, realistic photograph" / negative
"huge mug, bowl, plate, saucer, two cups, hole, grommet, text, logo, people, blurry".

Outpaint (#8, #9, creativity 0.35): "the same room continues: smooth off-white plaster wall above,
pale honed stone floor with a fine light speckle below, neutral soft daylight from the left, empty
and calm, nothing else in the room".

## Local (call-free) steps — reproducible

`python assets-src/product/imagegen/assemble_home.py` → `final/goren-home-daylight-1500.png`:
1. cup region (ellipse mask dilated 12 px, feathered) merged onto the structure base; every other
   pixel — product included — stays the base's (the inpaint model also nudges up to ~9 k pixels
   outside its mask, measured on #5/#6, so the merge is masked, not whole-image);
2. `edit.beam_composite(replaced=#4, base=#1, render, bg=scene)` — the render's slim beam registered
   to the apron (dx 0, dy −12, bottom-align +21), painted matte black, apron remainder filled with
   wall from below;
3. `round3.measure/apply` — beam edges fitted as lines (height 43 px at x 800, render 45), beam
   extended to the near-left leg's edge (x 763.5) and anti-aliased at 4×, fill boundary
   straightened, gap strip darkened with `GAP_SHADE = (0.70, 0.88)` (round-3 default 0.82–0.95 left
   the pale strip JUDGE-2 flagged; strip now 0.79 of the wall below the beam, was 0.89);
4. three `clone` patches: leg side face notch (736,478,24×48 ← 50 px lower), near-edge notch at
   x≈1078 (← 26 px right), sheen streak on the top (1095,402,75×22 ← 28 px lower).

`python assets-src/product/imagegen/extend_home.py prep-mobile | paste-desktop | paste-mobile | tone-match`
— crop/scale for the mobile input, paste the originals back over the outpaint outputs (feather
12 px only at the new strips), per-column tone match of the generated floor strips (fade to 60 % at
the frame edge), 1-row pad. Verified: desktop rows 0..1487 and the mobile crop region (minus the
feather) are **byte-identical** to the approved master.

## Honesty gate — final verdict: PASS (provisional)

Checked at 2400 px, at 1:1 and 3×/4× grid crops of the beam ends, both leg tops, the near edge and
the top surface, and at the delivery sizes (1600 desktop, 1080 mobile).

- **Trestles**: solid oak, same light natural tone as the top, square section, A-frame, four feet
  on the floor with contact shadows. No metal, no paint.
- **Beam**: exactly one, slim, matte black (mean rgb 27/27/28; render 13/13/13), under the top with
  the gap above it, running from behind the near-left leg to the near-right leg, with the far end
  visible between the right trestle's legs as in the render. Height 43 px at x 800 (render 45).
  Nothing else between the trestles.
- **Top**: 40 mm read, underside chamfer band visible along the near edge, no grommet, hole, apron,
  stretcher, fixings or leaf seam (the closed top shows only a soft veneer tone boundary near
  x≈1080, no line).
- **Seams**: beam/leg junction has no wall sliver (lum 54 → 41 → 28 across one pixel); the beam
  edges are 1-px anti-aliased stairs at 3× (invisible at 1600).
- **Chairs**: 0. **Cup**: 1, on the far half of the top, clear of edges.
- **Floor**: pale honed stone / polished concrete with veining and large slab joints; generated
  strips (desktop bottom 100 px, mobile bottom 420 px) are smoother and meet the original at a
  straight joint that reads as a slab joint after the tone match.
- **Wall**: off-white speckled lime plaster; the mobile's generated wall above y≈330 is smoother
  than the original.
- **No** people, text, logos, villa, arches, olive tree, travertine, clutter.
- The image corner is a room (wall/floor), not the page ground: expected for a home context.

## Remaining defects (recorded, not hidden)

1. The wall seen through the gap above the beam is a mirrored fill, darkened to 0.70–0.88 of the
   wall below; at 1600 it reads as a thin light-grey strip between top and beam (physically the
   wall through the gap, as in the render).
2. Beam edges: anti-aliased polygon, 1-px stairs at 3×.
3. Desktop / mobile floor: a straight full-width slab joint exactly at the outpaint seam; the
   generated slab is smoother than the veined original (visible at 1:1, not at 800).
4. Mobile wall above y≈330: smoother than the speckled original (texture change, Δ lum ≈ 1).
5. Cup shadow is faint and slightly to the left of the cup while the key light is from the left
   (the inpaint model's choice; minor).
6. No window / no chairs: the "home" reading rests on the plaster, the stone floor and the cup.

## Files

- `tools/imagegen/common.py` — `IMAGEGEN_DIR` / `IMAGEGEN_BUDGET` (default 70); `BASE` (alias `NIGHT`).
- `tools/imagegen/generate.py` — scene `daylight` (+ `neg_extra` per scene), sketch hints shared with `apartment`.
- `tools/imagegen/edit.py` — `outpaint IMG --up N --down N [--prompt] [--seed] [--outpaint-creativity]`.
- `tools/imagegen/encode_product.py` — spec → `site/assets/product/` + `manifest-home.json`.
- `tools/imagegen/README.md` — paths note, table rows.
- `assets-src/product/imagegen/{CALLS.jsonl, candidates/, final/, assemble_home.py, extend_home.py}`.
- `site/assets/product/goren-home-daylight-{800,1200,1600}.{avif,webp}`, `goren-home-daylight-m-{640,800,1080}.{avif,webp}`, `manifest-home.json`.

Note for the repo: `.gitignore` ignores `assets-src/*.png` only at the top level, so the ~60 MB of
candidate PNGs under `assets-src/product/imagegen/candidates/` would be tracked; consider adding
that directory (the finals + spec + scripts are enough to re-encode; the candidates are needed only
to rerun `assemble_home.py`).
