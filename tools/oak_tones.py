#!/usr/bin/env python3
"""П'ять тонів дуба з СПРАВЖНІХ фотосканів шпону (CC0, Poly Haven) — альбедо, нормалі, шорсткість і зразки.

    python3 tools/fetch_assets.py                  # скани в assets-src/ (gitignored)
    python3 tools/oak_tones.py                     # усе: текстури тонів + зразки + звіт середніх кольорів
    python3 tools/oak_tones.py --factory фото.jpg light   # фото зразка з фабрики -> site/assets/products/finishes/photo/light.jpg

Кожен тон — це скан реального шпону, на який покладено модель олійного шару (множення на колір плівки й легкий
пігмент), а не перефарбування одного дуба в «пастель». Звідки береться кожен тон і на які палітри олій ми
орієнтувались — docs/ASSETS.md, розділ «Тони дуба». Коротко:

  natural  oak_veneer_01           прозора олія: той самий запечений natural-albedo, що й досі (tools/bake_textures.py)
  light    washed_grey_oak_veneer  справжній вибілений дуб (біла пігментна олія), трохи прибрано рожевий відлив скану
  honey    oak_veneer_01           бурштинова олія: плівка тепла, але жовта — не помаранчева (зелений гасимо менше за синій)
  smoked   black_oak_veneer        фумований (копчений) дуб: темний скан, трохи теплішого коричневого — він не сірий
  black    black_oak_veneer        чорна/графітова олія: темніше в ~2,4 рази, зерно лишається читким

Скани 1 × 1 м (washed_grey, black_oak) мають зерно поперек — повертаємо на 90°, щоб воно йшло вздовж V, як у
oak_veneer_01 (1,83 м). Масштаб: SCALE — у скільки разів щільніше повторювати текстуру тону, щоб 1 м скану на
моделі був 1 м (aluma3d.js TONE_TEX і blender_scene.py читають той самий множник).

Виходи
  renders-master/textures/tone-<id>-albedo-2048.jpg       Blender (gitignored); natural — natural-albedo-2048.jpg
  renders-master/textures/<scan>-{normal,rough}-2048.jpg   нормалі й упакована шорсткість (R = AO, G = rough)
  site/assets/textures/tone-<id>-albedo-1024.jpg           3D-перегляд; карти скану — <scan>-{normal,rough}-1024.jpg
  site/assets/products/finishes/<id>.{webp,jpg}            зразок: шматок ~12 см цього ж альбедо, 240 px
"""
import pathlib, shutil, subprocess, sys
import numpy as np
from PIL import Image, ImageOps

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "assets-src"
MASTER = ROOT / "renders-master" / "textures"
SITE_TEX = ROOT / "site" / "assets" / "textures"
SWATCH = ROOT / "site" / "assets" / "products" / "finishes"
PHOTO = SWATCH / "photo"               # фото зразків з фабрики — їх бере build.py замість скану
LUM = np.array([0.299, 0.587, 0.114])

# скан -> (файл Poly Haven, розмір скану в метрах, повернути на 90°, префікс карт)
SCANS = {
    "oak": ("oak_veneer_01", 1.83, False, "oak"),
    "washed-oak": ("washed_grey_oak_veneer", 1.0, True, "washed-oak"),
    "black-oak": ("black_oak_veneer", 1.0, True, "black-oak"),
}


def natural(a):
    # як grade_natural у bake_textures.py: -14 % насиченості, ледь холодніше — щоб натуральні кадри лишились валідні
    lum = a @ LUM
    a = a * 0.86 + lum[..., None] * 0.14
    return a * np.array([0.99, 0.985, 0.98])


def light(a):
    # біла пігментна олія на вибіленому дубі: скан уже світлий, але плаский — під світлом кадру зерно зникало й
    # дерево читалось як фарбований МДФ. Контраст зерна ×1,5 навколо середнього, на 3 % темніше (це альбедо, не
    # колір на екрані), прибрати рожевий відлив скану (R на 4 % вниз — беж, не пудра)
    m = a.reshape(-1, 3).mean(0)
    a = (m + (a - m) * 1.5) * 0.97
    return a * np.array([0.96, 0.995, 0.99])


def honey(a):
    # бурштинова олія: плівка поглинає синій сильніше за зелений -> золотисто-медовий, не помаранчевий;
    # олія ще й «мокрить» деревину — гамма 1,08 трохи поглиблює зерно
    a = np.power(np.clip(natural(a), 0, 1), 1.08)
    return a * np.array([0.99, 0.91, 0.70])


def smoked(a):
    # фумування: дубильні речовини темніють у коричневий, не в сірий -> скан чорного дуба трохи тепліше
    a = np.power(np.clip(a, 0, 1), 1.06)
    return a * np.array([1.05, 0.95, 0.83])


def black(a):
    # чорна олія: темніше в ~2,4 рази, контраст зерна трохи більший, ніж просте множення (пори забирають пігмент)
    lum = (a @ LUM)[..., None]
    m = float(lum.mean())
    a = a * 0.75 + lum * 0.25
    a = m * 0.42 + (a - m) * 0.62
    return a * np.array([1.0, 0.97, 0.93])


