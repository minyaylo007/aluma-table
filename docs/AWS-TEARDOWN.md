# ALUMA — опись старого AWS и план его удаления

**Статус: удаление ЗАКОНЧЕНО. Все три пачки выполнены — 1 и 2 в 15:08–15:28Z 2026-09-11, 3 в
06:11–06:14Z 2026-09-12; сверка «до/после» зелёная (раздел «Подтверждение: ничего не осталось»).**
Единственный объект с отложенным концом — секрет `aluma/admin-credentials`: он запланирован к
удалению на 2026-09-19 09:13 +03:00 (окно 7 дней), до этой даты его ещё можно восстановить.
Актуальное — раздел «Перечень к удалению» ниже; §1–§9 — первичная опись и план, в части «оставить
копией» (§4, §8 пп.1–3) заменены решением владельца от 11.09.

Первичная опись снята 2026-09-11 ~12:00 UTC только чтением
(list/describe/get + один запрос Cost Explorer). `get-secret-value` не вызывался, содержимое таблиц не
выгружалось. Аккаунт `000000000000`, регион `eu-central-1` (+ `us-east-1` для ACM и CloudFront).

> **Маскировка перед публикацией (12.09.2026).** Номер аккаунта AWS в этом файле заменён заглушкой:
> `000000000000` там, где он стоит отдельно (в т. ч. в имени бакета), и `<account>` внутри ARN —
> 12 цифр внутри ARN ловит правило `aws_arn_account` в `scripts/secret_scan.py`. Так же убраны имена
> и права пользователей IAM чужих проектов. Оригинальные значения — в приватном архиве
> `aluma-table-archive-2026-09`; для ALUMA они больше не нужны: стек `fx-table` удалён.

**Решение владельца (11.09):** после переключения `table` на ace-main удалить старую инфраструктуру ALUMA
в AWS — «исключительно ресурсы старого проекта Table, не затрагивать другие сервисы, окружения и проекты».
**Решение дирижёра:** не сразу, а после 48 часов наблюдения: пока AWS жив, откат = вернуть DNS
(`docs/CUTOVER-CHECKLIST.md`, шаг 10).

**Кто выполняет.** Запись в AWS сессиям запрещена (`CLAUDE.md` §9). Команды ниже выполняет владелец —
или сессия, которой владелец письменно разрешил именно эти команды. Перед шагом 3 — объявление главному
дирижёру за 10 минут: удаление необратимо.

---

## Перечень к удалению (утверждён 2026-09-11)

**Решение владельца (11.09), заменяет «оставить копией» в §4 и §8:** «Полностью удалить старую
инфраструктуру Table из AWS, включая все связанные дубликаты ресурсов. Перед удалением составить и
сохранить перечень. Не затрагивать ресурсы других проектов. После удаления подтвердить, что в AWS не
осталось старой инфраструктуры/дубликатов этого проекта.» Все 20 заявок в DynamoDB — тестовые; живые
данные — SQLite коробки, копии — дампы в `/opt/ihor/aluma-table`. Поэтому удаляются и таблицы `fx_*`,
и секрет `aluma/admin-credentials`.

Машинный снимок «до»: `docs/aws-teardown/before-2026-09-11.json` (`scripts/aws_inventory.py snapshot`,
только чтение; снят 2026-09-11 13:42:15–13:42:55Z, после финальной выгрузки). Значений секретов в нём нет: `get-secret-value` скрипт не пропускает
вовсе, из `get-function` берётся лишь `APP_VERSION`.

Перед удалением: `scripts/daily_report.py` переведён на SQLite коробки (`4b81966`); финальная выгрузка
DynamoDB — `/opt/ihor/aluma-table/dump-2026-09-11-teardown/` (700, файлы 600), числа — ниже, в
«Выполнено».

### Что удаляется — 3 пачки

| Пачка | # | Ресурс | Идентификатор | Чем |
|---|---|---|---|---|
| 1 | 1.1 | Бакет сайта — содержимое | `s3://fx-table-site-000000000000`: 358 объектов, 9 639 881 байт, версионирование выключено | `aws s3 rm --recursive` |
| 1 | 1.2 | Стек `fx-table` (eu-central-1), 14 ресурсов | см. таблицу ниже; `EnableTerminationProtection=false`, экспортов нет | `cloudformation delete-stack` + `wait stack-delete-complete` |
| 2 | 2.1 | DynamoDB `fx_events` | `arn:aws:dynamodb:eu-central-1:<account>:table/fx_events` (Retain — стек её не удалит) | `dynamodb delete-table` |
| 2 | 2.2 | DynamoDB `fx_leads` | `…:table/fx_leads` (Retain) | `dynamodb delete-table` |
| 2 | 2.3 | DynamoDB `fx_sessions` | `…:table/fx_sessions` (Retain) | `dynamodb delete-table` |
| 3 | 3.1 | Группа логов | `/aws/lambda/fx-table-api` (96 205 байт, не в стеке) | `logs delete-log-group` |
| 3 | 3.2 | ACM-сертификат (us-east-1) | `arn:aws:acm:us-east-1:<account>:certificate/d2a264f2-b347-4ba3-8e58-d2139eda0c69` — `table.central-aparts.store`, `InUseBy` = только `E21KNA4YOX9CIB` | `acm delete-certificate` — после того как дистрибуция удалена (`InUseBy` = `[]`) |
| 3 | 3.3 | CNAME валидации в зоне `Z05565972H1DV59U5PO4I` | `_76330d86a537e3871c91496e2f84668a.table.central-aparts.store.` CNAME TTL 300 → `_899f0cee4466647eed6cd591e1093e6a.jkddzztszm.acm-validations.aws.` | `route53 change-resource-record-sets` DELETE (§7, шаг 7; сверка до символа со снимком «до») |
| 3 | 3.4 | Артефакты SAM в общем бакете | `aws-sam-cli-managed-default-samclisourcebucket-tqh5bzqhj11n`, префикс `fx-table/`: 13 версий 13 ключей, 0 delete-маркеров (ключи и VersionId — в снимке «до») | `s3api delete-objects` по списку `{Key, VersionId}`, все ключи под `fx-table/` |
| 3 | 3.5 | Секрет | `arn:aws:secretsmanager:eu-central-1:<account>:secret:aluma/admin-credentials-KqVbyK` | `secretsmanager delete-secret --recovery-window-in-days 7` (не force) |
| 3 | 3.6 | GitHub-переменная (дубликат вне AWS; добавлено дирижёром 11.09) | переменная репозитория `AWS_ROLE_ARN` в `minyaylo007/aluma-table` (создана 10.09) → общая роль бек-офиса `github-actions-deploy`. Workflows ALUMA её не читают — ни в дереве, ни в истории `.github` | `gh variable delete AWS_ROLE_ARN -R minyaylo007/aluma-table`. Саму роль `github-actions-deploy`, её доверие и OIDC-провайдер **не трогаем** — общее |

Ресурсы стека `fx-table` (уходят в пачке 1 одним `delete-stack`; DeletionPolicy — из `get-template
--template-stage Processed`):

