# Meta campaign plan — ₪1,000 smoke test

Nothing here is live. No campaign was created, no ad account was touched, no money was
committed. This is the plan you execute by hand after `setup-checklist.md`.

Every benchmark below is sourced in `night/research/meta-ads-il.md`, which labels each
figure VERIFIED / REPORTED / ESTIMATE. Read that file before you argue with a number here.

---

## 0. The timing decision comes first, and it is not close

Today is **2 September 2026**. Erev Rosh Hashana is **Friday 11 September**. Yom Kippur is
20–21 September. Sukkot runs 25 September – 2 October. Normal life resumes about 4–5 October.

That leaves two real options:

| | **A · Run now** | **B · Run 5–14 October** |
|---|---|---|
| Dates | ~3 Sep → hard stop 10 Sep | 5 Oct → 14 Oct |
| Days | 8 (if the ad account clears review same-day) | 10 |
| Daily budget | ₪125 | ₪100 |
| CPM climate | Pre-chag retail rush — expect **₪38–48**, above the ₪33.9 Israeli median | Post-chag normalisation, closer to median |
| Demand climate | Genuinely peak home-goods season: people buy *for the table* before Rosh Hashana | Ordinary |
| Lead follow-up | You must call every lead within hours, every day, including Thursday 10 Sep | Unconstrained |
| Risk | One slipped day and the test straddles the chag; those data are uninterpretable | Three weeks of waiting |

**Recommendation: B, 5–14 October.** Not because September is bad — the pre-chag window is
real demand — but because option A needs the ad account approved, the domain verified, the
pixel firing, a WhatsApp number connected and you personally free to phone strangers for
eight consecutive days, all starting tomorrow morning. Miss any of that and you have paid
premium-CPM money for leads that go cold across a three-day holiday. A truncated, expensive,
badly-followed-up test answers the wrong question.

**Take option A only if all four are true by Thursday 3 September:** the ad account is
approved, the domain is verified, `WHATSAPP_NUMBER` is live on the site, and you have blocked
out time to call leads daily through 10 September. Then run 3–10 Sep at ₪125/day and stop
dead on the 10th — do not let it run into erev chag.

Whatever you choose, **do not run a test that crosses 11 September.**

---

## 1. Structure

One campaign. One ad set. Four creatives. That is the whole thing.

```
Campaign  ALUMA · Goren · smoke test
  objective: Leads
  budget: campaign-level (CBO), ₪100/day
  bid strategy: highest volume, no cost cap
  ↓
Ad set  IL · 28-55 · broad+interest
  conversion location: Instant Forms  (see §2)
  optimisation: leads
  schedule: continuous, no dayparting
  ↓
  4 ads   A1 fits-everyone · A2 real-oak · A3 room-fit · A4 story
```

**Why one ad set.** Exiting the learning phase needs roughly 50 optimisation events per week
per ad set. At an estimated ₪30–70 per instant-form lead, ₪100/day buys 1.5–3 leads a day —
about 15 a week against a bar of 50. Splitting the budget across two ad sets halves that
again and guarantees both stay in learning forever. This test is a **signal read, not an
optimisation run**: you are asking "does anyone in Israel want this table", not "which
audience converts 8% better".

**Do not** create lookalikes, do not split by gender, do not split by city, do not add a
second ad set "just to compare". At this budget every split makes the answer noisier.

## 2. Conversion location: Instant Forms, with the site as the secondary path

Meta's Leads objective offers Website, Instant Forms, Messaging (WhatsApp) and Calls.

- **Website conversions** optimise against the pixel's `Lead` event. With maybe 20 events
  total across the whole test, the algorithm has nothing to learn from. This is the classic
  way to burn ₪1,000 and conclude nothing.
- **Click-to-WhatsApp** is attractive in Israel and will get the most clicks, but with the
  WhatsApp Business *app* (not the API) there are no webhooks and no `ctwa_clid`, so you
  cannot attribute a conversation to a campaign except by the prefilled-message trick below.
- **Instant Forms** are the only location that produces double-digit events at ₪100/day.
  Lower intent per lead — accept that and qualify on the phone.

Use **"Higher intent"** form type (adds a review step before submit) plus **one qualifying
question**. Both suppress the accidental-tap leads that make instant forms look bad.

**Form fields:** full name, phone, city. Nothing else.
**Qualifying question (single choice):** `מתי אתם צריכים את השולחן?` →
`בחודש הקרוב` / `בעוד 2–3 חודשים` / `עוד לא החלטנו, אוספים מידע`.
That one answer separates a buyer from a browser better than any targeting setting.

**Privacy policy URL:** `https://table.central-aparts.store/privacy` (Meta requires one; it exists).

**Send the site traffic too.** Every ad's destination on the "learn more" button is the
landing page with UTMs, so the page's own analytics still records behaviour even when the
conversion happens inside Meta's form.

## 3. Audience

- **Geography:** Israel, all of it. Not a radius, not a city list.
  Meta's own delivery will find Gush Dan and the Sharon because that is where the density and
  the money are — you do not need to help it, and excluding the periphery on day one throws
  away the "delivery to the whole country is included" advantage over ZAGA, who explicitly
  refuse Mitzpe Ramon and Eilat.
- **Age:** 28–55. **Gender:** all.
- **Language:** do not set a language restriction. The ad copy is Hebrew; that is the filter.
- **Detailed targeting:** one broad interest stack, expansion **on**:
  `עיצוב פנים` / interior design · `שיפוצים` / home improvement · `רהיטים` / furniture ·
  IKEA · `בית וגן` · homeowners · recently moved.
