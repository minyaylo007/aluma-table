# ALUMA · сповіщення про заявки з проду: пакет рішення

Складено 2026-09-11. В AWS за весь час — лише читання (describe / get / list / filter-log-events /
get-function). Change set не створювався, деплою не було, у прод-API не пішов жоден POST.
Реклама йде 5–14 жовтня.

## Рекомендация

**Вариант A: выкатить бекенд master на существующую Lambda сейчас, до 5 октября, по рецепту
ниже, в тихое время и с проверкой сразу после.** Сейчас о заявке с прода не узнаёт никто: письма
выключены (`LEAD_NOTIFY_EMAIL` пустая, SES в песочнице, подтверждённых адресов 0), так что до
переезда каждая заявка лежит в `/admin` молча, а если переезд съедет за 5.10, молча пройдёт и
реклама. Выкат A проверен настолько, насколько это можно без записи в AWS. Живой фронт шлёт ровно
то, что master принимает: блокера по совместимости нет, это доказано тестом. Ни один ресурс не
идёт на замену. Секреты стека остаются прежними (UsePreviousValue). Откат кода занимает 2 минуты,
zip 0.3.0 сохранён. Ошибка стоит минут неработающей формы в тихий период (с 5 по 10 сентября — от 2 до 16
обращений к API в сутки), и её сразу видно по health и тестовой заявке. Ошибка варианта B — пропущенные
горячие лиды во время оплаченной рекламы, и её не отыграть. Два условия: выкатывать коммит не
старше `93c329c` (в нём убрана утечка токена бота в журнал, найденная этой проверкой) и строго по
рецепту через change set, а не через `scripts/deploy.sh` и не через `samconfig.toml.example`
(причины в разделе «Блокери п.4»). Переезд A не отменяет: на своей машине тот же код работает
под gunicorn с `FX_STORAGE=sqlite`.

---

## 1. Стан проду (факти, 2026-09-11)

| Що | Факт | Як перевірено |
|---|---|---|
| Код Lambda `fx-table-api` | python3.13, arm64, `LastModified 2026-09-02T10:56:28Z`, `CodeSha256 bId7pCfLlKuI6MWT1mRgnMhp6T2iZ8QzwXOE+uQJw+g=`, 10180 байт | `get-function-configuration` |
| Вміст zip | `handler.py` + порожній `requirements.txt`. `handler.py` = `c0bd150:api/handler.py` байт-у-байт, якщо не зважати на CRLF (збирали на Windows) | `get-function`, `diff --strip-trailing-cr` |
| Змінні Lambda | задані: `ADMIN_PASS ADMIN_USER APP_VERSION EDGE_SECRET EVENTS_TABLE IP_SALT LEADS_TABLE SESSIONS_TABLE SITE_DOMAIN`; **порожні: `LEAD_NOTIFY_EMAIL`, `WHATSAPP_NUMBER`** | лише імена і задано/порожньо |
| Стек `fx-table` | `UPDATE_COMPLETE`, оновлено 2026-09-02 10:56Z. 9 параметрів, NoEcho: `AdminPass`, `IpSalt`, `EdgeSecret`. Розгорнутий шаблон — це шаблон `c0bd150` (`LeadNotifyEmail`, умова `HasNotifyEmail`) | `describe-stacks`, `get-template` |
| SES | `ProductionAccessEnabled=False`, підтверджених адрес 0 | `sesv2 get-account`, `list-email-identities` |
| Журнал `/aws/lambda/fx-table-api` | retention не задано, тобто **зберігається безстроково**. З 2026-09-01: 428 викликів, 0 `unhandled`, 0 `notify_failed`, 0 помилок, 0 згадок SES | `filter-log-events`, лише лічильники |
| Фронт у проді | `/assets/app-next.ba26d2a9fb.js` = `site/assets/app-next.js` з master байт-у-байт, якщо не зважати на CR. `consentVersion: "v2"`, `<html lang>`: `he` / `en` | GET сторінок і JS, `diff --strip-trailing-cr` |

Отже, у проді **фронт новіший за бекенд**: сторінка з 09.09 (`8296742`) говорить з бекендом
0.3.0 з 02.09.

## 2. Що зміниться після викату master (FX_STORAGE=dynamodb)

