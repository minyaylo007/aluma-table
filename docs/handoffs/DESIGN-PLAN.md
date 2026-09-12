# Furniture — audit, creative direction, and implementation plan

Date: 2026-09-09.

This is the saved planning handoff from the Codex conversation. The independently usable implementation instructions, including every asset brief and acceptance requirement, are in **FABLE-IMPLEMENTATION-PROMPT.md** in this folder.

Codex performed planning, inspection, and research only. No Furniture application files were modified during the audit or while saving these handoff documents. Specialist agents reviewed creative direction, furniture presentation, Israeli conversion UX, technical architecture, and the proposed design.

## 1. Existing Project Audit

**Recommendation:** transform the site into a precise, image-led product experience for ALUMA's GOREN table, preserving its enquiry funnel and static architecture.

Matching application: `C:\Users\igor\Desktop\gosha\furniture`.

The repository consistently configures `https://table.central-aparts.store`, not the brief's `FurnitureTable.CentralStore.com`. Verify the discrepancy before deployment; do not change infrastructure as a design decision.

The audit inspected source, provenance, 35 full-size render/lifestyle variants, the separate editorial hero, and saved desktop/mobile screenshots. Browser control was unavailable; this was not fresh live-browser certification.

| Area | Actual implementation | Decision |
|---|---|---|
| Framework | Python-generated static HTML, vanilla JS | Keep |
| Build | build.py token substitution, localization, technical SVG generation, dist copy | Improve |
| Main template | site/index.html | Replace composition |
| Active styles | site/assets/styles-next.css | Rewrite coherently |
| Active behavior | site/assets/app-next.js | Preserve contracts, refactor selectively |
| Legacy frontend | styles.css / app.js | Exclude after dependency checks |
| Content | content.json, i18n/he.json, i18n/en.json | Keep structure, audit claims |
| Brand / model | אלומה ALUMA / גורן GOREN | Keep |
| Fonts | Self-hosted IBM Plex Sans Hebrew 400/600/700, Hebrew/Latin subsets | Keep; improve hierarchy |
| States | natural/smoked/white, closed/open as 160/220 | Keep; clarify semantics |
| Images | Procedural renders, five documented AI interiors, separate editorial image | Validate and reart-direct |
| 3D | Custom procedural goren3d.js, interaction-loaded Three.js | Retain tooling, omit public viewer initially |
| Conversion | Callback form and optional WhatsApp; no checkout | Keep and simplify |
| Backend | Python Lambda, DynamoDB, optional SES, admin | Preserve; targeted fixes |
| Analytics | First-party events, optional Meta/Clarity | Preserve; correct meaning |
| Deployment | AWS SAM, S3, CloudFront, scripts/deploy.sh | Preserve infrastructure; repair caching |
| Tests | Playwright, isolated preview, production-oriented smoke suite | Keep; expand relevant coverage |

Repository specifications, not verified manufacturing evidence:
- ₪5,990.
- 160 cm closed, 220 cm open, 90 cm wide, 75 cm high.
- 40 mm top and 60 cm extension.
- Oak veneer over plywood, solid oak edging/legs, black steel beam.
- Natural, smoked, whitewashed finishes.
- Six/ten seats.
- Eight–ten weeks, five-year structural warranty, delivery/assembly inclusions.

No manufacturer photography or validated CAD was found. Source assets are generic texture/HDR resources.

Functional findings:
- WhatsApp/Meta/Clarity and seller identity fields are empty.
- Missing seller facts become placeholders; the production completeness gate claimed in a content comment does not exist.
- WhatsApp clicks fire both Meta Contact and Lead, overstating outcomes.
- **Correction verified directly:** API put_lead DOES store size. It omits lang. Notifications omit size and locale.
- Client/server phone normalization differs.
- Published retention statements differ from actual lead/session lifecycles.
- Mutable asset filenames receive immutable caching. Query-string versions do not solve the current CloudFront/browser caching problem reliably.
- Historical local Lighthouse report, September 8: approximately 3.03 s LCP, 260 ms TBT, 430 KiB transferred. Not current production results.

Uncommitted work existed in locale JSON, package.json, active JS/CSS, index template, and untracked local tests/config/editorial assets/tools. Fable must preserve and integrate existing work.

