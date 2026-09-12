# Заявка Денису: сайт ALUMA в боевом Caddy

От Игоря, проект ALUMA (лендинг одного стола), 11.09.2026.
Кладёшь и перезагружаешь ты: `/etc/caddy` и reload — только твои. Наши сессии в Caddy
ничего не делали и делать не будут.

> **Обновление 11.09.** Владелец решил иначе (`~/maestro/OWNER-RULES.md`, пп. 20–21): блок
> ALUMA ставим сами. Проверочное имя `table-new` поставлено нами 11.09 в 14:50 — журнал,
> sha и откат в разделе 6 «Выполнено нами 11.09». Боевое `table` — по-прежнему в день DNS.

**Что происходит.** ALUMA переезжает с AWS на ace-main. Фронт — твой Caddy, без nginx:
статика из `/srv/aluma` (опубликованная копия нашей сборки), API — gunicorn на
`127.0.0.1:8005` (слушает только localhost). Нужны два блока сайта: проверочный — сейчас,
боевой — в день переключения DNS.

**Файлы** — в папке `deploy/caddy/` проекта aluma-table:

| Файл | Что это |
|---|---|
| `aluma-site-body.caddyfile` | общее тело блока (статика, API, 404, кеш, заголовки). Сам по себе не конфиг |
| `aluma-table-new.caddyfile` | `table-new.central-aparts.store` — проверочное имя |
| `aluma-table.caddyfile` | `table.central-aparts.store` — боевое имя |

Оба файла с именами делают `import aluma-site-body.caddyfile` внутри своего блока. Путь
относительный, от папки самого файла, поэтому все три лежат рядом. Глобального блока в них
нет.

**Откуда брать.** Из нашего прод-клона на этой машине:
`/opt/ihor/aluma-table/deploy/caddy/`, коммит `0799273` (или новее — мы напишем, когда клон
обновлён). Root его прочитает. Копируем в `/etc/caddy`, а не импортируем из `/opt/ihor`:
конфиг остаётся под root, и наши правки попадают в боевой Caddy только через тебя. Точность
копии проверяешь по sha256 — строки ниже.

Проверено у нас на копии с `admin off`: `caddy fmt` — без изменений, `caddy adapt` — rc 0,
`caddy validate` — `Valid configuration`. Проверяли каждый файл отдельно и оба вместе.
Одно ожидаемое предупреждение `Unnecessary header_up X-Forwarded-For` — строка стоит
намеренно, объяснение в шапке `aluma-site-body.caddyfile`.

## 1. Сейчас: table-new.central-aparts.store

A-запись `table-new` → 95.216.10.169 уже есть.

