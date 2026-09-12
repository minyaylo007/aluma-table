# DECISIONS — night run 2026-09-01 → 2026-09-02

Every entry is a call I made without asking, because rule §1 forbids asking. Format: decision → why → how to reverse it.

---

**D-001 · Subdomain = `table.central-aparts.store`**
First preference in the brief; it was free in the zone. Reverse: change the alias record + CloudFront alias + cert.

**D-002 · New isolated SAM stack `fx-table`, not an addition to the `aparts` stack**
The `aparts` stack holds ~30 production secrets in `samconfig.toml` and serves live guest traffic through a Lambda alias. Touching it to add a landing page is an unnecessary risk for zero gain. Reverse: n/a, delete the stack.

**D-003 · Static site on S3+CloudFront, API on a small Lambda Function URL behind the same distribution**
Lighthouse ≥ 90 mobile is a hard requirement; a Lambda-rendered page cannot guarantee LCP < 2.5 s from cold. Same-origin API means no CORS and no preflight cost. This is the exception the brief explicitly permits.

**D-004 · Router (cc10x) AskUserQuestion gates skipped**
The global CLAUDE.md routes every dev task through cc10x, and that router demands clarification questions before BUILD. The night brief's rule §1 says a question to the owner is a failed night. Rule §1 wins (brief §11). The rest of the router contract — memory files, review + silent-failure + integration-verifier passes — is honoured.

**D-005 · TaskCreate/TaskList unavailable in this harness**
The router's task ledger is emulated with `night/PLAN.md` + `night/STATE.md` + TodoWrite. No behavioural change.

**D-006 · Zero paid services**
Everything used is already in the account or free tier: S3, CloudFront (1 TB/mo free tier), Lambda, DynamoDB on-demand, ACM, Route53 records in an existing zone. Expected steady-state cost of this project at smoke-test traffic: well under $1/month. No Amplify, no ECS, no NAT, no WAF (WAF is ~$5-8/mo minimum — deliberately skipped, noted in REVIEW).

**D-007 · No fabricated social proof of any kind**
No reviews, no "3 left", no press logos, no ratings, no stock photos of families. The trust argument on the page is: named factory, real spec numbers, a real warranty, an honest pre-launch status, and a price shown with VAT. Where a real site would put testimonials, we put the manufacturing story.

**D-008 · Product photography does not exist, so the site ships with vector illustration**
Every image on the page is hand-authored SVG (the table in three oak tones, top views at 160 and 220, the flat-pack boxes, the leg/beam detail). They are drawn to the real proportions from the frozen spec. `night/RENDER-BRIEF.md` specifies the seven photoreal renders that replace them, with exact framing and prompts. Swapping is a file replacement, not a code change.

**D-009 · Analytics: first-party events into DynamoDB, Meta Pixel + Clarity only if their IDs are provided via env**
No third-party tag is hard-coded. Without `META_PIXEL_ID` / `CLARITY_ID` the site is fully functional and simply loads no third-party script. This also means the site ships tonight with zero external trackers, which is the honest default.

**D-010 · Cookie/analytics notice, not a GDPR consent wall**
Israel is not under GDPR here and the brief asks for a light touch. One dismissible bar, a link to the policy, and Meta Pixel / Clarity are loaded **only after** the bar is acknowledged (accept or dismiss) — before that, only first-party events are recorded. First-party events use a random session id in `sessionStorage`, no cross-site identifier, and the IP is stored only as a salted hash.

**D-011 · IP is never stored. `ip_hash = sha256(salt + ip)[:32]`, salt from env**
Enough to count uniques and catch abuse, useless as an identifier if the table leaks.

**D-012 · `?me=1` sets a 1-year cookie `fx_me` that excludes the visitor from analytics; bot user-agents are filtered server-side**
Owner's own visits and Meta's crawler must not pollute a 20-lead dataset.

**D-013 · Price shown = one number, with VAT, marked מחיר השקה**
The exact figure is confirmed against the market research before the final deploy; the corridor is ₪5,490–7,490. If research says the honest median sits outside that corridor, the price stays inside it and the conflict is written up in REVIEW rather than silently overridden.

