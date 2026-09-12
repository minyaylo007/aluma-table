# Furniture — Fable 5.1 implementation handoff

Prepared from the read-only Codex audit on 2026-09-09. This document is self-contained. Recheck source facts because files may have changed. The accompanying DESIGN-PLAN.md records the audit, research, and selected direction.

=== START FABLE 5.1 IMPLEMENTATION PROMPT ===

You are Claude Fable 5.1 / Claude Code, acting as the implementation owner for an existing single-product furniture website.

Your task is to IMPLEMENT the redesign described here, preserve the existing business functionality, create or edit the necessary visuals using trusted available tools, run the site, inspect the rendered result, fix weaknesses, test, and iterate.

DO NOT STOP AT PLANNING.
START IMPLEMENTATION AFTER VERIFYING THE REPOSITORY.
MAKE THE CHANGES YOURSELF.
KEEP ITERATING UNTIL THE ACTUAL RENDERED SITE MEETS THE QUALITY BAR.

The Codex planning phase is complete. Its restriction against implementing applied to Codex during that phase, not to your implementation task. This prompt authorizes the Furniture implementation described below. Do not interpret the audit's "no files modified" statement as an instruction to avoid implementing.

## A. Scope and business reality

Workspace:

`C:\Users\igor\Desktop\gosha`

Work ONLY within the Furniture application:

`C:\Users\igor\Desktop\gosha\furniture`

The parent workspace contains unrelated projects. Do not modify them. This handoff folder is outside the application intentionally.

The owner calls the project FurnitureTable.CentralStore.com. The inspected repository instead consistently configures:

`https://table.central-aparts.store`

Verify this discrepancy, but preserve current routing, DNS, AWS stack identity, and domain configuration unless separately instructed to change them.

The product is one extending dining table for market validation in Israel. Traffic will come from Instagram, Facebook, TikTok, and other paid social sources.

The existing site is a PRELAUNCH ENQUIRY FUNNEL. It does not take online payment or complete purchases.

Preserve that business model:
- Primary action: request a callback.
- Secondary action: WhatsApp only when a real number is configured.
- No cart, Buy Now, checkout, reservation fiction, deposits, or Purchase events.
- Success means the enquiry was accepted by the backend, not an order was placed.
- Optimize for qualified enquiries after exposure to price and preorder context.

Finish the implementation in an isolated local preview. Deployment and cloud mutations are not part of this brief.

Inspect trusted available skills, agents, browser tools, image tools, plugins, and MCP capabilities. Use them when materially helpful. Follow applicable repository instructions. Do not blindly download random code or execute untrusted software.

## B. Existing architecture and files

This is a Python-generated static website with vanilla JavaScript, not React.

Important files:
- build.py
- content.json
- i18n/he.json
- i18n/en.json
- site/index.html
- site/thanks.html
- site/404.html
- site/terms.html
- site/privacy.html
- site/accessibility.html
- site/en/terms.html
- site/en/privacy.html
- site/en/accessibility.html
- site/assets/styles-next.css
- site/assets/app-next.js
- site/assets/fonts/fonts.css
- site/assets/logo.svg
- site/assets/logo-en.svg
- site/assets/logo-signoff.svg
- site/assets/favicon.svg
- site/assets/goren3d.js
- site/assets/renders/
- site/assets/photos/manifest.json
- site/assets/editorial/
- api/handler.py
- infra/template.yaml
- scripts/deploy.sh
- scripts/daily_report.py
- tests/redesign.spec.js
- tests/smoke.spec.js
- playwright.local.config.js
- playwright.config.js
- tools/serve-preview.py
- tools/render3d.js
- tools/render3d.html
- tools/optimise_renders.py
- tools/imagegen/README.md
- assets-src/SOURCES.md
- renders-master/
- renders-test/

build.py substitutes content and locale tokens, generates technical SVGs, and produces dist/. dist/ is generated output; edit source files rather than treating it as the source of truth.

Active frontend files are styles-next.css and app-next.js. Older styles.css and app.js exist; check all references before excluding them from published output.

Keep static HTML and vanilla JS, existing localization/build structure, useful validation/error handling, lead/event endpoints, state persistence, accessible form hooks, and local preview isolation.

Do not add React, Next.js, Tailwind, a client router, a component framework, a hydration layer, or a motion library without a concrete unavoidable requirement. None is expected.

The planning audit found uncommitted changes in:
`i18n/en.json`, `i18n/he.json`, `package.json`, `site/assets/app-next.js`, `site/assets/styles-next.css`, `site/index.html`.

