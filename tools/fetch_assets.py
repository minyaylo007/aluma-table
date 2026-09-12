#!/usr/bin/env python3
"""Re-download the CC0 source textures and HDRI listed in assets-src/SOURCES.md (Poly Haven).

    python tools/fetch_assets.py                 # everything in ASSETS
    python tools/fetch_assets.py oak_veneer_01   # one asset

Files land in assets-src/ (gitignored). Nothing here is deployed as-is; the render
pipeline (tools/render3d.*) and the viewer texture bake read from this folder.
"""
import json, pathlib, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DST = ROOT / "assets-src"
UA = {"User-Agent": "Mozilla/5.0 (aluma-fetch-assets)"}
API = "https://api.polyhaven.com/files/{}"

# asset -> (kind, resolution, maps)   kind: "textures" | "hdris"
ASSETS = {
    "oak_veneer_01": ("textures", "2k", ("Diffuse", "nor_gl", "Rough", "AO")),
    "wood_table_001": ("textures", "2k", ("Diffuse", "nor_gl", "Rough", "AO")),
    "white_oak_veneer": ("textures", "2k", ("Diffuse", "nor_gl", "Rough", "AO")),
    "mocha_oak_veneer": ("textures", "2k", ("Diffuse", "nor_gl", "Rough", "AO")),
    "brown_photostudio_02": ("hdris", "1k", ()),
}


def get(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()


def fetch(name: str) -> None:
    kind, res, maps = ASSETS[name]
    files = json.loads(get(API.format(name)))
    DST.mkdir(exist_ok=True)
    if kind == "hdris":
        out = DST / f"{name}_{res}.hdr"
        if not out.exists():
            out.write_bytes(get(files["hdri"][res]["hdr"]["url"]))
        print(f"{out.name}: {out.stat().st_size // 1024} KB")
        return
    for m in maps:
        node = files.get(m, {}).get(res, {}).get("jpg")
        if not node:
            print(f"{name}: no {m} {res} jpg, skipped")
            continue
        out = DST / f"{name}_{m}_{res}.jpg"
        if not out.exists():
            out.write_bytes(get(node["url"]))
        print(f"{out.name}: {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    names = sys.argv[1:] or list(ASSETS)
    for n in names:
        fetch(n)
