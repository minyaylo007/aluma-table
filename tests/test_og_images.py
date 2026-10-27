"""№37: OG-картинки (превью посилань у WhatsApp, Telegram, Facebook) — є для головної кожною мовою з героєм HERO_PRODUCT,
для кожного товару й «наступного видання»; 1200×630, не більше 300 КБ. Без збірки: перевіряє site/assets/og/ проти каталогу.
Що зібрані сторінки посилаються саме на них — tests/test_build_site.py (test_share_preview_*)."""

from __future__ import annotations

import json
import pathlib
import struct
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
OG = ROOT / "site" / "assets" / "og"
CONTENT = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
PRODUCTS = [p for p in json.loads((ROOT / "catalog" / "products.json").read_text(encoding="utf-8")) if not p.get("hidden")]
NEXT = json.loads((ROOT / "catalog" / "next.json").read_text(encoding="utf-8")).get("items") or []
LOCALES = ("he", "en", "ru")
MAX_BYTES = 300 * 1024


def jpeg_size(data: bytes) -> tuple[int, int]:
    """(ширина, висота) з маркера SOFn — без Pillow."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("не JPEG")
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        (seg,) = struct.unpack(">H", data[i + 2:i + 4])
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + seg
    raise ValueError("нема SOF")


def expected() -> list[str]:
    hero = CONTENT["HERO_PRODUCT"]
    return ([f"home-{hero}-{loc}.jpg" for loc in LOCALES]
            + [f"{p['slug']}.jpg" for p in PRODUCTS if any(i.get("src") for i in p.get("images") or [])]
            + [f"{n['slug']}.jpg" for n in NEXT if any(i.get("src") for i in n.get("images") or [])])


class OgImagesTests(unittest.TestCase):
    def test_every_page_kind_has_its_preview(self):
        for name in expected():
            self.assertTrue((OG / name).is_file(), f"нема {name}: node tools/make-og-products.js")

    def test_home_preview_follows_hero_product(self):
        # hero змінили — превью з назвою нового героя мусить бути; старі home-<loc>.jpg не лишаються в репо
        stale = [f.name for f in OG.glob("home-*.jpg") if not f.name.startswith(f"home-{CONTENT['HERO_PRODUCT']}-")]
        self.assertEqual(stale, [], "старі превью головної")

    def test_size_and_weight(self):
        for f in sorted(OG.glob("*.jpg")):
            data = f.read_bytes()
            self.assertEqual(jpeg_size(data), (1200, 630), f.name)
            self.assertLessEqual(len(data), MAX_BYTES, f.name)

    def test_jpeg_size_parser(self):
        sof = b"\xff\xd8" + b"\xff\xe0\x00\x04ab" + b"\xff\xc0\x00\x11\x08" + struct.pack(">HH", 630, 1200) + b"\x00" * 10
        self.assertEqual(jpeg_size(sof), (1200, 630))
        with self.assertRaises(ValueError):
            jpeg_size(b"\x89PNG")


if __name__ == "__main__":
    unittest.main()
