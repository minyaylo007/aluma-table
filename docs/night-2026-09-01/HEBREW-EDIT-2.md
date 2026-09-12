# עריכה לשונית 2 — אלומה גורן (החומר החדש)

Second Hebrew copy-edit pass, limited to the material added since `HEBREW-EDIT.md`.
Source reviewed: `furniture/i18n/he.json` (every value; the new keys in depth), seen in context in `furniture/dist/index.html`, `dist/thanks.html`, `dist/404.html`, and in the JS that composes the ETA line, the rotate hint, the room-fit verdicts and the form error line.
Scope: language only. No facts changed, no tokens touched, no country of origin added.

---

## Verdict

The new material is in better shape than what yesterday's pass started from, and most of it is simply native. The spec table (`מפרט · כל המספרים, במקום אחד`, `זמן אספקה`, `אחריות על המבנה`, `עובי משטח`), the gallery captions (`מהצד השני`, `הרגל והקורה`, `מלמעלה`, `מלפנים`), the three story blocks, the thanks page (`הפנייה נקלטה` / `קיבלנו. נחזור אליכם.` / `בתוך יום עסקים`) and the 404 (`יש לנו בדיוק עמוד אחד, וזה השולחן`) read as written in Hebrew, not translated into it; the register is consistent (plural imperative to the reader, impersonal present for how the table works), there are no gender slashes, the maqaf sits before every numeral (`מ־160`, `כ־55`, `ל־11 בנובמבר`), and the gershayim is inside abbreviations only — with one exception. The ETA line as it actually renders (`מזמינים היום — מגיע בערך בין 28 באוקטובר ל־11 בנובמבר`) is correct Hebrew, including the `בין … ל־` frame. What remains is small and specific: **two real errors** (the legal idiom in the cancellation FAQ uses the wrong preposition, and the packaging paragraph loses number agreement), **four turns of phrase that are still English or Russian under the skin** (`לנסיעה שטוחה`, `מפרט אמיתי`, `כלולים בכל הארץ`, `נסו שוב עוד קצת`), and **one typography leak** (gershayim used as quotation marks). Seven values in total; nothing that embarrasses the brand, but the cancellation-FAQ sentence matters because it is the one legal sentence on the product page.

---

## Corrections

Sorted: A outright errors → B unnatural / translated phrasing → C typography. Keys are exact `he.json` keys; `faq[N].a` is the 0-based index into the `faq` array (`faq[7]` = «אפשר לבטל או להחזיר?», `faq[8]` = «מי מייצר את זה?»). `current value` strings are exact and copy-pasteable. All {{TOKENS}} are unchanged.

### A. Outright errors

| key | current value (exact) | corrected value | why |
|---|---|---|---|
| `faq[7].a` | `כרגע אין מה לבטל: אנחנו לא מוכרים ולא גובים תשלום באתר. תנאי הביטול וההחזרה ייקבעו בכתב — יחד עם המחיר ומועד האספקה — לפני שתשלמו שקל, וזה מה שתקבלו לאישור. עסקה כזו כפופה לחוק הגנת הצרכן, ואת הזכויות שלכם לפיו איננו יכולים להתנות.` | `כרגע אין מה לבטל: אנחנו לא מוכרים ולא גובים תשלום באתר. תנאי הביטול וההחזרה ייקבעו בכתב — יחד עם המחיר ומועד האספקה — לפני שתשלמו שקל, וזה מה שתקבלו לאישור. עסקה כזו כפופה לחוק הגנת הצרכן, ועל הזכויות שלכם לפיו אי אפשר להתנות.` | The legal idiom for "contract out of / override statutory rights" is `להתנות על` (as in the statutes themselves: `אין להתנות על הוראות חוק זה`). `להתנות את הזכויות` means "to make your rights conditional" — a different claim, and one no lawyer would sign. Also `איננו יכולים` is literary inside an FAQ that says `אנחנו לא מוכרים` two sentences earlier; `אי אפשר` matches the voice. |
| `s3_p` | `170×100×12 ו־125×40×22 ס״מ, כ־55 ק״ג יחד — נכנס בדלת ובמעלית. המרכיב שלנו מגיע, מרכיב ב־20–25 דקות ולוקח את האריזות. משלוח והרכבה בכל הארץ כלולים במחיר.` | `170×100×12 ו־125×40×22 ס״מ, כ־55 ק״ג יחד — נכנסות בדלת ובמעלית. המרכיב שלנו מגיע, מרכיב ב־20–25 דקות ולוקח את האריזות. משלוח והרכבה בכל הארץ כלולים במחיר.` | The heading names `שתי אריזות` and the sentence enumerates both cartons — the only available subject is feminine plural, so `נכנסות`. Bare `נכנס` is the English "it fits" with no subject; spoken Hebrew tolerates it, written copy under a heading about two cartons does not. |

