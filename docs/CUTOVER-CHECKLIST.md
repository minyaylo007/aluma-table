# ALUMA — чек-лист переїзду з AWS на ace-main

Один файл, по порядку виконання. У кожного кроку є **Перевірка** — команда і те,
що вона МУСИТЬ віддати. «Зроблено» без відповіді команди кроком не вважається.

Чому саме так — у `deploy/README.md` (розділ «Користувацькі юніти»), у коментарях
`deploy/aluma.env.example`, `deploy/systemd/user/*` і `deploy/caddy/REQUEST-DENIS.md`.
Тут — послідовність і докази.

**Стан на 2026-09-12. Переїзд закінчено, старого AWS немає — цей файл тепер історія й докази.**
`table.central-aparts.store` дивиться на коробку з `2026-09-11T12:42:31Z` (коміт `a7e9c64`, «Журнал
переключення 11.09» нижче). Старий AWS ALUMA видалено повністю: стек `fx-table` (CloudFront, Lambda,
API Gateway) і таблиці `fx_*` — 11.09 15:08–15:28Z, решта — 12.09 06:11–06:14Z, звірка «до/після» зелена
(`docs/AWS-TEARDOWN.md`, коміт `3789f0c`). **Тому відкат кроку 10 (повернути DNS на CloudFront) більше
неможливий**, а разом із ним і «НЕ перевірено» про майбутнє переключення нижче: усе це вже сталося.
Поставка нових версій — `docs/DELIVERY.md` (як зараз — клон `563edc8` і юніти, поставлені руками; після
установки агента (T040) — агент).

**Хто що робить.** Написане нижче про «заявку Денису» — стан до 11.09. З `OWNER-RULES.md` п.20–21 свої
блоки Caddy ставимо самі, і блок `table` 11.09 поставили ми (журнал переключення, 8.2): сесія з явними
рядками «разрешено sudo» в завданні — копія Caddyfile, лише свій `import`, `validate`, **тільки** `reload`,
перевірка чужих сайтів до і після. Решта `sudo` сесіям і далі заборонена. DNS (Route 53, зона
`central-aparts.store`) — зміна бойового запису лише в день переключення, з
оголошенням власнику за 10 хвилин і готовим відкатом (`~/maestro/OWNER-RULES.md`, п.17).
DynamoDB — **тільки читання** (`scan`), на жодному кроці ні `put-item`, ні `delete-item`.

---

## ⚠️ ПРОЧИТАТИ ПЕРШИМ: другий прохід verify — з `--second-pass --leads-since`

Між першим і фінальним дампом дві речі законно розводять базу й знімок:

1. **TTL** у DynamoDB прибирає частину подій і сесій, які перший прохід уже залив
   у SQLite. `fx_events`, `fx_sessions`: у базі може бути БІЛЬШЕ, ніж у знімку.
2. **Коробка сама приймає заявки**: смоки (`is_test`), перевірка через
   `table-new`, а після 7.1 — справжні гості. У фінальному знімку DynamoDB цих
   заявок немає й бути не може.

`--second-pass` послаблює рівно це, і нічого більше:

- `fx_events`, `fx_sessions`: кожен ключ знімка є в базі; зайві — законні (TTL);
- `fx_leads`: **жодної пропажі** — кожна заявка знімка є в базі з тим самим вмістом
  (пункт 2-біс); зайва заявка законна **лише** якщо вона `is_test` АБО її `ts`
  пізніший за `--leads-since`. Решта — «непояснених N» і ЧЕРВОНО;
- `--leads-since` у вікні = `taken_at` **ПЕРШОГО** знімка (крок 4). Без нього поріг —
  час фінального знімка, а він знятий ПІСЛЯ переключення: справжня заявка, що прийшла
  на коробку між 7.1 і 7.3, старша за нього — і дала б хибне ЧЕРВОНО.

**Без прапорця на другому проході буде ЧЕРВОНО, і це не привід відкочуватись** —
це не та команда. На ПЕРШОМУ проході прапорець не ставити: там строгість доречна.
Крок 4 — без прапорця, крок 7.5 — з обома.

---

## Крок 0. Передумови

- Денис прийняв заявку `deploy/caddy/REQUEST-DENIS.md` (тека `/srv/aluma`, блоки Caddy);
- значення з живих Lambda читаються (`fx-table-api`, `aparts-api`), DynamoDB — на читання;
- порт 8005 закріплений за ALUMA в `~/maestro/PORTS.md`.

**Перевірка.**

```bash
aws dynamodb describe-table --table-name fx_leads --region eu-central-1 \
  --query 'Table.ItemCount'       # очікувано: число, не помилка доступу
```

---

## Крок 1. Клон і venv — ✅ зроблено 2026-09-11

Прод-клон `/opt/ihor/aluma-table` — **окремий клон, не worktree** (робочі дерева сесій
видаляються разом із сесією), у detached HEAD на зафіксованому sha. Тека вже містила
`rollback/` (zip відкату лямбди 0.3.0), тому клон робився так, щоб її не зачепити:

```bash
umask 027
cd /opt/ihor/aluma-table
git init -q . && git remote add origin git@github.com:minyaylo007/aluma-table.git
git fetch -q origin master
printf '%s\n' /rollback/ '/dump-*/' /.venv/ >> .git/info/exclude
git checkout -q --detach <sha>
chmod o-rwx /opt/ihor/aluma-table       # правило «Общие ресурсы»: «іншим» — нуль
python3 -m venv .venv && .venv/bin/pip install -r deploy/requirements-server.txt
install -d -m 0700 data                  # ЗАЗДАЛЕГІДЬ: store.py створив би її 0775
```

Оновлення клону на новий master — **замінено** (`docs/DELIVERY.md`): як зараз — лише з «так» власника
(викат поза конвеєром, конституція VI); після установки агента (T040) версії ставить агент, клон не оновлюють.

**Перевірка.**

```bash
.venv/bin/gunicorn --version                                   # gunicorn (version 26.2.0)
.venv/bin/gunicorn --help | grep -c -- '--no-control-socket'   # 1
stat -c '%a %n' /opt/ihor/aluma-table /opt/ihor/aluma-table/data   # 770 і 700
```

