# Implementation Plan: Выпуск и деплой ALUMA через GitHub

**Branch**: `001-release-pipeline` (папка фичи) | **Date**: 2026-09-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-release-pipeline/spec.md`

## Summary

После чистой проверки всей истории репозиторий становится публичным и получает правила: master только через PR с
зелёными проверками (линтер, тесты на Python 3.12/3.13, сборка, мокнутые браузерные тесты) и авто-merge. Каждое
слияние в master публикует версию SemVer `vX.Y.Z` (с `v0.5.0`): тег, релиз с воспроизводимым архивом и `SHA256SUMS`.
Задание `deploy` (окружение `production`) двигает git-ссылку `production` на коммит тега и ждёт, пока публичный health
покажет номер и sha. Агент на ace-main — пользовательский таймер раз в минуту, без токенов и без REST API: анонимно
читает ссылку протоколом git, качает артефакт по прямой ссылке, сверяет суммы, переключает каталог версии,
перезапускает `ihor-aluma-api`, проверяет health локально, публикует статику в `/srv/aluma`; при провале
возвращает прежнюю версию. Откат — `rollback.yml` с номером версии. Процесс — в `docs/DELIVERY.md`. Решения и
замеры — [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (машина, агент — системный `python3`), Python 3.13 (Lambda; в CI — матрица
3.12/3.13); YAML GitHub Actions; Node 24 (Playwright в CI).

**Primary Dependencies**: без новых зависимостей рантайма. Новые для разработки: `ruff` (закреплённый,
`requirements-lint.txt`); разовый инструмент проверки истории `gitleaks` (закреплённый, вне репозитория). Тестовые
`werkzeug`, `boto3`, `moto` переезжают из строки `ci.yml` в `tests/requirements.txt` с закреплёнными версиями.
Агент — только stdlib. Actions — `checkout@v6`, `setup-node@v6`, `setup-python@v6`.

**Storage**: живые данные (`data/aluma.db`) не меняются; состояние агента — JSON-файлы в
`/opt/ihor/aluma-table/state/` (0700); версии — каталоги `releases/<tag>/`.

**Testing**: `python -m unittest discover -s tests -t .` (stdlib unittest, без сети: git/HTTP/systemctl подменены);
Playwright `tests/redesign.spec.js`; живые проверки — quickstart.md и последняя фаза tasks.md.

**Target Platform**: GitHub Actions (`ubuntu-latest`, публичный репозиторий) + ace-main (Ubuntu, systemd 255,
менеджер пользователя `ihor`, linger включён).

**Project Type**: конвейер поставки + агент для существующего веб-сервиса (статика + WSGI API).

**Performance Goals**: merge → health новой версии ≤ 20 мин (SC-001); откат ≤ 10 мин (SC-002); начало установки
≤ 2 мин после сдвига ссылки (FR-011); перерыв API ≤ 30 с (SC-005).

**Constraints**: агент не слушает порты, без sudo, без Caddy, без токенов и без запросов к `api.github.com`; всё под
`ihor` пользовательскими юнитами; только пути ALUMA; gunicorn — `127.0.0.1:8005` с `--no-control-socket` (как
сейчас); Playwright в CI — порт 8007; секреты и данные заявок не печатаются.

**Scale/Scope**: единицы релизов в день; одна машина; 10 хранимых версий; флот — до 3 агентов на одном IP.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Проверено по `.specify/memory/constitution.md` (1.0.0) с учётом constitution-base 2.1.0, п.VI (сообщено дирижёром):
п.VI конституции проекта и абзац CLAUDE.md §9 о выкате приводятся к базе задачей T008 — первой в фазе проверок,
до появления любого конвейера выката (FR-028); релиз и деплой (T029 и далее) — только после её коммита.

| Принцип | Как план соблюдает | Итог |
|---|---|---|
| I. Тесты до пуша | в каждой фазе с изменением поведения — тесты (tasks.md); CI требует зелёных `lint`/`test`/`build`/`browser` до слияния; `build.py` проверяется в `build` | ✅ |
| II. Секреты и ПД | агент без токенов и без чтения `aluma.env`/`data/`; артефакт без секретов (запрет путей в `release_build.py`); проверка всей истории до публикации без печати значений; GitHub Secrets пусты; примеры в спеках синтетические | ✅ |
| III. Без новых AWS-зависимостей | конвейер и агент не используют AWS; `boto3` в тестах — уже существующая зависимость; AWS-стек не трогается | ✅ |
| IV. Сеть | агент не слушает ничего; gunicorn без изменений (`127.0.0.1:8005`, `--no-control-socket`); превью Playwright — 8007; Caddy не запускается/не останавливается/не перезагружается, порт 2019 не трогается | ✅ |
| V. Чужое не трогать | агент работает только с `/opt/ihor/aluma-table`, `/srv/aluma`, `~/.config/aluma/` (не читая `aluma.env`), своими юнитами; перезапуск только `ihor-aluma-api` через `systemctl --user`; процессы — по юниту/PID | ✅ |
| VI. Git | коммиты явным списком, без force-push в master (правило репозитория это закрепляет); выкат — по constitution-base 2.1.0: автодеплой после попадания в master разрешён, т. к. CI зелёный (релиз зависит от `checks`) и откат проверяется на деле (последняя фаза); выкат вне конвейера — только с «да» владельца: единственный такой шаг — первая установка на машину (T040), она
стоит за «да» владельца через дирижёра. Force-push есть только в служебную ветку `production` встроенным токеном конвейера — это не master и не история кода | ✅ |
| VII. Простота и границы | делается ровно spec.md; новые зависимость, инструмент и сервис — с обоснованием ниже; согласие дирижёра: линтер — его требование, pull-агент — одобрен им и главным дирижёром | ✅ (см. Complexity Tracking) |
| Критичные потоки | заявка, уведомление, вход в `/admin` и cookie, хранилище, EDGE_SECRET — не меняются; в хендлере — только тело health (+`git_sha`) и подпись версии в `/admin` | ✅ |

**Повторная проверка после Phase 1:** контракты и модель данных не добавили ни портов, ни AWS, ни чтения секретов;
агент — stdlib; нарушений нет.

## Project Structure

### Documentation (this feature)

```text
specs/001-release-pipeline/
├── spec.md
├── plan.md                  # этот файл
├── research.md              # решения и замеры, [флот]/[ALUMA]
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── health.md
│   ├── release-artifact.md
│   ├── production-ref.md
│   ├── agent-cli.md
│   ├── workflows.md
│   └── secret-scan.md
├── checklists/requirements.md
├── secret-scan-report.md    # создаёт исполнитель в фазе 1 (без значений)
├── verification.md          # живые доказательства исполнителя по ходу фаз (без секретов)
└── tasks.md                 # /speckit-tasks
```

### Source Code (repository root)

```text
.github/workflows/
├── ci.yml                   # [флот] изменить: триггеры, права, concurrency, lint/test-матрица/build/browser, v6
├── release.yml              # [флот] новый: checks → release → deploy
├── deploy.yml               # [флот] новый: workflow_call, окружение production, ссылка + наблюдатель health
└── rollback.yml             # [флот] новый: workflow_dispatch version → validate → deploy
deploy/agent/
├── pullagent.py             # [флот] новый: агент (stdlib)
└── aluma.json               # [ALUMA] новый: конфиг агента
deploy/systemd/user/
├── ihor-aluma-api.service   # [ALUMA] изменить: current/, RELEASE.env после aluma.env
├── ihor-aluma-purge.service # [ALUMA] изменить: current/
├── ihor-aluma-deploy.service# [ALUMA] новый (по шаблону флота)
└── ihor-aluma-deploy.timer  # [ALUMA] новый (по шаблону флота)
scripts/
├── next_version.py          # [флот] новый
├── release_build.py         # [флот] новый (сборка dist/ — вызов ALUMA build.py)
└── secret_scan.py           # [флот] новый; шаблоны ПД — [ALUMA]
api/handler.py               # [ALUMA] изменить: git_sha в health, подпись версии в /admin
tests/
├── requirements.txt         # [флот] новый: werkzeug, boto3, moto (закреплённые)
├── test_health_version.py   # [ALUMA]
├── test_next_version.py     # [флот]
├── test_release_build.py    # [флот]
├── test_pull_agent.py       # [флот]
├── test_secret_scan.py      # [флот]
├── test_user_units.py       # [ALUMA]
├── test_workflows.py        # [флот] текстовые инварианты YAML (права, v6, зависимости из файлов, без smoke)
└── test_delivery_doc.py     # [флот] разделы docs/DELIVERY.md
requirements-lint.txt, ruff.toml   # [флот] новые
.github/rulesets/{master,tags-v,production}.json   # [флот] новые: правила репозитория как файлы
tests/test_rulesets.py             # [флот] новый
docs/DELIVERY.md                   # [флот] новый (структура — образец УЗД)
CLAUDE.md, .specify/memory/constitution.md, deploy/README.md, docs/CUTOVER-CHECKLIST.md   # [ALUMA] привести в соответствие
```

**Structure Decision**: существующий однопроектный репозиторий; новые файлы — в уже принятых каталогах
(`.github/workflows/`, `deploy/`, `scripts/`, `tests/`, `docs/`). Новый каталог — только `deploy/agent/`.

## Общее для флота и специфика ALUMA

| Часть | [флот] — в шаблон | [ALUMA] — своё |
|---|---|---|
| Проверки | триггеры, права, concurrency, v6, зависимости из файлов, имена заданий | команды: unittest, `build.py`, `redesign.spec.js`, порт 8007 |
| Версия и релиз | SemVer + метки, `next_version.py`, архив + `SHA256SUMS` + `MANIFEST`, `RELEASE.env` | содержимое `dist/`, имя архива, режим preview без Pillow |
| Деплой | ссылка `production`, задание `deploy` с окружением, наблюдатель публичного health | `ALUMA_HEALTH_URL` (`table-new` → `table`) |
| Агент | `pullagent.py`: чтение ссылки, скачивание, суммы, блокировка, журнал, `--dry-run`, отказ при правках, возврат | `aluma.json`: пути, юнит `ihor-aluma-api`, `/srv/aluma`, rsync-флаги, `127.0.0.1:8005` |
| Правила репо | master, теги `v*`, `production`, окружение, сканирование секретов | — |
| Проверка истории | порядок, gitleaks, отчёт без значений | шаблоны ПД заявок, `samconfig.toml`, `dump/`, `data/` |
| Документ | структура `docs/DELIVERY.md` | содержимое |

## Фазы реализации (разворачиваются в tasks.md)

1. **Проверка истории и публикация** (US1) — сканер `secret_scan.py` с тестами → проверка зеркала и журналов Actions
   → отчёт → решение дирижёра. Смена видимости и правил — отдельной задачей в фазе 3, после зелёного CI.
2. **Проверки** (US1) — первой задачей правило выката в конституции и CLAUDE.md §9 (constitution-base 2.1.0);
   `requirements-lint.txt`, `ruff.toml`, исправление замечаний, `tests/requirements.txt`,
   новый `ci.yml`, `test_workflows.py`.
3. **Публикация и правила** (US1) — объявление дирижёру; видимость; rulesets; авто-merge; окружение; сканирование
   секретов; проверка отказа прямого push и работы авто-merge.
4. **Версия и релиз** (US2) — health `git_sha`, `next_version.py`, `release_build.py`, `release.yml` (+ тесты).
   `release.yml` — с выключателем выпуска `vars.RELEASES_ENABLED` (contracts/workflows.md): без переменной на master
   идут только проверки, релиз skipped; переменная включается в фазе 3 вместе с правилом тегов (решение дирижёра
   2026-09-11 — release.yml заменяет временный push-на-master в `ci.yml`, первый тег — только после правила тегов).
5. **Агент и деплой** (US3) — `pullagent.py`, `aluma.json`, юниты, `deploy.yml` (+ тесты); переход машины:
   `--dry-run`, первая установка (выкат вне конвейера — только с «да» владельца), паритет статики.
6. **Откат** (US4) — `rollback.yml` (+ тесты), проверка исключений rulesets для Actions. Откат не за выключателем
   выпуска и доступен всегда, когда агент установлен; без `refs/heads/production` — «откатывать нечего», без правок
   репозитория (решение дирижёра 2026-09-11, contracts/workflows.md).
7. **Документы** (US5) — `docs/DELIVERY.md`, остальное в CLAUDE.md, `deploy/README.md`,
   `docs/CUTOVER-CHECKLIST.md` (+ `test_delivery_doc.py`).
8. **Сквозные проверки** — quickstart, секреты после публикации, замер лимита API.
9. **Проверка реальным коммитом** — PR → проверки → merge → релиз → автодеплой → health с sha → откат → обратно.

## Риски

| Риск | Что делаем |
|---|---|
| Находки в истории | стоп до решения дирижёра; видимость не меняется (FR-032) |
| Исключение для `GITHUB_TOKEN` в ruleset не работает | запасной вариант R4: агент ставит только опубликованный тег с полным набором файлов и суммами |
| DNS `table` переключён на коробку 11.09 (`a7e9c64`), кеши ещё могут вести в AWS | `ALUMA_HEALTH_URL` = `table`; успех только при совпадении номера и sha — ответ AWS даёт провал, а не ложный успех; пайплайн DNS не трогает |
| Сломанная версия агента | агент предыдущей версии запускается вручную (docs/DELIVERY.md); автоматический путь продолжится после исправления |
| PyPI недоступен при смене зависимостей | установка не удаётся до переключения — стоит прежняя версия |
| `actions/setup-python@v6` ведёт себя иначе | подтверждается первым прогоном; итог — в DELIVERY.md для флота |
| Первый переход с `0.4.0-box` | `--dry-run`, затем `--once`; ручной возврат к прежнему клону описан |

## Complexity Tracking

> Нарушений конституции нет. Ниже — обоснования, которых принцип VII требует для нового.

| Новое | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| зависимость разработки `ruff` | стандарт флота п.1 требует линтер (требование дирижёра) | flake8/pylint/eslint тяжелее; без линтера — нарушение стандарта флота (R7) |
| разовый инструмент `gitleaks` (вне репозитория) | проверка всей истории перед публикацией — условие владельца | trufflehog шлёт найденные ключи наружу; только сканирование GitHub — уже после публикации (R8) |
| сервис `ihor-aluma-deploy` (таймер + oneshot, без порта) | модель pull — решение дирижёра и главного дирижёра; без входящего SSH | self-hosted runner и SSH из Actions отвергнуты (R1) |
| выключатель выпуска — переменная репозитория `RELEASES_ENABLED` (откат им не останавливается) | остановить выпуск версий без правки кода; до правила тегов (фаза 3) релизы не выходят, а master уже проверяется `release.yml` | держать `release.yml` вне master — master без проверок или временный push-на-master в `ci.yml` (решение дирижёра 2026-09-11) |
| ветка `production` и каталоги `releases/`, `venvs/`, `state/` на машине | сигнал без лимита API; атомарный откат без сети | опрос Deployments API не укладывается в лимит (замер, R1/R2); checkout в клоне — второй источник кода и откат через сеть (R10) |
