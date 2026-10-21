"""Креативи Meta (tools/creatives/, docs/creatives/): чесність тексту й межі зображень.

Сам знімок робить Playwright (node tools/creatives/build.js) і вже перевіряє текст ≤ 20 %, контраст ≥ 4.5:1,
позначку «הדמיה» і ≤ 500 КБ. Тут — те, що можна зламати правкою JSON без браузера: тексти не обіцяють
знижок, залишків і відгуків, товари є в каталозі, а викладені в docs/creatives/ файли відповідають звіту.

    python -m unittest tests.test_quality_creatives -v
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = ROOT / "tools" / "creatives" / "creatives.json"
TEMPLATE = ROOT / "tools" / "creatives" / "template.html"
CATALOG = ROOT / "catalog" / "products.json"
OUT = ROOT / "docs" / "creatives"

# Закон про захист споживача + правила власника: ні знижок, ні дефіциту, ні відгуків, ні «в наявності», ні «купи».
FORBIDDEN = [
    r"הנחה", r"מבצע", r"%", r"נותר", r"אחרונ", r"מוגבל", r"במלאי", r"ביקורות", r"לקוחות מרוצים",
    r"★", r"קנ[הו]\b", r"רק היום", r"חינם", r"עץ אלון מלא", r"שנות ניסיון",
    r"(?<!\w)מאלון(?!\w)",  # шпон: «פורניר אלון», як на сайті, а не «з дуба» — читається як масив
]
# Група C «русский» — ті самі заборони російською (re.I). «Массив» — лише про кромки, як на /ru/: сам стіл — шпон.
FORBIDDEN_RU = [
    r"скидк", r"акци", r"%", r"осталос", r"последн", r"ограничен", r"в наличии", r"отзыв", r"довольных клиентов",
    r"★", r"\bкупи(те)?\b", r"только сегодня", r"бесплатн", r"лет на рынке", r"лет опыта",
    r"массивн", r"из (цельного )?дуба", r"цельн\w* дуб", r"стол из массива",
]
NB = "\u00a0"


def texts(cfg: dict) -> list[str]:
    out = [cfg["mark"], cfg["cta"], cfg["cta_note"], cfg["price_note"], cfg["price_note_many"], cfg["includes"], cfg["brand"]]
    for v in cfg["variants"]:
        out += [v["headline"], v["sub"], v["price"]]
    return out


class CreativeConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.catalog = {p["id"]: p for p in json.loads(CATALOG.read_text(encoding="utf-8"))}

    def test_three_variants_three_formats(self):
        self.assertEqual(len(self.cfg["variants"]), 3)
        self.assertEqual({(f["width"], f["height"]) for f in self.cfg["formats"]},
                         {(1080, 1080), (1080, 1350), (1080, 1920)})

    def test_products_exist_in_catalog(self):
        for v in self.cfg["variants"]:
            for pid in v["products"]:
                self.assertIn(pid, self.catalog, v["id"])

    def test_honest_text(self):
        """Позначка візуалізації, ціна — орієнтир із «טרם אושר», жодної обіцянки, якої нема."""
        self.assertEqual(self.cfg["mark"], "הדמיה")
        self.assertIn("משוער", self.cfg["price_note"])
        self.assertIn("טרם אושר", self.cfg["price_note"])
        self.assertIn("טרם אושרו", self.cfg["price_note_many"])
        # магазин (specs/003-shop-funnel): ні «реєстрації», ні тижнів — лише те, що каже картка товару
        self.assertEqual(self.cfg["cta_note"], "זמן אספקה מדויק — באישור ההזמנה")
        for t in texts(self.cfg):
            for bad in ("הרשמה", "להרשמה", "ללא תשלום", "שבועות"):
                self.assertNotIn(bad, t)
        for t in texts(self.cfg) + [self.catalog[p]["tagline"]["he"] for v in self.cfg["variants"] for p in v["products"]]:
            for pat in FORBIDDEN:
                self.assertIsNone(re.search(pat, t), f"«{pat}» у «{t}»")

    def test_prices_come_from_catalog_not_config(self):
        """Одне джерело цифр: у creatives.json жодної ціни чи розміру — лише {price}/{length}/{extended}."""
        for v in self.cfg["variants"]:
            self.assertNotRegex(v["price"] + v["sub"], r"\d{3}", v["id"])
            self.assertIn("{price}", v["price"])
            # «מ־» лише через {from}: build.js ставить його, коли цін кілька (у SAHAR одна — аудит, рядок 35)
            self.assertNotIn("מ־", v["price"], v["id"])
            self.assertIn("{from}", v["price"])

    def test_seats_in_headline_come_from_catalog(self):
        """Місця в заголовку — лише {seats}/{seats_extended} з catalog seats, без цифр у конфігу (розвідка 21.10)."""
        for v in self.cfg["variants"]:
            self.assertNotRegex(v["headline"], r"\d", v["id"])
            if "{seats" in v["headline"]:
                for pid in v["products"]:
                    self.assertIn("seats", self.catalog[pid], f"{v['id']}: у каталозі нема seats")
        tavor = next(v for v in self.cfg["variants"] if v["id"] == "tavor")
        self.assertIn("{seats}", tavor["headline"])

    def test_template_marks_every_text_for_the_checks(self):
        """Кожен текстовий плейсхолдер стоїть в елементі з data-text — інакше 20 % і контраст його не бачать."""
        html = TEMPLATE.read_text(encoding="utf-8")
        for key in ("MARK", "BRAND", "HEADLINE", "SUB", "PRICE", "PRICE_NOTE", "CTA", "CTA_NOTE"):
            self.assertRegex(html, r"data-text>[^<]*\{\{" + key + r"\}\}", key)

    def test_generators_take_language(self):
        """--lang ru (група C): кожен генератор бере мову, шаблони — її lang/dir, ru пише в docs/creatives/ru/.
        he — за замовчуванням і в корінь docs/creatives/, щоб he-вихід лишився байт-у-байт тим самим."""
        js = (ROOT / "tools" / "creatives" / "build.js").read_text(encoding="utf-8")
        self.assertIn("he: { dir: 'rtl', locale: 'he-IL', out: '' },", js)
        self.assertIn("ru: { dir: 'ltr', locale: 'ru-RU', out: 'ru' },", js)
        for name in ("build.js", "tones.js", "video.js"):
            src = (ROOT / "tools" / "creatives" / name).read_text(encoding="utf-8")
            self.assertIn("'--lang'", src, name)
            self.assertIn("lang: 'he'", src, f"{name}: he — мова за замовчуванням")
            self.assertNotRegex(src, r"\.he\b|'he-IL'(?!, out)", f"{name}: іврит зашитий мимо мови")
        for name in ("template.html", "tones.html", "video.html"):
            html = (ROOT / "tools" / "creatives" / name).read_text(encoding="utf-8")
            self.assertIn('<html lang="{{LANG}}" dir="{{DIR}}">', html, name)
        # кирилиця — ті самі файли й unicode-range, що на сайті (site/assets/aluma.css)
        css = (ROOT / "site" / "assets" / "aluma.css").read_text(encoding="utf-8")
        self.assertIn("unicode-range: U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116;", css)
        self.assertIn("unicode-range:U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116;", js)
        for f in ("PlexSans-400-cyrillic.woff2", "PlexSans-600-cyrillic.woff2", "PlexSans-700-cyrillic.woff2", "PTSerif-cyrillic.woff2"):
            self.assertIn(f, js)
            self.assertTrue((ROOT / "site" / "assets" / "fonts" / f).is_file(), f)

    def test_static_9x16_card_below_product_above_reels_zone(self):
        """Статика 9:16: картка під кадрами, не в нижніх 20 %; вертикальний рендер — картка нижче 1000 px.
        Раніше картка лежала на кадрі й різала ніжки й нижні плитки колекції (дирижер, 21.10)."""
        html = TEMPLATE.read_text(encoding="utf-8")
        js = (ROOT / "tools" / "creatives" / "build.js").read_text(encoding="utf-8")
        media = int(re.search(r"\.f-9x16 \{ --media-h: (\d+)px;", html).group(1))
        self.assertLessEqual(media, 1000)
        self.assertIn(".f-9x16 .panel { inset: calc(var(--media-h) + 16px) 48px 384px 48px;", html)
        self.assertIn(".f-9x16.tall .panel { top: 1016px; }", html)
        self.assertEqual(384, 0.2 * 1920)
        for problem in ("картка закриває кадр товару", "картка в нижніх 20 %", "картка вище 1000 px", "вертикальний рендер не 9:16"):
            self.assertIn(problem, js)


class RussianCreativeTests(unittest.TestCase):
    """Група C «русский» (--lang ru): блок "ru" у creatives.json — той самий план, слова — як на /ru/ (i18n/ru.json)."""

    @classmethod
    def setUpClass(cls):
        cls.root = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.cfg = cls.root["ru"]
        cls.catalog = {p["id"]: p for p in json.loads(CATALOG.read_text(encoding="utf-8"))}
        cls.site = json.loads((ROOT / "i18n" / "ru.json").read_text(encoding="utf-8"))

    def test_same_structure_as_he(self):
        """Товари, формати й порядок — лише з кореня; ru міняє тільки слова."""
        self.assertEqual([v["id"] for v in self.cfg["variants"]], [v["id"] for v in self.root["variants"]])
        for v in self.cfg["variants"]:
            self.assertEqual(set(v), {"id", "headline", "sub", "price"}, v["id"])
        for key in ("mark", "cta", "cta_note", "from", "price_note", "price_note_many", "includes"):
            self.assertIn(key, self.cfg)
        self.assertNotIn("formats", self.cfg)
        self.assertEqual(self.cfg["brand"], self.root["brand"])
        for p in {p for v in self.root["variants"] for p in v["products"]}:
            self.assertEqual(self.catalog[p]["name"]["ru"], self.catalog[p]["name"]["en"], "назви — латиницею, як у каталозі")

    def test_words_are_the_site_words(self):
        """Позначка, строк, що входить у ціну, і застереження — дослівно як на /ru/."""
        self.assertEqual(self.cfg["mark"], self.site["viz_tag"])
        self.assertEqual(self.cfg["cta_note"], self.site["lead_exact"])
        self.assertEqual(self.cfg["includes"], self.site["price_incl"])
        self.assertTrue(self.site["cart_fine"].startswith(self.cfg["price_note"]), "застереження сайту змінилось")
        self.assertIn("не подтверждена", self.cfg["price_note"])
        self.assertIn("не подтверждены", self.cfg["price_note_many"])

    def test_honest_text(self):
        taglines = [self.catalog[p]["tagline"]["ru"] for v in self.root["variants"] for p in v["products"]]
        tones = [f["name"]["ru"] for f in self.catalog[self.root["tones"]["product"]]["finishes"]]
        for t in texts(self.cfg) + taglines + tones + [self.cfg["tones"]["sub"]]:
            self.assertNotRegex(t, r"[\u0590-\u05ff]", "іврит у ru")
            for pat in FORBIDDEN_RU:
                self.assertIsNone(re.search(pat, t, re.I), f"«{pat}» у «{t}»")
            for bad in ("регистрац", "недел", "без оплаты"):
                self.assertNotIn(bad, t.lower())

    def test_numbers_from_catalog_and_typography(self):
        """Жодної цифри в конфігу; «ёлочки» й «—»; нерозривний пробіл перед «₪», «см» і навколо «→»."""
        self.assertEqual(self.cfg["from"], "от" + NB)
        for v in self.cfg["variants"]:
            self.assertNotRegex(v["headline"] + v["sub"] + v["price"], r"\d", v["id"])
            self.assertEqual(v["price"], "{from}{price}" + NB + "₪", v["id"])
            if "{extended}" in v["sub"]:
                self.assertIn("{length}" + NB + "→" + NB + "{extended}" + NB + "см", v["sub"], v["id"])
        self.assertIn("{seats}", next(v for v in self.cfg["variants"] if v["id"] == "tavor")["headline"])
        self.assertNotRegex(self.cfg["tones"]["sub"].replace("{i}/{n}", ""), r"\d")
        for t in texts(self.cfg) + [self.cfg["tones"]["sub"]]:
            self.assertNotIn('"', t, "лапки — «ёлочки»")
            self.assertNotIn(" - ", t, "тире — «—»")


@unittest.skipUnless((OUT / "report.json").exists(), "docs/creatives/ ще не зібрано")
class PublishedCreativesTests(unittest.TestCase):
    out, lang = OUT, "he"

    def test_report_matches_files_and_limits(self):
        OUT = self.out  # той самий тест для he (docs/creatives/) і ru (docs/creatives/ru/)
        report = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report.get("lang", "he"), self.lang)
        items = report["creatives"]
        self.assertEqual(len(items), 9)
        for it in items:
            f = OUT / it["file"]
            self.assertTrue(f.is_file(), it["file"])
            self.assertLessEqual(f.stat().st_size, 500 * 1024, it["file"])
            self.assertEqual(f.stat().st_size, it["bytes"], it["file"])
            self.assertLessEqual(it["text_share"], 0.20, it["file"])
            self.assertGreaterEqual(it["min_contrast"], 4.5, it["file"])
            # кожен товар креативу видно: інакше «від ₪…» — ціна товару, якого на картинці немає
            self.assertEqual(len(it["tiles"]), len(it["products"]), it["file"])
            for pid, share in zip(it["products"], it["tiles"]):
                self.assertGreaterEqual(share, report["limits"]["min_tile_share"], f"{it['file']}: {pid}")
            for img in it["images"]:
                self.assertTrue(img.startswith("site/assets/products/"), f"{it['file']}: кадр не з каталогу — {img}")
        self.assertTrue((OUT / "preview.html").is_file())
        self.assertLessEqual((OUT / "preview.jpg").stat().st_size, 500 * 1024)


@unittest.skipUnless((OUT / "ru" / "report.json").exists(), "docs/creatives/ru/ ще не зібрано")
class PublishedRussianCreativesTests(PublishedCreativesTests):
    out, lang = OUT / "ru", "ru"


class TonesCarouselTests(unittest.TestCase):
    """Карусель «один стіл у п'яти тонах» (tools/creatives/tones.js, висновок 4): тони й застереження — з каталогу та сайту."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.catalog = {p["id"]: p for p in json.loads(CATALOG.read_text(encoding="utf-8"))}
        cls.he = json.loads((ROOT / "i18n" / "he.json").read_text(encoding="utf-8"))

    def test_config_has_no_own_facts(self):
        t = self.cfg["tones"]
        self.assertIn(t["product"], self.catalog)
        self.assertNotRegex(t["sub"].replace("{i}/{n}", ""), r"\d", "номер картки й кількість тонів рахує tones.js")
        self.assertTrue(self.he["matb_3_p"].startswith("הגוון במסך הוא קירוב;"), "застереження сайту змінилось")
        for pat in FORBIDDEN:
            self.assertIsNone(re.search(pat, t["sub"]), pat)

    def test_meta_test_card_names_are_catalog_tones(self):
        doc = (ROOT / "docs" / "META-TEST.md").read_text(encoding="utf-8")
        line = re.search(r"\*\*Заголовки карточек:\*\* (.+)", doc).group(1)
        names = [f["name"]["he"] for f in self.catalog[self.cfg["tones"]["product"]]["finishes"]]
        self.assertEqual(line.split(" · "), names)

    def test_template_marks_every_text(self):
        html = (ROOT / "tools" / "creatives" / "tones.html").read_text(encoding="utf-8")
        for key in ("MARK", "BRAND", "TONE", "SUB", "NOTE"):
            self.assertRegex(html, r"data-text>[^<]*\{\{" + key + r"\}\}", key)