> **`boto3` потрібен НАВІТЬ у режимі sqlite:** `api/handler.py` імпортує його
> безумовно. Без нього gunicorn падає на старті, юніт іде в перезапуск по колу.

---

## Крок 2. Оточення: `~/.config/aluma/aluma.env` — ✅ зроблено 2026-09-11

Не `/etc/aluma` (нема прав і не треба) і не в клоні (секретам не місце в дереві коду).
Файл пише програма, яка значень не друкує ні в stdout, ні в аргументи процесів:

```bash
python3 scripts/box_env.py --app-version 0.4.0-box --out ~/.config/aluma/aluma.env
```

Звідки що: `ADMIN_USER`, `ADMIN_PASS`, `IP_SALT`, `SITE_DOMAIN`, `WHATSAPP_NUMBER` — з
Lambda `fx-table-api`; `TELEGRAM_BOT_TOKEN`, `OWNER_TELEGRAM_CHAT_ID` — з `aparts-api`;
`FX_STORAGE=sqlite`, `FX_DB_PATH=/opt/ihor/aluma-table/data/aluma.db`,
`APP_VERSION=0.4.0-box`. Файл `0600`, тека `0700`, існуючий не перезаписується.

### 2.1. `EDGE_SECRET` — НЕ переноситься. Зовсім.

Він має сенс лише як спільний секрет із CloudFront. Задай його на коробці — перевірка
в `handler.py` стоїть **до маршрутизації** і віддасть 403 на ВСЕ: health, заявки,
адмінку. `box_env.py` його не пише навіть коли він є в джерелі.

### 2.2. `IP_SALT` і `ADMIN_PASS` — незмінними, символ у символ

Вони підписують куку адмінки (`_session_secret()`) і солять `hash_ip()`. Інше
значення — власника викине з адмінки рівно в момент переїзду, а ведра лімітів і
`ip_hash` старих заявок перестануть зводитись.

### 2.3. `FX_STORAGE=sqlite` — явно

**Перевірка** (значення не друкуються; `--pid` звіряє з оточенням живого процесу, тобто
доводить, що systemd розібрав файл рівно як записано):

```bash
python3 scripts/box_env.py --check ~/.config/aluma/aluma.env \
    --pid "$(systemctl --user show -p MainPID --value ihor-aluma-api)"
# права 600, папка 700; 10 ключів «совпадает»; «итог: ок»; EDGE_SECRET — нема
```

---

## Крок 3. `FX_STORAGE=dynamodb` у лямбді — лише якщо новий код їде в Lambda

Стосується **тільки** випадку, коли до переїзду бекенд `master` викочують у Lambda
(`docs/PROD-NOTIFY-DECISION.md`, робить власник). Дефолт у коді — sqlite з відносним
шляхом; лямбда без цієї змінної віддає 500 на КОЖНУ заявку й подію, а health лишається
200 (доведено `tests/test_lambda_no_fx_storage.py`). Змінна вже є в `infra/template.yaml`.

**Перевірка** (після такого викату):

```bash
aws lambda get-function-configuration --function-name fx-table-api \
  --region eu-central-1 --query 'Environment.Variables.FX_STORAGE'   # "dynamodb"
```

---

## Крок 4. Перший прохід переносу — ✅ зроблено 2026-09-11

```bash
cd /opt/ihor/aluma-table
install -d -m 0700 dump-<дата>
.venv/bin/python scripts/migrate_fx.py --phase dump   --dump-dir dump-<дата>
.venv/bin/python scripts/migrate_fx.py --phase load   --dump-dir dump-<дата>
.venv/bin/python scripts/migrate_fx.py --phase verify --dump-dir dump-<дата>
```

Скрипт сам ставить `umask 027`: знімок і база не ширші за `0640`/`0750`.

**Перевірка.** Останній рядок verify — `verify: ЗЕЛЕНО — усі перевірки пройшли`, код `0`.

**Що вийшло 2026-09-11** (`dump-2026-09-11`): знімок `taken_at` =
**`2026-09-11T11:02:12.816423+00:00`** — це `--leads-since` для кроку 7.5, якщо перший
прохід не повторюватимуть. `scan` тривав ~1 с, рядків: `fx_events` 1065, `fx_leads` 20
(усі тестові), `fx_sessions` 76. load 1161/1161, verify — ЗЕЛЕНО.

> Повторюєте перший прохід у нову теку — `--leads-since` на 7.5 береться з `manifest.json`
> САМЕ ТОГО знімка, дані якого лежать у базі найдовше: `python3 -c "import json;print(json.load(open('dump-<дата>/manifest.json'))['taken_at'])"`.

---

## Крок 5. Користувацькі юніти й локальна перевірка — ✅ зроблено 2026-09-11

Системних юнітів нема й не буде: `systemctl --user`, linger у `ihor` увімкнено (менеджер
стартує разом із машиною).

```bash
install -m 0644 deploy/systemd/user/ihor-aluma-api.service \
    deploy/systemd/user/ihor-aluma-purge.service \
    deploy/systemd/user/ihor-aluma-purge.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ihor-aluma-api.service ihor-aluma-purge.timer
```

Журнал — `journalctl --user -u ihor-aluma-api` (і `-u ihor-aluma-purge`).

**Перевірка.**

```bash
systemctl --user is-active ihor-aluma-api                # active
ss -ltnp | grep ':8005 '                                 # ТІЛЬКИ 127.0.0.1:8005
python3 scripts/smoke_local.py                           # 4/4, version=0.4.0-box
ls /run/user/1001/gunicorn.ctl ~/.gunicorn               # обидва: No such file
stat -c '%a %n' data data/*                              # 700; файли 600
```

> **`--no-control-socket` у юніті обовʼязковий:** сокет gunicorn один на користувача,
> без прапорця ALUMA зносить сокет `central-aparts-site`.
>
> **`version` мусить відрізнятися від `0.3.0`** — так відповідає лямбда. Інакше після
> переключення не зрозуміти, хто відповів.
>
> **Смок пише тестову заявку в ЖИВУ базу** (`is_test`, без сповіщення, в адмінці видно
> лише на `/admin?test=1`). Це законно: на 7.5 вони рахуються як «тестові».

