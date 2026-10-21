# Зразки тонів дуба

`<тон>.webp` / `<тон>.jpg` (240 px) — шматок ~12 см **справжнього фотоскану шпону** з олійним тоном поверх.
Згенеровано `tools/oak_tones.py` з CC0-сканів Poly Haven (автор сканів — Jenelle van Heerden, ліцензія CC0 1.0,
https://polyhaven.com/license):

| Тон | Скан | Сторінка |
|---|---|---|
| natural, honey | Oak Veneer 01 | https://polyhaven.com/a/oak_veneer_01 |
| light | Washed Grey Oak Veneer | https://polyhaven.com/a/washed_grey_oak_veneer |
| smoked, black | Black Oak Veneer | https://polyhaven.com/a/black_oak_veneer |

Це візуалізація, а не фото нашого зразка, тому на сайті біля зразків стоїть «הדמיה». Як підібрано кожен тон —
`docs/ASSETS.md`, розділ «Тони дуба».

## Фото зразків з фабрики

Покладіть фото в `photo/<тон>.jpg` (`natural`, `light`, `honey`, `smoked`, `black`) командою:

    python3 tools/oak_tones.py --factory шлях/до/фото.jpg honey

Скрипт виріже квадрат з центру й зменшить до 240 px. `build.py` (`FINISH_PHOTOS`) бере фото замість скану;
коли фото є для всіх тонів товару, підпис «הדמיה» біля зразків зникає. Файл більше 60 КБ збірка не пропустить.
