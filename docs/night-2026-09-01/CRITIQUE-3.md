# CRITIQUE-3 — table.central-aparts.store (the rebuilt page)

Reviewer: homeowner, 41, Givatayim, 4 rooms, a 3.4 m dining wall, ₪6,000 budget, burned once by a furniture site, arrived from an Instagram ad on a phone.
Tested live with Playwright at 390×844 (iPhone) and 360×800 (Android), he-IL locale, plus /en/ on a phone and one desktop pass at 1440×900, 2026-09-02, page `Last-Modified: 10:52:50 UTC`. WebGL via SwiftShader for the 3D viewer; a 4× CPU throttle and simulated 4G/3G for the phone-speed numbers. Screenshots and measurement logs in `C:\tmp\fx\crit3\`.

Not re-argued, per the brief: the country of origin. Owner-blocked items (name, phone, address, WhatsApp, the legal placeholders) are marked as such and not re-litigated beyond one line each — but they are still costing leads and I say where.

---

## Verdict

**Yes — I would leave my number now, for the first time in three rounds. As a callback, not as a buyer, and despite the site more than because of it.** What changed my mind is not the 3D: it is that the page finally shows me a product instead of a drawing, in my colour and at my length, tells me on the first screen that my 3.4 m wall works ("פתוח ל־220 יישארו 60 ס״מ בכל קצה", `fit-340.png`), and — this is the part that matters to someone who has been burned — asks for almost nothing: "מיוצר לפי הזמנה · אספקה 8–10 שבועות · ללא תשלום באתר" is the second line I read, the form says "בלי תשלום ובלי התחייבות", the consent text says what happens to my number, and when I tapped submit too early the form no longer looked broken. The cost of leaving a number has dropped to "one phone call I can screen". That is why the answer flipped. It flipped *barely*: the seller still has no name, no phone, no address, and legal pages printing "שם העוסק — להשלמה" in orange boxes (`pg-privacy.png`, `pg-terms.png`) — so I will leave the number expecting the caller to say a company name and a deposit percentage in the first minute, and hang up if they do not. And the rebuild added three things that nearly lost me before I got to the form: the main button now says **"הזמנה מוקדמת ₪5,990"**, which is a buy button on a page that says four times you cannot buy here; the delivery line reads backwards ("בין באוקטובר 28 ל־בנובמבר 11", `crop-eta.png`); and "סובבו את השולחן" froze the page for 8 seconds on a phone-speed CPU with nothing on screen to say it was working, then froze it again for 13 seconds when I tapped a colour (`throttle.json`). A burned buyer reads a frozen page as a broken site. I got through because I know what a WebGL stall looks like; my wife would have closed the tab.

---

## Round-2 findings: status table

| # | Round-2 finding | Status | Evidence observed |
|---|---|---|---|
| 1 | Nobody to call, nowhere on a map; origin scrubbed | **OWNER-BLOCKED** | 0 × `tel:`, 0 × `mailto:`, 0 × `wa.me` across `/`, `/privacy`, `/terms`, `/accessibility`, `/thanks` and the three `/en/` twins; `cfg.wa` is `""`, all three `.js-wa` buttons are `display:none`; footer still "אלומה · רהיטי אלון, בהזמנה מראש"; `/terms` §14 is still four orange boxes; FAQ "מי מייצר את זה?" still "נגרייה משפחתית שעובדת עם אלון אירופי" (`faq-8.png`). |
| 2 | Empty submit shows one error, hides the other two | **FIXED** | Empty submit: page scrolls from y=10,294 to 9,480, focus lands on `#f-name`, all three field errors visible, status line "חסר: שם, טלפון, אישור שאפשר לחזור אליכם." (`form-empty-submit.png`). Bad phone: scrolls to `#f-phone`, "מספר טלפון ישראלי, למשל 050-000-0000" (`form-badphone.png`). |
| 3 | "Why this price" asserts, contradicts the terms | **PARTLY** | Copy fixed as suggested — "על מה חסכנו / על מה לא חסכנו", "בלי תוספות בסוף ובלי ״החל מ־״: המחיר שרואים כאן הוא המחיר המלא, כולל הכול", Hebrew quote marks (`m390-s-09.png`). Still not one number: no local-carpenter comparison, no deposit percentage. `/terms` §5 still says "מחיר השקה משוער… אינו מחייב עד לאישור הזמנה בכתב, והוא עשוי להשתנות". "על מה לא חסכנו" is still the third recital of the same five claims. |
| 4 | Cookie bar eats 15% of every screen and suppresses the sticky CTA | **FIXED** | `#notice` is removed from the DOM at load when no pixel/Clarity id is configured (`notice.remove()` in `app-next.js`); `body.has-notice` never set; the sticky bar is on screen from the first scroll (`m390-s-02.png`). |
| 5 | Room-fit tool argues with itself (90 vs 60), "בלי מרווח" at 15 cm, ignores "3.6" | **PARTLY** | One rule everywhere now: default box "נשארים 60 ס״מ פנויים בכל קצה?" and the 340 verdict both say 60 (`fit-empty.png`, `fit-340.png`); 250 → "נכנס, כמעט בלי מרווח … 15 ס״מ" (`fit-250.png`); 290/300 → "נכנס פתוח, אבל צמוד"; 450 → "נכנס בנוח" 115 cm. Still one dimension; "3.6", "2000" and "59" are still silently ignored with the default box left on screen (`fit-3.6.png`); the HTML says `min="100"` while the JS accepts 60; the 160/220 toggle still does not change the verdict. |