Заміряно на встановленому сервісі: два `restart` і `kill -TERM <MainPID>` — піднімається
сам, смок 4/4 після кожного; purge вручну — `Result=success`. Деталі — `deploy/README.md`.

### 5.1. Три перевірки проти коробки — ✅ зроблено 2026-09-12

План переїзду вимагає трьох перевірок проти сайту на цій машині. Заявку в Telegram робить
**власник** (вона єдина доводить, що сповіщення доходить). Дві решти — нижче, обидві
повторювані.

**а) Браузерний прогін `tests/smoke.spec.js` — 30 passed.**

Проти **прода й `table-new` цей спек не ганяти**: він ПИШЕ у сховище (заявка `is_test` через
`route.fetch`, `page_view` без `X-Test` на кожен `goto`, події через `route.continue`). Йому
потрібен повний локальний стек із одноразовою базою — `tools/serve-local-stack.py`: один
процес на `127.0.0.1:8007`, статика з `dist/` рівно як у Caddy (чисті URL, `/en` → `/en/` 308,
404 сторінкою зі статусом 404, ті самі заголовки) плюс `/api/fx/*` і `/admin*` у
`api.wsgi:application` ТОГО Ж процесу; база — SQLite у тимчасовій теці `0700`, знімається
разом із процесом; `TELEGRAM_*` прибрано, тож сповіщень з прогону не йде.

```bash
python3 build.py
ss -ltn | grep ':8007 '                              # МУСИТЬ бути порожньо
python3 tools/serve-local-stack.py &                 # друкує свій pid і теку бази
PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright BASE_URL=http://127.0.0.1:8007 \
    npx playwright test tests/smoke.spec.js          # → 30 passed
kill -TERM <pid>                                     # ТІЛЬКИ за PID, ніколи pkill
ss -ltn | grep ':8007 '                              # знову порожньо; тимчасова база зникла
```

> Спек довелось привести до сайту: 8 його очікувань відстали. Дві були привʼязані до
> бойової адреси (схема `https://`, домен у переліку «сторонніх запитів») — тепер походять
> від `BASE_URL`, і перевірка на HTTPS лишається для публічного імені. Шість відстали від
> перебудови сторінки (коміт `8296742`, пізніший за останню правку спека `894a753`): зник
> біндинг `seatsword`, перемикач тону тепер міняє `#compare-img`, а не герой-портрет,
> калькулятор стіни згорнутий у `<details id="fit">` і його вердикти звуться
> `no`/`closed`/`open` замість `tight`/`ok`/`no`, англійський `h1` переписано.
> **Дефектів сайту прогін не знайшов** — усе червоне було про спек.

**б) Lighthouse проти бойової адреси — 100/100/100/100 на всіх чотирьох прогонах.**

Тільки `GET`, форми не відправляються. `/` та `/en/`, mobile і desktop. Команда, метрики,
топ зауважень і як повторити — `docs/lighthouse/2026-09-12/README.md`, числа —
`docs/lighthouse/2026-09-12/summary.json`. Провалених аудитів із ненульовою вагою немає.

---

## Крок 6. Статика: `dist/` → `/srv/aluma`

> **Після установки агента (T040) — замінено:** статику публікує агент (ті самі прапорці `rsync` + звірка сум) —
> `docs/DELIVERY.md`. Нижче — ручний крок, як зараз.

Caddy віддає статику з `/srv/aluma` (тека `0755`, власник `ihor`, створює Денис), а не
з клону: у `/opt/ihor` Caddy доступу не отримує. Збирається в клоні, публікується
копією — після КОЖНОЇ збірки:

```bash
cd /opt/ihor/aluma-table
umask 027
python3 build.py
rsync -a --delete-after --delay-updates --chmod=D0755,F0644 \
    /opt/ihor/aluma-table/dist/ /srv/aluma/
```

> 🛑 **Без `--chmod` — 403 на частину сторінок.** `rsync -a` переносить права як є, а
> `build.py` дає змішані: скопійоване з `site/` — `664`, створене ним самим (сторінки без
> розширення, `en/*`) — за umask, при `027` це `640`. Заміряно 2026-09-11: 14 файлів
> `640` (`/privacy`, `/terms`, `/en/…`), для Caddy («інші») — 403. З `--chmod` — нуль.

**Перевірка.**

```bash
find /srv/aluma ! -perm -o=r                      # ПОРОЖНЬО
python3 scripts/compare_sites.py https://table.central-aparts.store /srv/aluma --assets --ignore-eol
# код 0: сторінки й ассети однакові
```

`--ignore-eol` — свідомий виняток, доки прод зібраний на Windows (CRLF; викат 09.09,
коміт `8296742`). Він доводить, що однаковий **вміст**, але не що залито той самий
`dist/`. Після перевикату проду свіжим `build.py` прапорець прибрати — умова стає `0` без нього.

---

## Крок 7. Перевірочне імʼя `table-new` — Денис ставить блок

Заявка — `deploy/caddy/REQUEST-DENIS.md`, п.1. Денис бере три файли з прод-клону
`/opt/ihor/aluma-table/deploy/caddy/` і звіряє їх `sha256sum -c` рядками із заявки.
Тому **перед листом Денису** клон має стояти на коміті, де ці файли не старіші за
заявку, і звірку треба прогнати в себе:

```bash
cd /opt/ihor/aluma-table/deploy/caddy && sha256sum -c <<'EOF'
<три рядки з REQUEST-DENIS.md>
EOF
# три OK
```

A-запис `table-new.central-aparts.store` → `95.216.10.169` (TTL 300) уже є.

**Перевірка** (після reload у Дениса):

```bash
curl -sI https://table-new.central-aparts.store/                # 200, text/html; charset=utf-8
curl -sI https://table-new.central-aparts.store/no-such-page    # 404
curl -s  https://table-new.central-aparts.store/api/fx/health   # "version": "0.4.0-box"
python3 scripts/compare_sites.py https://table.central-aparts.store https://table-new.central-aparts.store --assets --ignore-eol
```

