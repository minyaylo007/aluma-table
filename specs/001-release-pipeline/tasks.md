---
description: "Задачи: выпуск и деплой ALUMA через GitHub (001)"
---

# Tasks: Выпуск и деплой ALUMA через GitHub

**Input**: `specs/001-release-pipeline/` — spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md

**Prerequisites**: plan.md, spec.md (обязательны); research.md, data-model.md, contracts/ (использованы)

**Tests**: обязательны — конституция I: каждое изменение поведения идёт с тестом; тесты пишутся первыми и должны
падать до реализации. Без сети: git, HTTP и `systemctl` подменяются; `FX_DB_PATH=:memory:` (tests/README-python-tests.md).

**Organization**: по историям spec.md. Первая фаза — проверка истории до публикации (требование дирижёра),
последняя — проверка реальным коммитом.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: можно параллельно (разные файлы, нет зависимости от незавершённых задач)
- **[Story]**: US1…US5 из spec.md
- Пути — от корня репозитория; пути машины — абсолютные

## Правила для исполнителя (на каждую задачу)

- Работать в своём worktree `~/repos/aluma-table`; `git pull --rebase` перед началом; `git add` — явным списком.
- До включения защиты master (T018) — каждая фаза: ветка → PR → merge; после — ветка → PR → авто-merge.
- Перед каждым push: `ruff check .` (после T009), `python -m unittest discover -s tests -t .` в venv вне дерева,
  `python3 build.py` (код 0). Красное не пушится.
- Машина: без sudo; Caddy не запускать/не останавливать/не перезагружать, порт 2019 не трогать; процессы — только по
  PID; слушать только `127.0.0.1:8005`/`8007`; `aluma.env`, `data/`, `dump*` не читать и не печатать.
- Живые доказательства (вывод команд без секретов) — в `specs/001-release-pipeline/verification.md` по ходу работы.
- [флот]/[ALUMA] в описании — куда пойдёт результат (шаблон флота или только ALUMA).

---

## Phase 1: Проверка всей истории до публикации (US1, блокирует смену видимости)

**Goal**: доказать, что в истории репозитория и на стороне GitHub нет секретов и персональных данных, до того как
репозиторий станет публичным (FR-030…FR-033).

**Independent Test**: `secret-scan-report.md` существует, не содержит ни одного значения, перечисляет охват и
находки; решение дирижёра записано. Видимость репозитория на этом этапе не меняется.

### Tests

- [X] T001 [P] [US1] [флот] Написать `tests/test_secret_scan.py`: во временной папке `git init` синтетического
  репозитория с коммитами, содержащими синтетические `AKIA` + 16 символов, `TELEGRAM_BOT_TOKEN=000000:fake-not-a-token`,
  `ADMIN_PASS=fake`, телефон `+972-50-000-0000`, JSON-строку с ключами `name`/`phone`, файлы `dump/x.jsonl`,
  `data/a.db`, `infra/samconfig.toml`, строку ARN ACM с синтетическим аккаунтом из 12 нулей (в тесте она собрана
  склейкой — `tests/test_secret_scan.py`, `ARN`, — чтобы сам файл не был находкой); ожидать код 1,
  в отчёте — правило, короткий sha, путь, номер строки; `assertNotIn` для каждого синтетического значения в stdout и
  в отчёте; чистый репозиторий — код 0; несуществующий путь — код 2 (contracts/secret-scan.md). Убедиться, что тесты
  падают.

### Implementation

- [X] T002 [US1] [флот] Реализовать `scripts/secret_scan.py` (stdlib; `--repo`, `--logs`, `--report`; чтение
  `git log --all -p --no-color`; шаблоны из research.md R8; вывод без значений; коды 0/1/2) — до зелёного T001.
- [X] T003 [US1] [флот] Подготовить инструменты вне дерева: `umask 077`; `mktemp -d /tmp/aluma-scan-XXXXXX`; скачать
  закреплённую версию `gitleaks` для linux x64 и `checksums.txt` её релиза; `sha256sum -c` по своей строке; версию и
  сумму записать в `specs/001-release-pipeline/secret-scan-report.md` (раздел «Инструменты»). В репозиторий бинарник
  не класть.
- [X] T004 [US1] `git clone --mirror https://github.com/minyaylo007/aluma-table.git <tmp>/mirror.git`; запустить
  `gitleaks git <tmp>/mirror.git --log-opts=--all --redact --report-format json --report-path <tmp>/gitleaks.json` и
  `python3 scripts/secret_scan.py --repo <tmp>/mirror.git --report <tmp>/patterns.md`; число коммитов и ссылок
  (включая `refs/pull/*`) — в отчёт.
- [X] T005 [US1] Сторона GitHub: `gh run list --limit 1000 --json databaseId`, для каждого — `gh run view <id> --log`
  в `<tmp>/logs/`; список артефактов прогонов (`gh api repos/minyaylo007/aluma-table/actions/artifacts`) — скачать и
  проверить, если есть; релизы, issues, PR и комментарии (`gh release list`, `gh issue list --state all`,
  `gh pr list --state all`); прогнать gitleaks (`dir`, `--redact`) и `scripts/secret_scan.py --logs` по сохранённому.