**Better / worse / sideways vs round 2.** *Better:* product imagery instead of six drawings; the first screen (headline → honesty line → price → dates → picture, all inside 844 px, `m390-01-first-load.png`); the form; the cookie bar; the fit-tool rule; an English twin that is real English, not a translation (`en-01.png`). *Worse:* the CTA wording regressed from an honest "השאירו פרטים" to "הזמנה מוקדמת ₪5,990"; the configurator that round 1 called "instant, no flash" now blanks the hero for 0.35–0.55 s on every tap; the 3D viewer is a new way to freeze the page; the delivery line is a new bidi bug; the sticky bar now covers the form's own submit button. *Sideways:* identity, deposit, legal placeholders, why-price arithmetic, "שאלות שנשאלנו", the `.store` subdomain, JSON-LD without a seller.

---

## The 5 most damaging remaining problems (ranked by lead cost)

The owner-blocked identity gap is still the largest single lead cost on the site; it is in the table above and I will not rank it again. These five are all buildable this week.

### 1. "סובבו את השולחן" freezes a phone for 8 seconds with no feedback, then 13 seconds per colour

**What I saw** (`throttle-viewer-300ms.png`, `throttle-viewer-on.png`, `viewer-2-on.png`, `viewer-5-smoked.png`, `throttle.json`, `viewer.json`, `canvas.json`): the link sits directly under the price on the first screen (y=505), so it is the first interactive thing a curious visitor taps. On tap the page loads `three.min.js` (135 KB brotli) from cdnjs and then generates the oak texture on the CPU — two 2048×1024 canvases per tone, every pixel through four noise lookups. On my desktop CPU that is a single **2.0 s** long task; at a 4× CPU throttle (a mid-range Android) the canvas appears **8.2 s** after the tap, with a **7.4 s** task during which nothing on the page responds. `aria-busy="true"` is set on the link but there is no CSS for it — 300 ms after the tap the screen is pixel-identical to before (`throttle-viewer-300ms.png`). Then, with the viewer open, tapping "מעושן" regenerates textures for the new tone: **6.7 s** on desktop, **13.2 s** of a blocked main thread at 4× (one 11.2 s task); "מולבן" costs another **5.0 s** on desktop. Android Chrome starts offering "wait / close page" at roughly 5 s of hang. When the viewer does appear, the table is drawn about a third smaller than the still it replaces (the 3D table spans ~400 of 780 device pixels versus ~620 for the render), the shadow becomes a hard grey parallelogram, and the link text turns into an underlined dead `href="#"` reading "גוררים כדי לסובב. פרופורציות אמיתיות, מפרט אמיתי." with no way back to the still (`viewer-3-dragged.png`, `canvas.json`). The canvas is also allocated at 1200×744 regardless of its 350×219 box, because `#viewer` is `display:none` at mount time and `clientWidth` reads 0.

