# Source assets (not in git — re-download with `python tools/fetch_assets.py`)

All files are CC0 from Poly Haven (https://polyhaven.com/license).

| File | Asset | URL |
|---|---|---|
| oak_veneer_01_{Diffuse,nor_gl,Rough,AO}_2k.jpg | Oak Veneer 01 (PBR, 2k JPG) | https://polyhaven.com/a/oak_veneer_01 |
| wood_table_001_{Diffuse,nor_gl,Rough,AO}_2k.jpg | Wood Table 001 (PBR, 2k JPG) | https://polyhaven.com/a/wood_table_001 |
| washed_grey_oak_veneer_{Diffuse,nor_gl,Rough,AO}_2k.jpg | Washed Grey Oak Veneer (PBR, 2k JPG) — light tone | https://polyhaven.com/a/washed_grey_oak_veneer |
| black_oak_veneer_{Diffuse,nor_gl,Rough,AO}_2k.jpg | Black Oak Veneer (PBR, 2k JPG) — smoked and black tones | https://polyhaven.com/a/black_oak_veneer |
| tex/Tiles110/*, hdri/bloem_olive_house_2k.hdr, tex/hessian_380/*, models/{potted_plant_02,potted_plant_04,wicker_basket_02} | home frame: terrazzo tiles (ambientCG, CC0), street view in the window, jute rug, plants — `python3 tools/fetch_cc0.py` | https://ambientcg.com/view?id=Tiles110 · https://polyhaven.com/a/bloem_olive_house · https://polyhaven.com/a/hessian_380 |
| brown_photostudio_02_1k.hdr | Brown Photostudio 02 (HDRI, 1k) | https://polyhaven.com/a/brown_photostudio_02 |

API: `https://api.polyhaven.com/files/<asset>` → `[map]["2k"]["jpg"]["url"]`, `["hdri"]["1k"]["hdr"]["url"]`.
Other oak veneers available on Poly Haven: oak_veneer_02..05, white_oak_veneer, mocha_oak_veneer, black_oak_veneer,
grey_oak_veneer_01/02. Tones are built from these scans by `tools/oak_tones.py` (see docs/ASSETS.md, «Тони дуба»).