- [X] T006 [US1] Составить `specs/001-release-pipeline/secret-scan-report.md` по data-model.md «Отчёт проверки
  истории»: охват, находки (правило, коммит, путь, строка — без значений), отдельным пунктом для решения
  дирижёра заведомые инфраструктурные идентификаторы: AWS account id и ARN сертификата в
  `infra/samconfig.toml.example`, а также IP сервера, имена хостов и пути машины в `docs/`, `deploy/`, `CLAUDE.md`; итог. Проверить
  отчёт `grep` по синтетическим и реальным префиксам секретов (`AKIA`, `ghp_`, `:AA`) — пусто. Удалить `<tmp>`.
- [X] T007 [US1] Закоммитить `scripts/secret_scan.py`, `tests/test_secret_scan.py`,
  `specs/001-release-pipeline/secret-scan-report.md` (ветка → PR → merge) и отправить отчёт дирижёру
  («🪵 ALUMA — дирижёр»). **СТОП**: при любой находке видимость не менять до его решения (ротация / чистка истории).

**Checkpoint**: отчёт принят дирижёром, решение по находкам записано в отчёт.

---

## Phase 2: Проверки на каждый PR и push (US1, основа для всего)

**Goal**: линтер, тесты на 3.12/3.13, сборка, браузерные тесты — на каждый push и PR, зависимости только из файлов
(FR-001, FR-004, FR-004a, FR-035).

**Independent Test**: PR с этой фазой показывает зелёные `lint`, `test (3.12)`, `test (3.13)`, `build`, `browser`;
заведомо сломанный тест в пробной ветке даёт красный `test`.

### Предусловие (до любого выката через конвейер)

- [X] T008 [US1] [ALUMA] Привести правило выката к constitution-base 2.1.0 до появления конвейера выката: в
  `.specify/memory/constitution.md` п.VI — основная ветка `master` и формулировка базы («Выкат — по docs/DELIVERY.md
  проекта. Автодеплой после попадания в целевую ветку разрешён и желателен (OWNER-RULES п.22), если проверки CI
  зелёные и откат проверен; выкат в прод вне этого конвейера — по-прежнему только с «да» владельца.»), версия и дата
  поправки — по разделу «Управление»; в `CLAUDE.md` §9 абзац «Deploy is owner-only» — та же формулировка (запреты AWS
  в абзаце остаются). Показать дифф дирижёру, дождаться согласия, отдельный коммит. Задачи T029 и далее, создающие
  релиз и деплой, — только после этого коммита.

### Tests

- [X] T009 [P] [US1] [флот] Создать `requirements-lint.txt` (`ruff==<закреплённая версия>`) и `ruff.toml`
  (`select = ["E9", "F"]`, исключить `node_modules`, `ms-playwright`, `dist`, `.build`, `assets-src`, `.claude`);
  прогнать `ruff check .` в venv вне дерева и записать число замечаний.
- [X] T010 [P] [US1] [флот] Создать `tests/requirements.txt` с закреплёнными версиями `werkzeug`, `boto3`, `moto`
  (версии — те, с которыми полный набор проходит локально на 3.12 и в CI на 3.13); обновить команду в
  `tests/README-python-tests.md`.
- [X] T011 [P] [US1] [флот] Написать `tests/test_workflows.py`, класс `CiYmlTests` (текстовые проверки без YAML-
  библиотеки): в `.github/workflows/ci.yml` есть `permissions:` с `contents: read`; триггеры `push` с
  `branches-ignore: [master]`, `pull_request` на `master`, `workflow_call`; `concurrency` с
  `cancel-in-progress: ${{ github.ref != 'refs/heads/master' }}`; только `actions/checkout@v6`,
  `actions/setup-node@v6`, `actions/setup-python@v6`; каждый `pip install` — только с `-r`; задания `lint`, `test`
  (матрица `3.12`, `3.13`), `build`, `browser`; нет `smoke.spec.js`; нет `secrets.`. Убедиться, что падает на
  нынешнем `ci.yml`.

### Implementation

- [X] T012 [US1] Исправить замечания `ruff` в затронутых файлах `api/`, `scripts/`, `tests/`, `tools/`, `build.py`
  без изменения поведения (или отключить правило для конкретного файла в `ruff.toml` с причиной в комментарии);
  полный набор тестов — прежнее число OK.
- [X] T013 [US1] [флот] Переписать `.github/workflows/ci.yml` по contracts/workflows.md «ci.yml»: задания `lint`
  (`ruff check .`, `node --check site/assets/*.js tests/*.js`), `test` (матрица 3.12/3.13, `pip install -r
  api/requirements.txt -r tests/requirements.txt`, `python -m unittest discover -s tests -t . -v`), `build`
  (`python build.py` дважды, суммы `dist/` совпадают; Pillow не ставить), `browser` (`npm ci`, Chromium,
  `PREVIEW_PORT=8007 PYTHON=python npx playwright test --config playwright.local.config.js`); удалить задание `smoke`.
