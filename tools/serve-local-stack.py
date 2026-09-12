"""ПОВНИЙ локальний стек ALUMA на ОДНОМУ порту 127.0.0.1 — статика + API в одному процесі.

Навіщо він є. `tools/serve-preview.py` віддає лише статику й на `/api/fx/lead` відповідає
503: заявки там нема куди класти. `tests/smoke.spec.js` натомість ПИШЕ у сховище (заявка
`is_test` через `route.fetch`, `page_view` без `X-Test` на кожен `goto`, події через
`route.continue`), тому проти прода й проти `table-new` його ганяти не можна — CLAUDE.md §6.
Цей файл дає йому те, чого бракує: справжній `api/handler.py` поверх ОДНОРАЗОВОЇ бази.

    PREVIEW_PORT=8007 python3 tools/serve-local-stack.py     # Ctrl-C або kill -TERM <pid>

Що всередині:
  * маршрути `/api/fx/*` і `/admin*` ідуть у `api.wsgi:application` ЦЬОГО Ж процесу —
    той самий код, що під gunicorn у проді (CLAUDE.md §1, «Same code, two runtimes»);
  * решта — статика з `dist/` РІВНО так, як її віддає Caddy (deploy/caddy/aluma-site-body.caddyfile):
    `redir /en /en/ 308`, `try_files {path} {path}/index.html`, сторінки без розширення —
    `text/html; charset=utf-8`, 403/404 → `/404.html` зі статусом 404, ті самі заголовки
    безпеки й Cache-Control, `encode gzip`;
  * база — ОДНОРАЗОВА: тимчасова тека 0700, `FX_STORAGE=sqlite`, знімається разом із процесом.
    У `/opt/ihor/aluma-table/data` і `/srv/aluma` не пишеться нічого;
  * `TELEGRAM_*` НЕ задаються — жодного сповіщення власнику з локального прогону не піде.

Слухає ТІЛЬКИ 127.0.0.1 (`--host` з будь-чим іншим = відмова, код 2). Порт ALUMA — 8007
(`~/maestro/PORTS.md`); 8005 зайнятий бойовим gunicorn, і цей скрипт його не чіпає.
"""
from __future__ import annotations

import argparse
import gzip
import os
import posixpath
import shutil
import signal
import socketserver
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST = ROOT / "dist"

# Ті самі префікси, що в блоці `@app path /api/fx/* /admin*` у Caddy.
API_PREFIXES = ("/api/fx/", "/admin")

# Caddy: encode zstd gzip. zstd ні Playwright, ні Lighthouse не вимагають, gzip досить.
COMPRESSIBLE = {
    "text/html", "text/css", "application/javascript", "text/javascript",
    "application/json", "image/svg+xml", "text/plain", "application/xml", "text/xml",
}

# Caddy: handle { header { … } } — те, що давала керована політика SecurityHeadersPolicy.
SECURITY_HEADERS = (
    ("Strict-Transport-Security", "max-age=31536000"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "SAMEORIGIN"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("X-XSS-Protection", "1; mode=block"),
)

# Типи, які справді трапляються в dist/. Словник прибиває залежність від системного
# /etc/mime.types: збірка має віддаватись однаково на будь-якій машині.
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml",
    ".webmanifest": "application/manifest+json",
    ".map": "application/json",
}


def is_api(path: str) -> bool:
    """Чи йде шлях у застосунок. `/admin*` у Caddy — саме префікс, не лише рівний шлях."""
    return path.startswith(API_PREFIXES)


def content_type(rel: str) -> str:
    """Caddy: @page_noext path_regexp ^[^.]*$ → text/html. Шлях БЕЗ ЖОДНОЇ крапки — сторінка."""
    if "." not in rel:
        return "text/html; charset=utf-8"
    return TYPES.get(posixpath.splitext(rel)[1].lower(), "application/octet-stream")


def cache_control(path: str) -> str:
    """Ті самі три ведра, що в Caddy і в scripts/deploy.sh."""
    if path.startswith("/assets/"):
        return "public, max-age=31536000, immutable"
    if path in ("/robots.txt", "/sitemap.xml"):
        return "public, max-age=3600"
    return "public, max-age=0, must-revalidate"


def resolve(dist: Path, path: str) -> Path | None:
    """try_files {path} {path}/index.html у межах dist/. Вихід за межі теки = None."""
    rel = unquote(path).lstrip("/")
    if "\x00" in rel:
        return None
    root = dist.resolve()
    target = (root / rel).resolve() if rel else root
    if target != root and root not in target.parents:
        return None                      # ../../etc/passwd і подібне
    if target.is_file():
        return target
    index = target / "index.html"
    if index.is_file():
        return index
    return None


