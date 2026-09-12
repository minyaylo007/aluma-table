"""scripts/box_env.py — без мережі й без AWS: aws-cli підмінено дублером.

Доведено: значення не друкуються, EDGE_SECRET не пишеться навіть коли він є в джерелі,
скрипт кличе лише get-function-configuration, файл 0600 у теці 0700 і не перезаписується,
--check показує тільки імена й «задано/пусто», а з --pid ловить розбіжність із процесом.
"""

from __future__ import annotations

import io
import os
import pathlib
import stat
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import box_env as b  # noqa: E402

FAKE_TOKEN = "1234567890:AAH" + "f" * 32
FAKE_CHAT = "555000111"
ADMIN_ENV = {"ADMIN_USER": "owner-fake", "ADMIN_PASS": "Pass-fake-771", "IP_SALT": "salt-fake-913",
             "SITE_DOMAIN": "table.example.test", "WHATSAPP_NUMBER": "",
             "EDGE_SECRET": "edge-fake-must-not-leak", "APP_VERSION": "0.3.0"}
TG_ENV = {"TELEGRAM_BOT_TOKEN": FAKE_TOKEN, "OWNER_TELEGRAM_CHAT_ID": FAKE_CHAT, "OTHER": "other-fake"}
SECRETS = ("Pass-fake-771", "salt-fake-913", "edge-fake-must-not-leak", FAKE_TOKEN, FAKE_CHAT, "owner-fake")


class FakeAws:
    def __init__(self, admin=None, tg=None):
        self.env = {"fx-table-api": dict(ADMIN_ENV if admin is None else admin),
                    "aparts-api": dict(TG_ENV if tg is None else tg)}
        self.calls = []

    def __call__(self, args):
        self.calls.append(tuple(args[:2]))
        if tuple(args[:2]) == ("lambda", "get-function-configuration"):
            return {"Environment": {"Variables": self.env[args[args.index("--function-name") + 1]]}}
        raise AssertionError(f"unexpected aws call {args}")


class BoxEnvTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix="aluma-box-env-test-")
        self.addCleanup(self.dir.cleanup)
        self.out = pathlib.Path(self.dir.name) / "cfg" / "aluma.env"

    def run_main(self, *argv, runner=None):
        buf = io.StringIO()
        rc = b.main(list(argv), runner=runner or FakeAws(), out=buf)
        return rc, buf.getvalue()

    def write(self, runner=None, version="0.4.0-box", db="/opt/ihor/aluma-table/data/aluma.db"):
        return self.run_main("--out", str(self.out), "--app-version", version, "--db", db, runner=runner)

    def assertNoSecrets(self, text):
        for s in SECRETS:
            self.assertNotIn(s, text)


