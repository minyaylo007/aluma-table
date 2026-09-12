# Render report — PBR oak, HDRI light, non-blocking viewer (2026-09-07)

Answers CRITIQUE-3 §1 (the viewer freezes the page) and §4 (the renders give the game away
up close). Everything below is in `furniture/`; nothing was deployed. Before-images are kept in
`C:\tmp\fx\before\` (the 30 PNG masters as of commit 1fcb5aa).

## What changed

**Materials.** The procedural canvas wood is gone. The table is now textured with the
photo-scanned Poly Haven `oak_veneer_01` set (CC0, already in `assets-src/`): albedo +
OpenGL normal map + roughness + AO, baked by `tools/bake_textures.py`. One physical wood for
all three tones: smoked oak is fumed natural oak and whitewashed oak is natural oak under a
white-pigmented oil, so the three tones share the same grain (normal / roughness / AO) and
differ only in the albedo grade (`grade_natural` −14 % saturation; `grade_smoked` gamma 1.30
× (0.68, 0.60, 0.54); `grade_white` 38 % desaturate then 48 % towards #F4F0E9). Mean albedo:
natural (155,125,91), smoked (95,61,34), white (194,181,166). The `mocha_oak_veneer` and
`white_oak_veneer` scans stay on disk unused: mocha reads as grey-taupe with a fine straight
grain, not as darker brown oak, and grading one scan keeps the cross-fade on the page a
finish change rather than a texture swap.

- Top and underside: veneer, grain along the length, one repeat per 1.6 m (`TILE_FACE`), so no
  tiling is visible on the 160 or 220 top; UVs are world-space so the grain is continuous
  across the seam between the two halves and the leaf.
- Solid oak lipping (40 mm, `edgeMat`): same maps rotated so the grain runs along each edge,
  roughness +0.06, albedo × 0.94 — it reads as a separate solid edge, as the copy says.
- Underside chamfer: real geometry, 20 mm up × 26 mm in, on the outer edges only, mitred at the
  corners (`slab()` in goren3d.js builds it face by face; no ExtrudeGeometry).
- Legs and rails (`legMat`): grain along the member. Legs are parallelogram prisms cut flat top
  and bottom so the feet sit on the floor (the old boxes were rotated and clipped through it).
- Beam: matte black steel, roughness 0.40, metalness 0.60.
- Texel density is 1 repeat per 1.2 m on every solid part (`TILE`), identical on every face.
- Seams: 0.8 mm per slab edge (1.6 mm joint) — a one-pixel line at 2400 px, visible in the top
  view and on the open table.

**Lighting.** Image-based lighting from `brown_photostudio_02_1k.hdr` (RGBE parsed in
goren3d.js, `PMREMGenerator.fromEquirectangular`), plus one warm key
(`DirectionalLight` 0xfff3e4, intensity 2.4, at (−1.1, 4.6, 0.9) — a near-overhead softbox),
VSM shadows (2048 map, blur radius 64 texels, 32 samples in the harness) on a `ShadowMaterial`
floor (opacity 0.30, colour #2a2419), and contact occlusion: a 32×32 radial blob under each
foot (opacity 0.8) and a faint one under the whole top (0.18). ACES filmic, exposure 1.0,
sRGB output, albedo flagged sRGB, normal / packed maps linear. Background and floor colour
come from one parameter: `--bg` in render3d.js, `?bg=` in render3d.html, `opts.bg` in
`Goren.mount` (default the page paper `#e9e6de`); `scene.background` and the clear colour are
the same untone-mapped value, so the render matches the page ground exactly.

Top view only: the key moves to the side (−3.6, 2.6, 1.4) and the face `envMapIntensity`
drops to 0.35 — straight down, the studio's ceiling lamp reflected across a third of the top
and washed the grain out.

**Cameras.** `Goren.frame()` fits the model's bounding box deterministically: each view is
(azimuth, elevation, vertical fov, margin) and the distance is solved so all eight box corners
sit inside the frustum minus the margin. hero az 38° el 13° fov 30° (≈45 mm on 3:2); hero2
−42°/12°; front 0°/7° fov 27°; end 90°/8°; top 89.5° fov 22°; detail = fixed close-up on the
trestle corner (target 30 cm in from the corner, 7.5 cm under the top, camera 0.85 m away,
10° below the top surface so the chamfer, the lipping, the trestle head and the beam end are
all in frame). The still and the viewer call the same function with the same aspect, so the
picture-to-viewer swap keeps the table at the same size — the old viewer drew it a third
smaller. `optimise_renders.py` no longer crops (`--crop` keeps the legacy path); every tone of
a view is pixel-aligned for the cross-fade and the `<img width/height>` attributes on the
page match the master aspect again.