| Логический id | Тип | Физический id | DeletionPolicy |
|---|---|---|---|
| `Distribution` | CloudFront::Distribution | `E21KNA4YOX9CIB` (`dnj0089lrzf76.cloudfront.net`) | Delete |
| `IndexRewrite` | CloudFront::Function | `fx-table-index-rewrite` | Delete |
| `SiteOac` | CloudFront::OriginAccessControl | `E2KHW7MW8K25XT` | Delete |
| `ApiOriginRequestPolicy` | CloudFront::OriginRequestPolicy | `a121b12a-5351-48b8-bc6d-c54e85b46b77` | Delete |
| `SiteBucket` | S3::Bucket | `fx-table-site-000000000000` | Delete (после 1.1 — пустой) |
| `SiteBucketPolicy` | S3::BucketPolicy | тот же бакет | Delete |
| `FxApi` | Lambda::Function | `fx-table-api` (python3.13, `APP_VERSION` 0.4.0) | Delete |
| `FxApiInvokePermission` | Lambda::Permission | `fx-table-FxApiInvokePermission-dNt5oTawxuFN` | Delete |
| `FxApiRole` | IAM::Role | `fx-table-FxApiRole-BiE09PLkm3Zy` | Delete |
| `FxHttpApi` | ApiGatewayV2::Api | `r7jel27uma` | Delete |
| `FxHttpApiApiGatewayDefaultStage` | ApiGatewayV2::Stage | `$default` | Delete |
| `FxEventsTable`, `FxLeadsTable`, `FxSessionsTable` | DynamoDB::Table | `fx_events`, `fx_leads`, `fx_sessions` | **Retain** → пачка 2 |

### Что остаётся — общее, не трогаем

Полные списки — `shared` в снимке «до»; «после» сверяется с ними командой `compare` (ниже).

| Что | Сколько в снимке «до» | Почему остаётся |
|---|---|---|
| Стеки `aparts`, `aparts-monitor`, `aparts-v2`, `aws-sam-cli-managed-default` | 4 | чужие / владелец общего SAM-бакета |
| Зона `Z05565972H1DV59U5PO4I` | 19 записей, из них уходит одна (3.3) | общая; `table.` A и `table-new.` A — это коробка, не старый AWS |
| CloudFront `E3A58MFOU2LI12` (апекс/www/v2), `E80XDWDORZKYP` (cv), функция `chernivtsi-guide-strip-prefix` | 2 + 1 | чужие |
| ACM us-east-1 — остальные сертификаты | 5 | чужие |
| Лямбды `aparts-*` | 9 | чужие |
| DynamoDB `aparts-*` | 12 | чужие |
| Группы логов без `fx-table` | 8 | чужие |
| Секреты без `aluma` | 16 | чужие |
| IAM: роли (кроме `fx-table-FxApiRole-…`), два пользователя-деплойщика соседних проектов | 17 + 2 | общие |
| S3: `aparts-uploads-…`, `gosha-archive-…`, общий SAM-бакет (650 версий вне `fx-table/`, sha256 списка — в снимке) | 3 | чужие / общий |
| EventBridge (19 правил), Scheduler (1), бюджет `aparts-monthly-10usd` | — | чужие / общий |

### Как повторить проверку

```bash
# «до» / «после» — только чтение; нужен AWS CLI v2 с доступом на чтение
python3 scripts/aws_inventory.py snapshot --label before --out docs/aws-teardown/before-2026-09-11.json
python3 scripts/aws_inventory.py snapshot --label after  --out docs/aws-teardown/after-2026-09-12.json
python3 scripts/aws_inventory.py compare docs/aws-teardown/before-2026-09-11.json docs/aws-teardown/after-2026-09-12.json
# ЗЕЛЕНО = из каждого общего списка исчезли ровно id ALUMA, всё чужое на месте (включая версии
# SAM-бакета вне fx-table/ по sha256), поиск по маркерам fx-table, fx_, aluma,
# table.central-aparts.store, E21KNA4YOX9CIB, r7jel27uma, d2a264f2 не находит ничего, кроме A-записей
# table/table-new на коробку и секрета в статусе «запланировано к удалению»; прод table: health
# 0.4.0-box, / 200, /admin 303.
```

## Выполнено

**Шаг 1 — `daily_report` на SQLite** (`4b81966`): читает базу коробки через `api/store.py` и `FX_DB_PATH`,
boto3 не нужен. Разовая сверка старого `load()` (moto) с новым на тех же данных — совпадение для
1/3/7/10 дней; живой прогон на базе коробки (`--no-ai`) — код 0.

**Шаг 2 — финальная выгрузка DynamoDB** (последняя копия):

| Проверка | Результат |
|---|---|
| `Invocations` `fx-table-api`, 12:41–13:43Z (поминутно) | ни одной точки > 0; последний вызов — 12:40Z, до SWITCH 12:42:31Z |
| `migrate_fx.py --phase dump` → `/opt/ihor/aluma-table/dump-2026-09-11-teardown/` (700, файлы 600) | `taken_at` `2026-09-11T13:41:55.873133+00:00`, код 0: `fx_events` 1076, `fx_leads` 21, `fx_sessions` 79, всего 1176 |
| Сверка с финальным дампом 8.5 (`dump-2026-09-11-final`, 12:58:18Z) по ключам и содержимому | 0 новых, 0 изменённых, 0 пропавших строк во всех трёх таблицах — DynamoDB после переключения не менялась |
| `verify --second-pass --leads-since 2026-09-11T11:02:12.816423+00:00` против живой `data/aluma.db` | **ЗЕЛЕНО**, код 0: не доехало 0/0/0; содержимое строк снимка = база (расхождений 0 из 1076 / 21 / 79); в базе сверх снимка — события 53, сессии 17, заявки: тестовые 6 + после `--leads-since` 1, необъяснённых 0 |
| `load` в живую базу | **не выполнялся** — verify без него зелёный, содержимое совпадает строка в строку, значит load ничего бы не изменил, а риск перезаписать строки, изменённые на коробке после 12:58Z (статусы, сессии), был бы. Согласовано с дирижёром ALUMA |

Справочно в базе коробки: заявок 28 (настоящих 1, тестовых 27). Содержимое не печаталось.

**Пачка 1 — стек** («выполняй» дирижёра ALUMA после окна объявления главному до 18:08 EEST):

