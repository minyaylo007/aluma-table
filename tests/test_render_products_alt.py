"""tools/render_products.js --add=life не губить ru alt у catalog/products.json (№25).

Без рендера, Blender і браузера: node підвантажує скрипт (require без запуску) і проганяє лише запис каталогу —
imageRecord + mergeImages — на копії products.json у пам'яті, з шириною й srcset старого запису. Файл на диску
не змінюється. Що перевірка вміє падати, доведено в пам'яті: той самий скрипт із вирізаним злиттям і без ru у
таблицях (стара поведінка) губить ru — test_old_behaviour_loses_ru.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "render_products.js"
CATALOG = ROOT / "catalog" / "products.json"
NODE = shutil.which("node")

# Харнес: компілює скрипт як модуль (з необов'язковими замінами в тексті — лише в пам'яті), робить --add=<кадри>
# на копії каталогу і друкує alt до і після.
HARNESS = r"""
const fs = require('fs'), Module = require('module');
const [script, catalogFile, frames, subs] = process.argv.slice(1);
let src = fs.readFileSync(script, 'utf8');
for (const [a, b] of JSON.parse(subs)) { if (!src.includes(a)) throw new Error('немає ' + a); src = src.split(a).join(b); }
const m = new Module(script, null); m.filename = script; m.paths = Module._nodeModulePaths(require('path').dirname(script));
m._compile(src, script);
const r = m.exports, catalog = JSON.parse(fs.readFileSync(catalogFile, 'utf8')), add = frames.split(',');
const out = {};
for (const p of catalog) {
  const before = p.images.map(im => [r.nameOf(im), im.alt]);
  const images = [];
  for (const f of r.framesFor(p)) {
    if (!add.includes(f.name)) continue;
    const old = p.images.find(im => r.nameOf(im) === f.name);
    const widths = old.srcset.split(', ').map(s => +s.split(' ')[1].replace('w', ''));
    images.push(r.imageRecord(p, f, old.width, old.height, widths));
  }
  p.images = r.mergeImages(p, images);
  out[p.id] = { before, after: p.images.map(im => [r.nameOf(im), im.alt]) };
}
process.stdout.write(JSON.stringify(out));
"""

# Стара поведінка (до №25): злиття нема, а altFor ru не дає.
OLD = [
    ["return Object.assign({}, prev && prev.alt, alt);", "return alt;"],
    ["if (kr && vr && !steel) alt.ru", "if (false) alt.ru"],
]


def add_frames(frames: str, subs=(), catalog: dict | None = None, tmp: Path | None = None) -> dict:
    path = CATALOG
    if catalog is not None:
        path = tmp / "products.json"
        path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run([NODE, "-e", HARNESS, str(SCRIPT), str(path), frames, json.dumps(list(subs))],
                         capture_output=True, text=True, timeout=30, check=True, cwd=ROOT)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "node не встановлено")
class RenderProductsAltTests(unittest.TestCase):
    def test_add_life_keeps_ru_in_all_products(self):
        before_disk = CATALOG.read_bytes()
        res = add_frames("life")
        self.assertEqual(sorted(res), ["ofek", "saf", "sahar", "tal", "tavor"])
        for pid, r in res.items():
            before, after = dict(r["before"]), dict(r["after"])
            self.assertEqual(list(before), list(after), pid)   # ті самі кадри в тому самому порядку
            self.assertTrue(before["life"]["ru"], pid)
            for name, alt in before.items():
                self.assertEqual(after[name], alt, f"{pid}/{name}")   # he, en і ru — як були
        self.assertEqual(CATALOG.read_bytes(), before_disk)   # каталог на диску не чіпано

    def test_all_frames_regenerated_keep_ru(self):
        # повний набір кадрів, які є в каталозі, — ru у кожного той самий, що й був
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        names = sorted({im["src"].split("/")[-1].rsplit("-", 1)[0] for p in cat for im in p["images"]})
        for pid, r in add_frames(",".join(names)).items():
            for (name, alt), (name2, alt2) in zip(r["before"], r["after"], strict=True):
                self.assertEqual((name, alt["ru"]), (name2, alt2["ru"]), pid)

    def test_unknown_language_is_merged_not_replaced(self):
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        for p in cat:
            for im in p["images"]:
                if im["src"].split("/")[-1].startswith("life-"):
                    im["alt"]["ar"] = "x-" + p["id"]
        with tempfile.TemporaryDirectory() as d:
            res = add_frames("life", catalog=cat, tmp=Path(d))
        for pid, r in res.items():
            self.assertEqual(dict(r["after"])["life"]["ar"], "x-" + pid)

    def test_old_behaviour_loses_ru(self):
        # доказ, що перевірка падає: стара поведінка (у пам'яті) лишає life без ru
        res = add_frames("life", subs=OLD)
        for pid, r in res.items():
            self.assertNotIn("ru", dict(r["after"])["life"], pid)
            self.assertIn("ru", dict(r["before"])["life"], pid)


if __name__ == "__main__":
    unittest.main()