```bash
# папка под статику — один раз; наполняем её мы
sudo install -d -o ihor -g ihor -m 0755 /srv/aluma

# три файла блока
sudo install -d -m 0755 /etc/caddy/aluma
sudo install -m 0644 /opt/ihor/aluma-table/deploy/caddy/aluma-site-body.caddyfile \
    /opt/ihor/aluma-table/deploy/caddy/aluma-table-new.caddyfile \
    /opt/ihor/aluma-table/deploy/caddy/aluma-table.caddyfile /etc/caddy/aluma/

# сверка перед reload — все три строки должны дать OK
cd /etc/caddy/aluma && sha256sum -c <<'EOF'
7d53564ed7791891b65792674f881bfe1bbdc83b33df1fd8f081641e647a2077  aluma-site-body.caddyfile
81436024e94452d21e0995aa021a339d50ca1129f1fcd7983ce5cd1f03731474  aluma-table-new.caddyfile
50632d1a0d72569202ed6e6bd42d45fce6a653952b08dcaf3953e523c0c88299  aluma-table.caddyfile
EOF

# в конец /etc/caddy/Caddyfile — одна строка:
#     import aluma/aluma-table-new.caddyfile
sudo caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

`aluma-table.caddyfile` лежит рядом, но пока **не импортируется**.

**Проверка после reload:**

```bash
journalctl -u caddy --since '5 min ago' | grep table-new        # certificate obtained successfully
curl -sI https://table-new.central-aparts.store/                # 200, content-type: text/html; charset=utf-8
curl -sI https://table-new.central-aparts.store/no-such-page    # 404
curl -s  https://table-new.central-aparts.store/api/fx/health   # {"ok": true, "version": ..., "ts": ...}
```

Плюс `curl -sI` на любой свой сайт — он должен отвечать как раньше. Если статика отвечает
404 на всё, значит папка `/srv/aluma` пуста — это наша сторона, напиши нам. Если
`/api/fx/health` отвечает 502, значит не запущен наш gunicorn — тоже наша сторона.

## 2. В день переключения: table.central-aparts.store

Сейчас `table` смотрит на CloudFront (A и AAAA). Раньше времени блок **не ставить**: Caddy
не получит сертификат и будет бесконечно повторять ACME-попытки в лог.

1. Мы договариваемся с тобой о времени, предупреждаем владельца за 10 минут и в Route 53
   переводим A-запись `table` на 95.216.10.169. AAAA на CloudFront убираем, иначе Let's
   Encrypt пойдёт проверять по IPv6 не туда.
2. Ты добавляешь в `/etc/caddy/Caddyfile` строку `import aluma/aluma-table.caddyfile` —
   `validate`, `reload`, как в п. 1.
3. Проверка — те же `curl`, что в п. 1, с `table` вместо `table-new`.

Между шагами 1 и 2 у части посетителей будет ошибка TLS, пока нет сертификата. Поэтому время
согласуем заранее, а шаг 2 делаем сразу после шага 1.

## 3. Откат

- **table-new:** удалить строку `import aluma/aluma-table-new.caddyfile` и сделать `reload`.
  Другие сайты это не затрагивает.
- **table:** мы возвращаем записи на CloudFront (AWS до конца проверки не выключается), ты
  удаляешь строку `import aluma/aluma-table.caddyfile` и делаешь `reload`.
- Когда обеих строк `import` нет, можно убрать и папки: `sudo rm -r /etc/caddy/aluma /srv/aluma`.

## 4. Почему статика в /srv/aluma, а не в /opt/ihor

Caddy берёт статику только из `/srv/aluma` — туда мы сами публикуем готовую сборку. `/opt/ihor`
остаётся `0750` без всяких ACL, так что Caddy не получает доступа ни к чему нашему — ни к коду,
ни к базе, ни к секретам, — кроме опубликованной статики. Пользователя `caddy` в группу `ihor`
не добавлять.

## 5. Давняя просьба

`admin off` и `Restart=always`: на 11.09 `Restart=always` уже стоит (`override.conf`), а управляющий
интерфейс общего веб-сервера переведён с сетевого порта на локальный файл с правами только своего
пользователя — нам он недоступен, и это закрывает ту же дыру, спасибо. Полный `admin off` не просим:
с ним перестанет работать перезачитывание конфига (`systemctl reload`).

## 6. Выполнено нами 11.09

Основание — `~/maestro/OWNER-RULES.md` п. 20 (ALUMA ставит свой блок в боевой Caddy сама).
Сессия «🪵 ALUMA · сайт в Caddy на table-new», reload — после «выполняй» дирижёра ALUMA и
объявления главному дирижёру (~14:40, окно до 14:50). Поставлено только `table-new`;
`aluma-table.caddyfile` лежит в `/etc/caddy/aluma/`, но **не импортируется**.

**Что сделано** (время EEST):

| Время | Шаг | Итог |
|---|---|---|
| 14:40 | базовая линия чужих сайтов, `sha256sum /etc/caddy/Caddyfile` | таблица ниже, caddy `active` |
| 14:41 | `sudo install -d -o ihor -g ihor -m 0755 /srv/aluma` | создана |
| 14:41 | прод-клон `/opt/ihor/aluma-table` (`563edc8`): `umask 027; python3 build.py` → `rsync -a --delete-after --delay-updates --chmod=D0755,F0644 dist/ /srv/aluma/` | 116 файлов; `find /srv/aluma ! -perm -o=r` — пусто; `compare_sites.py https://table.central-aparts.store /srv/aluma --assets --ignore-eol` — код 0 (страниц 10/10, ассетов 91/91) |
| 14:42 | `sha256sum -c` трёх файлов (строки из раздела 1) → `sudo install` в `/etc/caddy/aluma/` (`0644 root`) | 3×OK до и после копирования |
| 14:42 | `sudo cp -p /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-aluma-20260911-144236` | копия, sha = «до» |
| 14:42 | дописана в конец одна строка `import aluma/aluma-table-new.caddyfile` | `diff` копии и файла: `116a117`, одна строка |
| 14:42, 14:50 | `sudo caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile` | `Valid configuration` |
| **14:50:28** | `sudo systemctl reload caddy` | rc 0, caddy `active` |