`git diff c0bd150 origin/master -- api infra` плюс перевірка на moto.

**Гість (форма, події)**
- Коди й форми відповідей `/api/fx/lead` ті самі: 200 `{ok,id}`, 422 `{ok:false,errors}`,
  429 `{ok:false,error:"rate",field:"form"}`, 403 без `x-fx-edge`, 500 `internal`, ханіпот
  200 `{id:"hp"}`. **Нових кодів нема, 400 put_lead не повертає взагалі.**
- Телефон: правило те саме, яке вже виконує прод-фронт. Сервер додатково відкидає понад 15 цифр і
  не зараховує не-ASCII цифри. Раніше `\D` лишав, наприклад, арабські цифри.
- `size`/`lang`: невідоме значення пишеться як `""`, заявку не відхиляють.
- Швидкість: на кожну справжню заявку синхронно йде POST у Telegram (`timeout=5` на з'єднання і
  на читання). Зазвичай це частки секунди. Якщо Telegram завис, гість чекає `/thanks` до ~10 с
  (Lambda timeout 15 с, CloudFront 30 с). Холодний старт трохи довший: бандл ~1.1 МБ замість 10 КБ.
- Події: з'являється атрибут `attributed_at`, відповідь та сама.

**Адмінка**
- Кука підписується тим самим `ADMIN_PASS|IP_SALT`, тож відкриті сесії не злітають. Це правда
  лише за UsePreviousValue, див. рецепт.
- Рядок воронки «פתחו תלת־ממד» показується, лише якщо в діапазоні є історичні `viewer_open`,
  і тепер з позначкою «(היסטורי)».
- Таблиця лідів та сама. У шапці нова `AppVersion`.

**Власник**
- **На кожну справжню заявку приходить повідомлення в Telegram**: бот і чат ті самі, що в aparts.
  У тексті `ליד חדש — table.central-aparts.store`, ім'я, телефон, місто, колір, розмір, мова,
  сторінка, коментар, `consent_marketing`, `utm_source/utm_campaign`, час, id. Заявки з
  `x-test: 1` повідомлення **не дають** (так задумано).
- Невдача Telegram не губить лід, а пише в CloudWatch `{"event":"notify_failed",...}`, без токена
  (див. блокер 4.3).
- SES іде геть: `LEAD_NOTIFY_EMAIL` і умовний дозвіл `ses:SendEmail` з ролі (він і так був
  вимкнений умовою).

**Дані й інфраструктура**
- У нових лідах з'являються `lang` і `attributed_at`, `size` нормалізується. Старі рядки не
  чіпаються, старий код такі рядки читає.
- Три таблиці отримують `DeletionPolicy/UpdateReplacePolicy: Retain`: видалення стеку більше не
  зносить дані.

**Щоденний звіт** (`scripts/daily_report.py`): «бачили ціну» тепер рахує секцію `price` замість
`claims` (як на новій сторінці), у рядках лідів з'являється `lang`. Це локальний скрипт, від
деплою Lambda він не залежить.

## 3. Блокери п.2 — сумісність живого фронту з новим бекендом: **блокера нема**

Що шле форма проду (`app-next.ba26d2a9fb.js`, обробник submit): `name, phone, city, comment,
website, color, size, consent, consent_marketing, consent_text_version, session_id, page,
referrer, device, lang, utm_source, utm_medium, utm_campaign, utm_content, utm_term, fbclid,
attributed_at`. Ключі з `undefined` (візит без UTM) `JSON.stringify` викидає. Поле за полем
з `put_lead` master:

| Поле | Фронт | master | 400/422 там, де зараз 200? |
|---|---|---|---|
| name | trim, клієнт вимагає ≥2 | clip 80, ≥2, інакше 422 | ні: правило те саме, що в c0bd150 |
| phone | `normalizePhone`, те саме правило | `normalize_phone` | ні: 29 входів дають однаковий вердикт і однаковий e164 |
| size | `data-size` на `<html>`: 160/220 | 160/220, інше → `""`, 200 | ні |
| lang | `<html lang>`: he/en | he/en, інше → `""`, 200 | ні |
| color | `data-oak`: natural/smoked/white | те саме, інше → `""` | ні |
| consent | checkbox | обов'язкова, інакше 422 | ні: як було |
| решта | рядки / відсутні | clip, без валідації | ні |