**Why it costs leads:** the people who tap this are the engaged ones — the ones who would otherwise reach the form. A frozen page with no spinner reads as "site is broken", and a second freeze on the swatch reads as "phone is broken". Nobody blames three.js; they blame the shop.

**Fix:** stop generating textures on the main thread. Either pre-bake the three oak maps once (tileable 1024×512 JPEG/WebP per tone, ~40 KB each, `TextureLoader`), or generate at 512×256 inside a Worker with `OffscreenCanvas`, and generate all three tones once so a swatch switch is a material swap (the cached path already takes 135 ms). Add a visible busy state (`#rotate[aria-busy] { … }` spinner + "טוען…"). Keep the 3D at the same scale as the still (camera radius ≈ 3.0, not 3.9), restore the soft shadow (`radius`/`blurSamples` are set but `VSMShadowMap` on SwiftShader and low-end GPUs is hard-edged — test on a real phone), turn the hint back into text (not `<a href="#">`), add "חזרה לתמונה", and stop the idle turntable re-rendering every frame with a 2048² shadow map — render on interaction only. If none of that fits the week: replace the live 3D with a 24-frame turntable sprite (24 × ~10 KB) that swipes — same "rotate the table" promise, zero freeze.

### 2. The main CTA became a buy button on a page that says you cannot buy

**What I saw** (`m390-01-first-load.png`, `sticky-mid.png`, `m390-s-12.png`): hero button "**הזמנה מוקדמת ₪5,990**"; sticky bar "**הזמנה מוקדמת ₪5,990**"; eyebrow over the form "הזמנה מוקדמת"; form button "**אני רוצה שיחזרו אליי · ₪5,990**". Round 2's honest "השאירו פרטים" is gone (it survives only as a desktop-only masthead link). Meanwhile the line above the button says "ללא תשלום באתר", the FAQ says "לא באתר. אין כאן תשלום ואין כאן חיוב", the footer says "אי אפשר לשלם כאן", and `/terms` §2 says the product's "טרם החל ייצורו המסחרי".

**Why it costs leads:** two audiences, both lost. The burned buyer will not tap a button that says "pre-order ₪5,990" from an unnamed seller — that is exactly the button he regrets tapping last time. The trusting buyer taps it, lands on a callback form, and feels switched. And "I want a callback · ₪5,990" reads, on a phone, like the callback costs ₪5,990.

**Fix:** put the price next to the button, not in it, and make the verb match the action. Hero: price line "₪5,990 · כולל מע״מ, משלוח והרכבה", button "שיחזרו אליי — בלי תשלום". Sticky: "₪5,990 כולל הכול" as text, button "שיחזרו אליי". Form button: "אני רוצה שיחזרו אליי". Eyebrow: "השארת פרטים". Keep "הזמנה מוקדמת" as a status label ("לפני השקה · הזמנה מוקדמת"), never as a verb.

### 3. The delivery-date line — the rebuild's trust device — reads backwards, promises an order you cannot place, and is computed from the visit date

**What I saw** (`crop-eta.png`, `m390-01-first-load.png`, `desk-01.png`): the line is `<b class="num">28 באוקטובר</b>` inside an RTL sentence; `.num` forces `direction:ltr` on a Hebrew string, so on every device it renders "מזמינים היום — מגיע בערך בין **באוקטובר 28** ל־**בנובמבר 11**" — day and month swapped, and "ל־" glued to the wrong word. The dates are `today + 8 weeks` / `today + 10 weeks` in JavaScript: visit on 10 September and it says 5–19 November; the promise slides with the visitor, not with a production calendar. And "מזמינים היום" is not something I can do today: the FAQ says 8–10 weeks run "מאישור ההזמנה", which comes after a call, a written offer and a deposit — realistically a week or two after "today", which pushes a September visitor into late November, after the holidays the page also does not mention. The English twin renders correctly ("between 28 October and 11 November", `en-01.png`), which is how I know it is a Hebrew-only bug.

**Why it costs leads:** this is the one line written specifically to make the 8–10 weeks feel like a plan, and for the Hebrew reader it is the one line on the first screen that looks foreign. A sceptic who spots a reversed date stops reading the rest as carefully written.

