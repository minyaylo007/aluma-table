# CRITIQUE-1 — table.central-aparts.store

Reviewer: homeowner, 38, Ramat Gan, 4 rooms, ₪6,000 budget, arrived from an Instagram ad on an iPhone.
Tested live with Playwright at 390×844 (iPhone) and 360×800, he-IL locale. Screenshots in `C:\tmp\fx\`.

---

## Verdict

**No. I would not leave my phone number.** Not because the table is wrong — the table is actually the most convincing part — but because the page asks me for my number while refusing to give me anything back. There is no phone number, no email, no address, no company name, and no WhatsApp anywhere on this site; the three WhatsApp buttons are `href="#"` with `display:none`, so the *only* channel that exists is the one where I hand over my details and wait. Then I did the thing a careful buyer does before ticking a consent box — I tapped "מדיניות פרטיות" — and the page told me the site is operated by **"שם העוסק — להשלמה"**, "מס׳ עוסק — להשלמה", "כתובת — להשלמה", printed inside orange dashed TODO boxes (`pg-privacy.png`). At that moment the site stops being a young brand and becomes an unfinished template. Add it up: an anonymous seller, a factory in a country at war, an 8–10 week lead time, a deposit "מקדמה בהזמנה" of an unstated amount, no photograph of a single finished table, no showroom, no reviews, no Instagram link back to the ad I came from, and no phone I can call to shout at when week 12 arrives. I have been burned by exactly this shape before, and last time the company at least had a name.

---

## The 5 most damaging problems

### 1. The legal pages are unfinished, and they are the pages a serious buyer reads last, right before converting

**What I saw** (`pg-privacy.png`): `/privacy` §1 reads "האתר מופעל על ידי **שם העוסק — להשלמה** … מספר **מס׳ עוסק — להשלמה** … מכתובת **כתובת — להשלמה**. בכל שאלה … בדוא״ל **כתובת דוא״ל — להשלמה** או בטלפון **טלפון — להשלמה**." Each placeholder is rendered in an orange dashed box, so it is not even subtle. `/terms` has the same in §1 and §13, plus "סמכות השיפוט … בעיר — להשלמה". `/accessibility` names the operator as "שם העוסק — להשלמה", the accessibility officer as "שם האחראי — להשלמה", and — worst — §5 offers the legally required alternative channel as "כל המידע … זמין גם בטלפון **טלפון — להשלמה** ובדוא״ל **כתובת דוא״ל — להשלמה**."

**Why it matters:** the consent checkbox in the form links straight to `/privacy`. The people who click that link are the highest-intent visitors on the site — the ones who read before they commit. You are killing them at the last step, with proof (not suspicion) that nobody finished the job. It also breaks Israeli accessibility regulations, which require a real alternative channel and a named accessibility officer.

**Fix:** put the real עוסק מורשה/ח.פ. name, number, address, email and phone into all three pages and into the footer, today. Until they exist, do not publish the pages — a 404 is less damaging than a visible TODO. Add a build check that fails the deploy if the string "להשלמה" appears in any rendered page.

### 2. There is no way to contact this business, at all

**What I saw:** every `<a>` on the page — `#main`, `/`, `#`, `#form`, `/privacy`, `/terms`, `/accessibility`, `#`, `#`, `#form`, `/privacy`. Zero `tel:`, zero `mailto:`, zero `wa.me`. The three WhatsApp buttons ("דברו איתנו בוואטסאפ" in the hero, "וואטסאפ" in the footer and in the sticky bar) all carry `class="js-wa is-off"` and measure 0×0. Footer says only "אלומה · רהיטי אלון, בהזמנה מראש · © 2026 אלומה". `/terms` §8 cheerfully disclaims liability for "קישורים … ובכללם וואטסאפ" — links that do not exist. `/thanks` (`pg-thanks.png`) asks "רוצים לכתוב לנו עכשיו במקום לחכות לשיחה?" and then offers nothing but "חזרה לעמוד המוצר" — a question with the answer deleted.

**Why it matters:** this is the exact asymmetry a burned buyer is scanning for. You want ₪5,990 and a deposit; I want a number I can call at 21:00 on week 9. You are pre-launch with no stock and no showroom — the only thing you have to trade for my trust is reachability, and you have removed it. It also makes the "אנחנו חוזרים בטלפון" promise unverifiable: I cannot test you before I commit.