### 7.1-перед. Експеримент з `X-Forwarded-For` — робить ВЛАСНИК

`client_ip()` бере **перший** елемент `X-Forwarded-For`; фронт мусить його
перезаписувати. Caddy ≥ 2.7 за замовчуванням клієнтському XFF не довіряє, а блок
додатково має `header_up X-Forwarded-For {remote_host}`. Критерій приймання: сім
`POST /api/fx/lead` з тілом `{}` і однаковим підробленим `X-Forwarded-For` через
`https://table-new.central-aparts.store` дають `422 ×5`, далі `429 429`; восьмий — з
ІНШИМ підробленим значенням — **теж `429`**. `422` на восьмому = дірка у фронті.
`X-Test: 1` не ставити (інший ліміт). Заявок цей експеримент не створює.

**Сесії цей експеримент не відтворюють** ні з яким конфігом — тільки власник через
живий фронт. Причина — розділ «Безпека експериментів» нижче.

---

## Крок 8. ВІКНО — переключення `table`

Порядок усередині — найважливіше місце чек-листа. 8.0–8.7 підряд, не міняючи місцями.

### 8.0. Оголошення і «було»

Оголосити власнику за 10 хвилин (OWNER-RULES п.17), узгодити час із Денисом (його крок
8.2 іде одразу за 8.1). Попросити власника **не міняти статуси заявок в адмінці між 8.1
і 8.6**: фінальний `load` перезапише їх значеннями з DynamoDB (розділ Б). Зняти й зберегти поточні записи — вони і є відкат:

```bash
aws route53 list-resource-record-sets --hosted-zone-id Z05565972H1DV59U5PO4I \
  --query "ResourceRecordSets[?Name=='table.central-aparts.store.']" --output json
```

**«Було» — знято 2026-09-11 (тільки читання):**

| Імʼя | Тип | Значення |
|---|---|---|
| `table.central-aparts.store.` | `A` | alias → `dnj0089lrzf76.cloudfront.net.` (HostedZoneId `Z2FDTNDATAQYW2`, EvaluateTargetHealth false) |
| `table.central-aparts.store.` | `AAAA` | alias → `dnj0089lrzf76.cloudfront.net.` (HostedZoneId `Z2FDTNDATAQYW2`, EvaluateTargetHealth false) |
| `table-new.central-aparts.store.` | `A` | `95.216.10.169`, TTL 300 (не чіпається) |

Якщо в день вікна знято щось інше — відкат будувати з того, що знято, а не з таблиці.

### 8.1. DNS: `A` на коробку, `AAAA` на CloudFront — ВИДАЛИТИ

`AAAA` лишати не можна: Let's Encrypt піде перевіряти `table` по IPv6 на CloudFront, і
Caddy не отримає сертифікат; частина гостей теж піде по IPv6 на старий стек. Одна
атомарна пачка змін (зона `Z05565972H1DV59U5PO4I`), файл `switch.json`:

```json
{"Comment": "ALUMA: table -> ace-main",
 "Changes": [
  {"Action": "DELETE", "ResourceRecordSet": {"Name": "table.central-aparts.store.", "Type": "A",
    "AliasTarget": {"HostedZoneId": "Z2FDTNDATAQYW2", "DNSName": "dnj0089lrzf76.cloudfront.net.", "EvaluateTargetHealth": false}}},
  {"Action": "DELETE", "ResourceRecordSet": {"Name": "table.central-aparts.store.", "Type": "AAAA",
    "AliasTarget": {"HostedZoneId": "Z2FDTNDATAQYW2", "DNSName": "dnj0089lrzf76.cloudfront.net.", "EvaluateTargetHealth": false}}},
  {"Action": "CREATE", "ResourceRecordSet": {"Name": "table.central-aparts.store.", "Type": "A",
    "TTL": 300, "ResourceRecords": [{"Value": "95.216.10.169"}]}}
 ]}
```

`aws route53 change-resource-record-sets --hosted-zone-id Z05565972H1DV59U5PO4I --change-batch file://switch.json`.
DELETE мусить збігатися з записом **до байта** — інакше Route 53 відхилить усю пачку і
нічого не зміниться (це безпечна відмова). **Цей рецепт не виконувався** — перевірити
вміст пачки проти знятого «було» перед запуском.

**Занотувати точний час UTC:** `date -u +%Y-%m-%dT%H:%M:%SZ` — потрібен на кроці 10.

### 8.2. Денис: блок `table`

`REQUEST-DENIS.md`, п.2: рядок `import aluma/aluma-table.caddyfile`, `validate`, `reload`.
Раніше 8.1 блок не ставити — Caddy безкінечно повторюватиме ACME.

### 8.3. Перевірка, що відповідає коробка

```bash
dig +short table.central-aparts.store A       # 95.216.10.169
dig +short table.central-aparts.store AAAA    # порожньо
curl -s https://table.central-aparts.store/api/fx/health   # "version": "0.4.0-box"
```

`0.3.0` = відповіла стара лямбда.

### 8.4. Дочекатись ТИШІ на старому стеку

Доки хоч частина гостей резолвить старий запис, лямбда пише в DynamoDB. Фінальний дамп
раніше — і заявка, що прийде в DynamoDB після нього, у SQLite не потрапить ніколи.

```bash
aws cloudwatch get-metric-statistics --namespace AWS/Lambda \
  --metric-name Invocations --dimensions Name=FunctionName,Value=fx-table-api \
  --start-time "$(date -u -d '15 minutes ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 900 --statistics Sum --region eu-central-1 --query 'Datapoints[0].Sum'
# 0 або null — жодного виклику за 15 хвилин
```

### 8.5. Фінальний дамп

```bash
cd /opt/ihor/aluma-table
install -d -m 0700 dump-final
.venv/bin/python scripts/migrate_fx.py --phase dump --dump-dir dump-final
python3 -c "import json;m=json.load(open('dump-final/manifest.json'));print(m['taken_at'], m['total'])"
# taken_at ПІЗНІШИЙ за час із 8.1, total ненульовий
```

