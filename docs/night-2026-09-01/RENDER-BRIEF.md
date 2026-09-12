# Render brief — the seven images that replace the drawings

> **Updated 2 Sep, 12:30.** R1 (hero, three tones, closed and open), R4 (twin state), R7 (leg
> and beam detail) and a top/front/end set now exist as **3D renders from a parametric model**
> (`furniture/site/assets/goren3d.js`, rendered by `tools/render3d.js`). They are on the live
> page. What this brief still asks for: **R3, the macro of real oiled oak** (a procedural texture
> cannot honestly stand in for a photograph of the surface), **R6, real cartons** (must be a
> photograph), and **R2, the apartment context** — and, eventually, photographs of the first
> built table to replace every render.

The site is finished and honest without photographs: every image on it is a hand-authored
technical drawing, dimensionally true, and the terms of use say so in plain Hebrew.
These seven renders replace them when they exist. **Swapping is a file replacement, not a
code change** — drop a file into `furniture/site/assets/renders/` and run
`bash scripts/deploy.sh`.

## Rules that apply to all seven

- **The table must be built to the frozen spec.** 160→220 × 90 × 75 cm, 40 mm top with an
  underside chamfer, oak veneer on plywood with a solid oak edge, two A-frame solid-oak legs,
  black steel beam between them, no aprons. If a render shows a different table, the site
  becomes a lie and the whole honesty position is gone.
- **Three tones, every time:** natural, smoked, whitewashed. Legs always match the top.
  The beam is always matte black.
- **Israeli apartment, not a Scandinavian magazine.** Iron-framed windows, tiled floor
  (not oak parquet), a merpeset visible through the glass, roller shutters. A Copenhagen
  loft reads as stock imagery to an Israeli and destroys the credibility the copy is building.
- **Daylight, no HDR, no bloom, no lens flare.** Slightly under-lit beats glossy.
- **No people.** No hands, no families, no dinner parties. The brief forbids stock people and
  a rendered person is worse than a stock one.
- **No food styling.** A bowl and a folded cloth is the ceiling.
- **Deliver:** 2400 px on the long edge, sRGB, PNG. The build pipeline converts to WebP and
  AVIF and writes the `<picture>` sources.
- **Label anything that is a render.** Until a real photograph exists, the footer line
  "ההדמיות באתר הן שרטוטים טכניים" changes to "חלק מהתמונות הן הדמיות" — Israeli consumer
  law §2 covers advertising before the first sale.

---

## R1 · Hero — the table alone
**Replaces:** the elevation drawing in the hero sheet.
**Where:** `site/assets/renders/hero-{natural,smoked,white}.webp` — three files, one per tone.
**Framing:** three-quarter view, camera at 120 cm (seated eye level), 50 mm equivalent, table
filling 75% of frame width, closed at 160 cm.
**Background:** flat warm paper `#e9e6de`, no floor line, no shadow except a soft contact shadow.
**Why this framing:** it has to sit on the drawing sheet where the elevation sits now, and read
at 390 px wide.
**Prompt seed:** *product photograph of a rectangular oak dining table on a plain warm off-white
background, three-quarter view at seated eye level, 160 cm long, 40 mm thick top with a
chamfered underside edge, two solid oak A-frame trapezoid legs joined by a matte black steel
beam beneath the top, no apron, matte oil-wax finish, soft even daylight, subtle contact
shadow, no props, no people, studio product photography, 50mm lens*

## R2 · The table in an Israeli apartment
**Replaces:** nothing yet — this is the ad asset (`creative-brief.md`, A1) and a future
section image.
**Framing:** open at 220 cm, ten chairs, seen from the corner of an open-plan kitchen/living
room. Late afternoon light from the left through an iron-framed window.
**Must contain:** tiled floor, a kitchen counter edge, a glimpse of a merpeset.
**Must not contain:** people, food beyond a bowl and a cloth, oak parquet, a fireplace.
**Warning:** frame tight enough that the room is context, not subject. Meta's 2026 classifiers
can misfile a room-dominant image as the Housing special ad category.
**Prompt seed:** *interior photograph of an Israeli apartment open-plan dining area, extendable
oak dining table extended to 220 cm with ten chairs, late afternoon daylight through an
iron-framed window, tiled floor, kitchen counter at the edge of frame, no people, natural
colours, architectural photography*

## R3 · Macro of the surface — **the highest-value render**
**Replaces:** the swatch colours; becomes the material section's lead image.
**Framing:** 15 cm of tabletop filling the frame, shot at a low raking angle so the grain and
the open pore of oil-waxed oak catch the light. The chamfered edge must be in frame with the
solid-oak lipping visible against the veneer face.
**Why it matters most:** the entire A2 ad argument is "real oak, not a print". This image is
that argument. A weak version of it undermines the strongest claim on the page.
**Three versions**, one per tone.
**Prompt seed:** *extreme close-up macro photograph of an oiled European oak tabletop surface,
raking side light revealing open grain and pore texture, matte oil-wax finish, the chamfered
edge of a 40 mm slab visible with a solid oak lipping meeting the veneer face, shallow depth
of field, no gloss, natural colour*

## R4 · Closed and open, same frame
**Replaces:** supports the plan drawing in the size section.
**Framing:** identical camera, identical crop, two exposures — 160 and 220 — for a
before/after slider or a stacked pair. The camera must not move by one pixel.
**Why:** the twin-state comparison is the single most persuasive layout pattern found in the
landing-page research, and it only works if the scale is provably identical.

## R5 · Dimensions
**Replaces:** nothing — it supplements the plan drawing.
**Framing:** straight-on plan and elevation, orthographic, on the paper background, with the
dimension lines and Hebrew labels composited in afterwards rather than rendered.
**Note:** the existing SVG already does this correctly and to scale. A render is only worth it
if it is *better* than the drawing; if in doubt, keep the drawing. A photograph with dimension
lines drawn over it is usually worse than a clean orthographic drawing.

## R6 · Flat pack
**Replaces:** the two-cartons drawing in the logistics section.
**Framing:** the two real cartons — 170×100×12 and 125×40×22 cm — standing against a doorway,
with a folding rule or a tape measure in frame for scale. **Photograph, not a render.** This is
a logistics proof, and a rendered box proves nothing.
**Second frame:** the open carton with the parts laid out — two frames, the beam, the top
halves, the leaf, the fittings, the single hex key. Everything the customer will see.

## R7 · Leg and beam detail
**Replaces:** supports the materials section.
**Framing:** the joint where the black steel beam meets the solid oak A-frame, from below and
to one side, showing the fixing. Shallow depth of field.
**Why:** it is the only structural claim on the page a buyer cannot verify from the outside,
and the 5-year warranty is written against it.

---

## Order of value, if only some get made

1. **R3 macro** — carries the material argument, which is the differentiator.
2. **R6 flat pack** — must be a real photograph; proves the logistics promise.
3. **R1 hero** — replaces the drawing that everything else hangs off.
4. **R2 interior** — the ad asset.
5. **R4 twin state**, 6. **R7 detail**, 7. **R5 dimensions** (probably never — the drawing is better).

## The honest caveat

R1–R5 and R7 can be generated before a prototype exists. **R6 cannot** — it needs real cartons.
And the moment any of these goes on the site, the site is showing a table nobody has built yet.
That is legal if labelled as a render, and dishonest if not. The current drawings have the
advantage of being self-evidently drawings: nobody mistakes a line drawing for a photograph,
which is exactly why shipping tonight with drawings was the right call rather than a weakness.
