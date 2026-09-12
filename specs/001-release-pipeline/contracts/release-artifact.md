# Contract: файлы релиза [флот; содержимое `dist/` — ALUMA]

Собирает `scripts/release_build.py --tag vX.Y.Z --sha <40 hex> --out <dir>` из чистого checkout коммита тега.

## Файлы релиза GitHub

| Имя | Что |
|---|---|
| `aluma-vX.Y.Z.tar.gz` | архив (ниже) |
| `SHA256SUMS` | строки `<64 hex>␠␠<имя>` для каждого файла релиза, кроме себя; LF; сортировка по имени |

Ссылки скачивания (без API, без авторизации):
`https://github.com/minyaylo007/aluma-table/releases/download/vX.Y.Z/SHA256SUMS`,
`https://github.com/minyaylo007/aluma-table/releases/download/vX.Y.Z/aluma-vX.Y.Z.tar.gz`.

## Архив

Детерминированный: записи отсортированы по имени; `mtime` = время коммита; uid/gid 0, имена пустые; права 0644 /
0755 (исполняемые из git — 0755); gzip без имени файла и времени. Одинаковый коммит → побайтно одинаковый архив.

```
aluma-vX.Y.Z/
├── <дерево коммита из git archive>        api/, build.py, deploy/, scripts/, site/, i18n/, content.json, …
├── dist/                                  результат `python3 build.py` (preview, без Pillow) этого коммита
├── RELEASE.json
├── RELEASE.env
└── MANIFEST.sha256                        `<64 hex>␠␠<путь от корня>` для каждого файла архива, кроме себя
```

`RELEASE.json`:
```json
{"version": "v0.5.0", "git_sha": "0123456789abcdef0123456789abcdef01234567", "build_mode": "preview",
 "committed_at": "2026-09-12T09:55:00Z"}
```

`RELEASE.env` (не секреты; читается юнитом API после `aluma.env`):
```
APP_VERSION=v0.5.0
GIT_SHA=0123456789abcdef0123456789abcdef01234567
```

**Запрещено в архиве:** `data/`, `dump*`, `*.db`, `.env*` (кроме `deploy/aluma.env.example`), `infra/samconfig.toml`,
`node_modules/`, `ms-playwright/`, `.venv/`. Сборка падает, если такой путь встретился.

## Проверки у агента

1. `SHA256SUMS` скачан; сумма архива совпала.
2. Архив распакован во временный каталог; каждый файл совпал с `MANIFEST.sha256`, лишних файлов нет.
3. `RELEASE.json`: `version` = тег, `git_sha` = sha ссылки `production`.
Любой провал — ничего не ставится (`REFUSED`).
