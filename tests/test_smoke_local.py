"""scripts/smoke_local.py — без сокетів і без мережі: транспорт підміняється.

Головне тут — червоні випадки. Смок, який зеленіє на поганих відповідях, —
декорація, тому кожна перевірка має тест, де вона ПАДАЄ.

    python -m unittest tests.test_smoke_local -v
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import smoke_local as s  # noqa: E402

BASE = "http://127.0.0.1:8005"


def _j(status, obj, headers=None):
    return s.Response(status, headers or {"Content-Type": "application/json"},
                      json.dumps(obj).encode("utf-8"))


def good_routes():
    return {
        ("GET", "/api/fx/health"): _j(200, {"ok": True, "version": "0.4.0-smoke", "ts": "x"}),
        ("GET", "/__smoke_nope__"): _j(404, {"ok": False, "error": "not found"}),
        ("GET", "/admin"): s.Response(303, {"Location": "/admin/login"}, b""),
        ("POST", "/api/fx/lead"): _j(200, {"ok": True, "id": "0123456789ab"}),
    }


class FakeTransport:
    """Віддає заготовлені відповіді й записує кожен запит."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        path = url[len(BASE):] if url.startswith(BASE) else url
        route = self.routes[(method, path)]
        if isinstance(route, Exception):
            raise route
        return route


def run(routes, base=BASE):
    t = FakeTransport(routes)
    out = io.StringIO()
    code = s.run(base, transport=t, out=out)
    return code, out.getvalue(), t


class AllGreen(unittest.TestCase):
    def test_good_stack_exits_0(self):
        code, out, t = run(good_routes())
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("PASS"), 4, out)
        self.assertNotIn("FAIL", out)
        self.assertIn("version=0.4.0-smoke", out)
        self.assertEqual(len(t.calls), 4)

    def test_trailing_slash_in_base(self):
        code, out, _ = run(good_routes(), base=BASE + "/")
        self.assertEqual(code, 0, out)

    def test_lead_request_is_marked_test_and_valid(self):
        _, _, t = run(good_routes())
        method, url, headers, body = [c for c in t.calls if c[0] == "POST"][0]
        self.assertEqual(url, BASE + "/api/fx/lead")
        self.assertEqual(headers.get("x-test"), "1")
        data = json.loads(body)
        self.assertIs(data["consent"], True)
        self.assertGreaterEqual(len(data["name"]), 2)
        self.assertNotIn("website", data)  # інакше спрацює ханіпот і нічого не запишеться

    def test_lead_body_passes_real_handler_validation(self):
        # Тіло має пройти справжні правила handler.py, а не наше уявлення про них.
        import tests.test_handler  # noqa: F401 — ставить фейковий boto3, якщо SDK нема
        import api.handler as h
        _, plausible = h.normalize_phone(s.TEST_LEAD["phone"])
        self.assertTrue(plausible)

    def test_admin_body_never_printed(self):
        routes = good_routes()
        routes[("GET", "/admin")] = s.Response(303, {"Location": "/admin/login"}, b"SECRET-ADMIN-HTML")
        _, out, _ = run(routes)
        self.assertNotIn("SECRET-ADMIN-HTML", out)