### 8.6. Завантажити фінальний дамп у ЖИВУ базу

```bash
.venv/bin/python scripts/migrate_fx.py --phase load --dump-dir dump-final
# «load: усього записано <N> рядків», код 0
```

> **`load` — ПІСЛЯ фінального дампа.** Між проходами власник міняє статуси в адмінці;
> `INSERT OR REPLACE` перезапише рядок свіжішою версією лише за такого порядку.
>
> **У ЖИВУ базу, не в чисту:** у `data/aluma.db` уже лежать заявки, що прийшли після 8.1.

### 8.7. `verify` другого проходу

```bash
.venv/bin/python scripts/migrate_fx.py --phase verify --second-pass \
  --dump-dir dump-final --db data/aluma.db \
  --leads-since <taken_at ПЕРШОГО знімка, крок 4>
```

**Перевірка.** Останні рядки — такого виду, код `0`:

```
Підсумок другого проходу — розбіжності допустимі ЛИШЕ тут:
  fx_events (TTL): зі знімка не доїхало 0, у базі понад знімок 7
  fx_leads: зі знімка не доїхало 0; зайві в базі — тестові 5, прийшли після --leads-since 2, непояснених 0
       вміст кожної заявки знімка звірено в пункті 2-біс; «не доїхало» і «непояснених» мусять бути 0
  fx_sessions (TTL): зі знімка не доїхало 0, у базі понад знімок 3
       значення має лише «не доїхало» — воно мусить бути 0; «понад знімок» тут очікуване
verify: ЗЕЛЕНО — усі перевірки пройшли
```

Дивитись на **«не доїхало»** (усі три таблиці) і **«непояснених»** (`fx_leads`) — вони
мусять бути `0`. «Понад знімок», «тестові», «прийшли після» — довідка, ненульові значення
тут нормальні. Вміст рядків знімка звіряється з базою суцільно (пункт 2-біс).

Прогін на коробці 2026-09-11 (знімок `dump-2026-09-11`, без `--leads-since`):
`fx_leads: не доїхало 0; тестові 5, прийшли після знімка 0, непояснених 0`, ЗЕЛЕНО.

---

## Крок 9. Післяперевірка, коли вікно закрите

```bash
curl -s  https://table.central-aparts.store/api/fx/health     # 0.4.0-box
curl -sI https://table.central-aparts.store/admin | head -1   # 200 або 303, не 403
```

- Адмінка пускає **без повторного логіну** — `IP_SALT`/`ADMIN_PASS` перенесені вірно.
- Кількість справжніх заявок в адмінці = було на AWS + прийшли після 8.1.
- Одна справжня заявка з телефона: зʼявилась в адмінці **і** прилетіла в телеграм.
- `403` на всьому = хтось задав `EDGE_SECRET` (2.1).

---

## Крок 10. Відкат — і до якої миті він ще щось означає

**Відкат — повернути DNS «як було» (8.0) і прибрати блок `table` у Дениса.** AWS до
кінця перевірки не вимикається. Пачка `rollback.json`:

```json
{"Comment": "ALUMA: table -> CloudFront (відкат)",
 "Changes": [
  {"Action": "DELETE", "ResourceRecordSet": {"Name": "table.central-aparts.store.", "Type": "A",
    "TTL": 300, "ResourceRecords": [{"Value": "95.216.10.169"}]}},
  {"Action": "CREATE", "ResourceRecordSet": {"Name": "table.central-aparts.store.", "Type": "A",
    "AliasTarget": {"HostedZoneId": "Z2FDTNDATAQYW2", "DNSName": "dnj0089lrzf76.cloudfront.net.", "EvaluateTargetHealth": false}}},
  {"Action": "CREATE", "ResourceRecordSet": {"Name": "table.central-aparts.store.", "Type": "AAAA",
    "AliasTarget": {"HostedZoneId": "Z2FDTNDATAQYW2", "DNSName": "dnj0089lrzf76.cloudfront.net.", "EvaluateTargetHealth": false}}}
 ]}
```

Потім Денис: прибрати `import aluma/aluma-table.caddyfile`, `reload` (`REQUEST-DENIS.md`, п.3).
Сервіс на коробці можна лишити — він нікому не заважає; повністю —
`systemctl --user disable --now ihor-aluma-api.service ihor-aluma-purge.timer`.

> **Цей відкат більше неможливий:** стек `fx-table` з CloudFront видалено 2026-09-11 15:08–15:28Z, решта
> старого AWS ALUMA — 2026-09-12 (`docs/AWS-TEARDOWN.md`). Пачки Route 53 вище — історія; сайт віддає лише
> коробка, і відновлення — це відновлення коробки (`docs/DELIVERY.md`, розділ 8).

### `ALUMA_HEALTH_URL`: якщо `table` знову веде не на коробку

Наглядач деплою (`deploy.yml`) чекає номер і sha версії на адресі зі змінної окруження `production`
`ALUMA_HEALTH_URL` (`https://table.central-aparts.store/api/fx/health`). Якщо `table` переведуть з коробки, кожен
деплой провалиться за таймаутом — машині це не шкодить, але статус у GitHub буде хибним. Тоді:

```bash
gh variable set ALUMA_HEALTH_URL --env production --body 'https://table-new.central-aparts.store/api/fx/health'
# table знову на коробці — назад:
gh variable set ALUMA_HEALTH_URL --env production --body 'https://table.central-aparts.store/api/fx/health'
```

Змінна й окруження з'являються в Phase 3 (SDD 001) — не перевірено, після Phase 3.

### Момент незворотності

**Відкат повертає дані доти, доки в SQLite не лягла ЖОДНА справжня заявка після 8.1.**
Після неї сайт повернеться, а дані — ні: зворотної синхронізації SQLite → DynamoDB нема,
і писати в DynamoDB нам заборонено. Те саме — статуси, наклацані в адмінці після 8.1.