def build_application(dist: Path, api_app=None):
    """WSGI-застосунок усього стека. api_app підміняється в тестах — сокети не потрібні."""
    dist = Path(dist)
    if api_app is None:
        from api.wsgi import application as api_app    # env мусить бути вже виставлений

    def application(environ, start_response):
        path = environ.get("PATH_INFO", "") or "/"
        if is_api(path):
            return api_app(environ, start_response)

        # Caddy: redir /en /en/ 308 — у CloudFront цей шлях падав у 404.
        if path == "/en":
            start_response("308 Permanent Redirect",
                           [("Location", "/en/"), ("Content-Length", "0")])
            return [b""]

        target = resolve(dist, path)
        if target is None:
            return _error_page(dist, start_response)

        body = target.read_bytes()
        # Тип — за ЗАПИТАНИМ шляхом, не за знайденим файлом: /privacy має віддатись як
        # сторінка, хоча try_files міг привести до privacy/index.html.
        ctype = content_type(path.rstrip("/") or "index.html")
        headers = [("Content-Type", ctype), ("Cache-Control", cache_control(path))]
        headers += list(SECURITY_HEADERS)

        if ctype.split(";")[0] in COMPRESSIBLE and "gzip" in environ.get("HTTP_ACCEPT_ENCODING", ""):
            body = gzip.compress(body, 6)
            headers += [("Content-Encoding", "gzip"), ("Vary", "Accept-Encoding")]

        headers.append(("Content-Length", str(len(body))))
        start_response("200 OK", headers)
        return [b""] if environ.get("REQUEST_METHOD") == "HEAD" else [body]

    return application


def _error_page(dist: Path, start_response):
    """Caddy: handle_errors 403 404 { rewrite * /404.html; file_server { status 404 } }."""
    page = Path(dist) / "404.html"
    body = page.read_bytes() if page.is_file() else b"404"
    start_response("404 Not Found", [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Cache-Control", "no-store"),
        ("Content-Length", str(len(body))),
    ])
    return [body]


def prepare_environment(db_dir: Path, version: str) -> None:
    """Одноразова база + вигадані секрети. Викликати ДО імпорту api.wsgi: handler читає env
    на імпорті (api/handler.py, module-level UPPER_SNAKE)."""
    os.environ["FX_STORAGE"] = "sqlite"
    os.environ["FX_DB_PATH"] = str(db_dir / "local-stack.db")
    os.environ["APP_VERSION"] = version
    os.environ.setdefault("ADMIN_USER", "local")
    os.environ.setdefault("ADMIN_PASS", "throwaway-local-stack")
    os.environ.setdefault("IP_SALT", "throwaway-local-stack")
    # EDGE_SECRET не задаємо: із ним handler віддав би 403 на КОЖЕН запит, включно з адмінкою.
    # TELEGRAM_* прибираємо з успадкованого середовища: з локального прогону сповіщень нема.
    for leak in ("TELEGRAM_BOT_TOKEN", "OWNER_TELEGRAM_CHAT_ID", "EDGE_SECRET"):
        os.environ.pop(leak, None)


def install_term_handler() -> None:
    """SIGTERM мусить прибирати за собою так само, як Ctrl-C.

    Типовий обробник SIGTERM у Python гасить процес НЕГАЙНО, не розкручуючи стек: блок
    `finally` не виконується, і тимчасова тека з базою лишається лежати в /tmp. А гасять
    цей сервер саме так — `kill -TERM <pid>` (єдиний дозволений спосіб на цій машині:
    ніяких pkill/killall, CLAUDE.md §8). Заміряно: без цих рядків тека переживала процес.
    """
    def _stop(signum, frame):
        raise KeyboardInterrupt                    # той самий шлях виходу, що й Ctrl-C
    signal.signal(signal.SIGTERM, _stop)


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


class ThreadingWSGIServer(socketserver.ThreadingMixIn, WSGIServer):
    """Playwright ганяє кілька воркерів паралельно; однопотоковий сервер їх серіалізує."""

    daemon_threads = True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PREVIEW_PORT", "8007")))
    ap.add_argument("--dist", type=Path, default=DEFAULT_DIST)
    ap.add_argument("--version", default="0.4.0-local")
    args = ap.parse_args(argv)

    if args.host not in ("127.0.0.1", "localhost"):
        print(f"відмова: слухати можна лише 127.0.0.1, а не {args.host!r}", file=sys.stderr)
        return 2
    if not (args.dist / "index.html").is_file():
        print(f"відмова: немає {args.dist}/index.html — спершу python3 build.py", file=sys.stderr)
        return 2

    install_term_handler()
    db_dir = Path(tempfile.mkdtemp(prefix="aluma-local-stack-"))
    db_dir.chmod(0o700)
    prepare_environment(db_dir, args.version)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    try:
        server = make_server("127.0.0.1", args.port, build_application(args.dist),
                             server_class=ThreadingWSGIServer, handler_class=QuietHandler)
        print(f"ALUMA local stack: http://127.0.0.1:{args.port}  (pid {os.getpid()}, "
              f"одноразова база в {db_dir})", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        shutil.rmtree(db_dir, ignore_errors=True)     # одноразова база не переживає процес
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
