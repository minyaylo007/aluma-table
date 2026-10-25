#!/usr/bin/env python3
"""Сторож журналів ALUMA: один прогін (кличе ihor-aluma-journal-watch.timer кожні 10 хв) → дирижеру.

OWNER-RULES п.42: error/warning у журналі власного проєкту — одразу сесія й фікс. Сторож лише помічає
й повідомляє одним рядком через ~/bin/lead-say.sh aluma: тип, лічильник, юніт або шлях, де дивитись лог.
Жодного тексту повідомлення з журналу, секрету, телефону, імені, тіла відповіді — у рядок не потрапляє.

Джерела:
  a. journalctl --user -u 'ihor-aluma-*' (власний юніт — ні) від збереженого курсора;
  b. упалі юніти ihor-aluma-* і таймери, що не спрацьовували довше за два свої періоди;
  c. GET http://127.0.0.1:8005/api/fx/health — не 200 або 5 с без відповіді;
  d. база (лише читання, лише агрегати): 404 одного шляху ≥ 3 за годину (подія NotFound зі сторінки 404);
     невдалі входи в /admin ≥ 5 за годину (рядок admin_login_failed у журналі API) — підбір пароля;
  e. нічний ci.yml на GitHub — failure; немає gh чи мережі — тихо пропускаємо, відмітка в стані.

Дедуп: відбиток → не частіше разу на годину; у повідомленні — скільки накопичилось з першої появи.

    python3 scripts/journal_watch.py --since '7 days ago' --dry-run     # перший прохід: друк, без відправки
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

UNIT_GLOB = "ihor-aluma-*"
SELF_UNIT = "ihor-aluma-journal-watch.service"
API_UNIT = "ihor-aluma-api.service"
HEALTH_URL = os.environ.get("JOURNAL_WATCH_HEALTH_URL", "http://127.0.0.1:8005/api/fx/health")
DB_PATH = os.environ.get("FX_DB_PATH", "/opt/ihor/aluma-table/data/aluma.db")
DATA_DIR = os.environ.get("JOURNAL_WATCH_DIR", "/opt/ihor/aluma-table/data")
LEAD_SAY = os.path.expanduser("~/bin/lead-say.sh")
REPO = "minyaylo007/aluma-table"
RESEND_SECONDS = 3600            # один відбиток — не частіше разу на годину
FIRST_SINCE = "-15min"           # перший прогін без курсора: не тягнути всю історію журналу
MAX_MESSAGES = 5                 # більше за прогін — один підсумковий рядок, а не стіна в чаті дирижера
NOT_FOUND_MIN = 3
LOGIN_FAILED_MIN = 5

# Таймер → найбільша пауза між спрацюваннями (два періоди). digest — 09:00 і 20:00 Jerusalem: нічний
# проміжок сам по собі 13 год, а в ніч переходу на зимовий час (кінець жовтня) — 14 год реального
# часу, тож поріг 14 год 30 хв: +30 хв запасу, щоб прогін о 09:00 не випередив сам дайджест.
# Навесні проміжок 12 год — менше звичайного. purge добовий: у ніч переходу 25 год, поріг 26 — запас є.
# ig-refresh (1-го і 15-го) не тут: від установки він ще жодного разу не спрацьовував, а пропуск
# видно й так — тоді впаде публікація.
TIMER_MAX_GAP = {
    "ihor-aluma-backup.timer": timedelta(hours=2),
    "ihor-aluma-purge.timer": timedelta(hours=26),
    "ihor-aluma-digest.timer": timedelta(hours=14, minutes=30),
}

# Відомий шум — НЕ тривога, перевіряється ПЕРШИМ:
#  * gunicorn при кожному викаті/рестарті пише «Worker exiting», «Booting worker» і рівнем [ERROR]
#    «Worker (pid:N) was sent SIGTERM!» — це штатна зупинка воркера, не збій;
#  * systemd про oneshot-юніти: «Starting …», «Finished …», «Deactivated successfully», «Consumed … CPU».
NOISE = re.compile(
    r"Worker exiting|Booting worker|was sent SIGTERM|^Starting |^Started |^Finished |^Stopping |^Stopped "
    r"|Deactivated successfully|Consumed .* CPU time|Handling signal: term|Shutting down: Master"
    r"|Starting gunicorn|Listening at: |Using worker: "
)
GUNICORN_LEVEL = re.compile(r"\[(ERROR|WARNING|CRITICAL)\]")
KEYWORD = re.compile(r"(?i)(critical|traceback|exception|error|warning|failed)")
EVENTS = {"notify_failed", "capi_failed", "unhandled", "wsgi_unhandled", "settings_unavailable", "purge_skipped"}


def run(cmd: list, timeout: int = 30, env=None):
    """stdout або None, якщо команди нема / не відповіла / ненульовий код. Без shell."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ a. журнал

