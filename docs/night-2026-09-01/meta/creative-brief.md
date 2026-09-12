# Creative brief — what each ad needs, and what already exists

> **Updated 2 Sep, 12:30.** The 3D renders now exist (`furniture/renders-master/`, 30 views ×
> tones × states) and every ad below has been regenerated on them by `node tools/make-ads.js`
> → `night/meta/creative/`. The drawing-based fallbacks described further down are superseded;
> the framing notes and the "no room interiors" rule still apply. Each frame carries a small
> "3D render · הדמיה" label.

Two things are true at once: the site ships with hand-authored technical drawings that are
dimensionally correct and look deliberate, and **photographs of this table do not exist**.
This brief says exactly which asset each ad needs, which of them can be produced tonight from
the site's own SVG, and which need a camera or a render.

Photoreal renders are specified separately in `night/RENDER-BRIEF.md`.

---

## What can be produced without any new asset

The landing page's drawings are SVG on a light "sheet". Screenshotting them at ad dimensions
produces clean, on-brand creative in minutes, and it is honest: a technical drawing does not
pretend to be a photograph.

`furniture/tools/make-og.js` already does exactly this for the 1200×630 link preview. The same
five-line script re-pointed at a different HTML file and viewport gives you any ad size.

| Asset | Size | Source | Status |
|---|---|---|---|
| Link preview card | 1200×630 | `tools/og.html` | **done**, live at `/assets/og.png` |
| A1 feed square | 1080×1080 | elevation, closed→open | scriptable tonight |
| A1 feed 4:5 | 1080×1350 | same | scriptable |
| A3 feed square | 1080×1080 | plan view + room-fit verdict | scriptable |
| S1 story frames | 1080×1920 ×3 | plan view at 6 seats / mid / 10 seats | scriptable |
| S2 story frames | 1080×1920 ×3 | elevation in the three oak tones | scriptable |

For the story videos: export the three frames as PNG and assemble them in any editor, or use
the CSS transition already on the page and screen-record it. A 6-second silent loop is enough.

---

## Per-ad requirements

### A1 · `a1_fits` — "everyone fits"
**Primary asset:** the plan view, animated or as a two-state pair — 6 chairs on the left of the
frame, 10 on the right, same scale, so the growth is literally visible.
**Fallback available now:** static 1080×1080 of the open state with all 10 chairs.
**What would be better:** RENDER-BRIEF #2 (interior, table set for Friday dinner) — but that
render must show a *real* table, so it waits for the prototype.
**Avoid:** any image containing a room interior with visible flooring and walls as the dominant
subject. Meta's 2026 visual classifiers can misfile that as the Housing special ad category.
Frame tight on the furniture.

### A2 · `a2_oak` — "real oak, not a print"
**Primary asset:** the edge cross-section drawing, cropped tight, with the three tone swatches
beneath it. It is the most information-dense image we have and it makes an argument no
competitor's photo makes.
**What would be better:** RENDER-BRIEF #3 (macro of the oil-waxed oak surface, raking light).
This is the single highest-value render — the material claim is the ad's whole argument.
**Avoid:** side-by-side "us vs them" comparisons naming a competitor.

### A3 · `a3_roomfit` — "will it fit"
**Primary asset:** a screenshot of the room-fit tool mid-answer, showing an amber
"מתאים סגור, פתוח יהיה צפוף" verdict rather than a green one. The honest answer is more
arresting than the flattering one and it is the reason to click.
**Second frame:** the plan view with the 90 cm clearance ring drawn around the open table.
**No render needed.** This ad is about the tool, not the table.

### A4 · `a4_story` — "who makes it"
**Primary asset:** the flat-pack drawing — two cartons against a 90 cm doorway.
**What would be better:** a real photograph from the Chernivtsi workshop. Not a render — a
phone photo of the actual bench, the actual clamps, the actual person. Slightly imperfect is
the point; this is the one asset where authenticity beats production value, and it costs
nothing but asking.
**Avoid:** stock photography of any workshop. If the photo is not from Impuls it does not go in
this ad.

---

## Specs

| Placement | Ratio | Pixels | Safe area |
|---|---|---|---|
| Feed (primary) | 1:1 | 1080×1080 | keep text out of the bottom 15% |
| Feed (tall) | 4:5 | 1080×1350 | best mobile real estate per shekel |
| Stories / Reels | 9:16 | 1080×1920 | keep everything inside the middle 1080×1420 |

- PNG or JPG, sRGB, under 30 MB.
- Text in the image is allowed and no longer penalised by a hard rule, but keep it short —
  the drawing should carry the ad, not a paragraph.
- Every image needs the price to be legible at thumbnail size or not present at all. Half-legible
  is worse than absent.

## Brand constants for every asset

| | |
|---|---|
| Paper | `#e9e6de` |
| Sheet | `#f4f2ec` |
| Ink | `#1a2434` |
| Oak, natural | `#d8b487` face, `#c19863` edge |
| Oak, smoked | `#6d4d33` face, `#563c27` edge |
| Oak, whitewashed | `#e4d9c8` face, `#cfc0a9` edge |
| Steel | `#23262b` |
| Display type | Frank Ruhl Libre 700 |
| Body type | Assistant 400 / 600 |

Wordmark: `אלומה` in Frank Ruhl Libre 700 with `ALUMA` beneath it in Assistant 600, muted.
Never set the Hebrew wordmark in the body face, and never letter-space Hebrew.

## The rule that governs all of it

Nothing in any creative may show a state of the world that does not exist. No showroom, no
delivery van with a logo, no styled dinner party in a home that owns this table, no product
photograph until a product has been photographed. A drawing labelled as a drawing is honest.
A render presented as a photo is not, and Israeli consumer law §2 covers advertising before
the first sale.