### B. Unnatural / translated phrasing

| key | current value (exact) | corrected value | why |
|---|---|---|---|
| `faq[8].a` | `נגרייה משפחתית שעובדת עם אלון אירופי. השולחן תוכנן לנסיעה שטוחה ולהרכבה בבית — כל שולחן נכנס לייצור אחרי שהוזמן.` | `נגרייה משפחתית שעובדת עם אלון אירופי. השולחן תוכנן למשלוח באריזה שטוחה ולהרכבה בבית — כל שולחן נכנס לייצור אחרי שהוזמן.` | `נסיעה שטוחה` is "flat travel" — a calque of flat-pack shipping; yesterday's pass already removed `שייסע` from the story lede for the same reason. The Israeli phrase is `משלוח באריזה שטוחה` (the site's own `אריזות שטוחות` vocabulary). |
| `rotate_hint` | `גוררים כדי לסובב. פרופורציות אמיתיות, מפרט אמיתי.` | `גררו כדי לסובב. פרופורציות אמיתיות, לפי המפרט.` | `מפרט אמיתי` ("a real spec") is a word-for-word carry of the English tagline and sounds like a denial that the spec is fake; what is meant is that the model follows the spec — `לפי המפרט`. And this string replaces the link text after the viewer loads, i.e. it is an instruction to the person holding the mouse, so the plural imperative (`גררו`, like `סובבו`, `השאירו`, `כתבו`) fits better than the impersonal `גוררים`, which the site reserves for describing how the table works. |
| `spec_included` | `כלולים בכל הארץ` | `כלולים במחיר, בכל הארץ` | Renders as the row `משלוח והרכבה — כלולים בכל הארץ`, i.e. "included anywhere in the country" — the English `included, anywhere in Israel` squeezed into two words. Hebrew needs to say what they are included *in*. |
| `s_rate` | `נשלחו כמה פניות מהחיבור הזה. נסו שוב עוד קצת, או כתבו לנו בוואטסאפ.` | `נשלחו כמה פניות מהחיבור הזה. נסו שוב בעוד כמה דקות, או כתבו לנו בוואטסאפ.` | `נסו שוב עוד קצת` reads as "keep trying a bit more" — the opposite of what a rate-limit message wants. "Try again in a little while" is `בעוד כמה דקות` / `מאוחר יותר`. |

### C. Typography

| key | current value (exact) | corrected value | why |
|---|---|---|---|
| `why1_p` | `משלוח לכל הארץ, הרכבה בבית, ופינוי האריזות. בלי תוספות בסוף ובלי ״החל מ־״: המחיר שרואים כאן הוא המחיר המלא, כולל הכול.` | `משלוח לכל הארץ, הרכבה בבית, ופינוי האריזות. בלי תוספות בסוף ובלי "החל מ־": המחיר שרואים כאן הוא המחיר המלא, כולל הכול.` | `״` (U+05F4) is the gershayim — abbreviations only (`מע״מ`, `ס״מ`). Here it is doing duty as a pair of quotation marks, which the house rules forbid, and low quotes are also out. Plain straight quotes are the standard Israeli web form and are bidi-safe (curly “ ” are not mirrored in RTL and come out reversed). In the JSON file this is written `\"החל מ־\"`. Note: the legal pages currently use gershayim as quotes too (`״אנחנו״`, `״האתר״`, `״דילוג לתוכן הראשי״`) — outside this task's file, flagged for whoever owns them. |

**Applied:** all 7 rows above were applied to `furniture/i18n/he.json` (JSON re-validated, key set unchanged, every `{{TOKEN}}` preserved, no other value touched). Rebuild `dist/` to pick them up.

---

## Reads as machine-translated or foreign (all fixed above)