**D-014 · The lead form asks for name, phone, city, colour, free comment, and one consent checkbox**
No email field: Israelis convert on phone/WhatsApp, and an email field on mobile costs conversions. The consent text is versioned (`consent_text_version`) so a later wording change stays auditable.

**D-015 · Lead notification e-mail is best-effort and off by default**
Sending mail needs SES out of sandbox, which needs a support request and an owner decision. Without `LEAD_NOTIFY_EMAIL` the API records the lead and skips notification; the admin page is the reliable read path. Written up in REVIEW.

**D-016 · Admin is HTTP Basic auth over HTTPS, credentials from env**
Cheapest thing that is not "public". If `ADMIN_USER`/`ADMIN_PASS` are unset the admin route returns 503 rather than opening. No Cognito — that would be a day of work for a dashboard only one person opens.

**D-017 · The apartments system is proven untouched by running its pytest suite before and after the night and diffing the result**
Recorded in STATE.md.

**D-018 · `furniture/` gets its own git repository**
`gosha/` itself is not a git repo, and `aparts/` and `aparts-v2/` are separate repos that must not receive night commits. A fresh repo inside `furniture/` gives the brief's 30-minute commit+tag cadence without touching anything of the owner's. No remote is configured — nothing leaves the machine.

**D-019 · Hebrew is written by a dedicated native-editor pass, not by the builder**
Every user-visible string goes through a separate review whose only job is grammar, gender agreement, register and naturalness. Findings are applied before the final deploy and the pass is logged.

**D-020 · WhatsApp number is not invented**
Without `WHATSAPP_NUMBER` the WhatsApp buttons are replaced by the lead form CTA rather than pointing at a fake number. The number is an owner input, listed in REVIEW.

**D-021 · API moved from a Lambda function URL to an API Gateway HTTP API**
Function URLs in this account return `403 Forbidden` to every caller. Verified: public
(`AuthType: NONE`, `Principal: "*"`, `lambda:FunctionUrlAuthType: NONE`) and CloudFront OAC
(`AuthType: AWS_IAM`, `Principal: cloudfront.amazonaws.com`, correct `SourceArn`) both refused,
policies read back byte-identical to the working `aparts-api` policy, URL deleted and recreated,
permissions re-added by CLI, and **zero invocations** ever reached the function (CloudWatch
confirms only my manual `lambda invoke`). The account is not in an AWS Organization, so no SCP
or RCP explains it. Root cause unknown; I stopped digging because the night has a deadline and a
better road existed. HTTP API uses the same payload format 2.0, so `handler.py` did not change.
Cost: free tier, then $1.00 per million requests — a smoke test will not reach a dollar.
**For the owner:** this is worth a support ticket if you ever want function URLs in this account.

**D-022 · Price set at ₪5,990, not the brief's ₪6,490**
The brief permits ₪5,490–7,490 with justification. Market research (`night/research/market-il.md`,
20 product pages with prices): the median for genuine-oak 160–180 cm extendable tables is
₪6,300–6,450 incl. VAT. Our top is oak veneer with a solid-oak edge, not solid oak throughout, and
our lead time is 8–10 weeks against Nature Furniture's 21 days at ₪6,885 — so sitting exactly on the
median is the wrong place to stand. Worse, ₪6,490 appears to be Beitili's *crossed-out list price*
for a comparable veneer table that actually sells at ₪4,543; adopting a competitor's fake anchor as
our real price is a self-inflicted wound. ₪5,990 clears the ₪6,000 barrier, reads as a real number
rather than a discounted one in a category that runs on permanent fake discounts, and leaves room to
raise later. One number to change: `PRICE` in `furniture/content.json`.

**D-023 · The brief's "looks like a ₪10–12k table" claim is not on the page**
It is an unverifiable comparison about other people's products, and Israeli consumer law §2
(misleading advertising) binds advertising before any sale. Replaced with three claims that are
each checkable against the spec: real oak rather than a wood-look print, the 60 cm leaf stored
inside the table, and two flat boxes that fit through a door. Rule §4 outranks a suggested line.

