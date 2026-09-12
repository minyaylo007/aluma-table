# Contract: проверка истории перед публикацией [флот; шаблоны данных — ALUMA]

## `scripts/secret_scan.py`

```
python3 scripts/secret_scan.py --repo <путь к зеркалу> [--logs <папка с журналами Actions>] --report <файл.md>
```
- Читает `git log --all -p --no-color` зеркала (и файлы из `--logs`), ищет шаблоны (research.md R8).
- Печатает и пишет в отчёт **только**: правило, коммит (короткий sha), путь, номер строки, число совпадений.
  Значение, фрагмент строки, соседний текст — никогда.
- Код выхода: 0 — находок нет; 1 — есть находки; 2 — ошибка запуска (нет зеркала и т. п.).

## Порядок проверки (задачи фазы 1 в tasks.md)

1. Временная папка вне дерева: `umask 077`, `mktemp -d /tmp/aluma-scan-XXXXXX`.
2. `git clone --mirror https://github.com/minyaylo007/aluma-table.git <tmp>/mirror.git` (сессия-исполнитель; репо ещё
   приватный — с правами владельца на чтение).
3. gitleaks: закреплённая версия, суммы сверены с `checksums.txt` релиза gitleaks; `gitleaks git <mirror>
   --log-opts=--all --redact --report-format json --report-path <tmp>/gitleaks.json`; в отчёт — только правило,
   коммит, путь, строка.
4. `scripts/secret_scan.py` по зеркалу.
5. Журналы Actions: `gh run list --limit 1000 --json databaseId` → `gh run view <id> --log > <tmp>/logs/<id>.log`;
   артефакты прогонов, релизы, issues, PR с комментариями — перечень и тот же поиск.
6. Отчёт `specs/001-release-pipeline/secret-scan-report.md` (data-model.md «Отчёт проверки истории»); временная папка
   удаляется.

## Решение

- Находок нет → объявление дирижёру → отдельная задача смены видимости и правил.
- Есть находки (в том числе заведомые: AWS account id и ARN сертификата в `infra/samconfig.toml.example`) → стоп,
  отчёт дирижёру, видимость не меняется до его решения.
