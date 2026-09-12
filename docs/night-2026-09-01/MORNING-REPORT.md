# Day 2 — what changed after you woke up (2 September, 02:00 → 12:20)

You said: the design is weak ("just text"), find the ten best furniture sites in four markets,
make ours the most stylish and functional, Hebrew and English, no Chernivtsi/Ukraine, proper
product imagery — 3D. Here is what exists now.

## Live

| | |
|---|---|
| Hebrew | **https://table.central-aparts.store/** — Lighthouse mobile 100 / 100 / 100 / 100, LCP 1.5 s |
| English | **https://table.central-aparts.store/en/** — 98 / 100 / 100 / 100, LCP 1.1 s |
| Smoke tests | 27 / 27 on the new page |
| Cost | still ₪0 — one CloudFront function added, free tier |

## What you will see

- **A real 3D model of the table**, built in metres from the frozen spec (40 mm chamfered top,
  A-frame trestles, black steel beam, three oak tones). Rendered headlessly into 30 images —
  hero, reverse, front, end, top, detail — auto-cropped, WebP + AVIF. The page ships images, not
  a 3D library.
- **"סובבו את השולחן"** loads the same model live: drag to rotate, the tone and 160/220 switches
  drive it. Three.js loads only on tap, so it costs the page nothing until asked.
- **An editorial, image-led page**: hero render bleeding to the edge, the price inside the button
  ("הזמנה מוקדמת · ₪5,990"), a made-to-order line above it, the delivery window as real dates
  ("מגיע בין 28 באוקטובר ל־11 בנובמבר", computed each day), a configurator with render
  thumbnails, a peek-carousel of views, three image-led claims, the plan drawing with chairs,
  the room-fit tool, a sticky-text story with scrolling renders, a spec sheet, why-this-price,
  FAQ, form, and the brand name set giant as the sign-off.
- **A sheaf mark** for אלומה — five stalks bound at the waist, heads fanning up. It works at
  16 px. `furniture/site/assets/logo.svg`.
- **No country anywhere.** Story, FAQ, ads, alt-texts — "a family workshop, European oak".
- **English** is a full twin, not a translation layer bolted on: one template, one strings file per
  language, mirrored layout, `hreflang` both ways, legal pages in English marked as courtesy
  translations with Hebrew binding.

## The research — honest status

I launched 46 agents (4 scouts → 40 teardowns with screenshots → 4 regional syntheses → 1
design brief). **20 finished; 26 died on a session limit** that resets at 13:30. Nineteen
full teardowns are on disk (`night/research/design/`, with ~150 screenshots) and their
"steal / avoid" findings are digested in `DIGEST-partial.md`. I applied that digest by hand —
it is what the price-in-button, sticky-split story, spec sheet, dates and gallery came from.
The workflow is patched and resumable; when the limit lifts it finishes the missing regions
and the synthesis, and anything it adds goes in as a refinement, not another rebuild.

## Two things I want you to look at

1. **The critic's argument about the origin.** The second buyer critique (`night/CRITIQUE-2.md`)
   says scrubbing the country reads as evasion, that the Ukraine FAQ was the most trust-building
   paragraph on the page, and that Israeli labelling puts the country on the carton anyway — so
   the buyer learns it at delivery. I followed your instruction; the argument is recorded.
2. **The word "אלומה" as the sign-off on the English page.** It is a brand statement, deliberate;
   if you want `ALUMA` there instead, it is one line.

## Still yours

Unchanged from the first report: company identity (7 fields), a WhatsApp number, the price
decision, marketing yes/no, deposits no, legal review, trademark. The site now shows `להשלמה`
markers in the legal pages only — the product page has none.

## Where things are