def entry_unit(e: dict) -> str:
    return e.get("USER_UNIT") or e.get("_SYSTEMD_USER_UNIT") or e.get("UNIT") or "?"


def entry_message(e: dict) -> str:
    m = e.get("MESSAGE")
    if isinstance(m, list):                       # journalctl -o json віддає небезпечні байти масивом
        m = bytes(x & 0xFF for x in m if isinstance(x, int)).decode("utf-8", "replace")
    return str(m or "")


def classify(e: dict):
    """Запис журналу → тип тривоги або None (шум, норма, рахується окремо)."""
    msg = entry_message(e).strip()
    if NOISE.search(msg):
        return None
    if msg.startswith("{"):
        try:
            ev = json.loads(msg).get("event")
        except (ValueError, AttributeError):
            ev = None
        if ev == "admin_login_failed":            # один промах власника — не тривога; рахує login_failures()
            return None
        if isinstance(ev, str) and (ev in EVENTS or ev.endswith("_failed")):
            return ev
    g = GUNICORN_LEVEL.search(msg)
    if g:
        return "gunicorn " + g.group(1)
    k = KEYWORD.search(msg)
    try:
        prio = int(e.get("PRIORITY", 6))
    except (TypeError, ValueError):
        prio = 6
    if prio <= 4:
        return ("priority %d" % prio) + (" " + k.group(1).lower() if k else "")
    return k.group(1).lower() if k else None


def fingerprint_text(msg: str) -> str:
    """Повідомлення без цифр, ID і шляхів-хвостів — щоб «той самий збій» мав один відбиток."""
    msg = re.sub(r"[0-9a-f]{8,}", "#", msg.lower())
    return re.sub(r"\d+", "#", msg)[:160]


def journal(since, cursor):
    cmd = ["journalctl", "--user", "-o", "json", "--no-pager", "-u", UNIT_GLOB]
    cmd += ["--after-cursor", cursor] if cursor else ["--since", since or FIRST_SINCE]
    out = run(cmd, timeout=60)
    if out is None:
        return None, cursor
    findings, last = [], cursor
    journal.entries = 0
    for line in out.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        last = e.get("__CURSOR") or last
        journal.entries += 1
        unit = entry_unit(e)
        if unit == SELF_UNIT:
            continue
        kind = classify(e)
        if kind:
            ts = int(e.get("__REALTIME_TIMESTAMP", 0) or 0) / 1e6
            findings.append({"src": unit, "kind": kind, "n": 1,
                             "key": unit + "|" + kind + "|" + fingerprint_text(entry_message(e)),
                             "at": datetime.fromtimestamp(ts, timezone.utc) if ts else now_utc(),
                             "hint": "journalctl --user -u %s --since '{since}'" % unit})
    return findings, last


def login_failures():
    out = run(["journalctl", "--user", "-o", "cat", "--no-pager", "-u", API_UNIT, "--since", "-1h"], timeout=60)
    if out is None:
        return []
    n = sum(1 for x in out.splitlines() if '"admin_login_failed"' in x)
    if n < LOGIN_FAILED_MIN:
        return []
    return [{"src": API_UNIT, "kind": "підбір пароля /admin (admin_login_failed)", "n": n, "abs": True,
             "key": "login_failed", "at": now_utc() - timedelta(hours=1),
             "hint": "journalctl --user -u %s --since '{since}' | grep admin_login_failed" % API_UNIT}]


# ------------------------------------------------------------------ b. юніти й таймери

def failed_units():
    out = run(["systemctl", "--user", "list-units", "--failed", "--no-legend", "--plain", UNIT_GLOB])
    if out is None:
        return []
    units = [line.split()[0] for line in out.splitlines() if line.strip()]
    return [{"src": u, "kind": "юніт failed", "n": 1, "state": True, "key": "failed|" + u, "at": now_utc(),
             "hint": "systemctl --user status %s" % u} for u in units]


