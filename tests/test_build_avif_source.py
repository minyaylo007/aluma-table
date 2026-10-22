"""<source type="image/avif"> лише тоді, коли AVIF справді легший (22.10).

Браузер з AVIF бере <source> першим і не дивиться на вагу: на живому tavor home-1600.avif 75 КБ проти 65 КБ WebP —
телефон качав важчий файл. build.picture() віддає AVIF-набір, лише якщо в нього ті самі ширини, що в WebP, і КОЖЕН
AVIF є й легший за свого WebP-близнюка; інакше <source> немає зовсім (набір не «дірявий»).
Фікстура — тимчасова тека з файлами потрібної ваги, build.SITE підмінено на неї.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("aluma_build_avif", ROOT / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)

BASE = "/assets/products/x/home"
IMG = {
    "src": f"{BASE}-1600.webp", "alt": {"he": "הדמיה", "en": "visualization", "ru": "визуализация"},
    "width": 1600, "height": 1068,
    "srcset": f"{BASE}-400.webp 400w, {BASE}-800.webp 800w, {BASE}-1200.webp 1200w, {BASE}-1600.webp 1600w",
    "srcset_avif": f"{BASE}-400.avif 400w, {BASE}-800.avif 800w, {BASE}-1200.avif 1200w, {BASE}-1600.avif 1600w",
}
WEBP = {400: 7000, 800: 21000, 1200: 44000, 1600: 65000}


class AvifSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = pathlib.Path(self.tmp.name)
        (self.site / BASE.lstrip("/")).parent.mkdir(parents=True)
        patcher = mock.patch.object(build, "SITE", self.site)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def files(self, avif: dict):
        for w, n in WEBP.items():
            (self.site / f"{BASE.lstrip('/')}-{w}.webp").write_bytes(b"w" * n)
        for w, n in avif.items():
            (self.site / f"{BASE.lstrip('/')}-{w}.avif").write_bytes(b"a" * n)

    def html(self, img=IMG):
        return build.picture(img, "he", eager=True, sizes="(min-width: 960px) 58vw, 100vw")

    def test_lighter_avif_gives_source(self):
        self.files({w: n - 1000 for w, n in WEBP.items()})
        out = self.html()
        self.assertIn('<source type="image/avif"', out)
        self.assertIn(f"{BASE}-1200.avif 1200w", out)
        self.assertIn(f'srcset="{IMG["srcset"]}"', out)

    def test_one_heavy_avif_drops_whole_source(self):
        # як на живому tavor: усе легше, крім 1600 (75 КБ проти 65)
        self.files({400: 6000, 800: 20000, 1200: 43000, 1600: 75000})
        out = self.html()
        self.assertNotIn("image/avif", out)
        self.assertNotIn(".avif", out)
        self.assertIn(f'srcset="{IMG["srcset"]}"', out)   # WebP-набір цілий, з 1200w

    def test_equal_size_is_not_lighter(self):
        self.files({**{w: n - 1000 for w, n in WEBP.items()}, 400: WEBP[400]})
        self.assertNotIn("image/avif", self.html())

    def test_missing_avif_drops_source(self):
        self.files({400: 6000, 800: 20000, 1600: 60000})
        self.assertNotIn("image/avif", self.html())

    def test_avif_set_without_a_width_drops_source(self):
        # WebP з 1200w, а AVIF без неї: браузер з AVIF узяв би 1600 — не віддаємо
        self.files({w: n - 1000 for w, n in WEBP.items()})
        img = dict(IMG, srcset_avif=f"{BASE}-400.avif 400w, {BASE}-800.avif 800w, {BASE}-1600.avif 1600w")
        self.assertNotIn("image/avif", self.html(img))

    def test_derived_from_webp_srcset_when_no_srcset_avif(self):
        self.files({w: n - 1000 for w, n in WEBP.items()})
        img = {k: v for k, v in IMG.items() if k != "srcset_avif"}
        self.assertIn(f'srcset="{IMG["srcset_avif"]}"', self.html(img))


class CatalogAvifTests(unittest.TestCase):
    """Справжній каталог: кожен AVIF, який дійде до сторінки, легший за WebP; у home/hero є 1200w."""

    def test_catalog_home_and_hero_have_1200_and_only_light_avif(self):
        products = json.loads((ROOT / "catalog" / "products.json").read_text(encoding="utf-8"))
        for p in products:
            for img in p["images"]:
                if not re.search(r"/(home|hero)-\d+\.webp$", img["src"]):
                    continue
                with self.subTest(src=img["src"]):
                    self.assertIn("-1200.webp 1200w", img["srcset"])
                    avset = build.avif_srcset(img, img["src"])
                    for url in re.findall(r"(\S+\.avif)", avset):
                        a = (build.SITE / url.lstrip("/")).stat().st_size
                        w = (build.SITE / (url[:-5] + ".webp").lstrip("/")).stat().st_size
                        self.assertLess(a, w, url)


if __name__ == "__main__":
    unittest.main()
