# Data Model: выпуск и деплой ALUMA через GitHub (001)

Живые данные ALUMA (SQLite `data/aluma.db`: `fx_events`, `fx_leads`, `fx_sessions`) этой фичей **не меняются**.
Ниже — сущности конвейера и агента. Пометки [флот]/[ALUMA] — как в spec.md. Все примеры синтетические.

## Версия [флот]

| Поле | Тип | Правило |
|---|---|---|
| `tag` | строка `vX.Y.Z` | SemVer; уникален; создаётся только конвейером; не удаляется и не перезаписывается |
| `git_sha` | 40 hex | коммит master, на который указывает тег (для аннотированного — «очищенный») |
| `bump` | `patch` / `minor` / `major` | из меток слитого PR: `release:major` > `release:minor` > patch |
| `notes` | текст | список изменений со времени прошлого тега |

Первая версия — `v0.5.0`. Следующая — `next_version(теги, метки)` (contracts/workflows.md).

## Файлы релиза [флот]

| Файл | Содержимое |
|---|---|
| `aluma-vX.Y.Z.tar.gz` | детерминированный архив, корень `aluma-vX.Y.Z/` (contracts/release-artifact.md) |
| `SHA256SUMS` | `<sha256>  <имя файла>` для каждого файла релиза, кроме себя |

Внутри архива: дерево коммита, `dist/`, `RELEASE.json`, `RELEASE.env`, `MANIFEST.sha256`.

## Ссылка окружения [флот]

`refs/heads/production` → `git_sha` опубликованной версии. Двигает только задание `deploy` (вперёд — деплой,
назад — откат). Агент ставит её значение, только если на этот sha указывает тег `v*` с полным набором файлов релиза.

## Деплой в GitHub [флот] (создаётся GitHub для задания с `environment: production`)

Состояния, видимые в GitHub: `queued` → `in_progress` → `success` | `failure` | `cancelled`; успешный деплой
становится `inactive`, когда успешен следующий.

| Событие | Состояние |
|---|---|
| задание `deploy` началось | `in_progress` |
| публичный health показал `version` = тег и `git_sha` = sha до таймаута (15 мин) | `success` |
| таймаут, тег или файлы релиза не найдены | `failure` |
| новый деплой отменил ожидание (concurrency) | `cancelled` («неактуален» в терминах spec) |

## Окружение `production` [флот]

| Поле | Значение для ALUMA |
|---|---|
| правило веток | только `master` |
| переменная `ALUMA_HEALTH_URL` | `https://table.central-aparts.store/api/fx/health` (DNS `table` на коробке с 2026-09-11); `table-new` — только если переключение не принято |
| секреты окружения | нет (пусто и так задокументировано) |

## Состояние агента на машине [флот; пути — ALUMA]

Каталог `/opt/ihor/aluma-table/state/` (0700):

- `state.json`:
  ```json
  {"current": {"tag": "v0.5.1", "git_sha": "1111111111111111111111111111111111111111"},
   "previous": {"tag": "v0.5.0", "git_sha": "0000000000000000000000000000000000000000"},
   "updated_at": "2026-09-12T10:00:00Z"}
  ```
  `previous` = `null` при первом переходе с `0.4.0-box` (возврат — вручную, docs/DELIVERY.md).
- `failed.json`: `{"<git_sha>": {"tag": "v0.5.2", "at": "…", "reason": "local_health_timeout"}}` — sha, которые не
  ставятся повторно, пока ссылка на них не уйдёт и не вернётся новым деплоем (агент очищает запись, когда ссылка
  указывает на другой sha).
- `deploy.log` — строки JSON (contracts/agent-cli.md).
- `agent.lock` — `flock`, одна установка за раз.
- `downloads/<tag>/` — скачанные файлы релиза до проверки.

## Каталоги версий [ALUMA]

`releases/<tag>/` — распакованный архив; `.venv` → `../../venvs/<hash>`; `venvs/<hash>/` — venv по
`sha256(deploy/requirements-server.txt)[:12]`; `current` → `releases/<tag>`. Хранится 10 последних версий;
текущая и предыдущая не удаляются никогда.

## Переходы агента [флот]

```
IDLE ─read ref─► UNCHANGED (sha = current или в failed) ─► IDLE
     └► RESOLVE (тег v* на sha?) ─нет─► REFUSED("no_release_tag")
          └► PRECHECK (current совпадает с MANIFEST?) ─нет─► REFUSED("dirty_current")
               └► DOWNLOAD ─► VERIFY (SHA256SUMS, MANIFEST, RELEASE.json = тег и sha) ─нет─► REFUSED("checksum")
                    └► [--dry-run: PLAN_PRINTED ─► IDLE]
                    └► PREPARE (venv, юниты) ─► SWITCH (current) ─► RESTART ─► LOCAL_HEALTH ─► PUBLISH_STATIC
                         ─► VERIFY_STATIC ─► DONE
                         любой провал после SWITCH ─► REVERT ─► REVERTED (+failed.json) | REVERT_FAILED
```
Прерывание (перезагрузка) между SWITCH и DONE: при следующем запуске агент видит `current` ≠ `state.current` и
доводит до согласованного — либо проходит LOCAL_HEALTH/PUBLISH_STATIC новой версии, либо возвращает прежнюю.

## Отчёт проверки истории [флот]

`specs/001-release-pipeline/secret-scan-report.md`: дата; охват (число коммитов, ссылок, прогонов Actions,
артефактов, релизов, issues/PR); версии и суммы сканеров; находки — правило, коммит, путь, строка, без значений;
решение дирижёра по каждой; итог «можно публиковать / нельзя».
