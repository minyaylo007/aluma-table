# STATE — night run 2026-09-01 → 2026-09-02

Written after every iteration. If the run dies, this is where it resumes.

> **Masked on 2026-09-12, before publication:** the AWS account number inside the bucket name is
> replaced by `000000000000`. The stack is deleted (`docs/AWS-TEARDOWN.md`); the original is in the
> private archive `aluma-table-archive-2026-09`.

## Live now
- **Site:** https://table.central-aparts.store — HTTP 200, Hebrew, RTL.
- **API:** `/api/fx/health`, `/api/fx/event`, `/api/fx/lead` — all verified 200 through CloudFront.
- **Admin:** https://table.central-aparts.store/admin — signed-cookie login, credentials in `night/CREDENTIALS.md`.
- **Stack:** `fx-table` in eu-central-1. Distribution `E21KNA4YOX9CIB`. Bucket `fx-table-site-000000000000`.
  HTTP API `r7jel27uma`. Tables `fx_events`, `fx_leads`, `fx_sessions`.
- **Repo:** `furniture/` — local git, no remote. Tag `night-v1`.

## Untouched, as required
- `aparts` pytest baseline **before** the night: **3055 passed** (12m41s). Re-run at the end must match.
- No file outside `furniture/` and `night/` was modified, except the additive
  `.claude/cc10x/` memory files the global CLAUDE.md router requires.

## Iteration log

### 20:32 → 21:20 · Phase 0 + infra + first deploy
- Recon written to ARCHITECTURE-NOTES.md. Subdomain `table.` was free; ACM cert issued in ~2 min.
- Six research agents run in parallel; all six reports landed in `night/research/`.
- SAM stack created: DynamoDB + Lambda + S3 + CloudFront + OAC + Route53 alias.
- Site built and deployed. Static side green on the first try.
- **Blocker hit and cleared:** Lambda function URLs in this account answer 403 to
  every caller — public (`AuthType: NONE`) and CloudFront-OAC (`AWS_IAM`) alike,
  with textbook-correct resource policies and **zero invocations** reaching the
  function. The existing `aparts-api` function URL works, so it is not an account-wide
  block, and there is no AWS Organization, so no SCP/RCP. Root cause not identified.
  Worked around by moving the API onto an API Gateway HTTP API (same payload v2.0
  shape, handler unchanged). See DECISIONS D-021.
- End-to-end verified on prod: event batch written, lead validation rejects a bad
  phone, honeypot silently absorbs a bot, good lead stored, admin login + dashboard render.
- Committed, tagged `night-v1`.

## Next
See PLAN.md. Immediate: screenshots and critique, Playwright smoke suite, Lighthouse,
OG image, Hebrew native-editor pass, Meta materials, daily-report script.

### 21:20 → 00:55 · API rebuild, design fixes, Lighthouse, Hebrew, Meta
- **API rebuilt twice.** Lambda function URLs turned out to be unusable in this account
  (D-021). First moved to CloudFront OAC with `AWS_IAM`, which failed the same way, then to an
  API Gateway HTTP API, which worked immediately. Handler unchanged throughout — HTTP API and
  function URLs share payload format 2.0.
- **Admin auth rewritten** from HTTP Basic to a signed cookie, because OAC signing owns the
  `Authorization` header. Better anyway: `/admin/login`, HMAC token, 12-hour expiry, HttpOnly.
- **API locked to CloudFront.** The `execute-api` hostname is public, so CloudFront now injects
  a shared secret header and the API rejects anything without it. Verified: direct = 403, via
  CloudFront = 200. Rate limits and the bot filter can no longer be bypassed.
- **Playwright smoke suite: 22 tests, all green** against prod. Two real bugs found by it —
  a test-lead run consuming a real visitor's rate-limit quota, and a body-read race.
- **Drawings fixed after looking at screenshots**: grain ran past the closed tabletop, the seam
  was chamfered on both halves so a closed table had a notch down the middle, and the plan
  viewBox was sized to the table rather than the chairs, so every chair was cropped.
- **Lighthouse mobile 100 / 100 / 100 / 100** (was 98/94/100/100). Contrast token failed AA at
  11 px; the three claims were `h3` under an `h1`.
- **Hebrew native-editor pass: 76 corrections applied.** Including a word I had invented
  (`סקוסית`), and two things that were not language problems: the FAQ promised return terms
  that `/terms` did not contain, and the retention clause deleted the data twice.
- **Meta pack written** — campaign plan, ads, creative brief, setup checklist, go/no-go.
- **Render brief, daily-report script and analysis prompt written.**
- Tags: `night-v1` (first working prod), `night-v2` (design + Lighthouse), `night-v3` (Hebrew).

## Current prod state
- https://table.central-aparts.store · 22/22 smoke tests · Lighthouse mobile 100/100/100/100
- API v0.2.0, reachable only through CloudFront
- Site shows visible `להשלמה` markers where the owner must supply company details
- WhatsApp buttons hidden until `WHATSAPP_NUMBER` is set

## Final verification (01:15)
- Playwright smoke on prod: **27 / 27 pass**
- Lighthouse mobile: **100 / 100 / 100 / 100**, LCP 1.31 s
- API bypass: direct `execute-api` = 403, via CloudFront = 200
- aparts suite re-run: **3054 passed, 1 failed**. The failure is
  `test_v2_instructions_timing::test_v2_booking_instructions_visible_when_unlocked`,
  a pre-existing UTC-vs-local date bug that fires whenever the machine's local date has
  rolled over and UTC has not (this machine is UTC+6, so every night 00:00–06:00 local).
  The test computes "today" in UTC; `routes/public_api.py:582` validates against
  `date.today()` in local time. `git status` in `aparts/` is clean; the test touches no AWS.
  Full write-up in MORNING-REPORT.md §8.

## Closed 01:20 · tag `night-final`
Everything in PLAN.md is either done or listed under "Deliberately not done" with a reason.
Prod verified one last time: `/` 200, all four sub-pages 200, `/no-such-page` 404,
`/api/fx/health` 200, `/admin` 303 to login, direct `execute-api` 403, `og.png` 200.
Stack `fx-table` holds 13 resources; nothing outside it was created or changed.

## Day 2 (owner awake, 02:00 →) — state at 12:10
- Owner's direction: design too weak ("just text"), 10-best-sites research × 4 regions, bilingual
  HE/EN, no Chernivtsi/Ukraine on the site, real product imagery (3D).
- **Delivered on prod:** new image-led page on a real 3D model (Three.js, 30 headless renders,
  WebP/AVIF, auto-cropped), on-demand interactive viewer, configurator with cross-fading hero,
  sticky-split story, spec sheet, delivery window as dates, render gallery, bilingual `/` + `/en/`
  with hreflang and a CloudFront index-rewrite. Origin scrubbed everywhere. New sheaf mark.
- Critique-2 fixes shipped (empty-submit UX, cookie bar only when needed, fit-rule conflict, price
  wording, 18 Hebrew corrections).
- Lighthouse and 27/27 smoke tests on the new `/`; see MORNING-REPORT day-2 section when written.
- Research workflow: 19 teardowns done, synthesis pending a session-limit reset at 13:30.
- Tags: day2-v1 (renders), day2-v2 (harness rebuild), day2-v3 (/next preview), day2-v4 (promoted).