| Время UTC | Шаг | Итог |
|---|---|---|
| 15:08:23 | проверки перед стартом (только чтение) | `Invocations` `fx-table-api` 12:42–15:08Z — 0; `table`: health `0.4.0-box`, `/` 200, `/admin` 303 → `/admin/login` |
| 15:08:40–15:08:43 | `aws s3 rm s3://fx-table-site-000000000000 --recursive` | код 0; `list-object-versions` и `list-objects-v2` — пусто (0 версий, 0 delete-маркеров) |
| 15:08:59 | `aws cloudformation delete-stack --stack-name fx-table` | принят; стек `arn:aws:cloudformation:eu-central-1:<account>:stack/fx-table/f15ffcf0-a645-11f1-8935-0ac92f8cfc89` |
| 15:09:03 | `FxApiInvokePermission`, `FxHttpApiApiGatewayDefaultStage` (`$default`), `SiteBucketPolicy` | DELETE_COMPLETE |
| 15:11:34 | `Distribution` `E21KNA4YOX9CIB` | DELETE_COMPLETE (2.5 мин, а не 15–45) |
| 15:11:36–15:11:37 | `ApiOriginRequestPolicy` `a121b12a-…`, `SiteOac` `E2KHW7MW8K25XT`, `SiteBucket`, `FxHttpApi` `r7jel27uma`, `IndexRewrite` `fx-table-index-rewrite` | DELETE_COMPLETE |
| 15:11:40 | `FxApi` `fx-table-api` | DELETE_COMPLETE |
| 15:11:52 | `FxApiRole` `fx-table-FxApiRole-BiE09PLkm3Zy` | DELETE_COMPLETE |
| 15:11:53 | `fx_events`, `fx_leads`, `fx_sessions` | DELETE_SKIPPED (Retain) — остаются до пачки 2, ACTIVE |
| 15:11:53 | стек `fx-table` | **DELETE_COMPLETE** |

Проверка после (15:12:59Z, только чтение): `describe-stacks fx-table` — «does not exist»; `E21KNA4YOX9CIB` —
NoSuchDistribution; `fx-table-api` — ResourceNotFoundException; `r7jel27uma` — NotFoundException; роль — NoSuchEntity;
бакет — 404; функция, OAC, ORP — NoSuch…; чужие дистрибуции `E3A58MFOU2LI12`, `E80XDWDORZKYP` — Deployed, Enabled, как «до».
HTTP: `central-aparts.store` 200, `www` 200, `cv` 302 → `/auth/login`, `v2` — нет ответа (так же и в снимке «до»),
`table` `/` 200, `/admin` 303, health `0.4.0-box`. Штатный `aws … wait stack-delete-complete` дважды снимался системой
из-за нехватки памяти на машине — ждали опросом `describe-stacks` раз в минуту; на удаление это не влияло.

**Пачка 2 — данные** («выполняй» дирижёра ALUMA после нового окна объявления):

| Время UTC | Шаг | Итог |
|---|---|---|
| 15:27:16 | проверки перед стартом (только чтение) | `scan --select COUNT`: `fx_sessions` 79, `fx_events` 1076, `fx_leads` 21 — ровно как в дампе шага 2; `DeletionProtectionEnabled` = False у всех трёх |
| 15:27:28 | `aws dynamodb delete-table --table-name fx_sessions` | DELETING |
| 15:27:35 | `aws dynamodb delete-table --table-name fx_events` | DELETING |
| 15:27:41 | `aws dynamodb delete-table --table-name fx_leads` | DELETING (заявки — последними) |
| 15:27:50 | проверка | `describe-table` всех трёх — ResourceNotFoundException; `list-tables` — 12 таблиц `aparts-*`, ровно список «до» без `fx_*`; `table`: health `0.4.0-box`, `/` 200, `/admin` 303 |

Последняя копия данных DynamoDB — `/opt/ihor/aluma-table/dump-2026-09-11-teardown/` (700, файлы 600) и живая база
коробки, в которой каждая строка этого дампа есть байт в байт (verify шага 2).

**Пачка 3 — остатки** («выполняй» дирижёра ALUMA 2026-09-12 после окна объявления главному до 09:11 EEST).
Предпроверки 05:56–06:00Z, только чтение: все шесть объектов на месте и совпадают со снимком «до» —
лог-группа 96 205 байт, сертификат `ISSUED` с `InUseBy` = `[]`, зона 19 записей и целевой CNAME сверен
со снимком программно до символа, 13 версий под `fx-table/` (набор `{Key, VersionId}` = снимок, лишних и
недостающих 0), секрет без `DeletedDate`, переменная `AWS_ROLE_ARN` есть. Файлы изменений для Route 53 и
`delete-objects` собраны **из живых ответов AWS скриптом, а не набраны руками**, в
`/opt/ihor/aluma-table/teardown-2026-09-12/` (0700). Дополнительно проверено, что удаление переменной не
ломает CI: `AWS_ROLE_ARN` и `aws-actions/*` не встречаются ни в одном workflow (включая новые
`deploy.yml`, `release.yml`, `rollback.yml`) и 0 раз во всей истории `.github`.

| Время UTC | Шаг | Итог |
|---|---|---|
| 06:11:12 | 3.1 `logs delete-log-group /aws/lambda/fx-table-api` | код 0; `describe-log-groups --log-group-name-prefix /aws/lambda/fx-table` — пусто; чужих групп 8, ровно список «до» без нашей |
| 06:11:24 | повторная проверка перед сертификатом | `InUseBy` = `[]`, статус `ISSUED` |
| 06:11:28 | 3.2 `acm delete-certificate d2a264f2-…` (us-east-1) | код 0; `describe-certificate` — `ResourceNotFoundException`; остальные 5 чужих сертификатов на месте |
| 06:11:41 | 3.3 `route53 change-resource-record-sets` — один DELETE | принят, `/change/C05168939538Z87S280J`; **INSYNC 06:12:15**; в зоне 18 записей (было 19), программный diff «до/после» — исчезла ровно одна целевая запись, изменённых и новых 0; `table.` A и `table-new.` A на месте, обе на `95.216.10.169`; CNAME больше не отдаётся авторитетным NS |
| 06:12:35 | 3.4 `s3api delete-objects` по 13 парам `{Key, VersionId}` | `Deleted` 13, `Errors` 0, вне `fx-table/` 0, новых delete-маркеров 0; под префиксом версий 0 и маркеров 0; **вне префикса 650 версий и sha256 списка тот же, что в снимке «до»** |
| 06:13:33 | 3.5 `secretsmanager delete-secret --recovery-window-in-days 7` | код 0, `DeletionDate` 2026-09-19 09:13 +03:00; `describe-secret` — `DeletedDate` задан; `list-secrets --include-planned-deletion` — 17 секретов, из них 16 чужих без пометки. `get-secret-value` не вызывался ни раз, значение не читалось |
| 06:13:58 | 3.6 `gh variable delete AWS_ROLE_ARN -R minyaylo007/aluma-table` | код 0; `gh variable list` — пусто, API отдаёт `total_count` 0. Общая роль `github-actions-deploy` (создана 10.09) и OIDC-провайдер `token.actions.githubusercontent.com` на месте — не тронуты |

Одна остановка по ходу была, и не по вине AWS: собственный скрипт проверки шага 3.4 считал sha256 списка
чужих версий с табуляцией между `Key` и `VersionId`, а `scripts/aws_inventory.py` — с пробелом, поэтому
первая сверка дала «ИНОЙ sha256». Разобрано до следующего шага, формула исправлена, повторная сверка —
«ТОТ ЖЕ»; чужие 650 версий не менялись, удалено ровно 13 наших.

---

## Подтверждение: ничего не осталось

Проверено 2026-09-12 06:14–06:16Z. Всё ниже — **только чтение**, любой может повторить.

Машинная сверка (снимок «после» — `docs/aws-teardown/after-2026-09-12.json`, снят 06:14:17–06:14:52Z):