It also found untracked local config, tests, editorial assets, and preview/redesign tools. Inspect the current git state. Preserve existing work and integrate deliberately; do not reset or discard it.

## C. Product truth and claims

Existing displayed brand: **אלומה / ALUMA**.

Existing model: **גורן / GOREN**.

Keep these names. FurnitureTable is not the proposed displayed brand. CentralStore should not become the premium wordmark. Do not rename infrastructure.

The current repository specifies:
- Price: ₪5,990 / numeric 5990 ILS.
- Closed length: 160 cm.
- Open length: 220 cm.
- Width: 90 cm.
- Height: 75 cm.
- Top thickness: 40 mm.
- Extension leaf: 60 cm.
- Finishes: natural, smoked, whitewashed.
- Top: oak veneer over plywood.
- Edging and legs: solid oak.
- Beam: matte black steel.
- Six/ten seats.
- Eight–ten-week lead time.
- Five-year structural warranty.
- Delivery/assembly inclusion.
- Other packaging, weight, and assembly values in content.json.

These are REPOSITORY ASSERTIONS, not independently verified manufacturer facts.

The planning audit found no manufacturer photography or validated CAD. assets-src/SOURCES.md contains generic Poly Haven material textures and lighting. site/assets/photos/manifest.json identifies room images as AI visualizations derived from procedural renders.

The procedural model depicts two oak A-frame trestles, four floor contacts, a rectangular extending top, and a single black longitudinal beam. Preserve the existing design as a provisional baseline; do not redesign the physical table.

Use evidence in this order:
1. Owner/manufacturer photographs and measurements.
2. CAD checked against the physical references.
3. Existing geometry/specifications.
4. Generated illustrations.

A generated scene cannot establish physical truth.

Create a furniture-local evidence/asset register recording the claim or asset, source/reference, whether verified/provisional/unsupported, where used, and required follow-up.

Continue implementing the preview with clearly labeled provisional illustrations if physical references are missing. Do not stop the whole redesign because an owner fact is unavailable. Do not fabricate the missing fact, and do not call the site launch-ready while required facts remain unresolved.

Do not amplify unsupported claims such as:
- One-hand opening or ten-second opening.
- Family workshop or European timber origin.
- Universal delivery coverage or guaranteed door/lift access.
- Easy repair without a professional.
- "Half the price" or other unsupported comparisons.
- Comfortable capacity independent of chair dimensions.
- Blanket cancellation exclusions.

Do not describe the entire tabletop as solid oak.

Keep generated-image disclosure visible in a quiet caption. Never call renders or AI scenes photographs, real customer homes, or evidence of craftsmanship.

## D. Selected creative direction

Internal name: **THE EVERYDAY MONUMENT**. This name is not customer-facing copy.

Desired feeling: precise, tactile, useful, quietly confident, warm through the actual material.

The signature is a large, uninterrupted studio portrait of this exact table, with clear identity and a compact price/action band. This must be structurally different from the current split room-image/copy hero.

Avoid generic beige luxury templates, SaaS feature cards, repeated three-column selling points, pill badges, decorative gradients, animated grain, huge repeated section numbers, giant footer wordmarks, fake reviews, payment/security badges without payment, scarcity timers, invented maker stories, autoplay carousels, cursor followers, scroll hijacking, mandatory WebGL, and decorative effects that compete with the table.

Use the particular silhouette as visual identity: top, edge, trestles, floor contacts, and beam. Do not hide these under props, deep shadow, or exaggerated perspective.

## E. Visual system

Colors:
- Main: #F4F1EA.
- Alternate mineral surface: #E7E3DA.
- Input/light surface: #FFFFFF.
- Main text: #252720.
- Secondary text: #62645C.
- Decorative rule: #D1CEC5.
- Functional border: #77796F.
- Primary action: #493339.
- Primary hover: #36252A.
- On-action text: #FFFFFF.
- Error: #A52C2C.

Use the action color sparingly. Oak remains a product color. Verify actual text, control, and focus contrast. No global dark mode.

Typography: use existing self-hosted IBM Plex Sans Hebrew, including Latin coverage.
- Hero 48–64 px desktop, 34–40 px mobile.
- Section headings 34–44 px desktop, 26–32 px mobile.
- Body 18 px desktop, 16–17 px mobile.
- Labels/captions 13–14 px.
- Price 30–36 px.
- Body 400; factual emphasis and controls 600; 700 sparingly.
- Zero Hebrew letter spacing.
- Headline leading approximately 1.15–1.22.
- Body leading approximately 1.6.

Retain font license notices. Recheck fallback metrics against the new typography; do not assume metrics tuned for the previous headline remain ideal. Preload only fonts actually used above the fold.

