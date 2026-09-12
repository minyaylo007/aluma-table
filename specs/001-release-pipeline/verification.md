# Verification — живі докази виконавця (001)

Вивід команд без секретів і персональних даних. Час — UTC, якщо не сказано інше.

## Phase 1 — перевірка історії

Див. `secret-scan-report.md` (коміти 5dc3df4, 9ad0718). Видимість репозиторію не змінювалась.

## Phase 2 — перевірки на кожен PR і push

### Локально (2026-09-11, ace-main, Python 3.12.3, venv поза деревом)

| Перевірка | Результат |
|---|---|
| `ruff check .` (ruff 0.16.7, `select = ["E9", "F"]`) до правок | 8 зауважень: 5 × F401, 3 × F841 |
| `ruff check .` після T012 | `All checks passed!` |
| `python -m unittest discover -s tests -t .` | `Ran 282 tests … OK` (269 + 13 у `tests/test_workflows.py`) |
| `tests/test_workflows.py` на старому `ci.yml` | 10 червоних із 13 (помічники — зелені), як і має бути до T013 |
| `python3 build.py` | exit 0, PREVIEW build |
| `dist/` до і після правок `build.py` (T012) | 116 файлів, суми `sha256` побайтно однакові |
| `node --check` для `dist/assets/*.js`, `tests/*.js` | 3 файли, 0 помилок |
| Playwright `tests/redesign.spec.js` на 127.0.0.1:8007 | `39 passed (1.5m)`; порт 8007 вільний до і після |

Примітка до `node --check`: `site/assets/app.js` — шаблон із токенами `{{…}}`, які підставляє `build.py`,
тож `node --check site/assets/app.js` падає за визначенням. Завдання `lint` перевіряє зібраний `dist/assets/*.js`.

### GitHub Actions

