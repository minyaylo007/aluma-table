# עריכה לשונית — אלומה גורן

Hebrew copy edit / proofread of the built `dist/` output.
Scope: language only. No design, no code structure, no facts changed.

---

## Verdict

The Hebrew is **good — better than 90% of Israeli small-brand landing pages — but it is not yet native.** The voice is right (short sentences, concrete numbers, no adjective soup), the maqaf usage with numerals (`מ־160`, `כ־55`, `ה־IP`) is correct where most Israeli sites get it wrong, and the legal pages are drafted by someone who actually read the statutes. **The single biggest weakness is the technical vocabulary of the product itself.** The moment the page gets specific about the table — the one place where a furniture buyer decides whether you are a real workshop or a dropshipper — the words stop being Hebrew. `סקוסית` is not a Hebrew word at all; it is a transliteration of the Russian *скос* with a Hebrew feminine ending, and it appears twice, including in the alt-text of the cross-section drawing that is supposed to prove the product is real. Around it sit a cluster of calques that read as translated-from-Russian to a native ear: `ההארכה שמורה בתוך השולחן`, `כוונה להחזיק אחד`, `לא מתיימרים שיש`, `ההבדל מלכה`, `היא תיסע בעמידה`, `כתבו לנו את קומה`. A second, smaller weakness: the page cannot decide who it is talking to — plural (`השאירו`, `אצלכם`), impersonal (`מודדים`), and gender slashes (`מבקש/ת`, `חייב/ת`, `אחראי/ת`) all appear, and `accessibility.html` switches from `נתקלת` to `נתקלתם` inside one section.

**On `סקוסית` specifically:** it returns zero results in Hebrew woodworking sources. The trade word Israeli carpenters and panel suppliers actually use for a chamfer/bevel is **`פאזה`** (from German *Fase*; e.g. mivnit.co.il sells "שירות הוספת פאזה עבור פלטות עץ", and the standard נגרות glossaries define it as CHAMFER). The plain-Hebrew word a homeowner will understand without help is **`שיפוע`**. Recommended: `שיפוע` in the customer-facing spec line, `פאזה` only if you want to sound like the workshop. Both are correct; `סקוסית` is not a word.