```
furniture/site/index.html        the page (one template, both languages)
furniture/i18n/he.json, en.json   every string
furniture/site/assets/goren3d.js  the 3D model + on-page viewer
furniture/tools/render3d.js       headless renders   → renders-master/  → optimise_renders.py → site/assets/renders/
furniture/tools/make-ads.js       ad creative on the renders → night/meta/creative/
night/DESIGN-PLAN.md              the plan the page was built to
night/research/design/            19 teardowns + DIGEST-partial.md
night/CRITIQUE-2.md               second buyer critique
```

---

# Morning report — 2 September 2026

## 1. Where things stand

| | |
|---|---|
| **URL** | **https://table.central-aparts.store** |
| Admin | https://table.central-aparts.store/admin — credentials in `night/CREDENTIALS.md` |
| Version | site tag `night-v4`, API `0.2.0` |
| Smoke tests | **27 / 27 pass** against production (Playwright) |
| Lighthouse, mobile | **performance 100 · accessibility 100 · best practices 100 · SEO 100**, LCP 1.31 s |
| Apartments system | baseline before the night: **3055 tests pass**. Re-run at the end: see §8. |
| Cost incurred | **₪0.** New AWS resources are free tier; expected steady-state under $1/month. |
| Ads | **not launched.** Materials written, nothing created in any ad account, no money spent. |

The site is a real, working, honest product page. It is **not ready for traffic**, for one
reason that is entirely on your side of the line: the legal pages carry visible `להשלמה`
markers where the company name, ID, address, phone and email belong, and there is no WhatsApp
number, so every WhatsApp button is hidden. §3 is the list.

---

## 2. Problems first

**2.1 The site has no contact channel at all.** No phone, no email, no WhatsApp. A visitor who
wants to talk to you can only fill the form. In Israel WhatsApp is the primary channel, and a
furniture buyer who cannot reach a human reads the site as abandoned. This is the single
biggest conversion problem and it costs one line in `content.json`.

**2.2 The legal pages advertise that they are unfinished.** `/privacy`, `/terms` and
`/accessibility` render "שם העוסק — להשלמה" inside an orange dashed box. The consent checkbox
links straight to `/privacy`, so the highest-intent visitor on the page — the one about to
give you a phone number — meets it at the moment of decision. I made these visible rather than
inventing a company, and rather than shipping a raw `{{TOKEN}}`. They must be filled before any
traffic.

**2.3 The domain is wrong for the brand.** `table.central-aparts.store` is a subdomain of an
apartment-rental business, on a `.store` TLD. It is HTTPS, it works, and for a smoke test it is
defensible. It is also the first thing a careful Israeli buyer will notice, and no copy fixes
it. A real launch needs its own domain.

**2.4 There are no photographs.** Every image is a hand-authored technical drawing, drawn to the
frozen spec and honest about being a drawing. That is a legitimate position — Floyd sells a
table with an "email me when available" button and no reviews at all — but it is a position,
not a neutral choice, and some buyers will not cross it. `night/RENDER-BRIEF.md` specifies the
seven renders that replace them, in value order.

**2.5 The price is a judgement call I made without you.** ₪5,990, not the ₪6,490 you specified.
Reasoning in §4.

**2.6 Lambda function URLs do not work in your AWS account.** Not a furniture problem, but you
should know: a public function URL with a textbook-correct resource policy returns 403 with
zero invocations reaching the function, and so does the CloudFront-OAC variant. The existing
`aparts-api` function URL works, and there is no AWS Organization, so no SCP explains it. I
routed around it with an API Gateway HTTP API. Worth a support ticket if you ever want function
URLs again. Full evidence in `night/DECISIONS.md` D-021.

**2.7 A buyer-perspective critic read the live site and refused to leave a phone number.**
Its full write-up is `night/CRITIQUE-1.md`. Three of its five findings were real defects and
are fixed (§7); the other two are 2.1 and 2.2 above, which are yours.

---

## 3. REVIEW — decisions only you can make

Each line is one decision. The first block blocks traffic; the rest can wait.

**Blocking — the site should not receive a single paid visitor until these are done**

