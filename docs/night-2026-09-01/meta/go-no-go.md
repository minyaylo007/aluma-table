# Go / no-go — decide before you spend, not after

Write the date and your answer at the bottom of this file when the test ends. The point of
fixing the rule now is that in ten days you will have twenty phone conversations, some of them
warm, and warm conversations are the most expensive thing in a founder's judgement.

**Budget:** ₪1,000 · **Duration:** 10 days · **Measured on:** leads and what they say.

---

## The rule

| Outcome | Condition | Decision |
|---|---|---|
| **STOP** | fewer than **6 leads**, **or** not one lead asked unprompted about delivery, payment or timing | Close it. Do not build a prototype. |
| **GO** | **10 or more leads** **and** at least **3** asked to pay a deposit, get an invoice, or otherwise tried to give you money | Build the prototype and commit to a first batch. |
| **ONE MORE** | anything between | Spend ₪500 more on one changed variable. Then this table again, no third round. |

The second half of the STOP condition is the real test. Six people who filled a form because
the picture was nice is not demand. One person who asks "מתי אפשר לקבל את זה ואיך משלמים?"
is worth more than ten who ask "יש בצבע אחר?".

## Why these numbers

₪1,000 at an estimated ₪30–70 per instant-form lead buys 10–30 leads. So:

- **Under 6** means the CPL came in above ~₪165 — two to five times the plausible range. At that
  cost the funnel cannot work at any budget. The product, the price or the market is wrong, and
  another ₪1,000 will only tell you so more expensively.
- **10+ with 3 wanting to pay** is a 30% hot rate on a cold audience for a ₪5,990 considered
  purchase with an 8–10 week lead time and no showroom. That is a genuinely good signal.
- The middle band is the honest majority outcome, which is why it has its own instruction
  rather than a shrug.

## If it lands in the middle: change exactly one thing

Pick the one the data points at. Not two.

| What the data shows | Change |
|---|---|
| CTR under 1% | Creative. The ad is not being seen as relevant. |
| CTR fine, few form opens | The offer in the ad. Probably the price is doing the filtering. |
| Form opens, few submits | The form. Drop the qualifying question. |
| Leads arrive, all cold, nobody asks about paying | The price, or the 8–10 week lead time. These are the two things a buyer is actually weighing. |
| Everyone asks "יש מידה אחרת?" | The product. One size may be the wrong bet. |

Then ₪500, same audience, same dates-of-week, one variable different. Read this table again.
There is no third round: if two runs cannot produce three people trying to pay you, the answer
is no and the ₪1,500 bought you that answer cheaply.

## What does not count as a signal

- Likes, comments, shares, saves, follows. None of them is a table.
- "וואו יפה" in the comments. Compliments are free.
- Your own friends and family filling the form. Exclude yourself with `?me=1` and do not send
  the link to anyone you know until after the test.
- A lead who will not answer the phone. Two attempts on different days, then it is not a lead.

## What to record for every lead, in `/admin`

The dashboard has a status field per lead. Use it honestly the same day you call:

`new` → `called` → then one of `interested` / `not_interested` / `deposit`

`deposit` means they said yes to paying, whether or not you took the money. That count is the
numerator of the GO condition. If you cannot bring yourself to move a lead out of `interested`
after two conversations, it is `not_interested`.

## What to read from the site, not from Meta

The admin dashboard answers questions Meta cannot:

- **Reached the price** vs **visited**. A big drop here means the price is doing the filtering
  before anyone engages — that is useful and it is not the ad's fault.
- **Touched a switcher.** Colour or size interaction is the strongest engagement signal on
  the page. Someone who configures and then leaves is a price objection, not a disinterest.
- **Room-fit results.** If most answers come back `tight` or `no`, the table is too big for
  the Israeli apartments in your audience — which would be the single most valuable finding of
  the whole test, and it would change the product, not the ad.
- **Which colour wins.** Decides what the first batch is made in.
- **Which FAQ gets opened most.** That is the objection to answer higher up the page.

## Before you commit to a first batch, even on a GO

A GO means "the demand signal is real". It does not answer:

- the legal entity, VAT and importer-of-record position (`legal-il.md` §5.3);
- who honours the 5-year warranty in Israel, and how;
- the real landed cost per table from Chernivtsi, including shipping, customs and the
  nationwide delivery-and-assembly you promised;
- whether ₪5,990 still leaves a margin after all of the above.

Take no deposits until those are settled. A deposit taken against an unsettled warranty chain
is a liability, not a validation.

---

## Result

```
Dates run:              ______________
Spend (incl. VAT?):     ______________
Leads:                  ______________
Asked about delivery / payment / timing:   ______________
Status = deposit:       ______________
CPL:                    ______________
CTR:                    ______________

Decision (STOP / GO / ONE MORE):   ______________
Reason, in one sentence:
```
