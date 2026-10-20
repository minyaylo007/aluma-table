# Implementation Plan: 002-meta-settings

**Spec**: [spec.md](spec.md) · **Contracts**: [config](contracts/config.md), [lead](contracts/lead.md), [tracking](contracts/tracking.md)

## Технический контекст
- Python 3.12/3.13, stdlib + `requests` (уже есть) + `boto3` (уже есть). Новых зависимостей нет.
- Один хендлер `api/handler.py` (Lambda и gunicorn), хранилище SQLite через shim `api/store.py`.
- Тесты — stdlib `unittest`, без сети: `requests.post` патчится, база `:memory:`.

## Constitution Check
| Инвариант | Как соблюдён |
|---|---|
| I. Тесты до пуша | `tests/test_settings.py`, `tests/test_capi.py`, расширение `tests/test_handler.py`; `run_tests.py --pr` перед PR |
| II. Секреты | токен не выводится (HTML/JSON/лог), `_redact` режет и его; тест ищет токен во всех ответах и stdout |
| III. AWS | ничего нового от AWS; DynamoDB-ветка — только имя таблицы для симметрии |
| IV. Сеть | новых портов нет; тесты без порта |
| V. Чужое | только `api/`, `tests/`, `site/assets/tracking.js`, `docs/META-TEST.md`, `deploy/aluma.env.example`, `specs/002-*` |
| VI. Git | ветки `noch/3-nastroyki-<шаг>`, PR, `--squash --auto` |
| VII. Простота | одна новая таблица, без шифрования (решение 2 spec), без CSRF-токенов (решение 5) |

## Устройство
1. `api/store.py`: `tables()` без изменений; новая `SqliteTable.sibling(name, key_schema)` — таблица в той же базе.
2. `api/handler.py`:
   - `_settings_table()`; `load_settings()` (дефолты + запись `SETTINGS/current`), `save_settings()`,
     `audit()`; валидаторы полей (`SETTINGS_FIELDS`).
   - `GET /api/fx/config` → `public_config()`.
   - `GET/POST /admin/settings`, `POST /admin/settings/test`; проверка `Origin`.
   - `put_lead`: новые поля (FR-013), после `notify()` — `send_capi_lead()`.
   - `capi_send(events)` → `(ok, status)`; хеширование `_sha256_norm`; статус в `CAPI/status`.
   - `_redact` вырезает и токен CAPI (из настроек, не из env).
   - админка: колонки, фильтр `product`, `/admin/leads.csv`.
3. `site/assets/tracking.js` — по контракту.
4. `docs/META-TEST.md`, `deploy/aluma.env.example` (`META_GRAPH_VERSION`, необязательная).

## Шаги и PR
- PR-1 `noch/3-nastroyki-spec` — spec/plan/tasks/contracts (к 23:30).
- PR-2 `noch/3-nastroyki-api` — store, настройки, config, поля заявки, CAPI, журнал (к 02:00).
- PR-3 `noch/3-nastroyki-track` — tracking.js, админка заявок (колонки, фильтр, CSV), META-TEST.md (к 04:30).

## Complexity Tracking
Нет отступлений.
