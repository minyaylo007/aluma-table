# PLAN

Priority order fixed by the brief: infra → working honest site on prod → analytics → polish → Meta → extras.

## Done
- [x] P0 Recon, architecture notes, decisions log
- [x] P0 ACM cert + Route53 subdomain
- [x] P0 Isolated SAM stack (Lambda, 3× DynamoDB, S3, CloudFront)
- [x] P0 Research: market, landings, RTL/Hebrew, legal, Meta ads, naming
- [x] P1 Site v1 on prod, HTTPS, Hebrew, RTL, honest, with form
- [x] P1 Analytics API + event taxonomy + lead capture + honeypot + rate limit
- [x] P1 Admin dashboard with funnel, leads, status editing
- [x] P1 Legal pages: privacy, terms, accessibility
- [x] P1 aparts baseline test suite recorded (3055 passed)

## Done (continued)
- [x] P2 Playwright smoke suite — 27 tests, all green on prod
- [x] P2 Lighthouse mobile — 100 / 100 / 100 / 100, LCP 1.31 s
- [x] P2 Screenshots at 360×800 / 390×844 / desktop, no horizontal scroll
- [x] P2 Hebrew native-editor pass — 76 corrections applied
- [x] P2 OG image for WhatsApp link previews
- [x] P3 Critic pass — `night/CRITIQUE-1.md`; 3 real defects found and fixed, 5 regression tests added
- [x] P3 API locked to CloudFront only (shared secret header; direct execute-api now 403)
- [x] P3 `night/RENDER-BRIEF.md`
- [x] P4 Meta pack — campaign-plan, ads, creative-brief, setup-checklist, go-no-go
- [x] P4 daily-report script + prompts/daily-analysis.md
- [x] P5 MORNING-REPORT.md + REVIEW
- [x] P5 aparts suite re-run (3054/1 — pre-existing UTC-vs-local date bug, analysed in the report)

## Deliberately not done
- **Ads not launched.** The brief says materials only, and the site still shows `להשלמה`
  markers. Running paid traffic at a page that cannot be contacted would waste the budget.
- **No WAF.** ~$5–8/month minimum, over the zero-cost rule. Noted in REVIEW.
- **No SES / lead notification email.** Needs a support request to leave sandbox and an owner
  decision on the sending address. The admin dashboard is the reliable read path.
- **No CAPI (server-side Meta events).** Not needed for a ₪1,000 instant-form test; noted for
  April 2026 when conversion-leads optimisation starts requiring it.
- **The apartments test-suite bug was not fixed.** It is outside `furniture/` and `night/`,
  and rule §8 says those files are not mine to touch. Diagnosed in MORNING-REPORT.md §8.
- **A second critic round.** One round ran, its findings were applied and covered by tests.

# Day 2 — 2 September (owner's redirection at 02:00)

## Done
- [x] Origin (Chernivtsi / Ukraine / Impuls) removed everywhere on the site and in ad copy
- [x] 3D model of the table (Three.js, spec in metres) + headless render pipeline (30 masters → WebP/AVIF, auto-cropped)
- [x] On-demand interactive viewer (drag + keyboard orbit), three.js loaded only on tap
- [x] Sheaf mark for אלומה
- [x] Design plan (`night/DESIGN-PLAN.md`) from the owner's brief + finished teardowns
- [x] Rebuilt page, previewed at /next, promoted to / — Lighthouse 100/100/100/100 (he), 98/100/100/100 (en)
- [x] Bilingual: one template, `i18n/he.json` + `en.json`, `/en/` via CloudFront index rewrite, hreflang, EN legal pages
- [x] From the teardown digest: price in the button, made-to-order line, delivery window as dates, render gallery, sticky-split story, spec sheet
- [x] Critique-2 defects fixed (empty-submit UX, cookie bar only when needed, fit-rule conflict, price wording) + 18 Hebrew corrections
- [x] Ad creative regenerated on the renders (`night/meta/creative/`)
- [x] OG card on the new design
- [x] Smoke suite retargeted, EN tests added — 30/30
- [x] Crash recovery: harness rebuilt on the shared model, workflow journal cleaned, resumed

## In progress
- [ ] Research workflow resumed after the session-limit reset (20/46 cached; remaining teardowns + 4 regional syntheses + design brief)
- [ ] Hebrew native-editor pass on the new strings (agent running, writes HEBREW-EDIT-2.md and applies to he.json)
- [ ] Critique-3 on the rebuilt page (agent running, writes CRITIQUE-3.md)

## Next, in order
- [ ] Apply critique-3 defects and the editor's corrections; redeploy; re-run suite + Lighthouse
- [ ] Read DESIGN-SYNTHESIS.md when it lands; apply as a refinement pass (palette/type/logo/sections), not a rebuild
- [ ] Regenerate OG + ad creative if the palette moves
- [ ] Final report section for the owner; commit; tag day2-final

## Deliberately not done
- No photoreal renders beyond the parametric model (no image generator available; RENDER-BRIEF updated)
- No country of origin (owner's instruction; critic's counter-argument recorded in D-031)
- No ads launched; no paid services; no changes to the apartments system