```bash
python3 scripts/aws_inventory.py compare docs/aws-teardown/before-2026-09-11.json \
                                         docs/aws-teardown/after-2026-09-12.json
# → compare: ЗЕЛЕНО, код 0. 41 проверка OK, 0 FAIL
```

Что именно она подтверждает: из каждого общего списка исчезли **ровно** id ALUMA и ничего больше — стек
`fx-table`, дистрибуция `E21KNA4YOX9CIB`, функция `fx-table-index-rewrite`, OAC `E2KHW7MW8K25XT`, ORP
`a121b12a-…`, лямбда `fx-table-api`, роль `fx-table-FxApiRole-BiE09PLkm3Zy`, API `r7jel27uma`, таблицы
`fx_events`/`fx_leads`/`fx_sessions`, лог-группа `/aws/lambda/fx-table-api`, сертификат `d2a264f2-…`,
CNAME валидации, бакет `fx-table-site-000000000000`. Чужое на месте: дистрибуции `E3A58MFOU2LI12` и
`E80XDWDORZKYP` с теми же алиасами, статусом и `Enabled`; в общем SAM-бакете вне `fx-table/` те же 650
версий с тем же sha256; стеки `aparts*`, 9 лямбд, 12 таблиц `aparts-*`, 8 групп логов, 16 чужих секретов,
17 ролей и 2 пользователя IAM, 19 правил EventBridge, Scheduler, бюджет — без изменений.

Ручной поиск по маркерам `fx-table`, `fx_`, `aluma`, `table.central-aparts.store`, `E21KNA4YOX9CIB`,
`r7jel27uma`, `d2a264f2` по всем сервисам описи — три попадания, и все ожидаемые: `table.central-aparts.store. A`
(это коробка, новый прод), `aluma/admin-credentials` в `secrets` и он же в `secrets_planned_deletion`
(статус «запланирован к удалению» до 2026-09-19). Больше ничего.

Живая проверка по каждому id — все отвечают «нет такого»:

```bash
aws cloudformation describe-stacks --region eu-central-1 --stack-name fx-table   # ValidationError: does not exist
aws cloudfront get-distribution --id E21KNA4YOX9CIB                              # NoSuchDistribution
aws lambda get-function --region eu-central-1 --function-name fx-table-api        # ResourceNotFoundException
aws apigatewayv2 get-api --region eu-central-1 --api-id r7jel27uma                # NotFoundException
aws iam get-role --role-name fx-table-FxApiRole-BiE09PLkm3Zy                      # NoSuchEntity
aws s3api head-bucket --bucket fx-table-site-000000000000                         # 404 Not Found
aws dynamodb describe-table --region eu-central-1 --table-name fx_leads           # ResourceNotFoundException
aws dynamodb describe-table --region eu-central-1 --table-name fx_events          # ResourceNotFoundException
aws dynamodb describe-table --region eu-central-1 --table-name fx_sessions        # ResourceNotFoundException
aws logs describe-log-groups --region eu-central-1 \
    --log-group-name-prefix /aws/lambda/fx-table                                  # logGroups: []
aws acm describe-certificate --region us-east-1 \
    --certificate-arn arn:aws:acm:us-east-1:<account>:certificate/d2a264f2-b347-4ba3-8e58-d2139eda0c69
                                                                                  # ResourceNotFoundException
aws s3api list-object-versions --bucket aws-sam-cli-managed-default-samclisourcebucket-tqh5bzqhj11n \
    --prefix fx-table/ --query '{versions:length(Versions||`[]`),markers:length(DeleteMarkers||`[]`)}'
                                                                                  # {"versions": 0, "markers": 0}
aws secretsmanager describe-secret --region eu-central-1 --secret-id aluma/admin-credentials \
    --query DeletedDate                                                           # 2026-09-12T09:13:34+03:00
gh variable list -R minyaylo007/aluma-table                                       # пусто
```

Прод и чужие сайты после всего (06:16:02Z): `table` health `{"ok": true, "version": "0.4.0-box"}`, `/` 200,
`/en/` 200, `/admin` 303 → `/admin/login`; TLS у `table` теперь от Let's Encrypt с коробки
(`issuer=C = US, O = Let's Encrypt, CN = YE1`) — удаление сертификата ACM на живой сайт не влияет.
Чужие: `central-aparts.store` 200, `www` 200, `cv` 302, `v2` нет ответа, `table-new` 200, `box` 404 —
те же коды, что в снимке «до».

Что осталось намеренно и это не старый AWS: `table.central-aparts.store` A и `table-new.central-aparts.store` A
на `95.216.10.169` (коробка), общая роль `github-actions-deploy` с OIDC-провайдером, общий SAM-бакет с
чужими 650 версиями, зона `Z05565972H1DV59U5PO4I` целиком (18 записей). Секрет `aluma/admin-credentials`
исчезнет сам 2026-09-19; до тех пор он виден только с `--include-planned-deletion`.

---

## 1. Итог в цифрах

| | Сколько | Что |
|---|---|---|
| **Удалить** | 15 позиций | 11 ресурсов стека `fx-table` (уходят одним `delete-stack`) + 4 вне стека: группа логов, ACM-сертификат, CNAME валидации, 13 артефактов SAM. Подготовительно — очистка 358 объектов сайта в бакете |
| **Оставить как копию** | 4 | таблицы `fx_events`, `fx_leads`, `fx_sessions` (Retain) — на 30 дней; секрет `aluma/admin-credentials` — решение владельца |
| **Не трогать — общее** | 11 строк | зона Route 53, общий SAM-бакет и его стек, 3 других стека, 2 другие дистрибуции, остальные сертификаты, IAM-пользователи, бюджет, прочие логи/секреты/функции |
| **Деньги** | ≈ **$0.40–0.45 в месяц** | из них $0.40 — секрет; всё остальное ALUMA укладывается в бесплатные уровни (§6) |

---

## 2. Стек `fx-table` — что будет при `delete-stack`

Стек: `UPDATE_COMPLETE`, создан 2026-09-01, последнее обновление 2026-09-11 11:30 UTC (выкат 0.4.0),
`EnableTerminationProtection = false`, экспортов (`list-exports`) нет — ни один другой стек от него не зависит.
DeletionPolicy — из `get-template --template-stage Processed`.

