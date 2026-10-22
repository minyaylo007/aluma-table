#!/usr/bin/env python3
"""Завантажує CC0-ассети фотореальної сцени (Poly Haven, ambientCG) у окрему теку поза git.

    python3 -I tools/fetch_cc0.py              # усе з ASSETS
    python3 -I tools/fetch_cc0.py rough_linen  # один ассет

Тека — $ALUMA_CC0 або /opt/ihor/aluma-table/tmp/cc0 (не в git, не в публікацію). Джерела й ліцензія кожного
файла — docs/ASSETS.md. ambientCG (https://ambientcg.com/) — теж CC0. Чужих фото виробів тут немає й не буде: лише матеріали, HDRI і предмети декору.
"""
import io, json, os, pathlib, sys, urllib.request, zipfile

DST = pathlib.Path(os.environ.get("ALUMA_CC0", "/opt/ihor/aluma-table/tmp/cc0"))
UA = {"User-Agent": "Mozilla/5.0 (aluma-fetch-cc0)"}
API = "https://api.polyhaven.com/files/{}"
MAPS = ("Diffuse", "nor_gl", "Rough", "AO", "Displacement")
# ambientCG: архів <id>_2K-JPG.zip; карти перейменовуємо в ту саму розкладку, що Poly Haven (tex_material у Blender)
ACG = "https://ambientcg.com/get?file={}_{}-JPG.zip"
ACG_MAPS = {"Color": "Diffuse", "NormalGL": "nor_gl", "Roughness": "Rough", "AmbientOcclusion": "AO",
            "Displacement": "Displacement"}

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
    # жилий кадр «home» (21.10): ізраїльська квартира — плитка-терацо «балата», вікно з видом, рослини, текстиль
    "Tiles110": ("acg", "2K"),                    # ambientCG: бежева плитка-терацо з швами — підлога
    "bloem_olive_house": ("hdris", "2k"),         # вид за вікном: оливкове дерево, будинок, сонце (лише для камери)
    "hessian_380": ("textures", "2k"),            # джутовий килим
    "potted_plant_02": ("models", "2k"),          # рослина в горщику на підлозі
    "potted_plant_04": ("models", "2k"),          # сукулент на підвіконні
    "wicker_basket_02": ("models", "2k"),         # плетений кошик
    # фотореальний прохід (22.10): кам'яна підлога студії, деревце в теракоті, лимони
    "large_floor_tiles_02": ("textures", "2k"),   # підлога студії: великі кам'яні плити (перефарбовуються у вапняк)
    "potted_plant_01": ("models", "2k"),          # деревце в теракотовому горщику
    "lemon": ("models", "2k"),                    # лимони в мисці
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
    if kind == "acg":
        if (DST / "tex" / name / "Diffuse.jpg").exists():
            return
        z = zipfile.ZipFile(io.BytesIO(get(ACG.format(name, res))))
        for member in z.namelist():
            stem = member.rsplit(".", 1)[0]
            for key, out in ACG_MAPS.items():
                if stem.endswith("_" + key) and member.endswith(".jpg"):
                    path = DST / "tex" / name / f"{out}.jpg"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(z.read(member))
        print(f"{name}: ok")
        return
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
