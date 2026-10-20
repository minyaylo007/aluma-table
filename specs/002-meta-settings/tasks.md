# Tasks: 002-meta-settings

## Фаза 1 — спецификация (PR-1)
- [x] T001 spec.md, plan.md, contracts/{config,lead,tracking}.md, checklists/requirements.md

## Фаза 2 — API (PR-2)
- [x] T010 [US1] ~~store.py: `SqliteTable.sibling()`~~ — не понадобилось: отдельное соединение `_settings_table()`; тест в tests/test_store_sqlite.py
- [x] T011 [US1] handler: таблица настроек, load/save, валидаторы FR-002, журнал FR-005; tests/test_settings.py
- [x] T012 [US1] GET /api/fx/config по контракту (FR-010), кеш 60 с, без секретов; тест
- [x] T013 [US1] /admin/settings GET/POST: форма, инструкции по-русски, токен «задан/не задан», стереть, ошибки, Origin (FR-001…009); тесты
- [x] T014 [US3] put_lead: новые поля (FR-013), notify с товаром (FR-016); тесты в test_handler
- [x] T015 [US3] CAPI: send_capi_lead, хеши, fbp/fbc, best effort, capi_failed, _redact токена (FR-014/015); tests/test_capi.py
- [x] T016 [US2] /admin/settings/test — кнопка проверки (FR-007), статус CAPI в чек-листе (FR-008); тест
- [x] T017 QUICK.txt/CRITICAL.txt: новые модули; `run_tests.py --pr`, ruff

## Фаза 3 — трекинг, админка, документ (PR-3)
- [x] T020 [US4] site/assets/tracking.js по контракту; tests (node-free проверка: синтаксис через `node --check`, правила в test_tracking_js.py)
- [x] T021 [US5] админка: колонки новых полей, фильтр ?product=, /admin/leads.csv (FR-017); тесты
- [x] T022 [US6] docs/META-TEST.md (FR-018)
- [x] T023 deploy/aluma.env.example: META_GRAPH_VERSION; CLAUDE.md §3 — маршруты; `run_tests.py --full`
