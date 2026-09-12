# Доставка ALUMA: оточення, гілки, перевірки, релізи, викат, відкат

Процес проєкту за стандартом флоту (`~/maestro/cicd/PLAN.md`, OWNER-RULES п.22); ALUMA — пілот (SDD
[`specs/001-release-pipeline/`](../specs/001-release-pipeline/spec.md)). Тут — карта й правила; подробиці лежать за
посиланнями: [`CLAUDE.md`](../CLAUDE.md) (архітектура §3, команди §8, порядок SDD — розділ «SDD»),
[`deploy/README.md`](../deploy/README.md) (машина, юніти, Caddy, порти),
[контракти конвеєра й агента](../specs/001-release-pipeline/contracts/workflows.md),
[інваріанти](../.specify/memory/constitution.md).

**Стан на 2026-09-12. Два стани, і кожен факт нижче підписаний, до якого він належить:**

- **Як зараз** — сервіс на машині працює з клону `/opt/ihor/aluma-table` на коміті `563edc8` (detached HEAD) з
  юнітами, поставленими руками; health — `0.4.0-box` без `git_sha`. Репозиторій приватний, правил гілок немає,
  вимикач випуску вимкнений — конвеєр перевіряє, але нічого не випускає й не викочує.
- **Після установки агента (T040)** — версії з GitHub ставить агент: каталоги `releases/vX.Y.Z` + `current`, юніти з
  `current/`, health показує номер і sha версії. Це настає після Phase 3 (рішення власника про публікацію репозиторію,
  правила, окруження) і «так» власника на першу установку (T040).

Позначка **«не перевірено, після Phase 3»** — твердження, яке ще не звірене з живою системою; усі такі — і в розділі
«Розрив зі стандартом флоту».

## 1. Оточення

| Що | Як зараз | Після установки агента (T040) |
|---|---|---|
| **production** = машина ace-main | гості на коробці: DNS `table.central-aparts.store` сюди з `2026-09-11T12:42:31Z` (коміт `a7e9c64`, [журнал](CUTOVER-CHECKLIST.md)); `table-new` — теж сюди | те саме |
| API | `ihor-aluma-api` (користувацький юніт), gunicorn `127.0.0.1:8005`, код і `.venv` — клон `563edc8` | той самий юніт, код — `/opt/ihor/aluma-table/current` → `releases/vX.Y.Z`, venv — `venvs/<hash>` |
| статика | `/srv/aluma`, опублікована руками з `dist/` клону | `/srv/aluma`, публікує агент |
| окруження `production` у GitHub | **немає** (з'явиться з першим деплоєм) | правило «лише `master`», змінна `ALUMA_HEALTH_URL` = `https://table.central-aparts.store/api/fx/health` — не перевірено, після Phase 3 |
| staging / превʼю | немає | немає |
| старий AWS-стек `fx-table` | **видалений** 11–12.09 (розділ 7) — гостей віддає лише коробка | — |

## 2. Гілки, PR, коміти

- Основна гілка — **`master`**. Сесії — у своїх git worktree; `git pull --rebase` перед роботою; `git add` **явним
  списком**, ніколи `-A`; `git push --force` — ніколи; коміт після кожного кроку, пуш одразу (п.22).
- **Як зараз** (до Phase 3): правил немає; сесії вливаються в `master` перемоткою (rebase на `origin/master` +
  fast-forward). Кожен push у `master` запускає перевірки через `release.yml` (розділ 3).
- **Після Phase 3** (не перевірено, після Phase 3): ruleset `master` — лише через PR, обов'язкові перевірки `lint`,
  `test (3.12)`, `test (3.13)`, `build`, `browser`, 0 схвалень, **без обходу** (і для власника), заборона force-push і
  видалення; метод злиття — squash, заголовок PR = повідомлення коміту в стилі проєкту `type(scope): опис`; авто-merge
  після зелених перевірок. Шлях усіх сесій: гілка → PR → авто-merge.
- Мітки PR: `release:minor`, `release:major` — підняти minor / major (розділ 4); без мітки — patch.
- Коміти — українською, у стилі `git log` (`feat(001): …`, `fix(ci): …`, `docs(…): …`).

## 3. Перевірки (CI)

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml): push у будь-яку гілку, крім `master`; кожен PR у `master`;
і як частина [`release.yml`](../.github/workflows/release.yml) на кожен push у `master` (завдання `checks`, у GitHub
видно як `checks / lint` тощо). Права — `contents: read`; новий прогін тієї ж гілки скасовує старий, на `master` —
ніколи. Секретів CI не використовує.