class RedCases(unittest.TestCase):
    def assertRed(self, routes, needle):
        code, out, _ = run(routes)
        self.assertEqual(code, 1, out)
        fail_lines = [l for l in out.splitlines() if l.startswith("FAIL")]
        self.assertEqual(len(fail_lines), 1, out)
        self.assertIn(needle, fail_lines[0])
        return out

    def test_lambda_version_is_red(self):
        r = good_routes()
        r[("GET", "/api/fx/health")] = _j(200, {"ok": True, "version": "0.3.0"})
        self.assertRed(r, "health")

    def test_empty_version_is_red(self):
        for v in ("", "   ", None):
            with self.subTest(version=v):
                r = good_routes()
                r[("GET", "/api/fx/health")] = _j(200, {"ok": True, "version": v})
                self.assertRed(r, "health")

    def test_missing_version_is_red(self):
        r = good_routes()
        r[("GET", "/api/fx/health")] = _j(200, {"ok": True})
        self.assertRed(r, "health")

    def test_health_not_ok_is_red(self):
        r = good_routes()
        r[("GET", "/api/fx/health")] = _j(200, {"ok": False, "version": "0.4.0"})
        self.assertRed(r, "health")

    def test_health_500_is_red(self):
        r = good_routes()
        r[("GET", "/api/fx/health")] = _j(500, {"ok": False})
        self.assertRed(r, "health")

    def test_health_not_json_is_red(self):
        r = good_routes()
        r[("GET", "/api/fx/health")] = s.Response(200, {}, b"<html>")
        self.assertRed(r, "health")

    def test_unknown_path_200_is_red(self):
        r = good_routes()
        r[("GET", "/__smoke_nope__")] = _j(200, {"ok": True})
        self.assertRed(r, "404")

    def test_admin_200_is_red(self):
        r = good_routes()
        r[("GET", "/admin")] = s.Response(200, {}, b"<html>admin</html>")
        out = self.assertRed(r, "/admin")
        self.assertNotIn("<html>", out)

    def test_admin_302_is_red(self):
        r = good_routes()
        r[("GET", "/admin")] = s.Response(302, {"Location": "/admin/login"}, b"")
        self.assertRed(r, "/admin")

    def test_lead_without_id_is_red(self):
        r = good_routes()
        r[("POST", "/api/fx/lead")] = _j(200, {"ok": True})
        self.assertRed(r, "lead")

    def test_lead_empty_id_is_red(self):
        r = good_routes()
        r[("POST", "/api/fx/lead")] = _j(200, {"ok": True, "id": ""})
        self.assertRed(r, "lead")

    def test_lead_honeypot_id_is_red(self):
        r = good_routes()
        r[("POST", "/api/fx/lead")] = _j(200, {"ok": True, "id": "hp"})
        self.assertRed(r, "lead")

    def test_lead_422_is_red(self):
        r = good_routes()
        r[("POST", "/api/fx/lead")] = _j(422, {"ok": False, "errors": {"phone": "invalid"}})
        self.assertRed(r, "lead")

    def test_transport_error_is_red_not_traceback(self):
        r = good_routes()
        r[("GET", "/api/fx/health")] = ConnectionRefusedError(111, "Connection refused")
        self.assertRed(r, "ConnectionRefusedError")

    def test_everything_down_is_red(self):
        r = {k: ConnectionRefusedError(111, "refused") for k in good_routes()}
        code, out, _ = run(r)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("FAIL"), 4, out)


class HostGuard(unittest.TestCase):
    def test_remote_hosts_refused_with_2_and_no_request(self):
        for base in (
            "https://table.central-aparts.store",
            "http://95.216.10.169:8005",
            "http://0.0.0.0:8005",
            "http://127.0.0.1@evil.example:8005",
            "http://localhost.evil.example:8005",
            "http://127.0.0.2:8005",
            "ftp://127.0.0.1:8005",
            "127.0.0.1:8005",
            "",
        ):
            with self.subTest(base=base):
                code, out, t = run(good_routes(), base=base)
                self.assertEqual(code, 2, out)
                self.assertIn("ВІДМОВА", out)
                self.assertEqual(t.calls, [], "до відмови не має піти жодного запиту")

    def test_local_hosts_allowed(self):
        for base in ("http://127.0.0.1:8005", "http://localhost:8005", "http://LOCALHOST:8005"):
            with self.subTest(base=base):
                self.assertIsNone(s.host_refusal(base))

    def test_main_default_base_is_local_8005(self):
        with mock.patch.object(s, "run", return_value=0) as m:
            self.assertEqual(s.main([]), 0)
        m.assert_called_once_with("http://127.0.0.1:8005")

    def test_main_remote_exits_2_without_network(self):
        with mock.patch.object(s, "urllib_transport", side_effect=AssertionError("network!")), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(s.main(["https://table.central-aparts.store"]), 2)


if __name__ == "__main__":
    unittest.main()
