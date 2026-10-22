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

from tests.locales import DIRS, DIST_PREFIX, LOCALES
from tests.test_build_eol import make_tree, run_build

PROJECT = pathlib.Path(__file__).resolve().parent.parent
CATALOG = json.loads((PROJECT / "catalog" / "products.json").read_text(encoding="utf-8"))
PRODUCTS = [p for p in (CATALOG["products"] if isinstance(CATALOG, dict) else CATALOG) if not p.get("hidden")]
PAGES = ("", "catalog/", "how/", "about/", "faq/", "privacy", "terms", "accessibility", "cart/", "checkout/")


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

    def test_every_page_exists_in_every_language(self):
        for lang, prefix in DIST_PREFIX.items():
            direction = DIRS[lang]
            for rel in PAGES:
                html = self.page(prefix + rel)
                self.assertIn(f'<html lang="{lang}" dir="{direction}">', html, prefix + rel)
                self.assertEqual(len(re.findall(r"<h1[\s>]", html)), 1, f"{prefix + rel}: рівно один h1")
        self.assertIn('lang="he"', (self.dist / "404.html").read_text(encoding="utf-8"))

    def test_3d_button_points_at_published_files(self):
        # 21.10: data-model був відносним (з /en/p/tavor/ — у 404), файл не публікувався, і кнопка мовчала.
        # Тепер: шлях абсолютний, файл у dist/, і все, на що посилається модуль (three.js, текстури), теж там
        ref = re.compile(r"/assets/[\w\-./]+?\.(?:js|jpg|png|webp|hdr)")
        for p in PRODUCTS:
            for prefix in DIST_PREFIX.values():
                html = self.page(f"{prefix}p/{p['slug']}/")
                models = re.findall(r'data-model="([^"]*)"', html)
                with self.subTest(page=f"{prefix}p/{p['slug']}/"):
                    self.assertEqual(len(models), 1 if p.get("model3d") else 0)
                    for m in models:
                        self.assertTrue(m.startswith("/assets/"), m)
                        js = self.dist / m.lstrip("/")
                        self.assertTrue(js.is_file(), m)
                        deps = ref.findall(js.read_text(encoding="utf-8"))
                        self.assertTrue(any("/vendor/three." in d for d in deps), "модуль не посилається на свій three.js")
                        for d in deps:
                            self.assertTrue((self.dist / d.lstrip("/")).is_file(), f"{m} → {d}")
                    if models:
                        vid = re.search(r'class="g-3d js-3d"[^>]*aria-controls="([^"]+)"', html).group(1)
                        self.assertIn(f'<div class="viewer3d" id="{vid}" hidden>', html)
                        self.assertEqual('data-state="open"' in html, any(sz.get("extended_cm") for sz in p["sizes"]))

    def test_estimate_word_next_to_the_price(self):
        # аудит 22.10 (г) 1: реклама обіцяє «מחיר משוער» — слово стоїть у рядку під ціною, до плиток розмірів
        word = {"": "מחיר משוער", "en/": "estimate", "ru/": "ориентировочно"}
        for p in PRODUCTS:
            for prefix, w in word.items():
                html = self.page(f"{prefix}p/{p['slug']}/")
                with self.subTest(page=f"{prefix}p/{p['slug']}/"):
                    incl = re.search(r'<span class="price-incl">([^<]*)</span>', html)
                    self.assertIsNotNone(incl)
                    self.assertIn(w, incl.group(1))
                    self.assertLess(incl.start(), html.index('name="size"'), "рядок під ціною — над плитками")

    def test_price_includes_and_size_help_from_catalog(self):
        # 22.10: «מה כלול במחיר» на кожній картці; місця — з seats каталогу; «איך לבחור מידה» — лише на столах,
        # відстань — з content.json (CLEARANCE_CM), місце на людину — SEAT_CM плану
        content = json.loads((PROJECT / "content.json").read_text(encoding="utf-8"))
        for p in PRODUCTS:
            for prefix in ("", "en/"):
                html = self.page(f"{prefix}p/{p['slug']}/")
                with self.subTest(page=f"{prefix}p/{p['slug']}/"):
                    inc = re.search(r'<section class="pdp-inc".*?</section>', html, re.S)
                    self.assertIsNotNone(inc)
                    dining = p["category"] == "dining_table"
                    self.assertEqual(inc.group(0).count("<li>"), 5 + bool(p.get("seats")) + dining)
                    if p.get("seats"):
                        lo, hi = p["seats"]["closed"][0], p["seats"]["extended"][-1]
                        self.assertIn(f'<bdi dir="ltr">{lo}', inc.group(0))
                        self.assertIn(f'{hi}</bdi>', inc.group(0))
                    size = re.search(r'<section class="pdp-size".*?</section>', html, re.S)
                    self.assertEqual(size is not None, p["category"] in ("dining_table", "coffee_table"))
                    if size:
                        self.assertIn(f'{content["CLEARANCE_CM"]} ', size.group(0))
                        self.assertEqual("55 " in size.group(0), p["category"] == "dining_table")
                        self.assertIn('data-wa="size"', size.group(0))
                    self.assertNotIn("{{", html)

    def test_table_only_line_first_on_dining_tables_only(self):
        # 22.10, аудит (б) №2: «ціна — за стіл, без стільців» першим рядком «מה כלול במחיר» лише в обідніх столів;
        # ознака — категорія каталогу; країна виробництва — рядком inc_own на кожній картці (аудит (б) №3)
        for lang, prefix in DIST_PREFIX.items():
            t = json.loads((PROJECT / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
            only, own = t["inc_table_only"].split(",")[0], t["inc_own"].split(" · ")[0]
            for p in PRODUCTS:
                inc = re.search(r'<section class="pdp-inc".*?</section>', self.page(f"{prefix}p/{p['slug']}/"), re.S).group(0)
                first = re.search(r"<li>.*?<span>(.*?)</span>", inc, re.S).group(1)
                with self.subTest(page=f"{prefix}p/{p['slug']}/"):
                    self.assertEqual(first.startswith(only), p["category"] == "dining_table")
                    self.assertEqual(inc.count(only), int(p["category"] == "dining_table"))
                    self.assertIn(own, inc)

    def test_card_says_price_is_estimated_like_the_ads(self):
        # аудит 22.10 (в) 1: реклама обіцяє «מחיר משוער (טרם אושר)» — картка каже те саме рядком price_est над кнопкою
        word = {"he": "משוער", "en": "Estimated", "ru": "Ориентировочная"}
        for lang, prefix in DIST_PREFIX.items():
            est = json.loads((PROJECT / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["price_est"]
            self.assertIn(word[lang], est)
            for p in PRODUCTS:
                html = self.page(f"{prefix}p/{p['slug']}/")
                buy = re.search(r'<div class="pdp-buy">.*?<div class="pdp-actions">', html, re.S).group(0)
                with self.subTest(page=f"{prefix}p/{p['slug']}/"):
                    self.assertGreaterEqual(buy.count(word[lang]), 1)
                    self.assertIn(f'<p class="pdp-est muted small">{est}</p>', buy)

    def test_round_table_tile_reads_like_the_cart(self):
        # аудит 22.10 (б) 5: розмір із підписом «Ø…» на плитці — той самий «Ø115», що в кошику й рекламі, без висоти
        for lang, prefix in DIST_PREFIX.items():
            for p in PRODUCTS:
                html = self.page(f"{prefix}p/{p['slug']}/")
                tiles = re.findall(r'<span class="pill-main"><bdi dir="ltr">([^<]*)</bdi>', html)
                for s in p.get("sizes") or []:
                    with self.subTest(page=f"{prefix}p/{p['slug']}/", size=s["label"]):
                        if s["label"].startswith("Ø"):
                            self.assertIn(s["label"], tiles)
                        else:
                            self.assertIn("×".join(str(s[k]) for k in ("length_cm", "width_cm", "height_cm") if s.get(k)), tiles)

    def test_funnel_steps_and_buttons_never_promise_payment(self):
        # 22.10, аудит (б) №1: оплати на сайті немає — у кроках і кнопках кошика/оформлення ні слова «оплата»;
        # рамка «התשלום לא מתבצע באתר» лишається (вона — пояснення, а не обіцянка)
        word = {"he": "תשלום", "ru": "оплат", "en": "pay"}
        for lang, prefix in DIST_PREFIX.items():
            for rel in ("cart/", "checkout/"):
                html = self.page(prefix + rel)
                bits = re.findall(r'<ol class="co-steps"[^>]*>.*?</ol>', html, re.S)
                bits += re.findall(r"<(?:button|a)\b[^>]*class=\"btn\b[^>]*>(.*?)</(?:button|a)>", html, re.S)
                with self.subTest(page=prefix + rel):
                    self.assertTrue(bits)
                    for b in bits:
                        self.assertNotIn(word.get(lang, "pay"), re.sub(r"<[^>]+>", "", b).lower())  # текст, не data-атрибути
            self.assertIn("data-co-keep", self.page(prefix + "checkout/"))

    def test_workshop_photo_slot_hidden_until_photos(self):
        # 22.10, аудит (а) 6: «תמונות מבית המלאכה יעלו בקרוב» не показуємо, доки WORKSHOP_PHOTOS у content.json не "1";
        # розмітка лишається (з'явиться фото — один прапор)
        content = json.loads((PROJECT / "content.json").read_text(encoding="utf-8"))
        for prefix in DIST_PREFIX.values():
            slot = re.search(r'<div class="photo-slot"[^>]*>', self.page(prefix + "about/"))
            with self.subTest(page=prefix + "about/"):
                self.assertIsNotNone(slot)
                self.assertEqual(" hidden " in slot.group(0), content.get("WORKSHOP_PHOTOS") != "1")

    def test_sticky_thumb_has_alt(self):
        # 22.10, аудит (а) 11: жодного <img> без alt на картці; мініатюра смуги — «הדמיה: <назва>»
        for lang, prefix in DIST_PREFIX.items():
            viz = json.loads((PROJECT / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["viz_tag"]
            for p in PRODUCTS:
                html = self.page(f"{prefix}p/{p['slug']}/")
                with self.subTest(page=f"{prefix}p/{p['slug']}/"):
                    self.assertEqual([i for i in re.findall(r"<img\b[^>]*>", html) if not re.search(r'\balt="[^"]+"', i)], [])
                    self.assertRegex(html, r'<img class="sticky-thumb"[^>]*alt="' + re.escape(viz) + r': [^"]+"')

    def test_each_language_embeds_only_its_own_font_faces(self):
        # he-картка качала 44 КБ латинського Frank Ruhl і 15 КБ кирилиці (аудит 22.10): обличчя мови —
        # у fonts-<мова>.css, вбудованому лише в її сторінки; he — без кирилиці, крім літер «Русский»
        # (22.10, далі) і повну латиницю Plex — 39 КБ заради «Meta Pixel», «English»: на he — лише latin-he
        common = {"FrankRuhlLibre-hebrew"} | {f"PlexSansHebrew-{w}-{s}" for w in (400, 600, 700)
                                              for s in ("hebrew", "num")}
        plex_latin = {f"PlexSansHebrew-{w}-latin" for w in (400, 600, 700)}
        cyrillic = {"PlexSans-400-cyrillic", "PlexSans-600-cyrillic", "PlexSans-700-cyrillic", "PTSerif-cyrillic"}
        own = {"he": {"FrankRuhlLibre-latin-caps", "PlexSans-400-cyrillic-lang"}
               | {f"PlexSansHebrew-{w}-latin-he" for w in (400, 600, 700)},
               "en": {"FrankRuhlLibre-latin", "PlexSans-400-cyrillic-lang"} | plex_latin,
               "ru": {"FrankRuhlLibre-latin"} | cyrillic | plex_latin}
        self.assertEqual(set(own), set(LOCALES), "нова мова — додай її обличчя сюди і site/assets/fonts-<мова>.css")
        for loc, prefix in DIST_PREFIX.items():
            for rel in ("", "catalog/", f"p/{PRODUCTS[0]['slug']}/", "cart/", "privacy", "404.html"):
                html = self.page(prefix + rel)
                faces = {re.sub(r"\.[0-9a-f]{10}$", "", m)
                         for m in re.findall(r"url\(/assets/fonts/([\w\-.]+?)\.woff2\)", html)}
                with self.subTest(page=prefix + rel):
                    self.assertEqual(faces, common | own[loc])
                    self.assertNotIn('<link rel="stylesheet"', html, "стилі вбудовані, без блокуючого запиту")
                    if loc != "ru":
                        self.assertNotRegex(html, r"PlexSans-\d00-cyrillic\.|PTSerif-cyrillic")
                    if loc == "he":
                        self.assertNotRegex(html, r"PlexSansHebrew-\d00-latin\.", "he — лише latin-he")
        slug = PRODUCTS[0]["slug"]
        self.assertNotRegex(self.page(f"p/{slug}/"), r"PlexSansHebrew-(400|600)-latin\.[0-9a-f]{10}\.woff2")
        self.assertRegex(self.page(f"en/p/{slug}/"), r"PlexSansHebrew-400-latin\.[0-9a-f]{10}\.woff2")
        self.assertRegex(self.page(f"en/p/{slug}/"), r"PlexSansHebrew-600-latin\.[0-9a-f]{10}\.woff2")

    def test_locale_font_subsets_match_their_unicode_range(self):
        # unicode-range кожного вирізаного обличчя = список, з яким його вирізано; «Русский» — з i18n
        import importlib.util
        spec = importlib.util.spec_from_file_location("subset_locale_fonts", PROJECT / "tools" / "subset_locale_fonts.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        fonts = PROJECT / "site" / "assets"
        for loc in LOCALES:
            css = (fonts / f"fonts-{loc}.css").read_text(encoding="utf-8")
            faces = dict(re.findall(r"url\(/assets/fonts/([\w\-.]+)\)[^}]*?unicode-range: ([^;]+);", css))
            for src, dst, unicodes in tool.jobs():
                if dst in faces:
                    with self.subTest(loc=loc, face=dst):
                        self.assertEqual(faces[dst], unicodes)
                        self.assertTrue((fonts / "fonts" / dst).is_file())
        ru_name = json.loads((PROJECT / "i18n" / "ru.json").read_text(encoding="utf-8"))["lang_name"]
        self.assertEqual(tool.lang_unicodes(), ", ".join(f"U+{ord(c):04X}" for c in sorted(set(ru_name))))
        self.assertNotRegex(tool.CAPS_UNICODES, r"U\+006[1-9A-F]|U\+007[0-9A]\b", "без малих a–z")

    def test_no_cdn_for_3d(self):
        # three.js — свій файл: при відкритті 3D жодного зовнішнього запиту (приватність)
        for f in (self.dist / "assets").rglob("*.js"):
            with self.subTest(file=f.name):
                self.assertNotIn("cdnjs.cloudflare.com", f.read_text(encoding="utf-8"))

    def test_gallery_skips_mechanism_and_light(self):
        # mechanism і light — окремі блоки вітрини (catalog/README.md); у галереї й мініатюрах лише решта кадрів
        for p in PRODUCTS:
            html = self.page(f"p/{p['slug']}/")
            start = html.index('<ul class="g-track"') if p.get("images") else 0
            track = html[start:html.index("</ul>", start)] if p.get("images") else ""
            shown = [i for i in p.get("images") or [] if i["view"] not in ("mechanism", "light")]
            with self.subTest(product=p["id"]):
                self.assertEqual(track.count('class="g-slide"'), len(shown))
                for i in p.get("images") or []:
                    stem = i["src"].rsplit("/", 1)[1].rsplit("-", 1)[0]
                    if i["view"] in ("mechanism", "light"):
                        self.assertNotIn(f"/{p['id']}/{stem}-", track)

    def test_every_catalog_product_has_a_card_in_every_language(self):
        self.assertTrue(PRODUCTS)
        for p in PRODUCTS:
            for loc, prefix in DIST_PREFIX.items():
                html = self.page(f"{prefix}p/{p['slug']}/")
                self.assertIn(f'data-product="{p["id"]}"', html)
                for s in p["sizes"]:
                    # «₪4,490»; у ru — «4 490 ₪» з нерозривними пробілами (build.py money)
                    want = f'₪{int(s["price_ils"]):,}' if loc != "ru" else f'{int(s["price_ils"]):,}'.replace(",", "\u00a0") + "\u00a0₪"
                    self.assertIn(want, html, f"{p['slug']}: ціна розміру {s['label']} ({loc})")
                ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
                self.assertEqual(ld["@type"], "Product")
                self.assertEqual(ld["offers"]["priceCurrency"], "ILS")
                self.assertEqual(ld["offers"]["lowPrice"], min(int(s["price_ils"]) for s in p["sizes"]))
                for banned in ("aggregateRating", "review", "Review"):
                    self.assertNotIn(banned, json.dumps(ld), f"{p['slug']}: вигаданий рейтинг у schema.org")

    def test_preliminary_prices_carry_the_estimate_mark_in_cart_and_payment(self):
        # specs/003: чесна дрібна примітка — у кошику й на екрані оплати; з аудиту 22.10 (в) 1 — і на картці
        # (не в самій .pdp-price, а рядком над кнопкою — test_card_says_price_is_estimated_like_the_ads)
        if not any(p.get("preliminary") for p in PRODUCTS):
            self.skipTest("усі ціни підтверджені")
        for rel in ("cart/", "checkout/"):
            self.assertIn("מחיר משוער, טרם אושר", self.page(rel), rel)
            self.assertIn("not yet confirmed", self.page("en/" + rel).lower(), rel)
            self.assertIn("ещё не подтверждена", self.page("ru/" + rel), rel)
        for p in PRODUCTS:
            price = re.search(r'<div class="pdp-price">.*?</div>', self.page(f"p/{p['slug']}/"), re.S).group(0)
            self.assertNotIn("טרם אושר", price, p["slug"])

    def test_no_lead_weeks_early_registration_or_free_promise(self):
        # specs/003: «10–12 שבועות» → «זמן אספקה מדויק — באישור ההזמנה»; без «הרשמה מוקדמת» і «ללא תשלום וללא התחייבות»
        for rel, html in self.all_html():
            text = re.sub(r"<script\b.*?</script>|<[^>]+>", " ", html, flags=re.S)
            self.assertIsNone(re.search(r"\d+\s*[–-]\s*\d+\s*(שבועות|weeks)", text), rel)
            for phrase in ("הרשמה מוקדמת", "ללא תשלום וללא התחייבות", "Early registration", "No payment, no commitment"):
                self.assertNotIn(phrase, text, rel)
        for p in PRODUCTS:
            self.assertIn("זמן אספקה מדויק — באישור ההזמנה", self.page(f"p/{p['slug']}/"), p["slug"])

    def test_shop_pages_have_no_card_fields_and_are_noindex(self):
        # оплати на сайті немає: жодного поля карти, жодного «מספר כרטיס» / CVV; кошик і оформлення — не для пошуку
        for rel, html in self.all_html():
            self.assertIsNone(re.search(r'autocomplete="cc-|name="(card|cc|cvv|cvc)', html, re.I), rel)
            self.assertIsNone(re.search(r"מספר כרטיס|CVV|CVC|Card number", re.sub(r"<script\b.*?</script>", " ", html, flags=re.S)), rel)
        for rel in ("cart/", "checkout/", "en/cart/", "en/checkout/"):
            self.assertIn('<meta name="robots" content="noindex">', self.page(rel), rel)
        sitemap = (self.dist / "sitemap.xml").read_text(encoding="utf-8")
        self.assertNotIn("/cart/", sitemap)
        self.assertNotIn("/checkout/", sitemap)

    def test_add_to_cart_on_every_product_card_and_sticky_bar(self):
        for p in PRODUCTS:
            for rel, label in ((f"p/{p['slug']}/", "הוספה לסל"), (f"en/p/{p['slug']}/", "Add to cart")):
                html = self.page(rel)
                self.assertEqual(len(re.findall(r'data-add-cart data-cta="(pdp|sticky)">' + label + "<", html)), 2, rel)
                self.assertNotIn("data-quick", html, rel)

    def test_no_placeholders_buy_buttons_or_solid_oak_claims(self):
        for rel, html in self.all_html():
            text = re.sub(r"<[^>]+>", " ", html)
            self.assertNotIn("להשלמה", text, rel)
            self.assertNotIn("{{", html, rel)
            # масив дозволено лише про кромки, фасади, ніжки, раму; виріб цілком — шпон
            for m in re.finditer("עץ אלון מלא", text):
                self.assertRegex(text[max(0, m.start() - 30):m.start()], "קנט|חזית|רגל|מסגר", f"{rel}: «עץ אלון מלא» про виріб цілком")
            # «הוספה לסל» — так (specs/003); «קנה עכשיו» без оплати на сайті — обіцянка, якої нема
            self.assertIsNone(re.search(r">\s*(קנה|קנו|Buy now)\s*<", html), f"{rel}: кнопка «купити»")

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
        for rel in [*DIST_PREFIX.values(), f"p/{PRODUCTS[0]['slug']}/"]:
            html = self.page(rel)
            self.assertIn(f'<link rel="canonical" href="{site}/{rel}', html, rel)
            for lang in [*LOCALES, "x-default"]:
                self.assertIn(f'hreflang="{lang}"', html, rel)
            self.assertIn('property="og:image"', html)
            self.assertRegex(html, r'<meta name="description" content="[^"]{20,}">')

    def test_share_preview_is_own_language_and_product(self):
        # WhatsApp/Facebook: головна he/en — власне превью мовою сторінки, товар — свій герой, не старе og.png
        for rel, name in (("", "home-he"), ("en/", "home-en"), (f"p/{PRODUCTS[0]['slug']}/", PRODUCTS[0]["slug"])):
            self.assertRegex(self.page(rel), rf'property="og:image" content="[^"]*/assets/og/{name}\.[0-9a-f]+\.jpg"', rel)

    def test_sitemap_lists_products_and_robots_points_to_it(self):
        sm = (self.dist / "sitemap.xml").read_text(encoding="utf-8")
        for p in PRODUCTS:
            for prefix in LOCALES.values():
                self.assertIn(f"{prefix}/p/{p['slug']}/", sm)
        robots = (self.dist / "robots.txt").read_text(encoding="utf-8")
        self.assertRegex(robots, r"Sitemap: https://[^\s{]+/sitemap\.xml")

    def test_language_switcher_lists_every_language_current_not_a_link(self):
        # шапка і підвал: кожна мова своєю назвою, на ту саму сторінку; поточна — текст з aria-current
        names = [json.loads((PROJECT / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["lang_name"] for loc in LOCALES]
        for loc, prefix in DIST_PREFIX.items():
            for rel in ("", "catalog/", f"p/{PRODUCTS[0]['slug']}/", "privacy"):
                html = self.page(prefix + rel)
                groups = re.findall(r'<span class="(?:nav|foot)-lang" role="group"[^>]*>(.*?)</span>\n', html)
                with self.subTest(page=prefix + rel):
                    self.assertEqual(len(groups), 2, "перемикач у шапці і в підвалі")
                    for g in groups:
                        self.assertEqual(re.findall(r">([^<]+)</(?:a|span)>", g), names)
                        self.assertIn(f'<span class="lang-cur" lang="{loc}" aria-current="true">', g)
                        self.assertNotIn(f'hreflang="{loc}"', g, "поточна мова — не посилання")
                        for other, pre in LOCALES.items():
                            if other != loc:
                                href = f"{pre}/{rel}" if pre or rel else "/"
                                self.assertIn(f'<a href="{href}" hreflang="{other}"', g)

    def test_lead_form_has_unchecked_marketing_consent(self):
        html = self.page("")
        box = re.search(r'<input[^>]*name="consent_marketing"[^>]*>', html)
        self.assertIsNotNone(box, "окрема галочка згоди на рекламу (חוק התקשורת 30א)")
        self.assertNotIn("checked", box.group(0))
        self.assertIn('name="website"', html, "приманка для ботів")

    def test_accessibility_menu_and_cookie_choice_on_every_page(self):
        for rel, html in self.all_html():
            if not rel.endswith("index.html") and rel not in [pre + "privacy.html" for pre in DIST_PREFIX.values()]:
                continue
            self.assertIn('class="skip"', html, rel)
            self.assertIn("data-a11y-opt=", html, rel)
            self.assertIn("data-notice-no", html, rel)

    def test_legal_pages_hide_blocks_until_the_config_fills_them(self):
        if not (PROJECT / "i18n" / "legal.he.json").is_file():
            self.skipTest("legal.*.json ще немає (сесія 3)")
        for prefix in DIST_PREFIX.values():
            for rel in ("privacy", "terms", "accessibility"):
                html = self.page(prefix + rel + ".html")
                text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
                self.assertIsNone(re.search(r"\{[a-z0-9_]+\}", re.sub(r"<[^>]+>", " ", text)), f"{prefix}{rel}: сирий плейсхолдер")
                self.assertIn('class="legal-sec"', html, f"{prefix}{rel}: текст із legal.*.json")
                for tag in re.findall(r"<(?:p|li)[^>]*data-lneed=[^>]*>", html):
                    self.assertIn(" hidden", tag, f"{prefix}{rel}: блок без даних видно")
        self.assertIn('data-lneed="a11y_email a11y_name a11y_phone"', self.page("accessibility.html"))


    def test_no_comments_in_pages(self):
        # 22.10: коментарі aluma.css (12,9 КБ) і вбудованого скрипта їхали в кожну сторінку кожної мови
        pages = [f for f in sorted(self.dist.rglob("*")) if f.is_file() and (f.suffix == ".html" or f.suffix == "")]
        self.assertGreater(len(pages), 20)
        for f in pages:
            self.assertNotIn("/*", f.read_text(encoding="utf-8"), f.relative_to(self.dist).as_posix())

if __name__ == "__main__":
    unittest.main()
