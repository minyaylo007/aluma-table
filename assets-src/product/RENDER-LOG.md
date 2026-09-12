# Product render set — RENDER-LOG

Date: 2026-09-09. Output: `site/assets/product/` (84 WebP/AVIF variants + `manifest.json`), `site/assets/og.png`,
masters in `renders-master/product/` (gitignored; `<id>.png` at nominal size, `<id>.json` camera sidecar,
`ss2/<id>.png` the 2x frame, `_contact.png` contact sheet). Everything is a render/visualisation of the
PROVISIONAL procedural geometry in `site/assets/goren3d.js` (no manufacturer CAD) — never a photograph.
Ground: every master rendered with `--bg=f4f1ea` (the page ground); corners of all 60 ground-cornered variants
drift at most 2/255 after lossy encoding (limit 3).

## Pipeline

    node tools/render3d.js --product --ss=2        # 14 masters, 2x supersampled, ~130 s on SwiftShader
    node tools/make-og.js                          # og.png from the studio master
    python tools/product_assets.py                 # variants + manifest.json + _contact.png

## Harness changes

- `site/assets/goren3d.js` — VIEWS only, plus two small additions in `frame()`:
  - new views `studio`, `studioM`, `compare` (az/el fits) and `edge`, `frame` (explicit `eye`/`target` as functions of the box);
  - `frame()` gained an explicit-camera branch (`v.eye`) and an optional `shift` (fraction of the frame width, + = table moves left).
    Materials, geometry, lights and mount are untouched.
- `tools/render3d.html` — `&fit=open|closed` (build in the fit state, `Goren.frame` on those bounds, then `setState(<requested>)` + `relayoutShadows()`);
  per-view overrides `&az &el &fov &margin &lift &shift &eye &target`; `&key=x,y,z &ki=` (move the key), `&fill=` (shadowless
  directional fill from beside the camera); `window.__frame` now carries az/el/height/spec/key/fill.
- `tools/render3d.js` — `--product [idPrefix…]` with the fixed id table, `--ss=N` supersampling (Pillow LANCZOS downscale), `--q=` extra
  query, a JSON sidecar per id; the legacy view/tone/state mode is unchanged. Bug fixed on the way: option parsing split on every `=`.
- `tools/product_assets.py` — new encoder (LANCZOS, grain σ 0.5 per asset family, WebP 88/90, AVIF 64/62/60 speed 4, pixel checks,
  finish swatches from the 2x compare-closed frame, manifest, contact sheet).
- `tools/og.html` — self-contained (no dist/ sheet), ground `#F4F1EA`, ink `#252720`, secondary `#62645C`, IBM Plex Sans Hebrew
  self-hosted, the studio master, the inlined logo lockup, text only "גורן — שולחן אוכל נפתח" / "מ־160 ל־220 ס״מ". No price.

## Views — exact numbers

| view | az | el | fov_v | margin | lift | shift | fitted on | distance | camera height | table width (geometry >40) | width incl. cast-shadow tail (>6) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| studio (hero 2.2:1, 2400×1091) | 38 | 12.5 | 18.6 | 0.10 | −0.15 | 0.01 | closed | 3.752 m | **1.075 m** | 0.690 | 0.802 |
| studioM (hero-m 3:2, 2000×1333) | 38 | 12.5 | 27 | 0.255 | −0.16 | 0.03 | closed | 3.486 m | **1.010 m** | 0.743 | 0.864 |
| compare (3:2, 2400×1600) | 34 | 11 | 27 | 0.215 | −0.16 | 0.035 | **open** | 4.208 m | **1.058 m** | open 0.781 / closed 0.615 | open 0.883 / closed 0.717 |

Camera positions (m, from the sidecars): studio `[2.303, 1.075, 2.849]` → target `[0.048, 0.263, −0.037]`;
studioM `[2.183, 1.010, 2.614]` → `[0.088, 0.255, −0.069]`; compare `[2.454, 1.058, 3.328]` → `[0.144, 0.255, −0.097]`
(identical for all six compare renders — one fit on the open bounds, exposure 1.0, key `(−1.2, 4.4, 1.5)` × 2.4, HDRI, VSM r80).

Close-ups (closed state, three tones with the identical camera):

| view | eye (m) | target (m) | distance | fov_v | az / el | light |
|---|---|---|---|---|---|---|
| edge (1600²) | `[1.299, 0.905, 0.870]` = (max.x+0.50, HGT+0.155, max.z+0.42) | `[0.769, 0.730, 0.420]` | 0.717 m | 15 | 49.7° / 14.1° | key moved to `(−0.5, 1.75, 2.15)` × 2.2: raking across the top, the end face left to the HDRI |
| frame (1600×1200) | `[1.889, 0.550, 1.550]` = (fx+1.35, HGT−0.20, 1.55) | `[0.489, 0.450, 0.000]` | 2.091 m | 30 | 42.1° / 2.7° | default key + `fill=1.0` from beside the camera + floor bounce 0.9 |

Frame gaps measured on the masters (fraction of the frame; L/R/T/B): studio geometry 0.145/0.165/0.049/0.119, faint (shadow)
0.145/0.053/0.049/0.071; studioM geometry 0.098/0.160/0.170/0.221, faint 0.097/0.039/0.169/0.185; compare-open geometry
0.074/0.145/0.224/0.259, faint 0.073/0.043/0.223/0.237; compare-closed geometry 0.139/0.245/0.228/0.289, faint 0.139/0.145/0.228/0.269.
Ends, feet and the contact shadow are inside on every hero/compare master (all checks true, ≥ 1 % from every edge).