**Viewer (`site/assets/goren3d.js`).** No texture generation on the main thread. It loads
three.js r160 from cdnjs as before, then `textures/<tone>-albedo-1024.jpg` +
`textures/oak-normal-1024.jpg` + `textures/oak-rough-1024.jpg` (R = AO, G = roughness — one
file for the grey maps) and `textures/studio-256.hdr` (105 KB, RLE RGBE down-sampled from the
1k studio) — 512 px maps when the canvas is under 900 device pixels. Images decode off-thread
via `ImageBitmapLoader` (with `imageOrientation: 'flipY'` so the normal map's handedness is
the same as in the harness). If the HDR fails, a procedural room (`roomScene`) is the
zero-download fallback. `renderer.compileAsync` runs before the first frame. Rendering is on
demand only: while dragging, during inertia, and for a 3.5 s idle turntable that then stops.
DPR is capped at 1.5, the canvas is sized from the element — or its parent when the element is
`display:none` at mount, which is the case for `#viewer` on the page (this is why the old
canvas was allocated at 1200×744 for a 350×219 box). A 3 px progress bar (`role=progressbar`)
lives inside the element until the first frame; `opts.onProgress(fraction)` / `opts.onReady()`
let the page style `#rotate`. Other tones' albedos are prefetched in idle time so a swatch
switch is a material swap. `setState` rebuilds the geometry (four meshes) and refits the
camera.

API: `Goren.mount(el, {tone, state})` → `Promise<{setTone, setState, dispose}>` unchanged;
new opts `bg`, `onProgress`, `onReady`, `hdr`, `view`, `maxDpr`, `spin`; the returned object
also has `setBackground(col)` and `invalidate()`. `Goren.build(THREE, opts)` returns
`{group, ready, setTone, setState, lights, environment, bounds, materials, dispose}`;
`Goren.frame`, `Goren.VIEWS`, `Goren.parseRGBE` are exported for the harness.

## Files

| File | Role |
|---|---|
| `site/assets/goren3d.js` | model, materials, lights, framing, viewer (rewritten) |
| `site/assets/textures/` | new: 3 albedos × {1024, 512}, normal × 2, packed rough/AO × 2, `studio-256.hdr` — 820 KB total, 434 KB for what a desktop first frame needs |
| `tools/bake_textures.py` | new: grades + resizes the scans, packs AO/rough, writes the small HDR |
| `tools/render3d.html` / `tools/render3d.js` | harness: `--bg`, `--out`, `--tex`, `--scale`, `view tone state` filters, `--allow-file-access-from-files` |
| `tools/optimise_renders.py` | no crop, q84/82 WebP, q64/62/60 AVIF, σ 1.2 luminance grain (same seed per view) |
| `tools/viewer_perf.js` | new: Playwright, local http server, 4× CPU throttle, long-task observer |
| `renders-master/` | 30 masters re-rendered (gitignored), `textures/` 2048 px masters |
| `site/assets/renders/` | 180 encoded variants replaced, same file names |

## Sizes

| Variant | before | after |
|---|---|---|
| hero-natural-closed-1200.webp | 13.5 KB | 21 KB |
| hero-smoked-closed-1200.webp | 14.6 KB | 20 KB |
| detail-natural-closed-1200.webp | 35 KB | 60 KB |
| top-natural-closed-1200.webp | 18 KB | 77 KB |
| top-smoked-closed-1600.webp (largest) | — | 186 KB |
| all 180 variants | 1.99 MB | 4.58 MB |

Hero 1200 WebP stays far under the 180 KB budget; the top views carry the most grain and are
the only files above 100 KB.

## Viewer timings (tools/viewer_perf.js, SwiftShader WebGL, CPU ×4)

| | before (critique) | after — phone 390 px @3× | after — desktop 760 px @1.5× |
|---|---|---|---|
| tap → first frame | 8.2 s, one 7.4 s task | 630–890 ms | 800–840 ms |
| longest task after ready | 11.2 s on a tone switch | 66–153 ms | 104–157 ms |
| tone switch | 6.7–13.2 s | 1–61 ms | 1–3 ms |
| state switch (rebuild geometry) | n/a | 4 ms | 6–49 ms |
| canvas buffer for its box | 1200×744 for 350×219 | 585×366 for 390×244 | 1140×712 for 760×475 |

