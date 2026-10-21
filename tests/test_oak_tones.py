"""Тони дуба: одна таблиця в трьох місцях (генератор, 3D, Blender), зразок на кожен тон каталогу, фото з фабрики."""
import json
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEX = ROOT / "site" / "assets" / "textures"
SWATCH = ROOT / "site" / "assets" / "products" / "finishes"


def js_finishes():
    """FINISHES з aluma3d.js -> {тон: (альбедо, скан, щільність)}; шляхи там повні — їх публікує build.py."""
    src = (ROOT / "site" / "assets" / "products" / "aluma3d.js").read_text(encoding="utf-8")
    rows = re.findall(r"(\w+):\s*\{[^}]*scale:\s*([\d.]+),\s*albedo:\s*'/assets/textures/([\w-]+)-1024\.jpg',\s*"
                      r"nmap:\s*'/assets/textures/([\w-]+)-normal-1024\.jpg',\s*rmap:\s*'/assets/textures/([\w-]+)-rough-1024\.jpg'\s*\}", src)
    for t, _s, _a, n, r in rows:
        assert n == r, f"{t}: нормалі й шорсткість — з одного скану"
    return {t: (a, n, float(s)) for t, s, a, n, _r in rows}


def blender_tones():
    src = (ROOT / "tools" / "blender_scene.py").read_text(encoding="utf-8")
    body = src[src.index("TONE_TEX = {"):]
    body = body[:body.index("}") + 1]
    rows = re.findall(r'"(\w+)":\s*\("([\w-]+)",\s*"([\w-]+)",\s*([\d.]+)\)', body)
    return {t: (a, m, float(s)) for t, a, m, s in rows}


def catalog_tones():
    data = json.loads((ROOT / "catalog" / "products.json").read_text(encoding="utf-8"))
    products = data if isinstance(data, list) else data["products"]
    return {f["id"] for p in products for f in p.get("finishes") or []}


class OakTonesTables(unittest.TestCase):
    def test_3d_and_blender_share_one_table(self):
        js, bl = js_finishes(), blender_tones()
        self.assertEqual(set(js), catalog_tones())
        self.assertEqual(js, bl)

    def test_generator_matches_the_table(self):
        # oak_tones.py тягне numpy і Pillow, яких немає в CI — читаємо таблиці текстом
        src = (ROOT / "tools" / "oak_tones.py").read_text(encoding="utf-8")
        scans = {k: (float(m), pre) for k, m, pre in
                 re.findall(r'"([\w-]+)":\s*\("\w+",\s*([\d.]+),\s*(?:True|False),\s*"([\w-]+)"\)', src)}
        tones = dict((t, (k, stem)) for t, k, stem in
                     re.findall(r'"(\w+)":\s*\("([\w-]+)",\s*\w+,\s*"([\w-]+)"\)', src))
        js = js_finishes()
        self.assertEqual(set(tones), set(js))
        for tone, (scan, stem) in tones.items():
            with self.subTest(tone=tone):
                self.assertEqual(stem, js[tone][0])
                self.assertEqual(scans[scan][1], js[tone][1])
                # щільність повтору = 1,83 м oak_veneer_01 / розмір скану
                self.assertAlmostEqual(js[tone][2], round(1.83 / scans[scan][0], 2))

    def test_every_tone_file_is_in_the_site(self):
        for tone, (albedo, maps, _s) in js_finishes().items():
            with self.subTest(tone=tone):
                for name in (f"{albedo}-1024.jpg", f"{maps}-normal-1024.jpg", f"{maps}-rough-1024.jpg"):
                    self.assertTrue((TEX / name).is_file(), name)
                for ext in ("webp", "jpg"):
                    f = SWATCH / f"{tone}.{ext}"
                    self.assertTrue(f.is_file(), f.name)
                    self.assertLess(f.stat().st_size, 20 * 1024, f.name)


class FinishChips(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT))
        import build
        self.build = build
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.addCleanup(sys.path.remove, str(ROOT))

    def test_scan_chip_is_a_visualization(self):
        style, photo = self.build.finish_chip({"id": "honey", "hex": "#956D3E"})
        self.assertIn("--i:url(/assets/products/finishes/honey.webp)", style)
        self.assertFalse(photo)
        self.assertTrue(self.build.finishes_viz([{"id": "honey", "hex": "#956D3E"}]))

    def test_factory_photo_replaces_the_scan(self):
        (self.tmp / "honey.jpg").write_bytes(b"\xff\xd8" + b"0" * 100)
        with mock.patch.object(self.build, "FINISH_PHOTOS", self.tmp):
            style, photo = self.build.finish_chip({"id": "honey", "hex": "#956D3E"})
            self.assertIn("/assets/products/finishes/photo/honey.jpg", style)
            self.assertTrue(photo)
            self.assertFalse(self.build.finishes_viz([{"id": "honey", "hex": "#956D3E"}]))
            # фото є не для всіх тонів — група лишається «הדמיה»
            self.assertTrue(self.build.finishes_viz([{"id": "honey"}, {"id": "black"}]))

    def test_oversized_factory_photo_stops_the_build(self):
        (self.tmp / "black.jpg").write_bytes(b"0" * (self.build.FINISH_PHOTO_MAX + 1))
        with mock.patch.object(self.build, "FINISH_PHOTOS", self.tmp):
            with self.assertRaises(SystemExit):
                self.build.finish_chip({"id": "black", "hex": "#2D2722"})

    def test_unknown_id_falls_back_to_colour(self):
        style, photo = self.build.finish_chip({"id": "../x", "hex": "not-a-hex"})
        self.assertEqual(style, "--c:#c8a27a")
        self.assertFalse(photo)


if __name__ == "__main__":
    unittest.main()
