# tools/imagegen — render → AI lifestyle visualisation pipeline

Turns our own 3D renders (`renders-master/*.png`) into photoreal room visualisations of the GOREN
table with Amazon Bedrock (Stability AI image services, `us-east-1`, `us.stability.*` inference
profiles — the bare model ids fail with a ValidationException). Every Bedrock call is logged to
`<IMAGEGEN_DIR>/CALLS.jsonl` and counted against a hard cap (`common.BUDGET_CALLS`, env
`IMAGEGEN_BUDGET`, default 70); the cap is enforced in `common.invoke()`, failed calls count too.

**Paths (Sept 9, 2026):** the pipeline directory is env `IMAGEGEN_DIR`, default
`furniture/assets-src/product/imagegen/` (candidates/, final/, CALLS.jsonl under it). The rounds
below were run in `../night/imagegen/`; to rerun `round2.py`, `round3.py` or `encode.py` on those
files set `IMAGEGEN_DIR=../night/imagegen` (relative to furniture/) — the log there stays at 59/70.
The "goren-home-daylight" asset (design brief A3) lives in the new default dir with its own
`CALLS.jsonl` (`IMAGEGEN_BUDGET=24`), see `assets-src/product/HOME-SCENE-LOG.md`.

The product is frozen; the pipeline exists to put *that* table in a room, not to design a table.
An image is usable only if it passes the honesty gate (see `generate.py` docstring): oak A-frame
trestles in the same tone as the top, one slim matte-black steel beam under the top, 40 mm top
with an underside chamfer, no apron / stretcher / grommet / metal legs / extra parts, no people,
no text, no logos. Props are scene context only.

## Files

| file | role |
|---|---|
| `common.py` | paths, model ids, `invoke()` (Bedrock + log + cap), `grade()` |
| `generate.py` | `gen`: render → candidate via control-structure (scene prompts in `SCENES`); `grade`: accept/reject a candidate in the log |
| `edit.py` | Bedrock edits (`recolor`, `erase`, `replace`, `inpaint`, `upscale`, `upscale-fast`, `outpaint --up/--down`) and **local, call-free** steps: `mask`, `beam-mask`, `gapfix`, `beam-fix`, `darken`, `grade`, `clone` |
| `encode.py` | accepted finals (`<IMAGEGEN_DIR>/final/<id>.png`) → `site/assets/photos/<id>-{800,1200,1600}.webp/.avif` + `manifest.json` |
| `encode_product.py` | spec JSON → `site/assets/product/<id>-<w>.{avif,webp}` + `manifest-home.json` (the home-context asset; no alt/caption text, the page supplies it) |
| `round2.py` | the audit-round repair of `nook-white-closed` (four `clone_patch` steps, no calls); rebuilds that final from `candidates/nook-white-closed-FINAL-r1.png` |

## The recipe that works (Sept 2026)

1. **Base** — `generate.py gen --render renders-master/hero-natural-closed.png --scene apartment --seeds 16 --control 0.9 --sketch`
   Control 0.9 keeps the geometry exact (0.7 redesigns the legs). Seed 16 is the cleanest of the
   seeds tried. The model *always* paints the beam as oak and merges it with the gap above it into
   an apron flush under the top; the negatives cannot stop it. Sketched room hints are mostly
   ignored (a pendant lamp is the one that took).
2. **Beam** — `edit.py beam-fix BASE.png --render RENDER.png` (1 call): search-replace repaints
   the apron as steel, which is only used as a *mask* of what the model considers the beam; then
   `beam_composite()` registers the render's true beam to that region (horizontal search, then
   bottom-edge alignment), paints only the beam core matte black and fills the strip above it with
   the wall mirrored from below. Result: the slim beam with the gap under the top, like the render.
   `gapfix REPLACED --ref BASE --render R --bg INPAINTED` re-runs only the local step.
3. **Scene** — `edit.py mask BASE --poly ... --exclude-render RENDER --out M.png` then
   `edit.py inpaint BASE --mask M.png --prompt "..."` (1 call each). Masks that exclude the
   render's table silhouette never touch the product. Reliable: window, curtain, plant in a corner,
   bowl / fruit / vase / cups on the top. **Not** reliable: chairs or any furniture (two attempts
   produced nothing / repainted the floor).
4. **Order**: inpaint the *base*, then `gapfix` with `--bg` = the inpainted image, so the wall
   seen through the gap matches the new scene.
5. `edit.py grade` (warm/dark/vignette/lamp glow) for the evening scene; `edit.py clone` for the
   small notch the model leaves at the leaf seam in the open state.
6. `encode.py` after copying the final to `night/imagegen/final/<id>.png` and adding it to
   `FINALS` (Hebrew/English alt + caption, both saying it is a visualisation).

## Round 2 (audit, 2026-09-08)

Three of the eight round-1 finals were removed (both open-state kitchen images and the hero2
apartment view: composited beams that read as brackets / hanging grey bars) and `nook-white-closed`
was repaired locally; the manifest has 5 entries. Details and open issues in
`night/imagegen/REPORT.md` → "Round 2". `clone` grew `--feather` and `--match-rect` (scale the
source patch to the mean of a reference region) because a patch cloned from outside a shadow reads
as a pale ghost rectangle — the very defect the audit flagged.

## Gotchas

- Conservative upscale at 4x PNG exceeds Bedrock's 16 MB response cap → `--format jpeg` (default
  for the upscalers). At the site's 1600 px it adds nothing over the 2400 px master.
- `--from=-90,-4` (with `=`) for negative offsets in `clone`; argparse eats `-90` otherwise. Small
  patches need `--feather 2-4`: the feathered core is the rect inset by `feather`, so a 16 px rect with
  the default 6 barely applies.
- Check patches with a 4x nearest-neighbour crop with a coordinate grid drawn on it, not with a
  smooth downscale; the auditor looks at 1:1 and a blurred 3x crop hides ghost rectangles.
- Render vs candidate geometry differs by ~20 px at the legs even at control 0.9; a render-mask
  composite at identity registration cuts into the candidate's legs (the failed hero2 re-composite).
- search-recolor paints "black" as mid grey; inpaint with the beam mask *removes* the beam. Hence
  the local composite.
- Never call these images photographs on the page; `manifest.json` carries `kind: ai-visualisation`.