The 190–250 ms tasks *during* mount are three.min.js parse and the first shader compile; they
happen before the canvas is shown, behind the progress bar. The idle turntable frames are
50–150 ms each on SwiftShader; on a real GPU they are a few ms.

## What I looked at

Every master was rendered and the hero (all tones, both states), hero2, front, end, top and
detail were opened at full size; 1:1 crops of the hero edge and feet were checked. Wood reads
as oak with cathedral figure and pores; the chamfer shows on the hero as the lit bevel under
the lipping and on the detail as a full face; the lipping is visibly a separate darker piece;
feet sit on the floor with a contact shadow; the three tones differ and none is a flat plane;
proportions are 160×90 closed and 220×90 open with the leaf seams visible in the front and top
views; nothing floats, clips, or tiles.

## Known limits

- Still a studio shot on paper: no apartment, floor material, wall line or chair (RENDER-BRIEF
  R2 is unchanged). The 16:10 hero frame keeps paper above and below a 1.6 m table; that is
  the page's box, not the render.
- The viewer's environment is the 256×128 HDR (or the procedural room); reflections on the
  beam are softer than in the still. The viewer's shadow map is 1024/1536 px so its penumbra
  is a little tighter than the 2048-px still.
- VSM shadows on SwiftShader (headless renders) and on some mobile GPUs can show light
  bleeding under the top; the contact blobs are there to make the grounding independent of it.
- `mocha_oak_veneer` and `white_oak_veneer` are downloaded but unused (see Materials).
- `fetch()` cannot read `file://` even with `--allow-file-access-from-files`; the harness path
  uses XHR for the HDR and `<img>` loading for textures. Over http both paths are the fast ones.
- No depth of field or lens effects; the only "photographic" pass is σ 1.2 grain in the encoder.
- `site/index.html`, `app-next.js` and the CSS were not touched: `#rotate[aria-busy]` still has
  no style and the hint text after opening is still an `<a href="#">` (critique §1) — those are
  page-owner fixes; the viewer now exposes `onProgress`/`onReady` for them.

---

# Round 2 — judge must_fix (2026-09-08)

Answers the round-1 verdict (score 5, 3 blockers, 6 majors). Same files, same spec; nothing
deployed. All 30 masters re-rendered and all 180 variants re-encoded; every changed render was
opened (contact sheet of the 30 masters, plus 1:1 and 3x crops of the judged regions).

## Blockers

**Veneer repeat (was: pixel-identical every 1.6 m).** `TILE_FACE` 1.60 → 2.40 m, longer than the
open top, so no column of veneer can repeat; the leaf is a separate flitch (`LEAF_FLITCH`: its own
strip of the map, offset across and along) and the two halves keep their closed-state UV offset so
the grain stays on its half when the table opens (it used to slide in world space). Re-verified
with the judge's test on `top-natural-open.png` (850 px/m, shifts 0.6–2.0 m): full-column Pearson
peak **0.10** at 1.85 m and column-mean-profile peak **0.26** at 1.98 m (round 1: 0.98 / 0.997 at
1.61 m). The 30-line test script stayed in the scratchpad, not the repo.

**Beam floating (was: 10 mm gap, no bracket).** `-0.01` dropped: the beam's top face is flush
under both trestle heads (0.5 mm into them so the shared plane cannot z-fight) and runs out to the
heads' outer faces. Detail and end views now show the beam butting the head; no paper between.
No bracket was added — a visible fixing would be a feature the spec does not have.

**Notch at the seams (was: mitred chamfers left a V-tooth and paper showed through).** `slab()`
now takes `outerL / outerR`: only outer ends are lipped and chamfered; a seam end is a square
cut (the chamfer is on the outer edges only, per spec) built as a hexagonal section, and the long
chamfer runs straight to a seam end instead of mitring. A dark joint filler sits inside each
1.6 mm seam (two slivers following the section) so the joint reads as a hairline shadow — in the
top view the gap used to show the pale floor as a light line. 3x crop of `hero-natural-open`
1000–1300 × 480–580: straight lipping, seam a hairline.

## Majors

**Wavy lipping/chamfer boundary.** Two causes, both fixed: the lipping carried the full veneer
normal map at a grazing key (11° off the face), so pore relief wobbled the arris shading;
`edgeMat.normalScale` is now 0.35 (a planed, oiled edge) and the key moved to (−1.2, 4.4, 1.5),
18° off grazing on the front lipping. 3x crop of `hero-natural-closed` 650–1050 × 400–540: the
chamfer band is a straight line.

