#!/usr/bin/env python3
"""Завантажує CC0-ассети фотореальної сцени (Poly Haven) у окрему теку поза git.

    python3 -I tools/fetch_cc0.py              # усе з ASSETS
    python3 -I tools/fetch_cc0.py rough_linen  # один ассет

Тека — $ALUMA_CC0 або /opt/ihor/aluma-table/tmp/cc0 (не в git, не в публікацію). Джерела й ліцензія кожного
файла — docs/ASSETS.md. Чужих фото виробів тут немає й не буде: лише матеріали, HDRI і предмети декору.
"""
import json, os, pathlib, sys, urllib.request

DST = pathlib.Path(os.environ.get("ALUMA_CC0", "/opt/ihor/aluma-table/tmp/cc0"))
UA = {"User-Agent": "Mozilla/5.0 (aluma-fetch-cc0)"}
API = "https://api.polyhaven.com/files/{}"
MAPS = ("Diffuse", "nor_gl", "Rough", "AO", "Displacement")

# ассет -> (вид, роздільність)   вид: textures | hdris | models
ASSETS = {
    "oak_veneer_01": ("textures", "4k"),          # дуб виробу — той самий, що в 3D-перегляді
    "plastered_wall_04": ("textures", "2k"),      # стіна: гладка штукатурка
    "smooth_concrete_floor": ("textures", "2k"),  # підлога: мікроцемент (перефарбовується в сцені)
    "rough_linen": ("textures", "2k"),            # лляна доріжка на столі
    "photo_studio_loft_hall": ("hdris", "2k"),    # денне світло з великих вікон
    "lebombo": ("hdris", "2k"),
    "ceramic_vase_01": ("models", "2k"),
    "ceramic_vase_02": ("models", "2k"),
    "dry_branches_medium_01": ("models", "2k"),
    "wooden_cutting_board": ("models", "2k"),
    "food_pears_asian_01": ("models", "2k"),
    "wooden_bowl_02": ("models", "2k"),
}


def get(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read()


def save(path: pathlib.Path, url: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(get(url))
    tmp.rename(path)


def fetch(name: str) -> None:
    kind, res = ASSETS[name]
    files = json.loads(get(API.format(name)))
    if kind == "hdris":
        save(DST / "hdri" / f"{name}_{res}.hdr", files["hdri"][res]["hdr"]["url"])
    elif kind == "textures":
        for m in MAPS:
            node = files.get(m, {}).get(res, {}).get("jpg") or files.get(m, {}).get(res, {}).get("png")
            if node:
                save(DST / "tex" / name / f"{m}.{node['url'].rsplit('.', 1)[1]}", node["url"])
    else:
        node = files["gltf"][res]["gltf"]
        base = DST / "models" / name
        save(base / f"{name}.gltf", node["url"])
        for rel, inc in node.get("include", {}).items():
            save(base / rel, inc["url"])
    print(f"{name}: ok")


if __name__ == "__main__":
    for n in sys.argv[1:] or list(ASSETS):
        fetch(n)
