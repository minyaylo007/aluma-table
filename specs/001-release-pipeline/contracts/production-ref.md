# Contract: ссылка окружения `refs/heads/production` [флот]

**Смысл.** Коммит опубликованной версии, которая должна стоять на машине. Единственный сигнал для агента.

**Кто пишет.** Только задание `deploy` (contracts/workflows.md), встроенным `GITHUB_TOKEN` с `contents: write`:
`git push --force origin <sha тега>:refs/heads/production` — вперёд при деплое, назад при откате. Правило репозитория
(R4): запись и перезапись — только исключению GitHub Actions; удаление — никому. Запасной вариант, если исключение
невозможно: правила на ветке нет, защита — на стороне агента (ниже) и правило тегов `v*`.

**Кто читает.** Агент, анонимно, протоколом git v2:

```
git -c credential.helper= -c protocol.version=2 ls-remote https://github.com/minyaylo007/aluma-table \
    refs/heads/production 'refs/tags/v*'
```
с окружением `GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false`.

**Правила агента.**
- Желаемый sha = значение `refs/heads/production`. Нет ссылки → ничего не делать.
- Тег = тег `v*`, чей очищенный sha (`^{}` для аннотированных) равен желаемому; несколько — наибольший по SemVer;
  нет ни одного → `REFUSED(no_release_tag)`, в журнал, машину не трогать.
- Установка — только если файлы релиза этого тега скачались и сошлись (contracts/release-artifact.md).
- Сдвиги ссылки между двумя чтениями не ставятся по отдельности — ставится последнее значение.
- Запросы к `api.github.com` агент не делает никогда.
