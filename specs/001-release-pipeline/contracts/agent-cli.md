# Contract: агент деплоя `deploy/agent/pullagent.py` [флот; конфиг — ALUMA]

Python 3 stdlib, без сторонних пакетов. Запуск — системный `python3` (не venv версии).

## Командная строка

| Вызов | Что делает |
|---|---|
| `pullagent.py --config <json> --once` | один цикл: прочитать ссылку, при изменении — поставить (так зовёт таймер) |
| `pullagent.py --config <json> --dry-run` | прочитать ссылку, скачать и сверить артефакт, напечатать «было → станет», ничего не переключать |
| `pullagent.py --config <json> --status` | напечатать `state.json` и последние 5 строк журнала |

## Коды выхода

| Код | Смысл |
|---|---|
| 0 | ничего не изменилось, или установка прошла успешно, или `--dry-run` сошёлся |
| 1 | установка не удалась, прежняя версия возвращена |
| 2 | не удался и возврат — нужен человек |
| 3 | отказ до установки: ручные правки, нет тега, суммы не сошлись |
| 4 | GitHub недоступен / отказал — повтор в следующем цикле |
| 5 | уже идёт другая установка (занята блокировка) |

## Конфиг [ALUMA] `deploy/agent/aluma.json`

```json
{"repo_url": "https://github.com/minyaylo007/aluma-table",
 "ref": "refs/heads/production", "tag_glob": "refs/tags/v*",
 "asset_name": "aluma-{tag}.tar.gz",
 "base_dir": "/opt/ihor/aluma-table", "keep_releases": 10,
 "requirements": "deploy/requirements-server.txt",
 "units_dir": "deploy/systemd/user", "restart_unit": "ihor-aluma-api.service",
 "health_url": "http://127.0.0.1:8005/api/fx/health", "health_timeout_s": 60,
 "static_src": "dist/", "static_dst": "/srv/aluma/",
 "rsync_flags": ["-a", "--delete-after", "--delay-updates", "--chmod=D0755,F0644"]}
```
Агент отказывается стартовать, если `health_url` не на `127.0.0.1`, `base_dir`/`static_dst` вне разрешённых путей
или `repo_url` не `https://github.com/…`.

## Журнал

Одна строка JSON на событие — в `state/deploy.log` и в stdout (journald):
```json
{"event": "deploy_done", "at": "2026-09-12T10:01:30Z", "trigger": "production_ref",
 "from": {"tag": "v0.5.0", "sha": "0000000"}, "to": {"tag": "v0.5.1", "sha": "1111111"}, "result": "ok", "secs": 41}
```
События: `unchanged`, `refused`, `dry_run`, `deploy_start`, `deploy_done`, `revert_done`, `revert_failed`,
`source_unavailable`, `lock_busy`. Поле `reason` — код (`dirty_current`, `no_release_tag`, `checksum`,
`local_health_timeout`, `static_verify`, …) и не более 200 символов текста без URL с параметрами, без содержимого
файлов, без переменных окружения. Короткий итог в stdout: `v0.5.0 → v0.5.1: ok (41 s)`.

## Запрещено (проверяется тестами)

Слушать порты; `sudo`; любые вызовы `caddy`, порта 2019, admin-сокета; запросы к `api.github.com`; заголовок
`Authorization`; git без изолированной конфигурации; чтение `~/.config/aluma/aluma.env` и `data/`; перезапуск
любого юнита, кроме `restart_unit`, и любого не через `systemctl --user`.
