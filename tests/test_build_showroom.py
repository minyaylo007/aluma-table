"""№30: район показу і самовивозу — лише з факту власника OWNER_FACTS.SHOWROOM_AREA_<МОВА>.

Порожній факт — у dist/ нема ні району, ні маркера, ні плитки «לראות מקרוב», ні питання FAQ.
Заповнений — плитка на картці (data-visit → #register), «איסוף עצמי (район)» на картці й у /checkout/,
питання в FAQ, фраза в кроці «משלוח או איסוף» — у всіх трьох мовах. Дві збірки в тимчасових копіях дерева.
"""

from __future__ import annotations

import html
import json
import pathlib
import shutil
import tempfile
import unittest

from tests.locales import DIST_PREFIX
from tests.test_build_eol import make_tree, run_build

PROJECT = pathlib.Path(__file__).resolve().parent.parent
I18N = {loc: json.loads((PROJECT / "i18n" / f"{loc}.json").read_text(encoding="utf-8")) for loc in DIST_PREFIX}
# вигадані райони, яких нема ніде в текстах сайту: знайшли рядок — значить, він із факту
AREA = {"he": "שכונת־בדיקה", "en": "Testarea <&>", "ru": "Тестрайон"}   # en — ще й перевірка екранування
PAGES = ("p/tavor/", "checkout/", "cart/", "faq/", "how/", "")


def build(tmp: pathlib.Path, areas: dict | None) -> pathlib.Path:
    """areas=None — усі три факти порожні (незалежно від того, що зараз у content.json)."""
    tree = tmp / ("filled" if areas else "empty")
    tree.mkdir()
    make_tree(tree, crlf_sources=False)
    c = json.loads((tree / "content.json").read_text(encoding="utf-8"))
    for loc in DIST_PREFIX:
        c["OWNER_FACTS"][f"SHOWROOM_AREA_{loc.upper()}"] = (areas or {}).get(loc, "")
    (tree / "content.json").write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return run_build(tree, as_windows=False)


def page(dist: pathlib.Path, rel: str) -> str:
    return (dist / rel / "index.html").read_text(encoding="utf-8")


class ShowroomAreaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-showroom-"))
        cls.empty = build(cls.tmp, None)
        cls.filled = build(cls.tmp, AREA)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_facts_in_repo_holon(self):
        # слово власника 27.10 через диригента: показ і самовивіз — Холон (лише район: без адреси, телефону, імені)
        facts = json.loads((PROJECT / "content.json").read_text(encoding="utf-8"))["OWNER_FACTS"]
        self.assertEqual({loc: facts[f"SHOWROOM_AREA_{loc.upper()}"] for loc in DIST_PREFIX},
                         {"he": "חולון", "en": "Holon", "ru": "Холон"})

    def test_hebrew_wording_with_holon(self):
        s = I18N["he"]
        self.assertEqual(s["trust_strip_visit_h"].replace("{{SHOWROOM_AREA}}", "חולון"), "לראות מקרוב בחולון")
        self.assertEqual(s["ship_pickup_area"].replace("{{SHOWROOM_AREA}}", "חולון"), "איסוף עצמי (חולון)")
        self.assertTrue(s["faq_visit"]["a"].replace("{{SHOWROOM_AREA}}", "חולון").startswith("כן, בחולון, בתיאום מראש."))

    def test_empty_fact_renders_nothing(self):
        for loc, pre in DIST_PREFIX.items():
            s = I18N[loc]
            for rel in PAGES:
                html = page(self.empty, pre + rel)
                with self.subTest(loc=loc, page=rel):
                    self.assertNotIn("data-visit", html)
                    self.assertNotIn("SHOWROOM", html)
                    self.assertNotIn(s["faq_visit"]["q"], html)

    def test_filled_fact_on_card_checkout_faq_how(self):
        for loc, pre in DIST_PREFIX.items():
            s, area = I18N[loc], html.escape(AREA[loc], quote=False)
            pickup = s["ship_pickup_area"].replace("{{SHOWROOM_AREA}}", area)
            with self.subTest(loc=loc):
                card = page(self.filled, pre + "p/tavor/")
                self.assertIn('href="#register" data-visit data-cta="trust"', card)
                self.assertIn(s["trust_strip_visit_h"].replace("{{SHOWROOM_AREA}}", area), card)
                self.assertIn(pickup, card)
                self.assertIn(pickup, page(self.filled, pre + "checkout/"))
                faq = page(self.filled, pre + "faq/")
                self.assertIn(s["faq_visit"]["q"], faq)
                self.assertIn(s["faq_visit"]["a"].replace("{{SHOWROOM_AREA}}", area), faq)
                self.assertIn(s["s5_visit"].replace("{{SHOWROOM_AREA}}", area), page(self.filled, pre + "how/"))
                self.assertNotIn("{{", card + faq)

    def test_fact_is_escaped(self):
        card = page(self.filled, DIST_PREFIX["en"] + "p/tavor/")
        self.assertIn("Testarea &lt;&amp;&gt;", card)
        self.assertNotIn("Testarea <", card)

    def test_self_delivery_phrase_always_on_how(self):
        for loc, pre in DIST_PREFIX.items():
            phrase = {"he": "מרכיבים ומוסרים בעצמנו", "en": "We assemble and deliver ourselves",
                      "ru": "Собираем и передаём сами"}[loc]
            self.assertIn(phrase, page(self.empty, pre + "how/"))


if __name__ == "__main__":
    unittest.main()