Finish swatches: 62 px square of the tabletop face at (1360, 397) of `goren-compare-<tone>-closed` (measured as the largest
square between the far and near arrises, which both rise to the right), cut from the 2x frame (124 px) → 160 / 240 px.
Same region, camera, light and exposure for the three tones.

## What was rejected and why

1. **First studio fit (margin 0.14, lift −0.03)** — on 2.2:1 the fit is bound *vertically*: from eye level the table's
   silhouette is ~1.8:1, so the camera landed at 4.5 m / 1.33 m high with the table 57 % wide. 80–86 % of the width would need
   >100 % of the height (the far top corner and the shadow under the near feet cannot both stay inside). Resolution: keep the
   50 mm lens and the eye-level camera (1.075 m), balance the top/bottom gaps with lift −0.15 (the near virtual AABB corner
   binds the fit, not the far real corner), and accept 69 % geometry / 80 % with the shadow tail. Lowering the camera to
   ~0.7 m would reach 80 % geometry but flattens the top into a sliver — not done.
2. **Compare / mobile first fits** — the key's cast-shadow tail (~0.28 m beyond the geometry at >6/255) touched the right edge
   (R gap 0). Fixed with larger margins (0.13→0.215, 0.18→0.255) and `shift` 0.03–0.035; the tail now ends 3.9–5.4 % from the edge.
3. **Edge view at 1.39 m** — a 15° lens looking along the top shows half the table (the top recedes into the frame); moved
   to 0.72 m so the corner is centred and the 40 mm section is ~20 % of the height.
4. **1x renders** — the 1.6 mm seam aliased into a dotted line on the top face and SwiftShader's arrises were stair-stepped
   (3x crops). All 14 masters were re-rendered with `--ss=2`; the seam is now a continuous hairline.
5. **Finish region** — three candidate squares (1560,620,150 / 1462,398,68 / 1504,396,62) hit the legs or the near lipping
   arris in a corner; the arris lines were then measured per column and the largest clean square fitted (1360,397,62).
6. `--q` option parsing (`el=10.5` became an empty `el` → 0° camera) — fixed before any master was rendered.

## Bytes (AVIF / WebP)

| id | widths | AVIF | WebP | budget |
|---|---|---|---|---|
| goren-studio-hero-natural-closed | 1200 / 1600 / 2000 | 10.8 / 16.0 / 22.6 KB | 24.1 / 41.6 / 59.4 KB | AVIF 2000 ≤ 250 KB ✓ |
| goren-studio-hero-m-natural-closed | 640 / 800 / 1000 | 4 / 6 / 8 KB | 8 / 11 / 19 KB | AVIF 1000 ≤ 150 KB ✓ |
| goren-compare-{natural,smoked,white}-{closed,open} | 800 / 1200 / 1600 | 3–5 / 5–9 / 7–14 KB | 5–10 / 11–22 / 17–36 KB | AVIF 1600 ≤ 200 KB ✓ (max 14 KB) |
| goren-edge-detail-{tone} | 640 / 1000 | 10–20 / 19–39 KB | 20–41 / 49–95 KB | — |
| goren-frame-detail-{tone} | 640 / 1000 | 4–7 / 7–15 KB | 7–14 / 17–36 KB | — |
| goren-finish-{tone} | 160 / 240 | ≤ 2 KB | ≤ 4 KB | — |
| og.png | 1200×630 | — | — (PNG, 138,904 B) | — |

Total encoded variants 1345 KB. AVIF q60 vs master at 2000 px: mean |Δ| 1.0 level, grain and arrises intact (3x crops).

## Limitations / notes for the page

- **Hero width.** The brief's 80–86 % is geometrically incompatible with 2.2:1 + 50 mm + eye-level camera + nothing cropped
  (see rejection 1). The manifest's `table_width_fraction` follows the brief's >6/255 definition (0.802 hero, 0.864 mobile,
  0.883/0.717 compare); the geometry-only widths are in each entry's `notes`.
- The key's cast shadow (0.12 wash) always trails to the right, so the geometry sits 1–3.5 % left of centre by design (`shift`)
  and the closed compare image sits left in the locked open frame.
- `ground_ok` is `null` for the edge close-ups (no image corner is flat ground: the top corners are wood, the bottom ones are in
  the cast shadow) and for the finish tiles (no ground). Frame close-ups: true (≤ 2/255).
- The finish tiles are a foreshortened region of the top (the compare camera is 11° above the plane), so the grain reads as
  fine streaks; 240 px is a 1.9x upscale of the 124 px 2x cut.
- SwiftShader: VSM shadows are soft but slightly noisy at the penumbra; 2x supersampling costs ~4x render time (8–15 s per master).
- `reference_version` is `goren3d.js 6bae08c+dirty` — the VIEWS used are not committed yet; the marker clears after a commit + re-run.
- `site/assets/product/` is shared with the imagegen engineer's `goren-home-daylight-*` variants and `manifest-home.json`;
  `manifest.json` lists only this set (18 entries: hero, hero-mobile, 6 compare, 3 edge, 3 frame, 3 finish, social).