TONES = OUT / "tones"


@unittest.skipUnless((TONES / "report.json").exists(), "docs/creatives/tones/ ще не зібрано")
class PublishedTonesTests(unittest.TestCase):
    tones_dir, lang = TONES, "he"

    def test_report_matches_files_and_limits(self):
        TONES = self.tones_dir
        report = json.loads((TONES / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report.get("lang", "he"), self.lang)
        catalog = {p["id"]: p for p in json.loads(CATALOG.read_text(encoding="utf-8"))}
        tones = catalog[report["product"]]["finishes"]
        cards = report["cards"]
        self.assertEqual({(c["tone"], c["width"], c["height"]) for c in cards},
                         {(t["id"], 1080, h) for t in tones for h in (1080, 1350)})
        names = {t["id"]: t["name"][self.lang] for t in tones}
        images = set()
        for c in cards:
            f = TONES / c["file"]
            self.assertEqual(f.stat().st_size, c["bytes"], c["file"])
            self.assertLessEqual(c["bytes"], 500 * 1024, c["file"])
            self.assertLessEqual(c["text_share"], 0.20, c["file"])
            self.assertGreaterEqual(c["min_contrast"], 4.5, c["file"])
            self.assertEqual(c["tone_name"], names[c["tone"]])
            self.assertEqual(c["image"], f"site/assets/products/{report['product']}/finish-{c['tone']}-1600.jpg")
            images.add(c["image"])
        self.assertEqual(len(images), len(tones), "у кожного тону свій рендер")
        self.assertTrue((TONES / "sheet.jpg").is_file())


@unittest.skipUnless((OUT / "ru" / "tones" / "report.json").exists(), "docs/creatives/ru/tones/ ще не зібрано")
class PublishedRussianTonesTests(PublishedTonesTests):
    tones_dir, lang = OUT / "ru" / "tones", "ru"


VIDEO = OUT / "video"


@unittest.skipUnless((VIDEO / "report.json").exists(), "docs/creatives/video/ ще не зібрано")
class PublishedVideosTests(unittest.TestCase):
    """Відео (tools/creatives/video.js): 3 ролики × 9:16, 4:5 і 1:1, 6–10 с, ≤ 4 МБ, кадри лише з каталогу."""

    video_dir, lang = VIDEO, "he"

    def test_report_matches_files_and_limits(self):
        VIDEO = self.video_dir
        report = json.loads((VIDEO / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report.get("lang", "he"), self.lang)
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        items = report["videos"]
        self.assertEqual({(it["file"].rsplit("-", 1)[0], it["width"], it["height"]) for it in items},
                         {(v["id"], w, h) for v in cfg["variants"] for w, h in ((1080, 1920), (1080, 1350), (1080, 1080))})
        for it in items:
            f = VIDEO / it["file"]
            self.assertTrue(f.is_file(), it["file"])
            self.assertEqual(f.stat().st_size, it["bytes"], it["file"])
            self.assertLessEqual(it["bytes"], report["limits"]["max_bytes"], it["file"])
            self.assertLessEqual(report["limits"]["max_bytes"], 4 * 1024 * 1024)
            self.assertTrue(6 <= it["duration"] <= 10, it["file"])
            self.assertGreaterEqual(it["min_contrast"], 4.5, it["file"])
            self.assertEqual(f.read_bytes()[4:8], b"ftyp", f"{it['file']}: не MP4")
            for img in it["images"]:
                self.assertTrue(img.startswith("site/assets/products/"), f"{it['file']}: кадр не з каталогу — {img}")
        self.assertAlmostEqual(report["limits"]["safe_zone"], 0.14)
        self.assertTrue((VIDEO / "sheet.jpg").is_file())


@unittest.skipUnless((VIDEO.parent / "ru" / "video" / "report.json").exists(), "docs/creatives/ru/video/ ще не зібрано")
class PublishedRussianVideosTests(unittest.TestCase):
    video_dir, lang = VIDEO.parent / "ru" / "video", "ru"
    test_report_matches_files_and_limits = PublishedVideosTests.test_report_matches_files_and_limits

    def test_vertical_formats_keep_product_above_card(self):
        # 9:16 і 4:5: кадр — смуга над карткою (весь стіл на 0 с), video.js падає, якщо картка заходить на кадр
        # або в нижні 20 % 9:16. Без цього картка закривала ніжки й довжину стола (дирижер, 21.10).
        html = (ROOT / "tools" / "creatives" / "video.html").read_text(encoding="utf-8")
        js = (ROOT / "tools" / "creatives" / "video.js").read_text(encoding="utf-8")
        self.assertIn(".f-9x16 .shot, .f-4x5 .shot { inset: auto 0 auto 0; top: var(--media-top); height: var(--media-h); }", html)
        top, media = (int(x) for x in re.search(r"\.f-9x16 \{ --media-top: (\d+)px; --media-h: (\d+)px; \}", html).groups())
        self.assertLessEqual(top + media, 0.55 * 1920, "9:16: стіл має бути у верхніх 55 %")
        self.assertIn("картка закриває кадр товару", js)
        self.assertIn("картка в нижніх 20 %", js)


class MetaTestPlanTests(unittest.TestCase):
    """docs/META-TEST.md: реклама веде на сторінки, що є, а текст оголошень — за тими ж заборонами."""

    @classmethod
    def setUpClass(cls):
        cls.doc = (ROOT / "docs" / "META-TEST.md").read_text(encoding="utf-8")
        cls.ids = {p["id"] for p in json.loads(CATALOG.read_text(encoding="utf-8"))}

    def test_ad_links_lead_to_existing_pages(self):
        line = re.search(r"\*\*Ссылки объявлений:\*\*(.*?)\n\n", self.doc, re.S).group(1)
        links = re.findall(r"`(/[^`]*)`", line.split("Якорей")[0])
        self.assertEqual(len(links), 3, line)
        for link in links:
            self.assertNotIn("#", link, "якоря на головній немає")
            m = re.fullmatch(r"/p/([a-z]+)/", link)
            if m:
                self.assertIn(m.group(1), self.ids, link)
            else:
                self.assertIn(link, ("/", "/catalog/"), link)

    def test_ad_names_match_creative_files(self):
        names = set(re.findall(r"`([a-z]+-\d+x\d+)`", self.doc.split("Названия объявлений", 1)[1].split("Групп", 1)[0]))
        ratio = {"1080x1080": "1x1", "1080x1350": "4x5", "1080x1920": "9x16"}
        files = {f"{f.stem.rsplit('-', 1)[0]}-{ratio[f.stem.rsplit('-', 1)[1]]}" for f in OUT.glob("*-1080x*.jpg")}
        self.assertEqual(names, files)

    def test_ad_copy_is_honest(self):
        section = self.doc.split("## 3.", 1)[1].split("## 4.", 1)[0]
        # текст оголошення — частина рядка після останнього «**», без кирилиці пояснень
        ads = [t for t in (ln.split("**")[-1] for ln in section.splitlines())
               if re.search(r"[\u0590-\u05ff]", t) and not re.search(r"[а-яА-Я]", t)]
        self.assertGreaterEqual(len(ads), 10)
        for t in ads:
            for pat in FORBIDDEN:
                self.assertIsNone(re.search(pat, t), f"{pat}: {t}")
            self.assertNotIn("מקבלים מחיר השקה", t, "знижку раннім ніхто не підтвердив")

    def test_every_ad_says_what_the_price_includes(self):
        """В описі кожного оголошення — фраза launch-bar сайту дослівно; ні «реєстрації», ні «без оплати», ні тижнів."""
        section = self.doc.split("## 3.", 1)[1].split("## 4.", 1)[0]
        descs = re.findall(r"^- \*\*Описание:\*\* (.+)$", section, re.M)
        self.assertEqual(len(descs), 4, descs)  # три креативи + карусель тонів
        phrase = "המחיר כולל מע״מ, משלוח והרכבה"
        for d in descs:
            self.assertIn(phrase, d)
        site = json.loads((ROOT / "i18n" / "he.json").read_text(encoding="utf-8"))
        self.assertIn(phrase, site["launch_bar"])
        for bad in ("הרשמה", "ללא תשלום", "שבועות"):
            self.assertNotIn(bad, self.doc.split("## 3.", 1)[1].split("## 4.", 1)[0])


class MetaTestGroupCTests(unittest.TestCase):
    """docs/META-TEST.md §4а, група C «русский»: посилання на /ru/, назви з -ru — за файлами docs/creatives/ru/."""

    @classmethod
    def setUpClass(cls):
        doc = (ROOT / "docs" / "META-TEST.md").read_text(encoding="utf-8")
        cls.section = doc.split("## 4а.", 1)[1].split("## 5.", 1)[0]
        cls.ids = {p["id"] for p in json.loads(CATALOG.read_text(encoding="utf-8"))}
        cls.site = json.loads((ROOT / "i18n" / "ru.json").read_text(encoding="utf-8"))

    def test_links_lead_to_ru_pages(self):
        line = re.search(r"\*\*Ссылки объявлений:\*\*(.*?)\n\n", self.section, re.S).group(1)
        links = re.findall(r"`(/[^`]*)`", line)
        self.assertEqual(links, ["/ru/p/tavor/", "/ru/p/sahar/", "/ru/catalog/"])
        for link in links[:2]:
            self.assertIn(link.split("/")[3], self.ids, link)

    def test_ad_names_match_ru_files(self):
        part = self.section.split("**Названия объявлений**", 1)[1].split("UTM", 1)[0]
        names = set(re.findall(r"`([a-z]+-[a-z0-9]+-ru)`", part))
        ratio = {"1080x1080": "1x1", "1080x1350": "4x5", "1080x1920": "9x16"}
        ru = OUT / "ru"
        files = {f"{f.stem.rsplit('-', 1)[0]}-{ratio[f.stem.rsplit('-', 1)[1]]}-ru" for f in ru.glob("*-1080x*.jpg")}
        files |= {f"{f.stem.rsplit('-', 1)[0]}-video-ru" for f in (ru / "video").glob("*-1080x1920.mp4")}
        files |= {"tavor-tones-ru"} if (ru / "tones").is_dir() else set()
        self.assertEqual(names, files)

    def test_ad_copy_is_honest(self):
        ads = re.findall(r"```text\n(.*?)```", self.section, re.S)
        ads += re.findall(r"^- \*\*(?:Заголовок|Описание|Заголовки карточек):\*\* (.+)$", self.section, re.M)
        self.assertEqual(len(ads), 4 * 3 + 1)
        for t in ads:
            self.assertNotRegex(t, r"[\u0590-\u05ff]")
            for pat in FORBIDDEN_RU:
                self.assertIsNone(re.search(pat, t, re.I), f"{pat}: {t}")
            for bad in ("регистрац", "недел", "без оплаты"):
                self.assertNotIn(bad, t.lower())
            self.assertNotRegex(t, r"\d ₪|\d см", "перед «₪» і «см» — нерозривний пробіл")

    def test_every_ad_says_what_the_price_includes(self):
        descs = re.findall(r"^- \*\*Описание:\*\* (.+)$", self.section, re.M)
        self.assertEqual(len(descs), 4, descs)
        phrase = "в цену входят НДС, доставка и сборка"
        self.assertIn(phrase, self.site["launch_bar"])
        for d in descs:
            self.assertIn(phrase, d)


PAGEKIT = ROOT / "tools" / "creatives" / "pagekit.json"
KIT = ROOT / "docs" / "page-kit"
PAGE_BUTTON = ("https://table.central-aparts.store/catalog/"
               "?utm_source=facebook&utm_medium=page&utm_campaign=page_button")


def catalog_numbers(catalog: dict) -> set[str]:
    """Усі числа каталогу (розміри, розкладені довжини, місця, ціни) — інших цифр у підписах сторінки бути не може."""
    nums = set()
    for p in catalog.values():
        nums.add(str(p["price_from_ils"]))
        for s in p["sizes"]:
            for k in ("length_cm", "width_cm", "height_cm", "extended_cm", "price_ils"):
                if k in s:
                    nums.add(str(s[k]))
        for pair in p.get("seats", {}).values():
            nums.update(str(n) for n in pair)
    return nums


class PageKitTests(unittest.TestCase):
    """Стартовий набір сторінки Meta (tools/creatives/pagekit.js, docs/page-kit/): ті самі заборони, факти — з каталогу."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(PAGEKIT.read_text(encoding="utf-8"))
        cls.catalog = {p["id"]: p for p in json.loads(CATALOG.read_text(encoding="utf-8"))}
        cls.readme = (KIT / "README.md").read_text(encoding="utf-8")
        # підписи для копіювання — блоки ```text (іврит), посилання з них прибираємо перед перевіркою цифр
        cls.blocks = re.findall(r"```text\n(.*?)```", cls.readme, re.S)

    def config_texts(self) -> list[str]:
        c = self.cfg
        out = [c["avatar"]["he"], c["cover"]["headline"], c["cover"]["sub"]] + [h["title"] for h in c["highlights"]]
        for post in c["posts"]:
            out += [post["headline"], post["sub"]]
        return out

    def test_nine_posts_three_highlights(self):
        self.assertEqual(len(self.cfg["posts"]), 9)
        self.assertEqual(len({p["id"] for p in self.cfg["posts"]}), 9)
        self.assertEqual([h["title"] for h in self.cfg["highlights"]], ["הסדרה", "גוונים", "איך זה עובד"])
        self.assertEqual({(f["width"], f["height"]) for f in self.cfg["formats"]}, {(1080, 1080), (1080, 1350)})

    def test_config_text_is_honest_and_has_no_own_numbers(self):
        for t in self.config_texts():
            for pat in FORBIDDEN:
                self.assertIsNone(re.search(pat, t), f"{pat}: {t}")
            # цифри лише з каталогу: у JSON — тільки {плейсхолдери}
            self.assertNotRegex(re.sub(r"\{[a-z_]+\}", "", t), r"\d", t)

    def test_frames_come_from_catalog(self):
        frames = {i["jpg"] for p in self.catalog.values() for i in p["images"] if i.get("kind") == "visualization"}
        keys = [self.cfg["cover"]["image"]] + [k for p in self.cfg["posts"] if p["images"] != "@tones" for k in p["images"]]
        for key in keys:
            pid, view = key.split("/")
            self.assertIn(f"/assets/products/{pid}/{view}-1600.jpg", frames, key)
        for post in self.cfg["posts"]:
            self.assertIn(post["product"], self.catalog, post["id"])

    def test_template_marks_every_text(self):
        js = (ROOT / "tools" / "creatives" / "pagekit.js").read_text(encoding="utf-8")
        for snippet in ('<div class="mark" data-text>', '<h1 class="headline" data-text>', '<p class="sub" data-text>',
                        '<div class="brand" data-text>', 'class="logo-lat keep" data-text'):
            self.assertIn(snippet, js)

    def test_readme_captions_are_honest(self):
        self.assertGreaterEqual(len(self.blocks), 12)  # 3 «אודות»/bio + 9 підписів постів
        nums = catalog_numbers(self.catalog)
        for b in self.blocks:
            for pat in FORBIDDEN + [r"שבועות", r"הרשמה"]:
                self.assertIsNone(re.search(pat, b), f"{pat}: {b[:60]}")
            plain = re.sub(r"https?://\S+", "", b)
            for n in re.findall(r"\d[\d,]*", plain):
                self.assertIn(n.replace(",", ""), nums, f"число не з каталогу: {n}")

    def test_readme_links(self):
        self.assertIn(PAGE_BUTTON, self.readme)
        ids = [p["id"] for p in self.cfg["posts"]]
        posts = [b for b in self.blocks if "utm_campaign=page_posts" in b]
        self.assertEqual(len(posts), 9)
        for n, (pid, b) in enumerate(zip(ids, posts), 1):
            url = re.search(r"https://table\.central-aparts\.store(/\S*)\?(\S+)", b)
            self.assertIsNotNone(url, pid)
            page, query = url.groups()
            self.assertIn(f"utm_content=post-{n:02d}-{pid}", query, "підпис не до того поста")
            m = re.fullmatch(r"/p/([a-z]+)/", page)
            if m:
                self.assertIn(m.group(1), self.catalog, page)
            else:
                self.assertIn(page, ("/catalog/", "/faq/"), page)


@unittest.skipUnless((KIT / "report.json").exists(), "docs/page-kit/ ще не зібрано")
class PublishedPageKitTests(unittest.TestCase):
    def test_report_matches_files_and_limits(self):
        report = json.loads((KIT / "report.json").read_text(encoding="utf-8"))
        items = report["items"]
        sizes = sorted((it["kind"], it["width"], it["height"]) for it in items)
        self.assertEqual(sizes, sorted([("avatar", 1080, 1080), ("cover", 1640, 624)]
                                       + [("post", 1080, h) for h in (1080, 1350) for _ in range(9)]
                                       + [("hl", 1080, 1920)] * 3))
        for it in items:
            f = KIT / it["file"]
            self.assertTrue(f.is_file(), it["file"])
            self.assertEqual(f.stat().st_size, it["bytes"], it["file"])
            self.assertLessEqual(it["bytes"], 500 * 1024, it["file"])
            self.assertLessEqual(it["text_share"], 0.20, it["file"])
            if it["min_contrast"] is not None:
                self.assertGreaterEqual(it["min_contrast"], 4.5, it["file"])
            if it["images"]:
                self.assertTrue(it["has_mark"], f"{it['file']}: немає «הדמיה»")
            for img in it["images"]:
                self.assertTrue(img.startswith("site/assets/products/"), f"{it['file']}: кадр не з каталогу — {img}")
        self.assertTrue(all(it["has_mark"] for it in items if it["kind"] == "post"))
        self.assertEqual(report["limits"]["cover_safe_width"], 1080)
        self.assertTrue((KIT / "preview.html").is_file())
        self.assertLessEqual((KIT / "preview.jpg").stat().st_size, 900 * 1024)


if __name__ == "__main__":
    unittest.main()