- [X] T014 [US1] Прогнать локально: `ruff check .`, полный unittest, `python3 build.py`, Playwright на 8007
  (CLAUDE.md §8; перед запуском `ss -ltn | grep ':8007 '` — пусто). Ветка → PR → дождаться зелёных пяти проверок;
  записать в `verification.md` номера прогонов и что `actions/setup-python@v6` отработал. Merge.

**Checkpoint**: пять проверок зелёные на PR; имена заданий зафиксированы для ruleset.

---

## Phase 3: Публикация репозитория и защита master (US1) 🎯 MVP

**Goal**: после чистой проверки (Phase 1) и зелёного CI (Phase 2) репозиторий публичен; master защищён для всех;
авто-merge; окружение `production`; сканирование секретов GitHub (FR-002, FR-003, FR-025a, FR-034).

**Independent Test**: PR с падающим тестом не вливается; исправленный вливается сам; `git push origin HEAD:master`
отклоняется; окружение `production` видно в настройках с правилом «только master».

### Tests

- [ ] T015 [P] [US1] [флот] Создать файлы правил `.github/rulesets/master.json`, `.github/rulesets/tags-v.json`,
  `.github/rulesets/production.json` (формат REST API rulesets) и `tests/test_rulesets.py`: master — `pull_request`
  с 0 одобрений, `required_status_checks` ровно `lint`, `test (3.12)`, `test (3.13)`, `build`, `browser` (сверка с
  именами заданий `ci.yml`), `non_fast_forward`, `deletion`, `bypass_actors` пуст; `tags-v` — цель `refs/tags/v*`,
  `creation`/`update`/`deletion`, обход — только приложение GitHub Actions; `production` — цель
  `refs/heads/production`, `deletion`, `update`/`non_fast_forward` с обходом только для GitHub Actions. Сначала
  красный (файлов нет), затем зелёный.

### Implementation

- [ ] T016 [US1] Объявить дирижёру (SendMessage «🪵 ALUMA — дирижёр») перечень изменений в GitHub (видимость, три
  правила, авто-merge, squash, окружение, сканирование секретов) и дождаться «выполняй». Без ответа — не продолжать.
- [ ] T017 [US1] `gh repo edit minyaylo007/aluma-table --visibility public --accept-visibility-change-consequences`;
  `gh repo edit … --enable-auto-merge --enable-squash-merge --enable-merge-commit=false --enable-rebase-merge=false
  --delete-branch-on-merge`; включить secret scanning и push protection (`gh api -X PATCH repos/minyaylo007/aluma-table`
  с `security_and_analysis`); включить неизменяемые релизы, если настройка доступна. Вывод — в `verification.md`.
- [ ] T018 [US1] Применить `.github/rulesets/master.json` (`gh api -X POST repos/minyaylo007/aluma-table/rulesets
  --input …`); проверить `gh api repos/minyaylo007/aluma-table/rulesets`.
- [ ] T019 [US1] Применить `tags-v.json` и `production.json`; если API отвергает обход для GitHub Actions — применить
  запасной вариант research.md R4 (правило тегов без обхода на создание, только запрет обновления/удаления; ветка
  `production` без правила), записать причину в `verification.md` и в раздел «Разрыв со стандартом флота» будущего
  `docs/DELIVERY.md` (T046).
- [ ] T020 [US1] Создать окружение `production` (`gh api -X PUT repos/minyaylo007/aluma-table/environments/production`
  с правилом веток: только `master`) и переменную окружения `ALUMA_HEALTH_URL` = `https://table.central-aparts.store/api/fx/health` (DNS `table`
  переключён на коробку 11.09, `a7e9c64`; `table-new` — только если дирижёр скажет, что переключение не принято).
- [ ] T021 [US1] Проверить вживую: (1) пробная ветка с заведомо падающим тестом → PR с авто-merge → не влилась;
  (2) исправить → влилась сама; (3) `git push origin HEAD:master` из другой ветки → отказ сервера; (4) `gh api
  repos/minyaylo007/aluma-table/secret-scanning/alerts` → пусто. Всё — в `verification.md`; отчёт дирижёру.

**Checkpoint**: US1 готова — в master попадает только проверенное. С этого момента все сессии — через PR.

---

## Phase 4: Каждое слияние публикует версию (US2)

**Goal**: SemVer-тег, релиз с воспроизводимым архивом и `SHA256SUMS`, health отдаёт `version` и `git_sha`
(FR-005…FR-009).

**Independent Test**: слияние PR → тег `v0.5.0` и релиз с двумя файлами; `sha256sum -c SHA256SUMS` — OK;
`scripts/release_build.py` дважды на том же коммите — одинаковый архив (quickstart.md §3).

### Tests

