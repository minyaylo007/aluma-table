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

Прогін [34608006392](https://github.com/minyaylo007/aluma-table-archive-2026-09/actions/runs/34608006392) — подія `push` у гілку
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

Прогін [34613440508](https://github.com/minyaylo007/aluma-table-archive-2026-09/actions/runs/34613440508) — push у master `66350c0`:
lint, test (3.12), test (3.13), build, browser — усі success. Розрив закрито; диригент прийняв 08aebaa і 66350c0.

## Phase 3 — публікація репозиторію і захист master (2026-09-12)

### Чому публікується НОВИЙ репозиторій, а не цей (заміна T017)

Власник 12.09: GitHub Pro не купуємо, репозиторій робимо публічним. Серверний захист `master` на free-плані є лише
в публічному репозиторії. Але історію цього репозиторію публікувати не можна: у ній описи слабких місць машини
(категорія `host_security_detail`, `secret-scan-report.md` розділ В) і номер облікового запису AWS в ARN, а
прибрати їх з історії можна лише переписуванням, яке заборонене (конституція VI, force-push — ніколи).

Рішення диригента: публічним стає **новий** репозиторій `minyaylo007/aluma-table` з чистою історією — поточне
дерево `master` одним початковим комітом; цей репозиторій перейменовується в приватний архів
`aluma-table-archive-2026-09` (там і лишаються всі 100+ старих sha). OWNER-RULES п.23 — саме ця процедура.

### Чистка дерева перед знімком (коміти `2f76919`, `84d95dc`)

`2f76919` — з поточних файлів прибрано все, що ловлять правила `host_security_detail` (7 збігів) і
`aws_arn_account` (36): права й імена користувачів IAM сусідніх проєктів, керуючий інтерфейс спільного
веб-сервера, адміністративні права користувача машини, номер облікового запису AWS. Сенс документів збережено,
у кожному зачепленому файлі — помітка про маскування й посилання на архів.

Маскування: `000000000000` там, де номер стоїть окремо (у т. ч. в назвах бакетів), і `<account>` **у складі ARN**.
Заглушка з 12 нулів усередині ARN критерію «`aws_arn_account` 0» не дає — правило ловить будь-які 12 цифр після
регіону, і сам проєкт це вже враховує: в `tests/test_secret_scan.py` синтетичний ARN склеєний з частин, щоб файл
тесту не був знахідкою. Правило не ослаблювалось (рішення диригента на S1). Той самий вигляд у константі `CERT`
`scripts/aws_inventory.py`, щоб `compare()` і знімки `docs/aws-teardown/*.json` лишились сумісні.

`84d95dc` — `.claude/cc10x/*` більше не відслідковується (пам'ять помічника, не авторитетна, `CLAUDE.md` §10);
тека в `.gitignore`, старі копії лишаються в архіві.

**Скани по ДЕРЕВУ** (не по історії): `git archive HEAD` → одноразовий репозиторій з одного коміту (577 файлів) →
обидва сканери по ньому.

| Сканер | Результат |
|---|---|
| `scripts/secret_scan.py` | `host_security_detail` **0**, `aws_arn_account` **0**. Разом 107: `env_secret` 10, `json_pii` 5, `phone_il` 53, `phone_ua` 37, `telegram_bot_token` 2 — усе група Б з `secret-scan-report.md`: публічний контакт бізнесу в `i18n/*.json`, регулярки розбору телефону в `api/handler.py`, синтетика тестів, імена змінних без значень. Критерій приймання (рішення диригента на S1): дві категорії по нулю, група Б лишається |
| gitleaks 8.30.1, режим `dir` по дереву | **0** — «no leaks found». Бінарник поза репозиторієм, sha256 `551f6fc8…70eb` — той самий, що звірений з `checksums` релізу вище в цьому файлі. Режим історії (`--log-opts`) сторож сесії відхиляє як git-операцію поза worktree — для дерева режим `dir` еквівалентний |

`ruff` — All checks passed; `unittest` — Ran 417 … OK; `python3 build.py` — exit 0.

### T015. Правила як файли — задумано п'ять, застосовано три

**Задум.** Обхід (`bypass_actors`) у GitHub задається на **весь** ruleset, не на окреме правило, а R4 вимагає різного
обходу для різних дій: тег ставить конвеєр, але переписати чи видалити випущену версію не може ніхто. В одному файлі
так не розділити, тому спершу зроблено п'ять файлів — кожна пара розбита на «робоче» правило з обходом для застосунку
GitHub Actions (`Integration`, `actor_id` 15368, `gh api /apps/github-actions`) і «замок» без обходу взагалі
(рішення диригента 12.09): `master`, `tags-v` (`creation`, обхід Actions) + `tags-v-lock` (`update`, `deletion`, без
обходу), `production` (`update`, `non_fast_forward`, обхід Actions) + `production-lock` (`deletion`, без обходу).

**Чим це закінчилось.** GitHub відкинув обидва файли з обходом (нижче, T018–T019), тому в дереві лишились три файли —
рівно ті, що застосовані. Пара «робоче + замок» виявилась непотрібною: без можливості дати обхід «робоче» правило
або ламає конвеєр, або нічого не додає.

`tests/test_rulesets.py` — спочатку **червоний** (файлів не було): 15 errors; на п'яти файлах 21 тест зелений; після
зведення до трьох — 19. Крім вмісту кожного файлу перевіряється: перелік закритий (рівно три файли — новий без тесту
не проскочить); **обходу немає ні в одному** правилі; обов'язкові перевірки зіставляються з іменами завдань `ci.yml`
з розкриттям матриці `python-version`; `smoke` в обов'язкових перевірках немає;
`require_extra_approval_for_unattributed_changes` задано явно `false`; у замку тегів `creation` НЕ обмежений, у замку
`production` не обмежені `update` і `non_fast_forward` — бо без обходу це зламало б випуск і викат.

Доказ, що тести не зеленіють впустую — поломки **в пам'яті**, не на диску (як усюди в
`tests/README-python-tests.md`): замок з обходом → 1 червоний; сторонній обхід `RepositoryRole` замість застосунку →
1; перевірка, перейменована мимо `ci.yml` → 1; правила пари, що перекриваються → 2; `enforcement: disabled` → 1.
Плюс три червоні випадки в самих помічниках.

Окремо звірено з живим GitHub: `name`, `target`, `enforcement`, `bypass_actors`, `conditions`, набір правил і всі
параметри, які задаємо явно — **три з трьох збігаються** з файлами в дереві.

### Міграція репозиторію (12.09, замість T017 «змінити видимість цього»)

| Крок | Зроблено | Доказ |
|---|---|---|
| архів | `gh repo rename aluma-table-archive-2026-09` | `visibility` PRIVATE; `actions/permissions` → `{"enabled": false}`; опис «архів історії ALUMA до 12.09.2026, див. aluma-table». Уся стара історія лишилась там: нічого не переписувалось і не видалялось |
| новий | `gh repo create minyaylo007/aluma-table --private` | ім'я те саме, тож `origin` у `~/repos/aluma-table` і `/opt/ihor/aluma-table` уже вказує куда треба — `set-url` не потрібен |
| знімок | `git archive 84d95dc` → `git init -b master` → один коміт | `9984319`; автор і коміттер — `Ihor Minyaylo`, як у `git log` |
| виправлення | другий коміт `556731e` | див. «Урок» нижче |
| дерево | `git diff --stat 84d95dc origin/master` — **пусто**, 0 файлів | hash дерева `origin/master` = `ee62ae2f1125f943d884c51b4692d1946fad8022` — той самий об'єкт, що в `84d95dc`. 575 файлів; `dist/`, `data/`, `dump*`, `node_modules/`, `ms-playwright/`, `.venv`, `.claude/cc10x/` відсутні |
| скани | по новій історії (обидва коміти) | `secret_scan.py`: `host_security_detail` **0**, `aws_arn_account` **0**, разом 107 — група Б. gitleaks: **0** |
| CI | прогін `Release` на push `556731e` — **success** | `checks / lint`, `test (3.12)`, `test (3.13)`, `build`, `browser` — 5/5 success; `release` і `deploy` skipped (`RELEASES_ENABLED` немає). Тегів 0, релізів 0 |

**Урок: перелік заборонених шляхів — не та сама перевірка, що рівність дерева.** Перший знімок зібрався через
`git add -A` у щойно створеному репозиторії, і `-A` викинув `package-lock.json`: файл **відслідковувався**, але
підпадав під `.gitignore` (рядок лишився з часів до Playwright). Сторож у збірнику дивився лише на заборонені
шляхи — відсутній файл він не бачить у принципі. Наслідок був негайний: прогін
[34682721072](https://github.com/minyaylo007/aluma-table/actions/runs/34682721072) (коміт `9984319`) — `browser`
**failure** на `npm ci`, решта чотири success. Виправлено другим комітом (без force-push: рішення диригента —
нічого не видаляти, «одним комітом» у OWNER-RULES п.23 — про чисту історію, а не про арифметику), а сам збірник
тепер перед пушем порівнює **hash дерева** знімка з hash дерева джерела й відмовляється при розбіжності.
Інваріант перенесений у дерево: `tests/test_workflows.py::TrackedFilesAreNotIgnoredTests` — жоден
відслідковуваний файл не підпадає під `.gitignore`, і `npm ci` має свій lock-файл. До правки `.gitignore` тест
червоний і показує рівно `package-lock.json`.

`gitleaks` **не читає** `package-lock.json` узагалі — у нього власний список пропусків для lock-файлів
(«scanned ~0 bytes», навіть якщо подати файл окремо в порожній теці). Тому перевірено іншим: `secret_scan.py`
пройшов по ньому в історії — 0 знахідок; греп по `_auth`, `authToken`, `npm_token`, `:_password` — 0 при
204 записах `resolved`.

**Робочі копії.** `~/repos/aluma-table`: доданий remote `archive` → архівний репозиторій (конфіг спільний для
всіх worktree), `git fetch origin` зроблений. `/opt/ihor/aluma-table`: доданий **лише** remote `archive`
(дописаний у `.git/config` текстом, копія конфігу до правки — поза репозиторієм); `fetch` не робився
(`refs/remotes/` містить тільки `origin`), `checkout` і `reset` — ні, `HEAD` як був — `563edc8`, сервіс не
чіпався.

### T017 + B.6. Налаштування репозиторію і видимість

Порядок довелось поміняти проти задання, і причина варта запису: **auto-merge і сканування секретів на приватному
репозиторії особистого акаунта недоступні.** `PATCH` з `allow_auto_merge=true` молча повертав `false`, а сканування —
`422 «Secret scanning is not available for this repository»`. Після зміни видимості обидва ввімкнулись з першого разу.
Тому T017 виконаний двома заходами: спершу те, що можна на приватному, потім B.6, потім решта.

| Налаштування | Значення |
|---|---|
| `allow_squash_merge` / `allow_merge_commit` / `allow_rebase_merge` | `true` / `false` / `false` |
| `delete_branch_on_merge` | `true` — перевірено вживу: гілка `phase3-rulesets` після злиття зникла сама |
| `allow_auto_merge` | `true` (лише після `public`) |
| `secret_scanning` / `secret_scanning_push_protection` | `enabled` / `enabled`. Push protection вмикається **окремим** викликом: разом зі скануванням в одному `PATCH` лишається `disabled` |
| `secret-scanning/alerts` | **0** (T021 п.4) |
| незмінні релізи | **недоступно**: поля `immutable_releases` API не має взагалі (`has("immutable_releases")` → `false`), `PATCH` його молча ігнорує. Роль виконує ruleset `tags-v-lock` — він сильніший: тег не перепише навіть конвеєр |

Видимість: `gh repo edit minyaylo007/aluma-table --visibility public` — gh 2.45 відпрацював без
`--accept-visibility-change-consequences` (цього флага в 2.45 немає), `PATCH` не знадобився. Після зміни:
`visibility: public`, архів — `private`. Перед зміною скани прогнані ще й по дереву **гілки** (вона теж ставала
публічною): `host_security_detail` 0, `aws_arn_account` 0, gitleaks — no leaks found.

### T018–T019. Правила: відмова GitHub і запасний варіант R4

Ризик, який R4 прямо позначав як неперевірений, реалізувався. Обидва файли з обходом для застосунку Actions
відкинуті однаково:

```
POST /rulesets --input .github/rulesets/tags-v.json     → 422
POST /rulesets --input .github/rulesets/production.json → 422
"Actor GitHub Actions integration must be part of the ruleset source or owner organization"
```

У особистому репозиторії застосунок Actions у `bypass_actors` дати не можна — він мусить бути встановлений в
організації-власнику. Організацію не заводимо (рішення диригента 12.09). Діє запасний варіант R4 — **три правила,
обходу немає ні в одному**:

| ruleset | id | ціль | правила | `enforcement` |
|---|---|---|---|---|
| `master` | 23027162 | `refs/heads/master` | `pull_request`, `required_status_checks`, `non_fast_forward`, `deletion` | active |
| `tags-v-lock` | 23027575 | `refs/tags/v*` | `update`, `deletion` | active |
| `production-lock` | 23027579 | `refs/heads/production` | `deletion` | active |

Чому конвеєр не зламався: `release.yml` тег **створює** (`creation` не обмежений), `deploy.yml` двигає
`refs/heads/production` (`update` і `non_fast_forward` не обмежені), і ні той, ні той нічого не видаляє — а видалення
заборонене всім. Що стало слабше за задум: людина може руками поставити тег `v*` або зсунути `production`.
Компенсація — та, що R4 і передбачав: агент ставить лише коміт опублікованого тега з повним набором файлів релізу й
зійшлими сумами, тому руками можна викотити лише вже випущену версію. Формулювання для `docs/DELIVERY.md` §9 —
диригента, 12.09.

Файли в дереві зведені до того, що справді застосовано (`tags-v.json` і `production.json` видалені як неможливі), і
звірені з GitHub полем за полем — `name`, `target`, `enforcement`, `bypass_actors`, `conditions`, набір правил і всі
параметри, які ми задаємо явно: **три з трьох — збігається**.

**Параметр, якого ми не заказували.** У відповіді `POST /rulesets` видно
`require_extra_approval_for_unattributed_changes: true` — GitHub підставляє його сам, якщо не задати. З ним PR, у
якому є коміт із автором без прив'язаного акаунта GitHub (у нас це трейлер `Co-Authored-By` помічника), висить в
очікуванні схвалення, і авто-merge не працює, хоча схвалень потрібно нуль. Задано явно `false`, закріплено тестом,
правило оновлене тим самим файлом (`PUT /rulesets/23027162`).

### T020. Окруження `production`

`PUT /environments/production` — `deployment_branch_policy`: `protected_branches` `false`,
`custom_branch_policies` `true`; політика веток рівно одна: `branch: master` (`total_count` 1). Змінна
`ALUMA_HEALTH_URL` = `https://table.central-aparts.store/api/fx/health`; адреса жива — `GET` віддав
`{"ok": true, "version": "0.4.0-box"}`. Синтаксис для протоколу: `-f 'deployment_branch_policy[protected_branches]=false'`
API відкидає (рядок замість boolean) — потрібен JSON через `--input`.

### T021. Живі перевірки

| # | Що перевіряли | Результат |
|---|---|---|
| 3 | прямий push у `master` з гілки | **відмова сервера**: `GH013: Repository rule violations found for refs/heads/master` — «Changes must be made through a pull request», «5 of 5 required status checks are expected», `! [remote rejected] HEAD -> master` |
| 2 | зелений PR вливається сам | PR [#1](https://github.com/minyaylo007/aluma-table/pull/1): авто-merge `SQUASH`, перевірки 5/5 success, злився сам 08:37:19Z, merge-коміт `78201d2`, гілка прибрана, заголовок squash = заголовок PR |
| 1 | падаючий PR НЕ вливається | PR [#2](https://github.com/minyaylo007/aluma-table/pull/2), і червоний він **по-справжньому**: у `.gitignore` рядок `test-results/` стояв двічі, а новий тест цього не пробачає. Перший коміт: `test (3.12)` і `test (3.13)` FAILURE, `lint`/`build`/`browser` success, `mergeState` BLOCKED, `state` OPEN — авто-merge був увімкнений і НЕ влив. Другий коміт прибрав дублікат → 5/5 success → злився сам 08:42:49Z, `f2235ed`. У `master` при цьому не лишилось нічого зайвого, а інваріант лишився корисний |
| 4 | `secret-scanning/alerts` | **0** |
| — | тег `v*` не перезаписати | `PATCH git/refs/tags/v0.0.0-ruleset-test force=true` → `422 «Cannot update this protected ref.»` |
| — | тег `v*` не видалити | `DELETE git/refs/tags/v0.0.0-ruleset-test` → `422 «Cannot delete this tag»` |

Пробний тег створено **до** застосування `tags-v-lock` — після нього людина тег уже не поставить. Прибирання двома
сусідніми викликами, між ними нічого: `enforcement` до — `active`; `PUT` з `disabled` → `disabled`; `DELETE` тега →
код 0; `PUT` тим самим файлом → `active`. Підсумок: тегів у репозиторії **0**, усі три правила `active`.

Спосіб перевірки перезапису тега — окремо: `git push --force` тут не виконувався, цю форму команди локальний сторож
`claude-guard` забороняє вовсі, і обходити його командою сесія не стала. Перевірка зроблена через REST API на
одноразовому тезі, створеному за хвилину до того; очікуваним результатом була саме відмова.

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

Прогін [34614386303](https://github.com/minyaylo007/aluma-table-archive-2026-09/actions/runs/34614386303) — workflow `Release`,
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
[34678409442](https://github.com/minyaylo007/aluma-table-archive-2026-09/actions/runs/34678409442)): `Release` — success;
`checks / lint` 8 с, `checks / test (3.12)` 31 с, `checks / test (3.13)` 33 с, `checks / build` 8 с,
`checks / browser` 1 хв 47 с — усі зелені; `release` і `deploy` — skipped (змінної `RELEASES_ENABLED` немає),
тегів і релізів як не було, так і нема. Тобто вимикач випуску тримає, а перевірки на кожен push у `master`
працюють. Перевірку «деплой пройшов success» (T050) робити нема на чому — вона лишається на T030/T041.