**Fix:** remove `class="num"`/`dir` from the date spans (or write numerals only: "28.10–11.11", which needs no bidi). Reword: "משאירים פרטים היום ומאשרים הזמנה השבוע — השולחן אצלכם בערך בין 28.10 ל־11.11". Compute from "confirmation this week" (today + 7 days + 8/10 weeks), skip the holiday shutdown window, or drop the computation and hand-set a planning window per month.

### 4. The renders convince at hero size and give the game away up close — and the close-ups are the second thing you see

**What I saw** (`crop-hero-render.png`, `crop-detail-render.png`, `touch-gallery-1.png`, `touch-gallery-2.png`, `m390-s-06.png`, `m390-s-07.png`, `desk-gallery.png`): the hero render is a competent catalogue visualisation — right proportions, soft contact shadow, the black beam reads as steel, "הדמיה" is disclosed in the corner. I would not call it a video-game asset at that size. Then I swipe the gallery once and get "הרגל והקורה": a from-below close-up where the "oak" is a procedural streak pattern with no cathedral figure, no rays, no end grain on the "קנט אלון מלא" (the edge is the same colour and grain as the face — the render contradicts the copy), corners razor-sharp, and the underside a uniform plane. That *is* a game asset, and it is the first image after the hero and the first image in the story section. The "מהקצה" card is worse: two splayed legs under a slab, a black notch (the beam end) in the middle, and a hard grey shadow slab that clips at the frame edge (`m390-s-07.png`); peeking in from the side of the carousel it looks like a broken image (`touch-gallery-1.png`, left edge). "מלמעלה" is a beige rectangle. The renders are 2.25:1 but the hero box is 16:10 (`width="2400" height="1500"`), so 63 of the hero's 219 CSS pixels are empty paper above and below the table — the table floats small in a beige void, with no floor, wall, chair or person to tell me it is 160 cm and not 100. The smoked tone is a flat brown plane (`viewer-5-smoked.png`, `cfg-smoked.png`); the swatches are flat rectangles; nothing on the page shows what "מעושן" or "מולבן" look like in wood.

**Why it costs leads:** the rebuild's whole bet is "now it looks like a product". At hero size it does; the gallery then spends three of five cards undoing it. For a ₪6,000 veneer top, the close-up is where I decide whether the finish is real.

**Fix, in order of return:** (1) real oak maps — photo-scanned veneer with figure, a distinct end-grain/solid-edge material 3–5% darker than the face, a satin oil sheen via an HDRI environment; (2) a scene — floor plane with a floor material, a wall line, one chair (the fit tool asks me for centimetres; the picture gives me none); (3) crop the hero frame to the render's aspect and fix the `width/height` attributes; (4) replace "הרגל והקורה" and "מלמעלה" with the two images the copy keeps promising and never shows — the leaf half-pulled, and the two cartons standing at a door; (5) a slight grain/noise pass and shallow depth of field so the flatness stops reading as CG; (6) three real veneer sample photos next to the swatches, even phone photos.

### 5. Every swatch or length tap blanks the hero for half a second — the configurator that used to be instant now flashes

**What I saw** (`cfg-smoked-mid.png`, `cfg-natural-mid.png`, `throttle.json`, `interact.json`): `paintHero()` adds `.is-fading` (opacity 0) immediately and only swaps the source when a 1200-px WebP has loaded — but the `<picture>` then picks the AVIF, which loads separately. Net effect at simulated 4G: the hero is blank or ghosted from ~170 ms to ~500 ms after the tap; at 3G from 166 ms to 722 ms, complete at 848 ms. `cfg-smoked-mid.png` is an empty hero with only "הדמיה" in the corner. On a desktop connection the first smoked switch still took 850 ms. Meanwhile the 160/220 thumbnails always show natural oak whatever tone is selected (`cfg-smoked.png`, `cfg-white.png`), and the wasted `<link rel=preload>` for the 800-px WebP throws a console warning on every load because the AVIF is what gets used.

**Why it costs leads:** round 1 named this control as the best thing on the page *because* it was instant. A blank rectangle on every tap makes the three-tone promise feel like a slideshow that has not loaded.