- [X] T022 [P] [US2] [ALUMA] Написать `tests/test_health_version.py` (по образцу `tests/test_handler.py`):
  `GET /api/fx/health` при `APP_VERSION=v0.5.0` и `GIT_SHA=` 40 hex → тело с `version` = `v0.5.0` и тем же
  `git_sha`; при отсутствии или пустом `GIT_SHA` → `"git_sha": null`; остальные поля (`ok`, `ts`) — как раньше;
  подпись версии в `/admin` не содержит `vv` (contracts/health.md).
- [X] T023 [P] [US2] [флот] Написать `tests/test_next_version.py`: без тегов → `v0.5.0`; `v0.5.3` без меток →
  `v0.5.4`; `release:minor` → `v0.6.0`; `release:major` → `v1.0.0`; обе метки → major; теги не по шаблону
  `vX.Y.Z` игнорируются; `v0.10.0` старше `v0.9.9`.
- [X] T024 [P] [US2] [флот] Написать `tests/test_release_build.py`: на временном клоне текущего HEAD
  `scripts/release_build.py --tag v0.0.1 --sha <HEAD> --out <tmp>` дважды → побайтно одинаковые
  `aluma-v0.0.1.tar.gz`; в архиве есть `dist/`, `RELEASE.json` (поля `version`, `git_sha`, `build_mode`,
  `committed_at`), `RELEASE.env` ровно из `APP_VERSION=v0.0.1` и `GIT_SHA=<HEAD>`, `MANIFEST.sha256` сходится со
  всеми файлами; `SHA256SUMS` в формате `<64 hex>␠␠<имя>`; при отслеживаемом файле `data/x.db` во временном репо —
  сборка падает (contracts/release-artifact.md, «Запрещено в архиве»).
- [X] T025 [P] [US2] [флот] Дополнить `tests/test_workflows.py` классом `ReleaseYmlTests`: триггер `push` на
  `master`; задание `checks` вызывает `./.github/workflows/ci.yml`; `release` имеет `needs: checks`, права
  `contents: write` и `pull-requests: read` только у себя, `concurrency: release-production` без отмены; вызывает
  `scripts/next_version.py` и `scripts/release_build.py`.

### Implementation

- [X] T026 [US2] [ALUMA] `api/handler.py`: `GIT_SHA = os.environ.get("GIT_SHA") or None` рядом с `APP_VERSION`;
  ответ health `{"ok": True, "version": APP_VERSION, "git_sha": GIT_SHA, "ts": now_iso()}`; подпись в `/admin` —
  без двойной `v`. Больше ничего в хендлере не менять (критичные потоки).
- [X] T027 [P] [US2] [флот] Реализовать `scripts/next_version.py` (`--tags`, `--labels`; печатает следующий тег)
  до зелёного T023.
- [X] T028 [P] [US2] [флот] Реализовать `scripts/release_build.py` по contracts/release-artifact.md (`git archive`
  коммита, `python3 build.py` в чистом checkout без Pillow, `RELEASE.json`, `RELEASE.env`, `MANIFEST.sha256`,
  детерминированный tar/gzip, `SHA256SUMS`, отказ на запрещённых путях) до зелёного T024.
- [X] T029 [US2] [флот] Создать `.github/workflows/release.yml` по contracts/workflows.md «release.yml» (пока без
  задания `deploy` — оно появится в T037): метки PR коммита через `gh api repos/${{ github.repository }}/commits/${{ github.sha }}/pulls`,
  тег на `$GITHUB_SHA`, `gh release create` с файлами из `out/` и списком изменений.
- [ ] T030 [US2] Ветка → PR → авто-merge; проверить: появились тег `v0.5.0` и релиз; скачать оба файла по прямым
  ссылкам, `sha256sum -c SHA256SUMS` — OK; локально `scripts/release_build.py` для того же тега и sha — та же сумма;
  `python3 scripts/compare_sites.py https://table-new.central-aparts.store <распакованный архив>/dist --assets --ignore-eol`
  (только GET) — код 0 или объяснённые отличия. Всё — в `verification.md`.

**Checkpoint**: US2 готова — версии публикуются сами и проверяемы побайтно.

---

## Phase 5: Опубликованная версия сама встаёт на машину (US3)

**Goal**: задание `deploy` двигает `production` и ждёт публичный health; агент без токенов и без REST API ставит
версию, проверяет, публикует статику, при провале возвращает прежнюю (FR-010…FR-021).

**Independent Test**: после деплоя `v0.5.x` локальный и публичный health показывают её номер и sha; окружение
`production` в GitHub — «success»; агент ничего не слушает; тесты сценариев провала зелёные.

### Tests

