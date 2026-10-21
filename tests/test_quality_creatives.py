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
    r"★", r"קנ[הו]\b", r"רק היום", r"חינם", r"עץ אלון מלא",
    r"(?<!\w)מאלון(?!\w)",  # шпон: «פורניר אלון», як на сайті, а не «з дуба» — читається як масив
]


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
        # снімає страх, як launch-bar сайту (розвідка 21.10, висновок 5) — і нічого не обіцяє понад сайт
        self.assertEqual(self.cfg["cta_note"], "ללא תשלום וללא התחייבות")
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


@unittest.skipUnless((OUT / "report.json").exists(), "docs/creatives/ ще не зібрано")
class PublishedCreativesTests(unittest.TestCase):
    def test_report_matches_files_and_limits(self):
        report = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
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


VIDEO = OUT / "video"


@unittest.skipUnless((VIDEO / "report.json").exists(), "docs/creatives/video/ ще не зібрано")
class PublishedVideosTests(unittest.TestCase):
    """Відео (tools/creatives/video.js): 3 ролики × 9:16, 4:5 і 1:1, 6–10 с, ≤ 4 МБ, кадри лише з каталогу."""

    def test_report_matches_files_and_limits(self):
        report = json.loads((VIDEO / "report.json").read_text(encoding="utf-8"))
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

    def test_every_ad_says_no_payment_no_commitment(self):
        """Висновок 5 розвідки 21.10: у описі кожного з трьох оголошень — фраза launch-bar сайту, дослівно."""
        section = self.doc.split("## 3.", 1)[1].split("## 4.", 1)[0]
        descs = re.findall(r"^- \*\*Описание:\*\* (.+)$", section, re.M)
        self.assertEqual(len(descs), 3, descs)
        for d in descs:
            self.assertIn("ללא תשלום וללא התחייבות", d)
        site = json.loads((ROOT / "i18n" / "he.json").read_text(encoding="utf-8"))
        self.assertIn("ללא תשלום וללא התחייבות", site["launch_bar"])


if __name__ == "__main__":
    unittest.main()