**Fix:** turn on the WhatsApp button with a real number, and print that number in plain text in the footer next to a real business name and city. If there is no business phone yet, get one — a ₪30/month VoIP line is cheaper than the leads this is costing. Fix `/thanks` to show the same channel, or remove the dangling question.

### 3. The cookie bar never dismisses, and it sits on top of the sticky price bar — the persistent CTA is physically unclickable

**What I saw** (`s-01.png` … `s-10.png`, `cookie-after.png`, `sticky-clean.png`): the notice is `position:fixed; z-index:50`, top 715px, height 129px on a 844px viewport — 15% of every screen, on every screen, forever. Clicking "הבנתי" writes `fx_notice_v1=1` to localStorage and **does not hide the bar**: after the click it is still `display:flex; visibility:visible` at the same coordinates, and it is still there after a reload. Meanwhile the real sticky bar (`.stickybar`, `z-index:40`, top 762, height 82) carries "₪5,990 · כולל מע״מ ומשלוח · השאירו פרטים" and is completely buried underneath it. `document.elementFromPoint()` at the centre of the sticky "השאירו פרטים" button returns the cookie bar's `הבנתי` button.

**Why it matters:** the one element designed to keep the price and the CTA in front of me for the whole 7,860px scroll is invisible and dead for 100% of mobile sessions. Every tap on it dismisses a cookie notice instead. And a cookie banner that ignores its own accept button reads as "this site is broken", which is the last impression you want from a pre-launch brand.

**Fix:** make `#notice-ok` actually remove/hide the `.notice` element and read `fx_notice_v1` on load. Give the notice a higher `z-index` than the sticky bar only while it is up, and offset the sticky bar by the notice height so the two never stack. Verify with a hit-test, not by eye.

### 4. On a phone, the first screen has no price and no CTA — and the cookie bar covers the colour swatches

**What I saw** (`s-01.png`, `w360-01.png`): at 390×844 the price sits at y=815 and the first "השאירו פרטים" at y=904, while the cookie bar starts at y=715 — so the usable fold is 715px and the price is a full 100px below it, the CTA 190px below it. The oak swatches begin at y=714 and are covered by the notice on first load; you can see three half-buttons peeking out from behind it. At 360×800 it is worse: price at y=803, CTA at y=892, and the entire first screen is header + headline + drawing + one size toggle (`w360-01.png`). I have to scroll a full screen height before I learn what this costs.

**Why it matters:** "what is it and what does it cost" is the whole first-three-seconds job on an ad landing page. Right now the answer to the first half is good and the second half is missing. Instagram traffic bounces.

**Fix:** move the ₪5,990 line directly under the sub-headline, above the elevation drawing. Keep the drawing, keep the toggle — just reorder. The strip "מחיר השקה · כולל מע״מ · משלוח והרכבה בכל הארץ" is the single most reassuring line on the page and it is currently hidden.

### 5. The room-fit tool tells most of its target market "no", and contradicts itself one centimetre apart

**What I saw** (`fit-300.png`, `fit-450.png`, `fit-150.png`, `fit-stale-empty.png`, threshold sweep):
- 160–339 cm all return the identical "**צר מדי למעבר** — השולחן עצמו נכנס, אבל לא יישאר מקום למשוך כיסא משני הצדדים." A 3.3 m dining wall is a completely normal Ramat Gan wall, and you are telling that person the table does not work.
- 399 cm → "**מתאים סגור. פתוח יהיה צפוף.** … יישארו בערך **90 ס״מ** מכל צד, כך שבערב גדול עוברים בצמוד לקיר." 400 cm → "**נכנס, גם פתוח** — נשארים בערך **90 ס״מ** מכל צד — מספיק כדי למשוך כיסא ולעבור." The same displayed 90 cm produces opposite verdicts one centimetre apart, because the copy rounds and the threshold does not.
- Clear the field, or type `0`, and the previous verdict stays on screen: after 450 I emptied the input and it still reads "בקיר של **450** ס״מ יש מקום לשולחן פתוח" — a green "it fits" for a wall I no longer claim to have (`fit-stale-empty.png`).
- It only ever asks one dimension. My problem is not the wall length, it is whether a 90 cm deep table plus two rows of chairs fits across the room. The tool cannot answer the question its own heading asks ("ייכנס אצלי בבית?"), and the 90 cm-per-side rule you quote is a *behind-the-chair* rule being applied to the *ends* of the table, where nobody sits unless you use the two extra chairs.