# тон -> (скан, грейд, ім'я альбедо без розміру)
TONES = {
    "natural": ("oak", natural, "natural-albedo"),
    "light": ("washed-oak", light, "tone-light-albedo"),
    "honey": ("oak", honey, "tone-honey-albedo"),
    "smoked": ("black-oak", smoked, "tone-smoked-albedo"),
    "black": ("black-oak", black, "tone-black-albedo"),
}
SWATCH_CM = 12.0


def load(name, mp, rot):
    im = Image.open(SRC / f"{name}_{mp}_2k.jpg")
    return im.transpose(Image.Transpose.ROTATE_90) if rot else im


def save_jpg(im, path, q):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "JPEG", quality=q, optimize=True, progressive=False, subsampling=0 if q >= 90 else 2)
    return path.stat().st_size


def scan_maps(key):
    name, _, rot, pre = SCANS[key]
    nor = load(name, "nor_gl", rot).convert("RGB")
    if rot:
        # поворот на 90° проти годинникової: старий +X дотичної -> +Y, старий +Y -> -X; перекладаємо вектор нормалі
        n = np.asarray(nor).astype(np.int16)
        n = np.dstack([255 - n[..., 1], n[..., 0], n[..., 2]]).astype(np.uint8)
        nor = Image.fromarray(n)
    rough = np.asarray(load(name, "Rough", rot).convert("L"))
    ao = np.asarray(load(name, "AO", rot).convert("L"))
    packed = Image.fromarray(np.dstack([ao, rough, np.zeros_like(rough)]))
    if key == "oak":
        return                                      # карти oak_veneer_01 вже пише bake_textures.py (oak-normal / oak-rough)
    for px, dst, q in ((2048, MASTER, 92), (1024, SITE_TEX, 82)):
        n = nor if px == nor.width else nor.resize((px, px), Image.LANCZOS)
        p = packed if px == packed.width else packed.resize((px, px), Image.LANCZOS)
        save_jpg(n, dst / f"{pre}-normal-{px}.jpg", max(q, 88))
        save_jpg(p, dst / f"{pre}-rough-{px}.jpg", 90 if px == 2048 else 70)


def swatch(im: Image.Image, scan_m: float, tone: str):
    """Зразок — квадрат ~12 см з альбедо тону (не з центру: там у сканах буває найрівніше зерно, беремо третину)."""
    side = round(im.width * SWATCH_CM / (scan_m * 100))
    x0, y0 = im.width // 3, im.height // 3
    crop = im.crop((x0, y0, x0 + side, y0 + side)).resize((240, 240), Image.LANCZOS)
    SWATCH.mkdir(parents=True, exist_ok=True)
    jpg = SWATCH / f"{tone}.jpg"
    crop.save(jpg, "JPEG", quality=84, optimize=True, progressive=False)
    subprocess.run(["convert", str(jpg), "-strip", "-quality", "82", "-define", "webp:method=6",
                    str(SWATCH / f"{tone}.webp")], check=True)
    for old in (SWATCH / f"{tone}.avif",):          # зразок іде як <img> webp/jpg; старі avif з three.js-дощечки не потрібні
        old.unlink(missing_ok=True)
    return crop


def bake():
    for key in SCANS:
        scan_maps(key)
    report = []
    for tone, (key, fn, stem) in TONES.items():
        name, scan_m, rot, _ = SCANS[key]
        if tone == "natural":
            im = Image.open(MASTER / "natural-albedo-2048.jpg").convert("RGB")
        else:
            diff = np.asarray(load(name, "Diffuse", rot).convert("RGB")).astype(np.float32) / 255.0
            im = Image.fromarray((np.clip(fn(diff), 0, 1) * 255 + 0.5).astype(np.uint8))
            save_jpg(im, MASTER / f"{stem}-2048.jpg", 92)
            save_jpg(im.resize((1024, 1024), Image.LANCZOS), SITE_TEX / f"{stem}-1024.jpg", 82)
        sw = swatch(im, scan_m, tone)
        m = np.asarray(im).reshape(-1, 3).mean(0)
        ms = np.asarray(sw).reshape(-1, 3).mean(0)
        report.append((tone, name, "#%02X%02X%02X" % tuple(int(round(v)) for v in m),
                       "#%02X%02X%02X" % tuple(int(round(v)) for v in ms)))
    print(f"{'тон':8s} {'скан':24s} {'середнє альбедо':16s} зразок")
    for r in report:
        print(f"{r[0]:8s} {r[1]:24s} {r[2]:16s} {r[3]}")


def factory(src: str, tone: str):
    """Фото зразка з фабрики: квадрат з центру, 240 px, jpg ~10 КБ. Після цього build.py бере його замість скану
    і знімає з групи зразків позначку «הדמיה» (коли фото є для всіх тонів товару)."""
    if tone not in TONES:
        raise SystemExit(f"невідомий тон {tone!r}: {', '.join(TONES)}")
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
    out = PHOTO / f"{tone}.jpg"
    PHOTO.mkdir(parents=True, exist_ok=True)
    im.resize((240, 240), Image.LANCZOS).save(out, "JPEG", quality=84, optimize=True, progressive=False)
    print(f"{out.relative_to(ROOT)}: {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--factory":
        factory(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 1:
        if not shutil.which("convert"):
            raise SystemExit("потрібен ImageMagick convert (webp зразків)")
        bake()
    else:
        raise SystemExit(__doc__)
