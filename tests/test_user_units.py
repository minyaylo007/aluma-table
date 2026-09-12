"""Користувацькі юніти ALUMA під агент деплою (research.md R10–R13, contracts/agent-cli.md).

Розкладка на машині: /opt/ihor/aluma-table/current → releases/vX.Y.Z; API і чистка працюють із current/,
номер і sha версії приходять із current/RELEASE.env (після aluma.env — пізніше значення перемагає),
агент — oneshot-сервіс за таймером. Лише текст файлів, без systemd.

    python -m unittest tests.test_user_units -v
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UNITS = ROOT / "deploy" / "systemd" / "user"
BASE = "/opt/ihor/aluma-table"
CURRENT = BASE + "/current"


def directives(name: str) -> list:
    """[(ключ, значення)] у порядку файлу; коментарі пропущено, «\\» у кінці рядка склеєно."""
    text = (UNITS / name).read_text(encoding="utf-8")
    text = re.sub(r"[ \t]*\\\n\s*", " ", text)
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";", "[")):
            continue
        key, _, value = line.partition("=")
        out.append((key.strip(), value.strip()))
    return out


def values(name: str, key: str) -> list:
    return [v for k, v in directives(name) if k == key]


def one(name: str, key: str) -> str:
    found = values(name, key)
    assert len(found) == 1, (name, key, found)
    return found[0]


class ApiUnitTests(unittest.TestCase):
    NAME = "ihor-aluma-api.service"

    def test_runs_from_current(self):
        self.assertEqual(one(self.NAME, "WorkingDirectory"), CURRENT)
        self.assertTrue(one(self.NAME, "ExecStart").startswith(CURRENT + "/.venv/bin/gunicorn "))

    def test_gunicorn_flags_unchanged(self):
        cmd = one(self.NAME, "ExecStart").split()
        self.assertIn("--no-control-socket", cmd)
        self.assertEqual(cmd[cmd.index("-b") + 1], "127.0.0.1:8005")
        self.assertEqual(cmd[-1], "api.wsgi:application")

    def test_release_env_after_secrets(self):
        env = values(self.NAME, "EnvironmentFile")
        self.assertEqual(env, ["%h/.config/aluma/aluma.env", CURRENT + "/RELEASE.env"])

    def test_umask_and_privileges(self):
        self.assertEqual(one(self.NAME, "UMask"), "0077")
        self.assertEqual(one(self.NAME, "NoNewPrivileges"), "true")


class PurgeUnitTests(unittest.TestCase):
    NAME = "ihor-aluma-purge.service"

    def test_runs_from_current(self):
        self.assertEqual(one(self.NAME, "WorkingDirectory"), CURRENT)
        self.assertEqual(one(self.NAME, "ExecStart"), CURRENT + "/.venv/bin/python scripts/purge.py")
        self.assertEqual(values(self.NAME, "EnvironmentFile"), ["%h/.config/aluma/aluma.env"])


class DeployUnitTests(unittest.TestCase):
    NAME = "ihor-aluma-deploy.service"

    def test_oneshot_system_python_once(self):
        self.assertEqual(one(self.NAME, "Type"), "oneshot")
        self.assertEqual(one(self.NAME, "ExecStart"),
                         f"/usr/bin/python3 {CURRENT}/deploy/agent/pullagent.py "
                         f"--config {CURRENT}/deploy/agent/aluma.json --once")

    def test_hardening(self):
        self.assertEqual(one(self.NAME, "NoNewPrivileges"), "true")
        self.assertEqual(one(self.NAME, "UMask"), "0027")

    def test_no_secrets_file(self):
        # Агент не читає aluma.env (FR-019): у його юніті немає EnvironmentFile взагалі.
        self.assertEqual(values(self.NAME, "EnvironmentFile"), [])


class DeployTimerTests(unittest.TestCase):
    NAME = "ihor-aluma-deploy.timer"

    def test_schedule(self):
        self.assertEqual(one(self.NAME, "OnBootSec"), "2min")
        self.assertEqual(one(self.NAME, "OnUnitInactiveSec"), "60s")
        self.assertEqual(one(self.NAME, "Unit"), "ihor-aluma-deploy.service")
        self.assertEqual(one(self.NAME, "WantedBy"), "timers.target")


class AllUnitsTests(unittest.TestCase):
    def test_no_sudo_no_caddy_no_foreign_paths(self):
        for path in sorted(UNITS.iterdir()):
            body = " ".join(v for _, v in directives(path.name))
            self.assertNotRegex(body, r"\bsudo\b", path.name)
            self.assertNotRegex(body, r"(?i)caddy|:2019\b", path.name)
            self.assertNotRegex(body, r"/opt/(?!ihor/aluma-table)", path.name)

    def test_parser_is_not_vacuous(self):
        self.assertTrue(values("ihor-aluma-api.service", "ExecStart"))
        self.assertGreater(len(directives("ihor-aluma-api.service")), 8)


if __name__ == "__main__":
    unittest.main()
