#!/usr/bin/env python3
"""Кадри «наступного видання» (№22): два трендові варіанти TAVOR на перевірку попиту рекламою.

    python3 tools/render_next.py                        # усе: 4 кадри × 2 варіанти, потім стиснення
    python3 tools/render_next.py --preview              # звірка ракурсів: ½ сторони, 12 семплів, нічого не пише в site/
    python3 tools/render_next.py fluted --only life     # один варіант, один кадр
    python3 tools/render_next.py --encode               # не рендерити, лише стиснути наявні майстри

Геометрія — tools/blender_scene.py --next fluted|oval (у 3D на сайті цих виробів немає), сцена й світло — ті самі, що в
кадрів TAVOR каталогу (LIFE / HOME у tools/render_products.js), тож варіанти й TAVOR порівнюються в одній кімнаті.
Майстри PNG — renders-master/next/ (gitignored). Виходи:
  site/assets/next/<варіант>/<кадр>-{800,1600}.{webp,avif}  — сторінки /p/tavor-fluted/, /p/tavor-oval/
  docs/creatives/stage2-design/<варіант>-1080x1080.jpg, -1080x1350.jpg — креативи (без тексту на кадрі)
Запускати в рамці §8 через heavy: heavy --label aluma -- python3 tools/render_next.py
"""
import json, os, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MASTER = ROOT / "renders-master" / "next"
SITE = ROOT / "site" / "assets" / "next"
ADS = ROOT / "docs" / "creatives" / "stage2-design"
BLENDER = os.environ.get("ALUMA_BLENDER", "/opt/ihor/aluma-table/tmp/blender/blender-4.5.14-linux-x64/blender")
VARIANTS = {"fluted": "tavor-fluted", "oval": "tavor-oval"}

# та сама квартира й камера «як фото», що LIFE.tavor у render_products.js
HOME_LIGHT = {"room": "home", "sun": 7.0, "window": 150, "hdri_strength": 0.16, "exposure": 1.5, "fstop": 2.2}
LIFE = {**HOME_LIGHT, "end_chair": True, "eye": 1.55, "lens": 45, "margin": 0.03, "az": 32, "target_z": 0.55, "book": True}
# чистий фронтальний: студія, без стільців і декору — видно саму форму опори
FRONT = {"az": 0, "eye": 0.95, "lens": 50, "margin": 0.1, "sun": 7.0, "window": 200, "hdri_strength": 0.2, "fstop": 4.0,
         "exposure": 1.5, "target_z": 0.4}
# квадрат і 4:5 для реклами: та сама життєва сцена, камера трохи ближче й нижче, стіл займає кадр
AD = {**LIFE, "eye": 1.35, "lens": 40, "margin": 0.06, "az": 34, "target_z": 0.45}
SHOTS = {
    "life": (1600, 1068, "dining", LIFE),
    "front": (1600, 1068, "none", FRONT),
    "ad-1x1": (1080, 1080, "dining", AD),
    "ad-4x5": (1080, 1350, "dining", AD),
}


def blender(variant, shot, out, preview, samples):
    w, h, decor, cam = SHOTS[shot]
    if preview:
        w, h, samples = w // 2, h // 2, 12
    cmd = ["timeout", "180m", "systemd-run", "--user", "--scope", "-q", "--slice=app-ihor\\x2dconductor.slice",
           "-p", "MemoryMax=4G", "nice", "-n", "15", BLENDER, "-b", "--factory-startup",
           "-P", str(ROOT / "tools" / "blender_scene.py"), "--",
           "--next", variant, "--out", str(out), "--w", str(w), "--h", str(h), "--samples", str(samples),
           "--threads", os.environ.get("HEAVY_CPUS", "4"), "--decor", decor, "--cam", json.dumps(cam)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env={**os.environ, "TMPDIR": "/tmp"})
    if r.returncode or "ALUMA_RENDER_OK" not in r.stdout:
        sys.exit(f"blender {variant}/{shot}\n{r.stderr[-2000:]}{r.stdout[-2000:]}")


def run(*a):
    subprocess.run(a, check=True, capture_output=True)


def encode(variant):
    src = MASTER / variant
    dst = SITE / VARIANTS[variant]
    dst.mkdir(parents=True, exist_ok=True)
    ADS.mkdir(parents=True, exist_ok=True)
    for shot in ("life", "front"):
        png = src / f"{shot}.png"
        for width in (800, 1600):
            base = dst / f"{shot}-{width}"
            run("convert", str(png), "-resize", f"{width}x", "-strip", "-quality", "80", "-define", "webp:method=6",
                f"{base}.webp")
            run("convert", str(png), "-resize", f"{width}x", "-strip", "-quality", "60", f"{base}.avif")
    for shot, name in (("ad-1x1", "1080x1080"), ("ad-4x5", "1080x1350")):
        run("convert", str(src / f"{shot}.png"), "-strip", "-sampling-factor", "4:2:0", "-quality", "88",
            str(ADS / f"{VARIANTS[variant]}-{name}.jpg"))


def main():
    args = sys.argv[1:]
    preview, only_encode = "--preview" in args, "--encode" in args
    only = args[args.index("--only") + 1].split(",") if "--only" in args else list(SHOTS)
    samples = int(next((a.split("=")[1] for a in args if a.startswith("--samples=")), 192))
    variants = [a for a in args if a in VARIANTS] or list(VARIANTS)
    for v in variants:
        (MASTER / v).mkdir(parents=True, exist_ok=True)
        if not only_encode:
            for shot in only:
                out = MASTER / v / (f"preview-{shot}.png" if preview else f"{shot}.png")
                blender(v, shot, out, preview, samples)
                print(f"{v}/{shot} -> {out.relative_to(ROOT)}", flush=True)
        if not preview and all((MASTER / v / f"{s}.png").exists() for s in SHOTS):
            encode(v)
            print(f"{v}: стиснуто -> {(SITE / VARIANTS[v]).relative_to(ROOT)}, {ADS.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