| # | Decision | Where |
|---|---|---|
| R1 | **The legal entity.** Ukrainian manufacturer / new Israeli company / Israeli עוסק מורשה / a partner as importer. Everything below depends on it. | — |
| R2 | `COMPANY_NAME` — trading name as registered | `furniture/content.json` |
| R3 | `COMPANY_ID` — ח.פ. or ע.מ. | same |
| R4 | `ADDRESS` — a real one; an accountant's or virtual office is normal and accepted | same |
| R5 | `CONTACT_EMAIL` — **must be monitored**; it carries privacy and accessibility requests that have statutory deadlines | same |
| R6 | `PHONE` — a number a customer can actually call | same |
| R7 | `ACCESSIBILITY_CONTACT` — a real person's name | same |
| R8 | `COURT_CITY` — usually the city of the registered address | same |
| R9 | **`WHATSAPP_NUMBER`** — format `972501234567`, no plus, no leading zero. Highest-impact single field on the site. | same |

Then `cd furniture && bash scripts/deploy.sh`. Two minutes, and the markers disappear.

**Not blocking, but decide before spending**

| # | Decision | My recommendation |
|---|---|---|
| R10 | **Price.** ₪5,990 or your ₪6,490? | ₪5,990 — see §4 |
| R11 | **Brand name.** אלומה / ALUMA, model גורן / GOREN. Ten alternatives ranked in `night/research/naming.md`. | Keep it — nothing in Israeli furniture uses it, and it carries the sheaf→wheat→Friday-table story without saying "Shabbat" |
| R12 | **Do you intend to send marketing at all?** If never — only ever calling people back about their own enquiry — your spam-law exposure drops to near zero and the second checkbox can go. | Decide explicitly; it is the highest-leverage legal decision you have |
| R13 | **Will you take deposits?** | **No**, not until R1, VAT and the warranty chain are settled |
| R14 | **VAT and import position.** Importer of record, VAT registration or fiscal representative, Ukraine–Israel FTA origin docs, ISPM 15 for wooden goods. | Needs an Israeli accountant and a customs broker. Open question. |
| R15 | **Lead notification email.** Off by default — SES needs to leave sandbox, which needs a support request. | The admin dashboard is the reliable read path meanwhile |
| R16 | **Meta Pixel and Microsoft Clarity ids.** Both free, both off until you supply an id. | Add Clarity even if you skip the pixel — ten session recordings beat any dashboard at 20 leads |
| R17 | **Legal review.** The three policy pages are drafted from statute to make a lawyer's review fast and cheap, not to replace it. | Budget a few hours of an Israeli lawyer |
| R18 | **Trademark and handles.** Nothing was registered — zero budget. | Israeli Patent Office search in classes 20/35, both scripts, before you print anything |
| R19 | **Admin password.** Generated by me and sitting in a plain file. | Change it: edit `parameter_overrides` in `furniture/infra/samconfig.toml`, redeploy |
| R20 | **A WAF.** Deliberately not created — ~$5–8/month minimum, over the zero-cost rule. | Not needed at smoke-test traffic |

---

## 4. The price, argued

The brief said ₪6,490 and allowed ₪5,490–7,490 with justification. I set **₪5,990**.

- The median for genuinely-oak 160–180 cm extendable tables in Israel is **₪6,300–6,450**
  including VAT, from 20 product pages with prices (`night/research/market-il.md`).
- Our top is oak **veneer** on plywood with a solid oak edge, not solid oak throughout, and the
  lead time is 8–10 weeks against Nature Furniture's 21 days at ₪6,885. Sitting exactly on the
  median with a weaker spec and a slower promise is the wrong place to stand.
- **₪6,490 appears to be Beitili's crossed-out list price** for a comparable veneer table that
  actually sells at ₪4,543. Adopting a competitor's fake anchor as your real price is a
  self-inflicted wound.
