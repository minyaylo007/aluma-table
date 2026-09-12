"""scripts/secret_scan.py — перевірка історії git перед публікацією (contracts/secret-scan.md).

Синтетичні «секрети» складаються під час виконання з частин, щоб у самому цьому файлі
не було рядка, який сканер (або gitleaks, або GitHub) прийняв би за справжній. Головне —
червоні випадки і те, що значення НІКОЛИ не потрапляє ні в stdout, ні у звіт.

    python -m unittest tests.test_secret_scan -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "secret_scan.py"

# Git тестового репозиторію не бачить конфігурації користувача (помічники облікових даних,
# хуки, підписи) — лише те, що задано тут.
GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "Synthetic",
    "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
    "GIT_COMMITTER_NAME": "Synthetic",
    "GIT_COMMITTER_EMAIL": "synthetic@example.invalid",
}

# Синтетика (складається з частин, див. docstring).
AWS_KEY = "AKIA" + "Q7" * 8
TG_VALUE = "000000" + ":" + "fake-not-a-token"
TG_SHAPED = "1234567" + ":" + "Zz" * 18   # форма справжнього токена бота
ADMIN_VALUE = "fa" + "ke"
PHONE = "+972-50-" + "000-0000"
PERSON = "Synthetic " + "Person"
ARN = "arn:aws:acm:eu-central-1:" + "0" * 12 + ":certificate/fake"
SECRETS = [AWS_KEY, TG_VALUE, TG_SHAPED, PHONE, PERSON, ARN, "0" * 12]


def git(repo, *args):
    env = dict(os.environ, **GIT_ENV)
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def commit(repo, files, message):
    for rel, content in files.items():
        path = pathlib.Path(repo, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
        git(repo, "add", "--", rel)
    git(repo, "commit", "-q", "-m", message)


def run_scan(*args):
    env = dict(os.environ, **GIT_ENV)
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                          capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


class SecretScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-scan-test-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        commit(self.repo, {"README.md": "clean\n"}, "init")
        self.report = self.tmp / "report.md"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def dirty_history(self):
        lead = json.dumps(dict(name=PERSON, phone=PHONE))
        commit(self.repo, {
            "app/config.py": "x = 1\nkey = '" + AWS_KEY + "'\n",
            "deploy/box.env.txt": "TELEGRAM_BOT_TOKEN" + "=" + TG_VALUE + "\n"
                                  + "ADMIN_PASS" + "=" + ADMIN_VALUE + "\n",
            "notes.md": "line one\nline two\ncall " + PHONE + "\n",
            "bot.py": "url = 'https://api.telegram.org/bot" + TG_SHAPED + "/sendMessage'\n",
            "fixtures/lead.txt": lead + "\n",
            "infra/samconfig.toml": "x = 1\n",
            "infra/example.toml": "cert = \"" + ARN + "\"\n",
            "dump/x.jsonl": "{}\n",
            "data/a.db": b"SQLite format 3\x00\x00\x01",
        }, "dirty")
        # Друга гілка — `--all` мусить її бачити.
        git(self.repo, "checkout", "-q", "-b", "side")
        commit(self.repo, {"side.txt": "k = " + AWS_KEY + "\n"}, "side")
        git(self.repo, "checkout", "-q", "main")
        # Видалення з робочого дерева не прибирає з історії.
        git(self.repo, "rm", "-q", "-r", "app", "dump", "data", "notes.md")
        git(self.repo, "commit", "-q", "-m", "cleanup")

    def assert_no_values(self, text):
        for value in SECRETS + [ADMIN_VALUE + "\n", "=" + ADMIN_VALUE]:
            self.assertNotIn(value, text)

    def test_dirty_history_exit_1_and_no_values(self):
        self.dirty_history()
        code, out = run_scan("--repo", str(self.repo), "--report", str(self.report))
        self.assertEqual(code, 1, out)
        report = self.report.read_text(encoding="utf-8")
        for text in (out, report):
            self.assert_no_values(text)
        for rule in ("aws_access_key_id", "telegram_bot_token", "env_secret", "phone_il",
                     "json_pii", "aws_arn_account", "path_samconfig", "path_dump",
                     "path_sqlite_db"):
            self.assertIn(rule, report, rule)

    def test_report_has_rule_short_sha_path_line(self):
        self.dirty_history()
        run_scan("--repo", str(self.repo), "--report", str(self.report))
        report = self.report.read_text(encoding="utf-8")
        sha = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "--short=10", "side"],
                             capture_output=True, text=True, check=True).stdout.strip()
        # Рядок таблиці: | правило | шлях | збігів | <коротке sha>:<рядок> |
        # side.txt, рядок 1, коротке sha коміту гілки side.
        self.assertRegex(report, r"\| aws_access_key_id \| side\.txt \| 1 \| " + sha[:7] + r"[0-9a-f]*:1 \|")
        # notes.md, телефон — рядок 3.
        self.assertRegex(report, r"\| phone_il \| notes\.md \| 1 \| [0-9a-f]{7,}:3 \|")
        # app/config.py, ключ — рядок 2.
        self.assertRegex(report, r"\| aws_access_key_id \| app/config\.py \| 1 \| [0-9a-f]{7,}:2 \|")

    def test_clean_repo_exit_0(self):
        commit(self.repo, {"deploy/aluma.env.example": "ADMIN_PASS=\nIP_SALT=\n",
                           "code.py": "ADMIN_PASS = os.environ.get('ADMIN_PASS', '')\n"},
               "clean example")
        code, out = run_scan("--repo", str(self.repo), "--report", str(self.report))
        self.assertEqual(code, 0, out)
        self.assertTrue(self.report.exists())

    def test_env_example_is_not_an_env_file(self):
        commit(self.repo, {"deploy/aluma.env.example": "X=\n"}, "example")
        code, out = run_scan("--repo", str(self.repo), "--report", str(self.report))
        self.assertEqual(code, 0, out)
        commit(self.repo, {".env": "X=\n"}, "real env")
        code, out = run_scan("--repo", str(self.repo), "--report", str(self.report))
        self.assertEqual(code, 1, out)
        self.assertIn("path_env_file", self.report.read_text(encoding="utf-8"))

    def test_missing_repo_exit_2(self):
        code, _ = run_scan("--repo", str(self.tmp / "nope"), "--report", str(self.report))
        self.assertEqual(code, 2)
        self.assertFalse(self.report.exists())

    def test_not_a_git_repo_exit_2(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        code, _ = run_scan("--repo", str(plain), "--report", str(self.report))
        self.assertEqual(code, 2)

    def test_logs_folder_is_scanned_without_values(self):
        logs = self.tmp / "logs"
        logs.mkdir()
        (logs / "123.log").write_text("step ok\nenv " + AWS_KEY + "\n", encoding="utf-8")
        code, out = run_scan("--repo", str(self.repo), "--logs", str(logs),
                             "--report", str(self.report))
        self.assertEqual(code, 1, out)
        report = self.report.read_text(encoding="utf-8")
        self.assertRegex(report, r"\| aws_access_key_id \| logs/123\.log \| 1 \| -:2 \|")
        self.assert_no_values(out + report)

    def test_host_security_details_are_findings(self):
        # Кожен термін — окремим рядком, складений із частин (див. docstring).
        terms = ["Administrator" + "Access", "NO" + "PASSWD", "sudo " + "без пароля", "admin" + ".sock",
                 "hetzner" + "-box", "delete" + "_repo", "admin" + ":org", "паці" + "єнтів", "паци" + "енты",
                 "Pati" + "ents"]
        commit(self.repo, {"docs/box.md": "".join(f"row {t} here\n" for t in terms)}, "box notes")
        code, out = run_scan("--repo", str(self.repo), "--report", str(self.report))
        self.assertEqual(code, 1, out)
        report = self.report.read_text(encoding="utf-8")
        self.assertRegex(report, r"\| host_security_detail \| docs/box\.md \| " + str(len(terms)) + r" \|")
        for n in range(1, len(terms) + 1):
            self.assertRegex(report, r"host_security_detail \| docs/box\.md .*:" + str(n) + r"\b", terms[n - 1][:3])

    def test_near_words_are_not_host_details(self):
        commit(self.repo, {"docs/ok.md": "administrator of the patio\nsudo is forbidden\nadmin panel\n"
                                         "password protected\ndelete the repo branch\n"},
               "harmless words")
        code, out = run_scan("--repo", str(self.repo), "--report", str(self.report))
        self.assertEqual(code, 0, out)

    def test_scanner_and_its_test_do_not_flag_themselves(self):
        # Шаблони в коді сканера й терміни в цьому тесті розбиті на частини — у звіті їх бути не повинно.
        spec = importlib.util.spec_from_file_location("secret_scan_mod", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for rel in ("scripts/secret_scan.py", "tests/test_secret_scan.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for no, line in enumerate(text.splitlines(), 1):
                self.assertEqual(mod.scan_line(line), set(), f"{rel}:{no}")

    def test_placeholders_are_not_secrets(self):
        commit(self.repo, {"docs/x.md": "ADMIN_PASS=<set-me>\nIP_SALT=${IP_SALT}\n"
                                        "EDGE_SECRET=$EDGE_SECRET\n" "TELEGRAM_BOT_TOKEN" "=\n"},
               "placeholders")
        code, out = run_scan("--repo", str(self.repo), "--report", str(self.report))
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