Grid:
- 12 columns desktop, 24 px gaps.
- Max content width 1440 px.
- Fluid desktop gutters 32–64 px.
- Four-column alignment mobile, 20 px gutters, 12 px gaps.
- Major section spacing 88–120 px desktop, 48–64 px mobile.
- Straight boundaries, thin rules, open composition.
- Avoid indiscriminate card containers.

Brand: keep ALUMA/אלומה and GOREN/גורן. Refine current vector logo sizing and clear space. Remove the enormous footer sign-off. Do not generate a new raster logo or claim naming/trademark clearance.

Photography:
- Studio hero: 45–60 mm photographic feel, camera approximately 1.0–1.15 m above floor.
- No wide-angle distortion or exaggerated nearest leg.
- Neutral daylight, approximately 5000–5600 K.
- Product occupies about 80–86% of studio frame width.
- All tabletop ends, visible feet, and ground shadow remain inside image.
- Soft directional light with fill distinguishing the beam from a black void.
- One home scene: believable apartment scale, restrained furnishings, credible chair clearances, no mansion or prop collection.
- Do not mirror photography for RTL.

## F. Page sequence

1. Compact masthead and product portrait.
2. One table, two states, with finish selection.
3. One believable home context.
4. Material and construction details.
5. Dimensions and fit.
6. Offer and ordering process.
7. Focused FAQ and enquiry form.
8. Seller/legal footer.

Preserve #table, #dimensions, and #form anchors where practical.

### Section 1: Hero

Question: What is this, why is it desirable, and what is the next step?

Desktop:
- Compact masthead.
- Short product identity/headline.
- Full-width studio stage.
- Compact baseline band containing price, essential preorder context, primary callback action, and optional secondary WhatsApp.
- Do not recreate a dominant 60/40 product-image/copy split.
- Keep product, identity, price, and action within a useful first screen at 1440×900.

Mobile:
- Compact identity/headline.
- Complete table image.
- Price and callback action immediately below.
- Aim for the action to be fully visible by roughly 620 px at 390×844 with default text.
- Do not shrink text or clip content to force fixed height.

Draft Hebrew copy:
- Category/identity: “גורן — שולחן אוכל נפתח”
- Short headline option: “מקום ליום־יום. מקום לכולם.”
- Factual supporting line based on confirmed content: “מ־160 ל־220 ס״מ.”
- Primary CTA: “לתיאום שיחה”
- Form submit: “אני רוצה שיחזרו אליי”
- Context: “ללא תשלום באתר”

Draft English:
- “GOREN — an extending dining table”
- “Room for every day. Room for everyone.”
- “160 to 220 cm.”
- “Arrange a callback”
- “Request a callback”
- “No online payment”

Refine Hebrew naturally and keep English equivalent, without inventing claims. Product identity must remain explicit even if the emotional line is used. Avoid stacking six separate introductory labels above the image.

Implementation: semantic HTML and responsive picture. Hero, price, and action visible immediately, without entrance delay.

### Section 2: One table, two states

Question: How does it extend, and which finish do I prefer?

- Large matched studio comparison; desktop may use a restrained controls column, mobile controls sit below the image.
- Clear controls: “סגור · 160 ס״מ” and “פתוח · 220 ס״מ”.
- Explain these are states of one extending table, not two purchasable sizes.
- Keep backend/state values 160 and 220 for compatibility.
- Three labeled finish choices using approved material crops, not unexplained flat dots.
- State and finish changes update product image and enquiry summary.
- Do not resize both states to the same visible table width; preserve physical comparison scale.
- No invented extension animation or auto-rotation.
- Use existing state hooks and local persistence; decode then crossfade.
- A restrained callback link may carry the selected finish forward.

### Section 3: At home

Question: How might it belong in my home?

- One generous architectural interior.
- Dedicated mobile composition.
- Full table remains recognizable; no furniture hiding the base.
- Quiet caption identifies finish/state and visualization status.
- Chairs shown as context, not included products; no false capacity proof.
- One sentence of context, not an invented lifestyle story.
- Optional dimensions anchor; no redundant major purchase pitch.

### Section 4: Materials

Question: What is it made from?

- Two useful details: edge/chamfer and trestle/beam/top relationship.
- Unequal editorial compositions desktop; sequential mobile.
- Short factual copy, not a three-card feature grid.
- Clearly distinguish veneer, core, edging, legs, finish, and steel where verified.
- Real details where available; honest diagrams or labeled renders otherwise.
- No fake workshop images, hands, joinery, or craft evidence.
- Optional restrained entrance only; no visual layer separating the product from its shadow.