Доказ — `tests/test_lambda_dynamodb.py` (коміт `1037ca7`). Тіло рівно такої форми, як будує прод-фронт,
проходить put_lead master на moto з FX_STORAGE=dynamodb: 200, лід у `fx_leads`, notify рівно раз.
Тест звіряє набір ключів із самим JS, тож новий ключ у формі зробить його червоним. Паритет
телефону перевіряється через `node` на коді з `app-next.js`. 5 мутацій у пам'яті дають
червоне. Прогін: `Ran 212 tests — OK`.

Єдиний теоретичний випадок: вкладку відкрили до 09.09 і не оновлювали (старий JS `8f954f4`/`b317a27`
з м'яким regex), а номер понад 15 цифр на кшталт `+972 000000 50 123 4567`. c0bd150 відповів би
200, master відповідає **422, не 400**, і фронт покаже помилку телефону. Практично це нуль.

## 4. Блокери п.4 — SAM і CloudFormation

**4.1. Параметри, не передані в `parameter_overrides`: SAM це вміє.** Вихідний код
aws-sam-cli 1.166.1, `samcli/commands/deploy/deploy_context.py::merge_parameters`: кожен параметр
шаблону, якого нема в overrides, іде як `UsePreviousValue=True`.
`samcli/lib/deploy/deployer.py::create_changeset`: для ІСНУЮЧОГО стеку `UsePreviousValue` для
параметрів, яких у стеку ще не було, відкидається, а overrides з іменами, яких нема в шаблоні,
ігноруються. Тож `AdminPass`, `IpSalt`, `EdgeSecret`, `CertificateArn` лишились би незмінними
навіть через `sam deploy`. **Проте для викату `sam deploy` не беремо:**
- `print_deploy_args` друкує overrides. `hide_noecho_parameter_overrides` маскує лише NoEcho, а
  `OwnerTelegramChatId` у шаблоні не NoEcho, тож він піде в консоль;
- `--parameter-overrides TelegramBotToken=...` лежить в аргументах процесу, а `/proc` на машині
  змонтовано без `hidepid`, і аргументи бачать усі користувачі.

Тому рецепт іде через `create-change-set --parameters file://` (файл 0600 від
`scripts/prod_notify_params.py`, коміт `74c9488`), з `UsePreviousValue=true` для всього, крім трьох значень.

**4.2. На машині нема Python 3.13.** `sam build` падає:
`Binary validation failed for python ... runtime: python3.13`. Docker для нас недоступний.
Обхід без root перевірено: `uv python install 3.13` у `/tmp`, `python3` → 3.13 першим у PATH, і
`sam build` проходить. Бандл: `handler.py`, `store.py`, `wsgi.py`, `requests`, `urllib3`, `idna`,
`certifi`, `charset_normalizer` (`.so` під `cpython-313-aarch64`, як і треба для arm64), ~2.5 МБ,
у zip ~1.1 МБ. Імпорт `handler` з бандла (розкладка `/var/task`, репозиторій прибрано з
`sys.path`): `store` береться з бандла, `requests 2.34.2` з бандла, health 200.
**Пропустити `sam build` не можна:** без нього в zip не буде `requests`, і кожне сповіщення
закінчиться `notify_failed`.

**4.3. Знайдено й виправлено: токен бота потрапляв у журнал.** requests кладе URL
(`/bot<token>/sendMessage`) у текст винятку, а `notify()` писав `repr(exc)` у stdout. Журнал
Lambda зберігається безстроково. Відтворено локально без мережі: у рядку `notify_failed` був
повний фіктивний токен. Виправлено в `93c329c` (`_redact()`, два тести; з вимкненим `_redact`
обидва червоні). **Викочувати тільки `93c329c` або новіше.**

**4.4. Пастки, яких рецепт уникає**
- `scripts/deploy.sh --infra` після `sam deploy` **перезбирає й заливає статику**, а цей викат
  статики не чіпає. Не використовувати.
- `infra/samconfig.toml.example` містить `AdminPass=<set-me>`, `IpSalt=<set-me>`,
  `AppVersion=0.1.0`. Скопійований як є, він **перезапише секрети** буквальним `<set-me>`: злетить
  пароль адмінки й кука, зміняться хеші IP. Не використовувати.
- Не заливати новий код через `aws lambda update-function-code` без шаблону: у master типове
  `FX_STORAGE=sqlite`, і без змінної з шаблону Lambda піде в SQLite на read-only диску, а кожна
  заявка отримає 500. У зворотний бік (відкат коду) це безпечно, див. §7.
- Health показує `AppVersion` з параметра, а не з коду. Тому після викату перевіряється ще й
  `CodeSha256`/`CodeSize` (§8).

**4.5. Жоден ресурс не йде на заміну.** Обидва шаблони (`c0bd150` і master) транслював
локально samtranslator 1.113.0 і порівняв ресурси: 14 і 14, додань і видалень нема.

| Ресурс | Що змінюється | Поведінка за документацією CloudFormation | Replacement |
|---|---|---|---|
| `FxApi` `AWS::Lambda::Function` | `Code` (новий S3-ключ), `Environment.Variables` (+`FX_STORAGE`, +`TELEGRAM_BOT_TOKEN`, +`OWNER_TELEGRAM_CHAT_ID`, −`LEAD_NOTIFY_EMAIL`) | Code: No interruption; Environment: No interruption | ні |
| `FxApiRole` `AWS::IAM::Role` | `Policies`: прибрано `Fn::If` з `ses:SendEmail` | Policies: No interruption | ні |
| `FxEventsTable`, `FxLeadsTable`, `FxSessionsTable` | `DeletionPolicy`, `UpdateReplacePolicy` = Retain | це атрибути ресурсу, не властивості: сам ресурс не оновлюється | ні |
| `Distribution`, `FxHttpApi`, стейдж, `SiteBucket`, решта | нічого (`EdgeSecret` = UsePreviousValue) | — | — |

`sam validate --lint`: `valid SAM Template`. У change set (§6, крок 5) власник бачить колонку
Replacement від самого CloudFormation. Це і є остаточна перевірка.

## 5. Звідки Telegram-значення

У стеку `aparts` параметр `TelegramBotToken` має NoEcho, тож `describe-stacks` віддає `****` і з
CloudFormation його **не взяти**. `OwnerTelegramChatId` там не NoEcho. Обидва значення задані
змінними `TELEGRAM_BOT_TOKEN` і `OWNER_TELEGRAM_CHAT_ID` у Lambda `aparts-api` (і в
`aparts-guest-messages`, `aparts-ical-sync`, `aparts-pricing`). `scripts/prod_notify_params.py`
читає їх з `aparts-api` просто в пам'ять і пише у файл 0600. Значень немає ні в консолі, ні в
журналі оболонки (у командах тільки шлях до файлу), ні в аргументах процесу, ні в git. Файл
знищується `shred -u` одразу після `create-change-set`.

## 6. Рецепт выката (для владельца)

Выполнять на ace-main под `ihor`, из одной оболочки, сверху вниз. Что пишет в AWS, помечено.
Шаги 0–2 прогнаны 2026-09-11 с нуля в отдельной папке `/tmp`: Python 3.13.15,
`Build Succeeded`, `grep -c` дал 3, `~/.local/bin` не тронут (`--no-bin`).

```bash
# 0. Код и тесты (в AWS ничего не пишет)
umask 077
cd ~/repos/aluma-table && git pull --rebase
git log --oneline -1 -- api/handler.py          # 93c329c или новее
python3 -m venv /tmp/aluma-deploy/venv
/tmp/aluma-deploy/venv/bin/pip install -q -r api/requirements.txt werkzeug boto3 moto aws-sam-cli uv
/tmp/aluma-deploy/venv/bin/python -m unittest discover -s tests -t . 2>&1 | tail -3   # ... OK

# 1. Python 3.13 для sam build (без root, всё в /tmp)
export UV_PYTHON_INSTALL_DIR=/tmp/aluma-deploy/py
/tmp/aluma-deploy/venv/bin/uv python install 3.13 --no-bin
mkdir -p /tmp/aluma-deploy/bin
ln -sf "$(/tmp/aluma-deploy/venv/bin/uv python find 3.13)" /tmp/aluma-deploy/bin/python3
export PATH="/tmp/aluma-deploy/bin:/tmp/aluma-deploy/venv/bin:$PATH" SAM_CLI_TELEMETRY=0
python3 --version                               # Python 3.13.x

# 2. Сборка (локально)
cd ~/repos/aluma-table/infra
sam build --template-file template.yaml         # Build Succeeded
ls .aws-sam/build/FxApi | grep -cxE 'handler\.py|store\.py|requests'   # 3

# 3. [запись в AWS: zip кода в S3-бакет SAM; стек и сайт не меняются]
sam package --template-file .aws-sam/build/template.yaml --resolve-s3 --s3-prefix fx-table \
  --region eu-central-1 --output-template-file /tmp/aluma-deploy/packaged.yaml

# 4. Параметры: Telegram из aparts-api, остальное «как было». Секреты не печатаются.
python3 ../scripts/prod_notify_params.py --app-version 0.4.0 --out /tmp/aluma-deploy/params.json
#   ожидается: AdminPass / IpSalt / EdgeSecret / CertificateArn / AdminUser / SiteDomain /
#   WhatsappNumber — «как было»; TelegramBotToken, OwnerTelegramChatId — «новое значение
#   из aparts-api, не печатается»; AppVersion: 0.4.0; «исчезнут из стека: LeadNotifyEmail».

# 5. [запись в AWS: change set; стек НЕ меняется, пока его не выполнить]
aws cloudformation create-change-set --region eu-central-1 --stack-name fx-table \
  --change-set-name aluma-notify-040 --change-set-type UPDATE \
  --template-body file:///tmp/aluma-deploy/packaged.yaml \
  --parameters file:///tmp/aluma-deploy/params.json \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND --query Id --output text
aws cloudformation wait change-set-create-complete --region eu-central-1 \
  --stack-name fx-table --change-set-name aluma-notify-040
shred -u /tmp/aluma-deploy/params.json
aws cloudformation describe-change-set --region eu-central-1 --stack-name fx-table \
  --change-set-name aluma-notify-040 \
  --query 'Changes[].ResourceChange.[Action,LogicalResourceId,ResourceType,Replacement]' --output table
```

**Читать таблицу.** Ожидается `Modify FxApi AWS::Lambda::Function False` и
`Modify FxApiRole AWS::IAM::Role False`. Три таблицы могут появиться как `Modify … False`, а могут
и не появиться: изменение только `DeletionPolicy` CloudFormation показывает по-разному, оба
варианта нормальны. **СТОП и не выполнять**, если есть хоть одно `True` или `Conditional` в
Replacement, любой `Add` или `Remove`, или в списке есть `Distribution`, `FxHttpApi`,
`SiteBucket`. Тогда удалить набор и написать дирижёру:
`aws cloudformation delete-change-set --region eu-central-1 --stack-name fx-table --change-set-name aluma-notify-040`.

```bash
# 6. [запись в AWS: выкат, ~1–2 мин]
aws cloudformation execute-change-set --region eu-central-1 --stack-name fx-table \
  --change-set-name aluma-notify-040
aws cloudformation wait stack-update-complete --region eu-central-1 --stack-name fx-table \
  && echo UPDATE_COMPLETE
```

Если обновление упало, CloudFormation сам откатит стек к прежнему состоянию
(`UPDATE_ROLLBACK_COMPLETE`), и прод останется как сегодня.

## 7. Откат (для владельца)

zip 0.3.0 сохранён:
`/opt/ihor/aluma-table/rollback/fx-table-api-0.3.0-c0bd150-2026-09-11.zip`,
sha256 `6c877ba427cb94ab88e8c593d664609cc869e93da267c433c17384fae409c3e8`, 10180 байт, внутри
`handler.py` (= c0bd150) и пустой `requirements.txt`. Секретов в нём нет: проверено грепом,
в коде только имена переменных.

**Быстрый откат кода, ~2 минуты:**

```bash
cd /opt/ihor/aluma-table/rollback && sha256sum -c fx-table-api-0.3.0-c0bd150-2026-09-11.zip.sha256
aws lambda update-function-code --region eu-central-1 --function-name fx-table-api \
  --zip-file fileb:///opt/ihor/aluma-table/rollback/fx-table-api-0.3.0-c0bd150-2026-09-11.zip \
  --query '[CodeSha256,LastUpdateStatus]' --output text
aws lambda wait function-updated --region eu-central-1 --function-name fx-table-api
```

Ожидается `CodeSha256 = bId7pCfLlKuI6MWT1mRgnMhp6T2iZ8QzwXOE+uQJw+g=`. Старый код не знает
`TELEGRAM_*` и `FX_STORAGE`. `LEAD_NOTIFY_EMAIL` нет, значит пусто. Поведение ровно сегодняшнее,
без уведомлений. Новые поля в лидах старый код игнорирует. Health при этом покажет 0.4.0,
потому что версия приходит из параметра стека, а не из кода. Старый код узнают по `CodeSha256`.
Стек после этого в дрейфе, следующий выкат его перезапишет.

**Полный откат шаблона и версии 0.3.0, ~5 минут, секреты не нужны:**

```bash
git -C ~/repos/aluma-table worktree add /tmp/aluma-rollback c0bd150
cd /tmp/aluma-rollback/infra
sam build --template-file template.yaml          # python3.13 из шага 1 в PATH
sam deploy --stack-name fx-table --region eu-central-1 --capabilities CAPABILITY_IAM \
  --resolve-s3 --s3-prefix fx-table --confirm-changeset --parameter-overrides AppVersion=0.3.0
git -C ~/repos/aluma-table worktree remove /tmp/aluma-rollback
```

Здесь `sam deploy` безопасен. Все параметры, кроме `AppVersion`, SAM передаёт как
`UsePreviousValue`, так что `AdminPass`, `IpSalt` и `EdgeSecret` не меняются. `LeadNotifyEmail`,
которого в текущем стеке нет, получает значение по умолчанию `""`. Печатается только `AppVersion`.

## 8. Проверка после выката (для владельца)

```bash
# 1) версия и что код действительно новый (печатаются только имена переменных)
curl -s https://table.central-aparts.store/api/fx/health            # "version": "0.4.0"
aws lambda get-function-configuration --region eu-central-1 --function-name fx-table-api \
  --query '{sha:CodeSha256,size:CodeSize,modified:LastModified,env:keys(Environment.Variables)}'
#   sha НЕ bId7pC…, size ~1.1 МБ (не 10180), в env есть FX_STORAGE, TELEGRAM_BOT_TOKEN,
#   OWNER_TELEGRAM_CHAT_ID, нет LEAD_NOTIFY_EMAIL

# 2) тестовая заявка с пометкой теста: запись в DynamoDB работает
curl -s -X POST https://table.central-aparts.store/api/fx/lead \
  -H 'content-type: application/json' -H 'x-test: 1' \
  --data '{"name":"SMOKE TEST (fake)","phone":"050-000-0000","consent":true,"comment":"post-deploy check, not a real lead","page":"/post-deploy-check"}'
#   {"ok": true, "id": "…"}. В Telegram НИЧЕГО не придёт: x-test владельца не будит, так задумано.
```

3) **Telegram.** Раз x-test уведомлений не даёт, нужна одна заявка без пометки. Откройте в
браузере `https://table.central-aparts.store/?me=1` (метка `fx_me` уберёт ваши события из
воронки), в форме: имя «ТЕСТ ВЛАДЕЛЬЦА — не звонить», телефон `050-000-0000`, согласие → `/thanks`.
В течение нескольких секунд в Telegram (бот aparts) придёт «ליד חדש — table.central-aparts.store»
с этим именем. Потом в `/admin` поставьте этой заявке статус `spam`.