| Завдання | Що перевіряє | Залежності (лише з файлів) |
|---|---|---|
| `lint` | `ruff check .` (E9 + F, `ruff.toml`); `node --check` зібраного `dist/assets/*.js` і `tests/*.js` | `requirements-lint.txt` |
| `test (3.12)`, `test (3.13)` | `python -m unittest discover -s tests -t . -v` — увесь набір; 3.12 — як на машині, 3.13 — як у Lambda | `api/requirements.txt`, `tests/requirements.txt` |
| `build` | `python build.py` (preview, без Pillow) двічі — суми `dist/` однакові | — |
| `browser` | `tests/redesign.spec.js` (повністю мокнутий) на `PREVIEW_PORT=8007`, Chromium | `package-lock.json` |

**Що НЕ запускається і чому:** `tests/smoke.spec.js` — пише в сховище (тестова заявка, `page_view`), тому лише
вручну й лише проти локального стеку з одноразовою базою (`CLAUDE.md` §6). Lighthouse — не в CI.

**Версії actions (FR-035, для шаблону флоту):** `actions/checkout@v6`, `actions/setup-python@v6`,
`actions/setup-node@v6` — працюють на Node 24, у журналі 0 попереджень про застарілість; `actions/setup-python@v6`
підтверджено прогоном [34608006392](https://github.com/minyaylo007/aluma-table/actions/runs/34608006392).

Локально перед пушем (venv поза деревом, `CLAUDE.md` §8): `ruff check .`, повний `unittest`, `python3 build.py`;
при правці `site/` — Playwright на `127.0.0.1:8007`. Дивитися прогони: `gh run list --limit 5`, `gh run view <id>`,
`gh run view <id> --log-failed`.

## 4. Релізи й версії

- Номер — SemVer `vX.Y.Z`, перша версія `v0.5.0`; за замовчуванням +patch, мітки злитого PR `release:minor` /
  `release:major` — +minor / +major ([`scripts/next_version.py`](../scripts/next_version.py)).
- `release.yml`: `checks` зелені → `release`: номер → [`scripts/release_build.py`](../scripts/release_build.py) → тег на
  коміт → GitHub Release з `aluma-vX.Y.Z.tar.gz` і `SHA256SUMS` і списком змін → `deploy`. Червоні перевірки — ні
  тегу, ні релізу, ні деплою.
- Архів відтворюваний (той самий коміт — ті самі байти): дерево коміту, `dist/` (preview), `RELEASE.json`,
  `RELEASE.env` (`APP_VERSION`, `GIT_SHA` — не секрети), `MANIFEST.sha256`. Живих даних, `.env`, `samconfig.toml`,
  `node_modules` у ньому бути не може — збірка відмовляє.
- **Вимикач випуску `RELEASES_ENABLED`** (змінна репозиторію): `release` і за ним `deploy` виконуються лише при
  `true`. **Як зараз** — змінної немає: на кожен push у `master` лише перевірки, `release`/`deploy` — skipped (прогони
  [34614386303](https://github.com/minyaylo007/aluma-table/actions/runs/34614386303),
  [34616141687](https://github.com/minyaylo007/aluma-table/actions/runs/34616141687)); тегів і релізів — 0.
  Вмикається пунктом Phase 3 разом із правилом тегів: `gh variable set RELEASES_ENABLED --body true`. Зупинити випуск
  без правки коду: `gh variable delete RELEASES_ENABLED`. **Відкат вимикач не зупиняє** (розділ 8).
- Незмінність: теги `v*` створює лише конвеєр, перезаписати й видалити — ніхто (ruleset); незмінні релізи — якщо
  налаштування доступне. Не перевірено, після Phase 3.
- Перевірити реліз руками (не перевірено, після Phase 3):
  `curl -fsSLO https://github.com/minyaylo007/aluma-table/releases/download/vX.Y.Z/SHA256SUMS`, те саме для архіву,
  `sha256sum -c SHA256SUMS`.

## 5. Викат

**Як зараз.** Автодеплою немає: агент не встановлений, вимикач випуску вимкнений. Код на машині — клон `563edc8`;
будь-яке оновлення машини — це викат поза конвеєром, **лише з «так» власника** (конституція VI). Історична ручна
процедура — [`docs/CUTOVER-CHECKLIST.md`](CUTOVER-CHECKLIST.md), кроки 1 і 6 (там позначено «замінено»).

**Після установки агента (T040)** — не перевірено, після Phase 3:

1. Злиття в `master` → `release.yml`: перевірки → реліз `vX.Y.Z`.
2. [`deploy.yml`](../.github/workflows/deploy.yml) (окруження `production`): тег і обидва файли релізу є → git-посилання
   `refs/heads/production` пересувається на sha тегу → наглядач до 15 хв опитує публічний health (`ALUMA_HEALTH_URL`)
   і ставить деплою «success», лише коли `version` = тег **і** `git_sha` = повний sha; інакше — «failure». Новіший
   деплой скасовує очікування старішого.
3. Агент [`deploy/agent/pullagent.py`](../deploy/agent/pullagent.py) (таймер `ihor-aluma-deploy.timer`, раз на хвилину,
   без облікових даних GitHub): анонімно читає посилання протоколом git (ізольований git, без помічників облікових
   даних, REST API не використовує) → скачує реліз за прямими посиланнями → звіряє `SHA256SUMS`, `MANIFEST.sha256`,
   `RELEASE.json` → venv за хешем вимог → юніти версії → атомарне перемикання `current` → `systemctl --user restart
   ihor-aluma-api` → локальний health (номер і sha, до 60 с) → `rsync` статики в `/srv/aluma` і звірка сум.
   Провал будь-якого кроку після перемикання — автоматичне повернення попередньої версії (розділ 8).
4. Статус — у GitHub: Environments → `production` (активна версія) і сам деплой.

Команди агента на машині (після T040): `… /current/deploy/agent/pullagent.py --config … /current/deploy/agent/aluma.json
--dry-run` (що буде поставлено, «було → стане», нічого не змінює), `--status` (стан і останні 5 подій журналу).
Контракт агента — [agent-cli.md](../specs/001-release-pipeline/contracts/agent-cli.md).

## 6. Секрети

- **GitHub Secrets — порожні**, і не потрібні: перевірки, реліз і деплой — вбудованим `GITHUB_TOKEN`; права на запис
  (`contents: write`) — лише в завданнях `release` і `deploy`.
- Змінні GitHub (не секрети): `RELEASES_ENABLED` (репозиторій) і `ALUMA_HEALTH_URL` (окруження `production`) —
  **як зараз обидві не створені**.
- Машина: `~/.config/aluma/aluma.env` — файл `0600`, тека `0700`, поза git; пише [`scripts/box_env.py`](../scripts/box_env.py),
  склад — [`deploy/aluma.env.example`](../deploy/aluma.env.example). Агент його **не читає**; номер і sha версії
  приходять окремим `current/RELEASE.env` (юніт читає його після `aluma.env`).
- Агент без облікових даних GitHub; токен `gh`, залогінений на машині, агенту використовувати заборонено — git
  агента ізольований (тест `tests/test_pull_agent.py`).
- Перед публікацією репозиторію перевірено всю історію — [secret-scan-report.md](../specs/001-release-pipeline/secret-scan-report.md)
  ([`scripts/secret_scan.py`](../scripts/secret_scan.py) + gitleaks). Значень секретів не друкувати ніде.

## 7. Ресурси

| Що | Де |
|---|---|
| машина | ace-main (Hetzner), користувач `ihor`, linger увімкнено |
| код | **як зараз:** клон `/opt/ihor/aluma-table` (`563edc8`, `770`); **після T040:** там же `releases/`, `venvs/`, `state/` (`0700`), `current` |
| жива база | `/opt/ihor/aluma-table/data/` (`0700`) — деплой і агент її не чіпають |
| статика | `/srv/aluma` (`0755`, `ihor`) |
| юніти | `~/.config/systemd/user/ihor-aluma-{api.service,purge.service,purge.timer}`; після T040 ще `ihor-aluma-deploy.{service,timer}` |
| порти | `8005` — gunicorn ALUMA, `8007` — превʼю Playwright; лише `127.0.0.1` (`~/maestro/PORTS.md`) |
| блоки Caddy | `table`, `table-new` — наші (OWNER-RULES п.20), `deploy/caddy/` |
| GitHub | `minyaylo007/aluma-table`, **приватний**; публікація — рішення власника |
| AWS | **нічого не залишилось**: стек `fx-table` з CloudFront, Lambda й API Gateway видалено 2026-09-11 15:08–15:28Z, таблиці `fx_*` там же, решта (лог-група, сертифікат ACM, CNAME валідації, артефакти SAM, секрет, змінна `AWS_ROLE_ARN`) — 2026-09-12 06:11–06:14Z; звірка «до/після» зелена — [docs/AWS-TEARDOWN.md](AWS-TEARDOWN.md) (коміт `3789f0c`). Єдиний відкладений кінець — секрет `aluma/admin-credentials`: вікно відновлення 7 днів, зникає 2026-09-19. Акаунт спільний з іншими проєктами — запис до AWS сесіям, як і раніше, заборонено (`CLAUDE.md` §9) |

## 8. Відкат

**Відкат доступний завжди, коли агент установлений, навіть при вимкненому випуску:** вимикач випуску його не
зупиняє — його вимикають саме при поганій версії. Випуск і відкат зупиняються незалежно.

- **Автоматичний** (агент, після T040): провал локальної перевірки після перемикання — повернення юнітів, `current`,
  рестарт, health і статика попередньої версії; sha проваленої — у `state/failed.json`, вона не ставиться повторно,
  доки посилання не піде на інший sha. Деплой у GitHub — «failure» за таймаутом.
- **Ручний — [`rollback.yml`](../.github/workflows/rollback.yml)** (право запису в репозиторій, запуск із `master`):
  `gh workflow run rollback.yml -f version=vX.Y.Z` → перевірка формату, тегу й обох файлів релізу (інакше відмова
  до деплою) → той самий `deploy.yml`. Назад на новішу — той самий виклик з її номером. Версія, уже розпакована на
  машині, ставиться без мережі. Не перевірено, після Phase 3 (T044, Phase 9).
- **Як зараз** (агента немає): `refs/heads/production` не існує → `rollback.yml` завершується «nothing to roll back»,
  нічого не змінюючи. Повернення машини — лише руками з «так» власника. Відкоту «назад на AWS» більше не існує:
  старий стек видалено (розділ 7), і це єдиний шлях подачі сайту.
- **З першої версії агента назад до клону `563edc8`** (після T040): точка ручного повернення записується в
  [verification.md](../specs/001-release-pipeline/verification.md) перед T040 — повернути юніти з клону
  (`WorkingDirectory=/opt/ihor/aluma-table`), `systemctl --user daemon-reload`, рестарт. Не перевірено, після Phase 3.
- **Код у `master`** — новим комітом (`git revert`), не переписуванням історії.

## 9. Розрив зі стандартом флоту

Чесний список того, чого ще немає (стандарт — `~/maestro/cicd/PLAN.md`):

1. **Захист `master`, правила тегів і посилання `production`, окруження `production`, сканування секретів GitHub** —
   не застосовані: на приватному репозиторії тарифу free правила недоступні, а публікацію власник ще вирішує
   (знахідки категорії `host_security_detail` у [secret-scan-report.md](../specs/001-release-pipeline/secret-scan-report.md)).
   Перевірки є й зелені, але обов'язковими для злиття стануть лише з ruleset. Не перевірено, після Phase 3.
2. **Автодеплой** (п.2) — код є (`release.yml` → `deploy.yml` → агент), не діє: вимикач випуску вимкнений, агент не
   встановлений (T038–T041).
3. **Релізи** (п.3) — 0; перший `v0.5.0` — після Phase 3 (T030). `/api/fx/health` уже вміє віддавати `git_sha`, але
   на машині стоїть `0.4.0-box` без нього.
4. **Відкат** (п.5) — `rollback.yml` є, на ділі не перевірений (T044, Phase 9).
5. **Перевірка реальним комітом** (п.6) — не зроблена (Phase 9).
6. **Виняток для GitHub Actions у правилах тегів і `production`** (research.md R4) — не перевірений; якщо не
   спрацює, діє запасний варіант: агент ставить лише коміт опублікованого тегу з повним набором файлів і сумами.
7. **SC-010** (агент не витрачає ліміт REST API) — доведено тестами; добовий замір — після T040.
8. **Провали агента не видні в systemd** — `SuccessExitStatus=1 2 3 4 5` (розділ 11); компенсується журналом і
   статусом деплою в GitHub.

## 10. Хто що натискає

| Хто | Що |
|---|---|
| **Конвеєр** (GitHub Actions) | перевірки на кожен push і PR; після злиття — номер, тег, реліз, пересування `production`, статус деплою |
| **Агент** (машина, після T040) | помічає нове `production`, ставить, перевіряє, публікує статику, повертає попередню версію при провалі |
| **Власник** | рішення про публікацію репозиторію (Phase 3); «так» на викат поза конвеєром (T040 і будь-яке ручне оновлення машини); налаштування репозиторію, змінні, аварійне зняття захисту; DNS |
| **«🪵 ALUMA — дирижёр»** | ставить завдання сесіям, приймає результат, номери SDD-спек; код не пише |
| **Сесії** | код і тести; зараз — перемотка в `master`, після Phase 3 — гілка → PR → авто-merge; `rollback.yml` за потреби |

## 11. Якщо щось зламалось

**Де видно провали агента.** `ihor-aluma-deploy.service` має `SuccessExitStatus=1 2 3 4 5`, щоб таймер гарантовано
продовжував цикл, — тому `systemctl --user status` показує «успіх» навіть на провалі. Дивитися:

- журнал агента — `state/deploy.log` (рядок JSON на подію: `deploy_done`, `revert_done`, `revert_failed`, `refused`,
  `source_unavailable`, `lock_busy`, поле `reason`) і journald: `journalctl --user -u ihor-aluma-deploy -n 50`;
- `state/failed.json` — sha, які агент більше не ставить, і причина;
- `pullagent.py --status` — поточна й попередня версії, останні 5 подій;
- статус деплою в GitHub: Environments → `production` (наглядач ставить «failure» за таймаутом).

Коди агента: `0` — нічого / успіх / dry-run; `1` — не вдалося, попередню повернуто; `2` — не вдалося й повернення,
**потрібна людина**; `3` — відмова до установки (ручні правки `dirty_current`, немає тегу, суми); `4` — GitHub
недоступний; `5` — триває інша установка.

- **`revert_failed` (код 2)** — машина могла лишитися на новій версії без перевірки: подивитися `--status`, health
  (`curl -s http://127.0.0.1:8005/api/fx/health`), журнал; вирішує власник.
- **`dirty_current`** — у каталозі поставленої версії руками змінено файли; агент нічого не ставить. Прибрати ручні
  правки (каталог версії не для редагування) або звернутися до власника.
- **Зламана версія агента** — запустити агента попередньої версії вручну:
  `/usr/bin/python3 /opt/ihor/aluma-table/releases/<попередня>/deploy/agent/pullagent.py --config
  /opt/ihor/aluma-table/releases/<попередня>/deploy/agent/aluma.json --once`. Не перевірено, після Phase 3.
- **GitHub недоступний або відмовив у git** — агент нічого не чіпає, пропускає цикл, пауза зростає до 10 хв (код 4).
  Ліміт REST API агент не витрачає зовсім; конвеєр працює вбудованим токеном.
- **Захист `master` довелося зняти в аварії** — лише власник: Settings → Rules → ruleset `master` → вимкнути, зробити
  потрібне, увімкнути назад і записати в журнал проєкту.
- **Треба зупинити випуск нових версій** — `gh variable delete RELEASES_ENABLED`; відкат при цьому працює.