### Section 5: Dimensions and fit

Question: Will it fit?

- Responsive top/front diagrams.
- Plain text closed/open length, width, and height.
- Draw geometry from one shared data source.
- Desktop drawings and measurements may sit side by side; mobile drawing then readable data.
- Keep existing room-length estimator behind a concise disclosure.
- Report numerical clearance, not guaranteed comfort.
- Explain it does not account for room width, chairs, walkways, trestle interference, or delivery access.
- Do not add unsupported recommended clearance as a product fact.
- Seating diagrams are illustrative and require chair/base verification.

### Section 6: Offer and process

Question: What does it cost, and what happens after contacting you?

- Price from content data.
- Confirmed inclusions and lead time only.
- Three concise steps: callback, written proposal, customer decision.
- Production/delivery described only to the extent confirmed.
- No online payment.
- Remove unsupported comparative-price explanations.
- Avoid a rolling calendar promise derived solely from browser time.
- Compact factual rows, not decorative cards; primary callback CTA.

### Section 7: FAQ and form

Question: Can I resolve remaining uncertainty and enquire easily?

FAQ topics: dimensions/seating limitations, materials/care, delivery/building access, preorder timing, payment process, cancellation information appropriate to the actual business stage.

Form:
- Name.
- Phone.
- Optional city.
- Optional comment.
- Required permission for requested callback, preserving accurate disclosure.
- Separate unchecked optional marketing consent.
- Selected finish and displayed open/closed state.
- Submit action.
- Clear sending, success, validation, rate-limit, server-error, and offline states.

Use visible field boundaries rather than making every input an ambiguous underline. Do not collapse essential consent or seller information into unreadable text. Desktop can have a concise summary beside form; mobile is single column. Reuse existing endpoint and error hooks.

### Section 8: Footer

- Modest brand.
- Actual seller identity/contact when supplied.
- Privacy, terms, accessibility, locale links.
- Honest prelaunch and imagery disclosure.
- No giant sign-off or extra sales pitch.

The sticky action is a return shortcut, not another sales section.

## G. Visual assets and exact briefs

Create a product asset manifest, preferably `site/assets/product/manifest.json`.

Keep source/approval records inside furniture, preferably `assets-src/product/`.

Do not write to unrelated projects. Existing tools/imagegen documentation references night/imagegen paths; inspect and adapt paths before using those tools. Do not execute them blindly.

Common consistency instruction for EVERY generation/edit:

> Use the attached validated product references as identity and geometry truth. Preserve tabletop outline, thickness, edge profile, seams, grain orientation, proportions, support locations, floor contacts, beam, and selected finish. The existing design depicts two oak A-frame trestles, four floor contacts, and one black longitudinal beam; retain this as a provisional baseline until verified. Do not add or remove legs, leaves, aprons, stretchers, grommets, hardware, joinery, logos, text, certifications, people, or included accessories. Do not invent hidden construction or change veneer into solid wood. Do not conceal defects with props or shadows. Prefer preserving an approved product layer and editing its surroundings. Any render-derived output remains a labeled visualization. Reject geometry or material drift.

### A1: goren-studio-hero-natural-closed

Purpose: hero and product recognition.

Desktop: approximately 2.2:1; derive exact height from complete silhouette, not rigid crop; widths 1200/1600/2000.

Mobile: separately composed 3:2; widths 640/800/1000.

Prompt:

> Present the attached exact GOREN table, natural finish, closed state, alone on a continuous pale neutral studio floor/background. Corrected three-quarter 50 mm photographic perspective, camera approximately 1.05 m high. Show both tabletop ends, underside edge, two trestles, visible floor contacts, and the single beam without obstruction. Table occupies approximately 83% of frame width. Large soft daylight from camera-left, gentle fill under the top, neutral oak color, coherent grounded contact shadows. No room decor, props, haze, vignette, exaggerated grain, text, or invented construction.

Apply common consistency instruction. For mobile recompose without cropping feet or ends. Required realism: credible material/light response, exact provisional or verified geometry; never relabel a render as photography.

### A2: goren-compare-{tone}-{state}

Purpose: state comparison and finish selection.

Six combinations: natural/smoked/white × closed/open.

Matched 3:2 frames; widths 800/1200/1600.

Prompt:

> Produce the referenced GOREN in the specified finish/state from an identical locked camera, focal length, floor plane, exposure, and lighting. Preserve identical physical image scale across every output. Frame for the complete open table. Use only documented state geometry and actual seams/grain relationships. Change only the selected state or verified finish. Do not auto-fit the table independently, invent intermediate mechanics, or reinterpret the supports.

