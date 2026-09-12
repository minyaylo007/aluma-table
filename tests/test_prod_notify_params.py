"""scripts/prod_notify_params.py — без мережі й без AWS: aws-cli підмінено дублером.

Головне, що тут доведено: секрети не друкуються, AdminPass/IpSalt/EdgeSecret лишаються
UsePreviousValue, скрипт кличе лише два читальні виклики, файл — 0600 і не перезаписується.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import re
import stat
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import prod_notify_params as p  # noqa: E402

FAKE_TOKEN = "1234567890:AAH" + "f" * 32
FAKE_CHAT = "555000111"
# імена параметрів розгорнутого стеку fx-table, як їх віддав describe-stacks 2026-09-11
DEPLOYED_KEYS = ["LeadNotifyEmail", "AppVersion", "EdgeSecret", "WhatsappNumber", "AdminUser",
                 "SiteDomain", "AdminPass", "IpSalt", "CertificateArn"]
TEMPLATE_TEXT = (ROOT / "infra" / "template.yaml").read_text(encoding="utf-8")


class FakeAws:
    def __init__(self, env=None, keys=DEPLOYED_KEYS):
        self.env = {"TELEGRAM_BOT_TOKEN": FAKE_TOKEN, "OWNER_TELEGRAM_CHAT_ID": FAKE_CHAT} if env is None else env
        self.keys = keys
        self.calls = []

    def __call__(self, args):
        self.calls.append(tuple(args[:2]))
        if tuple(args[:2]) == ("cloudformation", "describe-stacks"):
            return {"Stacks": [{"Parameters": [{"ParameterKey": k, "ParameterValue": "****"} for k in self.keys]}]}
        if tuple(args[:2]) == ("lambda", "get-function-configuration"):
            return {"Environment": {"Variables": dict(self.env, OTHER_SECRET="must-not-leak")}}
        raise AssertionError(f"unexpected aws call {args}")


class ParamsTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix="aluma-params-test-")
        self.addCleanup(self.dir.cleanup)
        self.out = pathlib.Path(self.dir.name) / "params.json"

    def run_main(self, *extra, runner=None, version="0.4.0"):
        buf = io.StringIO()
        argv = ["--app-version", version, "--out", str(self.out), *extra]
        rc = p.main(argv, runner=runner or FakeAws(), out=buf)
        return rc, buf.getvalue()


class TemplateTests(unittest.TestCase):
    def test_parameters_of_the_real_template(self):
        self.assertEqual(p.template_parameters(TEMPLATE_TEXT), [
            "SiteDomain", "CertificateArn", "AdminUser", "AdminPass", "IpSalt", "WhatsappNumber",
            "TelegramBotToken", "OwnerTelegramChatId", "EdgeSecret", "AppVersion",
        ])


class HappyPathTests(ParamsTestCase):
    def test_file_content(self):
        rc, _ = self.run_main()
        self.assertEqual(rc, 0)
        params = json.loads(self.out.read_text(encoding="utf-8"))
        by_key = {x["ParameterKey"]: x for x in params}
        self.assertEqual(by_key["AppVersion"], {"ParameterKey": "AppVersion", "ParameterValue": "0.4.0"})
        self.assertEqual(by_key["TelegramBotToken"]["ParameterValue"], FAKE_TOKEN)
        self.assertEqual(by_key["OwnerTelegramChatId"]["ParameterValue"], FAKE_CHAT)
        kept = {"SiteDomain", "CertificateArn", "AdminUser", "AdminPass", "IpSalt", "WhatsappNumber", "EdgeSecret"}
        for key in kept:
            with self.subTest(key=key):
                self.assertEqual(by_key[key], {"ParameterKey": key, "UsePreviousValue": True})
        self.assertNotIn("LeadNotifyEmail", by_key)  # у новому шаблоні його нема
        self.assertEqual(len(params), 10)
        for x in params:  # рівно одне з двох — інакше CloudFormation відмовить
            self.assertEqual(len({"ParameterValue", "UsePreviousValue"} & set(x)), 1)

    def test_file_is_private(self):
        self.run_main()
        self.assertEqual(stat.S_IMODE(os.stat(self.out).st_mode), 0o600)

    def test_no_secret_on_stdout(self):
        rc, text = self.run_main()
        self.assertEqual(rc, 0)
        self.assertNotIn(FAKE_TOKEN, text)
        self.assertNotIn(FAKE_CHAT, text)
        self.assertNotIn("AAH", text)
        self.assertNotIn("must-not-leak", text)
        self.assertIn("AdminPass: как было", text)
        self.assertIn("LeadNotifyEmail", text)  # сказано, що зникне

    def test_only_two_read_calls(self):
        aws = FakeAws()
        self.run_main(runner=aws)
        self.assertEqual(aws.calls, [("cloudformation", "describe-stacks"),
                                     ("lambda", "get-function-configuration")])

    def test_write_calls_are_refused_before_reaching_aws(self):
        aws = FakeAws()
        for verb in (["cloudformation", "create-change-set"], ["cloudformation", "update-stack"],
                     ["lambda", "update-function-configuration"], ["lambda", "invoke"]):
            with self.subTest(verb=verb):
                with self.assertRaises(p.Refusal):
                    p._call(aws, verb)
        self.assertEqual(aws.calls, [])


class RefusalTests(ParamsTestCase):
    def assert_refused(self, rc, text):
        self.assertEqual(rc, 2)
        self.assertIn("ОТКАЗ", text)
        self.assertFalse(self.out.exists())
        self.assertNotIn(FAKE_TOKEN, text)
        self.assertNotIn(FAKE_CHAT, text)

    def test_old_version(self):
        self.assert_refused(*self.run_main(version="0.3.0"))

    def test_garbage_version(self):
        self.assert_refused(*self.run_main(version="latest"))

    def test_missing_token(self):
        self.assert_refused(*self.run_main(runner=FakeAws(env={"OWNER_TELEGRAM_CHAT_ID": FAKE_CHAT})))

    def test_empty_chat(self):
        self.assert_refused(*self.run_main(runner=FakeAws(env={"TELEGRAM_BOT_TOKEN": FAKE_TOKEN,
                                                               "OWNER_TELEGRAM_CHAT_ID": ""})))

    def test_malformed_token_is_refused_without_echo(self):
        bad = "not-a-token-but-still-secret"
        rc, text = self.run_main(runner=FakeAws(env={"TELEGRAM_BOT_TOKEN": bad,
                                                     "OWNER_TELEGRAM_CHAT_ID": FAKE_CHAT}))
        self.assert_refused(rc, text)
        self.assertNotIn(bad, text)

    def test_unknown_new_parameter(self):
        tpl = pathlib.Path(self.dir.name) / "t.yaml"
        tpl.write_text(TEMPLATE_TEXT.replace("  AppVersion:\n", "  BrandNew:\n    Type: String\n  AppVersion:\n"),
                       encoding="utf-8")
        self.assert_refused(*self.run_main("--template", str(tpl)))

    def test_must_keep_parameter_missing_from_the_stack(self):
        """EdgeSecret, якого нема в стеку, не можна «лишити як було» — відмова."""
        keys = [k for k in DEPLOYED_KEYS if k != "EdgeSecret"]
        self.assert_refused(*self.run_main(runner=FakeAws(keys=keys)))

    def test_must_keep_parameter_missing_from_the_template(self):
        """Шаблон без EdgeSecret зняв би x-fx-edge з CloudFront — саме це ловить MUST_KEEP."""
        tpl = pathlib.Path(self.dir.name) / "t.yaml"
        text, n = re.subn(r"^  EdgeSecret:\n(?:    .*\n)+", "", TEMPLATE_TEXT, flags=re.M)
        self.assertEqual(n, 1)
        tpl.write_text(text, encoding="utf-8")
        rc, out = self.run_main("--template", str(tpl))
        self.assert_refused(rc, out)
        self.assertIn("EdgeSecret", out)

    def test_existing_file_is_not_touched(self):
        self.out.write_text("keep me", encoding="utf-8")
        rc, text = self.run_main()
        self.assertEqual(rc, 2)
        self.assertEqual(self.out.read_text(encoding="utf-8"), "keep me")


if __name__ == "__main__":
    unittest.main()