**Why it matters:** this is the only interactive proof-of-fit on the page and it is the thing that turns "nice table" into "my table". A tool that says "too narrow" to a normal apartment, and flips verdict on a 1 cm change, gets no more trust than a guess — and I stop believing the 6/10 seat claim too.

**Fix:** ask two numbers (wall length **and** room depth) and grade against both. Widen the "fits" band: 220 + 2×60 = 340 for comfortable, 220 + 2×35 = 290 for "tight but workable with one side against the wall", and only call it "too narrow" below that. Derive the message from the same rounded number you print. Clear the verdict when the input is empty or ≤ 0 and show the hint instead.

---

## Everything else I noticed, roughly by severity

- **"אלון אמיתי, לא הדפס עץ" is a bait headline for a veneer top.** Three sections later: "משטח — **פורניר אלון על דיקט**" (`s-04.png`). Both statements are true, but leading with "real oak" and burying "veneer on plywood" is exactly the move a buyer expects from someone who is hiding something. The engineering justification ("משטח מלא ברוחב 90 ס״מ עובד עם הלחות … זז") is genuinely persuasive — say it *at the headline*, not 2,000px later.
- **₪5,990 sits in the worst possible price band.** Too much for veneer-on-plywood if I compare to imported furniture; too little for the "family carpentry, hand-applied oil layers" story if I compare to a local נגר, who would quote ₪9–12k for solid oak. Nothing on the page explains why it is this number, and "מידה אחת היא הסיבה שהמחיר הוא ₪5,990 ולא כפול" is asserted, not shown. A one-line comparison ("נגר מקומי בסולידי: ₪9,000+; אנחנו: ₪5,990 כי אין חנות, אין מלאי, ומידה אחת") would do more than the whole materials section.
- **"מחיר השקה" implies a discount that `/terms` §5 explicitly denies** — "אין באתר מחיר מבוטל, מבצע או הנחה." Pick one. As written it is soft fake-urgency with no expiry date and no reference price, and I notice.
- **Made in Chernivtsi, Ukraine, and the page does not address the obvious question** (`s-05.png`). No mention of the war, of what happens to my deposit if the workshop stops, of who insures the shipment, or of how a 5-year structural warranty is honoured when "אין לנו מחסן בישראל ואין לנו כוונה להחזיק אחד". The honesty is admirable and the risk is unmitigated. One paragraph — "אם הייצור נעצר, המקדמה חוזרת במלואה תוך X ימים" — would neutralise most of it.
- **The deposit amount is never stated.** "המתווה המתוכנן: מקדמה בהזמנה, היתרה במסירה." How much? 10%? 50%? To whom, by what method, refundable when? This is the number that decides whether I call back.
- **The return policy is a promise to write a policy later.** "יש החזרה? כן. התנאים המלאים מופיעים בתנאי השימוש" — and `/terms` contains no return terms at all, only "ההחזרה תיסגר בכתב לפני התשלום הראשון." Israeli distance-selling law gives me 14 days; custom-made goods are an exception; the page never says which one I am in.
- **Zero photographs of anything.** Six SVG technical drawings, no photo of the workshop, the oak, a finished top, the extension mechanism mid-slide, or a single human being. It is disclosed honestly in the footer, which is worth something, but for a ₪6,000 furniture purchase from an Instagram ad, a shaky 15-second video of the leaf being pulled out would be worth more than every drawing on the page combined.
- **No link back to the Instagram account I came from**, no follower count, no comments, no reviews, no press, no "who we are". The ad is the only social proof and you dropped the thread.
- **"שאלות שנשאלנו"** ("questions we were asked") on a product with no customers. Small, but it is the one place the copy tries to sound bigger than it is, and it stands out against an otherwise honest page.
- **The hero over-promises 10 seats.** H1 and spec strip say 220 = "10 מקומות"; the FAQ says "פתוח: **8 בנוחות**, 10 כשמוסיפים כיסא בכל קצה", and the plan drawing shows 3+3 with no end seats. Lead with 8, mention 10 as the squeeze — it will read as more credible, not less.
- **"דגם: גורן · 90×75"** in the hero spec strip. "גורן" is never explained anywhere on the site, and "90×75" without labels is a riddle. It is one of four cells crammed across 390px at 12px type.
- **Text at 11–13px in several places**: "ALUMA" at 11px, the four hero spec labels at 12px, the swatch labels טבעי/מעושן/מולבן at 12px, "רהיטי אלון, בהזמנה מראש" and "גורן · 90×75" at 13px, footer copyright at 12px. On a phone at arm's length these are squint-territory.
- **Colour swatch tap targets are 44px wide** — the bare minimum, and they sit in a row of three with 12px labels underneath. The consent checkbox itself is 20×20 (the wrapping `<label>` is 308×127, so it is tappable in practice, but the box looks unhittable).
- **The honeypot field is announced in the text layer**: `<label for="f-website">אל תמלאו שדה זה</label>` appears in the page's `innerText`. It is inside `aria-hidden="true"` and positioned off-canvas at x≈10,358, so it does not break layout or screen readers — but it will confuse anyone reading the DOM, and it is one CSS regression away from appearing in the form.
- **`אורך` is used as the label for both the hero spec value and the 160/220 toggle**, immediately above each other. Two identical labels, two different controls.
- **RTL line-breaking artefacts**: "הרכבה 20–25 דקות" wraps to "…הרכבה −20" / "25 דקות" at 360px (`w360-02.png`). Technically correct bidi, visually looks like a typo. Use a non-breaking hyphen in ranges.
- **Structured data has no seller**: the JSON-LD `Product`/`Offer` declares `price: 5990`, `PreOrder`, but no `seller`, no `Organization`, no `priceValidUntil` — the same missing-identity problem, machine-readable.
- **Nothing reads as machine-translated.** The Hebrew is genuinely native — "שישה ביום שני. עשרה בשישי בערב." is a line a person from here wrote. The foreign smell is not in the language, it is in the structure: a `.store` TLD, on a subdomain of `central-aparts` (an apartment-rental brand), for a furniture company with no name. That domain alone would make me close the tab if the copy were any worse. Buy `aluma.co.il`.

