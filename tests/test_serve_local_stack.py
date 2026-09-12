"""tools/serve-local-stack.py — без сокетів: WSGI-застосунок викликається напряму.

Головне, що тут доводиться, — що статика поводиться ЯК CADDY
(deploy/caddy/aluma-site-body.caddyfile), бо саме на цьому припущенні тримається
`tests/smoke.spec.js`: чисті URL, 404 замість підміни лендингом, редирект /en → /en/.
І що маршрутизація не мажеться: `/api/fx/*` і `/admin*` не мають шансу впасти в статику.

    python -m unittest tests.test_serve_local_stack -v
"""

from __future__ import annotations

import gzip
import importlib.util
import io
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load():
    """Імʼя файлу з дефісом як решта tools/ — імпортувати можна лише через loader."""
    path = ROOT / "tools" / "serve-local-stack.py"
    spec = importlib.util.spec_from_file_location("serve_local_stack", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


s = _load()


def call(app, path, method="GET", accept_encoding="", **extra):
    """Один запит до WSGI-застосунку. Повертає (статус, заголовки-словник, тіло)."""
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "SERVER_NAME": "127.0.0.1",
        "SERVER_PORT": "8007",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.input": io.BytesIO(b""),
        "wsgi.errors": io.BytesIO(),
        "wsgi.url_scheme": "http",
    }
    if accept_encoding:
        environ["HTTP_ACCEPT_ENCODING"] = accept_encoding
    environ.update(extra)
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(app(environ, start_response))
    return captured["status"], dict(captured["headers"]), body


def echo_api(environ, start_response):
    """Заглушка застосунку: віддає шлях, щоб тест бачив, ЩО саме туди доїхало."""
    body = environ["PATH_INFO"].encode()
    start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))])
    return [body]


