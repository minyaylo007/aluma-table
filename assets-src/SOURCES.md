# Source assets (not in git — re-download with `python tools/fetch_assets.py`)

All files are CC0 from Poly Haven (https://polyhaven.com/license).

| File | Asset | URL |
|---|---|---|
| oak_veneer_01_{Diffuse,nor_gl,Rough,AO}_2k.jpg | Oak Veneer 01 (PBR, 2k JPG) | https://polyhaven.com/a/oak_veneer_01 |
| wood_table_001_{Diffuse,nor_gl,Rough,AO}_2k.jpg | Wood Table 001 (PBR, 2k JPG) | https://polyhaven.com/a/wood_table_001 |
| brown_photostudio_02_1k.hdr | Brown Photostudio 02 (HDRI, 1k) | https://polyhaven.com/a/brown_photostudio_02 |

API: `https://api.polyhaven.com/files/<asset>` → `[map]["2k"]["jpg"]["url"]`, `["hdri"]["1k"]["hdr"]["url"]`.
Other oak veneers available on Poly Haven: oak_veneer_02..05, white_oak_veneer, mocha_oak_veneer, black_oak_veneer,
grey_oak_veneer_01/02, washed_grey_oak_veneer (useful for the smoked / whitewashed tones).
