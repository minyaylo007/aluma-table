# Quickstart: проверка выпуска и деплоя ALUMA (001)

Сценарии, доказывающие, что фича работает. Детали форматов — в `contracts/`, сущности — в `data-model.md`.
Правила машины в силе: без sudo, без Caddy (никаких его подкоманд, порт 2019 не трогать), процессы — только по PID,
секреты не печатать.

## 0. Локально (любая сессия, до пуша)

```bash
git pull --rebase
python3 -m venv /tmp/aluma-venv-$USER
/tmp/aluma-venv-$USER/bin/pip install -r api/requirements.txt -r tests/requirements.txt -r requirements-lint.txt
/tmp/aluma-venv-$USER/bin/ruff check .                                   # → All checks passed!
/tmp/aluma-venv-$USER/bin/python -m unittest discover -s tests -t .      # → OK (новые тесты агента, релиза, health)
python3 build.py                                                         # → exit 0
```
Ожидаемо: `tests/test_pull_agent.py` проходит без сети (git, HTTP и systemctl подменены); `tests/test_release_build.py`
собирает архив дважды и получает одинаковую сумму.

## 1. Проверка истории (до публикации) — contracts/secret-scan.md

Итог: `secret-scan-report.md` без значений; «находок нет» или стоп и решение дирижёра.

## 2. Проверки на PR

Ветка с заведомо падающим тестом → PR → `lint`/`test`/`build`/`browser`: красный `test`, слияние заблокировано.
Исправить → зелёные → PR вливается сам (авто-merge). `git push origin HEAD:master` → отказ сервера (правило `master`).

## 3. Релиз

После слияния: вкладка Actions → `release.yml` зелёный; появился тег `vX.Y.Z` и релиз с `aluma-vX.Y.Z.tar.gz` и
`SHA256SUMS`.
```bash
curl -fsSLO https://github.com/minyaylo007/aluma-table/releases/download/vX.Y.Z/SHA256SUMS
curl -fsSLO https://github.com/minyaylo007/aluma-table/releases/download/vX.Y.Z/aluma-vX.Y.Z.tar.gz
sha256sum -c SHA256SUMS                                                  # → aluma-vX.Y.Z.tar.gz: OK
```

## 4. Агент на машине

```bash
python3 /opt/ihor/aluma-table/current/deploy/agent/pullagent.py \
    --config /opt/ihor/aluma-table/current/deploy/agent/aluma.json --dry-run    # «было → станет», код 0
systemctl --user list-timers ihor-aluma-deploy.timer                          # раз в минуту
journalctl --user -u ihor-aluma-deploy -n 20                                  # deploy_done … result ok
curl -s http://127.0.0.1:8005/api/fx/health                                   # version = тег, git_sha = sha тега
ss -ltnp | grep -c pullagent                                                  # → 0 (агент ничего не слушает)
```
В GitHub: Environments → production → активен `vX.Y.Z`, деплой «success».

## 5. Откат и обратно

Actions → `rollback.yml` → Run workflow (ветка `master`) → `version = v<предыдущая>`. ≤ 10 мин: health показывает
прежние номер и sha, статика `/srv/aluma` — от прежней версии (`sha256sum` файла из `MANIFEST.sha256`). Снова
`rollback.yml` с новой версией — возврат.

## 6. Провал проверки здоровья (в пилоте, на безвредной версии)

Версия, у которой health намеренно не отвечает (например, ветка-проба, выпущенная как отдельный релиз): агент
возвращает прежнюю версию (`revert_done`), sha в `state/failed.json`, задание `deploy` — «failure» по таймауту; сайт
всё время отвечает.

## 7. Реальный коммит (FR-029)

Безобидная правка → PR → проверки → авто-merge → релиз → автодеплой → публичный health (`ALUMA_HEALTH_URL`)
показывает новый номер и **sha этого коммита** → откат на прежнюю → health прежних номера и sha → деплой обратно.
Каждый шаг — с ответом GitHub или машины в отчёте исполнителя.
