# Lighthouse — 2026-09-12, бойовий `table.central-aparts.store` з ace-main

Перший замір сайту **після переїзду** з AWS (CloudFront + S3 + Lambda) на цю машину
(Caddy + статика з `/srv/aluma` + gunicorn `127.0.0.1:8005`). Це крок 5 плану переїзду —
третя з трьох перевірок проти коробки, поряд із тестовою заявкою в Telegram (робить
власник) і `tests/smoke.spec.js` (`docs/CUTOVER-CHECKLIST.md`, крок 5).

**Це ЗАМІР, а не правка.** Нічого за його результатами не чинилося.

Тільки `GET`. Жодна форма не відправлялась, у базу з цього прогону не пішло нічого.

## Оцінки — 100/100/100/100 на всіх чотирьох прогонах

| Сторінка | Режим | Performance | Accessibility | Best Practices | SEO |
|---|---|---:|---:|---:|---:|
| `/` (іврит, RTL) | mobile | **100** | **100** | **100** | **100** |
| `/` (іврит, RTL) | desktop | **100** | **100** | **100** | **100** |
| `/en/` (англійська, LTR) | mobile | **100** | **100** | **100** | **100** |
| `/en/` (англійська, LTR) | desktop | **100** | **100** | **100** | **100** |

Метрики (те, з чого складається Performance):

| Сторінка / режим | FCP | LCP | TBT | CLS | Speed Index |
|---|---:|---:|---:|---:|---:|
| `/` mobile | 1.0 с | 1.1 с | 40 мс | 0 | 1.0 с |
| `/` desktop | 0.3 с | 0.3 с | 0 мс | 0 | 0.3 с |
| `/en/` mobile | 0.9 с | 1.2 с | 0 мс | 0 | 0.9 с |
| `/en/` desktop | 0.3 с | 0.3 с | 0 мс | 0 | 0.3 с |

`CLS = 0` на всіх чотирьох — сторінка не «стрибає»; розміри картинок проставлені в розмітці.

## Топ зауважень

Провалених аудитів з ненульовою вагою немає — **жодне зауваження нижче на оцінку не впливає**,
усі вони мають вагу 0 (Lighthouse показує їх довідково). Порядок — за розміром виграшу.

| # | Аудит | Що каже | Де | Вага |
|---|---|---|---|---:|
| 1 | `image-delivery-insight` | можна зекономити ≈45 КБ на картинках | тільки mobile, обидві мови | 0 |
| 2 | `unminified-javascript` | можна зекономити ≈3 КБ — `app-next.js` віддається без мініфікації | усі чотири | 0 |
| 3 | `render-blocking-insight` | ≈10 мс на ресурсах, що блокують промальовку | усі чотири | 0 |
| 4 | `network-dependency-tree-insight` | довжина ланцюжка критичних запитів (довідково, економії не названо) | усі чотири | 0 |
| 5 | `max-potential-fid` | 190 мс найгіршої потенційної затримки на дію | тільки `/` mobile | 0 |

Повний перелік з деталями — `summary.json`, поле `findings`.

## Що лежить поруч

- `summary.json` — **у git**: оцінки, метрики й усі зауваження чотирьох прогонів в одному файлі.
- `*.report.report.json` / `*.report.report.html` — сирі звіти Lighthouse, **у git НЕ йдуть**
  (`.gitignore`): по ~650 КБ на прогін, і перезняти їх дешевше, ніж возити в репозиторії.
  Якщо їх треба подивитись — прогнати команду нижче ще раз.

## Як повторити

З кореня робочої копії (`~/repos/aluma-table` або її worktree). Lighthouse і chromium — свої,
не глобальні: пакет із `node_modules` цього дерева, браузер — із `PLAYWRIGHT_BROWSERS_PATH`.

```bash
npm ci                                        # lighthouse 12.8.2 з package.json
OUT=docs/lighthouse/$(date -u +%F)
mkdir -p "$OUT"
export CHROME_PATH=/opt/ihor/aluma-table/ms-playwright/chromium-1234/chrome-linux64/chrome
for page in 'he:/' 'en:/en/'; do
  slug=${page%%:*}; path=${page#*:}
  for preset in mobile desktop; do
    [ "$preset" = desktop ] && extra=--preset=desktop || extra=
    node_modules/.bin/lighthouse "https://table.central-aparts.store$path" \
      --quiet --chrome-flags='--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage' \
      $extra --only-categories=performance,accessibility,best-practices,seo \
      --output=json --output=html --output-path="$OUT/$slug-$preset.report"
  done
done
```

> ⚠️ **Тільки бойова адреса і тільки GET.** Lighthouse форм не відправляє, тож заявок він не
> створює. Проти коробки напряму (`127.0.0.1:8007`) міряти сенсу немає: там немає ні Caddy з
> його `encode`/кешем, ні TLS, і число вийде не про той сайт, який бачить гість.

Заміряно: Lighthouse 12.8.2, chromium 1234 (Playwright 1.62.1), headless, з ace-main.
Точний час кожного прогону — `fetchTime` у `summary.json`.