**Terms that are correct and should NOT be touched:** `פורניר` (veneer), `דיקט` (plywood), `קנט` / `סרט קנט` (edge / edge banding tape — the contrast `קנט אלון מלא, לא סרט קנט` is exactly how an Israeli furniture buyer thinks about it), `מפתח אלן` (hex key), `מט` (matte), `שולחן נפתח` (extendable — this is IKEA Israel's own term), `הארכה` (leaf), `שמן־שעווה`, `רגליים טרפזיות`, `מע״מ`, `ת״י 5568`, `חוק הגנת הפרטיות, התשמ״א־1981`.

---

## Register decision

**Chosen convention: second-person plural (גוף שני רבים) in all marketing copy; impersonal present (בינוני סתמי) only for describing a process; zero gender slashes anywhere; singular masculine + the standard `בלשון זכר מטעמי נוחות` disclaimer in the legal pages only.**

Why: plural is what every Israeli commercial site uses (`השאירו פרטים`, `נחזור אליכם`) because it is warm, it is *already* gender-inclusive with no typographic cost, and it does not force a slash. The impersonal present (`מודדים מקיר לקיר`, `מושכים, מרימים, סוגרים`) is not a competing register — it is the normal Hebrew way to describe *how a thing works* rather than *what you should do*, and mixing the two is native, not sloppy. What is not native is the slash: `מבקש/ת`, `חייב/ת`, `תבחר/י`, `הימנע/י`, `משתמש/ת`, `אחראי/ת`. Slashes are a form-filling convention that leaked into prose; in body copy they read bureaucratic and instantly translated. Where the sentence is about the *reader themselves* in first person (the consent checkbox), the fix is not a slash and not a gender — it is to rewrite so gender never arises: `אשמח ש...` instead of `אני מבקש/ת ש...`. In `terms.html` the slashes are additionally self-contradictory: the same paragraph declares `התנאים מנוסחים בלשון זכר מטעמי נוחות בלבד` and then writes `מסכים/ה`. Pick one — the disclaimer — and delete the slashes.

---

## Corrections

Sorted by severity: outright errors → unnatural / translated phrasing → typography. `current text` strings are exact and copy-pasteable.

### A. Outright errors (wrong word, wrong grammar, wrong gender)

| file | current text | corrected text | why |
|---|---|---|---|
| index.html | `מ״מ, סקוסית בצד התחתון` | `מ״מ, שיפוע בצד התחתון` | `סקוסית` is not a Hebrew word — transliterated Russian *скос*. Zero hits in Hebrew woodworking. Trade term is `פאזה`, plain term `שיפוע`. |
| index.html | `וסקוסית בצד התחתון שגורמת לקצה להיראות דק` | `ושיפוע בצד התחתון שגורם לקצה להיראות דק` | Same non-word, in the drawing's alt-text. Also fixes gender: `שיפוע` is masculine → `שגורם`. |
| index.html | `כתבו לנו את קומה ואת סוג המעלית ונבדוק לפני` | `כתבו לנו באיזו קומה אתם ואיזו מעלית יש בבניין, ונבדוק מראש` | `את קומה` is ungrammatical — a definite object with no article. `ונבדוק לפני` is a dangling adverb (before what?). |
| index.html | `זה בדיוק ההבדל מלכה — לכה שנשרטת מחייבת ליטוש של כל המשטח.` | `זה בדיוק ההבדל בין שמן־שעווה ללכה: לכה שנשרטת מחייבת ליטוש של כל המשטח.` | `ההבדל מ־` does not exist in Hebrew. It is `ההבדל בין X ל־Y` (or `שונה מ־`). Direct calque. |
| index.html | `ואנחנו לא מתיימרים שיש` | `ואנחנו לא מעמידים פנים שיש` | `מתיימר` takes an infinitive (`מתיימר להיות`), never a `ש־` clause. Ungrammatical. |
| index.html | `עד לחות עבודה יציבה` | `עד ללחות יציבה` | Missing preposition `ל` after `עד`; `לחות עבודה` is a Russian/German calque with no Hebrew currency. |
| terms.html | `ולחזרה אלייך בלבד` | `ולחזרה אליך בלבד` | `אלייך` (double yod) is **feminine** singular. The document declares itself masculine two paragraphs earlier. Spelling/gender error. |
| index.html | `אנחנו חוזרים בטלפון, עוברים על הפרטים,` | `אנחנו חוזרים אליכם בטלפון, עוברים על הפרטים,` | `חוזרים` here needs its complement — `חוזרים אליכם`. Without it the verb reads as "we return by phone" (i.e. come back). |
| accessibility.html | `אפשר להשאיר הודעה בכל שעה\n  ואנחנו חוזרים.` | `אפשר להשאיר הודעה בכל שעה ואנחנו חוזרים אליכם.` | Same missing complement. |
| index.html | `משייפים קלות את האזור ומורחים שוב` | `משייפים קלות את האזור ומורחים שמן מחדש` | `מורחים` with no object. In Hebrew you cannot leave `מרח` intransitive. |
| accessibility.html | `רואה חשיבות רבה במתן שירות שוויוני לכלל הלקוחות, ופועלת להנגשת האתר` | `רואים חשיבות רבה במתן שירות שוויוני לכלל הלקוחות, ופועלים להנגשת האתר` | Gender/number mismatch with the `שם העוסק` placeholder (masculine `עוסק` + feminine `ופועלת`). First-person plural sidesteps it and matches the rest of the page (`אנחנו מעדיפים`, `אנו ממשיכים`). Prepend `אנחנו` if the placeholder is dropped. |
| accessibility.html | `נתקלת בבעיית נגישות באתר? נשמח מאוד לשמוע, ופנייתך תטופל בהקדם האפשרי.` | `נתקלתם בבעיית נגישות באתר? נשמח מאוד לשמוע, ופנייתכם תטופל בהקדם האפשרי.` | The very next paragraph uses `נתקלתם` / `תציינו` / `השתמשתם`. Singular here is an internal inconsistency. |
| index.html | `אני מבקש/ת שתיצרו איתי קשר בטלפון בנוגע לפנייה הזו.` | `אשמח שתיצרו איתי קשר בטלפון בנוגע לפנייה הזו.` | Removes the slash without picking a gender; also warmer, which suits a consent checkbox nobody wants to read. |
| privacy.html | `אינך חייב/ת על פי דין למסור לנו מידע כלשהו.` | `אינך חייב על פי דין למסור לנו מידע כלשהו.` | Slash removed per register decision. **Also add** to §1: `המדיניות מנוסחת בלשון זכר מטעמי נוחות בלבד ומופנית לכל אדם.` (terms.html already has this line; privacy.html does not.) |
| privacy.html | `אם תבחר/י שלא למסור אותם` | `אם תבחר שלא למסור אותם` | Same. |
| terms.html | `אם אינך מסכים/ה להם,\n  אנא הימנע/י משימוש באתר.` | `אם אינך מסכים להם, אנא הימנע משימוש באתר.` | Slashes contradict the `בלשון זכר מטעמי נוחות` disclaimer in the same paragraph. |
| accessibility.html | `האתר טרם נבדק ידנית על ידי משתמש/ת בתוכנת הקראת מסך.` | `האתר טרם נבדק ידנית על ידי משתמשים בתוכנת הקראת מסך.` | Slash removed; plural is the natural form here anyway. |
| accessibility.html | `אחראי/ת נגישות:` | `אחראי נגישות:` | This is a named individual — write the gender that matches the person once the placeholder is filled. A slash in a contact list looks like an unfinished form. |
| privacy.html | `נתוני הגלישה הטכניים נמחקים אוטומטית לאחר\n  <span class="num">180</span> יום. לאחר מכן המידע יימחק או יהפוך לאנונימי.` | `לאחר מכן פרטי הפנייה יימחקו או יהפכו לאנונימיים. נתוני הגלישה הטכניים נמחקים אוטומטית לאחר <span class="num">180</span> יום.` | Logical error, not just style: as written, "after that the information will be deleted" follows a sentence that already deleted it. `לאחר מכן` belongs to the 24-month retention clause. Legal meaning preserved exactly, order fixed. |
| privacy.html | `את המידע האישי שאנו מחזיקים אודותיך` | `את המידע האישי שאנו מחזיקים עליך` | `אודות` cannot stand alone — it is `על אודות`. `מידע אודותיך` is a well-known error; `מידע עליך` is both correct and plainer. |
| privacy.html | `ואיננו אוספים ביודעין מידע אודותיהם` | `ואיננו אוספים ביודעין מידע עליהם` | Same. |

### B. Unnatural / translated phrasing

| file | current text | corrected text | why |
|---|---|---|---|
| index.html | `ייכנס אצלי בבית?` | `ייכנס לי בבית?` | `נכנס` governs `ל`, not `אצל`. `אצלי בבית` is fine on its own but not with this verb — it is the Russian *у меня дома* pattern. |
| index.html | `אורך הקיר שלאורכו יעמוד השולחן` | `אורך הקיר שלידו יעמוד השולחן` | `אורך ... לאורכו` in five words is a stumble no Israeli would write. |
| index.html | `כי אין לנו מחסן בישראל ואין לנו כוונה להחזיק אחד.` | `כי אין לנו מחסן בישראל, ולא מתכוונים לפתוח כזה.` | `להחזיק אחד` is a bare English/Russian calque ("to hold one"). Hebrew does not use `אחד` as a pronoun this way. |
| index.html | `השולחן תוכנן מראש כך שייסע בשתי חבילות שטוחות ויורכב בבית` | `השולחן תוכנן מראש כך שיגיע בשתי אריזות שטוחות ויורכב בבית` | Tables do not `נוסעים`. Also `חבילה`→`אריזה`: in Israeli furniture Hebrew a flat-pack is `אריזה שטוחה` (IKEA Israel's own wording); `חבילה` is what a courier carries. |
| index.html | `מגיע בשתי חבילות שטוחות, <span class="num">0.31</span> מ״ק סה״כ.` | `מגיע בשתי אריזות שטוחות, בנפח כולל של <span class="num">0.31</span> מ״ק.` | Same `אריזה` fix; `סה״כ` is invoice language dropped into body copy. |
| index.html | `שתי חבילות: <span class="num" dir="ltr">170×100×12</span>` | `שתי אריזות: <span class="num" dir="ltr">170×100×12</span>` | Consistency. |
| index.html | `<desc id="boxDesc">שתי חבילות שטוחות:` | `<desc id="boxDesc">שתי אריזות שטוחות:` | Consistency (alt-text). |
| index.html | `<title id="boxTitle">שתי חבילות מול פתח דלת סטנדרטי</title>` | `<title id="boxTitle">שתי אריזות מול פתח דלת סטנדרטי</title>` | Consistency. |
| index.html | `<dt>חבילה א׳</dt>` | `<dt>אריזה א׳</dt>` | Consistency. |
| index.html | `<dt>חבילה ב׳</dt>` | `<dt>אריזה ב׳</dt>` | Consistency. |
| index.html | `החבילות הן <span class="num" dir="ltr">170×100×12</span>` | `האריזות הן <span class="num" dir="ltr">170×100×12</span>` | Consistency. |
| index.html | `החבילה הארוכה עוברת בדלת סטנדרטית` | `האריזה הארוכה עוברת בדלת סטנדרטית` | Consistency. |
| index.html | `אבל במעלית קטנה היא תיסע בעמידה או במדרגות.` | `אבל במעלית קטנה נצטרך להעמיד אותה, ואם גם זה לא עובד — לעלות במדרגות.` | A package does not "travel standing". The `או במדרגות` is also a false parallel — standing is a position, stairs are a route. |
| index.html | `ההארכה שמורה בתוך השולחן ונפתחת ביד אחת.` | `לוח ההארכה נמצא בתוך השולחן ונפתח ביד אחת.` | `ההארכה שמורה` reads as "the extension is reserved/kept safe". `שמור` is for secrets and seats, not for parts. |
| index.html | `לוח ההארכה ברוחב <span class="num">60</span> ס״מ שמור בתוך השולחן עצמו.` | `לוח ההארכה ברוחב <span class="num">60</span> ס״מ מאוחסן בתוך השולחן עצמו.` | Same. |
| index.html | `משטח מלא ברוחב <span class="num">90</span> ס״מ עובד עם הלחות ועם הזמן זז.` | `משטח אלון מלא ברוחב <span class="num">90</span> ס״מ עובד עם הלחות — מתרחב, מתכווץ, ועם הזמן מתעקם.` | `העץ עובד` alone is the correct Israeli carpentry idiom; `עובד עם הלחות` is half-translated, and `זז` is too vague for the objection you are answering. |
| index.html | `מורכב הוא שוקל כ־<span class="num">55</span> ק״ג. להזיז אותו במקום זה עבודה לשניים.` | `כשהוא מורכב הוא שוקל כ־<span class="num">55</span> ק״ג. להזיז אותו בתוך החדר — עבודה לשניים.` | Fronted participle without `כש` is stiff. `להזיז אותו במקום` literally means "move it in place" — contradiction; you mean *around the room*. |
| index.html | `הכלל שאנחנו עובדים לפיו:` | `כלל האצבע שלנו:` | Correct but bookish. `כלל אצבע` is what an Israeli says. |
| index.html | `שריטה מתוקנת במקום, בלי להחליף את המשטח.` | `שריטה מתקנים נקודתית, בלי להחליף את המשטח.` | `במקום` is ambiguous — "on the spot" or "instead"? `נקודתית` is the word the page itself already uses correctly twice elsewhere. |
| index.html | `המרכיב שלנו מגיע, מרכיב ולוקח את האריזות.` | `המרכיב שלנו מגיע, מרכיב את השולחן ולוקח איתו את האריזות.` | `מרכיב ... מרכיב` in four words. (`מרכיב` as a noun is fine — IKEA Israel uses `מרכיב מקצועי`.) |
| index.html | `משאירים טלפון, אנחנו מתקשרים, עוברים על המידות ועל הגוון.` | `אתם משאירים טלפון, אנחנו מתקשרים ועוברים איתכם על המידות ועל הגוון.` | The subject flips mid-sentence: `משאירים` = you, `מתקשרים` = we, `עוברים` = ? Naming both subjects fixes it. |
| index.html | `הבחירה שלכם באתר נשמרת עם הפנייה:` | `הבחירה שלכם באתר נשלחת יחד עם הפנייה:` | `נשמרת עם` is not Hebrew collocation; and the true action is *sent*, not stored. |
| index.html | `<dd>חיתוך, הרכבת מסגרות, קנט</dd>` | `<dd>חיתוך, הרכבת מסגרות, הדבקת קנט</dd>` | `קנט` is a noun; in a list of production *steps* it needs its verb. |
| index.html | `<dd>שמן־שעווה, שכבות ידניות</dd>` | `<dd>שמן־שעווה, במריחה ידנית בשכבות</dd>` | `שכבות ידניות` describes the layers as manual rather than the application. |
| index.html | `ולא כפול.` | `ולא כפול מזה.` | `כפול` needs its comparand in Hebrew. |
| index.html | `ההחזרה תיסגר בכתב לפני התשלום הראשון.` | `תנאי ההחזרה יסוכמו בכתב לפני התשלום הראשון.` | You don't "close a return"; you agree its terms. |
| index.html | `<summary>יש החזרה?</summary>` | `<summary>אפשר לבטל או להחזיר?</summary>` | `יש החזרה?` is not how an Israeli consumer asks. The mental category is `ביטול עסקה`. |
| index.html | `<h1>שולחן אלון שגדל מ־` | `<h1>שולחן אלון שמתארך מ־` | Tables do not `גדלים` in Hebrew — children and companies do. `מתארך` / `נפתח` are the domain verbs (your own `<title>` already uses `נפתח` correctly). |
| index.html | `content="אלומה גורן — שולחן אלון שגדל מ־160 ל־220"` | `content="אלומה גורן — שולחן אלון שמתארך מ־160 ל־220"` | Same, in og:title. |
| terms.html | `האתר מציג מוצר הנמצא בשלבי פיתוח וטרם יוצר לצריכה מסחרית.` | `האתר מציג מוצר הנמצא בשלבי פיתוח, וטרם החל ייצורו המסחרי.` | `יוצר לצריכה מסחרית` is a stiff back-translation. Legal meaning identical. |
| terms.html | `<h2>2. מה האתר הזה כן — ומה הוא אינו</h2>` | `<h2>2. מה האתר הזה כן — ומה הוא לא</h2>` | The colloquial `כן` and the literary `אינו` cannot share a heading. |
| accessibility.html | `סימון ברור וגלוי של מוקד ההתמקדות;` | `סימון ברור וגלוי של הפוקוס;` | `מוקד ההתמקדות` is tautological (focus-of-focusing). Israeli accessibility statements say `הפוקוס`. |
| privacy.html | `בנוסף נאסף מידע טכני על הגלישה:` | `נוסף על כך נאסף מידע טכני על הגלישה:` | `בנוסף` as a sentence opener is the single most-corrected Hebrew style error; `נוסף על כך` is the accepted form. Low stakes, but this is a legal page. |
| thanks.html | `<dd>תוך יום עסקים</dd>` | `<dd>בתוך יום עסקים</dd>` | Time spans take `בתוך`; `תוך` is the colloquial clipping. |

### C. Typography and punctuation

| file | current text | corrected text | why |
|---|---|---|---|
| index.html | `ב-SMS ובוואטסאפ` | `ב־SMS ובוואטסאפ` | Hyphen-minus instead of maqaf (U+05BE). The rest of the site uses the maqaf correctly — this is the one leak. |
| index.html | `ו-125 על 40 על 22 סנטימטר` | `ו־125 על 40 על 22 סנטימטר` | Same, inside the drawing's alt-text. |
| privacy.html | `(להלן: „אנחנו״ או „החברה״)` | `(להלן: „אנחנו” או „החברה”)` | **Gershayim (״, U+05F4) is not a closing quote.** The Academy reserves it for abbreviations (`מע״מ`, `ת״י`) and places it before the last letter. Opening low `„` correctly paired with closing high `”`. Occurs in every legal page. |
| terms.html | `(להלן: „האתר״)` | `(להלן: „האתר”)` | Same. |
| terms.html | `(להלן: „החברה״)` | `(להלן: „החברה”)` | Same. |
| terms.html | `כמות שהם („AS IS״)` | `כמות שהם (AS IS)` | A Latin string inside Hebrew low-quotes inside RTL parentheses is a bidi mess on a phone. Parentheses alone are the standard Israeli contract form. |
| accessibility.html | `קישור „דילוג לתוכן הראשי״ בתחילת כל עמוד;` | `קישור „דילוג לתוכן הראשי” בתחילת כל עמוד;` | Same gershayim-as-quote error. |
| accessibility.html | `כיבוד הגדרת „הפחתת תנועה״ של מערכת ההפעלה;` | `כיבוד הגדרת „הפחתת תנועה” של מערכת ההפעלה;` | Same. |
| index.html | `<h2>נגריית Impuls, צ׳רנוביץ, אוקראינה</h2>` | `<h2>נגריית Impuls — צ׳רנוביץ, אוקראינה</h2>` | A comma immediately after an LTR run inside an RTL heading is a classic bidi jump — on some Android browsers the comma renders on the wrong side of "Impuls". An em dash is directionally neutral here and reads better anyway. |
| index.html | `"description": "שולחן אוכל נפתח מאלון, 160–220×90×75 ס\"מ,` | `"description": "שולחן אוכל נפתח מאלון, 160–220×90×75 ס״מ,` | JSON-LD uses a straight ASCII quote for the `ס״מ` gershayim, so Google renders `ס"מ`. Everywhere else on the site it is correct. |
| index.html | `<small>כולל מע״מ ומשלוח</small>` | `<small>כולל מע״מ, משלוח והרכבה</small>` | Not typography — the sticky bar silently drops assembly, which is the most valuable thing in the price. Every other price statement includes it. |

**Verified as correct — leave alone:** all `ס״מ` / `מ״מ` / `מ״ק` / `ק״ג` / `מע״מ` / `ת״י` / `דוא״ל` / `סה״כ` gershayim; the geresh in `צ׳רנוביץ`, `א׳–ה׳`, `חבילה א׳`, `מס׳ עוסק`; the maqaf in `מ־160`, `ל־220`, `כ־55`, `ב־60`, `ה־IP`, `אי־דיוקים`, `אי־המסירה`, `חד־כיווני`, `שמן־שעווה`, `התשמ״א־1981`, `התשנ״ח־1998`, `התשע״ג־2013`; the en-dashes in `8–10`, `20–25`, `160–220`; the `·` spacing throughout.

---

## Would rewrite more aggressively (needs permission)

### Headline
Current: `שולחן אלון שגדל מ־160 ל־220` / `שישה מקומות ביום רגיל, עשרה כשכולם מגיעים. ההארכה שמורה בתוך השולחן ונפתחת ביד אחת.`

The lede is genuinely good and I would keep its rhythm. The H1 is the weak half: `שגדל` is wrong, and the naked numbers make the reader do arithmetic before they know what the product is.

> **שולחן אלון אחד. שישה ביום רגיל, עשרה כשכולם מגיעים.**
> מ־160 ל־220 ס״מ בעשר שניות. לוח ההארכה נמצא בתוך השולחן ונפתח ביד אחת.

(Moves the human claim up, the numbers down, and kills the need for the `שגדל` verb entirely.)

### The three claim blocks
**1 — currently `אלון אמיתי, לא הדפס עץ` + a paragraph that immediately says `פורניר`.** This headline arms the objection it then has to disarm; an Israeli buyer reads `פורניר` as the *opposite* of "real oak". Lead with the thing that is unambiguously true:

> **אלון שנוגעים בו, לא הדפס**
> קנט אלון מלא בכל ההיקף ופורניר אלון על ליבת דיקט — עובי 40 מ״מ. כל מה שהיד והעין פוגשות הוא עץ. גימור שמן־שעווה מט: שריטה מתקנים נקודתית, בלי להחליף את המשטח.

**2 — currently `מ־160 ל־220 בעשר שניות`.** Nearly right. Only fix `שמור`:

> **מ־160 ל־220 בעשר שניות**
> לוח ההארכה ברוחב 60 ס״מ יושב בתוך השולחן עצמו. מושכים, מרימים, סוגרים — ביד אחת, בלי לחפש אותו במחסן.

**3 — currently `נכנס בדלת, נפתח בבית`, then contradicts itself** by giving a DIY assembly time and then saying you assemble it:

> **נכנס בדלת, נפתח בבית**
> שתי אריזות שטוחות בנפח כולל 0.31 מ״ק — עוברות בפתח דלת רגיל. אנחנו מרכיבים אצלכם ולוקחים את האריזות; מי שמעדיף לבד, מפתח האלן בקופסה ו־25 דקות מספיקות.

### FAQ answers
Three are weak enough to redo:

**`כמה אנשים באמת יושבים סביבו?`** — the honest answer contradicts the hero (see content issues below). Make the honesty explicit instead of letting the reader catch you:

> סגור — שישה בנוחות, שלושה בכל צד ארוך. פתוח — שמונה בנוחות, ועשרה כשמוסיפים כיסא בכל קצה. אנחנו סופרים עשרה כי ככה עורכים שולחן בחג, לא כי זה מרווח.

**`מה קורה כשנשרט?`**

> גימור שמן־שעווה מתקנים נקודתית: משייפים קלות את האזור ומורחים שמן מחדש. בלי בעל מקצוע ובלי להחליף משטח. זה בדיוק ההבדל בין שמן־שעווה ללכה — לכה שנשרטת מחייבת ליטוש של כל המשטח.

**`ייכנס לי במעלית ובדלת?`**

> האריזות הן 170×100×12 ס״מ ו־125×40×22 ס״מ. הארוכה עוברת בדלת רגילה של 80–90 ס״מ; במעלית קטנה מעמידים אותה, ואם גם זה לא — עולים במדרגות. אם יש ספק, כתבו לנו באיזו קומה אתם ואיזו מעלית יש בבניין, ונבדוק מראש.

---

## Hebrew is fine, but the content will confuse an Israeli reader

1. **The seat count contradicts itself.** The hero, the switcher and the plan drawing all promise `220 ס״מ · 10`. The FAQ then says open is `8 בנוחות, 10 כשמוסיפים כיסא בכל קצה`. A careful reader concludes the headline number is inflated — on a page whose entire positioning is "we don't pretend". Either say ten everywhere with the caveat attached, or say eight everywhere and treat ten as the holiday configuration.

2. **Claim block 3 argues against itself.** `הרכבה 20–25 דקות עם מפתח אלן אחד — ואנחנו מרכיבים אצלכם.` If you assemble it, why is the reader being told how long *they* would need? It reads as hedging about whether assembly is really included. Same problem repeats in the logistics section.

3. **`אלון אמיתי, לא הדפס עץ` sits directly above `פורניר אלון על דיקט`.** For an Israeli furniture buyer `פורניר` is the standard shorthand for "not solid wood". The materials section defends the choice very well (`ומה שנוגעים בו הוא אלון`) — but the claim headline creates the objection 400px earlier, where there is no defence yet.

4. **The return-policy FAQ points at a document that has no return policy.** `יש החזרה?` → `התנאים המלאים מופיעים בתנאי השימוש`. `terms.html` contains no cancellation or return clause at all — §2 says the site isn't a shop, and that's it. This is not a language problem; it's a promise the linked page does not keep, and for a consumer-facing Israeli site it is the kind of gap a regulator notices. Either add a `ביטול עסקה` clause to terms.html or stop linking there.

5. **`מחיר השקה` vs `אין באתר מחיר מבוטל, מבצע או הנחה`.** The landing page frames ₪5,990 as a launch price (implying it will rise); terms §5 explicitly disclaims any promotional pricing and calls the number `מחיר השקה משוער ... עשוי להשתנות`. To a reader who opens both, the homepage promises a deal and the terms deny one.

6. **55 ק״ג is used twice for two different things.** Shipping weight (`שתי אריזות ... יחד כ־55 ק״ג`) and assembled weight (`מורכב הוא שוקל כ־55 ק״ג`). Packaging is not weightless — one of these is wrong, and a reader who notices reads the whole spec sheet as approximate.

7. **`אישור ההזמנה` starts the 8–10 week clock but is never defined**, and terms.html insists nothing on the site creates an order. The reader cannot tell what event begins the wait — the phone call? A signed quote? A deposit? The FAQ on payment hints at `מקדמה בהזמנה` but never joins the two.

8. **The room-fit rule is ambiguous.** `90 ס״מ פנויים מכל צד כדי למשוך כיסא ולעבור מאחוריו` — the input asks only for wall length, so "each side" must mean the two ends along the wall; but the stated reason (pulling a chair out and walking behind it) is about clearance *in front of* the table, which the tool never asks about. The reader gets a verdict from a rule that doesn't match the question.

9. **`שאלות שנשאלנו`** on a product that, by the page's own repeated admission, has no customers, no stock and no showroom. Minor, but it is the one place the page's honesty slips, and it sits right above the most honest section on the site. `שאלות שאנחנו נשאלים` or simply `שאלות ותשובות` costs nothing.

10. **`נגריית Impuls`** — the workshop is named only in Latin, and the page asks Israeli buyers to trust a Ukrainian family workshop they cannot look up in Hebrew. Not a language error, but adding a Hebrew transliteration (`נגריית אימפולס`) on first mention would make the sentence searchable and the claim checkable.
