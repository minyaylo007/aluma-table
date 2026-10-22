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


class BackupUnitTests(unittest.TestCase):
    """Бекап заявок: з клону, як встановлені сьогодні api і purge (не current/ — коментар у юніті)."""
    NAME = "ihor-aluma-backup.service"
    TIMER = "ihor-aluma-backup.timer"

    def test_runs_from_clone_with_api_venv_and_env(self):
        self.assertEqual(one(self.NAME, "Type"), "oneshot")
        self.assertEqual(one(self.NAME, "WorkingDirectory"), BASE)
        self.assertEqual(one(self.NAME, "ExecStart"), BASE + "/.venv/bin/python scripts/backup_leads.py")
        self.assertEqual(values(self.NAME, "EnvironmentFile"), ["%h/.config/aluma/aluma.env"])

    def test_background_and_private(self):
        self.assertEqual(one(self.NAME, "Nice"), "10")
        self.assertEqual(one(self.NAME, "IOSchedulingClass"), "idle")
        self.assertEqual(one(self.NAME, "UMask"), "0077")
        self.assertEqual(one(self.NAME, "NoNewPrivileges"), "true")
        # Як у сусідів: опції простору імен у менеджері користувача мовчки не діють — не вдавати захист.
        for key in ("User", "PrivateTmp", "ProtectSystem", "ProtectHome", "ReadWritePaths"):
            self.assertEqual(values(self.NAME, key), [], key)

    def test_timer_hourly_at_07_not_00(self):
        self.assertEqual(one(self.TIMER, "Unit"), self.NAME)
        self.assertEqual(one(self.TIMER, "OnCalendar"), "*-*-* *:07:00")
        self.assertTrue(one(self.TIMER, "OnBootSec"))
        self.assertEqual(one(self.TIMER, "Persistent"), "true")
        self.assertEqual(one(self.TIMER, "WantedBy"), "timers.target")


class DigestUnitTests(unittest.TestCase):
    """Дайджест воронки: ті самі інваріанти, що в бекапу; розклад — за Єрусалимом, не за зоною машини."""
    NAME = "ihor-aluma-digest.service"
    TIMER = "ihor-aluma-digest.timer"

    def test_runs_from_clone_with_api_venv_and_env(self):
        self.assertEqual(one(self.NAME, "Type"), "oneshot")
        self.assertEqual(one(self.NAME, "WorkingDirectory"), BASE)
        self.assertEqual(one(self.NAME, "ExecStart"), BASE + "/.venv/bin/python scripts/funnel_digest.py")
        self.assertEqual(values(self.NAME, "EnvironmentFile"), ["%h/.config/aluma/aluma.env"])
        self.assertNotIn("--dry-run", one(self.NAME, "ExecStart"))

    def test_background_and_private(self):
        self.assertEqual(one(self.NAME, "Nice"), "10")
        self.assertEqual(one(self.NAME, "UMask"), "0077")
        self.assertEqual(one(self.NAME, "NoNewPrivileges"), "true")
        for key in ("User", "PrivateTmp", "ProtectSystem", "ProtectHome", "ReadWritePaths"):
            self.assertEqual(values(self.NAME, key), [], key)

    def test_timer_09_and_20_jerusalem(self):
        self.assertEqual(one(self.TIMER, "Unit"), self.NAME)
        self.assertEqual(one(self.TIMER, "OnCalendar"), "*-*-* 09,20:00:00 Asia/Jerusalem")
        self.assertEqual(one(self.TIMER, "Persistent"), "true")
        self.assertEqual(one(self.TIMER, "WantedBy"), "timers.target")
        # Не частіше: OnBootSec/OnUnitActiveSec слали б зайві повідомлення власнику.
        for key in ("OnBootSec", "OnUnitActiveSec", "OnUnitInactiveSec"):
            self.assertEqual(values(self.TIMER, key), [], key)


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


class IgRefreshUnitTests(unittest.TestCase):
    """Оновлення токена Instagram: лише --refresh (не публікація), без aluma.env, не частіше двох разів на місяць."""
    NAME = "ihor-aluma-ig-refresh.service"
    TIMER = "ihor-aluma-ig-refresh.timer"

    def test_refresh_only_from_clone(self):
        self.assertEqual(one(self.NAME, "Type"), "oneshot")
        self.assertEqual(one(self.NAME, "WorkingDirectory"), BASE)
        self.assertEqual(one(self.NAME, "ExecStart"), BASE + "/.venv/bin/python scripts/ig_publish.py --refresh")
        self.assertEqual(values(self.NAME, "EnvironmentFile"), [])
        self.assertEqual(one(self.NAME, "UMask"), "0077")
        self.assertEqual(one(self.NAME, "NoNewPrivileges"), "true")

    def test_timer_twice_a_month(self):
        self.assertEqual(one(self.TIMER, "Unit"), self.NAME)
        self.assertEqual(one(self.TIMER, "OnCalendar"), "*-*-01,15 04:00:00")
        self.assertEqual(one(self.TIMER, "Persistent"), "true")
        self.assertEqual(one(self.TIMER, "WantedBy"), "timers.target")
        # OnBootSec оновлював би токен після кожного перезапуску — і раніше 24 годин від видачі.
        for key in ("OnBootSec", "OnUnitActiveSec", "OnUnitInactiveSec"):
            self.assertEqual(values(self.TIMER, key), [], key)


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