- **Exclusions:** your own visitors. Create a custom audience from the pixel (`All website
  visitors, 30 days`) and exclude it, so you are not paying to re-show the ad to yourself and
  to people already in the funnel. Also open the site once as `?me=1` on every device you own —
  that sets a cookie that removes you from the site's own analytics.

Do **not** narrow further. At ₪1,000 the audience is not the variable you are testing.

## 4. Budget and pacing

| | |
|---|---|
| Total | ₪1,000 |
| Daily | ₪100 (option B) / ₪125 (option A) |
| Level | Campaign budget optimisation |
| Schedule | Run continuously; no dayparting |
| Edits | **None** for the first 72 hours |

Every edit to an active ad set restarts the learning phase. At this budget you get one
learning phase; spend it on data, not on fiddling. If an ad is obviously broken (rejected,
zero impressions after 24h) fix that one ad, not the ad set.

**Check whether the ₪1,000 is before or after 18% Israeli VAT** in Payment Settings before you
start. This is genuinely unverified — if VAT is added on top, your real spend is ₪1,180.

## 5. UTM scheme

Put this in the ad-level "URL parameters" field so every ad inherits it:

```
utm_source=facebook&utm_medium=paid&utm_campaign=aluma_goren_smoke_2026_10&utm_content={{ad.name}}&utm_term={{placement}}
```

Meta expands `{{ad.name}}` and `{{placement}}` automatically. Name the ads exactly `a1_fits`,
`a2_oak`, `a3_roomfit`, `a4_story` so the admin dashboard's source breakdown is readable
without a lookup table.

For **WhatsApp** clicks there are no UTMs — the site instead prefills the message with the
configuration the visitor chose, so the first line of every WhatsApp conversation tells you
the colour and the length they were looking at when they tapped.

## 6. Events

Already implemented on the site and firing today (first-party, into DynamoDB):

`page_view` · `scroll_25/50/75/100` · `section_view` · `color_select` · `size_toggle` ·
`room_fit_check` · `faq_open` · `form_start` · `form_field` · `form_error` · `form_submit` ·
`lead_success` · `whatsapp_click` · `phone_click` · `exit`

Meta Pixel events, which start firing the moment you put a pixel id in `content.json`:

| Pixel event | Fires when | Note |
|---|---|---|
| `PageView` | page load, after the cookie notice is acknowledged | consent-gated on purpose |
| `ViewContent` | same moment | carries `content_name`, `currency: ILS`, `value: 5990` |
| `Lead` | form submitted successfully | `content_name: form` |
| `Lead` | WhatsApp button tapped | `content_name: whatsapp_<placement>` — deliberately a different name so you can tell them apart |
| `Contact` | WhatsApp button tapped | |

The pixel does **not** load until the visitor dismisses the cookie bar. That is a deliberate
choice under Amendment 13 (in force 14 Aug 2025) and it means your pixel numbers will be
lower than your first-party numbers. The admin dashboard is the source of truth for behaviour;
the pixel is only there to give Meta a signal.

**Conversions API is not needed** for a ₪1,000 instant-forms test. Note for later: from
April 2026 the *conversion leads* optimisation requires CAPI on new campaigns.

## 7. What to look at each morning, in order

1. **Leads.** The only number that matters. Everything below explains it.
2. **CPL.** Target ≤ ₪60. Above ₪100 after 300 clicks, the offer or the price is the problem.
3. **CTR (link).** Target ≥ 1.5%. Below 1% = the creative is not landing.
4. **CPC (link).** Target ≤ ₪4. Israeli median is ~₪2.15.
5. **CPM.** Expect ₪34–48. A sudden spike means auction competition, not your ad.
6. **Frequency.** Above 2.0 before day 7 means the audience is too small — widen it.
7. **The admin dashboard** at `/admin`: how many people reached the price, how many touched
   a switcher, how many used the room-fit tool, which colour wins, which FAQ gets opened.
   This is the part Meta cannot tell you and it is why the site was built this way.
8. **The leads themselves.** Read the comments. Call them. What they ask about is the answer.

Ignore: reach, impressions, video views, engagement, and every "recommendation" Meta shows
you about raising the budget.

## 8. Benchmarks, stated honestly

| Metric | Target | Basis |
|---|---|---|
| CPM (Israel, all verticals) | ₪34 median, ₪38–48 in the pre-chag window | Superads Israel dataset, >$3B spend, Sep 2025–Sep 2026 |
| CPC (link) | ≤ ₪4, median ~₪2.15 | same |
| CTR (link) | ≥ 1.5% | industry norm, not Israel-specific |
| CPL, instant form | ₪30–70 | **derived estimate** — no published Israeli furniture CPL exists |
| CPL, website | ₪70–150 | derived estimate |
| Total leads on ₪1,000 | 10–30 | derived estimate |

Israeli CPM is roughly half the global median and about 58% more volatile. Do not read a
single bad day as a trend.

## 9. What this test cannot tell you

- Whether people will actually pay ₪5,990. A lead is not a deposit. `go-no-go.md` handles this.
- Whether the price is right. One price is being shown; there is no A/B.
- Whether the design converts. One landing page, no variants.
- Anything statistically significant. 10–30 leads is a signal, not a measurement.

It can tell you whether Israelis who see this table want to talk to you about it. That is
the whole question, and ₪1,000 is a fair price for the answer.