def stale_timers(now: datetime):
    cmd = ["systemctl", "--user", "show", *TIMER_MAX_GAP, "-p", "Id", "-p", "ActiveState", "-p", "LastTriggerUSec"]
    out = run(cmd, env={**os.environ, "TZ": "UTC", "LC_ALL": "C"})   # час без «EEST», який strptime не розбирає
    if out is None:
        return []
    found = []
    for block in out.strip().split("\n\n"):
        props = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        unit = props.get("Id", "")
        if unit not in TIMER_MAX_GAP:
            continue
        kind = None
        if props.get("ActiveState") != "active":
            kind = "таймер не активний"
        else:
            last = props.get("LastTriggerUSec", "").strip()
            try:
                when = datetime.strptime(last, "%a %Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
            except ValueError:
                continue                           # ще не спрацьовував — нема з чим порівнювати
            if now - when > TIMER_MAX_GAP[unit]:
                kind = "таймер мовчить %d год" % ((now - when).total_seconds() // 3600)
        if kind:
            found.append({"src": unit, "kind": kind, "n": 1, "state": True, "key": "timer|" + unit, "at": now,
                          "hint": "systemctl --user list-timers %s" % unit})
    return found


# ------------------------------------------------------------------ c. здоров'я

def health():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as r:   # noqa: S310 — лише 127.0.0.1
            code = r.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception:                              # таймаут, відмова з'єднання
        code = "timeout"
    if code == 200:
        return []
    return [{"src": API_UNIT, "kind": "health %s" % code, "n": 1, "state": True, "key": "health", "at": now_utc(),
             "hint": "journalctl --user -u %s --since '{since}'" % API_UNIT}]


# ------------------------------------------------------------------ d. база: 404

SAFE_PATH = re.compile(r"[^A-Za-z0-9/._%~-]")


def not_found(db_path: str, now: datetime):
    if not db_path or db_path == ":memory:" or not os.path.exists(db_path):
        return []
    since = (now - timedelta(hours=1)).isoformat()
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True, timeout=5)
        try:
            rows = con.execute(
                "SELECT json_extract(doc, '$.page'), count(*) FROM fx_events WHERE rk >= ? "
                "AND json_extract(doc, '$.event_name') = 'NotFound' AND NOT coalesce(json_extract(doc, '$.is_test'), 0) "
                "GROUP BY 1 HAVING count(*) >= ?", (since, NOT_FOUND_MIN)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    out = []
    for page, n in rows:
        path = SAFE_PATH.sub("?", str(page or "").split("?", 1)[0])[:80] or "/"
        out.append({"src": "404 " + path, "kind": "NotFound", "n": int(n), "abs": True, "key": "404|" + path,
                    "at": now - timedelta(hours=1), "hint": "/admin/funnel або fx_events NotFound"})
    return out


# ------------------------------------------------------------------ e. CI

def nightly_ci(status: dict):
    out = run(["gh", "run", "list", "-R", REPO, "-w", "ci.yml", "-e", "schedule", "--limit", "1",
               "--json", "conclusion,databaseId"], timeout=30)
    if out is None:
        status["ci"] = "skipped"
        return []
    try:
        runs = json.loads(out)
    except ValueError:
        status["ci"] = "skipped"
        return []
    status["ci"] = "ok"
    if runs and runs[0].get("conclusion") == "failure":
        rid = str(runs[0].get("databaseId", ""))
        return [{"src": "ci.yml nightly", "kind": "CI failure", "n": 1, "key": "ci|" + rid, "at": now_utc(),
                 "hint": "gh run view %s -R %s --log-failed" % (rid, REPO)}]
    return []


# ------------------------------------------------------------------ дедуп і відправка

def window(seconds: float) -> str:
    m = max(1, int(seconds // 60))
    if m < 120:
        return "%d хв" % m
    if m < 72 * 60:
        return "%d год" % (m // 60)
    return "%d дн" % (m // 1440)


def message(f: dict, n: int, first: datetime, now: datetime) -> str:
    local = first.astimezone().strftime("%Y-%m-%d %H:%M")
    text = "🔴 ALUMA журнал: %s — %s ×%d за %s; лог: %s" % (
        f["src"], f["kind"], n, window((now - first).total_seconds()), f["hint"].replace("{since}", local))
    return " ".join(text.split())                  # lead-say бере лише один рядок


def plan(findings: list, state: dict, now: datetime) -> list:
    """Оновлює стан; повертає [(ключ, текст)] до відправки. Ключ стану — хеш, не текст журналу."""
    seen = state.setdefault("seen", {})
    now_keys = set()
    for f in findings:
        k = hashlib.sha256(f["key"].encode()).hexdigest()[:16]
        now_keys.add(k)
        s = seen.setdefault(k, {"last_sent": 0, "pending": 0, "first": f["at"].timestamp()})
        if not s["pending"]:
            s["first"] = f["at"].timestamp()
        # абсолютні агрегати (лічильник за годину) не складаємо між прогонами — беремо найбільший
        s["pending"] = max(s["pending"], f["n"]) if f.get("abs") else s["pending"] + f["n"]
        s["f"] = {x: f[x] for x in ("src", "kind", "hint")}
        s["state"] = bool(f.get("state"))
    # стан (таймер мовчить, юніт failed, health) або є зараз, або його нема: зниклий не досилаємо.
    # Лічильники подій (журнал, 404, login_failed) — події вже сталися, накопичене доповідаємо.
    for k, s in seen.items():
        if s.get("state") and k not in now_keys:
            s["pending"] = 0
    out = []
    for k, s in seen.items():
        if s["pending"] and now.timestamp() - s["last_sent"] >= RESEND_SECONDS and "f" in s:
            first = datetime.fromtimestamp(s["first"], timezone.utc)
            out.append((k, message(s["f"], s["pending"], first, now)))
    return out


def send(text: str, dry_run: bool) -> bool:
    if dry_run:
        print(text)
        return True
    try:
        r = subprocess.run([LEAD_SAY, "aluma", text], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def load_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path: str, state: dict, now: datetime) -> None:
    week = now.timestamp() - 7 * 86400            # тихі відбитки старші за тиждень — геть
    state["seen"] = {k: s for k, s in state.get("seen", {}).items() if s.get("pending") or s.get("last_sent", 0) > week}
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="друк замість lead-say; курсор і стан не міняються")
    ap.add_argument("--since", help="журнал від цього часу, без курсора (перший прохід)")
    ap.add_argument("--data-dir", default=DATA_DIR)
    ap.add_argument("--db", default=DB_PATH)
    a = ap.parse_args(argv)

    now = now_utc()
    state_path = os.path.join(a.data_dir, "journal-watch-state.json")
    cursor_path = os.path.join(a.data_dir, "journal-watch.cursor")
    state = {} if a.dry_run else load_state(state_path)
    cursor = None
    if not a.since:
        try:
            with open(cursor_path, encoding="utf-8") as fh:
                cursor = fh.read().strip() or None
        except OSError:
            cursor = None

    status = {}
    jf, last = journal(a.since, cursor)
    status["journal"] = "skipped" if jf is None else "ok"
    status["entries"] = getattr(journal, "entries", 0)
    findings = (jf or []) + login_failures() + failed_units() + stale_timers(now) + health() + not_found(a.db, now)
    findings += nightly_ci(status)

    todo = plan(findings, state, now)
    sent = failed = 0
    for i, (k, text) in enumerate(todo):
        if i == MAX_MESSAGES:
            text = "🔴 ALUMA журнал: ще %d відбитків понад %d — journalctl --user -u '%s' --since '-1h'" % (
                len(todo) - MAX_MESSAGES, MAX_MESSAGES, UNIT_GLOB)
        ok = send(text, a.dry_run)
        for kk in ([k] if i < MAX_MESSAGES else [x for x, _ in todo[MAX_MESSAGES:]]):
            if ok:
                state["seen"][kk].update(last_sent=now.timestamp(), pending=0)
        sent, failed = sent + ok, failed + (not ok)
        if i == MAX_MESSAGES:
            break

    print(json.dumps({"event": "journal_watch", "findings": len(findings), "sent": sent,
                      "send_errors": failed, **status}))
    if not a.dry_run:
        os.makedirs(a.data_dir, exist_ok=True)
        state["status"] = {**status, "at": now.isoformat()}
        save_state(state_path, state, now)
        if last and last != cursor and not a.since:
            with open(cursor_path, "w", encoding="utf-8") as fh:
                fh.write(last + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
