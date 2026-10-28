"""№39 (28.10): картка вдвічі коротша — глави під спойлером, відеодзвінок на першому екрані, липка смуга після нього.

Без збірки: шаблон site/pages/product.html, build.py (acc(), steps_acc()), aluma.js, i18n. Висота й клік — tests/redesign.spec.js.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build  # noqa: E402

TEMPLATE = (ROOT / "site" / "pages" / "product.html").read_text(encoding="utf-8")
JS = (ROOT / "site" / "assets" / "aluma.js").read_text(encoding="utf-8")
CATALOG = json.loads((ROOT / "catalog" / "products.json").read_text(encoding="utf-8"))
PRODUCTS = CATALOG["products"] if isinstance(CATALOG, dict) else CATALOG


def i18n(lang):
    return json.loads((ROOT / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))


class AccordionTests(unittest.TestCase):
    def test_spec_and_more_are_closed_details_with_visible_heading(self):
        for sid, key in (("spec", "spec_h2"), ("more", "more_h2")):
            with self.subTest(sid=sid):
                sec = re.search(rf'<section class="sec sec--acc" id="{sid}" aria-labelledby="{sid}-h">(.*?)</section>', TEMPLATE, re.S)
                self.assertIsNotNone(sec)
                self.assertIn('<details class="pdp-acc" data-acc>', sec.group(1))   # без open — закрита
                self.assertIn(f'<summary class="pdp-acc-sum"><h2 class="h2 pdp-acc-h" id="{sid}-h">{{{{t.{key}}}}}</h2></summary>',
                              sec.group(1))

    def test_generated_chapters_are_closed_details(self):
        p = next(x for x in PRODUCTS if x["slug"] == "tavor")
        for sid, html in (("unfold", build.how(p, "he")), ("light", build.light(p, "he")), ("how", build.steps_acc())):
            with self.subTest(sid=sid):
                self.assertTrue(html.startswith('<section class="sec sec--acc'), html[:80])
                self.assertIn(f'id="{sid}" aria-labelledby="{sid}-h"', html)
                self.assertIn('<details class="pdp-acc" data-acc><summary', html)
                self.assertNotIn("<details open", html)
        steps = build.steps_acc()
        for i in range(1, 6):
            self.assertIn(f"{{{{t.s{i}_h}}}}", steps)

    def test_first_screen_and_size_choice_stay_outside_accordions(self):
        buy = TEMPLATE[:TEMPLATE.index("</article>")]
        self.assertNotIn("<details", buy)
        for tok in ("{{P_CONFIG}}", "{{P_SIZES}}", "{{P_INC}}", "{{P_TRUST}}", "{{P_FACTS}}", "{{P_TERMS}}"):
            self.assertIn(tok, buy)

    def test_chapter_link_opens_its_accordion(self):
        self.assertIn('qs("details[data-acc]", sec)', JS)
        self.assertIn('W.addEventListener("hashchange"', JS)


class VideoCallTests(unittest.TestCase):
    def test_button_right_under_the_pair_opens_callback(self):
        m = re.search(r'</div>\n      <button class="pdp-video" type="button" data-video data-cta="pdp" aria-expanded="false" '
                      r'aria-controls="callback"><svg[^>]*aria-hidden="true"[^>]*>.*?</svg><span>\{\{t\.video_cta\}\}</span></button>\n'
                      r'      <p class="pdp-ask-hint', TEMPLATE, re.S)
        self.assertIsNotNone(m, "кнопка відео — одразу під парою «הוספה לסל» + «שאלה?»")

    def test_text_three_languages_no_number_no_whatsapp_no_render_word(self):
        for lang in ("he", "en", "ru"):
            v = i18n(lang)["video_cta"]
            with self.subTest(lang=lang):
                self.assertTrue(0 < len(v) <= 32, v)
                self.assertNotRegex(v.lower(), r"\d|whats|ווטס|וואטס|ватс|הדמיה")

    def test_click_preselects_video_and_tracks_cta_video_without_pixel(self):
        self.assertIn('track("cta_video", { content_ids: [cur.id], cta: videoBtn.getAttribute("data-cta") || "" }, { pixel: false })', JS)
        self.assertIn("cbOpen(videoBtn, false, true)", JS)
        self.assertIn('qs(\'input[name="contact_pref"][value="video"]\', cbForm)', JS)
        # заявка — та сама міні-форма: lead_source=callback, contact_pref з чипа (video)
        self.assertIn('data.lead_source = "callback";', JS)


class StickyTests(unittest.TestCase):
    def test_sticky_waits_for_first_screen_and_hides_over_open_callback(self):
        self.assertIn('var anchor = qs(".hero .actions") || qs(".pdp-actions")', JS)
        self.assertIn("anchor.getBoundingClientRect().bottom < 0", JS)
        self.assertIn("!(cb && !cb.hidden && visible(cb))", JS)


if __name__ == "__main__":
    unittest.main()