---

## What actually works — do not break these

1. **The size/colour configurator.** Tapping 160 ↔ 220 and the three swatches updates the elevation drawing, the seat count, the plan view and the hero spec strip instantly, with no flash and no layout shift (`toggle-220.png`, `swatch-smoked.png`). The drawing genuinely changes proportion, not just a caption. And the form tells me my choice travels with the lead — "הבחירה שלכם באתר נשלחת יחד עם הפנייה: אורך 160 ס״מ, גוון אלון טבעי" — which is a small, real reason to believe the callback will be competent.
2. **The form's error handling.** Submitting empty produces red-outlined fields with specific Hebrew messages under each one: "צריך שם כדי לדעת למי לפנות", "מספר טלפון ישראלי, למשל 050-000-0000", and for the unticked consent "צריך לאשר שאפשר לחזור אליכם" (`form-empty-submit.png`). Inline, next to the field, in plain language. Better than most Israeli lead forms.
3. **The logistics honesty.** Package dimensions (170×100×12 and 125×40×22), 0.31 m³, 55 kg, 8–10 weeks, "מגיע בשתי חבילות שטוחות", the door-and-elevator FAQ, "אין מלאי, אין חנות תצוגה, ואנחנו לא מתיימרים שיש", and "ההדמיות באתר הן שרטוטים טכניים … לא צילומים". This is the material that separates you from the company that took four months off me. It is currently doing its work from 4,000px down the page, next to a privacy policy that has no company name in it — which is why the honesty does not land. Fix the identity problems and this section becomes your best asset.

---

### Screenshot index (`C:\tmp\fx\`)
`s-01.png`–`s-10.png` full scroll at 390×844 · `w360-01.png`, `w360-02.png` at 360×800 · `cookie-after.png` notice after clicking הבנתי · `sticky-clean.png`, `sticky-mid.png` sticky bar buried · `toggle-220.png`, `swatch-smoked.png`, `swatch-white.png` configurator · `fit-150.png`, `fit-300.png`, `fit-450.png`, `fit-stale-empty.png` room-fit tool · `form-empty-submit.png`, `form-noconsent.png`, `form-badphone.png` validation · `pg-privacy.png`, `pg-terms.png`, `pg-accessibility.png`, `pg-thanks.png` sub-pages