class DistCase(unittest.TestCase):
    """Мініатюрний dist/ тієї ж форми, що дає build.py: сторінки з розширенням і без,
    en/index.html, 404.html, хешований ассет."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._tmp = tempfile.TemporaryDirectory()
        # dist/ лежить УСЕРЕДИНІ тимчасової теки, а поруч із ним — файл, якого гість
        # бачити не повинен. Без цього сусіда тест на вихід за межі теки нічого не
        # доводить: підніматися було б нікуди.
        cls.outside = pathlib.Path(cls._tmp.name) / "secret-outside-dist.txt"
        cls.outside.write_text("ЦЕ НЕ МАЄ ПОТРАПИТИ В ВІДПОВІДЬ", encoding="utf-8")
        cls.dist = pathlib.Path(cls._tmp.name) / "dist"
        cls.dist.mkdir()
        (cls.dist / "index.html").write_text("<html>he</html>", encoding="utf-8")
        (cls.dist / "404.html").write_text("<html>not found</html>", encoding="utf-8")
        (cls.dist / "privacy.html").write_text("<html>privacy</html>", encoding="utf-8")
        (cls.dist / "privacy").write_text("<html>privacy</html>", encoding="utf-8")
        (cls.dist / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
        (cls.dist / "en").mkdir()
        (cls.dist / "en" / "index.html").write_text("<html>en</html>", encoding="utf-8")
        assets = cls.dist / "assets"
        assets.mkdir()
        (assets / "app.0123456789.js").write_text("console.log(1)\n" * 200, encoding="utf-8")
        (assets / "hero.0123456789.webp").write_bytes(b"\x00RIFF-not-really")
        # staticmethod: інакше WSGI-функція стане методом і дістане зайвий self
        cls.app = staticmethod(s.build_application(cls.dist, api_app=echo_api))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


class TestRouting(DistCase):
    def test_api_and_admin_prefixes_reach_the_application(self):
        for path in ("/api/fx/health", "/api/fx/lead", "/admin", "/admin/login",
                     "/admin/status", "/admin?range=7"):
            status, _, body = call(self.app, path)
            self.assertEqual(status, "200 OK", path)
            self.assertEqual(body.decode(), path, f"{path} не доїхав у застосунок")

    def test_static_paths_do_not_reach_the_application(self):
        for path in ("/", "/en/", "/privacy", "/assets/app.0123456789.js", "/robots.txt"):
            status, _, body = call(self.app, path)
            self.assertNotEqual(body.decode("utf-8", "replace"), path,
                                f"{path} помилково пішов у застосунок замість статики")
            self.assertIn(status, ("200 OK", "404 Not Found"), path)

    def test_admin_prefix_is_a_prefix_like_in_caddy(self):
        # `/admin*` у Caddy — саме префікс: /administration теж піде в застосунок.
        # Тест фіксує НАЯВНУ поведінку фронту, щоб локальний стек і прод не розійшлися.
        _, _, body = call(self.app, "/administration")
        self.assertEqual(body.decode(), "/administration")

    def test_is_api_matches_the_caddy_matcher(self):
        for path in ("/api/fx/health", "/admin", "/admin/login"):
            self.assertTrue(s.is_api(path), path)
        for path in ("/", "/en/", "/privacy", "/api/other", "/assets/app.js"):
            self.assertFalse(s.is_api(path), path)


class TestStaticLikeCaddy(DistCase):
    def test_clean_urls_serve_html(self):
        status, headers, body = call(self.app, "/privacy")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(body, b"<html>privacy</html>")

    def test_directory_falls_back_to_index_html(self):
        status, headers, body = call(self.app, "/en/")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body, b"<html>en</html>")
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")

    def test_en_without_slash_redirects_308(self):
        status, headers, _ = call(self.app, "/en")
        self.assertEqual(status, "308 Permanent Redirect")
        self.assertEqual(headers["Location"], "/en/")

    def test_missing_page_is_404_with_the_site_page_not_the_landing(self):
        status, headers, body = call(self.app, "/no-such-page-xyz")
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(body, b"<html>not found</html>")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn(b"he</html>", body)

    def test_traversal_outside_dist_is_404_not_a_file(self):
        name = self.outside.name
        for path in (f"/../{name}", f"/..%2f{name}", f"/assets/../../{name}",
                     f"/en/../../{name}"):
            status, _, body = call(self.app, path)
            self.assertEqual(status, "404 Not Found", path)
            self.assertNotIn("НЕ МАЄ ПОТРАПИТИ".encode(), body, f"{path} віддав файл поза dist/")

    def test_cache_control_buckets(self):
        _, headers, _ = call(self.app, "/assets/app.0123456789.js")
        self.assertEqual(headers["Cache-Control"], "public, max-age=31536000, immutable")
        _, headers, _ = call(self.app, "/robots.txt")
        self.assertEqual(headers["Cache-Control"], "public, max-age=3600")
        _, headers, _ = call(self.app, "/")
        self.assertEqual(headers["Cache-Control"], "public, max-age=0, must-revalidate")

    def test_security_headers_on_static(self):
        _, headers, _ = call(self.app, "/")
        for name, value in s.SECURITY_HEADERS:
            self.assertEqual(headers[name], value)

    def test_gzip_only_when_asked_and_only_for_text(self):
        _, headers, body = call(self.app, "/assets/app.0123456789.js", accept_encoding="gzip")
        self.assertEqual(headers["Content-Encoding"], "gzip")
        self.assertEqual(headers["Vary"], "Accept-Encoding")
        self.assertIn(b"console.log(1)", gzip.decompress(body))
        self.assertEqual(int(headers["Content-Length"]), len(body))

        _, headers, _ = call(self.app, "/assets/app.0123456789.js")
        self.assertNotIn("Content-Encoding", headers)

        # картинка вже стиснута — gzip поверх неї Caddy теж не кладе
        _, headers, _ = call(self.app, "/assets/hero.0123456789.webp", accept_encoding="gzip")
        self.assertNotIn("Content-Encoding", headers)

    def test_head_sends_headers_without_a_body(self):
        status, headers, body = call(self.app, "/", method="HEAD")
        self.assertEqual(status, "200 OK")
        self.assertEqual(body, b"")
        self.assertEqual(int(headers["Content-Length"]), len(b"<html>he</html>"))


class TestContentType(unittest.TestCase):
    def test_extensionless_path_is_html(self):
        for path in ("/privacy", "/en/terms", "/next", "/"):
            self.assertEqual(s.content_type(path.rstrip("/") or "index.html"),
                             "text/html; charset=utf-8", path)

    def test_known_extensions(self):
        self.assertEqual(s.content_type("/assets/a.css"), "text/css; charset=utf-8")
        self.assertEqual(s.content_type("/assets/a.js"), "text/javascript; charset=utf-8")
        self.assertEqual(s.content_type("/assets/a.webp"), "image/webp")
        self.assertEqual(s.content_type("/assets/a.woff2"), "font/woff2")

    def test_unknown_extension_is_not_guessed_as_html(self):
        self.assertEqual(s.content_type("/assets/a.bin"), "application/octet-stream")


class TestRefusesForeignHost(unittest.TestCase):
    """Правило машини: слухати тільки 127.0.0.1. Це не порада, а вихід 2."""

    def setUp(self):
        self.err = io.StringIO()

    def _run(self, argv):
        old, sys.stderr = sys.stderr, self.err
        try:
            return s.main(argv)
        finally:
            sys.stderr = old

    def test_public_interfaces_are_refused(self):
        for host in ("0.0.0.0", "::", "95.216.10.169", "localhost.evil.example"):
            self.err = io.StringIO()
            self.assertEqual(self._run(["--host", host, "--port", "8007"]), 2, host)
            self.assertIn("127.0.0.1", self.err.getvalue())

    def test_missing_build_is_refused_before_any_socket(self):
        code = self._run(["--dist", "/nonexistent-dist-xyz", "--port", "8007"])
        self.assertEqual(code, 2)
        self.assertIn("build.py", self.err.getvalue())


class TestEnvironment(unittest.TestCase):
    """Одноразова база й відсутність сповіщень — не «мабуть», а перевірено."""

    def setUp(self):
        self.saved = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)

    def test_throwaway_db_and_no_telegram(self):
        import tempfile
        os.environ["TELEGRAM_BOT_TOKEN"] = "must-be-dropped"
        os.environ["OWNER_TELEGRAM_CHAT_ID"] = "must-be-dropped"
        os.environ["EDGE_SECRET"] = "must-be-dropped"
        with tempfile.TemporaryDirectory() as tmp:
            s.prepare_environment(pathlib.Path(tmp), "0.4.0-local")
            self.assertEqual(os.environ["FX_STORAGE"], "sqlite")
            self.assertTrue(os.environ["FX_DB_PATH"].startswith(tmp))
            self.assertEqual(os.environ["APP_VERSION"], "0.4.0-local")
            self.assertTrue(os.environ["ADMIN_PASS"])
            self.assertTrue(os.environ["IP_SALT"])
        for leak in ("TELEGRAM_BOT_TOKEN", "OWNER_TELEGRAM_CHAT_ID", "EDGE_SECRET"):
            self.assertNotIn(leak, os.environ, f"{leak} лишився — прогін торкнеться зовнішнього світу")

    def test_db_never_lands_in_the_repo_or_srv(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            s.prepare_environment(pathlib.Path(tmp), "0.4.0-local")
            db = pathlib.Path(os.environ["FX_DB_PATH"]).resolve()
        self.assertFalse(str(db).startswith(str(ROOT)), db)
        self.assertFalse(str(db).startswith("/srv/"), db)


# Найважливіше, що треба довести про цей стек: у ньому стоїть СПРАВЖНІЙ api/handler.py,
# а не заглушка, і заявка справді лягає в одноразову базу. Перевірка йде в ОКРЕМОМУ
# процесі, і на це є дві причини:
#   1. handler читає env на імпорті (module-level UPPER_SNAKE), а в спільному прогоні
#      api.handler уже імпортований іншими тестами з іншим APP_VERSION. `del sys.modules`
#      тут не рятує: `from api import handler` віддасть атрибут пакета `api`, не
#      перечитавши модуль, — саме на цьому перша редакція тесту й зеленіла хибно;
#      reload же лишив би решті тестів handler, прив'язаний до вже видаленої тимчасової бази.
#   2. підпроцес доводить те, чого не доводить жоден виклик у пам'яті: що стек піднімається
#      з ЧИСТОГО середовища, як його піднімає Playwright.
# Мережі й сокетів тут все одно немає: WSGI-застосунок викликається напряму.
_CHILD = r'''
import io, json, os, pathlib, shutil, sys, tempfile, importlib.util
ROOT = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("sls", ROOT / "tools" / "serve-local-stack.py")
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

tmp = pathlib.Path(tempfile.mkdtemp())
s.prepare_environment(tmp, "0.4.0-local")
app = s.build_application(ROOT / "dist")

def call(path, method="GET", body=b"", **extra):
    env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "",
           "SERVER_NAME": "127.0.0.1", "SERVER_PORT": "8007", "SERVER_PROTOCOL": "HTTP/1.1",
           "wsgi.input": io.BytesIO(body), "wsgi.errors": io.BytesIO(), "wsgi.url_scheme": "http"}
    env.update(extra)
    got = {}
    out = b"".join(app(env, lambda st, hd: got.update(status=st, headers=hd)))
    return got["status"], out

out = {}
st, body = call("/api/fx/health")
out["health_status"] = st
out["version"] = json.loads(body).get("version")

payload = json.dumps({"name": "בדיקה", "phone": "0501234567", "consent": True}).encode()
st, body = call("/api/fx/lead", "POST", payload, HTTP_X_TEST="1",
                CONTENT_TYPE="application/json", CONTENT_LENGTH=str(len(payload)))
out["lead_status"] = st
out["lead_ok"] = json.loads(body).get("ok")
out["db_written"] = pathlib.Path(os.environ["FX_DB_PATH"]).is_file()
out["db_outside_repo"] = not str(pathlib.Path(os.environ["FX_DB_PATH"]).resolve()).startswith(str(ROOT))
print("RESULT" + json.dumps(out))
shutil.rmtree(tmp, ignore_errors=True)   # не лишати одноразову базу в /tmp після прогону
'''


class TestRealApiIsWired(unittest.TestCase):
    def test_health_and_lead_round_trip(self):
        import json
        import subprocess
        if not (ROOT / "dist" / "index.html").is_file():
            self.skipTest("немає dist/ — спершу python3 build.py")
        proc = subprocess.run([sys.executable, "-c", _CHILD, str(ROOT)],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT"))
        got = json.loads(line[len("RESULT"):])
        self.assertEqual(got["health_status"], "200 OK")
        self.assertEqual(got["version"], "0.4.0-local", "health віддає не ту версію — env не доїхав")
        self.assertEqual(got["lead_status"], "200 OK")
        self.assertTrue(got["lead_ok"])
        self.assertTrue(got["db_written"], "заявку прийнято, але база не зʼявилась")
        self.assertTrue(got["db_outside_repo"], "база лягла в репозиторій")
        # Сповіщення не пішло: TELEGRAM_* знято, тому notify() навіть не пробує мережу.
        self.assertNotIn("notify_failed", proc.stdout)


class TestSigtermCleansUp(unittest.TestCase):
    """Прибирання за собою — по SIGTERM, а не лише по Ctrl-C.

    Це єдиний тест у файлі, який справді відкриває сокет, і причина рівно та: довести
    прибирання можна тільки на живому процесі, який справді вбили. Слухає 127.0.0.1 і
    порт бере у ядра (0 = вільний), щоб не зайняти 8007 у паралельного прогону Playwright.
    Перша редакція скрипта цей тест НЕ проходила: типовий обробник SIGTERM гасив процес
    повз `finally`, і тимчасова тека з базою лишалась у /tmp.
    """

    def test_temp_db_dir_is_removed_on_sigterm(self):
        import re
        import signal
        import subprocess
        import time
        if not (ROOT / "dist" / "index.html").is_file():
            self.skipTest("немає dist/ — спершу python3 build.py")

        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "tools" / "serve-local-stack.py"), "--port", "0"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(ROOT))
        try:
            line = proc.stdout.readline()
            match = re.search(r"одноразова база в ([^\s)]+)", line)   # рядок закінчується дужкою
            self.assertIsNotNone(match, f"сервер не назвав теку бази: {line!r}")
            db_dir = pathlib.Path(match.group(1))
            self.assertTrue(db_dir.is_dir(), "теки бази немає ще до зупинки")
            self.assertEqual(db_dir.stat().st_mode & 0o777, 0o700, "тека бази не 0700")

            proc.send_signal(signal.SIGTERM)
            self.assertEqual(proc.wait(timeout=30), 0, "сервер не вийшов чисто по SIGTERM")
            for _ in range(50):                       # прибирання — остання дія процесу
                if not db_dir.exists():
                    break
                time.sleep(0.1)
            self.assertFalse(db_dir.exists(),
                             f"{db_dir} пережила процес — одноразова база лишилась у /tmp")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
