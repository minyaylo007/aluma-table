# CRITIQUE-2 — table.central-aparts.store

Reviewer: homeowner, 44, Petah Tikva, 4 rooms, a 3.6 m dining wall, ₪6,000 budget, burned once by a furniture site, arrived from an Instagram ad on a phone.
Tested live with Playwright at 390×844 (iPhone) and 360×800, he-IL locale, 2026-09-02. Screenshots in `C:\tmp\fx\crit2\`.

**Timing note, because it matters:** the site was redeployed *while I was reading it*. My first load (before 05:46 UTC) had eleven FAQs including "הייצור באוקראינה — מה אם משהו משתבש?" and a story section headed "נגריית Impuls — צ׳רנוביץ, אוקראינה". The page served from 05:46:24 UTC (`Last-Modified`) has ten FAQs, no Ukraine, no Impuls, no Chernivtsi — zero mentions of any country. The repo confirms it was deliberate (`FACTORY`/`FACTORY_CITY` deleted from `content.json`, `site/index.html` rewritten). Everything below is judged against the page as it is now; where the removed version was better, I say so.

---

## Verdict

**Still no — but for different reasons than last time, and I got closer.** Three of round 1's five killers are gone: the price is the third thing I see (₪5,990 at y=324, "כולל מע״מ · משלוח והרכבה" under it, CTA at y=412), the cookie bar actually dismisses and stays dismissed, and the room-fit tool told me my 3.6 m wall works — "נכנס, גם פתוח — יישארו 70 ס״מ בכל קצה" — with a number I can check against my own tape measure. That is real progress; for the first twenty seconds this now reads like a product I could buy. Then I do what a burned buyer does: I open "מי מייצר את זה?" and get "נגרייה משפחתית שעובדת עם אלון אירופי" — a family workshop, somewhere, working with oak from somewhere in Europe. Eight to ten weeks, two flat boxes, "אין לנו מחסן", "אלון אירופי", and no country. Half an hour earlier this page told me Chernivtsi, Ukraine, and had a whole FAQ about it. A page that *hides* where the table is made is worse than a page that names a country at war and explains what happens to my deposit — and Israeli labelling law puts ארץ ייצור on the carton anyway, so I find out at delivery, at the worst possible moment. Add the things that have not moved: no name, no phone, no address, no WhatsApp, anywhere, on any of the five pages; `/privacy`, `/terms`, `/accessibility` still printing "שם העוסק — להשלמה" in orange boxes; a deposit whose size is never stated; and a form that, when I tap submit too early, shows me one error and hides the other two off-screen so it looks broken. I would screenshot the price and the fit result and send them to my wife. I would not type my number.

---

## Round-1 findings: status table

| # | Round-1 finding | Status | Evidence observed |
|---|---|---|---|
| 1 | Legal pages are unfinished templates | **OWNER-BLOCKED** (worse: still shipped) | `/privacy` 6 × "להשלמה", `/terms` 8 ×, `/accessibility` 7 × — all still in orange dashed boxes (`pg-privacy-s1.png`, `pg-terms-s14.png`, `pg-access-s5.png`). New §6 "ביטול והחזרה" in `/terms` is a genuine improvement (`pg-terms-s6.png`). |
| 2 | No way to contact the business at all | **OWNER-BLOCKED** | Across index/privacy/terms/accessibility/thanks: 0 × `tel:`, 0 × `mailto:`, 0 × `wa.me`. All three `.js-wa` buttons are still `display:none`, 0×0 (`CFG.wa = ""`). `/thanks` now hides the dangling "רוצים לכתוב לנו עכשיו…?" question together with the button — that part is fixed (`pg-thanks-top.png`). |
| 3 | Cookie bar never dismisses, buries the sticky CTA | **FIXED** | Click "הבנתי" → `#notice` `hidden=true`, `display:none`, `fx_notice_v1=1`; still hidden after reload (`cookie-after.png`). `elementFromPoint` at the centre of the sticky "השאירו פרטים" returns the anchor itself; clicking it lands on `#form` at scrollY 7399 (`sticky-mid.png`, `sticky-click-landed.png`). Caveat below (#4): the bar now *suppresses* the sticky bar instead of covering it. |
| 4 | No price / CTA on the first phone screen | **FIXED** | 390×844: `.price` y=324, price-note y=364, CTA y=412, drawing y=475 (`s-01.png`). 360×800: price y=324, CTA y=412 (`w360-01.png`). Swatches are still below the fold (y=863) and at 360 the cookie bar still covers the spec strip. |
| 5 | Room-fit tool says "no" to normal walls, flips at 1 cm, keeps stale verdicts | **PARTLY** | Bands now: <160 "קצר מדי"; 160–219 closed only; 220–289 "נכנס בדיוק"; 290–339 "צמוד"; 340–399 "נכנס, גם פתוח"; ≥400 "בנוח". 360 → 70 cm, green (`fit-360.png`). Sweep 100→520 shows the printed number and the verdict come from the same integer — no 399/400 flip. Clearing the field resets the box (`fit-cleared.png`). Still one dimension, and the fix introduced a new contradiction (see problem #5). |

Other round-1 items, briefly: "אלון אמיתי" bait headline → **PARTLY** (the veneer disclosure "פורניר אלון על דיקט" is now the first sentence under that heading, `s-02.png`). Plan drawing at 220 → **FIXED** (now 4+4 plus two end chairs = 10, `plan-220.png`). Hyphen wrapping "20–25" at 360 → **FIXED** (single line, `w360-story.png`). Ukraine question → **added, then removed** (regression, see #1). Deposit amount, return terms detail, photos, Instagram link, "שאלות שנשאלנו", "גורן · 90×75", two "אורך" labels, 12–13 px text, JSON-LD seller, `.store` subdomain → **NOT FIXED**, unchanged.

---

## The 5 most damaging remaining problems (ranked by lead cost)

### 1. Nobody to call — and now nowhere to point at on a map

**What I saw** (`footer.png`, `faq-who.png`, `story-1.png`, `pg-terms-s14.png`): footer = three legal links, "אלומה · רהיטי אלון, בהזמנה מראש", "© 2026 אלומה". No name, phone, address, email. `/terms` §14 "יצירת קשר" is four orange boxes. The story section now reads "נגרייה משפחתית, אלון אירופי, שולחן אחד" over a drawing of five empty circles; the FAQ "מי מייצר את זה?" answers "נגרייה משפחתית שעובדת עם אלון אירופי". Even "אין לנו מחסן **בישראל**" was trimmed to "אין לנו מחסן" — the one word that admitted this is an import.

**Why it costs leads:** the identity gap was round 1's #1 and #2 and it is untouched; the origin scrub makes it worse, because now the page *looks* like it is avoiding a question. The removed FAQ ("שאלה הוגנת, וזו הסיבה שאנחנו לא מבקשים כסף עכשיו…") was the single most trust-building paragraph on the site: it named the risk and tied it to "no money until a signed document". Deleting it, and the city, converts honesty into evasion for the exact reader who opens "מי מייצר" — the reader who is about to convert.

**Fix:** (a) name, city, phone in the footer and in `/terms` §1/§14 — today, even a VoIP number; (b) put the origin back, in the story heading and in the FAQ, and keep the removed answer but add the one sentence it lacked: "אם הייצור נעצר מסיבה שאינה תלויה בכם — המקדמה חוזרת במלואה תוך 14 יום." If the owner insists on softening, "נגרייה משפחתית בצ׳רנוביץ, מערב אוקראינה" is still a place; "אלון אירופי" is not.

### 2. Empty submit shows one error and hides the other two — the form looks broken

**What I saw** (`form-empty-submit.png` vs `form-empty-submit-top.png`): I tapped "אני רוצה שיחזרו אליי" with nothing filled. Validation marked all three fields (`e-name`, `e-phone`, `e-consent` all unhidden — the logic is right), but the page did **not** scroll (scrollY stayed at 8052), focus stayed on the button, and `#f-status` was set to an empty string. On screen I see only "צריך לאשר שאפשר לחזור אליכם" above the button; the red name and phone fields are ~900 px above the viewport.

**Why it costs leads:** the natural next move is to tick the consent box and tap again. Nothing visible changes. Second tap, third tap — the button appears dead. On a site with no phone number, a dead-looking submit is the end of the session.

**Fix:** on validation failure, `scrollIntoView({block:'center'})` + `focus()` the first invalid field, and write a one-line summary into `#f-status` ("חסרים שם וטלפון, וצריך לאשר את החזרה"). Keep the per-field messages — they are good.

### 3. "למה זה עולה מה שזה עולה" asserts instead of showing, and contradicts the terms

**What I saw** (`why-1.png`, `s-03.png`, `pg-terms-s5.png`): three cards. "נכלל במחיר" ends with "**₪5,990 זה מה שתשלמו**". `/terms` §2 calls it "מחיר משוער", §5 says "המחיר אינו מחייב עד לאישור הזמנה בכתב, והוא עשוי להשתנות", §4 says the company may "להפסיק את הפרויקט כליל, ללא הודעה מוקדמת וללא חבות". "איפה חסכנו" lists no number — not what a local carpenter charges, not what an imported veneer table costs, not what the deposit is. "איפה לא חסכנו" repeats the claims section almost word for word: on this page "קנט אלון מלא" appears 3 ×, "ביד אחת" 3 ×, "אלון אמיתי / הדפס" 2 × each, across three consecutive sections (claims → why-price → materials).

**Why it costs leads:** I asked in round 1 *why 5,990 and not 3,500 or 9,000*. The section answers "because we are good and frugal", which is what every furniture site says. A burned buyer reads the promise "זה מה שתשלמו", then reads §5, and concludes the marketing and the lawyer have not met. Salesmanship, not arithmetic.

**Fix:** replace "איפה חסכנו" with one honest comparison: "נגר מקומי, אלון: ₪9,000–12,000. יבוא בשתי אריזות שטוחות, בלי חנות ובלי מלאי: ₪5,990. מקדמה: 30% — מוחזרת במלואה אם לא סיפקנו." Then make the terms agree: either "המחיר מובטח למי שמאשר הזמנה עד [תאריך]" or drop "זה מה שתשלמו". Delete the repeated claims — say each thing once.

### 4. The cookie bar is legally unnecessary, eats 15% of every screen, and now *suppresses* the sticky CTA until tapped

**What I saw** (`1.png`, `sticky-mid-notice-up.png`, `w360-01.png`): `#notice` is 129 px tall, fixed, on every screen until "הבנתי" is tapped. While it is up, `body.has-notice` keeps `.stickybar` at `translateY(110%)` — so a visitor who never taps cookie bars (most of us) never sees the sticky price/CTA at all; the round-1 fix moved the problem rather than removing it. At 360×800 the bar covers the hero spec strip. Meanwhile `/privacy` §5 says measurement is first-party, IP is hashed, and third-party tools load "רק לאחר שאישרת" — and `app.js` has `pixel: ""`, `clarity: ""`. Nothing third-party loads. No Israeli rule requires a banner for that.

**Why it costs leads:** a dark bar with a legal sentence is the first thing an Instagram visitor sees at the bottom of screen one, and on screens two to eleven it replaces the only persistent price+CTA the page has.

**Fix:** remove the bar until a pixel is actually configured. If it must stay: one line, 40 px, auto-dismiss on first scroll, and never suppress `.stickybar`.

### 5. The room-fit tool now argues with itself, and still asks the wrong question

**What I saw** (`fit-empty.png`, `fit-cleared.png`, `fit-250.png`, `fit-3.6.png`): on first view the box says "כלל האצבע שלנו: **90** ס״מ פנויים **מכל צד**". Type a value and delete it, and the same box now says "נשארים **60** ס״מ פנויים **בכל קצה**?" — two different rules of thumb, two different words for the dimension. My 360 gets "70 ס״מ … מספיק" a second after the page told me 90 is the rule. 250 → title "נכנס בדיוק, **בלי מרווח**", body "יישארו **15** ס״מ". Typing "3.6" (how a person says a wall length) → nothing happens, no message; same for 2000. The 160/220 toggle does not affect the verdict (it always assumes 220 — defensible, but unexplained). And it still asks one number: the question in my flat is whether a 90 cm-deep table plus two rows of chairs fits *across* the room, not along the wall.

**Why it costs leads:** the tool is the page's only proof-of-fit and the thing that turns "nice" into "mine". A tool whose stated rule changes depending on whether I have typed yet is a tool whose green verdict I discount.

**Fix:** one rule string, in HTML and JS, using the same number and the same word (60 ס״מ בכל קצה); derive the title from the same integer as the body (15 cm is not "בלי מרווח"); accept decimals and metres ("3.6 → 360 ס״מ?"); add a second field "רוחב החדר" with a 250 cm threshold.

---

## Hebrew in the new sections

Nothing here is machine-translated; the problems are logic and register, plus a few lines that should be tightened.

**"למה זה עולה מה שזה עולה" block**

- `לא תוספת בקופה ולא „החל מ־״ — ₪5,990 זה מה שתשלמו.` — there is no קופה on this site (the FAQ says so). → **`בלי תוספות בסוף ובלי „החל מ־״: ₪5,990, וזה המחיר.`** (and only if `/terms` §5 is changed to match).
- `איפה חסכנו` / `איפה לא חסכנו` — "לחסוך" takes על/ב, not איפה; reads like a heading translated from "where we saved". → **`על מה חסכנו` / `על מה לא חסכנו`**.
- `ולכן אנחנו לא מגלגלים עליכם מחסן וחלון ראווה.` — "מגלגלים עליכם" is fine and native; "חלון ראווה" right after "חנות תצוגה" in the same sentence is two names for one thing. → **`ולכן אתם לא משלמים לנו על שכירות ועל מלאי שיושב במחסן.`**
- `אלון אמיתי ולא הדפס, קנט אלון מלא בהיקף, לוח הארכה שנשלף ביד אחת, גימור שמן־שעווה` — correct Hebrew, third repetition on the page. Cut the list; leave "אחריות 5 שנים על המבנה" and say what it means from abroad: **`אחריות 5 שנים על המבנה — מטפלים אצלכם בבית, לא שולחים חזרה.`** (only if true).
- The low opening quote `„` (in `„החל מ־״`, and throughout `/privacy` and `/terms`: `„אנחנו” או „החברה”`) is Central-European typesetting; in Israeli web Hebrew it reads imported. Use `״החל מ־״` or plain `"החל מ-"`.

**Ukraine FAQ (as it stood before 05:46 UTC, now deleted)**

- `שאלה הוגנת, וזו הסיבה שאנחנו לא מבקשים כסף עכשיו. אין תשלום באתר.` — native, good, keep.
- `מועד האספקה, תנאי התשלום ומה קורה אם המועד נדחה — כל אלה ייקבעו בכתב ויישלחו לכם לאישור לפני התשלום הראשון.` — good, but it answers *delay*, not *stoppage*; the buyer's fear is the deposit, not the date. Add: **`ואם הייצור נעצר — המקדמה חוזרת במלואה.`**
- `אתם מחליטים על סמך מסמך, לא על סמך הבטחה באתר.` — the best line the site had. It is gone. Put it back.

**Story / "מי מייצר" (new wording, live now)**

- `נגרייה משפחתית, אלון אירופי, שולחן אחד` — grammatical, empty. A heading with no place in it is a heading that is hiding one.
- `נגרייה משפחתית שעובדת עם אלון אירופי.` as the answer to `מי מייצר את זה?` — an Israeli asks "מי" and expects a name or a city. → **`נגרייה משפחתית בצ׳רנוביץ, אוקראינה. השולחן תוכנן לנסיעה שטוחה ולהרכבה בבית.`**
- `כי אין לנו מחסן ואין לנו חנות תצוגה, ולא מתכוונים לפתוח כאלה.` — fine; restoring `בישראל` after `מחסן` is the honest version.

**Room-fit strings**

- HTML default `כלל האצבע שלנו: 90 ס״מ פנויים מכל צד כדי למשוך כיסא ולעבור מאחוריו.` vs JS reset `נשארים 60 ס״מ פנויים בכל קצה? אפשר למשוך כיסא ולעבור בנוחות.` → one string: **`כלל האצבע שלנו: 60 ס״מ פנויים בכל קצה — מספיק כדי למשוך כיסא ולעבור.`**
- `נכנס בדיוק, בלי מרווח` with `יישארו 15 ס״מ` → **`נכנס, כמעט בלי מרווח`** for 1–34 cm; keep `בלי מרווח` only at 0.

**Form**

- Marketing consent: `אפשר לעדכן אותי גם על ההשקה ועל דגמים חדשים בדוא״ל, ב־SMS ובוואטסאפ.` — the form has no email field. Either add one or drop `בדוא״ל`.

---

## Everything else, by severity

- **Deposit amount still unstated** anywhere ("מקדמה בהזמנה, היתרה במסירה"). This is the number that decides the callback.
- **`/terms` §4** lets the company "להפסיק את הפרויקט כליל … ללא חבות כלפי הנרשמים" — legally sensible for a pre-launch, but next to "₪5,990 זה מה שתשלמו" it reads as "we promise nothing". Add the deposit-refund sentence here too.
- **"מחיר השקה"** in the hero and sticky bar still contradicts `/terms` §5 "לא מחיר מוזל: אין באתר מחיר מבוטל, מבצע או הנחה". Unchanged from round 1.
- **`/terms` §9 and `/accessibility` §4** still describe a WhatsApp button that does not exist on the site.
- **`/accessibility` §5–6**: the legally required alternative channel and the accessibility officer are still "להשלמה". Exposure, not just embarrassment.
- **No photographs**, still. Six drawings, five hollow circles, no oak, no hand pulling a leaf.
- **No link back to the Instagram account** the ad came from; no reviews, no "who we are".
- **"שאלות שנשאלנו"** still heads an FAQ for a product with no customers.
- **Hero copy still leads with 10 seats** ("220 ס״מ · 10"); the plan drawing is now honest (4+4+2 end chairs) which makes the copy the outlier — lead with 8, offer 10.
- **Swatches below the fold** at both widths (y=863/851). The colour choice is the most engaging control on the page and needs a scroll to find.
- **Story drawing** (`story-1.png`): five empty circles joined by a line, `role="presentation"`, no labels. On a phone it looks like icons that failed to load.
- **"גורן · 90×75"** still unexplained; **"אורך"** still labels both the spec cell and the toggle, one above the other.
- **Text under 14 px** unchanged: titleblock labels 12 px, swatch names 12 px, "ALUMA" 12 px, sticky "כולל מע״מ, משלוח והרכבה" 12 px, eyebrows/hints 13 px, footer © 12 px.
- **Room-fit input** silently ignores <60, >1500 and decimals; no unit inside the field.
- **Consent checkbox** still 20×20 (label is tappable, box looks not).
- **`/privacy` §9** documents the `?me=1` opt-out parameter — a developer note in a public policy, and an open invitation to opt out of measurement.
- **JSON-LD** still has `Offer` with no `seller`/`Organization`.
- **Domain** still `table.central-aparts.store`, a subdomain of an apartment-rental brand.
- **`/privacy` §5** "Amazon Web Services באזור פרנקפורט" — fine, actually reassuring; leave it.
- Regression check: nothing that worked in round 1 is broken now; the two regressions are the origin scrub (#1) and the two-rules contradiction the fit fix introduced (#5).

---

## What works — do not break these

1. **The first screen.** Brand → headline → lede → ₪5,990 → "מחיר השקה · כולל מע״מ · משלוח והרכבה בכל הארץ" → "השאירו פרטים" → to-scale drawing → 160/220 toggle, all inside 844 px, no horizontal scroll at 390 or 360 (`s-01.png`, `w360-01b.png`). This is the correct order. Leave it.
2. **The configurator and the drawings.** Toggling 220 redraws the elevation and the plan (now with the two end chairs), updates the spec strip, the state cards and the form note ("אורך 220 ס״מ, גוון אלון מעושן") with no layout shift (`toggle-220.png`, `swatch-smoked.png`, `plan-220.png`). The sticky CTA lands exactly on the form.
3. **The no-money-on-site logic and the form's per-field validation.** "איך משלמים?" → "אפשר לבטל?" → `/terms` §6 → `/thanks` "הצעה בכתב — מפרט, מחיר, מועד — לפני כל תשלום" is a coherent chain, and the field errors ("צריך שם כדי לדעת למי לפנות", "מספר טלפון ישראלי, למשל 050-000-0000") are still the best on any Israeli lead form I have used. Fix the scroll (#2) without touching the messages.

---

### Screenshot index (`C:\tmp\fx\crit2\`)
`1.png` first load with notice · `s-01.png`–`s-11.png` full scroll at 390×844 after dismissal · `cookie-after.png` notice gone · `sticky-mid.png`, `sticky-mid-notice-up.png`, `sticky-click-landed.png` sticky bar · `toggle-220.png`, `swatch-smoked.png`, `swatch-white.png`, `swatch-natural.png`, `plan-220.png` configurator · `fit-empty.png`, `fit-360.png`, `fit-250.png`, `fit-300.png`, `fit-450.png`, `fit-cleared.png`, `fit-3.6.png` room-fit · `why-1.png`, `why-2.png` price section · `story-1.png`, `story-2.png` story · `faq-all-open.png`, `faq-cancel.png`, `faq-pay.png`, `faq-size.png`, `faq-who.png` FAQ · `form-1.png`, `form-2.png`, `form-empty-submit.png`, `form-empty-submit-top.png`, `form-empty-submit-consent.png`, `form-noconsent.png` form · `footer.png` · `pg-privacy*.png`, `pg-terms*.png` (incl. `pg-terms-s5.png`, `pg-terms-s6.png`, `pg-terms-s14.png`), `pg-accessibility*.png`, `pg-access-s5.png`, `pg-thanks*.png`, `pg-nope-404*.png` sub-pages · `w360-*.png` at 360×800 (`w360-01.png` with notice, `w360-01b.png` without, `w360-fit-360.png`, `w360-claims.png`, `w360-why.png`, `w360-form.png`).
