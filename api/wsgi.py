"""WSGI-обгортка навколо handler.lambda_handler.

Дзеркало aparts/backend/wsgi_adapter.py, тільки в інший бік: там Flask-застосунок
прикидався лямбдою, тут лямбда прикидається WSGI-застосунком. Форма event —
payload API Gateway v2.0, бо саме її читає handler.py і саме її він отримує в проді.

    gunicorn -w 2 --threads 4 --no-control-socket -b 127.0.0.1:8005 api.wsgi:application

(--no-control-socket обовʼязковий, чому — deploy/systemd/aluma-api.service.)

Що навмисно НЕ робиться: жодної логіки, жодної валідації, жодних заголовків від
себе. Усе, що вміє відповісти, лишається в handler.py — інакше сервер і лямбда
почнуть поводитись по-різному, і саме це ми ловитимемо весь тиждень.
"""

from __future__ import annotations

import base64
import http
import json
from urllib.parse import parse_qsl

try:  # з кореня репозиторію
    from api import handler
except ImportError:  # pragma: no cover - коли коренем є сама тека api/
    import handler


def _path(environ) -> str:
    raw = (environ.get("SCRIPT_NAME", "") + environ.get("PATH_INFO", "")) or "/"
    # PEP 3333 віддає шлях декодованим у latin-1; повертаємо його в utf-8.
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _headers(environ) -> dict:
    headers = {}
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            headers[key[5:].replace("_", "-").lower()] = value
    for key, name in (("CONTENT_TYPE", "content-type"), ("CONTENT_LENGTH", "content-length")):
        if environ.get(key):
            headers[name] = environ[key]
    return headers


def _body(environ) -> str:
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        length = 0
    if length <= 0:
        return ""
    return environ["wsgi.input"].read(length).decode("utf-8", "replace")


def build_event(environ) -> dict:
    """environ → payload API Gateway v2.0."""
    query = environ.get("QUERY_STRING", "") or ""
    params = {}
    for key, value in parse_qsl(query, keep_blank_values=True):
        # API GW v2 склеює повтори комою; беремо ту саму поведінку, щоб адмінка
        # на сервері й на лямбді читала однакове.
        params[key] = f"{params[key]},{value}" if key in params else value
    cookie = environ.get("HTTP_COOKIE", "") or ""
    path = _path(environ)
    method = (environ.get("REQUEST_METHOD") or "GET").upper()
    return {
        "version": "2.0",
        "rawPath": path,
        "rawQueryString": query,
        "queryStringParameters": params,
        "headers": _headers(environ),
        "cookies": [c.strip() for c in cookie.split(";") if c.strip()],
        "body": _body(environ),
        "isBase64Encoded": False,
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
                "sourceIp": environ.get("REMOTE_ADDR", ""),
                "userAgent": environ.get("HTTP_USER_AGENT", ""),
            }
        },
    }


def application(environ, start_response):
    try:
        result = handler.lambda_handler(build_event(environ), None) or {}
    except Exception as exc:  # хендлер має свій except; це остання сітка
        print(json.dumps({"event": "wsgi_unhandled", "error": repr(exc)}))
        result = {"statusCode": 500, "headers": {"content-type": "application/json"},
                  "body": '{"ok": false, "error": "internal"}'}

    body = result.get("body") or ""
    payload = base64.b64decode(body) if result.get("isBase64Encoded") else body.encode("utf-8")

    headers = [(k, str(v)) for k, v in (result.get("headers") or {}).items()]
    # Лямбда віддає печиво окремим списком; у HTTP це просто кілька Set-Cookie.
    headers += [("Set-Cookie", c) for c in (result.get("cookies") or [])]
    headers.append(("Content-Length", str(len(payload))))

    start_response(_status_line(result.get("statusCode", 200)), headers)
    return [payload]


def _status_line(code) -> str:
    code = int(code)
    try:
        return f"{code} {http.HTTPStatus(code).phrase}"
    except ValueError:  # нестандартний код — рядок стану все одно має бути валідним
        return f"{code} Unknown"