| Логический id | Тип | Физический id | DeletionPolicy | При удалении стека |
|---|---|---|---|---|
| `FxEventsTable` | DynamoDB::Table | `fx_events` | **Retain** | **останется** (§4) |
| `FxLeadsTable` | DynamoDB::Table | `fx_leads` | **Retain** | **останется** (§4) |
| `FxSessionsTable` | DynamoDB::Table | `fx_sessions` | **Retain** | **останется** (§4) |
| `SiteBucket` | S3::Bucket | `fx-table-site-000000000000` | Delete | **удаление упадёт, если бакет не пуст** → стек в `DELETE_FAILED`. Сейчас 358 объектов, 9.6 МБ, версионирование **выключено**, lifecycle/object lock/репликации нет. Лечение: шаг 3 (очистить) до шага 4 |
| `SiteBucketPolicy` | S3::BucketPolicy | на тот же бакет | Delete | удалится |
| `Distribution` | CloudFront::Distribution | `E21KNA4YOX9CIB` (`dnj0089lrzf76.cloudfront.net`) | Delete | удалится; CloudFormation сам сначала выключает её и ждёт — **15–45 минут** |
| `IndexRewrite` | CloudFront::Function | `fx-table-index-rewrite` | Delete | удалится (после дистрибуции — порядок CFN соблюдает сам) |
| `SiteOac` | CloudFront::OriginAccessControl | `E2KHW7MW8K25XT` | Delete | удалится |
| `ApiOriginRequestPolicy` | CloudFront::OriginRequestPolicy | `a121b12a-5351-48b8-bc6d-c54e85b46b77` | Delete | удалится |
| `FxApi` | Lambda::Function | `fx-table-api` | Delete | удалится — вместе с ручным правом `CfOacNoCond` (см. ниже) |
| `FxApiRole` | IAM::Role | `fx-table-FxApiRole-BiE09PLkm3Zy` | Delete | удалится с 3 inline-политиками и привязкой `AWSLambdaBasicExecutionRole` |
| `FxApiInvokePermission` | Lambda::Permission | `fx-table-FxApiInvokePermission-dNt5oTawxuFN` | Delete | удалится |
| `FxHttpApi` | ApiGatewayV2::Api | `r7jel27uma` | Delete | удалится |
| `FxHttpApiApiGatewayDefaultStage` | ApiGatewayV2::Stage | `$default` | Delete | удалится |

Замечено при описи (дрейф от шаблона, на удаление не влияет):

- В ресурсной политике лямбды два права: стековое (`apigateway.amazonaws.com`, `r7jel27uma/*`) и
  **ручное `CfOacNoCond`** (`cloudfront.amazonaws.com`, только `E21KNA4YOX9CIB`) — след эксперимента с
  Function URL 01.09 (`night-2026-09-01/DECISIONS.md` D-021). Живёт внутри функции, уйдёт вместе с ней.
- PITR в шаблоне включён только у `fx_leads`, а по факту — у всех трёх таблиц (у `fx_events` и `fx_sessions`
  самая ранняя точка восстановления — 2026-09-10 12:17 UTC, т.е. включали руками 10.09).

---

## 3. ALUMA вне стека — и почему это только ALUMA

Искал по `fx-table`, `fx_`, `table.central-aparts.store`, `aluma`, `E21KNA4YOX9CIB`, `r7jel27uma`, `d2a264f2`.

| Ресурс | Id | Кто на него ссылается (проверено) | Вывод |
|---|---|---|---|
| ACM-сертификат `table.central-aparts.store` (us-east-1) | `arn:aws:acm:us-east-1:<account>:certificate/d2a264f2-b347-4ba3-8e58-d2139eda0c69` | `InUseBy` = только `E21KNA4YOX9CIB`; SAN только `table.central-aparts.store`; действует до 2027-03-18. Параметр стека `CertificateArn` — сам сертификат стеком не создан. Caddy на коробке берёт Let's Encrypt, ACM не нужен | только ALUMA → удалить после дистрибуции |
| CNAME валидации ACM в зоне `Z05565972H1DV59U5PO4I` | `_76330d86a537e3871c91496e2f84668a.table.central-aparts.store.` → `_899f0cee4466647eed6cd591e1093e6a.jkddzztszm.acm-validations.aws.`, TTL 300 | Совпадает с `DomainValidationOptions` только этого сертификата. Два других CNAME валидации в зоне (`_71ac…` у апекса, `_10af…` у `www`) — чужие | только ALUMA → удалить после сертификата |
| Группа логов | `/aws/lambda/fx-table-api`, 96 205 байт, retention не выставлена, фильтров метрик и подписок нет | Пишет только лямбда `fx-table-api` (`LoggingConfig.LogGroup`). **Не в стеке** — после `delete-stack` останется | только ALUMA → удалить после стека |
| Артефакты SAM в общем бакете | `aws-sam-cli-managed-default-samclisourcebucket-tqh5bzqhj11n`, префикс `fx-table/`: **13 объектов, 794 673 байта**, 13 версий, 0 delete-маркеров (01.09–11.09) | Префикс задан в `infra/samconfig.toml.example` (`s3_prefix = "fx-table"`); текущий шаблон стека ссылается на `fx-table/7e19cbff01d127f0bd335fb02a0d76f1`. Вне префикса ключей с `fx`/`table` нет. **Бакет версионирован** — простое `rm` оставит старые версии | только ALUMA (сами объекты) → удалить по версиям; бакет — общий, не трогать |
| Секрет | `aluma/admin-credentials` (создан 2026-09-10, «admin login and IP_SALT — was only on the laptop disk») | `LastAccessedDate` = пусто (API его не читал ни разу), ротации и ресурсной политики нет. В коде всех 15 репозиториев `~/repos` имя встречается только в `aparts/docs/plans/HANDOFF-2026-09-10.md` (описание, не чтение). В env всех 10 лямбд — ни одного совпадения с `aluma`/`fx` (проверено числом, значения не печатались) | только ALUMA, но это **резервная копия** живых секретов коробки → §4 |
| EventBridge, Scheduler, алармы, дашборды, AWS Backup, SSM | — | Правил с целью `fx-table-api` — 0; правил с `fx`/`table`/`aluma` в имени — 0; расписаний — 1 (`aparts-monitor-daily-scan`, чужое); алармов в обоих регионах — 0; дашбордов — 0; планов Backup — 0; SSM-параметров ALUMA — 0 | ничего нет |
| Бюджеты | `aparts-monthly-10usd` ($10, без фильтров) | общий на весь аккаунт | не трогать |

Перекрёстные проверки «на нас никто не ссылается»:

- **CloudFormation:** шаблоны `aparts`, `aparts-v2`, `aparts-monitor`, `aws-sam-cli-managed-default` —
  0 вхождений любого из идентификаторов ALUMA. Экспортов нет, StackSets нет.
- **IAM:** роль `fx-table-FxApiRole-…` использует только `fx-table-api`. Inline-политики всех ролей и
  пользователей просмотрены: `fx_`/`fx-table`/`aluma` встречается только в трёх политиках самой этой роли.
  Customer-managed политик в аккаунте нет.
- **CloudFront:** `a121b12a…` (ORP), OAC `E2KHW7MW8K25XT` и функция `fx-table-index-rewrite` подключены
  только к `E21KNA4YOX9CIB` (проверены все 3 дистрибуции). Остальные политики в дистрибуции
  (`Managed-CachingOptimized`, `Managed-CachingDisabled`, `Managed-SecurityHeadersPolicy`) — управляемые
  AWS, их не удалить и трогать не нужно. Логирования, WAF, Lambda@Edge, KeyValueStore нет.
- **API Gateway:** `r7jel27uma` — единственный HTTP API в аккаунте; кастомных доменов, VPC-линков,
  авторайзеров, usage plans нет; access-логи не включены.
- **DynamoDB:** у `fx_*` нет стримов, GSI, реплик, ресурсных политик, on-demand бэкапов, экспортов.
- **Теги:** `project=fx-table` висит ровно на 3 таблицах, бакете сайта и дистрибуции.
- **Telegram-бот не наш ресурс:** `scripts/box_env.py` берёт `TELEGRAM_BOT_TOKEN` из env лямбды
  `aparts-api` — бот и чат общие с aparts. Удаление `fx-table-api` бота не касается.

