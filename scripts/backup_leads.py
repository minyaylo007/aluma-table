#!/usr/bin/env python3
"""Почасовий бекап бази заявок ALUMA: консистентна копія SQLite + перевірка + ротація.

ЧОМУ ЦЕ ІСНУЄ. Заявки — єдиний результат тесту попиту, а data/aluma.db до цього
не копіювалася автоматично ніколи (лише ручні копії 11.09). Щогодинні бекапи
машини — Дениса, вони покривають чужі /opt, не нашу теку.

Що робить один запуск (кличе таймер ihor-aluma-backup.timer, щогодини в :07):

  1. Відкриває базу з FX_DB_PATH лише на читання і робить копію через
     sqlite3 Connection.backup() — це консистентний знімок навіть під живим
     gunicorn у режимі WAL (cp файлу без -wal дав би напівзаписану базу).
     Лічба заявок і копія беруться з ОДНОГО знімка читання, тож заявка, що
     прийшла посеред бекапу, не дає хибного «rows не зійшлися».
  2. Копію пише у тимчасовий файл у теці бекапів (0600, тека 0700), переводить
     її в journal_mode=DELETE (один файл, без -wal/-shm), перевіряє
     PRAGMA integrity_check і рядки таблиці заявок = в оригіналі, і лише тоді
     перейменовує в aluma-ГГГГММДД-ЧЧММ.db (час UTC — без дублів при переході
     на зимовий час).
  3. Ротація: останні 72 копії (3 доби почасово) + найсвіжіша копія кожної доби
     за 30 діб. Видаляє ЛИШЕ файли за шаблоном імені вище й лише в цій теці.

Вивід — один JSON-рядок, без даних і без секретів:
    {"event": "backup_ok", "rows": N, "bytes": M, "kept": K}
    {"event": "backup_failed", "reason": "..."}            → код виходу 1

Руками (так само, як юніт):
    FX_DB_PATH=/opt/ihor/aluma-table/data/aluma.db python3 scripts/backup_leads.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import sys
import urllib.parse

FX_DB_PATH = os.environ.get("FX_DB_PATH", "data/aluma.db")
LEADS_TABLE = os.environ.get("LEADS_TABLE", "fx_leads")
BACKUP_DIR = os.environ.get("FX_BACKUP_DIR", "/opt/ihor/aluma-table/backups")

KEEP_RECENT = 72
KEEP_DAYS = 30

NAME_RE = re.compile(r"^aluma-(\d{8})-(\d{4})\.db$")
TMP_PREFIX = ".aluma-backup-"


class BackupError(Exception):
    """Відмова з коротким кодом причини — без шляхів і даних."""


def backup_name(now: dt.datetime) -> str:
    return now.strftime("aluma-%Y%m%d-%H%M.db")


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {_quote_ident(table)}").fetchone()[0]


def _integrity_ok(conn: sqlite3.Connection) -> bool:
    return conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]


def make_backup(db_path: str, backup_dir: str, leads_table: str, now: dt.datetime) -> tuple:
    """Копія бази в backup_dir; повертає (імʼя файлу, рядків заявок, байтів)."""
    if not os.path.isfile(db_path):
        raise BackupError("no_db")
    os.makedirs(backup_dir, mode=0o700, exist_ok=True)
    os.chmod(backup_dir, 0o700)

    final = os.path.join(backup_dir, backup_name(now))
    tmp = os.path.join(backup_dir, f"{TMP_PREFIX}{os.getpid()}.tmp")
    # Файл створюємо самі з 0600 — sqlite3 відкриє вже наявний і прав не розширить.
    os.close(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600))
    try:
        uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
        src = sqlite3.connect(uri, uri=True, timeout=30.0, isolation_level=None)
        try:
            # Один знімок читання на лічбу й копію: backup() іде в тій самій транзакції.
            src.execute("BEGIN")
            try:
                rows = _count(src, leads_table)
            except sqlite3.OperationalError:
                raise BackupError("no_leads_table") from None
            dst = sqlite3.connect(tmp, isolation_level=None)
            try:
                src.backup(dst)
                src.execute("COMMIT")
                dst.execute("PRAGMA journal_mode=DELETE")
                if not _integrity_ok(dst):
                    raise BackupError("integrity")
                if _count(dst, leads_table) != rows:
                    raise BackupError("rows_mismatch")
            finally:
                dst.close()
        finally:
            src.close()
        os.chmod(tmp, 0o600)
        os.replace(tmp, final)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return os.path.basename(final), rows, os.path.getsize(final)


def _stamp(name: str):
    m = NAME_RE.match(name)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
    except ValueError:
        return None


def select_keep(names, now: dt.datetime, keep_recent: int = KEEP_RECENT,
                keep_days: int = KEEP_DAYS) -> set:
    """Які з наших імен лишити: keep_recent найсвіжіших + найсвіжіша за кожну з keep_days діб."""
    ours = sorted(((s, n) for n in names if (s := _stamp(n)) is not None), reverse=True)
    keep = {n for _, n in ours[:keep_recent]}
    cutoff = (now - dt.timedelta(days=keep_days)).replace(tzinfo=None)
    seen_days = set()
    for stamp, name in ours:
        if stamp < cutoff:
            break
        if stamp.date() not in seen_days:
            seen_days.add(stamp.date())
            keep.add(name)
    return keep


def rotate(backup_dir: str, now: dt.datetime) -> int:
    """Видаляє лише наші файли поза select_keep; повертає, скільки наших лишилось."""
    names = [n for n in os.listdir(backup_dir)
             if _stamp(n) is not None and os.path.isfile(os.path.join(backup_dir, n))]
    keep = select_keep(names, now)
    for name in names:
        if name not in keep:
            os.unlink(os.path.join(backup_dir, name))
    return len(keep)


def run(db_path: str, backup_dir: str, leads_table: str, now: dt.datetime) -> dict:
    try:
        _, rows, size = make_backup(db_path, backup_dir, leads_table, now)
        kept = rotate(backup_dir, now)
    except BackupError as exc:
        return {"event": "backup_failed", "reason": str(exc)}
    except sqlite3.Error as exc:
        return {"event": "backup_failed", "reason": "sqlite_" + type(exc).__name__}
    except OSError as exc:
        return {"event": "backup_failed", "reason": "os_" + (os.strerror(exc.errno) if exc.errno else "error")}
    return {"event": "backup_ok", "rows": rows, "bytes": size, "kept": kept}


def main() -> int:
    # Копія містить імена й телефони: що б не прийшло ззовні, файли — лише для власника.
    os.umask(0o077)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    result = run(FX_DB_PATH, BACKUP_DIR, LEADS_TABLE, now)
    print(json.dumps(result), flush=True)
    return 0 if result["event"] == "backup_ok" else 1


if __name__ == "__main__":
    sys.exit(main())