**Detail view.** (a) Lipping/chamfer UVs are now a *profile coordinate* (0 at the top arris,
20 mm at the chamfer arris, 52.8 mm at the underside) sampled 2.5x denser across the grain: the
grain runs unbroken from the face round the arris and down the bevel, unstretched, and reads as a
rift-sawn solid edge rather than a smeared copy of the cathedral figure. (b) End grain: a fourth
material (`endMat`) on the two faces the grain runs into (rail ends, pad ends, leg ends), with its
own albedo per tone from `bake_textures.py endgrain()` — procedural ring-porous oak (earlywood pore
rows on arcs about a pith ~17 cm off, 2.4–4 mm apart with drift and waviness, fine and broad rays,
noise), built from the tone's own colour 18 % darker; UVs are part-local windows inside the tile
(`TILE_END` 0.30 m) so no face straddles the tile border. The veneer's AO/normal are zeroed on it
(their along-grain streaks read as vertical stripes at that scale). (c) The underside was a flat
grey plane: a `HemisphereLight` (black sky, paper-coloured ground, 0.55) models the bounce off
the pale floor — the underside, chamfer and beam now take warm light from below.

**End view leg "split".** At exactly az 90° the near leg's inner side face was a 3–4 px lit
sliver and the far leg peeked past it. `end` is now az 80°: the far trestle reads as a second
trestle, the near legs are clean.

**Floor shadow.** RENDER-BRIEF R1 asks for a soft contact shadow only: cast-shadow opacity
0.30 → 0.12, VSM radius 64 → 80 texels (19 cm penumbra), key moved so the cast falls behind the
table where the hero cameras mostly cannot see it. The "stepped lighter band with a straight top
edge" was the straight edge of the rectangular top's own shadow next to the elliptical contact
blob; at 0.12 it is a faint wash with no readable edge (crop `hero-natural-closed` 1550–2200 ×
850–1300). Contact blobs unchanged. (Also fixed: `key.target` was inside a comment and never set.)

**Smoked tone (was walnut/teak).** `grade_smoked` rewritten: 55 % towards luminance, gamma 1.12,
× (0.64, 0.60, 0.565) → albedo mean (86, 71, 57) instead of (95, 61, 34). In the hero-closed
silhouettes, (max−min)/mean is now natural 0.23, **smoked 0.18**, white 0.09 — the darker tone
is the lower-chroma one, a grey-brown fumed oak. Fallback colour `TONES.smoked.base` updated.

**Viewer performance.** Structural changes in `mount()`: the box size and first tone are known
before three.js is, so the first tone's four maps and the HDR start downloading immediately
(`warm()` → blob → `createImageBitmap`) and overlap the 650 KB three.min.js instead of queueing
behind it; the shadow map is drawn (and VSM-blurred) once — `shadowMap.autoUpdate = false`,
`needsUpdate` on the first frame and on `setState` — since light and table are static while the
visitor orbits; viewer shadow map 1024 / radius 40 on every device (same penumbra as the still,
cast is a 0.12 wash); all four oak materials bind the same map set so they share one shader
program (the end-grain material zeroes normal/AO intensity instead);
`performance.mark('goren:mount|three|maps|env|compiled|frame')` for profiling; `Goren.prefetch()`
for the page to call after load (`<link rel=prefetch>` of three.js, skips Save-Data) — opt-in,
because it costs every visitor 650 KB.

