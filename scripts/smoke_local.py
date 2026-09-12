#!/usr/bin/env python3
"""Смок ЛОКАЛЬНОГО стека ALUMA (gunicorn на 127.0.0.1:8005) — одна команда замість памʼяті.

    python3 scripts/smoke_local.py                          # http://127.0.0.1:8005
    python3 scripts/smoke_local.py http://localhost:8005

Чотири перевірки, ті самі, що вночі робилися руками (deploy/README.md,
«Що перевірено руками»):

  1. GET  /api/fx/health    -> 200, ok=true, version непорожня і НЕ 0.3.0
                               (0.3.0 віддає стара Lambda — інакше не зрозуміти,
                               який стек відповів);
  2. GET  /__smoke_nope__   -> 404;
  3. GET  /admin без куки   -> 303 (редиректів НЕ слідуємо);
  4. POST /api/fx/lead      -> 200 і id заявки; заголовок x-test: 1, дані фіктивні.

Код виходу: 0 — усе зелене, 1 — хоч одна червона, 2 — відмова працювати.

ЗАХИСТ. Скрипт ПИШЕ заявку, тому працює тільки з 127.0.0.1 / localhost.
Будь-який інший хост — відмова з кодом 2 ще до першого запиту. Прапорця
«дозволити віддалений» нема і не буде: жодної заявки в прод, навіть тестової.

Лише стандартна бібліотека. Тіла відповідей не друкуються (адмінка — теж):
тільки статус, версія й id заявки.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, NamedTuple

DEFAULT_BASE = "http://127.0.0.1:8005"
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})
LAMBDA_VERSION = "0.3.0"
TIMEOUT = 10

# Явно фіктивна заявка. Телефон синтаксично валідний (5 + 8 цифр після 0),
# але з самих нулів — ні в кого такого нема.
TEST_LEAD = {
    "name": "SMOKE TEST (fake)",
    "phone": "050-000-0000",
    "consent": True,
    "comment": "scripts/smoke_local.py — automated smoke, not a real lead",
    "page": "/smoke-local",
}


class Response(NamedTuple):
    status: int
    headers: dict
    body: bytes


# transport(method, url, headers, body) -> Response. У тестах підміняється.
Transport = Callable[[str, str, dict, "bytes | None"], Response]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 3xx повертається як є, через HTTPError


_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),  # http_proxy з оточення не має права увести localhost кудись
    _NoRedirect(),
)


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None) -> Response:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=TIMEOUT) as r:
            return Response(r.status, dict(r.headers), r.read())
    except urllib.error.HTTPError as e:
        return Response(e.code, dict(e.headers or {}), e.read() or b"")


def host_refusal(base: str) -> str | None:
    """Причина відмови або None, якщо з цим адресом працювати можна."""
    try:
        u = urllib.parse.urlsplit(base)
        host = (u.hostname or "").lower()
        u.port  # noqa: B018 — кривий порт кидає ValueError
    except ValueError as e:
        return f"не розібрати адресу {base!r}: {e}"
    if u.scheme not in ("http", "https"):
        return f"схема {u.scheme!r} не підтримується, треба http://"
    if host not in ALLOWED_HOSTS:
        return (f"хост {host or '(порожній)'!r} не локальний. Смок пише заявку, тому працює "
                f"ТІЛЬКИ з {', '.join(sorted(ALLOWED_HOSTS))}. Віддалений прогін не передбачено.")
    return None


def _json(r: Response):
    try:
        return json.loads(r.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def check_health(base: str, transport: Transport) -> tuple[bool, str]:
    r = transport("GET", base + "/api/fx/health", {}, None)
    if r.status != 200:
        return False, f"status {r.status}, треба 200"
    data = _json(r)
    if not isinstance(data, dict):
        return False, "тіло не JSON-обʼєкт"
    if data.get("ok") is not True:
        return False, f"ok={data.get('ok')!r}, треба true"
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        return False, "version порожня"
    if version.strip() == LAMBDA_VERSION:
        return False, f"version={version} — це стара Lambda, не новий стек"
    return True, f"200, version={version}"


def check_not_found(base: str, transport: Transport) -> tuple[bool, str]:
    r = transport("GET", base + "/__smoke_nope__", {}, None)
    if r.status != 404:
        return False, f"status {r.status}, треба 404"
    return True, "404"


def check_admin_redirect(base: str, transport: Transport) -> tuple[bool, str]:
    r = transport("GET", base + "/admin", {}, None)
    if r.status != 303:
        return False, f"status {r.status}, треба 303 (без куки адмінка має відсилати на вхід)"
    return True, "303"


def check_lead(base: str, transport: Transport) -> tuple[bool, str]:
    body = json.dumps(TEST_LEAD).encode("utf-8")
    headers = {"content-type": "application/json", "x-test": "1"}
    r = transport("POST", base + "/api/fx/lead", headers, body)
    if r.status != 200:
        return False, f"status {r.status}, треба 200"
    data = _json(r)
    if not isinstance(data, dict) or data.get("ok") is not True:
        return False, "у відповіді нема ok=true"
    lead_id = data.get("id")
    # "hp" — відповідь ханіпота: 200 без запису. Це не заявка.
    if not isinstance(lead_id, str) or not lead_id.strip() or lead_id == "hp":
        return False, "у відповіді нема id заявки"
    return True, f"200, id={lead_id}"


CHECKS = [
    ("GET /api/fx/health", check_health),
    ("GET /__smoke_nope__ -> 404", check_not_found),
    ("GET /admin без куки -> 303", check_admin_redirect),
    ("POST /api/fx/lead (x-test)", check_lead),
]


def run(base: str, transport: Transport = urllib_transport, out=None) -> int:
    out = out or sys.stdout
    base = base.rstrip("/")
    refusal = host_refusal(base)
    if refusal:
        print(f"ВІДМОВА: {refusal}", file=out)
        return 2
    print(f"smoke {base}", file=out)
    failed = 0
    for title, check in CHECKS:
        try:
            ok, reason = check(base, transport)
        except Exception as e:  # недоступний порт, таймаут — це FAIL, а не traceback
            ok, reason = False, f"{type(e).__name__}: {e}"
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {title}: {reason}", file=out)
    print(f"{len(CHECKS) - failed}/{len(CHECKS)} зелених", file=out)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Смок локального стека ALUMA (тільки localhost).")
    p.add_argument("base", nargs="?", default=DEFAULT_BASE, help=f"базова адреса, типово {DEFAULT_BASE}")
    return run(p.parse_args(argv).base)


if __name__ == "__main__":
    sys.exit(main())