- [X] T031 [P] [US3] [флот] Написать `tests/test_pull_agent.py` (подмены: запуск git, HTTP-открыватель, `systemctl`,
  `rsync`, часы; временная `base_dir` и `static_dst`): (a) sha ссылки = `state.current` → код 0, событие
  `unchanged`, ничего не скачано; (b) новая версия → скачан `SHA256SUMS` и архив, распакован в `releases/<tag>/`,
  `current` переключён, `systemctl --user restart ihor-aluma-api.service` вызван, health проверен, `rsync` с ровно
  `-a --delete-after --delay-updates --chmod=D0755,F0644`, суммы файлов в `static_dst` сверены с `MANIFEST.sha256`
  (файл не читаем для всех → провал), `state.json` обновлён, событие `deploy_done`, короткий итог в stdout; (c) сумма
  не сошлась → код 3, `current` не менялся; (d) локальный health не сошёлся за `health_timeout_s` → возврат
  прежнего `current`, повторный `rsync` прежней `dist/`, sha в `failed.json`, код 1; повторный цикл с тем же sha →
  `unchanged`, без установки; (e) файл текущей версии изменён относительно `MANIFEST.sha256` → код 3,
  `reason: dirty_current`; (f) на sha нет тега `v*` → код 3, `no_release_tag`; (g) `--dry-run` → ничего не
  переключено, код 0; (h) блокировка занята → код 5; (i) прерывание после переключения (`current` ≠
  `state.current`) → следующий цикл доводит до согласованного; (j) ни в одном HTTP-запросе нет `Authorization`, ни
  одного обращения к `api.github.com`, хосты только `github.com` и `objects.githubusercontent.com`; (k) git вызывается
  с `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_TERMINAL_PROMPT=0`, `-c credential.helper=`,
  `-c protocol.version=2`; (l) в исходнике `deploy/agent/pullagent.py` нет подстрок `sudo`, `caddy`, `2019`,
  `.bind(`, `.listen(`; (m) конфиг с `health_url` не на `127.0.0.1` или путями вне разрешённых → отказ старта;
  (n) журнал не содержит значений переменных окружения и тела ответов; (o) хранится не больше `keep_releases`
  версий, текущая и предыдущая не удаляются; (p) ни в одном сценарии, включая возврат, агент не открывает и не
  меняет `data/` и `aluma.env` (подменённые пути доступны только на чтение — попытка записи роняет тест).
- [X] T032 [P] [US3] [ALUMA] Написать `tests/test_user_units.py`: `deploy/systemd/user/ihor-aluma-api.service` —
  `WorkingDirectory=/opt/ihor/aluma-table/current`, `ExecStart` из `current/.venv/bin/gunicorn` с
  `--no-control-socket` и `-b 127.0.0.1:8005`, строка `EnvironmentFile=/opt/ihor/aluma-table/current/RELEASE.env`
  ПОСЛЕ `EnvironmentFile=%h/.config/aluma/aluma.env`, `UMask=0077`; `ihor-aluma-purge.service` — `current/`;
  `ihor-aluma-deploy.service` — `Type=oneshot`, системный `/usr/bin/python3`, `--once`, `NoNewPrivileges=true`,
  `UMask=0027`, без `sudo`; `ihor-aluma-deploy.timer` — `OnBootSec=2min`, `OnUnitInactiveSec=60s`.
- [X] T033 [P] [US3] [флот] Дополнить `tests/test_workflows.py` классом `DeployYmlTests`: `workflow_call` со входом
  `tag`; задание с `environment` `production`; `concurrency: deploy-production` с `cancel-in-progress: true`; права —
  только `contents: write`; `git push --force origin …:refs/heads/production`; опрос `ALUMA_HEALTH_URL` со сверкой
  `version` и `git_sha`, таймаут 15 мин; в `release.yml` задание `deploy` с `needs: release`.

### Implementation

- [X] T034 [US3] [флот] Реализовать `deploy/agent/pullagent.py` по contracts/agent-cli.md, contracts/production-ref.md,
  contracts/release-artifact.md и переходам data-model.md (stdlib; `--once`, `--dry-run`, `--status`; коды 0–5;
  журнал JSON в `state/deploy.log` и stdout; блокировка `flock`; venv по хешу требований; синхронизация
  `deploy/systemd/user/` → `~/.config/systemd/user/` + `systemctl --user daemon-reload`; атомарное переключение
  `current`) — до зелёного T031.
- [X] T035 [P] [US3] [ALUMA] Создать `deploy/agent/aluma.json` ровно по contracts/agent-cli.md «Конфиг».
- [X] T036 [P] [US3] [ALUMA] Изменить `deploy/systemd/user/ihor-aluma-api.service` и `ihor-aluma-purge.service`
  (пути `current/`, второй `EnvironmentFile`), создать `deploy/systemd/user/ihor-aluma-deploy.service` и
  `ihor-aluma-deploy.timer` (research.md R13; комментарии на украинском, как в соседних юнитах) — до зелёного T032.
- [X] T037 [US3] [флот] Создать `.github/workflows/deploy.yml` по contracts/workflows.md «deploy.yml» и добавить в
  `.github/workflows/release.yml` задание `deploy` (`needs: release`, `uses: ./.github/workflows/deploy.yml`,
  `with: tag`) — до зелёного T033.
- [ ] T038 [US3] Ветка → PR → авто-merge → появился релиз `v0.5.x` с агентом; задание `deploy` ждёт (агента на машине
  ещё нет) и падает по таймауту — ожидаемо, записать.