**Fix:** keep the old image on screen until the new one has decoded (`new Image()` on the *same* format the `<picture>` will pick, or `img.decode()` on a second stacked `<img>` and cross-fade); preload all six hero variants after load (6 × ~6 KB AVIF ≈ 40 KB); drop the WebP preload or make it AVIF; render the chips per tone (`front-{tone}-{state}`).

---

## Hebrew in the new sections — exact current text → corrected

Nothing here is machine-translated. The problems are three lines that read as translated marketing, one rendering bug, and copy that contradicts itself.

**Hero**

- `מזמינים היום — מגיע בערך בין 28 באוקטובר ל־11 בנובמבר` (rendered as "בין באוקטובר 28 ל־בנובמבר 11") → **`משאירים פרטים היום ומאשרים הזמנה השבוע — השולחן אצלכם בערך בין 28.10 ל־11.11`** (and drop `class="num"` from any span that contains Hebrew).
- `הזמנה מוקדמת` (button label, hero and sticky) → **`שיחזרו אליי — בלי תשלום`** (price as a line beside it, not inside it).
- `אני רוצה שיחזרו אליי · ₪5,990` (form button) → **`אני רוצה שיחזרו אליי`**.
- `הזמנה מוקדמת` (eyebrow over the form) → **`השארת פרטים`**.
- `מיוצר לפי הזמנה · אספקה 8–10 שבועות · ללא תשלום באתר` — fine; for register consistency with the rest of the page (which says "בלי" everywhere) → **`… · בלי תשלום באתר`**.
- Viewer hint after opening: `גוררים כדי לסובב. פרופורציות אמיתיות, מפרט אמיתי.` — "real proportions, real spec" is an English slogan wearing Hebrew → **`גררו כדי לסובב · המידות והפרופורציות לפי המפרט`**, or simply **`גוררים כדי לסובב`**.
- The `.hero-media img` `alt`: `…, הדמיה תלת־ממדית` — fine, keep.

**Gallery captions** — `מהצד השני` · `הרגל והקורה` · `מהקצה` · `מלמעלה` · `מלפנים` — native, fine. If the close-up stays: `הרגל והקורה` → **`הרגל והקורה, מלמטה`** (the viewer is looking up at it).

**Claims (image-led)**

- `הרכבה 20–25 דקות עם מפתח אלן אחד — ואנחנו מרכיבים אצלכם.` — the hex key tells me I am assembling; the dash tells me I am not → **`ההרכבה לוקחת 20–25 דקות, ואנחנו עושים אותה אצלכם.`**

**Story blocks ("איך זה נעשה")**

- `170×100×12 ו־125×40×22 ס״מ, כ־55 ק״ג יחד — נכנס בדלת ובמעלית.` — contradicts the FAQ two screens later ("במעלית קטנה נצטרך להעמיד אותה, ואם גם זה לא עובד — לעלות במדרגות") → **`170×100×12 ו־125×40×22 ס״מ, כ־55 ק״ג יחד — עובר בדלת רגילה; במעלית קטנה מעמידים את האריזה, ואם צריך — עולים במדרגות.`**
- `המרכיב שלנו מגיע, מרכיב ב־20–25 דקות ולוקח את האריזות.` — good, keep; this is the line the claim above should have been.
- `נגרייה משפחתית, אלון אירופי, שולחן אחד` — unchanged from round 2; not re-argued.

**Spec sheet ("כל המספרים, במקום אחד")**

- `משקל ≈ 55 ק״ג` — the ≈ sign is not something an Israeli spec sheet prints → **`משקל כ־55 ק״ג`**.
- `אחריות על המבנה` → **`אחריות למבנה`** (and add what it covers: `למבנה — רגליים, קורה, מנגנון ההארכה. לא לגימור.` if that is the truth).
- `זמן אספקה 8–10 שבועות` → **`זמן אספקה 8–10 שבועות מאישור ההזמנה`** — the "from when" is the whole question.
- `לוח הארכה 60 ס״מ`, `עובי משטח 40 מ״מ`, `אריזה א׳ / אריזה ב׳`, `קורה פלדה בשחור מט`, `גימור שמן־שעווה מט` — fine.

**Why-price**

