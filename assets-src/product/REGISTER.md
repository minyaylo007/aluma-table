# GOREN — evidence, claims and asset register

Maintained with the page. Every public claim and every image on the site is listed here with its
source and its verification status. **Status vocabulary:** `verified` = confirmed against a
physical unit, manufacturer document or the owner in writing; `provisional` = a repository
assertion (content.json / goren3d.js) that the owner has not yet confirmed; `unsupported` = must
not appear on the page. Nothing on the page may be stronger than this register.

Evidence order used: owner/manufacturer photographs and measurements → CAD checked against the
physical references → existing geometry/specification in the repository → generated illustration.
As of 2026-09-09 **no manufacturer photograph, measurement or validated CAD exists in this
repository**; every product fact below is therefore provisional, and every image is a render or a
labelled visualisation. A generated scene never establishes a physical fact.

## 1. Product claims

| Claim (as shown) | Source | Status | Where used | Follow-up needed |
|---|---|---|---|---|
| Brand אלומה / ALUMA, model גורן / GOREN | content.json | provisional (naming, no trademark clearance) | masthead, hero, footer, JSON-LD | owner: confirm names; no clearance claim is made |
| Price ₪5,990 incl. VAT | content.json PRICE / PRICE_PLAIN | provisional | hero band, offer, form summary, sticky, JSON-LD | owner: confirm launch price |
| Delivery and assembly included in the price | i18n price_incl / offer_incl_v / FAQ 3 / terms §5 | provisional | hero band, offer, FAQ, terms (both locales) | owner: confirm. No geographic coverage is claimed anywhere: the page and the terms both say the delivery area and building access are checked on the call and confirmed in the written proposal |
| Closed 160 cm, open 220 cm, width 90, height 75 | content.json | provisional | everywhere, drawings from the same numbers | owner: confirm |
| Top 40 mm, leaf 60 cm, leaf stored inside the table | content.json TOP_MM / LEAF_CM, goren3d.js spec | provisional | materials, dimensions | owner: confirm; the storage mechanism is shown only as a hidden-line drawing, never animated |
| Oak veneer on plywood core, solid-oak lipping, solid-oak legs, matte-black steel beam, matte oil-wax finish | i18n mat_* (repository) | provisional | materials, FAQ | owner/manufacturer: confirm construction; "the whole top is not solid oak" is stated explicitly |
| Three finishes: natural, smoked, whitewashed | content.json / renders | provisional | configurator | owner: confirm; finish swatches are render crops, not physical samples |
| Up to 6 / up to 10 seats | content.json SEATS_* | provisional, qualified ("depends on chairs and trestle positions") | dimensions, FAQ | owner: confirm; plan drawing marked illustrative |
| 8–10 weeks from written order confirmation | content.json LEAD_WEEKS | provisional | hero, offer, FAQ, thanks | owner: confirm capacity; no calendar dates are derived from browser time |
| 5-year structural warranty | content.json WARRANTY_YEARS | provisional | offer | owner: confirm terms in writing |
| Two cartons 170×100×12 and 125×40×22 cm | content.json BOX_A/BOX_B | provisional | FAQ only | owner: confirm; door/lift access is never guaranteed |
| No online payment; written proposal before any payment; cancellation terms in the proposal, subject to the Consumer Protection Law | business model (brief) | verified as the site's behaviour | offer, FAQ, footer, terms | legal review of the wording before launch |
| Operator name, registration number, address, e-mail, phone, accessibility contact, court city | content.json (EMPTY) | **unsupported until supplied** | footer, legal pages (visible "להשלמה" markers) | owner MUST supply before launch; `python build.py --production` refuses to build without them |
| Data retention: enquiry details kept until deleted (no TTL), usage events 180 days, visit records 400 days | api/handler.py EVENT_TTL_DAYS / SESSION_TTL_DAYS / put_lead | verified as the system's behaviour | privacy §6, both locales | The privacy pages now state this instead of the previous "24 months", which no code implemented. Owner + legal must still SET a retention rule for enquiry details and have it implemented before launch; `content.json` carries the note in place of the retired RETENTION_MONTHS token |