## 2. What Is Currently Visually Wrong

The current design is restrained, but restraint alone does not make it exceptional.

**Images undermine premium quality.** Grain repetition, uniform surfaces, synthetic contact shadows, and a black beam rendered as a void make the studio assets feel artificial. The underside macro exposes render construction rather than material credibility.

**Product identity drifts.** Editorial hero edge/support appearance differs from procedural views; the closed center seam is not clearly expressed. Reconcile these before reuse.

**The page loses energy after opening.** Room hero → another product stage → repeated frames → drawings → packaging → price justification → specifications → FAQ → large form gives too many elements similar weight.

**Mobile starts too slowly.** Saved 390 px screenshot puts the product around y284 and action around y630. It fits an 844 px capture but is fragile on short screens, browser chrome, or enlarged text.

**Interiors repeat rather than tell a story.** Similar poses with altered fruit/curtains/light do not build stronger product understanding.

**Branding dominates the ending.** Oversized sign-off gives the logo a bigger final moment than the table.

**Copy is stronger than evidence.** "Length" implies distinct products; these are two states of one extending table. Craft, capacity, care, access, delivery, and comparison claims need substantiation.

Change composition, evidence, and priority—not just beige values.

## 3. Research Findings

These references support design judgments, not promised conversion lift. Dates describe documented products/publications/showcases, not assumed website redesign dates.