class WriteTests(BoxEnvTestCase):
    def test_writes_all_keys_and_prints_no_values(self):
        aws = FakeAws()
        rc, out = self.write(runner=aws)
        self.assertEqual(rc, 0, out)
        self.assertNoSecrets(out)
        values = b.parse(self.out.read_text(encoding="utf-8"))
        self.assertEqual(values["ADMIN_PASS"], "Pass-fake-771")
        self.assertEqual(values["IP_SALT"], "salt-fake-913")  # незмінною, символ у символ
        self.assertEqual(values["TELEGRAM_BOT_TOKEN"], FAKE_TOKEN)
        self.assertEqual(values["OWNER_TELEGRAM_CHAT_ID"], FAKE_CHAT)
        self.assertEqual(values["FX_STORAGE"], "sqlite")
        self.assertEqual(values["FX_DB_PATH"], "/opt/ihor/aluma-table/data/aluma.db")
        self.assertEqual(values["APP_VERSION"], "0.4.0-box")  # не прод-овська 0.3.0 з джерела
        self.assertEqual(values["WHATSAPP_NUMBER"], "")
        self.assertEqual(set(aws.calls), {("lambda", "get-function-configuration")})

    def test_edge_secret_never_written(self):
        rc, _ = self.write()
        self.assertEqual(rc, 0)
        text = self.out.read_text(encoding="utf-8")
        self.assertNotIn("EDGE_SECRET=", text)
        self.assertNotIn("edge-fake-must-not-leak", text)
        self.assertNotIn("other-fake", text)

    def test_file_0600_dir_0700(self):
        self.assertEqual(self.write()[0], 0)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.out.parent.stat().st_mode), 0o700)

    def test_never_overwrites(self):
        self.assertEqual(self.write()[0], 0)
        before = self.out.read_bytes()
        rc, out = self.write(runner=FakeAws(admin=dict(ADMIN_ENV, ADMIN_PASS="other-pass")))
        self.assertEqual(rc, 2)
        self.assertIn("не перезаписываю", out)
        self.assertEqual(self.out.read_bytes(), before)

    def test_refuses_open_parent_dir(self):
        self.out.parent.mkdir(mode=0o755)
        os.chmod(self.out.parent, 0o755)
        rc, out = self.write()
        self.assertEqual(rc, 2)
        self.assertFalse(self.out.exists())

    def test_refusals_write_nothing_and_print_no_values(self):
        cases = [
            dict(version="0.3.0"),
            dict(version="box"),
            dict(db="data/aluma.db"),
            dict(runner=FakeAws(admin=dict(ADMIN_ENV, ADMIN_PASS=""))),
            dict(runner=FakeAws(admin=dict(ADMIN_ENV, IP_SALT="  "))),
            dict(runner=FakeAws(tg=dict(TG_ENV, TELEGRAM_BOT_TOKEN="not-a-token"))),
            dict(runner=FakeAws(admin=dict(ADMIN_ENV, ADMIN_PASS='Pass-fake-771"x y'))),
        ]
        for kw in cases:
            with self.subTest(**{k: str(v) for k, v in kw.items() if k != "runner"}):
                rc, out = self.write(**kw)
                self.assertEqual(rc, 2, out)
                self.assertIn("ОТКАЗ", out)
                self.assertNoSecrets(out)
                self.assertFalse(self.out.exists())

    def test_only_read_only_calls(self):
        with self.assertRaises(b.Refusal):
            b._call(FakeAws(), ["lambda", "update-function-configuration"])


class CheckTests(BoxEnvTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.write()[0], 0)

    def test_check_prints_names_only(self):
        rc, out = self.run_main("--check", str(self.out))
        self.assertEqual(rc, 0, out)
        self.assertNoSecrets(out)
        self.assertIn("ADMIN_PASS: задано", out)
        self.assertIn("WHATSAPP_NUMBER: пусто", out)
        self.assertIn("права 600", out)

    def test_check_against_process_env(self):
        values = b.parse(self.out.read_text(encoding="utf-8"))
        buf = io.StringIO()
        self.assertEqual(b.check(self.out, dict(values), buf), 0)
        self.assertNoSecrets(buf.getvalue())
        buf = io.StringIO()
        self.assertEqual(b.check(self.out, dict(values, IP_SALT="drifted"), buf), 1)
        self.assertIn("IP_SALT: задано; в процессе НЕ совпадает", buf.getvalue())
        self.assertNoSecrets(buf.getvalue())

    def test_check_flags_edge_secret_and_open_file(self):
        with open(self.out, "a", encoding="utf-8") as f:
            f.write("EDGE_SECRET=x\n")
        os.chmod(self.out, 0o640)
        rc, out = self.run_main("--check", str(self.out))
        self.assertEqual(rc, 1)
        self.assertIn("EDGE_SECRET присутствует", out)
        self.assertIn("нужна 0600", out)

    def test_proc_environ_reads_own_process(self):
        os.environ["ALUMA_BOX_ENV_TEST"] = "1"
        self.addCleanup(os.environ.pop, "ALUMA_BOX_ENV_TEST", None)
        # /proc/<pid>/environ — оточення на момент exec, тож дописане зараз там не видно;
        # PATH же є завжди.
        self.assertIn("PATH", b.proc_environ(os.getpid()))


if __name__ == "__main__":
    unittest.main()
