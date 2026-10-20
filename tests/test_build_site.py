"""Зібрана вітрина: сторінки, товари з каталогу, чесні позначки, SEO.

Одна збірка в тимчасовій копії дерева (як test_build_eol), dist/ проєкту не чіпаємо. Перевіряємо те,
що бачить гість і пошуковик: кожна сторінка обох мов, картка кожного товару, позначка «משוער» біля
попередніх цін, жодного «להשלמה», «קנה», «עץ אלון מלא», рейтингів чи відгуків у schema.org.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import tempfile
import unittest

from tests.test_build_eol import make_tree, run_build

PROJECT = pathlib.Path(__file__).resolve().parent.parent
CATALOG = json.loads((PROJECT / "catalog" / "products.json").read_text(encoding="utf-8"))
PRODUCTS = [p for p in (CATALOG["products"] if isinstance(CATALOG, dict) else CATALOG) if not p.get("hidden")]
PAGES = ("", "catalog/", "how/", "about/", "faq/", "privacy", "terms", "accessibility")


class BuiltSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-build-site-"))
        tree = cls.tmp / "t"
        tree.mkdir()
        make_tree(tree, crlf_sources=False)
        cls.dist = run_build(tree, as_windows=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def page(self, rel: str) -> str:
        p = self.dist / rel
        if rel == "" or rel.endswith("/"):
            p = p / "index.html"
        return p.read_text(encoding="utf-8")

    def all_html(self):
        return [(f.relative_to(self.dist).as_posix(), f.read_text(encoding="utf-8"))
                for f in sorted(self.dist.rglob("*.html"))]

    def test_every_page_exists_in_both_languages(self):
        for prefix, lang, direction in (("", "he", "rtl"), ("en/", "en", "ltr")):
            for rel in PAGES:
                html = self.page(prefix + rel)
                self.assertIn(f'<html lang="{lang}" dir="{direction}">', html, prefix + rel)
                self.assertEqual(len(re.findall(r"<h1[\s>]", html)), 1, f"{prefix + rel}: рівно один h1")
        self.assertIn('lang="he"', (self.dist / "404.html").read_text(encoding="utf-8"))

    def test_gallery_skips_mechanism_and_light(self):
        # mechanism і light — окремі блоки вітрини (catalog/README.md); у галереї й мініатюрах лише решта кадрів
        for p in PRODUCTS:
            html = self.page(f"p/{p['slug']}/")
            track = html[html.index('<ul class="g-track"'):html.index('<div class="viewer3d"')] if p.get("images") else ""
            shown = [i for i in p.get("images") or [] if i["view"] not in ("mechanism", "light")]
            with self.subTest(product=p["id"]):
                self.assertEqual(track.count('class="g-slide"'), len(shown))
                for i in p.get("images") or []:
                    stem = i["src"].rsplit("/", 1)[1].rsplit("-", 1)[0]
                    if i["view"] in ("mechanism", "light"):
                        self.assertNotIn(f"/{p['id']}/{stem}-", track)

    def test_every_catalog_product_has_a_card_in_both_languages(self):
        self.assertTrue(PRODUCTS)
        for p in PRODUCTS:
            for prefix in ("", "en/"):
                html = self.page(f"{prefix}p/{p['slug']}/")
                self.assertIn(f'data-product="{p["id"]}"', html)
                for s in p["sizes"]:
                    self.assertIn(f'{int(s["price_ils"]):,}', html, f"{p['slug']}: ціна розміру {s['label']}")
                ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
                self.assertEqual(ld["@type"], "Product")
                self.assertEqual(ld["offers"]["priceCurrency"], "ILS")
                self.assertEqual(ld["offers"]["lowPrice"], min(int(s["price_ils"]) for s in p["sizes"]))
                for banned in ("aggregateRating", "review", "Review"):
                    self.assertNotIn(banned, json.dumps(ld), f"{p['slug']}: вигаданий рейтинг у schema.org")

    def test_preliminary_prices_carry_the_estimate_mark(self):
        for p in PRODUCTS:
            if not p.get("preliminary"):
                continue
            self.assertIn("מחיר משוער, טרם אושר", self.page(f"p/{p['slug']}/"), p["slug"])
            self.assertIn("not yet confirmed", self.page(f"en/p/{p['slug']}/").lower(), p["slug"])

    def test_no_placeholders_buy_buttons_or_solid_oak_claims(self):
        for rel, html in self.all_html():
            text = re.sub(r"<[^>]+>", " ", html)
            self.assertNotIn("להשלמה", text, rel)
            self.assertNotIn("{{", html, rel)
            # масив дозволено лише про кромки, фасади, ніжки, раму; виріб цілком — шпон
            for m in re.finditer("עץ אלון מלא", text):
                self.assertRegex(text[max(0, m.start() - 30):m.start()], "קנט|חזית|רגל|מסגר", f"{rel}: «עץ אלון מלא» про виріб цілком")
            self.assertIsNone(re.search(r">\s*(קנה|קנו|Buy now|Add to cart)\s*<", html), f"{rel}: кнопка купівлі")

    def test_no_launch_discount_promise(self):
        # знижки для перших нема — ціни лише «משוער · טרם אושר»
        for rel, html in self.all_html():
            text = re.sub(r"<[^>]+>", " ", html)
            for phrase in ("מחיר השקה", "מחיר ההשקה", "launch price"):
                self.assertFalse(phrase in text, f"{rel}: «{phrase}»")
            # «справжній дуб» заголовком двозначний — у нас шпон; у FAQ пояснення шару шпону лишається
            self.assertIsNone(re.search(r">\s*(אלון אמיתי|Real oak)\s*<", html), f"{rel}: «אלון אמיתי» заголовком")

    def test_internal_links_resolve(self):
        for rel, html in self.all_html():
            for href in re.findall(r'href="(/[^"#?]*)', html):
                if href.startswith("/assets/") or href.startswith("/api/") or href.startswith("/admin"):
                    continue
                p = self.dist / href.lstrip("/")
                ok = p.is_file() or (p / "index.html").is_file() or p.with_suffix(".html").is_file()
                self.assertTrue(ok, f"{rel}: бите посилання {href}")

    def test_seo_head_canonical_hreflang_og(self):
        site = json.loads((PROJECT / "content.json").read_text(encoding="utf-8"))["SITE_URL"]
        for rel in ("", "en/", f"p/{PRODUCTS[0]['slug']}/"):
            html = self.page(rel)
            self.assertIn(f'<link rel="canonical" href="{site}/{rel}', html, rel)
            self.assertIn('hreflang="he"', html)
            self.assertIn('hreflang="en"', html)
            self.assertIn('property="og:image"', html)
            self.assertRegex(html, r'<meta name="description" content="[^"]{20,}">')

    def test_share_preview_is_own_language_and_product(self):
        # WhatsApp/Facebook: головна he/en — власне превью мовою сторінки, товар — свій герой, не старе og.png
        for rel, name in (("", "home-he"), ("en/", "home-en"), (f"p/{PRODUCTS[0]['slug']}/", PRODUCTS[0]["slug"])):
            self.assertRegex(self.page(rel), rf'property="og:image" content="[^"]*/assets/og/{name}\.[0-9a-f]+\.jpg"', rel)

    def test_sitemap_lists_products_and_robots_points_to_it(self):
        sm = (self.dist / "sitemap.xml").read_text(encoding="utf-8")
        for p in PRODUCTS:
            self.assertIn(f"/p/{p['slug']}/", sm)
            self.assertIn(f"/en/p/{p['slug']}/", sm)
        robots = (self.dist / "robots.txt").read_text(encoding="utf-8")
        self.assertRegex(robots, r"Sitemap: https://[^\s{]+/sitemap\.xml")

    def test_lead_form_has_unchecked_marketing_consent(self):
        html = self.page("")
        box = re.search(r'<input[^>]*name="consent_marketing"[^>]*>', html)
        self.assertIsNotNone(box, "окрема галочка згоди на рекламу (חוק התקשורת 30א)")
        self.assertNotIn("checked", box.group(0))
        self.assertIn('name="website"', html, "приманка для ботів")

    def test_accessibility_menu_and_cookie_choice_on_every_page(self):
        for rel, html in self.all_html():
            if not rel.endswith("index.html") and rel not in ("privacy.html", "en/privacy.html"):
                continue
            self.assertIn('class="skip"', html, rel)
            self.assertIn("data-a11y-opt=", html, rel)
            self.assertIn("data-notice-no", html, rel)

    def test_legal_pages_hide_blocks_until_the_config_fills_them(self):
        if not (PROJECT / "i18n" / "legal.he.json").is_file():
            self.skipTest("legal.*.json ще немає (сесія 3)")
        for prefix in ("", "en/"):
            for rel in ("privacy", "terms", "accessibility"):
                html = self.page(prefix + rel + ".html")
                text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
                self.assertIsNone(re.search(r"\{[a-z0-9_]+\}", re.sub(r"<[^>]+>", " ", text)), f"{prefix}{rel}: сирий плейсхолдер")
                self.assertIn('class="legal-sec"', html, f"{prefix}{rel}: текст із legal.*.json")
                for tag in re.findall(r"<(?:p|li)[^>]*data-lneed=[^>]*>", html):
                    self.assertIn(" hidden", tag, f"{prefix}{rel}: блок без даних видно")
        self.assertIn('data-lneed="a11y_email a11y_name a11y_phone"', self.page("accessibility.html"))


if __name__ == "__main__":
    unittest.main()