| Reference | Useful principle |
|---|---|
| [Cassina Vidalenta, design dated 2025](https://www.cassina.com/lu/en/products/vidalenta-table.html) | Product desire alongside materials, dimensions, care, technical resources |
| [B&B Italia 2026 catalogue](https://www.bebitalia.com/it-it/b-b-italia-presenta-il-nuovo-catalogo-2026) | One coherent contemporary home context |
| [Molteni atmospheres](https://www.molteni.it/en/us/atmospheres) | Table anchors the room; whole object, room, and detail have separate jobs |
| [Muuto Earnest extension leaves](https://www.muuto.com/product/Earnest-Extendable-Table-Extension-Leaves?configure=true) | Explicit functional states, materials, dimensions |
| [FRAMA dining tables](https://us.framacph.com/collections/dining-tables) | Quiet presentation with explicit material names and prices |
| [Apple iPhone 17 Pro](https://www.apple.com/iphone-17-pro/) | Distinct visual job per feature and persistent route to action |
| [Current Collection, Siteinspire April 19, 2025](https://www.siteinspire.com/website/13120-current-collection), [storefront](https://currentcollection.com/) | Editorial product display and direct action can coexist |

Conclusions:
1. Premium furniture depends on believable scale, material behavior, and context.
2. Useful interaction resolves uncertainty: state comparison, finish selection, enlargement, dimensions.
3. Hebrew determines composition; isolate mixed-direction content deliberately. [W3C guidance](https://www.w3.org/International/articles/inline-bidi-markup/Overview.en.php?changelang=en)

Keep IBM Plex's Hebrew/Latin support and relevant OFL notices. [Official project](https://github.com/IBM/plex/), [license](https://github.com/IBM/plex/blob/master/LICENSE.txt).

Use field p75 LCP ≤2.5 s, INP ≤200 ms, CLS ≤0.1; local Lighthouse cannot establish field results. [Web Vitals thresholds](https://web.dev/articles/defining-core-web-vitals-thresholds).

Accurate operator/data-use information must accompany collection. Do not invent identity or certify legal compliance from a redesign. [Israeli Privacy Protection Authority guidance](https://www.gov.il/BlobFolder/legalinfo/duty_to_notify/he/notify13.pdf).

## 4. Three Creative Directions

| Direction | Experience | Strength | Weakness | Verdict |
|---|---|---|---|---|
| The Everyday Monument | Exact large studio portrait, clear purchase context, one home, informative details | Recognition, material confidence, mobile feasibility | Generic beige risk without disciplined composition | Selected |
| After Hours | Dark gallery, spotlit oak, cinematic crops | Drama | Hides beam, distorts finish judgment, exposes CGI, mobile difficulty | Reject as main funnel |
| At the Table | Documentary meals/people/rituals/maker | Authentic emotion | Needs real photography and verified stories | Later genuine campaign |

The Everyday Monument is an internal direction name, not customer-facing branding.

## 5. Selected Creative Direction

Feeling: precise, tactile, useful, quietly confident, warm through real material.

Signature: uninterrupted studio stage; complete top/trestle/beam silhouette; compact price/action band beneath. This replaces the current dominant split hero.

Keep אלומה / ALUMA and גורן / GOREN. FurnitureTable is a category label; CentralStore suggests general retail. Preserve domain/legal operator distinction. Refine vector wordmark scale and clear space; remove huge footer logo. No trademark-clearance claim.

| Role | Color |
|---|---|
| Main | #F4F1EA |
| Alternate mineral | #E7E3DA |
| Input/light | #FFFFFF |
| Text | #252720 |
| Secondary | #62645C |
| Decorative rule | #D1CEC5 |
| Functional border | #77796F |
| Primary action | #493339 |
| Hover | #36252A |
| On-primary | #FFFFFF |
| Error | #A52C2C |

Restrained wine action distinguishes interface from oak. Use sparingly, verify contrast. No dark mode, decorative gradient, grain overlay, or tinted-card system.

IBM Plex Sans Hebrew: hero 48–64 desktop / 34–40 mobile; section headings 34–44 / 26–32; body 18 / 16–17; labels 13–14; price 30–36. Weights 400/600, 700 sparingly. Hebrew tracking zero, headline leading 1.15–1.22, body around 1.6.

Desktop 12 columns / 24 px gap / max 1440 / 32–64 gutters. Mobile four-column alignment / 20 gutters / 12 gaps. Section spacing 88–120 desktop, 48–64 mobile. Open layouts and rules; reserve split layout for configuration/details, not every section.

Hero photography: 45–60 mm feel, camera 1.0–1.15 m high, neutral 5000–5600 K daylight, product 80–86% width, protected ends/feet/shadow, soft fill under top. No wide-angle near-leg exaggeration. Home: believable apartment, restrained furnishings, no mansion/props cliché. Never mirror photos for RTL.

## 6. Page Architecture

| Section | Question / purpose | Composition and behavior |
|---|---|---|
| Masthead + portrait | What is this; do I want it? | Compact heading, uninterrupted stage, price/action band; mobile complete table then price/CTA; immediate visibility; picture/HTML |
| One table, two states | How does it adapt? | Matched fixed-scale image, explicit closed/open controls, labeled finishes; mobile controls below; decoded crossfade and existing state persistence |
| At home | Can I imagine it here? | One substantial interior, dedicated mobile crop, honest caption, optional dimensions anchor |
| Materials | What am I paying for? | Two unequal desktop details, sequential mobile; edge/chamfer and trestle/beam; fact-led copy; real source or labeled diagram |
| Dimensions/fit | Will it fit? | Top/front drawings and text; mobile readable stack; optional estimator disclosure, numerical clearances not guarantee |
| Offer/process | Cost and next step? | Price, confirmed inclusions/timing, callback → written proposal → decision; no checkout fiction |
| FAQ/enquiry | Remaining uncertainty and action? | Focused questions and short form; name/phone/callback consent, optional city/comment, separate unchecked marketing; existing endpoints/error states |
| Seller footer | Who is responsible? | Modest logo, actual operator/contact, legal/locale links, prelaunch/image disclosure |

Sticky is a shortcut: after hero action leaves, hide at form/keyboard; avoid extra pitch.

## 7. Visual Asset Manifest

Evidence hierarchy: manufacturer photos/measurements → validated CAD → provisional repo geometry/spec → generated illustration. A generated image never validates another.

All assets preserve outline, thickness, seams, grain, support positions, floor contacts, beam, finish, proportions. No invented joints/hardware/extra legs/leaves/solid-wood claims/text/people/certifications. Prefer locked product layer with environment editing. Render-derived outputs remain labeled visualizations.

| ID | Purpose and output | Art direction |
|---|---|---|
| A1 goren-studio-hero-natural-closed | Hero, desktop ~2.2:1 1200/1600/2000; mobile dedicated 3:2 640/800/1000 | Empty neutral studio, 50 mm feel, 1.05 m camera, soft daylight, complete silhouette 80–86% width |
| A2 goren-compare-{tone}-{state} | Six states, matched 3:2 800/1200/1600 | Same camera/light/floor/scale; frame for open state; closed must look shorter; deterministic rendering or matched photos |
| A3 goren-home-daylight | Desktop 3:2 800/1200/1600; mobile 4:5 640/800/1080 | Modest apartment, plaster/light stone, 50 mm feel, 1.15 m camera, table dominant, credible far-side chairs only |
| A4 goren-edge-detail | Square 640/1000 | Real or validated detail, 85–100 mm feel, raking light, no fabricated material/joinery |
| A5 goren-frame-detail | 4:3 640/1000 | Low close three-quarter, filled underside, actual connected structure |
| A6 dimensions | Responsive SVG + HTML | Orthographic approved dimensions; no image generation or ergonomic guarantee |
| A7 finishes | Three 160/240 crops | Approved A2 or actual samples, same exposure, text/selection marker |
| A8 social | 1200×630 | Approved A1 plus vector/code lettering; no new product or generated text |
| Final form | Optional reuse of A3 | No extra decorative scene |

Detailed executable prompts, realism requirements, prohibitions, and fallback rules are fully reproduced in the independent FABLE-IMPLEMENTATION-PROMPT.md, section G. These prompts are also summarized here for review:

- **A1:** exact natural closed GOREN alone on pale neutral studio floor/background, corrected 50 mm three-quarter at 1.05 m; both ends/edge/trestles/contacts/beam visible; about 83% width; soft camera-left daylight and underside fill; no props/haze/vignette/exaggerated grain. Mobile recomposed without cropping feet/ends.
- **A2:** locked camera/focal length/floor/exposure/light and physical scale; exact supplied finish and documented closed/open geometry/seams; no independent auto-fit or invented mechanics.
- **A3:** locked approved table in believable apartment, neutral plaster/stone/terrazzo, same light direction; 50 mm at 1.15 m; 65–75% width; at most two credible far-side chairs and one small cup; no people/villa/arches/olive-tree cliché/clutter. Simplify scene if product cannot be preserved.
- **A4:** crop/color-correct actual corner/underside, raking light, enough depth; keep actual grain/material boundaries/thickness; dust only; no pores/joints/hardware invention. Inadequate evidence → labeled construction diagram.
- **A5:** actual trestle/top/beam relationship, low three-quarter, soft underside fill; preserve documented attachment; no invented fasteners/brackets/floating parts. Inadequate evidence → labeled illustration.
- **A6:** vector top/front dimensions from shared data; readable numerical runs isolated from Hebrew units; no geometry mirroring; clearances labeled estimates.
- **A7/A8:** derive approved assets; no new geometry, finish, or generated lettering.

Record source/reference version, tone/state, crop, dimensions, format/bytes, localized alt/caption, verification status, acceptance/rejection reason for every asset.

## 8. 3D & Motion Specification

Select **Option C: high-quality stills plus restrained interface motion**.

| Option | Decision |
|---|---|
| WebGL | Useful only after geometry validation; retains GPU/loading/a11y/maintenance cost; keep source, omit public viewer |
| Scroll frame sequence | Many assets and interaction complexity, no source accuracy benefit; reject |
| Stills + limited motion | Predictable mobile quality and consistency; selected |
| Hybrid film/3D | Later verified enhancement, not completion dependency |

No React Three Fiber or WebGPU requirement. No disabled rotate teaser.

Hero/title/price/CTA immediate. State/finish decoded crossfade 180–240 ms. Detail/context entrances at most 12 px plus opacity, 300–400 ms once. Buttons 120–160 ms. Sticky 160–200 ms, no bounce. User-controlled gallery. Dimension updates immediate; no invented mechanism. Reduced motion removes translation/parallax/counting/automatic camera/smooth-scroll dependency. No table moving independently of shadow, masks hiding information, or split-letter Hebrew.

## 9. Mobile Strategy

Design at 390×844 and 430×932; challenge at 390×700, 360×667, enlarged text, and 320 px reflow.

390×844 approximate allocation: header 56; identity/headline 90–110; product media 235–275; price/action/context 120–145. Target complete CTA by y620 at default text without clipping or tiny controls.

Primary callback, optional configured WhatsApp. Button at least 48 px, practical hits 44 px, input text 16 px. Complete silhouette, no horizontal overflow or scroll hijacking, state buttons without drag dependency. Sticky safe-area/consent/keyboard coordination. Phone LTR, user text dir=auto, isolated prices/dimensions. No mandatory 3D. Content remains readable when scripts/images fail.

## 10. Technical Architecture

Keep Python build and vanilla frontend; no framework/router/hydration migration.

Modify main template, active CSS/JS, locale JSON, build.py, thanks page, shared legal/accessibility styling, tests/redesign.spec.js, and deploy script caching preparation. Backend changes limited to identified functionality/measurement gaps. Do not deploy.

Add product manifest and approved assets under site/assets/product, source/approval records under assets-src/product, stdlib helpers only if useful, focused regression tests.

Retire public viewer/loading, redundant unsupported room scenes, giant sign-off, repeated price cards, primary-story packaging drawing, and unused legacy CSS/JS after reference checks. Keep useful renderer/source tooling and packaging facts where relevant.

Preserve window.FX, key parity, Hebrew/English and thanks/legal routes, endpoints, form IDs/state values. Share dimensions across code/copy/drawings. Logical CSS and coherent DOM order. Hashed paths for static/dynamic assets, manifest-aware selection, font/CSS rewriting, revalidating HTML. Accurate canonical/hreflang/JSON-LD with no invented stock/ratings/seller.

Image tooling references night/imagegen: adapt furniture-local paths before use to avoid cross-project changes.

Proposed budgets: initial mobile first-party ≤400 KB; mobile hero AVIF ≤150 KB, desktop ≤250 KB; compressed CSS ≤20 KB; JS ≤35 KB; initial fonts ≤70 KB; ordinary page scroll ≤2.5 MB excluding deliberate zoom/variants. No initial WebGL/HDR/video. One prioritized responsive hero, lazy lower images, reserved dimensions, selected fonts only. Report third-party cost separately.

## 11. Implementation Order

1. Verify identity/instructions/current work.
2. Record contracts; isolated preview/tests.
3. Evidence/claims register.
4. Approve studio composition and mobile framing.
5. Tokens/type/masthead/hero/action band.
6. State/finish module.
7. One home and justified details.
8. Dimensions/process/FAQ/form.
9. Locales and attribution.
10. Targeted API/event/phone fixes.
11. Motion/fallbacks.
12. Hashing/publication/readiness checks.
13. Run, visually inspect, test, measure, iterate.
14. Deliver working preview, evidence, unresolved owner/manufacturer facts.

## 12. QA / Definition of Done

Visual: desktop 1440×900/1920×1080, mobile 390×844/430×932/short viewport, both locales, full page after visiting lazy sections; product consistency; immediate comprehension; no generic cards/fake trust/giant logo.

Functional: all six configurations/persistence; one product semantics; CTA routes; validation/mock success/422/429/500/offline/retry; no false success or duplicate conversion; WhatsApp absent if missing; locales/legal/thanks; selection and attribution preserved.

Accessibility: keyboard/focus/dialog return, labels/alt, manual RTL, 200% text zoom and narrow reflow, reduced motion, storage/image/script failure; sticky never obscures input/consent; no unexpected console/missing assets.

Performance: budgets, single prioritized hero, no graphics runtime, cold-cache mobile test conditions recorded, field metrics not fabricated from lab.

Readiness: separate completed design from launch readiness. Seller facts, product evidence, and operating terms remain explicit blockers to public launch if missing. No placeholders/fabrications or unverified production-ready claim. Do not run production smoke suite or send leads/messages while testing.

## 13. FABLE IMPLEMENTATION PROMPT

The complete independent implementation prompt is saved in:

`C:\Users\igor\Desktop\gosha\handoffs\furniture\FABLE-IMPLEMENTATION-PROMPT.md`

It repeats all operational requirements, asset prompts, technical decisions, mobile/RTL rules, budgets, and acceptance criteria without requiring this document or the previous conversation. It explicitly instructs Fable to implement, run, visually inspect, fix, test, iterate, and finish.

To start Fable, paste the contents of START-FABLE.txt from this folder into the Fable / Claude Code conversation with access to this local workspace.