```bash
# 4) журнал: ни notify_failed, ни падений за последние 30 минут
aws logs filter-log-events --region eu-central-1 --log-group-name /aws/lambda/fx-table-api \
  --start-time $(( ($(date +%s) - 1800) * 1000 )) \
  --filter-pattern '?notify_failed ?unhandled ?ImportModuleError ?"Task timed out"' \
  --query 'events[].eventId' --output text | wc -w                   # 0
```

Если health не 200, заявка не 200 или счётчик журнала больше нуля, сразу выполните быстрый откат
(§7) и потом разбирайтесь. Сообщения можно смотреть с `--query 'events[].message'`: после
`93c329c` токена в них нет.

## 9. Варіанти

### A — викотити бекенд master на Lambda зараз
- **Що дає:** сповіщення в Telegram про кожну справжню заявку з сьогодні, незалежно від строків
  переїзду. Retain на таблицях. `lang` і атрибуція в лідах.
- **Ризики:**
  - биткий бандл або імпорт дадуть API 5xx, і форма не працюватиме до відкату. Ловиться health і
    тестовою заявкою за хвилину, відкат 2 хв;
  - якщо Telegram недоступний, лід збережеться, а в журналі з'явиться `notify_failed`;
  - якщо Telegram завис, відповідь форми затримається до ~10 с;
  - ім'я й телефон гостя йтимуть у Telegram-чат власника;
  - бот спільний з aparts: зміна його токена в aparts заглушить і ALUMA, тоді параметр треба
    оновити.