- The category runs on permanent fake discounts — ZAGA −26/−40%, ID Design −30%, Tollman's
  −30/−39%. An honest un-discounted number has to read as correct with nothing beside it, which
  pushes it down, not up. ₪5,990 clears ₪6,000, yields "6 תשלומים של 998 ₪", and leaves headroom.

One field to change if you disagree: `PRICE` in `furniture/content.json`.

---

## 5. Meta — what you do by hand

Everything is written; nothing is created. Work through **`night/meta/setup-checklist.md`** —
about 2–3 hours, most of it waiting for Meta.

- `night/meta/campaign-plan.md` — one campaign, one ad set, four ads, Instant Forms, ₪100/day
- `night/meta/ads.md` — four Hebrew feed ads and two story variants, ready to paste
- `night/meta/creative-brief.md` — which asset each ad needs; most are scriptable tonight from
  the site's own drawings
- `night/meta/go-no-go.md` — the stop/go rule, fixed **before** you spend

**The timing matters more than anything else in that folder.** Erev Rosh Hashana is Friday
11 September. Yom Kippur 20–21. Sukkot 25 Sep – 2 Oct. A test that straddles the chag produces
data you cannot read, and leads that go cold over three days nobody answers a phone.

**Recommendation: run 5–14 October, not now** — unless by Thursday 3 September the ad account is
approved, the domain verified, the WhatsApp number live, and you are free to call leads daily
through the 10th. Then 3–10 September at ₪125/day, hard stop before the chag.

---

## 6. Renders