- [ ] T039 [US3] [ALUMA] Переход машины, шаг 1 (research.md R10): `umask 027`; создать `/opt/ihor/aluma-table/releases`,
  `/opt/ihor/aluma-table/venvs`, `/opt/ihor/aluma-table/state` (`chmod 0700 state`); скачать `aluma-v0.5.x.tar.gz` и
  `SHA256SUMS` по прямым ссылкам в `state/downloads/`, `sha256sum -c`; распаковать во временный каталог; прогнать его
  `deploy/agent/pullagent.py --config <распаковка>/deploy/agent/aluma.json --dry-run` — «было → станет», код 0.
  Прежний клон, `.venv`, `data/`, `dump-*`, `rollback/` не трогать.
- [ ] T040 [US3] [ALUMA] Переход машины, шаг 2 — **выкат вне конвейера: только после «да» владельца, полученного
  через дирижёра** (constitution-base 2.1.0, п.VI; до ответа — стоп): записать в `verification.md` текущие `systemctl --user cat
  ihor-aluma-api` и health (`0.4.0-box`) — это точка ручного возврата; запустить агент распакованной версии с
  `--once`; ожидать: юниты заменены, `current` → `releases/v0.5.x`, `ihor-aluma-api` перезапущен,
  `curl -s http://127.0.0.1:8005/api/fx/health` — `version` = тег, `git_sha` = sha тега; `find /srv/aluma ! -perm -o=r`
  — пусто. Затем `systemctl --user enable --now ihor-aluma-deploy.timer`. При провале — ручной возврат по
  записанной точке и стоп, доклад дирижёру.
- [ ] T041 [US3] Перезапустить задание `deploy` для `v0.5.x` (`rollback.yml` ещё нет — повторный запуск
  проваленного задания в Actions) → «success»; окружение `production` показывает `v0.5.x`; публичный health (адрес
  из `ALUMA_HEALTH_URL`) — те же номер и sha; `ss -ltnp` — у процессов агента нет слушающих сокетов; журнал
  `journalctl --user -u ihor-aluma-deploy -n 20` без секретов. В `verification.md`.

**Checkpoint**: US3 готова — версия встаёт сама, статус виден в GitHub.

---

## Phase 6: Откат одним действием (US4)

**Goal**: `rollback.yml` с номером версии — тот же путь деплоя; отказ на несуществующей версии; запуск только из
master (FR-022…FR-025a).

**Independent Test**: откат на несуществующую версию отказывает до деплоя; откат, запущенный с не-master ветки,
блокируется правилом окружения; откат на прежнюю версию и обратно (полный цикл — Phase 9).

### Tests

- [X] T042 [P] [US4] [флот] Дополнить `tests/test_workflows.py` классом `RollbackYmlTests`: `workflow_dispatch` со
  входом `version` (обязательный, шаблон `^v\d+\.\d+\.\d+$`); задание `validate` проверяет тег и оба файла релиза до
  вызова; `deploy` — `uses: ./.github/workflows/deploy.yml` с `needs: validate`; нет `secrets.`; права по умолчанию
  `contents: read`.

### Implementation

- [X] T043 [US4] [флот] Создать `.github/workflows/rollback.yml` по contracts/workflows.md «rollback.yml» — до
  зелёного T042. Ветка → PR → авто-merge.
- [ ] T044 [US4] Проверить вживую: `gh workflow run rollback.yml -f version=v9.9.9` → отказ в `validate`, деплоя нет;
  `gh workflow run rollback.yml --ref <не-master ветка> -f version=<текущая>` → задание `deploy` не проходит правило
  окружения; `gh workflow run rollback.yml -f version=<текущая>` → «success», машина не менялась (`unchanged` в
  журнале агента); `git push origin :refs/tags/v0.5.0` и повторный push этого тега на другой коммит — отказ сервера
  (FR-008); при включённых неизменяемых релизах `gh release upload v0.5.0 <файл> --clobber` — отказ (иначе — в
  «Розрив»). В `verification.md`.

**Checkpoint**: US4 готова.

---

## Phase 7: Документы процесса (US5)

**Goal**: `docs/DELIVERY.md` по структуре образца УЗД; CLAUDE.md, конституция, `deploy/README.md`,
`docs/CUTOVER-CHECKLIST.md` согласованы (FR-027, FR-028, FR-035).

**Independent Test**: `tests/test_delivery_doc.py` зелёный; в CLAUDE.md нет утверждений «deploy is owner-only» /
«push в master не выкатывает»; ссылки ведут на существующие файлы.

### Tests