- **Ціна помилки:** хвилини неробочої форми в тихий період (5–10 вересня — від 2 до 16
  звернень до API на добу), за 3+ тижні до реклами.
- **Блокери:** п.2 — нема. п.4 — усі зняті: Python 3.13 через uv, токен у журналі виправлено в
  `93c329c`, секрети через файл параметрів, змін із заміною нема.

### B — чекати переїзду на цю машину
- **Що дає:** жодного дотику до AWS-проду.
- **Ризики:** до переїзду заявки не дають сигналу, власник мусить сам заглядати в `/admin`.
  Якщо переїзд зсунеться за 5.10, реклама піде без сповіщень.
- **Ціна помилки:** гарячі ліди, на які передзвонять за години чи дні, під час оплаченої реклами.
  Цього не відіграти.
- **Блокери:** немає, але сповіщення тоді цілком залежать від строків переїзду й DNS.

## 10. WHATSAPP_NUMBER

`WHATSAPP_NUMBER` у Lambda порожня, і **handler її не читає зовсім**: вона є тільки в `env`
шаблону. Кнопки WhatsApp ховаються під час збирання статики (`content.json` `"WA_NUMBER": ""`,
`build.py:533`). Параметр `WhatsappNumber` у стеку на кнопки не впливає. Щоб їх показати,
треба вписати номер у `content.json`, перезібрати й залити статику. Це окреме рішення, у цей
викат воно не входить, і рецепт залишає `WhatsappNumber` «як було».