1. `תוכנן לנסיעה שטוחה` — the table "travels flat": flat-pack shipping calqued through Russian/English.
2. `פרופורציות אמיתיות, מפרט אמיתי` — "real proportions, real spec", the English tagline's rhythm with Hebrew words.
3. `כלולים בכל הארץ` — "included anywhere in Israel" with the "in the price" dropped; only makes sense if you know the English.
4. `נסו שוב עוד קצת` — mistranslated "try again a little later".
5. `ואת הזכויות שלכם לפיו איננו יכולים להתנות` — "we cannot condition your rights": the legal idiom with an English preposition.
6. `כ־55 ק״ג יחד — נכנס בדלת` — English "it fits" with no subject after two feminine plural cartons.

Checked and **not** foreign, left alone: `שנספג בעץ במקום לשבת עליו` (carpenters do say a lacquer `יושבת על העץ`); `עוד מבטים` (fine as a gallery label; `מבטים נוספים` would be equally good); `ללא תשלום באתר` in the lead line (`ללא` is right in a `·`-separated label even though body copy says `בלי`); `מתעניינים בשולחן` in the WhatsApp prefill (the couple's "we" is exactly how Israelis open a Yad2/WhatsApp enquiry); `שמן ולא לכה` as a headline (terse, but native — and safer than `בשמן`, which reads like tinned fish); `חסר:` as the error label (a label, like "Missing:", not a predicate).

---

## The render-related terms

- **`הדמיה` for "3D render" — yes, exactly.** This is the word Israeli real-estate, kitchen and furniture sites put on rendered images (`הדמיה`, `הדמיה בלבד`, `התמונה להמחשה בלבד`). `רנדר` is studio jargon and `רינדור` is developer jargon; neither belongs on a customer page. The footer's fuller `הדמיות תלת־ממד` and the alt-text's `הדמיה תלת־ממדית` are the right long forms; the one-word badge is the right short form.
- **`סובבו את השולחן` — yes.** Plural imperative, matches `השאירו פרטים` / `דברו איתנו`, and is what 360° viewers on Israeli sites say (`סובבו`, `לחצו וגררו לסיבוב`).
- **`גרירה` / `גוררים` → `גררו כדי לסובב`.** The noun `גרירה` is standard UI Hebrew (`גרירה לסיבוב`, `גרור ושחרר`), and `גוררים` was not wrong — but as the hint that replaces the link text once the viewer is live it is an instruction, so the imperative reads more naturally and keeps the page's own rule (imperative for what you do, impersonal for how the table works). Applied.

---

## Verified as correct in the new material — leave alone

`made_to_order`, `eta_label` + `eta_and` (renders `בין 28 באוקטובר ל־11 בנובמבר`, correct frame, correct maqaf), `gallery_label`, `g_hero2`, `g_detail`, `g_end`, `g_top`, `g_front`, `s1_h`, `s1_p`, `s2_h`, `s2_p`, `s3_h`, all `spec_*` except `spec_included`, `hero_alt`, `render_tag`, `rotate`, `fit_almost_h`, `e_consent_short` (renders `חסר: שם, טלפון, אישור שאפשר לחזור אליכם.` — fine), `s_missing`, `why2_p`, `why3_p`, `story_h2`, `story_lede`, `f_note` (renders `אורך 160 ס״מ, גוון אלון טבעי`), all `thanks_*`, all `notfound_*`. Yesterday's corrections are all present in the rebuilt page (`שיפוע`, `אריזות`, `מאוחסן`, `ההבדל בין שמן־שעווה ללכה`, `חוזרים אליכם`, `בתוך יום עסקים`, no slashes, `ב־SMS`).

---

## Not language, noticed while reading (no action taken)

- `s2_p` / `s3_p` carry the numbers literally (`60`, `160`, `220`, `170×100×12`, `55`, `20–25`) while the parallel `claim*_p` / `log*_p` strings use `{{TOKENS}}`. If a number in `content.json` ever changes, these two paragraphs will silently disagree with the spec table.
- `s3_p` says flatly `נכנסות בדלת ובמעלית`; the lift FAQ, four screens later, says a small lift may mean standing the long carton up or taking the stairs. Same page, two different promises.
- `fit_exact_p` is reused for the "almost no clearance" verdict, so a 221–224 cm wall gets `יישארו 1 ס״מ בכל קצה` and a 220 cm wall gets `יישארו 0 ס״מ` — grammatical, but `0 ס״מ` is a number no Israeli would write in a sentence.