Claims deliberately removed from the previous page (unsupported): one-hand opening, ten-second
opening, family workshop, European timber, nationwide delivery, easy repair without a
professional, "one size is why the price is not double", comfortable capacity independent of
chairs, blanket cancellation statements, rolling calendar delivery dates, the 60 cm "comfort"
clearance rule (the estimator now reports numbers only).

## 2. Assets (site/assets/product/)

Manifest: `site/assets/product/manifest.json` (render set) and `manifest-home.json` (home scene);
build.py merges them and refuses to publish a file the manifest does not list. All files are
content-hashed at build time. Provenance detail: `assets-src/product/RENDER-LOG.md` and
`assets-src/product/HOME-SCENE-LOG.md`.

| ID | Purpose | Kind / source | Status | Localized alt / caption | Notes |
|---|---|---|---|---|---|
| goren-studio-hero-natural-closed | A1 hero, desktop 2.2:1, 1200/1600/2000 | render, tools/render3d.js view `studio`, goren3d.js provisional geometry, bg #F4F1EA | provisional | i18n hero_alt; caption render_tag | camera and width fraction recorded in the manifest |
| goren-studio-hero-m-natural-closed | A1 hero, mobile 3:2, 640/800/1000 | render, view `studio-m` | provisional | hero_alt | art-directed `<source media>` |
| goren-compare-{natural,smoked,white}-{closed,open} | A2 state/finish comparison, 3:2, 800/1200/1600 | render, view `compare`, camera locked on the open bounds | provisional | cmp_alt template | same pixel scale in all six; open is physically longer |
| goren-home-daylight (+ -m 4:5) | A3 home context | AI-assisted visualisation: hero render → Bedrock Stability control-structure → local beam composite → inpaint; see HOME-SCENE-LOG.md | provisional, labelled "visualisation" | home_alt / home_caption | room illustrative; chairs (if any) not part of the offer. Fallback while absent: site/assets/editorial/goren-daylight (provenance undocumented, produced 2026-09-08 by a previous session; not acceptable for launch) |
| goren-edge-detail-{tone} | A4 material detail, 1:1, 640/1000 | render, view `edge` | provisional, labelled "render, not a photograph" | mat_edge_alt / mat_caption | paired with the labelled schematic edge section (build.py edge_svg) |
| goren-frame-detail-{tone} | A5 structure detail, 4:3, 640/1000 | render, view `frame` | provisional | mat_frame_alt / mat_caption | |
| goren-finish-{tone} | A7 finish swatches 160/240 | crop of goren-compare-{tone}-closed, same region | provisional | text label + visible marker | not physical samples |
| goren-social (site/assets/og.png) | A8 social preview 1200×630 | studio hero master + vector logo + HTML text (tools/og.html) | provisional | — | no price on the card |
| Dimensions drawings | A6 | build.py SVG from content.json numbers | provisional (numbers), illustrative (chairs) | draw_elev_*, draw_plan_*, dim_caption | trestle footprints marked; clearances labelled estimates |

Legacy sets kept as source (not published): site/assets/renders (180 files), site/assets/photos
(5 AI scenes, olive-tree / lemons props, rejected for the page), site/assets/editorial
(undocumented provenance), site/assets/textures + goren3d.js viewer (retained tooling, no public
viewer this release).

## 2b. Reviewed 2026-09-09

A seven-lens adversarial review checked every user-visible claim against this register. Two claim
defects were found and fixed: the terms pages asserted delivery and assembly "in Israel — the full
price, with no add-ons" (coverage this register declines to claim), and the English accessibility
statement described a 3D viewer that does not ship in this release. The privacy retention text was
replaced with the lifecycle that actually exists. Details in `docs/REDESIGN-2026-09-09.md`.

## 3. Launch blockers (facts only the owner can resolve)

1. Operator identity and contacts (seven content.json fields) — the legal pages and the footer show
   visible markers until then.
2. Confirmation of every product fact in section 1 (dimensions, materials, finishes, price,
   lead time, warranty, inclusions) against a physical unit or manufacturer document.
3. Real product photography or validated CAD — until then every image stays a labelled render or
   visualisation and the page says so in the footer.
4. Retention statement vs. actual data lifecycle (section 1, last row).
5. Optional: WhatsApp number (WA_NUMBER) — controls stay hidden without it; Meta pixel / Clarity
   ids — nothing third-party loads without them.