**sha256 `/etc/caddy/Caddyfile`:**

- до: `9e78a653eae656b48c3ce5597623d1879ab2da510bd2aaaccc33d78a71376d80` (= копия `.bak-aluma-20260911-144236`)
- после: `f6655ba93d9cf7f5ca0b6a88400b58af1c417e03875252bb86591a91364537a9`

**Чужие сайты** (`curl -sI -m 10 https://<имя>/`, первая строка):

| Сайт | До (14:40) | После (14:50:31) | После (14:51:14) |
|---|---|---|---|
| `95-216-10-169.sslip.io` | HTTP/2 200 | HTTP/2 200 | HTTP/2 200 |
| `iiko.95-216-10-169.sslip.io` | HTTP/2 404 | HTTP/2 404 | HTTP/2 404 |
| `atmo.95-216-10-169.sslip.io` | HTTP/2 404 | HTTP/2 404 | HTTP/2 404 |
| `tennis.95-216-10-169.sslip.io` | HTTP/2 200 | HTTP/2 200 | HTTP/2 200 |

Отличий нет, откат не понадобился.

**Журнал caddy после reload** (`journalctl -u caddy` с 14:49:30): для `table-new` —
`certificate obtained successfully`. Ошибок нет. Предупреждения: `Unnecessary header_up
X-Forwarded-For` (наше, ожидаемое — см. выше), `Caddyfile input is not formatted` (шапка
чужой части файла, строка 4), `admin endpoint on open interface`, `HTTP/2`/`HTTP/3 skipped`
на порту 80 — эти три были и при прежних загрузках 10–11.09, до нашей строки.

**ALUMA на `table-new`:**

| Запрос | Ответ |
|---|---|
| `curl -sI /` | 200, `text/html; charset=utf-8` |
| `curl -sI /privacy` | 200, `text/html; charset=utf-8` |
| `curl -sI /no-such-page` | 404, `text/html; charset=utf-8` |
| `curl -s /api/fx/health` | `{"ok": true, "version": "0.4.0-box", ...}` |
| `GET /admin` без куки | 303 → `/admin/login` (200) |

`HEAD /admin` отвечает 404 — так отвечает сам API и напрямую на `127.0.0.1:8005` (маршрут
только `GET`), Caddy тут ни при чём. Тестовая заявка не отправлялась.

**Как откатить** (`table-new`):

```bash
sudo cp -p /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-aluma-rollback-$(date +%Y%m%d-%H%M%S)
# убрать ТОЛЬКО свою строку; остальное не трогать
sudo sed -i '\#^import aluma/aluma-table-new\.caddyfile$#d' /etc/caddy/Caddyfile
diff /etc/caddy/Caddyfile.bak-aluma-20260911-144236 /etc/caddy/Caddyfile   # пусто, если чужие не правили файл после нас
sudo caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Затем — та же таблица чужих сайтов. Если после нас в Caddyfile никто ничего не менял
(`sha256sum` = `f6655ba9…37a9`), вместо `sed` можно вернуть копию `.bak-aluma-20260911-144236`.
Папки `/etc/caddy/aluma` и `/srv/aluma` на работу чужих сайтов не влияют; убирать их — только
когда нет ни одной строки `import aluma/…`.