- [X] T045 [P] [US5] [флот] Написать `tests/test_delivery_doc.py`: `docs/DELIVERY.md` существует и содержит разделы
  (язык — украинский, как документы проекта и DELIVERY.md УЗД): «Оточення», «Гілки, PR, коміти», «Перевірки (CI)»,
  «Релізи й версії», «Викат», «Секрети», «Ресурси», «Відкат», «Розрив зі стандартом флоту», «Хто що натискає»,
  «Якщо щось зламалось»; упоминает `docs/AWS-TEARDOWN.md`, `ALUMA_HEALTH_URL`, `rollback.yml`,
  `actions/setup-python@v6`; все относительные ссылки на файлы репозитория существуют; нет строк вида `KEY=значение`
  для `ADMIN_PASS`, `IP_SALT`, `TELEGRAM_BOT_TOKEN`, `EDGE_SECRET`.

### Implementation

- [X] T046 [US5] [флот] Написать `docs/DELIVERY.md` — то, что есть (не план): окружения (`production` = ace-main;
  `table-new`/`table`; превью нет); ветки, PR, squash, заголовок PR = `type(scope): опис`, метки `release:minor` /
  `release:major`; проверки (что запускается, что НЕ запускается и почему — `smoke.spec.js`); релизы и версии;
  выкат (ссылка `production`, агент, журнал, `--dry-run`, `--status`); секреты (GitHub Secrets пусты; на машине —
  `~/.config/aluma/aluma.env` 600; агент без токенов); ресурсы (ace-main, `/opt/ihor/aluma-table`, `/srv/aluma`,
  юниты, порты 8005/8007, список AWS — ссылкой на `docs/AWS-TEARDOWN.md`); откат (автоматический, `rollback.yml`,
  ручной возврат агентом предыдущей версии, возврат к `0.4.0-box`); «Разрыв со стандартом флоту» (честно: итог
  R4, SC-010 до суточного замера, всё непроверенное); «Хто що натискає» (конвейер, агент, владелец, сессии);
  «Якщо щось зламалось» (агент, отказ git, защита снята в аварии); закреплённые версии actions (FR-035).
- [X] T047 [P] [US5] [ALUMA] `CLAUDE.md`: шапка (как ALUMA живёт на машине и как туда попадает), §2 строка CI и
  новые файлы зависимостей, §3 (агент, workflows, `release_build.py`, `next_version.py`, `secret_scan.py`,
  `git_sha` в health), §8 (команды агента `--dry-run`/`--status`, линтер), §9 Git (ветка → PR → авто-merge,
  прямой push в master невозможен; абзац про выкат уже поправила задача-предусловие фазы 2); таблица «Where things are» → `docs/DELIVERY.md`. По CLAUDE.md §10: каждую команду прогнать или
  пометить непроверенной.
- [X] T048 [P] [US5] [ALUMA] `deploy/README.md`: разделы «Користувацькі юніти» (раскладка `releases/`/`current`,
  новые юниты агента) и «Публікація статики» — ручные шаги заменить ссылкой на `docs/DELIVERY.md`, историю
  оставить с пометкой «замінено».
- [X] T049 [P] [US5] [ALUMA] `docs/CUTOVER-CHECKLIST.md`: крок 1 «Оновити клон» и крок 6 — ссылка на
  `docs/DELIVERY.md`; в раздел отката переключения — пункт: при возврате `table` на AWS
  сменить переменную окружения `ALUMA_HEALTH_URL` на `table-new` (`gh variable set … --env production`) и обратно.
- [X] T050 [US5] Прогнать `tests/test_delivery_doc.py` и полный набор; ветка → PR → авто-merge (это само по себе
  создаст версию и деплой — проверить, что прошло «success»).
  **Сделано частично, остальное — после Phase 3:** тесты (`Ran 395 … OK`), `ruff`, `build.py` зелёные, слияние в
  `master` перемоткой (правил ветвления ещё нет). Версия и деплой не создались и не могли: `RELEASES_ENABLED`
  не задана, `release`/`deploy` — skipped. Проверка «success» переносится на T030/T041 (`verification.md`, Phase 7).

**Checkpoint**: US5 готова.

---

## Phase 8: Сквозные проверки

**Purpose**: то, что касается всех историй.

- [ ] T051 [P] Прогнать `quickstart.md` §0–§6 на актуальном master; отличия — исправить документ или код (отдельным PR).
- [ ] T052 [P] Проверить секреты и ПД после публикации: `gh api repos/minyaylo007/aluma-table/secret-scanning/alerts`
  — пусто; `python3 scripts/secret_scan.py` по свежему зеркалу — код 0; журналы последних прогонов Actions — без
  значений; итог — в `verification.md` и раздел «Секрети» `docs/DELIVERY.md`.
- [ ] T053 Замер SC-010: сохранить `curl -s https://api.github.com/rate_limit` (остаток) до включения таймера
  агента (T040) и через ≥ 24 ч работы; убедиться по журналу агента и тестам, что агент не обращался к
  `api.github.com`; итог — в `verification.md` (если суток ещё нет к концу фичи — отметить в «Розрив» и дописать позже).

---

## Phase 9: Проверка реальным коммитом (FR-029, SC-001, SC-002, SC-005, SC-008)

**Purpose**: доказать весь цикл на живом пайплайне. Каждый шаг — время и ответ GitHub или машины в
`specs/001-release-pipeline/verification.md`.