Prefer deterministic rendering or matched real photographs. Apply common consistency instruction. Same neutral studio environment as A1. Physically scaled endpoints; no generated mechanism. Do not use identical-width auto-crops that conceal extension.

### A3: goren-home-daylight

Purpose: home context.

Desktop 3:2, 800/1200/1600. Mobile dedicated 4:5, 640/800/1080.

Prompt:

> Place the locked approved GOREN in a believable contemporary apartment dining area with restrained off-white plaster, light stone or terrazzo, and neutral daylight from the same general side as the studio portrait. Use a 50 mm photographic feel from approximately 1.15 m. Table occupies 65–75% of frame width. Include at most two understated far-side chairs only if physically credible and not obscuring supports; they are context, not included merchandise. One small cup may sit away from seams and edges. No people, villa, ornamental arches, olive-tree cliché, excessive travertine, or decorative clutter. Preserve the product exactly.

Apply common consistency instruction. Required realism: credible room scale, physically separate chairs/table, consistent shadows. If tool cannot preserve product, simplify the room rather than accept drift. Caption as visualization when generated.

### A4: goren-edge-detail

Purpose: material explanation. Square, 640/1000. Real source or validated detailed render. Neutral unobtrusive setting, 85–100 mm detail feel, actual corner fills frame without hiding material transition.

Prompt:

> Crop and color-correct the supplied actual corner and underside edge. Use soft raking light and sufficient depth of field to understand material boundaries and thickness. Preserve actual grain, edge construction, and finish. Remove incidental dust only. Do not synthesize pores, joinery, solid-wood construction, hardware, or tool marks.

If evidence is inadequate, replace with an explicitly labeled construction diagram. Apply common consistency instruction; illustrative detail must not impersonate photographic evidence.

### A5: goren-frame-detail

Purpose: show support/beam/top relationship. 4:3, 640/1000. Neutral setting, low three-quarter close view with enough space to understand connected structure.

Prompt:

> Show the supplied actual trestle-to-top and beam relationship in a low three-quarter close view. Use soft fill to reveal the underside. Preserve every documented attachment and material boundary. No invented fasteners, brackets, joints, floating parts, or structural members.

Use labeled illustration if no adequate physical reference exists. Apply common consistency instruction. Do not conceal unsupported junctions with deep shadow.

### A6: dimensions

Purpose: fit. Generate SVG and readable HTML labels from shared data. Show closed/open length, width, height. Orthographic top/front views; responsive mobile arrangement rather than microscopic scaled labels. No image generation, mirrored geometry, or invented mechanical section. Clearance estimates explicitly labeled estimates.

### A7: finish samples

Three 160/240 px crops from actual finish samples or approved A2 images. Same lighting/exposure and material region. Label natural/smoked/whitewashed. Selection uses text and a visible marker as well as color. No newly invented exotic timber or finish opacity.

### A8: social preview

1200×630. Reuse approved A1. Compose ALUMA/GOREN and product category through HTML/SVG or ordinary graphics tools, not generated lettering. Do not embed a stale price casually. No new geometry or atmospheric scene.

Final form visual: reuse A3 only if useful; do not generate another scene.

For every image record:
asset ID, source, reference version, verification status, tone, state, camera/crop, output dimensions, formats, bytes, localized alt, localized disclosure caption, approval/rejection notes.

Compare every candidate side by side at useful size. Check geometry, seams, beam placement, support count, thickness, finish, grain, shadows, chair intersections. An aesthetically attractive but inaccurate image fails.

Do not use text-to-image to fabricate evidence. If genuine sources remain missing, complete an honest preview with labeled illustrations and report the limitation.

## H. 3D and motion

Selected media strategy: high-quality stills plus restrained interface motion.

Do not ship real-time 3D viewer, disabled rotate teaser, scroll-scrubbed frame sequence, WebGPU effects, React Three Fiber, or autoplay product film.

Retain goren3d.js and render tooling as source resources. Remove public loading references and controls for this release. Do not delete useful source merely to reduce runtime payload.

A future viewer can be reconsidered after physical geometry validation; it is not part of the current definition of done.

Motion:
- Hero, H1, price, primary CTA visible immediately.
- Finish/state swaps: decode first, 180–240 ms crossfade, old image retained on failure.
- Context/detail entrances: optional opacity and maximum 12 px translation, 300–400 ms, once.
- Button feedback: 120–160 ms.
- Sticky appearance: 160–200 ms, no bounce.
- Gallery controlled by user.
- No table movement independent from its shadow.
- No letter-by-letter Hebrew reveals.
- No counting animation for prices/dimensions.
- No hidden-by-default content permanently invisible if JS fails.