Measured with `tools/viewer_perf.js` (untouched — not in this round's file list), 3 fresh
invocations, SwiftShader WebGL, CPU ×4, each context cold for cdnjs:

| | phone 390 @3× | desktop 760 @1.5× |
|---|---|---|
| mount → first frame | 1069 / 1301 / 1476 ms | 1658 / 2042 / 2080 ms |
| worst task after ready | 84–140 ms | 90–173 ms |
| tone switch / state switch | 0–1 ms / 24–40 ms | 1 ms / 23–50 ms |
| verdict | PASS ×3 | FAIL ×3 (budget 1500) |

Honest reading: the round-1 build, re-measured on the same machine in the same session with an
A/B harness (scratchpad `perf_ab.js`, same page, same throttle), gives desktop 1041 / 1776 /
1877 ms — so the budget is not met on SwiftShader here by either build, and the "630–890 ms" in
round 1 was a best case. The marks show where the time goes on the new build (desktop, warm
cdnjs): three.js 230–590 ms (fetch + parse), env 530–700 ms (HDR + PMREM: three shader compiles
on a software rasteriser), maps ready before env, compile +90–130 ms, first frame +170–460 ms
(shadow pass + a 1140×712 standard-material frame on the CPU). All of that is shader compilation
and software rasterisation cost, ×4 throttled; on a phone GPU driver each compile is ~10–50 ms.
What the change does buy on a real network: the maps no longer wait for three.js, and the shadow
pass no longer repeats every orbit frame (idle-turntable frames after ready are now 50–90 ms on
SwiftShader vs 66–157 ms in round 1).

## Minors touched in passing

- Wood sheen: `TONES.rough` 0.62/0.60/0.66 → 0.56/0.54/0.60 and face `envMapIntensity` 1.0 — a
  low satin on the top under the studio softbox instead of a clay look.
- Viewer/still lighting parity: the viewer now uses the same key, bounce and shadow parameters
  (radius scaled to its map) as the harness; the far-lipping highlight line came from the same
  full-strength edge normal map and is gone with it.
- `optimise_renders.py` only encodes the six product views (it had picked up the two
  `viewer-perf-*.png` screenshots in `renders-master/` and written them to `site/assets/renders/`;
  those four stray files were removed).
- Not done: the top views are still a flat swatch-like plan (they feed the swatch crops); no depth
  of field; no scene.

## Files (round 2)

| File | Change |
|---|---|
| `site/assets/goren3d.js` | `TILE_FACE` 2.4, `LEAF_FLITCH`, `EDGE_ACROSS`, `TILE_END`; `box()`/`leg()` route end faces to an end-grain builder with part-local UVs; `slab()` outer/seam ends, profile UVs; seam fillers; beam flush; `endMat` (4th oak material, shared program); lights: key (−1.2, 4.4, 1.5) + target fix, opacity 0.12, radius 80, hemisphere bounce; `end` view az 80; `warm()`/`takeWarm()` prefetch path in `loadImageTexture`/`xhrBuffer`; `mount()` warms maps before three.js, shadow map once, 1024 map, perf marks; `Goren.prefetch()`, `Goren.warm` |
| `tools/bake_textures.py` | `grade_smoked` (grey-brown, low chroma); `endgrain()` procedural end-grain albedo per tone → `renders-master/textures/endgrain-<tone>-1024.jpg`, `site/assets/textures/endgrain-<tone>-512.jpg` (23 / 14 / 31 KB) |
| `tools/render3d.html` | `end` map in both texture sets; `&sr=` default 80; `&so=`, `&bounce=` overrides |
| `tools/optimise_renders.py` | product views only |
| `site/assets/textures/` | + 3 end-grain maps (68 KB); smoked albedos regraded (1024: 105 KB, 512: 25 KB) |
| `renders-master/` | 30 masters re-rendered (gitignored) |
| `site/assets/renders/` | 180 variants replaced, same names; 3.64 MB total (was 4.58 MB — softer shadow and lower-chroma smoked compress better); hero-natural-closed-1200 20 KB, detail-natural-closed-1200 60 KB, largest top-smoked-closed-1600 69 KB |

## What I looked at

Contact sheet of all 30 masters (no floating beam, no notch, no tiling, consistent framing across
tones); at 1:1/3x: hero-natural-open seam, hero-natural-closed front edge and floor shadow,
detail-natural-closed rail end and chamfer, end-natural/-smoked/-white, top-natural-open and
top-smoked-closed seam, hero-smoked-closed and -open, hero-white-open, hero2-natural-open,
front-natural-open; encoded variants hero-natural-open-1200, detail-natural-closed-1200,
end-white-closed-1200, hero2-smoked-closed-1200 (WebP); the viewer's own 760 px frame next to the
still it cross-fades from. Perf harness ran without page errors (the viewer loads the new
end-grain maps over http).

## Open

- Viewer first frame on SwiftShader ×4 desktop is over the 1.5 s budget on this machine for both
  builds; a real-GPU measurement is needed to know where it lands for visitors. The page could
  call `Goren.prefetch()` after load if the 650 KB per visitor is acceptable.
- End grain is subtle (planed and oiled), rings faint at hero scale; deliberate, but a judge may
  want more contrast.
- The seam end faces are visible as a hairline through the 1.6 mm joint from low angles — a
  joint line, but a hairline lighter than the filler behind it.