`night/RENDER-BRIEF.md` — seven renders, each with framing, lighting, constraints and a prompt.
Value order: **R3 the macro of the oiled oak surface** (it carries the whole "real oak, not a
print" argument), then **R6 the flat pack** — which must be a real photograph of real cartons,
because a rendered box proves nothing about logistics — then the hero.

Swapping is a file replacement in `furniture/site/assets/renders/` plus one deploy. No code change.

Note the constraint: the moment a render goes up, the site is showing a table nobody has built.
That is legal if labelled and dishonest if not. The current drawings have the advantage of being
self-evidently drawings.

---

## 7. What was fixed after looking at it properly

Screenshots and a buyer-perspective critique found things no test failed on:

- **The cookie notice never disappeared.** `display: flex` beat the browser's `[hidden]` rule, so
  a fixed bar at z-index 50 covered the sticky CTA at z-index 40 — for the whole session, on
  every phone, every visit. The persistent call to action was unclickable.
- **The room-fit tool rejected a 3.3 m wall.** It demanded 90 cm clearance at each *end* of the
  table; 90 cm is the rule for the *sides*. Retiered against end clearance, and 399 cm and
  400 cm no longer print the same number with opposite verdicts.
- **Price and CTA were below the fold** on a 390 px phone, behind the drawing.
- **Grain lines ran past the closed tabletop**, the seam was chamfered on both halves so a closed
  table had a notch down the middle, and the plan view's viewBox was sized to the table rather
  than the chairs — so every chair was cropped out of the drawing.
- **A word I invented.** `סקוסית` is not Hebrew; it is Russian *скос* with a Hebrew ending, and
  it was in the product's own spec line. 76 corrections applied from a native-editor pass.
- **The FAQ promised return terms that `/terms` did not contain.** Added the clause and rewrote
  the answer to state the true position.

Five regression tests were added so none of these can come back.

---

## 8. Proof the apartments system is untouched

Its pytest suite was run before the night started and again at the end.

- **Before (20:35 local): 3055 passed**, 12m41s.
- **After (00:58 local): 3054 passed, 1 failed**, 10m55s.

**The one failure is not mine, and it is a real latent bug in your test suite.**

`test_v2_instructions_timing.py::test_v2_booking_instructions_visible_when_unlocked`
books a stay for "today" and asserts 201. It got 400 `invalid_dates`.

The test computes "today" in **UTC**:

```python
def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
```

The endpoint validates against the machine's **local** date:

```python
if ci >= co or ci < date.today():        # routes/public_api.py:582
    return jsonify({"error": "invalid_dates"}), 400
```

This machine's clock is UTC+6. At the moment of the re-run:

```
local  2026-09-02 01:10
utc    2026-09-01 22:10
```

So the test booked `2026-09-01` and the endpoint, whose `date.today()` had already rolled over
to `2026-09-02`, rejected it as a date in the past. The baseline run at 20:35 local was inside
the same calendar day in both clocks and passed.

**It fails on this machine every night between local 00:00 and 06:00, and has nothing to do with
the furniture project.** Evidence: `git status` in `aparts/` is clean — no file was modified —
and this test uses the local Flask test client and SQLite, touching no AWS resource of any kind.

Worth fixing on its own merits: an apartment business operating in Kyiv should not be branching
on the *server's* local date at all. Either the test should use `date.today()`, or — better —
the endpoint should compare against an explicit Europe/Kyiv date. The same `date.today()` pattern
appears at four other `invalid_dates` sites in that file.

I did not change it: it is outside `furniture/` and `night/`, and rule §8 says I do not touch
your files.

No file outside `furniture/` and `night/` was modified, with one exception: the additive
`.claude/cc10x/` memory files that your global `CLAUDE.md` router requires. The `aparts` stack,
its tables, its `samconfig.toml` and its Lambda alias were never touched.

---

## 9. The three sharpest criticisms I did not close

1. **"₪5,990 is stranded between IKEA and a local carpenter, and the page never says why."**
   The price justifies itself on materials and inclusions, but never against the two things an
   Israeli actually compares it to. A short "why this costs what it costs" block — the ₪390–480
   delivery every competitor charges separately, the 5-year warranty against the market's 12
   months — would answer it. Not written; it needs your real cost numbers.

2. **"Chernivtsi, Ukraine, with no mitigation."** The factory story is told plainly and the
   country is named, which is right. But a buyer paying a deposit for delivery in 8–10 weeks
   from a country at war has a question the page does not acknowledge, let alone answer. This
   is a business decision (escrow? no deposit? Israeli-held stock for the first batch?) before
   it is a copy decision.

3. **"The claims block says אלון אמיתי over a veneer top."** The very next sentence says
   "פורניר אלון על דיקט", so it is disclosed immediately and the claim is true — veneer is real
   oak, as against a printed foil. But a skimmer reads the heading and not the sentence, and
   this is exactly the claim a competitor would attack. Worth deciding whether you want to lead
   with it.

---

## 10. Where everything is

```
furniture/                    the project (own git repo, no remote, tags night-v1..v4)
  content.json                every name, number and third-party id — the file you edit
  build.py                    renders site/ -> dist/ and generates the drawings
  site/                       source pages, CSS, JS, self-hosted fonts
  api/handler.py              events, leads, admin
  infra/template.yaml         the whole stack
  scripts/deploy.sh           build + upload + invalidate
  scripts/daily_report.py     reads fx_*, writes night/reports/REPORT-<date>.md
  prompts/daily-analysis.md   the analysis prompt (proposes only, changes nothing)
  tests/smoke.spec.js         27 tests against production

night/
  MORNING-REPORT.md           this file
  DECISIONS.md                every call I made without asking, and why
  STATE.md                    iteration log
  CREDENTIALS.md              admin password and IP salt — not in git
  CRITIQUE-1.md               the buyer-perspective critique, unedited
  HEBREW-EDIT.md              the native-editor corrections table
  RENDER-BRIEF.md             the seven renders
  ARCHITECTURE-NOTES.md       phase 0 recon
  PLAN.md                     what was done and what was not
  research/                   market-il · landing-best · hebrew-rtl-ux · legal-il · meta-ads-il · naming
  meta/                       campaign-plan · ads · creative-brief · setup-checklist · go-no-go
  reports/                    daily analysis output
```

Read `night/meta/setup-checklist.md` first. It is ordered so nothing blocks on anything below it.