## 11. Що не перевірено і чому

- Change set не створювався: це запис в AWS. Колонку Replacement від самого CloudFormation
  власник побачить на кроці 5. Висновок «без заміни» тут зроблено логічно, з документації й
  локальної трансляції.
- `sam package` і доставка в Telegram не перевірялись: перше пише в S3, друге потребує
  справжнього токена. Замість цього — moto і дублер `requests.post`.
- Як change set показує зміну лише `DeletionPolicy` — не перевірено, тому в §6 допустимі обидва
  варіанти.
- Холодний старт нового бандла на arm64 не заміряно. Імпорт з бандла перевірено на x86_64
  Python 3.13 (`.so` під aarch64 там не вантажаться, charset_normalizer іде чистим Python).
- Факти про SES з брифу перевірено повторно (`sesv2`). Вміст `aparts` — лише імена параметрів і
  змінних, значень не читали.

## Журнал выката

**2026-09-11, вариант A выкачен.** Сессия «🪵 ALUMA · выкат уведомлений на прод» по рецепту §6
с тремя остановками у дирижёра ALUMA (объявления владельцу — через главного дирижёра, окно
10 минут). Времена — по Киеву (EEST). Значений секретов в журнале нет.

| Что | Факт |
|---|---|
| Выкачен код | `3503b07` (= origin/master на момент сборки; последняя правка `api/handler.py` — `93c329c`) |
| Шаги 0–2 | `Ran 218 tests — OK`; Python 3.13.15 в `/tmp/aluma-deploy`; `Build Succeeded`, `grep -c` = 3 |
| Шаг 3 | `sam package` → `s3://aws-sam-cli-managed-default-samclisourcebucket-…/fx-table/7e19cbff01d127f0bd335fb02a0d76f1` |
| Шаг 4 | отчёт `prod_notify_params.py` ровно как в §6; файл 0600, после change set — `shred -u` (оба раза) |
| Шаг 5, первый набор | удалён без выполнения (стоп-критерий, см. ниже) |
| Шаг 5, второй набор | `aluma-notify-040` создан 14:14:47, прошёл уточнённый критерий |
| Шаг 6 | execute 14:30:30 → `UPDATE_COMPLETE` 14:31:09; `LastModified` функции 11:30:44Z |
| CodeSha256 до | `bId7pCfLlKuI6MWT1mRgnMhp6T2iZ8QzwXOE+uQJw+g=`, 10180 байт |
| CodeSha256 после | `vPUWcWh3UOKIyLyMSCsLDk0Pz5Ue2T2lRvhn+EkrtJk=`, 669934 байт |
| §8 п.1 | health 200, `"version": "0.4.0"`; sha новый; в env есть `FX_STORAGE` (= `dynamodb`), `TELEGRAM_BOT_TOKEN`, `OWNER_TELEGRAM_CHAT_ID`, нет `LEAD_NOTIFY_EMAIL` — **OK** |
| §8 п.2 | заявка с `x-test: 1` → HTTP 200 `{"ok": true, "id": "1d68d0ea7d6e"}` — **OK** |
| §8 п.4 | с 11:00Z (выкат и проверки внутри окна): `notify_failed` / `unhandled` / `ImportModuleError` / `Task timed out` — 0; вызовов (`REPORT`) — 3 — **OK** |
| §8 п.3 | **ждёт владельца**: одна заявка без пометки через `/?me=1`, сообщение в Telegram, потом статус `spam` в `/admin` |
| Откат | не понадобился; zip 0.3.0 на месте, `sha256sum -c` OK до выката |

