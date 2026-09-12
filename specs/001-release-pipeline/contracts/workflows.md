# Contract: workflows GitHub Actions [флот; команды проверок — ALUMA]

Все actions закреплены по мажорной версии: `actions/checkout@v6`, `actions/setup-node@v6` (Node 24),
`actions/setup-python@v6` (подтвердить первым прогоном). Права по умолчанию — `contents: read`.

## `ci.yml` — проверки

- **Триггеры:** `push` (все ветки, кроме `master`), `pull_request` (в `master`), `workflow_call`.
- **concurrency:** `ci-${{ github.workflow }}-${{ github.ref }}`, `cancel-in-progress: ${{ github.ref != 'refs/heads/master' }}`.
- **Задания (имена = обязательные проверки ruleset `master`):**

| Задание | Шаги [ALUMA] |
|---|---|
| `lint` | `pip install -r requirements-lint.txt`; `ruff check .`; `node --check` для `site/assets/*.js`, `tests/*.js` |
| `test (3.12)`, `test (3.13)` | `pip install -r api/requirements.txt -r tests/requirements.txt`; `python -m unittest discover -s tests -t . -v` |
| `build` | `python build.py` (код 0, без Pillow); вторая сборка → те же суммы `dist/` |
| `browser` | `npm ci`; `npx playwright install --with-deps chromium`; `python build.py`; `PREVIEW_PORT=8007 npx playwright test --config playwright.local.config.js` |

`tests/smoke.spec.js` не запускается (пишет в хранилище).

## `release.yml` — версия

- **Триггер:** `push` в `master`.
- **Задания:** `checks` → `uses: ./.github/workflows/ci.yml`; `release` (`needs: checks`, `permissions: contents: write,
  pull-requests: read`, `concurrency: release-production`, без отмены):
  1. checkout с тегами; `python scripts/next_version.py --tags <список> --labels <метки PR коммита>` → `vX.Y.Z`;
  2. `python scripts/release_build.py --tag vX.Y.Z --sha $GITHUB_SHA --out out/`;
  3. тег на `$GITHUB_SHA`, push тега; `gh release create vX.Y.Z out/* --notes <изменения>`;
  4. выход: `tag`.
  `deploy` (`needs: release`) → `uses: ./.github/workflows/deploy.yml` с `tag`.
- Если `checks` красные — ни тега, ни релиза, ни деплоя.
- **Выключатель выпуска [флот]** (решение дирижёра 2026-09-11; про новые версии, не про откат): задание `release`
  (а за ним и `deploy` из `release.yml`) выполняется
  только при переменной репозитория `RELEASES_ENABLED` = `true` — `if: vars.RELEASES_ENABLED == 'true'`. Без неё на
  каждом push в master идут только проверки (`checks`), а `release`/`deploy` в Actions видны как skipped: ни тега, ни
  релиза, ни деплоя. Назначение — остановить выпуск версий без правки кода (авария, пауза, до включения правила
  тегов). Переключает тот, у кого есть право на настройки репозитория: `gh variable set RELEASES_ENABLED --body true`
  / `gh variable delete RELEASES_ENABLED`. В ALUMA переменная включается пунктом Phase 3 вместе с правилом тегов.

## `deploy.yml` — деплой (вызывается)

- **Триггер:** `workflow_call`, вход `tag` (строка `vX.Y.Z`).
- **Задание `deploy`:** `environment: {name: production, url: <сайт>}`, `permissions: contents: write`,
  `concurrency: {group: deploy-production, cancel-in-progress: true}`, `timeout-minutes: 20`:
  1. проверить: тег существует, у релиза есть `aluma-<tag>.tar.gz` и `SHA256SUMS` — иначе провал;
  2. `git push --force origin <sha тега>:refs/heads/production`;
  3. раз в 20 с, до 15 мин: `curl -fsS --max-time 10 "$ALUMA_HEALTH_URL"` → успех, когда `ok` и `version` = тег и
     `git_sha` = sha; иначе провал по таймауту.
- Статус деплоя ставит GitHub по итогу задания (data-model.md «Деплой в GitHub»).

## `rollback.yml` — откат / деплой любой версии

- **Триггер:** `workflow_dispatch`, вход `version` (обязательный, шаблон `^v\d+\.\d+\.\d+$`).
- **Задания:** `validate` (тег есть, файлы релиза есть — иначе отказ до деплоя) → `deploy` (`uses: deploy.yml`).
- Запускать может любой с правом записи; правило окружения пропускает только запуск из `master`.
- **Откат доступен всегда, когда агент установлен, даже при выключенном выпуске** (решение дирижёра 2026-09-11):
  выключатель выпуска `rollback.yml` не останавливает — его выключают как раз при плохой версии, и откат в этот момент
  должен работать. Выпуск и откат останавливаются независимо.
- **Нет ссылки `refs/heads/production` — откатывать нечего:** `validate` завершается успешно с сообщением
  «откатывать нечего», `deploy` не запускается — ни сдвига ссылки, ни окружения, ни других правок репозитория.
  Ссылку создаёт первый деплой после публикации репозитория (фаза 3) и установки агента (T040).
- Порядок проверок `validate`: формат `vX.Y.Z` → есть ли `refs/heads/production` → тег → оба файла релиза.

## Переменные и секреты

| Имя | Где | Значение |
|---|---|---|
| `ALUMA_HEALTH_URL` | переменная окружения `production` | см. data-model.md «Окружение production» |
| `RELEASES_ENABLED` | переменная репозитория | `true` — выпуск версий включён; нет или иное значение — выключен (только проверки) |
| секреты | — | не нужны; GitHub Secrets пусты (так и записать в DELIVERY.md) |
