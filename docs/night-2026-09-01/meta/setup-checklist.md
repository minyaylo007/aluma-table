# Setup checklist — everything only you can do

Ordered so that nothing blocks on something below it. Rough total: **2–3 hours**, most of it
waiting for Meta to approve things. Do steps 1–3 first even if you decide to postpone the
campaign; they unblock the site itself.

Legend: ⏱ = expect a wait. 💰 = costs money.

---

## Part 1 — the site (do this first; the ads point at it)

**1 · Decide the legal identity.** Everything else depends on it. Who is the עוסק — the
Ukrainian manufacturer, a new Israeli company, an Israeli עוסק מורשה, or a partner acting as
importer? Until this is answered the privacy policy, the terms and the accessibility statement
all carry a visible `להשלמה` marker where the name should be.
See `night/research/legal-il.md` section C for the full list of twelve owner decisions.

**2 · Fill in `furniture/content.json`.** These fields are empty and render as visible
placeholders on the legal pages:

```
COMPANY_NAME           the trading name, exactly as registered
COMPANY_ID             ח.פ. for a company, ע.מ. for a dealer
ADDRESS                a real address; an accountant's or virtual office is normal
CONTACT_EMAIL          must be monitored — it carries privacy and accessibility requests
                       with statutory deadlines
PHONE                  the number a customer can actually call
ACCESSIBILITY_CONTACT  a real person's name
COURT_CITY             usually the city of the registered address
```

**3 · Get a WhatsApp number and put it in `WHATSAPP_NUMBER`.** Format `972501234567` — no
plus, no leading zero. Until this is set **every WhatsApp button on the site is hidden**, and
WhatsApp is the primary conversion path in Israel. This is the single highest-impact field in
the file. Install WhatsApp Business on that number.

Then: `cd furniture && bash scripts/deploy.sh`. Two minutes. The placeholders disappear.

**4 · Exclude yourself from the analytics.** Open `https://table.central-aparts.store/?me=1`
once on every device you use — phone, laptop, tablet. It sets a one-year cookie that removes
you from every count. Do this before you start sending traffic.

**5 · Check the admin works.** `https://table.central-aparts.store/admin`, credentials in
`night/CREDENTIALS.md`. Change the password by editing `parameter_overrides` in
`furniture/infra/samconfig.toml` and redeploying.

---

## Part 2 — Meta assets

**6 · Facebook Page.** A business page for the brand. Needs: name (`אלומה`), category
`Furniture Store`, profile image (crop the wordmark from `/assets/og.png`), cover image
(the elevation drawing), and a Hebrew bio. A page with nothing on it looks abandoned — post
three or four things before the ads run: the drawing, the three tones, the flat-pack diagram,
the spec list. They do not have to be good, they have to exist.

**7 · Instagram business account.** `@aluma.il` and `@aluma_il` were inconclusive when
checked — see `night/research/naming.md`. Claim whichever is free, convert it to a
professional account, connect it to the Page. Same three or four posts.

**8 · Business Manager** at `business.facebook.com`. Create a business, add the Page and the
Instagram account under it, and add the ad account there — **not** as a personal ad account.
Personal ad accounts are where Israeli furniture advertisers get stuck when they later want a
second person to have access.

**9 · Ad account.** ⏱💰 Currency **ILS**, timezone **Asia/Jerusalem**. Both are permanent —
getting the timezone wrong makes every daily report off by a day forever. Add a payment method.
Then check Payment Settings for whether **18% VAT is added on top** of your spend; this is
genuinely unverified and changes ₪1,000 into ₪1,180.

**10 · Verify the domain.** ⏱ Business Manager → Brand Safety → Domains → add
`central-aparts.store` → choose the **DNS TXT** method. Meta gives you a string like
`facebook-domain-verification=xxxxxxxx`.

In Route 53, hosted zone `Z05565972H1DV59U5PO4I`: the apex `central-aparts.store` **already
has records**. You must **add a value to the existing TXT record set if one exists**, not
create a second TXT record set — two TXT record sets on the same name is the classic failure
here. If no TXT record set exists on the apex, create one. Wait, then click Verify.

Note: verification is on the parent domain, which the apartments site also uses. It is
additive and does not affect that site.

**11 · Pixel.** ⏱ Events Manager → Connect Data Sources → Web → Meta Pixel. Copy the numeric
id. Put it in `furniture/content.json` as `META_PIXEL_ID`, run `bash scripts/deploy.sh`, then
use the **Meta Pixel Helper** browser extension on the live site to confirm `PageView` and
`ViewContent` fire.

**Important:** the pixel deliberately does not load until you dismiss the cookie bar. If the
Helper shows nothing, dismiss the bar and reload. This is correct behaviour, not a bug.

**12 · Register the Lead event.** In Events Manager the `Lead` event will appear on its own
once it fires. Submit the form once on the live site to make it appear. It carries
`content_name: form` for form leads and `content_name: whatsapp_<placement>` for WhatsApp taps,
so you can separate them.

**13 · (Optional) Microsoft Clarity.** Free session recordings and heatmaps, no credit card.
`clarity.microsoft.com` → new project → copy the id → `CLARITY_ID` in `content.json` → deploy.
On 20 leads, watching ten real sessions will teach you more than any dashboard. Also
consent-gated.

---

## Part 3 — the campaign

**14 · Read `campaign-plan.md` §0 and decide the dates.** The recommendation is 5–14 October.
Do not run a test across 11 September.

**15 · Build the campaign exactly as `campaign-plan.md` specifies.** One campaign, one ad set,
four ads. Instant Forms. ₪100/day CBO. Resist every prompt Meta shows you to "improve" it.

**16 · Build the instant form** from the copy in `ads.md`, including the qualifying question
and the privacy policy URL.

**17 · Upload creative** per `creative-brief.md`. The link-preview card already exists at
`/assets/og.png`; the feed and story assets are scriptable from the site's own drawings.

**18 · Set the UTM string** at ad level, from `campaign-plan.md` §5.

**19 · Submit and wait.** ⏱ Review is usually under 24 hours. Furniture is **not** a special ad
category — if Meta flags it as Housing, the cause is almost certainly an image with a room
interior in it; recrop tighter on the furniture and resubmit.

**20 · Before spend starts, send one test lead** through the live form and confirm it appears
in `/admin`. It is much cheaper to find a broken pipe now.

---

## Do not do these

- Do not create a second ad set "to compare". ₪1,000 does not support a split.
- Do not edit the ad set in the first 72 hours. Every edit restarts the learning phase.
- Do not raise the budget mid-test because day 2 looked good.
- Do not turn on Advantage+ campaign budget across multiple ad sets.
- Do not take deposits until the legal entity, the VAT position and the warranty chain are
  settled. See `night/research/legal-il.md` §5.3 — that alone removes most of the legal surface.

---

## Cost summary

| Item | Cost |
|---|---|
| Everything built tonight | **₪0** — free tier, existing AWS account |
| AWS running cost at smoke-test traffic | well under ₪5/month |
| Facebook Page, Instagram, Business Manager, pixel, domain verification | ₪0 |
| Microsoft Clarity | ₪0 |
| The ad test | ₪1,000 (+ possibly 18% VAT — verify) |
| Domain for a real brand later | not bought, not needed for the test |