**Стоп на первом наборе и уточнение критерия.** Таблица первого набора:

| Action | LogicalResourceId | ResourceType | Replacement |
|---|---|---|---|
| Modify | FxApiInvokePermission | AWS::Lambda::Permission | Conditional |
| Modify | FxApi | AWS::Lambda::Function | False |
| Modify | FxEventsTable | AWS::DynamoDB::Table | False |
| Modify | FxHttpApi | AWS::ApiGatewayV2::Api | False |
| Modify | FxLeadsTable | AWS::DynamoDB::Table | False |
| Modify | FxSessionsTable | AWS::DynamoDB::Table | False |

`Conditional` и `FxHttpApi` — стоп-критерии §6, набор удалён, дирижёру доложено. Details обеих
строк: единственная причина — `FxApi.Arn` (`Evaluation=Dynamic`, `ChangeSource=ResourceAttribute`):
у `FxApiInvokePermission` свойство `FunctionName` (`!GetAtt FxApi.Arn`), у `FxHttpApi` — `Body`
(`${FxApi.Arn}` в uri интеграции). `FxApi` идёт с `Replacement=False`, ARN не меняется; diff
`c0bd150..3503b07 -- infra/template.yaml` этих строк не трогает. CloudFormation помечает
зависимые ресурсы по динамической ссылке заранее, не зная, что ARN останется тем же.

Дирижёр уточнил критерий для этого выката: **допускаются ровно две строки —
`FxApiInvokePermission Modify Conditional` и `FxHttpApi Modify False` — и только если у обеих в
Details единственная причина `CausingEntity=FxApi.Arn` (Dynamic), без Static-изменений своих
свойств. Всё остальное — стоп, как в §6.** Второй набор дал ту же таблицу и те же Details
(по одной записи у каждой из двух строк) и прошёл.

**Расхождения с ожиданиями §4–§6** (не мешают, но стоит знать следующему выкату):
- `FxApiRole` в change set нет, хотя §6 его ждал: условный `ses:SendEmail` под ложным `Fn::If`
  CloudFormation изменением не считает.
- Три таблицы появились как `Modify … False`, Scope — только `DeletionPolicy`/`UpdateReplacePolicy`.
- Размер кода 669934 байт, а не ~1.1 МБ из §4.2; критерий §8 («не 10180») выполнен, импорт и
  health — рабочие.

**Что осталось на машине:** `/tmp/aluma-deploy` (venv, Python 3.13, `packaged.yaml`) — без
секретов; файла параметров нет. `infra/.aws-sam/` в рабочей копии (gitignored).