Прогін [34608006392](https://github.com/minyaylo007/aluma-table/actions/runs/34608006392) — подія `push` у гілку
`001-phase2-ci`, коміт `4dc1fd6`, 14:04:46–14:06:35Z (≈ 2 хв):

| Завдання | Висновок | Що в журналі |
|---|---|---|
| `lint` | success | CPython 3.13.15; `ruff check .` → `All checks passed!`; `node --check` без помилок |
| `test (3.12)` | success | CPython 3.12.14; `Ran 282 tests … OK` (без пропусків) |
| `test (3.13)` | success | CPython 3.13.15; `Ran 282 tests … OK` (без пропусків) |
| `build` | success | CPython 3.12.14; дві збірки — `diff` сум порожній, 116 файлів у `dist/` |
| `browser` | success | CPython 3.12.14; `npm ci`, Chromium; `39 passed (1.0m)` на `PREVIEW_PORT=8007` |

**actions на Node 24 (FR-035, п.8 стандарту флоту):** `actions/checkout@v6` (SHA d23441a4…), `actions/setup-python@v6`
(SHA ece7cb06…), `actions/setup-node@v6` (SHA 24997072…) — завантажені й відпрацювали; у журналі 0 попереджень
про застарілість / Node 20. **`actions/setup-python@v6` підтверджено реальним прогоном.**

Імена перевірок для ruleset `master` (T015): `lint`, `test (3.12)`, `test (3.13)`, `build`, `browser`.

До Phase 3 master оновлюється перемоткою (вказівка диригента); PR і авто-merge — після захисту master (T018).

### Розрив «push у master без перевірок» — закрито тимчасово (2026-09-11)

Після 1f0c97a `ci.yml` (контракт: `push` з `branches-ignore: [master]`) на master не запускався, а `release.yml`, що
викликає його на master, ще немає; сесія видалення AWS пушить у master напряму. Рішення диригента: закрити одразу.
Зроблено: `push` у `ci.yml` тимчасово без фільтра гілок (master теж). Інваріант у `tests/test_workflows.py`
(`test_every_master_push_is_checked`): поки `release.yml` не викликає `ci.yml` — push не фільтрується; щойно
викликає — обов'язковий `branches-ignore: [master]`. `release.yml` одразу не ставиться: перший тег `v0.5.0` — лише
після правила тегів (Phase 3, tasks.md «Dependencies»).

Прогін [34613440508](https://github.com/minyaylo007/aluma-table/actions/runs/34613440508) — push у master `66350c0`:
lint, test (3.12), test (3.13), build, browser — усі success. Розрив закрито; диригент прийняв 08aebaa і 66350c0.

## Phase 4 — кожне злиття публікує версію (без T030)

### Локально (2026-09-11)

| Перевірка | Результат |
|---|---|
| `tests/test_next_version.py` до `scripts/next_version.py` | червоний (модуля немає); після — 12 OK |
| `tests/test_release_build.py` до `scripts/release_build.py` | 12 червоних із 13; після — 13 OK (дві збірки HEAD — побайтно один архів; MANIFEST покриває всі файли; `data/`, `dump`, `.env`, `infra/samconfig.toml` — відмова до `build.py`) |
| `tests/test_health_version.py` до правки `api/handler.py` | 5 червоних із 7; після — 7 OK (`git_sha` — повний sha або `null`; `/admin` — `v0.5.0`, не `vv0.5.0`; старий `0.4.0-box` — `v0.4.0-box`) |
| `ReleaseYmlTests` + `test_every_master_push_is_checked` | зелені з `release.yml`; `ci.yml` знову `branches-ignore: [master]` |
| `python -m unittest discover -s tests -t .` | `Ran 324 tests … OK` |
| `ruff check .` | `All checks passed!` |
| YAML обох workflow (PyYAML, лише розбір) | ci.yml: browser, build, lint, test; release.yml: checks, release |

Вимикач релізів (рішення диригента, contracts/workflows.md): `release` лише при `vars.RELEASES_ENABLED == 'true'`.
Змінну НЕ створено — це налаштування репозиторію, вмикається пунктом Phase 3 після рішення власника.

### GitHub Actions

Прогін [34614386303](https://github.com/minyaylo007/aluma-table/actions/runs/34614386303) — workflow `Release`,
push у master `bcb9328`, 15:08:55–15:10:42Z (≈ 2 хв). Інших прогонів на цей коміт немає: `ci.yml` master пропускає.

| Завдання | Висновок |
|---|---|
| `checks / lint` | success |
| `checks / test (3.12)` | success |
| `checks / test (3.13)` | success |
| `checks / build` | success |
| `checks / browser` | success |
| `release` | **skipped** — змінної `RELEASES_ENABLED` немає |

Після прогону: тегів у репозиторії — 0 (`gh api repos/…/tags`), релізів — 0 (`gh release list`). Вимикач працює:
master перевіряється `release.yml`, версія не випускається. T030 (перший реліз `v0.5.0`) — після Phase 3.

Прогін 34614676074 (Release, push у master `7ada1ab`, лише документи): checks — 5 × success, release — skipped.

## Phase 5 — агент і деплой, локальна частина (T031–T037; T038–T041 — після Phase 3 і «так»)

Дозвіл диригента: лише файли в репозиторії. На машині нічого не ставилось і не запускалось; `/opt/ihor/aluma-table`,
`/srv/aluma`, `~/.config/systemd/user` не чіпались.

| Перевірка | Результат |
|---|---|
| `tests/test_pull_agent.py` до `deploy/agent/pullagent.py` | червоний (модуля немає); після — 31 OK |
| `tests/test_user_units.py` до правки юнітів | червоні; після — 12 OK |
| `DeployYmlTests` до `deploy.yml` | червоні; після — зелені; `release.yml`: checks → release → deploy (за release, тож за вимикачем) |
| Мутації агента в пам'яті (файл не змінювався) | MANIFEST/RELEASE.json не звіряються — 3 червоних; ізоляцію оточення `ls-remote` прибрано — 1; без повернення попередньої версії — 4; статика не звіряється — 1; блокування ігнорується — 1; контроль — 0 червоних із 31 |
| `python -m unittest discover -s tests -t .` | `Ran 375 tests … OK` |
| `ruff check .` | `All checks passed!` |
| YAML (PyYAML, лише розбір) | ci.yml, release.yml (checks, deploy, release), deploy.yml (deploy) |

Прогін 34616141687 (Release, push у master `ebc8261`): checks — 5 × success; release — skipped; deploy — skipped
(стоїть за release, отже й за вимикачем випуску). Диригент прийняв Phase 5 локально.

Уточнення до контракту: крім `github.com` і `objects.githubusercontent.com`, агент дозволяє переадресацію скачування
на `release-assets.githubusercontent.com` — туди GitHub зараз віддає файли релізів; інші хости (зокрема REST API)
відхиляються (`redirect_allowed`, тест `test_j_redirect_policy`). Сам агент запитує лише `https://github.com/…` і
`http://127.0.0.1:8005/…`.

## Phase 6 — відкат однією дією, локальна частина (T042–T043; T044 — після Phase 3)

Рішення диригента 2026-09-11 (варіант «в»): відкат **не** за вимикачем випуску — вимикач вимикають саме при поганій
версії; випуск і відкат зупиняються незалежно. `rollback.yml` щось робить лише коли `refs/heads/production` уже
існує (її створить перший деплой після Phase 3 і T040); немає — `validate` успішно завершується з «nothing to roll
back», `deploy` не запускається, репозиторій не змінюється. Лише `workflow_dispatch`.

| Перевірка | Результат |
|---|---|
| `RollbackYmlTests` до `rollback.yml` | 8 червоних із 8; після — 8 OK |
| `python -m unittest discover -s tests -t .` | `Ran 383 tests … OK` |
| `ruff check .` | `All checks passed!` |
| YAML (PyYAML) | rollback.yml: validate, deploy; тригер — лише workflow_dispatch |

Порядок у `validate`: формат `vX.Y.Z` → є `refs/heads/production` (інакше вихід 0 «відкатувати нічого») → тег →
`aluma-vX.Y.Z.tar.gz` і `SHA256SUMS` у релізі (інакше відмова до деплою, FR-023). `validate` без прав на запис;
`deploy` — той самий `deploy.yml`, що й після релізу.

### Для `docs/DELIVERY.md` (T046) — вимоги диригента

1. Прямо: **відкат доступний завжди, коли агент установлений, навіть при вимкненому випуску**.
2. `ihor-aluma-deploy.service` має `SuccessExitStatus=1 2 3 4 5` (щоб таймер гарантовано продовжував цикл), тож
   systemd провалів агента не показує. Описати, де вони видні: журнал агента `state/deploy.log` і journald
   (`journalctl --user -u ihor-aluma-deploy`), `state/failed.json`, `pullagent.py --status`, статус деплою в
   окруженні `production` на GitHub (наглядач ставить failure по таймауту).

## Phase 7 — документи процесу (T045–T050)

Сесія «🪵 ALUMA · реализация: документы выпуска и деплоя (001, Phase 7)», 2026-09-12, worktree
`aluma-001-phase7` від `3789f0c`. Чернетку попередньої сесії (сім файлів, не закомічена, дерево
`aluma-001-release-pipeline` на `5685b50`) забрано копіюванням і перевірено проти фактів 12.09.

| Перевірка | Результат |
|---|---|
| `python -m unittest discover -s tests -t .` (venv поза деревом, 3.12.3) | `Ran 395 tests … OK` |
| `tests/test_delivery_doc.py` окремо | `Ran 12 tests … OK` |
| `ruff check .` | `All checks passed!` |
| `python3 build.py` | код 0, `PREVIEW build`, 116 файлів |
| доказ, що нові перевірки падають (псування текстів **у пам'яті**) | `test_aws_is_gone_not_in_progress` і `test_docs_do_not_claim_aws_is_still_there` — 2 червоних із 2 |

**Два стани в документах** (рішення диригента 12.09, п.1). `docs/DELIVERY.md`, `CLAUDE.md`, `deploy/README.md`
скрізь розділяють «як зараз» (клон `563edc8`, юніти поставлені руками, health `0.4.0-box`, вимикач випуску
вимкнений) і «після установки агента (T040)» (`releases/`/`current`, юніти з `current/`, агент). Майбутня схема
ніде не подана як діюча; непідтверджене живою системою позначене «не перевірено, після Phase 3» і зібране в
розділі «Розрив зі стандартом флоту». Тест `test_two_states_are_explicit` цього вимагає.

**Відкат** (п.2). `docs/DELIVERY.md` §8 першим рядком: відкат доступний завжди, коли агент установлений, навіть
при вимкненому випуску — вимикач випуску його не зупиняє. §11 перелічує, де видні провали агента попри
`SuccessExitStatus=1 2 3 4 5`: `state/deploy.log`, `journalctl --user -u ihor-aluma-deploy`, `state/failed.json`,
`pullagent.py --status`, статус деплою в окруженні `production`.

**AWS** (п.3). Розділ «Ресурси» — за фактом: старого AWS ALUMA не залишилось (стек `fx-table` і таблиці `fx_*`
11.09 15:08–15:28Z, решта 12.09 06:11–06:14Z, `docs/AWS-TEARDOWN.md`, коміт `3789f0c`); єдиний відкладений кінець —
секрет `aluma/admin-credentials`, зникає 2026-09-19. `docs/AWS-TEARDOWN.md` і `docs/aws-teardown/` не чіпались.

**Що в чернетці було невірним** (писалась до 3789f0c): «AWS видаляється» в трьох шапках; «старий AWS-стек
`fx-table` — видаляється» в таблиці оточень; «Після видалення AWS (11.09)» — насправді 11–12.09; `infra/` як
«стек видаляється». Додатково виправлено вже несправжні твердження поруч: у `docs/CUTOVER-CHECKLIST.md` — «root і
Caddy тільки Денис» (блок `table` 11.09 поставили ми, `OWNER-RULES` п.20) і підсумок «НЕ перевірено», де крок 7
і пачка `switch.json` значились невиконаними; у `deploy/README.md` — «`/srv/aluma` ще нема» і `box_env.py`, що
«пише з живих Lambda». Опечатка «неизменні» → «незмінні».

**Не робилось** (поза Phase 7 і без «так» власника): нічого не ставилось і не запускалось на машині,
`/opt/ihor/aluma-table`, `/srv/aluma`, `~/.config/systemd/user`, `~/.config/aluma` не чіпались; налаштування
GitHub не змінювались; Caddy не запускався й не перезавантажувався; слухаючих процесів не піднімалось.

**Прогін на GitHub після злиття Phase 7** (push у `master`, `fcb7282`, 2026-09-12 06:32:48Z, прогін
[34678409442](https://github.com/minyaylo007/aluma-table/actions/runs/34678409442)): `Release` — success;
`checks / lint` 8 с, `checks / test (3.12)` 31 с, `checks / test (3.13)` 33 с, `checks / build` 8 с,
`checks / browser` 1 хв 47 с — усі зелені; `release` і `deploy` — skipped (змінної `RELEASES_ENABLED` немає),
тегів і релізів як не було, так і нема. Тобто вимикач випуску тримає, а перевірки на кожен push у `master`
працюють. Перевірку «деплой пройшов success» (T050) робити нема на чому — вона лишається на T030/T041.