Use CSS transitions and small IntersectionObserver logic; no added animation library. Reduced motion: remove translations, parallax, automatic camera motion, and smooth scrolling; update states immediately or with negligible opacity change.

## I. Mobile and RTL

Primary design sizes: 390×844 and 430×932.

Also test: 390×700, 360×667, 320 px reflow, 768, 1024, 1440, 1920.

At 390×844:
- Header approximately 56 px.
- Identity/headline approximately 90–110 px.
- Product media approximately 235–275 px.
- Price/action/context approximately 120–145 px.
- Aim for complete primary CTA by about 620 px at default text.
- Allow growth for localization/enlarged text; never crop essential content.

Rules:
- Full table silhouette in hero.
- At least 16 px input text.
- At least 48 px primary button height.
- At least 44 px practical hit regions.
- No page-level horizontal overflow.
- No gesture required to reach CTA.
- No scroll hijacking or mandatory media interaction.

Sticky:
- Price + callback action.
- Appears only after hero action leaves view.
- Hides while form/keyboard makes it redundant.
- Does not conflict with consent UI.
- Accounts for env(safe-area-inset-bottom).
- Correct hidden/inert state when absent.
- Never covers focused controls.

RTL:
- Keep separate statically generated Hebrew/English routes.
- Preserve locale-key parity and window.FX.
- Hebrew root lang=he dir=rtl; English lang=en dir=ltr.
- Use logical CSS properties.
- Preserve coherent DOM/screen-reader order.
- Do not globally row-reverse layouts.
- Isolate numerical runs, prices, and Latin names with appropriate bdi/dir.
- Keep Hebrew units outside LTR numerical runs where necessary.
- Phone input remains type=tel, inputmode=tel, autocomplete=tel, dir=ltr.
- Name/city/comment may use dir=auto.
- Do not mirror photos, physical diagrams, or arbitrary icons.
- Check gallery arrows against actual movement in each locale.
- No Hebrew tracking.

## J. Functional contracts and corrections

Preserve unless all consumers/tests are deliberately updated:
- #leadform, #f-name, #f-phone, #f-city, #f-comment, #f-website.
- #f-consent, #f-marketing, #f-submit, #f-status, matching #e-* error hooks.
- Root data-oak and data-size.
- natural|smoked|white and 160|220.
- POST /api/fx/lead and POST /api/fx/event.
- Localized thanks destinations.
- Honeypot, consent fields/version, session attribution.
- UTMs and fbclid.
- Configuration persistence.

API behavior:
- 200 {ok:true,id}: accepted enquiry.
- 422: show returned field errors.
- 429: explain temporary rate limit.
- Server/network failure: preserve input and permit retry.
- Never redirect on non-success.
- Prevent accidental duplicate submission.
- Do not represent honeypot decoy success as a genuine conversion in ordinary analytics.

Recheck and fix targeted issues:
1. Client phone acceptance differs from server normalize_phone. Align accepted formats, including relevant +972/00972 variants, without unnecessary libraries.
2. put_lead already stores size, though it is only clipped. Preserve and validate it.
3. lang is sent by client but was not stored. Add validated locale storage if still absent.
4. Notifications omit size and locale. Include useful configuration context without altering existing endpoint shape.
5. Existing rolling ETA adds an extra week and derives delivery dates without capacity evidence. Prefer confirmed relative lead-time text.
6. Preserve legal/consent meaning while improving readability.

Privacy/business gaps:
Seller fields are blank in the inspected version. A comment claims production builds reject missing fields, but build substitutes placeholders. Create explicit preview versus production readiness validation. Do not require optional WhatsApp or pixel IDs to exist. Do require necessary seller/contact facts and resolved public claims before a production-ready result.

The audit found published retention statements inconsistent with actual lead/session lifecycle. Do not invent a retention policy, delete existing records, or claim an automated deletion process exists when it does not. Make mismatch explicit and reconcile only against confirmed requirements. Complete independent design work regardless.

## K. Analytics and validation

Preserve existing first-party events/reporting meanings:
page_view, section_view, color_select, size_toggle, room_fit_check,
form_start, form_submit, form_error, lead_success, whatsapp_click,
form_anchor_click, faq_open, gallery_open, scroll milestones, exit.

Do not emit viewer events when no viewer exists.

Preserve ?me=1 / fx_me exclusion, session handling, nonblocking telemetry failures, existing configured third-party gating, and no third-party loading with empty IDs.