---

## 4. Оставить как резервную копию

| Ресурс | Сейчас | Почему оставить | Когда и чем убрать |
|---|---|---|---|
| `fx_events` | 1 072 записи, 481 КБ, TTL `ttl` вкл., PITR вкл. (35 дней), DeletionProtection **выкл.** | единственный «оригинал» данных до переезда; стоит ≈ $0 | через **30 дней после `delete-stack`**, после дампа и сверки (ниже) |
| `fx_leads` | 21 запись, 9 КБ, TTL выкл., PITR вкл., DeletionProtection **выкл.** | заявки — самое ценное | так же; последней из трёх |
| `fx_sessions` | 81 запись, 20 КБ, TTL вкл., PITR вкл., DeletionProtection **выкл.** | как `fx_events` | так же |
| Секрет `aluma/admin-credentials` | $0.40/мес, ни разу не читался | **единственная копия `ADMIN_PASS` и `IP_SALT` вне коробки.** После удаления лямбды `box_env.py` пересоздать env не сможет (он читает их из `fx-table-api`) | решение владельца (§8, п.1) |

`ItemCount` в DynamoDB обновляется раз в ~6 часов — это приблизительные числа; точные даёт дамп.

После `delete-stack` таблицы становятся «ничьими»: CloudFormation их больше не ведёт, TTL в `fx_events` и
`fx_sessions` продолжит удалять старые строки (это нормально — на коробке их прибирает `purge.py`).

**Удаление таблиц (через 30 дней, отдельное «да» владельца):**

```bash
cd /opt/ihor/aluma-table
install -d -m 0700 dump-aws-last-<дата>
.venv/bin/python scripts/migrate_fx.py --phase dump --dump-dir dump-aws-last-<дата>
.venv/bin/python scripts/migrate_fx.py --phase verify --second-pass \
  --dump-dir dump-aws-last-<дата> --db data/aluma.db \
  --leads-since <taken_at ПЕРВОГО снимка, CUTOVER-CHECKLIST шаг 4>
# «не доїхало 0» во всех трёх таблицах, «непояснених 0» в fx_leads, код 0 — иначе стоп
# дамп лежит в 0700 и не печатается; это последняя копия AWS-данных, её не удалять

# НЕ ВЫПОЛНЯТЬ без «да» владельца:
aws dynamodb delete-table --table-name fx_sessions --region eu-central-1
aws dynamodb delete-table --table-name fx_events   --region eu-central-1
aws dynamodb delete-table --table-name fx_leads    --region eu-central-1
```

По документации AWS при удалении таблицы с включённым PITR DynamoDB сам делает системный бэкап и держит его
35 дней — **не проверялось**; опираться нужно на дамп в `/opt/ihor`, а не на это.

Перед удалением таблиц должна быть решена судьба `scripts/daily_report.py`: он читает `fx_events`/`fx_leads`
напрямую из DynamoDB через boto3 и сломается (§8, п.2). Таймера или cron у него нет — запускается руками.

---

## 5. Не трогать — общее

| Ресурс | Id | Почему не трогать |
|---|---|---|
| Зона Route 53 | `Z05565972H1DV59U5PO4I` (`central-aparts.store`, 20 записей) | общая на все проекты. Из неё уходит **одна** запись — CNAME валидации `table` (шаг 7). Запись `table` (A на коробку) — это новый прод, её не трогаем. `table-new` — проверочное имя ALUMA на коробке, к старому AWS не относится (§8, п.4) |
| Общий SAM-бакет | `aws-sam-cli-managed-default-samclisourcebucket-tqh5bzqhj11n` (654 объекта, 10.6 ГБ) | в нём артефакты `aparts`, `v2-deploy` и корневые шаблоны. Удаляются только 13 версий под `fx-table/` |
| Стек SAM | `aws-sam-cli-managed-default` | владеет общим бакетом |
| Стеки | `aparts`, `aparts-v2`, `aparts-monitor` | чужие; ссылок на ALUMA 0 |
| CloudFront | `E80XDWDORZKYP` (`cv`), `E3A58MFOU2LI12` (`v2`/`www`/апекс), функция `chernivtsi-guide-strip-prefix` | чужие |
| ACM (us-east-1) | остальные 5 сертификатов, включая неиспользуемый `bill.cv.central-aparts.store` | чужие |
| CNAME валидации | `_71ac114f…central-aparts.store.`, `_10afe89f…www.central-aparts.store.` | принадлежат чужим сертификатам |
| IAM | два пользователя-деплойщика соседних проектов (права выданы владельцем аккаунта), остальные 17 ролей | общие; ключ одного из них нужен серверу для всего |
| Бюджет | `aparts-monthly-10usd` | на весь аккаунт |
| Логи, секреты, функции, таблицы | всё без `fx`/`aluma` в имени (8 групп логов, 15 секретов, 9 лямбд, 12 таблиц `aparts-*`) | чужие |
| Управляемые политики CloudFront | `658327ea…`, `4135ea2d…`, `67f7725c…` | принадлежат AWS |

---

## 6. Деньги

Один запрос Cost Explorer (`GetCostAndUsage`, 2026-08-01…2026-09-11, группировка SERVICE × тег `project`).
**Тег `project` не активирован как cost allocation tag** — все расходы легли в «без тега», отдельной строки
ALUMA Cost Explorer не даёт. Поэтому — оценка по ресурсам:

| Статья | ALUMA в месяц | Основание |
|---|---|---|
| Secrets Manager `aluma/admin-credentials` | **$0.40** | прайс $0.40/секрет |
| API Gateway `r7jel27uma` | ≈ $0.00 | единственный API в аккаунте: CE за 1–10.09 = **$0.0005** — это целиком ALUMA |
| DynamoDB `fx_*` | ≈ $0.00–0.02 | 0.5 МБ хранения, тысячи запросов в месяц, PITR $0.20/ГБ. Строка DynamoDB в сентябре ($1.64) — почти целиком aparts, точнее разделить нельзя |
| CloudFront, Lambda, CloudFront Functions | $0.00 | в бесплатных уровнях (1 ТБ / 10 млн запросов; 1 млн вызовов): за 14 дней ~9.6 тыс. запросов CloudFront, ~440 вызовов лямбды |
| S3 (сайт 9.6 МБ + артефакты 0.8 МБ), CloudWatch Logs (96 КБ), ACM | ≈ $0.00 | копейки / бесплатно |
| **Итого** | **≈ $0.40–0.45/мес (~$5/год)** | |

Эффект удаления — не деньги, а то, что пропадают второй прод и лишняя поверхность атаки: публичный
`execute-api`-адрес, копия `TELEGRAM_BOT_TOKEN`/`ADMIN_PASS`/`IP_SALT`/`EDGE_SECRET` в env мёртвой лямбды,
вторая `/admin`.

---

## 7. План удаления