- `אלון אמיתי ולא הדפס, קנט אלון מלא בהיקף, לוח הארכה שנשלף ביד אחת, גימור שמן־שעווה, ואחריות 5 שנים על המבנה.` — third recital → **`אחריות 5 שנים למבנה — ואם משהו זז, מתקנים אצלכם בבית.`** (only if true).

**FAQ**

- `שאלות שנשאלנו` (eyebrow) → **`שאלות ותשובות`** alone, or **`מה שכדאי לשאול`**.
- `עסקה כזו כפופה לחוק הגנת הצרכן, ואת הזכויות שלכם לפיו איננו יכולים להתנות.` — "להתנות" takes "על" → **`עסקה כזו כפופה לחוק הגנת הצרכן, ועל הזכויות שלכם לפיו אי אפשר להתנות.`**

**Form and status strings**

- `חסר: טלפון.` when the phone is filled but invalid (`form-badphone.png`) → **`מספר הטלפון לא תקין.`** (needs its own string; "חסר" is right only when the field is empty).
- `נשלחו כמה פניות מהחיבור הזה. נסו שוב עוד קצת, או כתבו לנו בוואטסאפ.` and `לא הצלחנו לשלוח. נסו שוב, או כתבו לנו בוואטסאפ.` — there is no WhatsApp on the site; the failure message sends me to a channel that does not exist → **`… נסו שוב בעוד כמה דקות.`** until `cfg.wa` is set, then restore.
- Marketing consent `… ב־SMS ובוואטסאפ. ניתן להסיר בכל עת. (לא חובה)` — the email mention is gone; fine now.

**Legal (Hebrew that is now simply wrong about the site)**

- `/terms` §4: `התמונות באתר הן שרטוטים טכניים של המוצר המתוכנן ולא צילומים שלו` → **`התמונות באתר הן הדמיות תלת־ממד של המוצר המתוכנן ולא צילומים שלו`** (the footer already says this correctly).
- `/terms` §5 `מחיר השקה משוער … עשוי להשתנות` vs the page's `המחיר שרואים כאן הוא המחיר המלא, כולל הכול` — one of them has to change; the honest version is **`המחיר מובטח למי שמאשר הזמנה בכתב עד [תאריך]`** in both places.

**English twin** — `Model GOREN · natural oak · 160 cm · 6 Seats` → **`6 seats`**. Otherwise the English is idiomatic and shorter than the Hebrew; leave it.

---

## Everything else, by severity

