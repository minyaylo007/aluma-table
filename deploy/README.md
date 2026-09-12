# deploy/ — ALUMA на звичайному сервері: gunicorn + systemd + nginx

Файли для переїзду ALUMA з **AWS Lambda + API Gateway + CloudFront + DynamoDB**
на звичайний сервер. Продовження вже зробленого: `api/wsgi.py` (лямбда під
gunicorn) і `api/store.py` (SQLite-двійник трьох таблиць DynamoDB).

> **СТАН НА 2026-09-12: ГОСТІ НА КОРОБЦІ, СТАРОГО AWS НЕМАЄ.** `table` дивиться сюди з
> 2026-09-11 12:42:31Z (`a7e9c64`, журнал — `docs/CUTOVER-CHECKLIST.md`); старий AWS ALUMA видалено
> повністю 11–12.09 (`docs/AWS-TEARDOWN.md`) — коробка тепер єдине місце, звідки подається сайт.
> **Як зараз:** користувацькі юніти (`systemd/user/`) з клону `/opt/ihor/aluma-table` на `563edc8`,
> поставлені руками (розділ «Користувацькі юніти»); статика в `/srv/aluma`; блоки Caddy — наші (п.20).
> **Після установки агента (T040):** версії з GitHub ставить агент `agent/pullagent.py` — розкладка
> `releases/`/`current`, юніти з `current/`, статика тим самим `rsync`; ручні кроки нижче для цього
> **замінено** — `docs/DELIVERY.md`. Системні юніти (`systemd/*.service`) і nginx — не встановлені.

## Що тут лежить

| Файл | Куди кладеться | Що робить |
|---|---|---|
| `systemd/aluma-api.service` | `/etc/systemd/system/ihor-aluma-api.service` | тримає gunicorn на `127.0.0.1:8005`, `Restart=always` |
| `systemd/aluma-purge.service` | `/etc/systemd/system/ihor-aluma-purge.service` | одноразовий запуск `scripts/purge.py` |
| `systemd/aluma-purge.timer` | `/etc/systemd/system/ihor-aluma-purge.timer` | кличе його щодня о 04:15 |
| `systemd/user/ihor-aluma-{api,purge}*` | `~/.config/systemd/user/` — **встановлено руками з клону `563edc8`** | ті самі юніти для `systemctl --user`; версія в репозиторії (з `current/`) діє після T040 |
| `systemd/user/ihor-aluma-deploy.{service,timer}` | `~/.config/systemd/user/` — **ще не встановлено** (T040) | агент деплою раз на хвилину, `docs/DELIVERY.md` |
| `agent/pullagent.py`, `agent/aluma.json` | каталог версії (`current/deploy/agent/`) після T040 | pull-агент GitHub → машина, без облікових даних |
| `../scripts/box_env.py` | у репозиторії | написав `~/.config/aluma/aluma.env` з живої тоді Lambda, не друкуючи значень; Lambda видалено — історія |
| `nginx/aluma.conf` | `/etc/nginx/sites-available/` + симлінк у `sites-enabled/` | статика з `dist/` (сторінки без розширення як `text/html`, 404-сторінка, кеш як у `deploy.sh`), `/api/fx/` і `/admin` — у gunicorn; `real_ip` + `listen 127.0.0.1:8007` |
| `caddy/aluma.Caddyfile` | блок сайту в `/etc/caddy/Caddyfile` — **кладе тільки власник** | варіант (в) Caddy → gunicorn і закоментований (б) Caddy → nginx; перевірений `caddy adapt`/`validate` |
| `aluma.env.example` | зразок для `/etc/aluma/aluma.env` | перелік змінних, **без жодного реального значення** |
| `../scripts/purge.py` | у репозиторії | чистка протухлих рядків + `VACUUM` |

## Імена юнітів: префікс `ihor-`

Правило машини: всі фонові сервіси Ігоря звуться `ihor-*`. У репозиторії файли
названі без префікса (щоб лежати поруч під одним коренем) — **у систему вони
ставляться під префіксом**: `ihor-aluma-api.service`,
`ihor-aluma-purge.service`, `ihor-aluma-purge.timer`. `Unit=` у таймері вже
вказує на `ihor-aluma-purge.service`.

## `--no-control-socket` в `ExecStart` — не прибирати

