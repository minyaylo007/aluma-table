#!/bin/bash
# deploy-box.sh — викат злитого коміта master на прод (ця машина) і відкат тією самою командою.
#
#   scripts/deploy-box.sh <sha>            # fetch → checkout sha у клоні → pip (пини) → build --production
#                                           #   → rsync у /srv/aluma → restart лише ihor-aluma-api → health
#   scripts/deploy-box.sh <sha> --preview  # так само, але збірка без --production (так прод зібраний сьогодні)
#   scripts/deploy-box.sh --status         # sha на проді, стан юніта, health, останні рядки журналу
#
# Відкат = та сама команда з попереднім sha (його друкує --status перед викатом і журнал).
#
# Межі, яких скрипт не переходить: Caddy не чіпає (ні reload, ні stop, ні порт 2019); перезапускає ТІЛЬКИ
# власний user-юніт ihor-aluma-api.service; у /srv/aluma пише лише rsync із --chmod (deploy/README.md,
# пастка з 403); секретів не читає й не друкує. Нічого руками на проді не лагодить: не вийшло — повертає
# попередній sha і виходить із кодом помилки.
#
# Коди виходу: 0 — ок; 2 — відмова до будь-яких змін (sha не в origin/master, брудне дерево клону, нема юніта);
# 3 — збірка відмовила (факти власника не заповнені), клон повернуто, /srv і юніт не чіпались;
# 4 — health після перезапуску не 200/ok, відкочено на попередній sha; 5 — rsync або права в /srv/aluma,
# відкочено. Журнал: /opt/ihor/aluma-table/tmp/deploy-box.log — рядок на спробу: час, було, стало, режим, результат.

set -euo pipefail

CLONE="${ALUMA_CLONE:-/opt/ihor/aluma-table}"
STATIC="${ALUMA_STATIC:-/srv/aluma}"
UNIT="${ALUMA_UNIT:-ihor-aluma-api.service}"
HEALTH_URL="${ALUMA_HEALTH_URL:-http://127.0.0.1:8005/api/fx/health}"
LOG="$CLONE/tmp/deploy-box.log"
HEALTH_WAIT="${ALUMA_HEALTH_WAIT:-30}"

say() { printf 'deploy-box: %s\n' "$*"; }
die() { say "$*" >&2; exit 2; }
log() { mkdir -p "$(dirname "$LOG")"; printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }

head_sha()  { git -C "$CLONE" rev-parse --short=7 HEAD; }
health()    { curl -s -m 5 -o /tmp/deploy-box-health.$$ -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || true; }

# Режим останнього вдалого викату (production/preview) — для відкату, коли режим не заданий явно.
last_ok_mode() {
    if [ -f "$LOG" ]; then
        awk '$5 == "ok" {m = $4} END {print (m == "" ? "preview" : m)}' "$LOG"
    else
        echo preview
    fi
}

status() {
    say "клон $CLONE на $(head_sha) ($(git -C "$CLONE" log -1 --format=%cd --date=short HEAD))"
    say "юніт $UNIT: $(systemctl --user is-active "$UNIT" 2>/dev/null || true)"
    local code; code="$(health)"
    say "health $HEALTH_URL → HTTP ${code:-000} $(cat /tmp/deploy-box-health.$$ 2>/dev/null || true)"
    rm -f /tmp/deploy-box-health.$$
    if [ -f "$LOG" ]; then say "журнал (останні 3):"; tail -3 "$LOG" | sed 's/^/  /'; else say "журналу ще немає"; fi
    say "відкат: scripts/deploy-box.sh $(head_sha)"
}