- [ ] T054 Безобидная правка (например, строка в `docs/DELIVERY.md` «Перевірено реальним комітом: <дата>») → ветка →
  PR с авто-merge; записать время создания PR, зелёных проверок, слияния и sha squash-коммита в master.
- [ ] T055 Дождаться релиза `vX.Y.Z` (тег на этот sha) и задания `deploy`; во время установки раз в секунду опрашивать
  `http://127.0.0.1:8005/api/fx/health` и считать неответы (SC-005: не больше 30 с); после — локальный и публичный
  health показывают `version` = новый тег и `git_sha` = **sha squash-коммита из T054**; окружение `production` —
  «success»; журнал агента `deploy_done`. Время «слияние → health» ≤ 20 мин (SC-001).
- [ ] T056 `gh workflow run rollback.yml -f version=<предыдущий тег>` → ≤ 10 мин: health показывает прежние номер
  и sha; сумма `/srv/aluma/index.html` = строке `dist/index.html` из `MANIFEST.sha256` прежней версии; окружение
  активно на прежней (SC-002).
- [ ] T057 `gh workflow run rollback.yml -f version=<новый тег>` → health снова показывает новый номер и sha из T054.
- [ ] T058 Итог: полный unittest и `python3 build.py` зелёные; `git status` чистый; в `verification.md` — таблица
  шагов T054–T057 с временем; отчёт дирижёру: хеши, номера версий, времена, что осталось в «Розрив».
- [ ] T059 (приёмка дирижёра, SC-009) Дирижёр поручает новой сессии без контекста провести пробное изменение через PR
  и откат по одной `docs/DELIVERY.md`; вопросы сессии — в «Розрив» / правки документа.

---

## Dependencies & Execution Order

### Phase Dependencies

- **T008 (правило выката в конституции и CLAUDE.md)** — блокирует T029 и все задачи, создающие релиз или деплой.
- **T040 (первая установка на машину)** — только после «да» владельца через дирижёра.
- **Phase 1 (проверка истории)** — сразу; **блокирует Phase 3** (смену видимости) до решения дирижёра.
- **Phase 2 (проверки)** — параллельно с Phase 1 или после; блокирует Phase 3 (нужны имена заданий и зелёный CI).
- **Phase 3 (публикация и защита)** — после Phase 1 (чистый отчёт + решение) и Phase 2; блокирует Phase 5
  (агент читает репозиторий анонимно — только публичный).
- **Phase 4 (релиз, US2)** — после Phase 2; может идти до Phase 3, но первый релиз `v0.5.0` — после Phase 3
  (иначе правило тегов ещё не действует).
- **Phase 5 (агент, US3)** — после Phase 3 и Phase 4.
- **Phase 6 (откат, US4)** — после Phase 5.
- **Phase 7 (документы, US5)** — после Phase 6 (описывает то, что есть); T047, T048, T049 параллельно между собой.
- **Phase 8** — после Phase 7; T053 тянется ≥ 24 ч после T040.
- **Phase 9** — последней.

### User Story Dependencies

- **US1 (P1)**: Phase 1 + Phase 2 + Phase 3. Независима.
- **US2 (P2)**: зависит от US1 (проверки как условие релиза).
- **US3 (P3)**: зависит от US2 (артефакт) и публичности из US1.
- **US4 (P4)**: зависит от US3 (тот же путь деплоя).
- **US5 (P5)**: описывает US1–US4.

### Within Each Phase

- Тесты пишутся первыми и должны падать; реализация — до зелёного.
- Коммит после каждой законченной задачи или логической группы; фаза завершается PR.

## Parallel Examples

```text
Phase 2:  T009 (ruff), T010 (tests/requirements.txt), T011 (test_workflows CI) — разные файлы
Phase 4:  T022, T023, T024, T025 — тесты; затем T027 и T028 параллельно, T026 и T029 — отдельно
Phase 5:  T031, T032, T033 — тесты; T035 и T036 параллельно с T034
Phase 7:  T047, T048, T049 — разные файлы
```

## Implementation Strategy

### MVP (US1)

Phase 1 → решение дирижёра → Phase 2 → Phase 3. Итог: публичный репозиторий без секретов в истории, master только
через PR с зелёными проверками и авто-merge. Уже это закрывает п.1 стандарта флота.

### Incremental Delivery

US2 (версии публикуются) → US3 (автодеплой на машину) → US4 (откат) → US5 (документ) → Phase 8–9 (сквозные
проверки и реальный коммит). После каждой истории — отчёт дирижёру; ALUMA — пилот, выводы идут в шаблон флота.

## Notes

- Секреты, данные заявок, значения из `aluma.env` — нигде: ни в выводе, ни в `verification.md`, ни в отчётах.
- Длинный текст в оболочку — только через файл или в одинарных кавычках; heredoc только `<<'EOF'`.
- Если задача упирается в решение владельца или дирижёра (находки проверки, правила, DNS) — стоп и SendMessage
  «🪵 ALUMA — дирижёр», не решать самому.