```bash
/opt/ihor/aluma-table/.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "/opt/ihor/aluma-table")
from api import store
SWITCH = "2026-09-__T__:__:00"      # <-- час із 8.1, UTC
db = store.SqliteStore("/opt/ihor/aluma-table/data/aluma.db")
rows = db.rows("SELECT doc FROM 'fx_leads' WHERE rk > ?", (SWITCH,))
db.close()
import json
real = sum(1 for r in rows if not json.loads(r["doc"]).get("is_test"))
print(f"справжніх заявок після переключення: {real}")
print("відкат ЩЕ безвтратний" if real == 0 else f"відкат ВТРАТИТЬ {real} заявок — переносити руками")
PY
```

(`rk` у `fx_leads` — `<ts>#<id>`, тож порівняння рядків працює як порівняння часу;
друкуються лише лічильники.)

Проміжок «безвтратного відкату» некерований — від хвилини до години. Рішення «їдемо чи
ні» приймати на кроках 6–7, доки DNS не перемкнутий: там відкат безкоштовний. Після 8.1
єдиний чесний план — доводити переїзд до кінця.

---

## Журнал переключення 11.09

Сесія «🪵 ALUMA · переключение table на машину», «виконуй» дирижера ALUMA — 15:40:43 EEST,
після reload сайту (15:29:15, «чужі сайти в порядку») і 10 хвилин оголошення. Кроки 8.0–8.7
підряд, без перестановок. Блок `table` у Caddy поставлено нами (`OWNER-RULES.md` п. 20), не Денисом.

**SWITCH = `2026-09-11T12:42:31Z` (15:42:31 EEST, Київ).** Route 53 change
`C06664871ZHOUM3735GUZ`, `SubmittedAt 12:42:31.035Z`, `INSYNC` о 12:43:05Z.

**8.0.** «Було» знято двічі (15:01 і 15:42:21) — однаково й до символа як у таблиці 8.0
(A і AAAA alias → `dnj0089lrzf76.cloudfront.net.`). `DELETE` пачки `switch.json` і `CREATE`
пачки `rollback.json` звірено з ним програмно (JSON з `sort_keys`), усі імена — лише `table.`.

**8.1.** Пачка — рівно та, що в 8.1. Висновок «Цей рецепт не виконувався» більше не діє:
`switch.json` виконано, Route 53 прийняв з першого разу.

