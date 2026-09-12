#!/usr/bin/env python3
"""Файл оточення ALUMA для коробки (користувацький юніт) — жоден секрет не друкується.

    python3 scripts/box_env.py --app-version 0.4.0-box --out ~/.config/aluma/aluma.env
    python3 scripts/box_env.py --check ~/.config/aluma/aluma.env
    python3 scripts/box_env.py --check ~/.config/aluma/aluma.env --pid <MainPID>

Звідки що береться (склад — deploy/aluma.env.example):
  ADMIN_USER, ADMIN_PASS, IP_SALT,   — зі змінних живої Lambda fx-table-api. ADMIN_PASS і
  SITE_DOMAIN, WHATSAPP_NUMBER         IP_SALT — НЕЗМІННИМИ: вони підписують куку адмінки
                                       й солять ip_hash (docs/CUTOVER-CHECKLIST.md, 2.2).
  TELEGRAM_BOT_TOKEN,                — зі змінних Lambda aparts-api, як у prod_notify_params.py:
  OWNER_TELEGRAM_CHAT_ID               той самий бот, той самий чат власника.
  FX_STORAGE=sqlite                  — явно (чек-лист 2.3).
  FX_DB_PATH                         — з --db, лише абсолютний шлях.
  APP_VERSION                        — з --app-version, не 0.3.0 (так відповідає прод).
  EDGE_SECRET                        — НЕ переноситься ніколи: без CloudFront він дає 403 на все
                                       (чек-лист 2.1). Є в джерелі — однаково не пишеться.

Значення живуть лише в памʼяті процесу й у файлі 0600, який створюється, тільки якщо його ще
нема; тека файлу — 0700. Ні в stdout, ні в аргументи процесів (/proc без hidepid) вони не
потрапляють: aws-cli віддає JSON у pipe. Друкуються імена ключів і ознака «задано/пусто».

--check FILE — лише імена ключів і «задано/пусто», плюс чи нема EDGE_SECRET.
--check FILE --pid PID — те саме, і для кожного ключа: чи збігається значення з оточенням
живого процесу (/proc/PID/environ). Так видно, що systemd розібрав файл рівно так, як його
записано. Друкується тільки «совпадает/НЕ совпадает».

AWS — тільки читання (get-function-configuration). Повідомлення — російською: їх читає власник.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import stat
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prod_notify_params import (  # noqa: E402  — ті самі форми й та сама обгортка aws
    CHAT_SHAPE, OLD_VERSION, TOKEN_SHAPE, VERSION_SHAPE, Refusal, Runner, aws_cli)

ADMIN_FUNCTION = "fx-table-api"
TELEGRAM_FUNCTION = "aparts-api"
READ_ONLY_CALLS = {("lambda", "get-function-configuration")}
DEFAULT_DB = "/opt/ihor/aluma-table/data/aluma.db"

# ключ -> чи мусить бути непорожнім. Порядок — порядок рядків у файлі.
FROM_ADMIN = {"ADMIN_USER": True, "ADMIN_PASS": True, "IP_SALT": True,
              "SITE_DOMAIN": True, "WHATSAPP_NUMBER": False}
FROM_TELEGRAM = {"TELEGRAM_BOT_TOKEN": TOKEN_SHAPE, "OWNER_TELEGRAM_CHAT_ID": CHAT_SHAPE}
FORBIDDEN = ("EDGE_SECRET",)

# systemd EnvironmentFile розбирає лапки, «\» і пробіли по-своєму. Замість екранування —
# відмова: значення з такими символами треба переносити руками й перевіряти через --pid.
PLAIN = re.compile(r"^[A-Za-z0-9._@:+/=,%-]*$")


def _call(runner: Runner, args: list) -> dict:
    if tuple(args[:2]) not in READ_ONLY_CALLS:
        raise Refusal(f"вызов «aws {' '.join(args[:2])}» не из разрешённых: скрипт только читает")
    return runner(args)


def _lambda_env(runner: Runner, function: str) -> dict:
    cfg = _call(runner, ["lambda", "get-function-configuration", "--function-name", function])
    return (cfg.get("Environment") or {}).get("Variables") or {}


def build(app_version: str, db_path: str, runner: Runner) -> tuple[list[tuple[str, str]], list[str]]:
    """(пари ключ/значення для файлу, рядки звіту без значень)."""
    if not VERSION_SHAPE.match(app_version or ""):
        raise Refusal("--app-version должна выглядеть как 0.4.0-box")
    if app_version == OLD_VERSION:
        raise Refusal("0.3.0 — версия прода: по health будет не отличить коробку от Lambda")
    if not os.path.isabs(db_path):
        raise Refusal("--db должен быть абсолютным путём")

    admin_env = _lambda_env(runner, ADMIN_FUNCTION)
    tg_env = _lambda_env(runner, TELEGRAM_FUNCTION)

    pairs, report = [], []
    for key, required in FROM_ADMIN.items():
        value = str(admin_env.get(key) or "").strip()
        if required and not value:
            raise Refusal(f"у {ADMIN_FUNCTION} переменная {key} пустая или отсутствует")
        pairs.append((key, value))
        report.append(f"{key}: {'задано' if value else 'пусто'} (из {ADMIN_FUNCTION})")
    for key, shape in FROM_TELEGRAM.items():
        value = str(tg_env.get(key) or "").strip()
        if not value:
            raise Refusal(f"у {TELEGRAM_FUNCTION} переменная {key} пустая или отсутствует")
        if not shape.match(value):
            raise Refusal(f"у {TELEGRAM_FUNCTION} переменная {key} не похожа на ожидаемый формат")
        pairs.append((key, value))
        report.append(f"{key}: задано (из {TELEGRAM_FUNCTION})")
    for key, value in (("FX_STORAGE", "sqlite"), ("FX_DB_PATH", db_path), ("APP_VERSION", app_version)):
        pairs.append((key, value))
        report.append(f"{key}: {value}")

    for key, value in pairs:
        if key in FORBIDDEN:  # сторож від майбутньої правки словників вище
            raise Refusal(f"{key} не переносится на коробку")
        if not PLAIN.match(value):
            raise Refusal(f"значение {key} содержит символы, которые systemd разберёт иначе — перенести руками")
    report.append("EDGE_SECRET: не переносится (намеренно)")
    return pairs, report


def render(pairs: list[tuple[str, str]]) -> str:
    head = ("# ALUMA на коробке — ~/.config/aluma/aluma.env, записан scripts/box_env.py.\n"
            "# Состав: deploy/aluma.env.example. EDGE_SECRET нет намеренно. Не печатать.\n")
    return head + "".join(f"{k}={v}\n" for k, v in pairs)


def private_dir(path: pathlib.Path) -> None:
    """Тека файлу: створити 0700 або переконатись, що вона вже закрита від групи й решти."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise Refusal(f"папка {path} открыта группе или всем ({mode:o}) — нужна 0700")