**Этот план уже выполнен целиком — 2026-09-11 и 2026-09-12. Запускать команды ниже повторно не нужно и
нечего: объекты, на которые они ссылаются, удалены (см. «Выполнено» и «Подтверждение: ничего не
осталось»). Раздел оставлен как запись того, что и в каком порядке делалось.**

Точка невозврата — **шаг 3**: после него DNS-откат уже не поднимет сайт на AWS. После шага 4 возврат —
только новым `sam deploy` (шаблон в git, сертификат живёт до шага 6).

### Шаг 0. Предусловия — все обязательны

1. **DNS переключён** (чек-лист, шаг 8.1): у `table` только `A 95.216.10.169`, alias на CloudFront нет.
   ```bash
   aws route53 list-resource-record-sets --hosted-zone-id Z05565972H1DV59U5PO4I \
     --query "ResourceRecordSets[?Name=='table.central-aparts.store.']" --output json
   dig +short table.central-aparts.store A      # 95.216.10.169
   dig +short table.central-aparts.store AAAA   # пусто
   ```
2. **Прошло ≥ 48 часов** с момента 8.1 (время UTC записано на шаге 8.1 чек-листа).
3. **Лямбда молчит все 48 часов:** каждое значение 0 или список пуст.
   ```bash
   aws cloudwatch get-metric-statistics --region eu-central-1 --namespace AWS/Lambda \
     --metric-name Invocations --dimensions Name=FunctionName,Value=fx-table-api \
     --start-time <время 8.1, UTC> --end-time <сейчас, UTC> \
     --period 3600 --statistics Sum --query 'Datapoints[?Sum>`0`]'
   # []  — иначе СТОП: кто-то ещё ходит на старый стек, выяснить до удаления
   ```
   Запросы CloudFront (`AWS/CloudFront Requests`, us-east-1) могут быть ненулевыми — боты по старому
   `dnj0089lrzf76.cloudfront.net`. Это не блокер: статика данных не пишет.
4. **Финальный перенос сделан** (чек-лист 8.5–8.7, verify второго прохода ЗЕЛЕНО) **и свежий контрольный
   дамп перед удалением** — те же команды, что в §4, в `dump-aws-last-<дата>`: «не доїхало 0»,
   «непояснених 0». Таблицы при этом остаются (Retain) — это вторая страховка, не первая.
5. **Env коробки полный** — после удаления лямбды `box_env.py` его не пересоздаст:
   ```bash
   python3 scripts/box_env.py --check ~/.config/aluma/aluma.env   # только имена и «задано/пусто»
   ```
6. **Решения владельца по §8, пп.1–2 приняты**, «да» на удаление получено, главный дирижёр предупреждён за
   10 минут. Никто не запускает `scripts/deploy.sh` (он заново зальёт объекты в бакет).

### Шаг 1. Снимок «до»

Команды — в §9 (`D=…/before`). Без снимка «до» шаг 9 не доказывает ничего.

### Шаг 2 (по желанию). Архив выложенного сайта

Сайт воспроизводится из git (`build.py`), но точную выложенную сборку можно сохранить — это чтение из AWS:

```bash
install -d -m 0700 /opt/ihor/aluma-table/teardown-<дата>/site-s3
aws s3 sync s3://fx-table-site-000000000000 /opt/ihor/aluma-table/teardown-<дата>/site-s3 --only-show-errors
```

### Шаг 3. Очистить бакет сайта  ⚠ точка невозврата

```bash
# НЕ ВЫПОЛНЯТЬ без «да» владельца
aws s3 rm s3://fx-table-site-000000000000 --recursive --only-show-errors
aws s3api list-object-versions --bucket fx-table-site-000000000000 \
  --query '{v:length(Versions||`[]`),d:length(DeleteMarkers||`[]`)}'   # {"v": 0, "d": 0}
```

Версионирование на бакете выключено — после `rm` он действительно пуст.

### Шаг 4. Удалить стек

```bash
# НЕ ВЫПОЛНЯТЬ без «да» владельца
aws cloudformation delete-stack --stack-name fx-table --region eu-central-1
aws cloudformation wait stack-delete-complete --stack-name fx-table --region eu-central-1
aws cloudformation describe-stacks --stack-name fx-table --region eu-central-1   # «does not exist»
```

- `sam delete` **не используем**: он интерактивный и в общем бакете трогает артефакты по-своему; явные
  команды проще проверить.
- Ждать 15–45 минут (CloudFront). `wait` сдаётся через час — тогда смотреть
  `describe-stack-events --stack-name fx-table`.
- `DELETE_FAILED` на `SiteBucket` = в бакет что-то попало после шага 3 → повторить шаг 3, затем `delete-stack`
  ещё раз. `--retain-resources` не использовать: оставит мусор вне учёта.
- Удаляется 11 ресурсов, три таблицы остаются (`DELETE_SKIPPED` в событиях — это норма).

### Шаг 5. Группа логов

```bash
# НЕ ВЫПОЛНЯТЬ без «да» владельца. Только после шага 4 — иначе живая лямбда создаст группу заново
aws logs delete-log-group --log-group-name /aws/lambda/fx-table-api --region eu-central-1
```

### Шаг 6. ACM-сертификат — после дистрибуции

```bash
aws acm describe-certificate --region us-east-1 \
  --certificate-arn arn:aws:acm:us-east-1:<account>:certificate/d2a264f2-b347-4ba3-8e58-d2139eda0c69 \
  --query Certificate.InUseBy            # [] — иначе дистрибуция ещё не удалена, ждать
# НЕ ВЫПОЛНЯТЬ без «да» владельца
aws acm delete-certificate --region us-east-1 \
  --certificate-arn arn:aws:acm:us-east-1:<account>:certificate/d2a264f2-b347-4ba3-8e58-d2139eda0c69
```

### Шаг 7. CNAME валидации — после сертификата

Файл `rm-acm-cname.json` (DELETE обязан совпасть с записью до байта, иначе Route 53 отклонит всю пачку и
ничего не изменит — безопасный отказ):

```json
{"Comment": "ALUMA: CNAME валидации ACM удалённого сертификата table",
 "Changes": [
  {"Action": "DELETE", "ResourceRecordSet": {
    "Name": "_76330d86a537e3871c91496e2f84668a.table.central-aparts.store.", "Type": "CNAME", "TTL": 300,
    "ResourceRecords": [{"Value": "_899f0cee4466647eed6cd591e1093e6a.jkddzztszm.acm-validations.aws."}]}}
 ]}
```

```bash
# НЕ ВЫПОЛНЯТЬ без «да» владельца
aws route53 change-resource-record-sets --hosted-zone-id Z05565972H1DV59U5PO4I \
  --change-batch file://rm-acm-cname.json
```

### Шаг 8. Артефакты SAM под `fx-table/` в общем бакете

Бакет версионирован — удаляем конкретные версии, и только под префиксом. Экономия ≈ $0, поэтому шаг
можно пропустить; делать — только с проверкой списка.