**D-024 · Marketing consent is a second, separate, unticked checkbox**
Israeli spam law §30א carries ₪1,000 per message in statutory damages with no proof of harm, and
bundling marketing consent into the contact consent invalidates it. The form therefore has two
lines: a required "call me about this enquiry" and an optional "you may also send me launch news".
They are stored as separate fields so a later blast can be filtered on the right one.

**D-025 · The accessibility statement admits what was not done**
It states that no human has yet tested the site with a screen reader, rather than claiming
NVDA/JAWS/VoiceOver compatibility that was never verified. A false accessibility statement is worse
than a modest one, and rule §4 applies to legal pages too.

**D-026 · Price-justification block and a Ukraine FAQ added; one invented detail caught and removed**
The buyer critique's sharpest unclosed point was that ₪5,990 never explains itself. Added a
three-column "what is included / where we saved / where we did not" block, every line checkable
against the frozen spec, naming no competitor. While writing it I typed "extension on steel
runners" — the spec says nothing about runners. Caught on re-read and replaced with what the spec
does say (the leaf is stored inside and pulled out one-handed). Logged because it is exactly the
failure mode rule §4 exists for, and it happened to me at 01:30 on a line I was confident about.
The Ukraine FAQ answers the risk question with what is true today — no payment on the site, terms
in writing before the first shekel — and promises nothing that is undecided.

**D-027 · Country of origin removed from the site, at the owner's instruction (02:00)**
The written brief (§4, §5.1.5) asked for an honest block about the Impuls workshop in
Chernivtsi. At 02:00 the owner said we had agreed not to state Ukraine/Chernivtsi on the site.
The live instruction wins. Every mention — the story section, two FAQ answers (including the
Ukraine-risk one added an hour earlier), the `FACTORY` tokens, the A4 ad copy — is gone.
What remains is true and non-geographic: a family workshop, European oak, flat-pack by design.
Nothing claims the table is made in Israel; the site simply does not say where it is made.
Flag for the owner: Israeli consumer regulations require country-of-origin marking on imported
goods **at the point of sale**. That obligation does not attach to a lead-gen page with no sale,
but it will attach the day a contract is signed — a line for the written offer, not the site.

**D-028 · Site design to be rebuilt after a 40-site teardown, per the owner (02:05)**
Owner's verdict on the drafting-sheet concept: "just text", far behind the field visually.
Launched a 49-agent workflow — 4 scouts, 40 per-site teardowns with screenshots (US / IL / EU /
UA), 4 regional syntheses, 1 design direction. Meanwhile building a real 3D model of the table
(Three.js, rendered headlessly at build time to static WebP/AVIF, so the page ships images not a
600 KB library) — the visuals are needed whatever the synthesis says. A bilingual HE/EN site is
assumed from the owner's message; the voice transcript there is garbled and this is flagged.

**D-029 · Process crash mid-morning; what was lost and how it was recovered (11:20)**
The Claude Code process exited while a 30-image render batch and the 49-agent research
workflow were running. Losses: the render harness file had been corrupted by my own edit a
minute earlier (a slice-replace that matched the wrong anchor and wrote whitespace); the
workflow journal had a trailing line of NUL bytes; 20 of 49 agents had started, 5 had
finished. Recovery: harness rewritten as a thin layer over the shared 3D module (better
architecture than before — one model, two consumers); journal cleaned with a backup kept;
workflow resumed from the run id so the five finished agents return from cache. Nothing on
prod was affected at any point.

**D-030 · Cookie bar removed unless a third-party id is configured**
The second buyer critique made a point I should have made myself: with no Meta Pixel and no
Clarity id, nothing third-party ever loads, the analytics are first-party with hashed IPs, and
Israeli law does not require a banner for that — yet a 129 px dark bar sat on every screen and,
after the round-1 fix, kept the sticky CTA hidden for anyone who never taps cookie bars. It now
appears only once an id is present, which is exactly when it starts to mean something.