Correct Meta semantics:
- WhatsApp click → first-party whatsapp_click and, where configured/permitted, Contact.
- Successful saved enquiry → Lead.
- No Lead on mere WhatsApp click.
- No Purchase.
- Prevent thank-you-page refresh creating duplicate lead conversions.

Do not add TikTok/Google pixels without configured IDs and a defined requirement. Do not claim all first-party telemetry is already consent-gated.

If improving attribution:
- Avoid combining indefinitely retained individual UTM values into a fictional campaign.
- Use coherent timestamped attribution records.
- Preserve legacy report fields.
- New channel IDs must be supported in client, backend, and reporting together.

Measure paid session → price exposure → form start → accepted enquiry. Measure qualified enquiries and cost per qualified enquiry when business follow-up data exists. Keep WhatsApp click intent separate. Do not equate raw leads with sales or invent conversion uplift.

Large sections may never reach existing 35% intersection threshold on mobile. Use appropriate small sentinels or equivalent measurement while preserving reporting compatibility.

## L. Build, assets, SEO, performance

Keep build.py and static approach.

Improve:
- Single source for dimensions and product facts.
- Localized strings remain in locale files.
- Asset manifest determines variants, URLs, dimensions, captions.
- Content-hashed asset filenames/paths.
- Explicit publication inventory excluding unused runtime assets.
- Correct font/CSS/image URL rewriting.
- Preview/production readiness validation.

Current deployment marks assets immutable despite stable filenames. Current CloudFront managed caching does not reliably make query-string versions a solution. Use actual hashed paths for immutable assets. Keep mutable documents revalidating. Do not execute deploy.sh as part of this task. Preserve AWS routing/security and unrelated stack resources.

SEO:
- Preserve canonical/hreflang and Hebrew/English paths.
- One H1.
- Accurate titles/descriptions.
- Approved OG image.
- Product structured data reflects actual confirmed facts.
- No invented ratings, inventory, seller identity, or transactability.
- Thanks pages should not behave like public product landing pages.
- No unresolved template tokens or missing URLs.

Media:
- AVIF with WebP fallback.
- srcset/sizes match actual rendered width.
- One responsive hero preload/high-priority request.
- Do not preload desktop/mobile heroes redundantly.
- Width/height or aspect-ratio reserves layout.
- Lazy-load below-fold images.
- Decode before switching.
- Avoid fetching all finish variants on entry.
- No video/Three/HDR/textures during normal load.
- Full-resolution enlargement only after user action.
- Essential content in static HTML; no hydration.

Budgets:
- Initial mobile first-party transfer target ≤400 KB.
- Mobile hero AVIF ≤150 KB.
- Desktop hero AVIF ≤250 KB.
- Initial compressed CSS ≤20 KB.
- Initial compressed JS ≤35 KB.
- Initial fonts ≤70 KB.
- Normal full-page scroll target ≤2.5 MB excluding deliberate zoom/alternate configuration downloads.
- Report configured third-party overhead separately.
- Preserve visible image quality; if a budget genuinely conflicts with approved quality, document measured tradeoff.

Performance targets:
- Field p75 LCP ≤2.5 s.
- Field p75 INP ≤200 ms.
- Field p75 CLS ≤0.1.
- Local lab results do not establish field results.

Historical September 8 local evidence was approximately LCP 3.03 s, TBT 260 ms, 430 KiB. Treat it only as historical context, not your result. Codex did not perform fresh live-browser QA; it inspected saved screenshots and assets because browser control was unavailable.

## M. Implementation sequence

1. Verify repo/instructions/git state and preserve existing work.
2. Inspect source, contracts, assets.
3. Establish isolated local preview and mocked API tests.
4. Create product/claims/asset register.
5. Approve studio composition and mobile framing.
6. Implement typography/tokens/masthead/hero/action band.
7. Implement matched finish/state module.
8. Create/edit approved home/detail visuals.
9. Implement material, dimension, ordering, FAQ, form, footer.
10. Verify Hebrew/English and functional contracts.
11. Correct targeted phone/API/event issues.
12. Add restrained motion and robust fallbacks.
13. Implement asset hashing/publication checks.
14. Run build/tests, inspect actual browser screenshots, measure performance.
15. Fix weaknesses and repeat until complete.
16. Deliver implementation and evidence, identifying only genuinely unresolved external facts.

Do not produce another plan in place of code. Do not stop after one screenshot. Do not call work finished merely because build passes.

## N. QA and definition of done

Use existing trusted testing tools.

Expected commands, after inspecting their behavior:
- npm run build
- npm run dev
- npm run test:local