**8.2. Caddy** (після `INSYNC`, щоб Let's Encrypt не пішов на CloudFront):

| Час EEST | Крок | Підсумок |
|---|---|---|
| 15:42:43 | `sudo cp -p` → `/etc/caddy/Caddyfile.bak-aluma-table-20260911-154243` | sha копії = «до» |
| 15:42:43 | `printf … \| sudo tee -a` — рядок `import aluma/aluma-table.caddyfile` | `diff`: `118a119`, один рядок |
| 15:42:43 | `sudo caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile` | `Valid configuration` |
| **15:43:09** | `sudo systemctl reload caddy` | rc 0, caddy `active` |

sha256 `/etc/caddy/Caddyfile`:

- до: `35ad6e2937f8a1b493e924e4e0e816cd13d07936922b04a63c180b89656136c6` (уже з рядком сайту,
  дописаним о 14:56 і завантаженим його reload о 15:29:15 — не наша правка, не чіпали);
- після: `7f605bd23a61f044d7bd35d1226b2b9bb7270fc42de290b75de969e3e97cc64e`.

Рядок `import aluma/aluma-table-new.caddyfile` не чіпали — `table-new` лишається.

> ⚠️ **Урок.** Рядок сайту стояв у файлі з 14:56, а завантажив його сайт лише о 15:29. Будь-який
> наш reload між цими моментами завантажив би й чужий блок. Перед reload дивитись не лише на
> файл, а й чи збігається він із тим, що вже завантажено (`journalctl -u caddy` — коли був
> останній reload; `stat` Caddyfile), і чекати доповіді власника рядка.

**Чужі сайти** (`curl -sI -m 10 https://<імʼя>/`, перший рядок; імена — з Caddyfile та імпортів):

| Сайт | До (15:42:21) | Після (15:43:10) | Після (15:44:05) |
|---|---|---|---|
| `95-216-10-169.sslip.io` | HTTP/2 200 | HTTP/2 200 | HTTP/2 200 |
| `iiko.95-216-10-169.sslip.io` | HTTP/2 404 | HTTP/2 404 | HTTP/2 404 |
| `atmo.95-216-10-169.sslip.io` | HTTP/2 404 | HTTP/2 404 | HTTP/2 404 |
| `tennis.95-216-10-169.sslip.io` | HTTP/2 200 | HTTP/2 200 | HTTP/2 200 |
| `site-new.central-aparts.store` | HTTP/2 200 | HTTP/2 200 | HTTP/2 200 |
| `table-new.central-aparts.store` (наш) | HTTP/2 200 | HTTP/2 200 | HTTP/2 200 |
| caddy | active | active | active |

Відмінностей нема, відкат не знадобився.

Журнал caddy після reload: для `table` — `certificate obtained successfully` (HTTP-01, Let's
Encrypt `YE1`, до 10.12.2026). Помилок нема; попередження ті самі, що й при попередніх
завантаженнях (`Unnecessary header_up X-Forwarded-For` ×3, `not formatted` рядок 4, `admin
endpoint on open interface`, HTTP/2 і HTTP/3 на :80).

**8.3** (15:43:52):

| Перевірка | Відповідь |
|---|---|
| `dig table A` @1.1.1.1 / @8.8.8.8 | `95.216.10.169` / `95.216.10.169` |
| `dig table AAAA` @1.1.1.1 / @8.8.8.8 | порожньо / порожньо |
| `/api/fx/health` | `{"ok": true, "version": "0.4.0-box", ...}` |
| `/`, `/privacy`, `/en/` | 200 `text/html; charset=utf-8` |
| `/no-such-page` | 404 `text/html; charset=utf-8` |
| `GET /admin` без куки | 303 → `/admin/login` (200) |

Тестових заявок не надсилали.

**Статика:** `compare_sites.py https://table.central-aparts.store /srv/aluma --assets` — **без**
`--ignore-eol`, код 0: сторінок 10/10, ассетів 91/91.

**8.4. Тиша на лямбді.** `Invocations` `fx-table-api` (похвилинно): останній виклик — хвилина
12:40Z, тобто ДО SWITCH; після нього — жодного. Вікно 15 хвилин без викликів:
**12:43:03Z–12:58:03Z** (15:43–15:58 EEST), `Sum = null`; повторно о 12:58:46Z — теж `null`.
Опитування кожні 3 хв з 12:45:53Z.

**8.5. Фінальний дамп** (12:58:17Z) у `dump-2026-09-11-final/` (700, файли 600):
`taken_at` = `2026-09-11T12:58:18.204937+00:00` (пізніший за SWITCH), `total` 1176 —
`fx_events` 1076, `fx_leads` 21, `fx_sessions` 79. Код 0.

**8.6. load у ЖИВУ базу** (12:58:30Z; перед ним ще одна копія — `data/aluma.db.pre-load-20260911-155830`):
записано 1076/1076, 21/21, 79/79 — `load: усього записано 1176 рядків`, код 0. Сервіс
`ihor-aluma-api` не перезапускали.

**8.7. verify** `--second-pass --dump-dir dump-2026-09-11-final --db data/aluma.db
--leads-since 2026-09-11T11:02:12.816423+00:00` (taken_at ПЕРШОГО знімка) — **ЗЕЛЕНО**, код 0:

```
fx_events (TTL): зі знімка не доїхало 0, у базі понад знімок 31
fx_leads: зі знімка не доїхало 0; зайві в базі — тестові 6, прийшли після --leads-since 1, непояснених 0
fx_sessions (TTL): зі знімка не доїхало 0, у базі понад знімок 12
verify: ЗЕЛЕНО — усі перевірки пройшли
```

База після load: `fx_events` 1107 (= 1076 + 31), `fx_leads` 28 (= 21 + 6 + 1), `fx_sessions` 91
(= 79 + 12). Зайві події й сесії — те, що коробка записала сама (смоки, `table-new`, гості
після SWITCH), а не TTL: DynamoDB їх ніколи не бачив.

**Крок 9** (12:58:45Z, те, що можна без власника):

- `https://table.central-aparts.store/api/fx/health` — `0.4.0-box`;
- `GET /admin` без куки — 303 → `/admin/login` (не 403: `EDGE_SECRET` на коробці нема);
- справжніх (не `is_test`) заявок на коробці — **1** = у фінальному знімку **0** + прийшли через
  `table-new` після першого знімка і до SWITCH **1** + прийшли після SWITCH **0**. Тестових — 27.

**Чекає власника:** вхід в адмінку без повторного логіну; одна справжня заявка з телефона —
видно в адмінці **і** прилетіла в телеграм; експеримент XFF (7.1-перед).

**Копії:**

| Що | Де |
|---|---|
| база коробки до переключення (sqlite backup API, 15:02:06; `fx_events` 1096, `fx_leads` 27, `fx_sessions` 88) | `/opt/ihor/aluma-table/data/aluma.db.pre-switch-20260911-150206` (600) |
| записи `table` «було» | `/opt/ihor/aluma-table/dns-before-2026-09-11.json` (600) |
| `switch.json`, `rollback.json`, `dns-before.json`, відповідь Route 53 | `/opt/ihor/aluma-table/dns-2026-09-11/` (700, файли 600) |
| Caddyfile до нашого рядка | `/etc/caddy/Caddyfile.bak-aluma-table-20260911-154243` |
| фінальний знімок DynamoDB | `/opt/ihor/aluma-table/dump-2026-09-11-final/` (700) |

**Як відкотити зараз** (AWS не вимикався і нічого в ньому не видалено):

```bash
cd /opt/ihor/aluma-table/dns-2026-09-11
aws route53 list-resource-record-sets --hosted-zone-id Z05565972H1DV59U5PO4I \
  --query "ResourceRecordSets[?Name=='table.central-aparts.store.']" --output json   # A 95.216.10.169 TTL 300 — і нічого більше
aws route53 change-resource-record-sets --hosted-zone-id Z05565972H1DV59U5PO4I --change-batch file://rollback.json
# потім Caddy: копія, прибрати ТІЛЬКИ свій рядок, validate, reload, таблиця чужих сайтів
sudo cp -p /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-aluma-rollback-<дата-час>
sudo sed -i '\#^import aluma/aluma-table\.caddyfile$#d' /etc/caddy/Caddyfile
sudo caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Якщо після нас у Caddyfile ніхто нічого не міняв (sha = `7f605bd2…c64e`), замість `sed` можна
повернути копію `.bak-aluma-table-20260911-154243`.

**Момент незворотності** — перша справжня (не `is_test`) заявка в SQLite з `rk` пізнішим за
`2026-09-11T12:42:31` (скрипт у розділі «Момент незворотності», `SWITCH` уже підставлено вище).
На 12:58:45Z таких заявок **0** — відкат ще безвтратний. Щойно власник надішле перевірочну
заявку з телефона (крок 9), вона стане першою: після цього відкат DNS поверне сайт, але не
дані — таку заявку й статуси, змінені в адмінці коробки, переносити руками. Перевірити будь-коли
тим самим скриптом.

---

# Безпека експериментів: у спільних керувальних каналів немає «свого» екземпляра

Сервіс може мати канал керування, спільний на всю машину і без автентифікації — у Caddy
це admin-ендпоінт. Команда «зупини мій тестовий інстанс» іде в цей канал і влучає в ТОЙ,
ЩО ПРАЦЮЄ. root для цього не потрібен. 10.09 о 22:42:37 так був зупинений бойовий Caddy:
чотири чужі проєкти, зокрема кабінет УЗД, лежали понад 15 хвилин.

- Сесії Caddy не запускають, не зупиняють і не перезавантажують **взагалі**, з будь-яким
  конфігом; до порту 2019 не звертаються нічим. Дозволено лише `caddy validate`,
  `caddy adapt`, `caddy fmt` на копії з `admin off`.
- Процеси гасити **тільки за PID** (`systemctl --user show -p MainPID` або `ss -ltnp`).
  Ніколи `pkill`, `killall`, `pkill -f` — поруч чужі сервіси з тими самими іменами.
- Довгий текст в оболонку — файлом або в одинарних лапках; heredoc — лише `<<'EOF'`.
  Подвійні лапки виконують зворотні лапки й `$(`: 10.09 так пішов реальний запит у порт
  2019 з речення ПРО заборону.

---

# Розділ А. Чому другий прохід не може бути строгим

**TTL.** `fx_events` (180 днів) і `fx_sessions` (400 днів) DynamoDB прибирає сама. Рядки,
залиті першим проходом, зникають із фінального знімка — у базі їх більше. Репетиція
(копія знімка мінус 7 подій): без прапорця — ЧЕРВОНО, три FAIL (кількість, sha256 ключів,
лічильник колонки `ttl`); з `--second-pass` — ЗЕЛЕНО, `не доїхало 0, понад знімок 7`.

**Заявки коробки.** До 2026-09-11 `fx_leads` звірявся строго на обох проходах. Тоді
кожна заявка, записана коробкою (смок, `table-new`, гість після 8.1), давала на 7.5
ЧЕРВОНО — на тій самій базі, де нічого не втрачено. Знайдено на живій коробці: 5 смоків
→ 25 заявок у базі проти 20 у знімку. Тепер правило — вгорі файлу.

**Чому пропажа заявки завжди справжня.** В `api/handler.py` і `api/store.py` немає
жодного шляху видалення заявки — ні `delete_item`, ні `DELETE`, ні ручки в адмінці;
єдиний `DELETE` (`purge_expired()`) рубає лише рядки з `ttl`, якого в заявок немає.
Тому «не доїхало» по `fx_leads` — завжди втрата. ⚠️ Щойно видалення заявки зʼявиться,
правило переглядати разом із тією правкою (докстрінг `relaxed_for_ttl()`).

Режим перевірено в обидва боки тестами `tests/test_migrate_fx.py` (розділ
`verify --second-pass`): пропажа, змінений вміст, зайва нетестова старша за поріг —
ЧЕРВОНО; зайва `is_test`, зайва новіша за поріг — ЗЕЛЕНО; без прапорця — строго, як
було. Червоність доведена мутацією: `classify_extra_leads`, підмінена на «усе
пояснено», робить червоні тести зеленими (тобто тести падають), на «нічого не пояснено» —
навпаки.

# Розділ Б. Межі того, що доводить зелений `verify`

- **Перший прохід:** контрольна сума — лише по ключах `(hk, rk)`; вміст звіряється
  вибірково (типи `ttl`/`is_test` суцільно, три заявки — через `handler.load_leads()`).
  Змінений вміст при тому самому ключі перший прохід НЕ ловить.
- **Другий прохід:** пункт 2-біс звіряє `doc` кожного рядка знімка з базою суцільно —
  змінений вміст ловить, зокрема застарілий статус, якщо `load` забули після 8.5.
  Але він доводить лише «база = фінальний знімок». **Статус, змінений в адмінці
  КОРОБКИ між 8.1 і 8.6, `load` перезапише старим значенням із DynamoDB, і verify
  буде ЗЕЛЕНИМ** — у знімку й у базі однаково старе. Тому між 8.1 і 8.6 статуси в
  адмінці не міняти (попередити власника в 8.0).
- Зайві заявки коробки verify не звіряє з нічим — лише рахує й класифікує (`is_test`,
  `ts`). Що вони справжні й дійшли в телеграм — крок 9.

---

# Що перевірено, а що ні

**Виконано на коробці:** кроки 1, 2, 4, 5 — 2026-09-11 (числа — у кроках); крок 6 (статика в
`/srv/aluma`), крок 7 (блок `table` у Caddy — поставили ми, `OWNER-RULES.md` п.20) і кроки 8.0–8.7
(перенос даних і переключення DNS) — 2026-09-11, докази в «Журналі переключення 11.09»; пачку Route 53
`switch.json` Route 53 прийняв з першого разу, `INSYNC` 12:43:05Z. Другий прохід verify з новим правилом
проти `dump-2026-09-11` — ЗЕЛЕНО; репетиції TTL і двопрохідного переносу — на копіях у `/tmp` (10.09),
бойові артефакти не чіпались.

**НЕ перевірено і вже не буде:** пачка `rollback.json` (повернення DNS на CloudFront) не виконувалась
ніде — з 2026-09-12 виконати її нема куди, дистрибуцію видалено (`docs/AWS-TEARDOWN.md`); експеримент
XFF на живому фронті CloudFront (власник) — фронту більше немає.

**НЕ перевірено:** `--leads-since` на справжньому вікні; окремий запис `compare_sites` проти
`/srv/aluma` у цьому файлі (сайт віддається з коробки — журнал 8.3); `ALUMA_HEALTH_URL` і окруження
`production` — не перевірено, після Phase 3.

---

# Історія: що з попередніх версій цього файлу більше не діє

- `/etc/aluma/aluma.env` і системні юніти `/etc/systemd/system/ihor-aluma-*` — замінені на
  `~/.config/aluma/aluma.env` і `systemctl --user` (root і `sudo` не потрібні й заборонені).
  Системні файли лишились у `deploy/systemd/` як варіант «якщо колись буде root».
- nginx у ланцюжку (Caddy → nginx → gunicorn, порт 8007, `realip`) — не ставиться; заявка
  лишилась у `deploy/nginx/aluma.conf`, розбір — `deploy/README.md`.
- Статика з `/opt/ihor/aluma-table/dist` через ACL для `caddy` — замінена на `/srv/aluma`.
- Тимчасові імена `*.sslip.io` — не використовуються; перевірочне імʼя — `table-new`.
- Строга звірка `fx_leads` на другому проході — замінена правилом вгорі файлу.

Попередній текст — у `git log -p docs/CUTOVER-CHECKLIST.md`.