**Questions the page still does not answer** (a buyer's list, in the order I asked them):

- How much is the deposit, to whom is it paid, by what method, and does it come back in full if the workshop stops or the date slips by more than X weeks? "מקדמה בהזמנה, היתרה במסירה" is still the whole answer.
- Can I pay in instalments (תשלומים)? Card, Bit, transfer? Do I get an Israeli VAT invoice, from which entity? (owner-blocked, but the *question* should be on the page.)
- What does "אחריות 5 שנים על המבנה" exclude — the veneer, the finish, the slide mechanism — and who comes to fix it, where?
- The mechanism: what do the halves slide on (wood, metal runners)? Does the leaf lock in? Is there a visible seam at the joins? Does the open table rock?
- Legroom at the ends. The A-frame legs sit ~26 cm in from each end (`goren3d.js`: `FRAME_INSET 0.26`) and the steel beam's underside is ~56 cm above the floor along the centreline. The plan drawing sells "כיסא בכל קצה" for 10 seats; an adult at the end has a trapezoid frame between the knees. Nothing on the page addresses it.
- Chairs: 3 chairs of 45 cm on a 160 side is 135 cm — what chair width did you plan for?
- What do "מעושן" and "מולבן" look like on real veneer? Can I get a sample?
- Care: how often to re-oil; what a hot pot or a wine ring does to an oil-wax finish.
- Floor: pads on the legs? Noise on tiles?
- Delivery: which days, what time window, is "בכל הארץ" really Eilat and the Golan, is carrying up stairs when the lift fails extra, who inspects damage at assembly?
- Return: the FAQ says terms come "בכתב"; distance-selling law gives 14 days on standard goods and exempts made-to-order — which one am I in?
- Will the price rise after "השקה", by how much, and when?
- How many have been made? Zero is an acceptable answer if it is written down.

**High**

- **OWNER-BLOCKED, still shipped:** `/privacy` 6 × "להשלמה", `/terms` 8 ×, `/accessibility` 7 × in orange dashed boxes, on both language versions (`pg-privacy.png`, `pg-terms.png`, `pg-accessibility.png`, `status /en/terms: todo 8`). `/accessibility` §5–6 still names the alternative channel and the accessibility officer as placeholders. `/terms` §9 and `/accessibility` §4 still describe a WhatsApp button that does not exist.
- **The sticky bar covers the form's own submit button** when it reaches the bottom of the screen: submit at y 778–843, sticky at 760–844, `elementFromPoint` on the submit's centre returns the sticky bar (`sticky-over-submit.png`). It also stays up while I am inside the form (`stickyLanded.stickyOn: true`), so there are two dark ₪5,990 buttons on screen and the top one scrolls me back to the top of the section I am already in. Hide `.stickybar` while `#form` intersects.
- **Deposit and stop-production refund** still unstated anywhere (see round 2 #1 fix, second half — not owner-blocked; it is a sentence).
- **Fit tool** still asks one dimension; silently ignores decimals ("3.6" → nothing, `fit-3.6.png`), metres and out-of-range; `min="100"` in HTML vs 60 in JS; the 160/220 toggle has no effect on the verdict and nothing says the verdict assumes 220.

**Medium**

- **Terms §2/§4/§5 contradict the page:** "טרם החל ייצורו המסחרי" vs "מזמינים היום"; "שרטוטים טכניים" vs 3D renders; "מחיר משוער" vs "המחיר המלא, כולל הכול".
- **Story vs FAQ on the lift** ("נכנס בדלת ובמעלית" vs "במעלית קטנה נצטרך להעמיד … לעלות במדרגות").
- **Gallery on desktop** is five thumbnails at five different scales — a full table, a cropped underside, a stool-like end view with a clipped shadow, a beige rectangle, a full table (`desk-gallery.png`). On the phone, the peek carousel works with a real swipe (one card per swipe, `touch-gallery-1.png`), but in my synthetic-touch run it settled at scrollLeft −235/−471 on a 278 px card pitch, i.e. `scroll-snap` did not snap — verify on a real device before trusting the snap.
- **JSON-LD** still has no `seller`/`Organization`, and says `"material":"Oak"` for a veneer-on-plywood top.
- **"שאלות שנשאלנו"** still heads an FAQ for a product with no customers.
- **Hero `<img width="2400" height="1500">`** does not match the 2.25:1 renders; the 16:10 box wastes 30% of the hero on paper.
- **Wasted preload** of `hero-natural-closed-800.webp` (AVIF is chosen) — console warning on every load.
- **three.min.js r160 from cdnjs** logs a deprecation warning; r160 is the last release that ships this build. Pinning is fine; know that there is no upgrade path without switching to modules.
- **Hint text after opening the viewer** is an underlined `<a href="#">` with `cursor:pointer` that does nothing (`canvas.json`).

**Low**

- **Text under 14 px:** "ALUMA" 10 px, "הדמיה" 12 px, © 12 px, swatch and chip labels, "גוון האלון", "אורך", the state-badge and the gallery captions all 13 px (`m390-info.json`).
- **Tap targets:** "סובבו את השולחן" 135×31 px; consent checkbox 20×20 (the label is tappable, the box looks not); footer links 25 px tall; "מדיניות הפרטיות" inline link 19 px.
- **Phone regex** accepts a 14-digit "05212345678901" and "972521234567" without "+"; rejects "054.123.4567".
- **`/en` without the trailing slash → 404** (the switcher links `/en/`, so only typed URLs).
- **`/privacy` §9** still documents the `?me=1` opt-out parameter in a public policy.
- **Chips 160/220** always natural oak (see #5).
- **Domain** still `table.central-aparts.store`; no Instagram link back to the account the ad came from.
- **Page weight is fine:** 20 requests, ~150 KB of assets plus ~90 KB HTML/CSS/JS, DOMContentLoaded 641 ms, load 1.1 s at simulated 4G, no horizontal overflow at 390 or 360 (`m360-01-first-load.png`), 13 screens of scroll (10,283 px). Nothing to fix here; noted so nobody "optimises" it.
- **Regression check:** nothing that worked in round 2 is broken except the CTA wording and the hero flash; the sticky-bar-over-submit is new because the bar is now always on.

---

## What works — do not break these

1. **The first screen, and the honesty line on it.** Brand → "שולחן אלון שמתארך מ־160 ל־220" → lede → "מיוצר לפי הזמנה · אספקה 8–10 שבועות · ללא תשלום באתר" → price → "מחיר השקה · כולל מע״מ · משלוח והרכבה בכל הארץ" → the table, all inside 844 px at 390 and inside 800 px at 360, no horizontal scroll (`m390-01-first-load.png`, `m360-01-first-load.png`). The green-dot line is the sentence that lowered the cost of leaving a number; keep it above the button whatever the button ends up saying.
2. **The form.** Per-field messages ("צריך שם כדי לדעת למי לפנות"), a summary line, scroll-and-focus to the first bad field, a consent text that says why you want the number and for how long you keep it, a separate optional marketing box with the email mention removed, and "הבחירה שלכם באתר נשלחת יחד עם הפנייה: אורך 160 ס״מ, גוון אלון טבעי" under the button (`form-empty-submit.png`, `m390-s-12.png`). Same on `/en/` (`en-form-empty.png`). Fix the sticky overlap without touching any of this.
3. **The spec sheet and the veneer paragraph.** "כל המספרים, במקום אחד" (`m390-s-08.png`) puts warranty, lead time, both sizes, both cartons, weight, volume, assembly time and every material in one scrollable table, and the note under it — "למה לא אלון מלא לכל המשטח: משטח אלון מלא ברוחב 90 ס״מ עובד עם הלחות — מתרחב, מתכווץ, ועם הזמן מתעקם" — is the most persuasive paragraph on the site. It is the reason I stopped minding "פורניר". Together with the fit tool's single 60 cm rule and the downstream sync (badge, size cards, gallery, story images and form note all follow the swatch), this is the part of the page a buyer can check against a tape measure.

---

### Screenshot index (`C:\tmp\fx\crit3\`)
`m390-01-first-load.png`, `m390-s-01.png`–`m390-s-13.png` full scroll at 390×844 · `m360-01-first-load.png`, `m360-s-01.png`–`m360-s-13.png` at 360×800 · `crop-eta.png` (date line at 4×), `crop-hero-render.png`, `crop-detail-render.png` · `cfg-smoked-mid.png`, `cfg-natural-mid.png` (blank hero mid-switch), `cfg-smoked.png`, `cfg-white.png`, `cfg-size220.png`, `cfg-natural.png`, `cfg-size160.png` configurator · `viewer-0-before.png`, `viewer-2-on.png`, `viewer-3-dragged.png`, `viewer-4-smoked-mid.png`, `viewer-5-smoked.png`, `viewer-6-open.png`, `viewer-7-white.png`, `throttle-viewer-300ms.png`, `throttle-viewer-on.png`, `touch-canvas-0.png`, `touch-canvas-1.png` 3D viewer · `gallery-0.png`, `touch-gallery-1.png`–`touch-gallery-3.png` carousel · `fit-empty.png`, `fit-340.png`, `fit-250.png`, `fit-450.png`, `fit-cleared.png`, `fit-3.6.png`, `fit-160.png`, `w360-fit-340.png`, `en-fit-340.png` room-fit · `faq-6.png`–`faq-9.png` · `form-1.png`, `form-2.png`, `form-empty-submit.png`, `form-badphone.png`, `en-form-empty.png`, `w360-form.png` form · `sticky-mid.png`, `sticky-landed.png`, `sticky-over-submit.png` sticky bar · `en-01.png`–`en-13.png` English twin · `pg-thanks.png`, `pg-en-thanks.png`, `pg-privacy.png`, `pg-terms.png`, `pg-accessibility.png` sub-pages · `desk-01.png`–`desk-06.png`, `desk-gallery.png` at 1440×900 · `w360-config.png`, `w360-spec.png`, `w360-why.png`, `w360-signoff.png` · `og.png` the share card · logs: `m390-info.json`, `m360-info.json`, `interact.json`, `viewer.json`, `canvas.json`, `throttle.json`, `touch.json`, `pages.json`.