def write_private(path: pathlib.Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def parse(text: str) -> dict:
    """Рівно той формат, що пише render(): KEY=VALUE, коментарі з «#»."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value
    return out


def proc_environ(pid: int) -> dict:
    raw = pathlib.Path(f"/proc/{pid}/environ").read_bytes()
    return dict(item.split("=", 1) for item in raw.decode("utf-8", "replace").split("\0") if "=" in item)


def check(path: pathlib.Path, environ: dict | None, out) -> int:
    mode = stat.S_IMODE(path.stat().st_mode)
    values = parse(path.read_text(encoding="utf-8"))
    bad = 0
    print(f"{path}: права {mode:o}, папка {stat.S_IMODE(path.parent.stat().st_mode):o}", file=out)
    if mode & 0o077:
        print("  ОШИБКА: файл открыт группе или всем — нужна 0600", file=out)
        bad += 1
    for key, value in values.items():
        line = f"  {key}: {'задано' if value else 'пусто'}"
        if environ is not None:
            same = environ.get(key) == value
            line += "; в процессе " + ("совпадает" if same else "НЕ совпадает")
            bad += 0 if same else 1
        print(line, file=out)
    for key in FORBIDDEN:
        if key in values or (environ is not None and key in environ):
            print(f"  ОШИБКА: {key} присутствует — будет 403 на всё", file=out)
            bad += 1
    print("итог: " + ("ок" if not bad else f"ошибок {bad}"), file=out)
    return 0 if not bad else 1


def restrict_umask() -> None:
    """umask не ширший за 027 — правило машини для скриптів, що створюють файли.

    Файл і теку тут і так створено з явними 0600/0700; umask — другий замок.
    """
    os.umask(os.umask(0o027) | 0o027)


def main(argv=None, runner: Runner = aws_cli, out=None) -> int:
    restrict_umask()
    out = out or sys.stdout
    ap = argparse.ArgumentParser(description="Файл окружения ALUMA для коробки, без печати значений.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=pathlib.Path, help="куда записать (файл 0600, папка 0700)")
    mode.add_argument("--check", type=pathlib.Path, help="проверить готовый файл: только имена и «задано/пусто»")
    ap.add_argument("--app-version", help="версия коробки, например 0.4.0-box (не 0.3.0)")
    ap.add_argument("--db", default=DEFAULT_DB, help=f"абсолютный путь к базе, по умолчанию {DEFAULT_DB}")
    ap.add_argument("--pid", type=int, help="с --check: сверить с окружением живого процесса")
    args = ap.parse_args(argv)
    try:
        if args.check:
            environ = proc_environ(args.pid) if args.pid else None
            return check(args.check.expanduser(), environ, out)
        if not args.app_version:
            raise Refusal("нужен --app-version")
        target = args.out.expanduser()
        if target.exists():
            raise Refusal(f"{target} уже существует — не перезаписываю")
        pairs, report = build(args.app_version, args.db, runner)
        private_dir(target.parent)
        write_private(target, render(pairs))
    except FileExistsError:
        print("ОТКАЗ: файл уже существует — не перезаписываю", file=out)
        return 2
    except (Refusal, OSError) as e:
        print(f"ОТКАЗ: {e}", file=out)
        return 2
    for line in report:
        print("  " + line, file=out)
    print(f"записано: {target} (права 0600)", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