Починаючи з 25.1.0, gunicorn при старті відкриває керуючий сокет для
`gunicornc`. Це `$XDG_RUNTIME_DIR/gunicorn.ctl`, а без цієї змінної, як у
системному юніті, `~/.gunicorn/gunicorn.ctl`. **Шлях один на користувача, а не
на процес.** Під `ihor` житимуть щонайменше два gunicorn: ALUMA (`8005`) і
`central-aparts-site` (`8004`). gunicorn 26.2.0 при старті зносить чужий сокет
і ставить свій, а при зупинці видаляє той, що лежить. Помилка створення для
нього — лише warning. Без прапорця один сервіс мовчки ламає керування іншим.
Сокет нам не потрібен: керуємо через systemd і сигнали по PID. Тому прапорець
стоїть у юніті й у кожній команді ручного запуску в документації
(`tests/README-python-tests.md`, `api/wsgi.py`). Рішення одне на всі наші
проєкти. Прапорець є з gunicorn 25.1.0
([changelog](https://github.com/benoitc/gunicorn/blob/master/docs/content/news.md),
розділ 25.1.0), пин `gunicorn==26.2.0` у `requirements-server.txt`. Оновлюєш
gunicorn вище 26.x — спершу `gunicorn --help | grep -- --no-control-socket`.
**Без прапорця gunicorn під `ihor` не запускати навіть на хвилину для тесту**:
саме такий запуск і зносить сокет сусіда.

## Порт 8005

8000–8003 слухають чужі **бойові** проєкти (8000 УЗД, 8001 iiko, 8002 atmosphere,
8003 теніс), 8004 закріплений за `central-aparts-site`. ALUMA — **8005**.
Порт названий у двох місцях: `systemd/aluma-api.service` (`-b`) і
`nginx/aluma.conf` (`proxy_pass`). Міняти тільки разом.

Якщо nginx стане **всередину** ланцюжка (топологія (б) нижче), йому теж
потрібен свій порт на петлі — виділено **8007** (реєстр `~/maestro/PORTS.md`).
Порт зв'язується РІВНО В ОДНОМУ місці — `nginx/aluma.conf`, рядок `listen`;
друга половина пари — `reverse_proxy` у варіанті (б) файлу
`caddy/aluma.Caddyfile` (заявка; у `/etc/caddy/Caddyfile` її кладе власник).
Міняти разом.

> **8006** у нас побув хвилин двадцять і поїхав: його встиг закріпити за собою
> `central-aparts-site` — у них та сама топологія Caddy → nginx → gunicorn.
> Обидва проєкти вибрали «перший вільний» за `ss -ltn` і обидва промахнулися:
> `ss` показує тільки те, що слухає ЗАРАЗ, а обидва конфіги лежали «у стіл» і
> не слухали нічого. **Вільний порт брати з `~/maestro/PORTS.md`**, а не з
> `ss`. Сам реєстр веде головний диригент — ми туди не пишемо.

> Дрібниця з натури: під час перевірки 8005 на хвилину зайняв ручний
> smoke-тест сусіднього проєкту (`central-aparts-site`) — їхній gunicorn, не
> сервіс. Постійно порт ні за ким не закріплений, але коли обидва проєкти
> поїдуть на сервер, 8004/8005 варто зафіксувати за ними в одному місці.

## Підняти: порядок дій

```bash
# 1. Код у свою теку (наша територія, не /opt/bots і не /opt/<чужий проєкт>)
git clone <repo> /opt/ihor/aluma-table
cd /opt/ihor/aluma-table

# 2. venv і залежності
python3 -m venv .venv
.venv/bin/pip install -r deploy/requirements-server.txt   # gunicorn 26.2.0 + boto3 + requests, див. нижче
mkdir -p data                                  # сюди ляже aluma.db (+ -wal, -shm)

# 3. Оточення (робить власник, від root)
sudo install -d -m 0750 -o root -g ihor /etc/aluma
sudo install -m 0640 -o root -g ihor deploy/aluma.env.example /etc/aluma/aluma.env
sudo nano /etc/aluma/aluma.env                 # вписати значення

# 4. Дані з DynamoDB (окремий крок, уже написаний)
#    scripts/migrate_fx.py — dump → load → verify

# 5. Юніти
sudo cp deploy/systemd/aluma-api.service   /etc/systemd/system/ihor-aluma-api.service
sudo cp deploy/systemd/aluma-purge.service /etc/systemd/system/ihor-aluma-purge.service
sudo cp deploy/systemd/aluma-purge.timer   /etc/systemd/system/ihor-aluma-purge.timer
sudo systemctl daemon-reload
sudo systemctl enable --now ihor-aluma-api
sudo systemctl enable --now ihor-aluma-purge.timer

# 6. Статика
python3 build.py                               # збирає dist/ (build.py:31)

# 7. nginx (лише якщо обрана топологія (а) або (б) — див. розділ про
#    X-Forwarded-For. У варіанті (в), «тільки Caddy», цього кроку нема.)
#    Конфіг у репозиторії налаштований під (б): listen 127.0.0.1:8007,
#    а фронтом лишається Caddy. Для (а) — замінити listen на 80, як
#    підписано в самому файлі.
sudo cp deploy/nginx/aluma.conf /etc/nginx/sites-available/aluma.conf
sudo ln -s /etc/nginx/sites-available/aluma.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## Користувацькі юніти (встановлено 2026-09-11)

> **Як зараз** — усе в цьому розділі (клон, `.venv`, юніти, поставлені руками). **Після установки агента
> (T040)** це **замінено**: код — `releases/vX.Y.Z` + `current`, venv — `venvs/<hash>`, юніти копіює агент,
> клон руками не оновлюють і статику руками не публікують — `docs/DELIVERY.md`. Розділ лишається історією й точкою
> ручного повернення з першої версії агента.

Системних юнітів ставити нікому: root тільки у власника, а `sudo` сесіям
заборонено. Тому ALUMA на коробці живе під менеджером користувача `ihor`
(`systemctl --user`). Linger у `ihor` увімкнено: менеджер стартує разом із
машиною, без входу в систему, тож після перезавантаження сервіс піднімається сам.

**Що де лежить:**

| Що | Де | Права |
|---|---|---|
| код | `/opt/ihor/aluma-table` — окремий клон (не worktree), detached HEAD на зафіксованому sha | `770` (`chmod o-rwx`: «іншим» — нуль) |
| venv | `/opt/ihor/aluma-table/.venv`, з `deploy/requirements-server.txt` | — |
| база | `/opt/ihor/aluma-table/data/aluma.db` | тека `0700` |
| знімок AWS | `/opt/ihor/aluma-table/dump-<дата>` (у `.git/info/exclude` клону) | тека `0700` |
| збірка статики | `/opt/ihor/aluma-table/dist` (`python3 build.py` у клоні) | — |
| статика для Caddy | `/srv/aluma` — копія `dist/` через `rsync`, див. «Публікація статики» (існує з 11.09) | `0755`, `ihor` |
| відкат проду | `/opt/ihor/aluma-table/rollback/` — zip лямбди 0.3.0, **не чіпати** | — |
| оточення | `~/.config/aluma/aluma.env` | файл `0600`, тека `0700` |
| юніти | `~/.config/systemd/user/ihor-aluma-{api.service,purge.service,purge.timer}` | — |

Оточення не в `/etc/aluma` (нема прав) і не всередині `/opt/ihor/aluma-table`
(секретам не місце в дереві коду, яке клонують і перезбирають). Написав його `scripts/box_env.py` — значення ніде не
друкуються: `ADMIN_*`, `IP_SALT`, `SITE_DOMAIN`, `WHATSAPP_NUMBER` бралися з Lambda
`fx-table-api` (`IP_SALT` і `ADMIN_PASS` незмінними), Telegram — з `aparts-api`,
`EDGE_SECRET` не переноситься, `APP_VERSION=0.4.0-box`. **Повторити це вже нема звідки**: Lambda видалено
11.09 (`docs/AWS-TEARDOWN.md`), джерело правди тепер — сам файл `~/.config/aluma/aluma.env` на коробці;
скрипт лишається історією того, звідки взялися значення. Номер версії після установки агента (T040) приходить
не звідси, а з `current/RELEASE.env` (`docs/DELIVERY.md`, розділ 6).

**Установка** (так і встановлено). Правило машини «Общие ресурсы»
(`~/maestro/leads/_rules.md`): верхній рівень теки проєкту закритий для
«інших», у юнітах `UMask` не ширший за `0027` (тут `0077`), у скриптах і в
ручних командах — `umask 027`. `migrate_fx.py`, `purge.py`, `box_env.py`
ставлять його самі; для решти команд — перший рядок нижче.

```bash
umask 027
chmod o-rwx /opt/ihor/aluma-table
python3 scripts/box_env.py --app-version 0.4.0-box --out ~/.config/aluma/aluma.env
install -m 0644 deploy/systemd/user/ihor-aluma-api.service \
    deploy/systemd/user/ihor-aluma-purge.service \
    deploy/systemd/user/ihor-aluma-purge.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ihor-aluma-api.service ihor-aluma-purge.timer
```

**Перезапуск, журнал, перевірка:**

```bash
systemctl --user restart ihor-aluma-api
systemctl --user status ihor-aluma-api
journalctl --user -u ihor-aluma-api -n 50          # і -u ihor-aluma-purge
python3 scripts/smoke_local.py                      # 4/4, version=0.4.0-box
python3 scripts/box_env.py --check ~/.config/aluma/aluma.env \
    --pid "$(systemctl --user show -p MainPID --value ihor-aluma-api)"
```

`--check --pid` друкує лише імена ключів і «совпадает/НЕ совпадает» з оточенням
живого процесу — так видно, що systemd розібрав файл рівно як записано.

**Відкат** (сервіс геть, дані лишаються):

```bash
systemctl --user disable --now ihor-aluma-api.service ihor-aluma-purge.timer
rm ~/.config/systemd/user/ihor-aluma-{api.service,purge.service,purge.timer}
systemctl --user daemon-reload
```

**Відмінності від системних юнітів:** нема `User=`/`Group=`;
`WantedBy=default.target`; нема `network-online.target` (системна ціль,
користувацькому юніту недоступна); `EnvironmentFile=%h/.config/aluma/aluma.env`.
**Прибрано `PrivateTmp`, `ProtectSystem`, `ProtectHome`, `ReadWritePaths`:**
у менеджері користувача на цій машині (systemd 255,
`kernel.apparmor_restrict_unprivileged_userns=1`) вони **мовчки не діють** —
заміряно через `systemd-run --user`: з `ProtectHome=read-only` процес пише в
`$HOME`, з `PrivateTmp=true` бачить спільний `/tmp`, код виходу 0. Лишився
`NoNewPrivileges=true` — він діє. Додано `UMask=0077` (обидва сервіси):
`api/store.py` створює базу, `-wal` і `-shm` за umask процесу, типовий `0002`
дав би `0664`. Теку `data/` створювати **заздалегідь** з `0700` — до першого
`load` і до старту юніта: `store.py` створив би її сам за umask (`0775`).

**Публікація статики: `dist/` → `/srv/aluma`** (рішення 2026-09-11). **Після T040 — замінено:** публікує
агент тими самими прапорцями `rsync` і звіряє суми з `MANIFEST.sha256` (`docs/DELIVERY.md`); нижче — ручний спосіб,
як зараз.
Caddy віддає статику з `/srv/aluma` (тека `0755`, власник `ihor`; створює
власник машини за заявкою), а **не** з клону: у `/opt/ihor` Caddy доступу не
отримує, ACL не потрібні. `dist/` і далі збирається в клоні. Після кожної
збірки — два кроки:

```bash
cd /opt/ihor/aluma-table
umask 027
python3 build.py                                    # → dist/ (частина файлів 0640!)
rsync -a --delete-after --delay-updates --chmod=D0755,F0644 \
    /opt/ihor/aluma-table/dist/ /srv/aluma/
find /srv/aluma ! -perm -o=r                         # мусить бути ПОРОЖНЬО
python3 scripts/compare_sites.py https://table.central-aparts.store /srv/aluma --assets --ignore-eol
```

> 🛑 **ПАСТКА: без `--chmod` Caddy віддасть 403 на ЧАСТИНУ сторінок — і це
> гірше, ніж на все: сайт виглядає живим.** `rsync -a` переносить права як є,
> а Caddy для `/srv/aluma` — «інші» (не власник, не в групі `ihor`). Права в
> `dist/` змішані: `shutil.copytree` з `site/` зберігає права вихідних файлів
> (у клоні вони `0664`), а файли, які `build.py` створює сам
> (`shutil.copyfile` — копії сторінок без розширення й `en/*`), беруть права з
> umask. Заміряно 2026-09-11, збірка при `umask 027`, rsync у тимчасову теку:
> без `--chmod` — 102 файли `664`, **14 файлів `640`** (`/privacy`, `/terms`,
> `/accessibility`, `/thanks`, `/404`, `/next`, `/en/index.html` і
> `/en/*`-сторінки), `find ! -perm -o=r` — 14; з
> `--chmod=D0755,F0644` — `644`/`755`, `find` порожній (116 файлів).
> Прапорець фіксує права незалежно від umask і від прав у `site/`.

Решта прапорців: `--delete-after --delay-updates` — нові файли зʼявляються
разом наприкінці, а старі ассети прибираються лише після цього, тож гість не
застане сторінку з посиланнями на ще не залиті ассети. Скісна риска в кінці
`dist/` обовʼязкова: без неї `rsync` покладе теку `dist` **всередину**
`/srv/aluma`. Умова — `find` порожній і `compare_sites` код `0`;
`--ignore-eol` лише доки прод зібраний на Windows (чек-лист, крок 6.5). Станом на кінець 2026-09-11
`/srv/aluma` існує: сайт віддається з коробки (`docs/CUTOVER-CHECKLIST.md`, журнал 11.09, крок 8.3).

**Що перевірено на встановленому сервісі (2026-09-11):**

* `ss -ltnp`: `8005` слухає тільки `127.0.0.1` (мастер + 2 воркери);
* `smoke_local.py` 4/4, health `version=0.4.0-box`; після кожного з двох
  `systemctl --user restart` — знову 4/4;
* `kill -TERM <MainPID>` — сервіс піднявся сам з новим PID (`NRestarts=1`),
  smoke 4/4;
* `box_env.py --check --pid`: усі 10 ключів збігаються з оточенням процесу,
  `EDGE_SECRET` нема;
* таймер у `systemctl --user list-timers`, ручний
  `systemctl --user start ihor-aluma-purge.service` — `Result=success`;
* `/run/user/1001/gunicorn.ctl` і `~/.gunicorn` не зʼявилися;
* `build.py` у клоні → `dist/`; `compare_sites.py` прод проти `dist`
  `--assets --ignore-eol` — код 0 (10 сторінок, 91 ассет).

> ⚠️ **`smoke_local.py` пише тестову заявку в ЖИВУ базу коробки.** Кожен прогін
> додає рядок у `fx_leads` (`is_test`, без сповіщення). `verify --second-pass`
> рахує такі рядки як «тестові» й не червоніє (з 2026-09-11); перший прохід на
> живій базі після смоків — червоний, і це правильно. Див.
> `docs/CUTOVER-CHECKLIST.md`, «ПРОЧИТАТИ ПЕРШИМ».

## `boto3` потрібен НАВІТЬ у режимі SQLite

`api/handler.py:33` робить `import boto3` **безумовно**, на рівні модуля — до
того, як хтось подивиться на `FX_STORAGE`. `api/requirements.txt` його не
містить, бо в лямбді boto3 дає сама середа виконання AWS.

На звичайному сервері його нема, і gunicorn **не піднімається взагалі**:

```
File "/…/api/handler.py", line 33, in <module>
    import boto3
ModuleNotFoundError: No module named 'boto3'
```

Це впіймано руками (див. «Що перевірено» нижче). Найдешевше — просто поставити
`boto3` у venv, як у кроці 2. Альтернатива — зробити імпорт лінивим у
`_tables()`; це правка `handler.py`, і її свідомо не зроблено в цьому комітi:
міняти хендлер напередодні переїзду ризикованіше, ніж поставити пакет.

## Перевірка переїзду: `/api/fx/health` і версія ≠ 0.3.0

```bash
curl -s http://127.0.0.1:8005/api/fx/health
{"ok": true, "version": "0.4.0", "ts": "…"}
```

`version` береться з `APP_VERSION` (`handler.py:931`). **Прод сьогодні віддає
0.3.0.** Тому в `/etc/aluma/aluma.env` `APP_VERSION` **зобовʼязана** бути іншою
(у зразку — `0.4.0`): якщо після переїзду health знову покаже `0.3.0`,
неможливо зрозуміти, який стек відповів — новий gunicorn чи стара лямбда за
CloudFront, який ще не встиг протухнути в кешах DNS. Це єдина дешева перевірка
того, що трафік реально приїхав на сервер.

## Умова переїзду: `FX_STORAGE` задана явно з обох боків

`handler.py:63` — `os.environ.get("FX_STORAGE", "sqlite")`, а `_tables()`
(`handler.py:89-108`) читає це як перемикач: рівно `"sqlite"` — файл на диску,
**будь-що інше — DynamoDB**. Дефолт мовчазний.

* **На сервері** — `FX_STORAGE=sqlite` **явно**. Дефолт сьогодні збігається з
  потрібним значенням, і саме тому його відсутність ніхто не помітить, якщо
  дефолт колись поміняють.
* **У лямбді** — `FX_STORAGE=dynamodb`. Зараз цієї змінної в бойовій лямбді
  **нема взагалі** — по її відсутності й видно, що новий код у прод ще не їхав.
  `infra/template.yaml:141` її вже містить, тож штатний `sam deploy` це
  закриває. Небезпека лишається лише в обхід шаблону: новий код у Lambda БЕЗ
  цієї змінної → handler мовчки обере sqlite → писатиме файл на ефемерний диск
  лямбди → **заявки губитимуться без жодної помилки в лозі**.

`infra/template.yaml` у цьому комітi не чіпався — там уже все правильно.

## Чистка бази: чому це окремий юніт

У DynamoDB протухлі рядки прибирав сам сервіс за атрибутом `ttl`. У SQLite не
прибирає ніхто: `api/store.py:292` `purge_expired()` написана й працює, але її
не кличе НІХТО, крім тестів. Без таймера вічними стають:

| Що | ttl | Скільки цього |
|---|---|---|
| події `fx_events` | `EVENT_TTL_DAYS` = 180 днів | по рядку на подію |
| сесії `fx_sessions` | `SESSION_TTL_DAYS` = 400 днів | по рядку на відвідувача |
| ведра обмежувача | вікно + 60 с (тобто **61 секунда**) | по рядку на IP на хвилину — саме вони й заповнять файл |

`scripts/purge.py` кличе `purge_expired()` по трьох таблицях і робить `VACUUM`
(без нього файл не зменшується). Заявки `fx_leads` не чіпаються: у них `ttl`
не ставиться, вони живуть вічно за задумом.

## X-Forwarded-For: три топології і чому realip потрібен у двох із них

Уся ця морока — через один рядок у коді. `client_ip()` (`handler.py:147-151`)
бере **перший** елемент `X-Forwarded-For` і будує на ньому ключ ведра
обмежувача (`RLL#…` заявки, `RLE#…` події, `LEADS_PER_IP_PER_HOUR=5`). Перший
елемент — найлегше підроблюваний кінець ланцюжка: його ставить сам клієнт.
Тому фронт зобовʼязаний віддавати в застосунок **рівно одне** значення —
адресу гостя, і нічого більше.

### Що виміряно

Сім `POST /api/fx/lead` підряд з **однаковим** підробленим `X-Forwarded-For`
при ліміті 5/год, потім восьмий — з **іншим** підробленим значенням
(422 — валідація тіла, тобто запит дійшов до застосунку; 429 — ліміт спрацював):

| Топологія | Сім запитів поспіль | Після зміни заголовка | Діра |
|---|---|---|---|
| A. напряму в gunicorn | 422 422 422 422 422 **429 429** | **422** | ⚠️ **відкрита** — новий заголовок = нове ведро |
| B. через Caddy без `header_up` | 422 422 422 422 422 **429 429** | **429** | закрита |
| C. через Caddy з `header_up` | 422 422 422 422 422 **429 429** | **429** | закрита |

Плюс пряме спостереження: замість gunicorn підставлено ехо-сервер, що друкує
заголовок. Клієнт шле `X-Forwarded-For: 9.9.9.9` — застосунок бачить
`127.0.0.1`. Клієнт шле `9.9.9.9, 5.5.5.5` — застосунок бачить `127.0.0.1`.

**Caddy за замовчуванням НЕ довіряє вхідному `X-Forwarded-For`: із версії 2.7
`trusted_proxies` порожній, тож клієнтське значення відкидається цілком і
заголовок ставиться заново за адресою зʼєднання. Виміряно на Caddy 2.11.4:
клієнт шле «X-Forwarded-For: 9.9.9.9, 5.5.5.5» — застосунок бачить рівно одну
адресу зʼєднання. Тому в топології Caddy → gunicorn діра закрита з коробки, а
`header_up X-Forwarded-For {remote_host}` дає ІДЕНТИЧНИЙ результат і потрібен
лише як явна страховка на випадок, якщо колись пропишуть `trusted_proxies`.**

> Раніше в цьому файлі й у коментарі `nginx/aluma.conf` було записано, що
> «Caddy за замовчуванням теж дописує до X-Forwarded-For». Це **невірно** —
> заміри вище показують протилежне. Обидва місця виправлені.

### (а) nginx першим: гість → nginx → gunicorn

`$remote_addr` у nginx — справжня адреса гостя. Клієнтський `X-Forwarded-For`
ігнорується: `set_real_ip_from 127.0.0.1` не довіряє запиту, що прийшов не з
петлі, тож realip мовчить і нічого не міняє. `proxy_set_header X-Forwarded-For
$remote_addr` віддає в застосунок одну справжню адресу. Діри нема.

Щоб підняти цю топологію, у конфізі треба замінити `listen 127.0.0.1:8007` на
`listen 80;` + `listen [::]:80;` — рядок і його заміна підписані в самому файлі.
Caddy при цьому має віддати 80/443, а це чужа спільна конфігурація на чотири
проєкти.

### (б) nginx усередині: гість → Caddy → nginx → gunicorn ← реальний варіант

Caddy уже тримає 80/443 і проксує чотири чужі проєкти, тож nginx потрібен не
замість нього, а **всередині** — заради кеша статики й лімитів.

Тут `$remote_addr` для nginx — це адреса Caddy, тобто `127.0.0.1`, **одна на
всіх гостей**. Без realip рядок `proxy_set_header X-Forwarded-For $remote_addr`
проштампував би кожного гостя як `127.0.0.1`: усі падають в одне ведро, і після
пʼятої заявки за годину 429 отримують **усі**. Це самоблокування, і воно
виміряне — в армі B за проксі всі запити лягли в одне ведро й з шостого пішов
429.

Лікує це блок realip у `server {}`:

```nginx
set_real_ip_from  127.0.0.1;
real_ip_header    X-Forwarded-For;
real_ip_recursive on;
```

Після цього `$remote_addr` **усередині** nginx стає справжньою адресою гостя, і
рядок `proxy_set_header X-Forwarded-For $remote_addr` знову вірний **без
змін**. Один конфіг працює в обох топологіях. Підробці взятися нема звідки:
Caddy кладе в `X-Forwarded-For` одне значення й клієнтського префікса не
зберігає (заміри вище), тож `real_ip_recursive` нема куди відходити назад по
ланцюжку.

**`listen` — тільки `127.0.0.1`.** У цій топології nginx мусить слухати
`listen 127.0.0.1:8007`, а не `listen 8007`. Інакше до нього можна постукатися
повз Caddy: підробити адресу це не дасть (`set_real_ip_from` не довіряє чужій
адресі, `X-Forwarded-For` буде проігноровано), а от обійти кеш і ліміти
фронту — дасть.

### (в) тільки Caddy, без nginx

Робочий варіант **уже сьогодні** і без діри: заміри B/C показують, що Caddy сам
нормалізує заголовок. Мінус — нема кеша статики й лімитів на рівні фронту, все
лягає на gunicorn.

**Блок сайту — у файлі [`caddy/aluma.Caddyfile`](caddy/aluma.Caddyfile).**
Тут його копії навмисно нема: дві копії розʼїдуться. У файлі ж — чому
`header_up X-Forwarded-For {remote_host}` лишається, хоча Caddy 2.11.4 і так
відкидає клієнтський XFF (явна страховка на випадок, якщо колись пропишуть
`trusted_proxies`), які імена сайту і коли, і що з CloudFront він замінює
(індекс теки для `/en/`, сторінка 404, `Cache-Control`, заголовки безпеки).

Для (б) у тому самому файлі закоментований блок: увесь вміст сайту
замінюється на `reverse_proxy 127.0.0.1:8007` — на nginx. Порт 8007 живе у
двох місцях, обидва в репозиторії: `nginx/aluma.conf`, рядок `listen` (єдине
справжнє звʼязування порту), і `reverse_proxy` у варіанті (б)
`caddy/aluma.Caddyfile`. Міняти разом.

#### Передумова: caddy має пройти в `/opt/ihor`

> **Замінено 2026-09-11.** Статику Caddy віддає з `/srv/aluma`, а не з
> `/opt/ihor/aluma-table/dist`: прохід у `/opt/ihor` і ACL більше не потрібні.
> Див. «Користувацькі юніти» → «Публікація статики». Нижче — попередній варіант,
> для історії.

`/opt/ihor` — `0750 ihor:ihor`, а користувач `caddy` у групі `ihor` не
складається: без права на прохід статика віддає 403/404 на все. Потрібне
право **лише на прохід** і **лише для caddy** — `setfacl -m u:caddy:--x` на
`/opt/ihor` і `/opt/ihor/aluma-table`, плюс `chmod 0700 data/` (там база з
заявками). **Не** додавати caddy в групу `ihor`: вона читає
`/etc/aluma/aluma.env`. Точні команди — у шапці файлу.

#### Як перевірено цей файл

Лише трьома підкомандами, які не слухають портів і не звертаються до
admin-ендпоінту: `caddy fmt`, `caddy adapt`, `caddy validate`. Перевіряється
**тимчасова копія** в `/tmp/<унікальна>/Caddyfile`, над якою дописано
глобальний блок з `admin off` і `storage file_system` у ту саму теку; теку
після перевірки прибрано. Результат на Caddy 2.11.4:

* `fmt --diff` — нуль змінених рядків;
* `adapt` — rc 0, у JSON `"admin": {"disabled": true}`, у `reverse_proxy` —
  `headers.request.set."X-Forwarded-For" = ["{http.request.remote.host}"]`
  (заміна, не дописування), помилки 403/404 → `/404.html` зі статусом 404;
  одне очікуване попередження `Unnecessary header_up X-Forwarded-For` — це
  лінтер радить те саме «спрощення», від якого застерігає шапка файлу;
* `validate` — `Valid configuration`.

Поведінку на живих запитах (try_files для `/en/`, тип сторінок без
розширення, 404) **не заміряно**: піднімати Caddy сесіям заборонено. Це
висновок із документації Caddy, а не замір.

`/etc/caddy/Caddyfile` у цій роботі не чіпався — це чужа спільна конфігурація,
правити її може лише власник.

### ⚠️ На ace-main фронтом стоїть Caddy, а не nginx

Перевірено на машині: `nginx` **не встановлений** (`/etc/nginx` не існує), а
порти 80/443 тримає **Caddy** (`/etc/caddy/Caddyfile`, сервіс `caddy`
активний). Тобто `nginx/aluma.conf` — це заявка «як має бути», а не файл, який
завтра можна покласти й перезавантажити. Вибір між (а), (б) і (в) — за
власником; конфіг у репозиторії налаштований під (б) як найдешевший.

## nginx/aluma.conf: сторінки, 404, кеш — як у Caddy

Звірка `caddy/aluma.Caddyfile` з кодом показала, що nginx-заявка від нього
відстала. Дві дірки були такі, що гість би їх побачив:

1. **`/privacy` скачувався б файлом.** `build.py` (кінець `main()`) кладе
   поруч із `privacy.html` копію **без розширення** — `privacy`, `terms`,
   `accessibility`, `thanks`, `404`, `next` і їхні `/en/`-версії, — і
   посилання сайту ведуть саме на них. nginx визначає тип за розширенням;
   нема розширення — бере `default_type`, а в стандартному `nginx.conf` це
   `application/octet-stream`.
2. **404 була б голою сторінкою nginx.** CloudFront сьогодні віддає сторінку
   `/404` зі статусом 404 (`CustomErrorResponses` в `infra/template.yaml`), а
   в конфізі не було `error_page`.

Конфіг приведено до поведінки Caddy-файлу (варіант (в)):

| Що | nginx | Звідки |
|---|---|---|
| Сторінки без розширення | `location ~ "^[^.]*$"` з `default_type text/html` + `charset utf-8` → `text/html; charset=utf-8` | `path_regexp ^[^.]*$` у Caddy; тип — як `deploy.sh` ставив у S3 |
| 404 | `error_page 403 404 =404 /404.html`; `Cache-Control: no-store` за `$status` | `handle_errors 403 404` у Caddy, `CustomErrorResponses` у CloudFront |
| JSON 404 від API | не переписується: `proxy_intercept_errors` вимкнений | `reverse_proxy` у Caddy; у CloudFront 404 навмисно не перехоплюється |
| `Cache-Control` | `map $uri`: `/assets/*` — рік, immutable; `robots.txt`, `sitemap.xml` — година; решта — `max-age=0, must-revalidate` | `scripts/deploy.sh` |
| Заголовки безпеки | `add_header … always` у `location /` | `SecurityHeadersPolicy` CloudFront, `header` у Caddy |
| `/en` | `return 308 /en/` + `absolute_redirect off` | `redir /en /en/ 308` |
| Стиск | `gzip` | `encode zstd gzip`, `Compress: true` |
| Лімит тіла | `client_max_body_size 1m` | `request_body { max_size 1MB }` |

Чому саме так, а не простіше:

* **`no-store` на 404 обовʼязковий.** Без нього 404 на `/assets/<старий хеш>`
  взяв би з мапи «рік, immutable», і браузер тримав би цю 404 рік. Рішення
  береться за `$status`, а не за шляхом: при `error_page` запит уже внутрішньо
  переведений на `/404.html`, і шлях не каже, помилка це чи ні.
* **Заголовки — у `location /`, а не в `server {}`.** nginx успадковує
  `add_header` лише з рівня, де своїх нема. На рівні `server` їх успадкував би
  `/api/fx/`, і до JSON доїхав би `Cache-Control` сторінки. Вкладені location
  (`= /en`, сторінки без розширення, `/assets/`) своїх `add_header` не мають і
  тому беруть заголовки з `location /`. Додаси `add_header` у вкладений —
  він втратить усі інші.
* **`absolute_redirect off`.** Інакше nginx пише в `Location` абсолютну адресу
  зі своїм портом, і в топології (б) гість полетів би на
  `http://<host>:8007/en/`, тобто на порт петлі.
* **`^~` на `/api/fx/` і `/admin`.** У цих шляхах теж нема крапки. Поки
  регулярка сторінок вкладена в `location /`, вона їх не бачить, а `^~`
  страхує на випадок, якщо її колись винесуть нагору.
* **`/assets/`: прибрано `expires 30d` + `Cache-Control: public`.** Це давало
  два заголовки `Cache-Control` і місяць замість року з `deploy.sh`.
* Імена змінних `map` — з префіксом `aluma_`: `map` живе в контексті `http`,
  і його імена спільні на весь nginx разом із сайтом `central-aparts-site`.

**Відмінності від Caddy, що лишилися** (кожна підписана в самому файлі):

* стиск лише `gzip`: zstd і brotli в nginx — сторонні модулі;
* `client_max_body_size` на весь `server`, а не лише на API. Різниці нема:
  статика тіла не приймає;
* nginx пише журнал доступу (`/assets/` — ні), а в блоці сайту Caddy `log` нема;
* на `/admin` nginx додає `Cache-Control: no-store`, Caddy — ні. Це дубль:
  `handler.py` `resp()` сам ставить `no-store` на кожну відповідь.

Рядки, вивірені раніше (блок `real_ip`, `listen 127.0.0.1:8007`,
`proxy_set_header X-Forwarded-For $remote_addr` із поясненням), не чіпалися.

### Як перевірено

nginx на машині не встановлений, ставити його не можна, тож **`nginx -t` не
запускався**. Замість нього:

* **Розбір crossplane 0.5.8** (одноразовий venv у `/tmp`, прибраний).
  Конфіг підключений через `include` в обгортку
  `events {} http { … }`, як його підключає `sites-enabled`. Звичайний режим
  (синтаксис, число аргументів, дозволені контексти): `status ok`, 0 помилок.
  Строгий режим (`strict=True`) дає 6 «unknown directive», і всі вони — рядки
  всередині двох блоків `map`: crossplane 0.5.8 читає пари «ключ значення» в
  `map` як директиви. Інших зауважень нема. Контрольна проба на зіпсованій
  копії — `add_header` без аргументів і `map` усередині `server` — дала
  помилки саме на цих рядках, тобто розбір справді ловить контексти й
  аргументи.
* **Звірка кожного location з `caddy/aluma.Caddyfile`** — таблиця вище.

**Живими запитами не заміряно.** Тип `/privacy`, 404 зі статусом 404 і
`no-store`, 308 з `/en`, успадкування `add_header` у вкладені location — це
висновок із документації nginx, а не замір.

## Заявка власнику на потім: полагодити причину в коді, а не симптом

Усе вище — лікування **симптому**. Причина в коді: `client_ip()`
(`handler.py:147-151`) читає **перший** елемент `X-Forwarded-For` — найлегше
підроблюваний кінець ланцюжка. Правильно читати одне довірене значення:
або останній елемент після довіреного проксі, або взагалі `X-Real-IP`, який
фронт ставить сам.

**Сьогодні цього НЕ зроблено свідомо.** Правка бойового шляху `client_ip()`
напередодні переїзду — не той ризик: від неї залежать обидва обмежувачі й
ключі ведер у базі. Поки код такий, фронт зобовʼязаний віддавати рівно одне
значення в `X-Forwarded-For` — саме це й роблять конфіги вище. Код у цьому
комітi не чіпався.

Та сама пастка знайдена в сусідньому проєкті (`central-aparts-site`,
обмежувач перебору купонів у бек-офісі) — вона одна на два проєкти.

## Що перевірено руками, а що ні

**Перевірено (одноразовий venv `/tmp/aluma-deploy-venv`, прибраний за собою):**

* gunicorn піднято **тією самою командою, що в `ExecStart`**
  (`-w 2 --threads 4 --timeout 60 -b 127.0.0.1:8005 api.wsgi:application`),
  з `FX_STORAGE=sqlite` і базою в тимчасовій теці (не в `data/`):
  * `GET /api/fx/health` → **200**, `{"ok": true, "version": "0.4.0", …}` —
    версія прийшла саме з оточення;
  * `GET /nope` → 404 `{"ok": false, "error": "not found"}`;
  * `POST /api/fx/lead` з `x-test: 1` → 200 і `id` заявки — запис у SQLite іде;
  * `GET /admin` без куки → 303 на форму входу.
* `scripts/purge.py`: підкладені протухлі рядки (ведро `RLL#…` і подія) —
  прибрані, заявка й жива сесія лишилися, `VACUUM` пройшов; повторний запуск
  на чистій базі і запуск без файлу бази не падають.
* `systemd-analyze verify` на всіх трьох юнітах: синтаксис чистий. Єдині
  зауваження — `Command /opt/ihor/aluma-table/.venv/bin/{gunicorn,python} is not
  executable: No such file or directory`, тобто «шляхів ще нема», що й
  очікувано: код у `/opt/ihor` ще не розкладений.
* `systemd-analyze calendar '*-*-* 04:15:00'` — розбирається, наступний запуск
  рахується.
* **`--no-control-socket`, 2026-09-11, gunicorn 26.2.0.** Імʼя прапорця
  звірене за `gunicorn --help` і за вихідним кодом (`ControlSocketDisable`,
  `versionadded:: 25.1.0`). Стек піднятий командою з нового `ExecStart` на
  `127.0.0.1:8005`, з `FX_STORAGE=sqlite`, базою в `/tmp` і вигаданими
  одноразовими секретами. `scripts/smoke_local.py` дав 4/4 і код 0. Ні
  `/run/user/1001/gunicorn.ctl`, ні `~/.gunicorn/` не створені ні під час
  роботи, ні після `kill -TERM` мастера по PID. Чужого сокета до прогону не
  було. e2e-gunicorn `central-aparts-site` на 8004 теж ішов із
  `--no-control-socket`. Без прапорця gunicorn свідомо не запускався: конфлікт
  підтверджено за вихідним кодом, відтворювати його означало б зносити сокет
  сусіда.

**НЕ перевірено, і чесно:**

* **Установка СИСТЕМНИХ юнітів не перевірялася** (нема root). Користувацькі —
  встановлені й перевірені, див. «Користувацькі юніти».
* **`nginx -t` не запускався і запустити його нема чим** — nginx на машині
  **не встановлений**, `/etc/nginx` не існує. Конфіг перевірений розбором
  crossplane і звіркою з `caddy/aluma.Caddyfile` (див. «nginx/aluma.conf:
  сторінки, 404, кеш — як у Caddy» → «Як перевірено»). Живими запитами не
  заміряний. Галочки тут не буде, доки власник не поставить nginx.
* **Топологія (б) — Caddy → nginx → gunicorn — цілком не перевірена**: nginx
  нема, зібрати ланцюжок ні з чого. Перевірені (заміри A/B/C у розділі про
  X-Forwarded-For) лише ланки *напряму в gunicorn* і *через Caddy в gunicorn*.
  Те, що `real_ip` дасть у (б) справжню адресу гостя, — висновок із документації
  й із поведінки Caddy, а не замір.
* Міграція даних із DynamoDB (`scripts/migrate_fx.py`) у цій роботі не
  запускалася — це окремий крок і окрема перевірка.
* TLS, DNS, вимкнення CloudFront — не чіпалося взагалі.