```bash
B=aws-sam-cli-managed-default-samclisourcebucket-tqh5bzqhj11n
aws s3api list-object-versions --bucket "$B" --prefix fx-table/ \
  --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}, Quiet: `false`}' --output json > fx-sam.json
python3 -c 'import json;k=[o["Key"] for o in json.load(open("fx-sam.json"))["Objects"]];assert k and all(x.startswith("fx-table/") for x in k);print(len(k),"ключей, все под fx-table/")'
# «13 ключей, все под fx-table/» (или больше, если были новые sam deploy) — иначе СТОП
# НЕ ВЫПОЛНЯТЬ без «да» владельца
aws s3api delete-objects --bucket "$B" --delete file://fx-sam.json
aws s3api list-object-versions --bucket "$B" --prefix fx-table/ \
  --query '{v:length(Versions||`[]`),d:length(DeleteMarkers||`[]`)}'     # {"v": 0, "d": 0}
```

### Шаг 9. Снимок «после» и сверка — §9

### Позже

- ~~+30 дней: таблицы `fx_*` (§4)~~ — решением владельца от 11.09 удалены сразу, пачкой 2 (15:27Z 11.09).
- ~~Секрет `aluma/admin-credentials` — по решению владельца~~ — удалён пачкой 3 (06:13:33Z 12.09) с окном
  **7** дней, а не 30: `--recovery-window-in-days 7`, без `--force-delete-without-recovery`. Исчезнет сам
  2026-09-19 09:13 +03:00; до этой даты восстановим через `secretsmanager restore-secret`.
- В репозитории — отдельной задачей: `infra/`, `scripts/deploy.sh`, `scripts/prod_notify_params.py`,
  AWS-ветка `scripts/box_env.py`, `scripts/daily_report.py` и `rollback/fx-table-api-0.3.0-*.zip` на коробке
  становятся мёртвыми.

---

## 8. Требует решения владельца

1. **Секрет `aluma/admin-credentials` ($0.40/мес).** Это единственная копия `ADMIN_PASS` и `IP_SALT` вне
   коробки. Рекомендация: **оставить**, пока env коробки (`~/.config/aluma/aluma.env`) не попадает в бэкап
   вне машины; потом удалить с окном 30 дней. Потеря не катастрофа (пароль меняется, соль только
   переобнулит `ip_hash`), но неприятна.
2. **`scripts/daily_report.py`** читает DynamoDB напрямую. Не блокирует удаление стека, но блокирует удаление
   таблиц: перевести на SQLite коробки или списать.
3. **Срок жизни таблиц `fx_*` после удаления стека.** Предложено 30 дней; стоят ≈ $0, так что можно и дольше.
   По желанию владелец может включить им DeletionProtection сразу после шага 4 (это запись в AWS — только сам).
4. **`table-new.central-aparts.store`** (A → 95.216.10.169) — проверочное имя, к старому AWS не относится;
   убрать после переключения или оставить — отдельное решение.
5. **Кто выполняет** шаги 3–8: владелец сам или сессия с явным письменным разрешением на эти команды.

---

## 9. Как проверить, что удалено только наше

Снимок снимается дважды — `before` (шаг 1) и `after` (шаг 9) — одним и тем же блоком, меняется только `D`.
Всё — чтение.

```bash
D=/opt/ihor/aluma-table/teardown-<дата>/before       # на шаге 9: …/after
install -d -m 0700 "$D"
R='--region eu-central-1'
aws cloudformation list-stacks $R --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --query 'StackSummaries[].StackName' --output text | tr '\t' '\n' | sort > "$D/stacks.txt"
aws cloudfront list-distributions --query 'DistributionList.Items[].[Id,Aliases.Items[0],Status,Enabled]' \
  --output text | sort > "$D/cloudfront.txt"
aws cloudfront list-functions --query 'FunctionList.Items[].Name' --output text | tr '\t' '\n' | sort -u > "$D/cf-functions.txt"
aws acm list-certificates --region us-east-1 --query 'CertificateSummaryList[].[DomainName,CertificateArn]' \
  --output text | sort > "$D/acm.txt"
aws route53 list-resource-record-sets --hosted-zone-id Z05565972H1DV59U5PO4I \
  --query 'ResourceRecordSets[].[Name,Type]' --output text | sort > "$D/route53.txt"
aws lambda list-functions $R --query 'Functions[].FunctionName' --output text | tr '\t' '\n' | sort > "$D/lambda.txt"
aws apigatewayv2 get-apis $R --query 'Items[].[ApiId,Name]' --output text | sort > "$D/apigw.txt"
aws logs describe-log-groups $R --query 'logGroups[].logGroupName' --output text | tr '\t' '\n' | sort > "$D/logs.txt"
aws secretsmanager list-secrets $R --query 'SecretList[].Name' --output text | tr '\t' '\n' | sort > "$D/secrets.txt"
aws dynamodb list-tables $R --query TableNames --output text | tr '\t' '\n' | sort > "$D/dynamodb.txt"
aws iam list-roles --query 'Roles[].RoleName' --output text | tr '\t' '\n' | sort > "$D/iam-roles.txt"
aws s3api list-buckets --query 'Buckets[].Name' --output text | tr '\t' '\n' | sort > "$D/buckets.txt"
aws s3api list-object-versions --bucket aws-sam-cli-managed-default-samclisourcebucket-tqh5bzqhj11n \
  --query 'Versions[].[Key,VersionId]' --output text | sort > "$D/sam-versions.txt"
for h in central-aparts.store www.central-aparts.store v2.central-aparts.store cv.central-aparts.store \
         table.central-aparts.store; do
  curl -s -o /dev/null --max-time 15 -w "$h %{http_code}\n" "https://$h/"
done > "$D/http.txt"
```

Сверка: `diff -r teardown-<дата>/before teardown-<дата>/after`. Допустимы **ровно** эти отличия:

| Файл | Ожидаемое отличие |
|---|---|
| `stacks.txt` | − `fx-table` |
| `cloudfront.txt` | − строка `E21KNA4YOX9CIB`; строки `E80XDWDORZKYP` и `E3A58MFOU2LI12` — без изменений, `Deployed True` |
| `cf-functions.txt` | − `fx-table-index-rewrite` |
| `acm.txt` | − `table.central-aparts.store` |
| `route53.txt` | − `_76330d86a537e3871c91496e2f84668a.table.central-aparts.store. CNAME`; всё остальное, включая `table A`, на месте |
| `lambda.txt` | − `fx-table-api` (остаются 9) |
| `apigw.txt` | − `r7jel27uma` (становится пусто) |
| `logs.txt` | − `/aws/lambda/fx-table-api` |
| `iam-roles.txt` | − `fx-table-FxApiRole-BiE09PLkm3Zy` |
| `buckets.txt` | − `fx-table-site-000000000000` |
| `sam-versions.txt` | − только строки с ключом `fx-table/…` (13 шт.); ни одной другой |
| `dynamodb.txt` | **без изменений** — `fx_*` на месте (Retain) |
| `secrets.txt` | без изменений (если владелец не решил иначе) |
| `http.txt` | чужие хосты — те же коды, что «до»; `table` — 200 с коробки |

Плюс: `curl -s https://table.central-aparts.store/api/fx/health` → `0.4.0-box`; адмінка на коробке пускает.
**Любое другое отличие — стоп и разбор до следующего шага.** Проверку `http.txt` имеет смысл повторить и
сразу после шага 4 (самый крупный шаг).
