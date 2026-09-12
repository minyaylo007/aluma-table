# Design plan — the rebuild (draft, before the 40-site synthesis lands)

Written while the teardown workflow runs, from the owner's direction, the two finished
teardowns (Hem, Sixpenny), the landing research, and the critiques. The synthesis will
adjust palette and type; the structure below is what it will be checked against.

## What the owner said, translated into constraints

| He said | It means |
|---|---|
| "просто текст", "слабенький" | The page must be **image-led**. Every section opens with the table, not a paragraph. Drawings are gone; 3D renders carry it. |
| "модный, стильный, красивый" | Editorial DTC register — Hem / Sixpenny / Floyd, not Israeli retail. Large type, large product, large air. One accent. |
| "функциональный, удобный, простой" | The configurator, the room-fit tool and the form are the page; everything else supports them. No decoration that is not information. |
| "классный логотип, классные цвета" | A real wordmark with a mark, not a serif word. A palette derived from the product: oak, paper, one deep accent. |
| "иврит и английский" | Bilingual from day one: `/` Hebrew RTL, `/en/` English LTR, mirrored layout, one content source. |
| "3D-модель" | Real renders in three tones × two states, plus an on-demand interactive viewer ("rotate the table"). |
| Origin not stated | No country anywhere. "Family workshop, European oak." |

## Palette (proposal — to be reconciled with the synthesis)

The current page is ink-on-paper. Keep the paper (it composites with the renders seamlessly)
but warm it slightly, and add one accent with real chroma so the page has a temperature.

| Token | Hex | Role |
|---|---|---|
| paper | `#ECE8DF` | page ground; renders are shot on it, so they sit flush |
| sheet | `#F6F3EC` | cards, form fields |
| ink | `#17202B` | text, primary button |
| soft | `#5B6472` | secondary text (AA on paper) |
| rule | `#CFC8BA` | hairlines |
| **accent** | `#B4552D` | burnt clay — links, focus, one CTA highlight, the mark |
| go | `#1F6F4A` | WhatsApp only |
| oak natural / smoked / white | `#D9B78A` / `#6F4F35` / `#E6DCCB` | swatches; match the render tones exactly |

Why clay and not green or blue: the product's own colours are oak and black steel on warm
paper; a warm-earth accent belongs to that world, green reads as WhatsApp and blue reads as
Hem. One accent, used rarely, is what makes it read as chosen.

## Typography

- **Display:** Frank Ruhl Libre 700 — already self-hosted, real Hebrew authority, pairs with
  the serif register of Sixpenny/Hem. Sizes: h1 44/1.1 mobile → 72/1.05 desktop; h2 30 → 44.
- **Body:** Assistant 400/600 — quiet, excellent Hebrew, digits sit well with the serif.
  17/1.7 mobile, 18/1.7 desktop. Captions 14/1.5 (never below 14).
- **Utility (LTR numerals, spec tables):** Assistant 600 tabular figures.
- No letter-spacing on Hebrew, ever. Latin wordmark may be tracked +8%.
- English pages: same faces (both have full Latin).

## Logo

**Wordmark + mark.** אלומה means a sheaf. The mark is a sheaf reduced to geometry: five
slender strokes converging to a waist and fanning again above it — a bound bundle, drawn
in 2 px line on a 32 px grid so it survives as a favicon. In the lockup the mark sits on the
start side of the wordmark (right in Hebrew, left in Latin); the Latin `ALUMA` in Assistant
600 tracked, small, under the Hebrew in the primary lockup. Colour: ink; the mark alone may
take the accent. Minimum size 24 px mark / 18 px wordmark. Never on a photograph; on paper
or on the oak swatch only.

## Section blueprint (top to bottom)

Each section: one job, one image, one micro-conversion.

1. **Masthead** — mark + wordmark, language switch (עב / EN), one quiet link "השאירו פרטים".
2. **Hero** — asymmetric editorial: the render (hero, current tone, current state) bleeds to
   one edge at ~62% width on desktop; text block at the opposite lower corner: h1, one
   sentence, price in the button ("הזמנה מוקדמת · ₪5,990"), reassurance line under it
   (incl. VAT · delivery + assembly · 8–10 weeks), and an arrow link "סובבו את השולחן →" that
   swaps the image for the live viewer. On mobile: image full-width, then text, price button
   above the fold.
3. **Configurator strip** — three oak swatches (real render thumbnails, not colour chips) and
   the 160/220 pair as two small silhouettes; changing either cross-fades the hero image and
   updates the title block. Persisted. This is the strongest engagement signal and sits
   directly under the hero.
4. **Three claims** — image-led cards: detail render (real oak), open-state render (160→220),
   flat-pack drawing (through the door). Short heading, two lines.
5. **Sizes and seating** — the plan drawing with chairs stays (it is information), on a tinted
   ground, beside the twin-state spec cards; the room-fit tool beneath.
6. **Sticky split: story** — three text blocks that stay put while three renders scroll past
   (oak & finish / the extension / delivery & assembly), alternating sides; mirrors for free
   in RTL. Sixpenny's `hp-sticky-split`, the one motion the page has.
7. **Spec sheet** — Hem's key/value groups: general (warranty, lead time) · dimensions
   closed/open · packaging (boxes, weight, volume) · materials. Downloads: dimension sheet
   PDF (generate from the drawings). No country row.
8. **Why this price** — kept, tightened to three lines and one honest comparison the owner
   can approve or strike.
9. **FAQ** — ten, as now.
10. **Form** — on the sheet colour, price in the button, status line, the two consent lines.
11. **Sticky mobile bar** — the same button as the hero ("הזמנה מוקדמת · ₪5,990"), fading in
    when the in-flow one leaves the viewport. WhatsApp beside it when configured.
12. **Footer** — giant wordmark sign-off (Hem), then links, then the pre-launch note.

## Imagery rules

- Every render on the paper colour, no backdrop, contact shadow only. Same camera per view
  across tones so the swatch switch is a pure cross-fade.
- Hero: closed by default, natural by default. `<picture>` with AVIF → WebP, 800/1200/1600
  widths, `fetchpriority="high"` on the hero, everything else lazy.
- The interactive viewer loads three.js (cdnjs) only on tap; the render stays as the
  fallback and the LCP.
- A tiny "הדמיה" (render) label near the hero image — honesty at no cost.

## Motion

Exactly four: hero cross-fade on tone/state (300 ms); the sticky-split story; the sticky bar
fade; the FAQ chevron. Nothing on scroll otherwise. `prefers-reduced-motion` kills all four.

## Bilingual

- `/` = Hebrew, `/en/` = English. Same template, `{{t.key}}` strings, `dir`/`lang` per page,
  `hreflang` both ways, switch in the masthead. Layout mirrors via logical properties; the
  renders, numerals, the plan drawing and the logo mark do not mirror.

## Performance budget

HTML ≤ 45 KB, CSS ≤ 20 KB, JS ≤ 25 KB (viewer excluded, on demand), hero image ≤ 90 KB
at 1200 w. Lighthouse mobile ≥ 95 all four; LCP ≤ 1.8 s on the 4G throttle.

## Not doing

Photos of people, room scenes, countdowns, reviews, financing widgets, autoplay video,
parallax, AR, a chatbot, a cookie wall.