**D-031 · The critic's argument for putting the origin back is recorded, not acted on**
CRITIQUE-2 argues that scrubbing the country reads as evasion, that the deleted Ukraine FAQ
was the most trust-building paragraph on the page, and that Israeli labelling rules put the
country of origin on the carton anyway, so the buyer learns it at delivery. It is a strong
argument. It is also the owner's explicit instruction (D-027), given after that FAQ existed.
Not reversed. Surfaced here and in the report so the owner decides with the argument in view.

**D-032 · The rebuild ships as a preview at /next before it replaces the live page**
The live page keeps working while the new one is built; the owner can open
https://table.central-aparts.store/next on a phone and judge it against the old one, and the
switch is one file rename in the build. The new page is image-led on the 3D renders, bilingual
by construction (one template, `{{t.key}}` strings, `/en/` output), and keeps every honesty
rule and every analytics event of the current page. It will be re-checked against the 40-site
design synthesis when that lands, then promoted.

**D-033 · The rebuild replaced the live page (12:10)**
Promoted after the smoke suite passed on the preview and the owner's four points were met:
image-led on real 3D renders, bilingual (`/` Hebrew, `/en/` English, one template), no
country of origin, an interactive model on demand. The 40-site synthesis did not finish
(session limit) — 19 teardowns did, and their digest was applied by hand: price in the button,
sticky-split story, spec sheet, two-state configurator, one accent, delivery window as dates,
a made-to-order line above the CTA, a render gallery. The workflow resumes when the limit
resets; whatever it adds goes in as a refinement pass, not a rebuild.

**D-034 · Session-limit failure of the research workflow, and what survives it**
26 of 46 agents died on "session limit". The script was patched so a region whose synthesis
fails no longer nulls the global step, and the journal keeps the 20 completed results for a
cached resume. Cost of the failed run: 2.9 M tokens. Lesson recorded in memory: a 40-agent
fan-out on one session is a limit risk; scout first, then tear down in batches of ten.

**D-035 · Design skills installed at user scope** (2026-09-07)
Installed `modern-web-guidance@claude-plugins-official` (Chrome team's best-practice guides, used via `npx.cmd modern-web-guidance search/retrieve`) and `example-skills@anthropic-agent-skills` (frontend-design v2, canvas-design, theme-factory, webapp-testing…); marketplace `anthropic-agent-skills` added. Skipped `superdesign` (hosted canvas, needs an account), `ui-theme-designer` (SAP-only), `canva`/`adobe-for-creativity`/`runway-api`/`togetherai` (external accounts or paid APIs).

**D-036 · AI image generation: Bedrock Stability only, capped, gated** (2026-09-07)
Nova Canvas is not usable in this account (legacy/verification wall). Stability image services work in us-east-1 via `us.stability.*` inference profiles. Test at control_strength 0.7 redesigned the legs (unusable); 0.85–0.95 kept the structure but recoloured the oak trestles black and invented a cable grommet. Decision: allow ≤70 Bedrock calls (≈$7 worst case, logged in night/imagegen/CALLS.jsonl), every accepted image must pass a per-image honesty gate against the frozen spec, and every published AI image is labelled "הדמיה בעזרת בינה מלאכותית" / "AI-assisted visualisation"; renders stay the authoritative product images.

**D-037 · Direction pass before re-render** (2026-09-07)
The frontend-design v2 skill names cream ground + serif display + terracotta accent as the most common tell of a generated page; the current site is exactly that (paper #e9e6de, Frank Ruhl Libre, #b4552d). A judge-panel workflow (3 directions → 3 lenses → synthesis → logo panel → page build → critic) chooses the new tokens; the render backdrop must equal the chosen page ground, so `tools/render3d.js --bg` is added and renders are re-run after the direction is final.

**D-038 · Source textures are CC0 Poly Haven, kept out of git** (2026-09-07)
`assets-src/` holds the PBR maps and HDRI (gitignored); `assets-src/SOURCES.md` + `tools/fetch_assets.py` make them reproducible. Baked viewer textures under `site/assets/textures/` are small derived files and are committed.
