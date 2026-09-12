#!/usr/bin/env python3
"""Файл параметрів для викату бекенду master на стек fx-table — жоден секрет не друкується.

    python3 scripts/prod_notify_params.py --app-version 0.4.0 --out /tmp/aluma-deploy/params.json

Результат — JSON для
    aws cloudformation create-change-set ... --parameters file://<out>

Звідки що береться:
  AppVersion              — з --app-version. Не 0.3.0: це версія, що зараз у проді,
                            і health після викату нічого б не показав.
  TelegramBotToken,       — зі змінних TELEGRAM_BOT_TOKEN і OWNER_TELEGRAM_CHAT_ID
  OwnerTelegramChatId       Lambda aparts-api: той самий бот, той самий чат власника.
  усе інше, що вже є      — UsePreviousValue=true. AdminPass, IpSalt, EdgeSecret,
  в стеку                   CertificateArn… лишаються рівно такими, як є: кука адмінки
                            не злітає, хеші IP не міняються, origin і далі закритий.

Друкуються лише імена параметрів і спосіб («новое значение» / «как было»); значення —
ніколи, крім AppVersion. Токен і chat id живуть у пам'яті процесу і у файлі з правами
0600, який створюється, лише якщо його ще нема. Після create-change-set файл знищити:
    shred -u <out>

Бо чому не `sam deploy --parameter-overrides TelegramBotToken=$TOKEN`: аргументи процесу
на цій машині видно всім користувачам (/proc без hidepid), а OwnerTelegramChatId SAM
друкує відкритим текстом у «Deploying with following values».

AWS — тільки читання: describe-stacks (імена параметрів) і get-function-configuration.
Повідомлення — російською: їх читає власник.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra" / "template.yaml"
STACK = "fx-table"
SOURCE_FUNCTION = "aparts-api"
REGION = "eu-central-1"
OLD_VERSION = "0.3.0"

# параметр шаблону -> змінна оточення aparts-api
FROM_APARTS = {
    "TelegramBotToken": "TELEGRAM_BOT_TOKEN",
    "OwnerTelegramChatId": "OWNER_TELEGRAM_CHAT_ID",
}
# ці три мусять лишитись рівно такими, як є; якщо скрипт не може цього гарантувати — відмова
MUST_KEEP = ("AdminPass", "IpSalt", "EdgeSecret")
READ_ONLY_CALLS = {("cloudformation", "describe-stacks"), ("lambda", "get-function-configuration")}

TOKEN_SHAPE = re.compile(r"^[0-9]{5,}:[A-Za-z0-9_-]{30,}$")
CHAT_SHAPE = re.compile(r"^-?[0-9]{3,}$")
VERSION_SHAPE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+[0-9A-Za-z.+-]*$")

Runner = Callable[[list], dict]


class Refusal(Exception):
    """Причина не писати файл. Текст ніколи не містить значень."""


def aws_cli(args: list) -> dict:
    try:
        done = subprocess.run(["aws", *args, "--region", REGION, "--output", "json"],
                              check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise Refusal(f"aws {' '.join(args[:2])} не выполнился (код {getattr(e, 'returncode', '?')}). "
                      "Проверьте доступ: aws sts get-caller-identity")
    return json.loads(done.stdout)


def _call(runner: Runner, args: list) -> dict:
    if tuple(args[:2]) not in READ_ONLY_CALLS:
        raise Refusal(f"вызов «aws {' '.join(args[:2])}» не из разрешённых: скрипт только читает")
    return runner(args)


def template_parameters(text: str) -> list[str]:
    """Імена параметрів верхнього рівня з infra/template.yaml — без PyYAML."""
    m = re.search(r"^Parameters:[ \t]*\n(.*?)(?=^\S)", text, re.S | re.M)
    if not m:
        raise Refusal("в шаблоне не найден раздел Parameters")
    return re.findall(r"^  ([A-Za-z0-9]+):[ \t]*$", m.group(1), re.M)


def build(app_version: str, template_text: str, runner: Runner) -> tuple[list[dict], list[str]]:
    """(Parameters для CloudFormation, рядки звіту без значень)."""
    if not VERSION_SHAPE.match(app_version or ""):
        raise Refusal("--app-version должна выглядеть как 0.4.0")
    if app_version == OLD_VERSION:
        raise Refusal("0.3.0 — версия, которая сейчас в проде: после выката health не покажет разницы")

    wanted = template_parameters(template_text)
    stack = _call(runner, ["cloudformation", "describe-stacks", "--stack-name", STACK])
    existing = {p["ParameterKey"] for p in stack["Stacks"][0].get("Parameters") or []}
    cfg = _call(runner, ["lambda", "get-function-configuration", "--function-name", SOURCE_FUNCTION])
    env = (cfg.get("Environment") or {}).get("Variables") or {}

    params, report = [], []
    for key in wanted:
        if key == "AppVersion":
            params.append({"ParameterKey": key, "ParameterValue": app_version})
            report.append(f"{key}: {app_version}")
        elif key in FROM_APARTS:
            var = FROM_APARTS[key]
            value = str(env.get(var) or "").strip()
            shape = TOKEN_SHAPE if key == "TelegramBotToken" else CHAT_SHAPE
            if not value:
                raise Refusal(f"у {SOURCE_FUNCTION} переменная {var} пустая или отсутствует")
            if not shape.match(value):
                raise Refusal(f"у {SOURCE_FUNCTION} переменная {var} не похожа на ожидаемый формат")
            params.append({"ParameterKey": key, "ParameterValue": value})
            report.append(f"{key}: новое значение из {SOURCE_FUNCTION} ({var}), не печатается")
        elif key in existing:
            params.append({"ParameterKey": key, "UsePreviousValue": True})
            report.append(f"{key}: как было (UsePreviousValue)")
        else:
            raise Refusal(f"параметр {key} новый в шаблоне, а откуда взять значение, скрипт не знает")

    for key in MUST_KEEP:
        if not any(p["ParameterKey"] == key and p.get("UsePreviousValue") for p in params):
            raise Refusal(f"{key} должен остаться прежним, а так не получается — остановка")
    dropped = sorted(existing - set(wanted))
    if dropped:
        report.append("исчезнут из стека (их больше нет в шаблоне): " + ", ".join(dropped))
    return params, report


def write_private(path: pathlib.Path, params: list[dict]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main(argv=None, runner: Runner = aws_cli, out=None) -> int:
    out = out or sys.stdout
    ap = argparse.ArgumentParser(description="Параметры для выката бекенда master на fx-table.")
    ap.add_argument("--app-version", required=True, help="новая версия, например 0.4.0 (не 0.3.0)")
    ap.add_argument("--out", required=True, type=pathlib.Path, help="куда записать JSON (права 0600)")
    ap.add_argument("--template", type=pathlib.Path, default=TEMPLATE, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        if args.out.exists():
            raise Refusal(f"{args.out} уже существует — не перезаписываю (shred -u и заново)")
        params, report = build(args.app_version, args.template.read_text(encoding="utf-8"), runner)
        write_private(args.out, params)
    except FileExistsError:
        print(f"ОТКАЗ: {args.out} уже существует — не перезаписываю", file=out)
        return 2
    except Refusal as e:
        print(f"ОТКАЗ: {e}", file=out)
        return 2
    for line in report:
        print("  " + line, file=out)
    print(f"записано: {args.out} (права 0600). После create-change-set: shred -u {args.out}", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