Local preview deliberately rejects real lead submission. Preserve that behavior.

IMPORTANT: playwright.config.js / tests/smoke.spec.js can target production and make real API calls, including test leads. Do not run that suite against production as part of redesign. Use isolated local preview, request interception, backend mocks, and synthetic test data. Do not send test WhatsApp messages, emails, or live leads.

Required screenshots:
- Hebrew and English desktop, 1440×900.
- 1920×1080.
- 390×844.
- 430×932.
- Short mobile viewport.
- Hero, configurator, materials, dimensions, form, footer.
- Full page after loading lazy sections through scrolling.

Visual acceptance:
- Complete recognizable table immediately.
- Product/category/price/context/action understood within five seconds.
- Hero materially differs from prior split layout.
- Product consistent across every asset.
- Open table physically longer in matched comparison.
- No clipped feet, ends, shadows, text, controls, or unsupported decorative sections.
- One purposeful home image.
- Details explain actual materials or are honestly labeled illustrations.
- No fake reviews, maker narrative, scarcity, badges, misleading imagery.
- No huge footer logo.
- No blank lazy frames in final inspection.

Functional acceptance:
- All six finish/state combinations.
- Persistence/reload and locale behavior.
- Form validation and mocked accepted enquiry.
- 422/429/500/offline handling.
- Retry and duplicate-submission protection.
- Attribution/configuration payloads.
- Appropriate size/locale storage.
- Correct analytics semantics.
- WhatsApp hidden when missing and valid URL/prefill when configured.
- Thanks/legal/accessibility routes.
- Image error handling.

Accessibility:
- Semantic headings/landmarks.
- Keyboard-only journey.
- Visible focus and practical hit areas.
- Dialog focus, Escape, return focus.
- Meaningful alt text/captions.
- Text/control contrast.
- Hebrew/English bidi.
- 200% text zoom and narrow reflow.
- Reduced motion.
- No-JS readable content and clear form limitation if JS required.
- Storage failure does not crash page.
- Sticky controls do not cover focused fields, keyboard, or consent.

Performance:
- No normal-entry 3D/video payload.
- Correct hero selection and no duplicate preload.
- No unexpected missing assets/console errors.
- Cold-cache mobile tests with recorded conditions.
- Budgets checked from network evidence.
- New hashed URLs change when assets change.
- Existing local suite plus focused meaningful regression tests.
- Do not weaken tests merely to get passing result.

Browser coverage:
Use Chromium and WebKit/Firefox where available; prioritize real iOS Safari and Android/in-app-browser inspection when trusted devices/tools are available. If browser/device unavailable, report limitation precisely rather than claim it passed.

Final report:
- What changed and why.
- Exact project scope.
- How to run local preview.
- Tests and results.
- Screenshot locations.
- Measured performance conditions/results.
- Asset provenance/verification status.
- Unresolved seller/product/operating facts preventing public launch.
- No deployment claim unless separately authorized and completed.

Finish all implementation and independent QA possible. Missing manufacturer/business facts must not become an excuse to leave design half-built, and must not be filled with inventions.

## O. Useful reference principles

Borrow principles, not brand assets, claims, or layouts.

- Cassina Vidalenta: desire with dimensions/material evidence:
  https://www.cassina.com/lu/en/products/vidalenta-table.html
- B&B Italia 2026: coherent home context:
  https://www.bebitalia.com/it-it/b-b-italia-presenta-il-nuovo-catalogo-2026
- Molteni atmospheres:
  https://www.molteni.it/en/us/atmospheres
- Muuto Earnest:
  https://www.muuto.com/product/Earnest-Extendable-Table-Extension-Leaves?configure=true
- FRAMA dining tables:
  https://us.framacph.com/collections/dining-tables
- Current Collection, Siteinspire April 19, 2025:
  https://www.siteinspire.com/website/13120-current-collection
- Apple product hierarchy:
  https://www.apple.com/iphone-17-pro/
- W3C bidi:
  https://www.w3.org/International/articles/inline-bidi-markup/Overview.en.php?changelang=en
- IBM Plex license:
  https://github.com/IBM/plex/blob/master/LICENSE.txt
- Web Vitals:
  https://web.dev/articles/defining-core-web-vitals-thresholds
- Israeli Privacy Protection Authority collection-notice guidance:
  https://www.gov.il/BlobFolder/legalinfo/duty_to_notify/he/notify13.pdf

IMPLEMENT → CREATE/EDIT REQUIRED VISUALS → RUN → INSPECT → FIX → TEST → ITERATE → FINISH.

=== END FABLE 5.1 IMPLEMENTATION PROMPT ===