# apply <sha> <mode> — checkout, залежності, збірка, статика, перезапуск, health. Повертає 0/3/4/5.
apply() {
    local sha="$1" mode="$2" flag=""
    [ "$mode" = production ] && flag="--production"
    git -C "$CLONE" checkout -q --detach "$sha"
    "$CLONE/.venv/bin/pip" install -q -r "$CLONE/deploy/requirements-server.txt"
    if ! (cd "$CLONE" && umask 027 && python3 build.py $flag > "$CLONE/tmp/deploy-box-build.log" 2>&1); then
        say "збірка ($mode) відмовила — див. $CLONE/tmp/deploy-box-build.log"
        return 3
    fi
    if ! rsync -a --delete-after --delay-updates --chmod=D0755,F0644 "$CLONE/dist/" "$STATIC/" \
        || [ -n "$(find "$STATIC" ! -perm -o=r | head -1)" ]; then
        say "rsync у $STATIC не вдався або лишив файли без прав на читання"
        return 5
    fi
    systemctl --user restart "$UNIT"
    local i code
    for ((i = 0; i < HEALTH_WAIT; i++)); do
        code="$(health)"
        if [ "$code" = 200 ] && grep -q '"ok": *true' /tmp/deploy-box-health.$$ 2>/dev/null; then
            rm -f /tmp/deploy-box-health.$$
            return 0
        fi
        sleep 1
    done
    say "health не відповів 200/ok за ${HEALTH_WAIT} с"
    rm -f /tmp/deploy-box-health.$$
    return 4
}

deploy() {
    local sha="$1" mode="$2"
    [[ "$sha" =~ ^[0-9a-f]{7,40}$ ]] || die "sha має бути 7–40 шістнадцяткових символів: '$sha'"
    [ -d "$CLONE/.git" ] || die "клон $CLONE не знайдено"
    [ -x "$CLONE/.venv/bin/pip" ] || die "у клоні немає .venv — юніт запускає gunicorn саме звідти"
    systemctl --user cat "$UNIT" > /dev/null 2>&1 || die "user-юніт $UNIT не встановлено"
    [ -d "$STATIC" ] && [ -w "$STATIC" ] || die "$STATIC відсутній або не для запису"
    [ -z "$(git -C "$CLONE" status --porcelain --untracked-files=no)" ] \
        || die "у клоні є незакомічені зміни відстежуваних файлів — спершу розібратись руками (git -C $CLONE status)"
    git -C "$CLONE" fetch -q origin master
    git -C "$CLONE" merge-base --is-ancestor "$sha" origin/master 2>/dev/null \
        || die "sha $sha не належить origin/master — викочуємо лише злите"

    local prev; prev="$(head_sha)"
    local full; full="$(git -C "$CLONE" rev-parse --short=7 "$sha")"
    if [ "$full" = "$prev" ]; then
        say "клон уже на $prev — перезбираю й перезапускаю той самий sha"
    fi
    say "викат $prev → $full ($mode); відкат: scripts/deploy-box.sh $prev"
    log "$prev $full $mode start"

    local rc=0
    apply "$full" "$mode" || rc=$?
    case "$rc" in
        0) log "$prev $full $mode ok"; say "готово: прод на $full, health ok"; status; return 0 ;;
        3) git -C "$CLONE" checkout -q --detach "$prev"; log "$prev $full $mode build-refused"
           say "клон повернуто на $prev; /srv/aluma і юніт не чіпались"; return 3 ;;
        *) log "$prev $full $mode failed-$rc rolling-back"
           say "відкочую на $prev ($(last_ok_mode))"
           local rb=0; apply "$prev" "$(last_ok_mode)" || rb=$?
           if [ "$rb" = 0 ]; then log "$full $prev $(last_ok_mode) rollback-ok"; say "відкочено: прод на $prev, health ok"
           else log "$full $prev $(last_ok_mode) rollback-FAILED-$rb"; say "ВІДКАТ НЕ ВДАВСЯ (код $rb) — потрібна людина" >&2; fi
           return "$rc" ;;
    esac
}

main() {
    local sha="" mode=production
    while [ $# -gt 0 ]; do
        case "$1" in
            --status) status; exit 0 ;;
            --preview) mode=preview ;;
            --production) mode=production ;;
            -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
            -*) die "невідомий прапорець $1" ;;
            *) [ -z "$sha" ] || die "зайвий аргумент $1"; sha="$1" ;;
        esac
        shift
    done
    [ -n "$sha" ] || { sed -n '2,8p' "$0"; exit 2; }
    deploy "$sha" "$mode"
}

main "$@"
