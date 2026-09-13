"""scripts/secret_scan.py — пошук секретів і ПД (contracts/secret-scan.md).

Синтетичні «секрети» складаються під час виконання з частин, щоб у самому цьому файлі
не було рядка, який сканер (або GitHub) прийняв би за справжній. Правило просте і
перевіряється тестом test_scanner_and_its_test_do_not_flag_themselves: слово-ознака
(«door code», «ІПН», ім'я змінної) і значення ніколи не стоять в одному рядку коду.

Головне, що тут перевіряється: кожне правило має червоний і зелений випадок, і значення
НІКОЛИ не потрапляє ні в stdout, ні у звіт.

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

# ── Синтетика. Значення — окремими рядками, слова-ознаки — окремими (див. docstring).
DIGITS4 = "43" + "21"
DIGITS6 = "123" + "456"
DIGITS10 = "12345" + "67890"
LONG20 = "A" * 24
AWS_KEY = "AKIA" + "Q7" * 8
TG_VALUE = "000000" + ":" + "fake-not-a-token"
TG_SHAPED = "1234567" + ":" + "Zz" * 18   # форма справжнього токена бота
ADMIN_VALUE = "thr" + "owaway"
PHONE_IL = "+972-50-" + "000-0000"
PHONE_UA = "+38(050) " + "123 45 67"
PERSON = "Synthetic " + "Person"
ARN = "arn:aws:acm:eu-central-1:" + "0" * 12 + ":certificate/fake"
MAIL = "person" + "@" + "gmail.com"
PASS_WORD = "Sup" + "erPass1"
IBAN = "UA" + "12" + "3" * 25
CARD = " ".join(["4111", "1111", "1111", "1111"])
JWT = "eyJ" + "a" * 10 + "." + "eyJ" + "b" * 10 + "." + "c" * 10

SECRETS = [AWS_KEY, TG_VALUE, TG_SHAPED, PHONE_IL, PHONE_UA, PERSON, ARN, "0" * 12,
           MAIL, PASS_WORD, IBAN, CARD, JWT, LONG20, DIGITS10]


def load_module():
    spec = importlib.util.spec_from_file_location("secret_scan_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = load_module()


def rules(text: str) -> set:
    return MOD.scan_line(text)


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
                          capture_output=True, text=True, timeout=180)
    return proc.returncode, proc.stdout + proc.stderr


class RuleTests(unittest.TestCase):
    """По одному червоному й зеленому випадку на кожне правило вмісту.

    Правила перенесені з бек-офісу (~/repos/aparts/scripts/secret_scan.py, 13.09.2026):
    саме вони знайшли в іншому проєкті коди дверей і пароль WiFi — у документах.
    """

    def assertRule(self, name, text):
        self.assertIn(name, rules(text), text[:40])

    def assertClean(self, text):
        self.assertEqual(rules(text), set(), text[:60])

    # ── ключі й токени
    def test_aws_access_key_id(self):
        self.assertRule("aws_access_key_id", "key = " + AWS_KEY)
        self.assertClean("AKIA" + " is a prefix")

    def test_aws_secret_access_key(self):
        self.assertRule("aws_secret_access_key", "aws_secret_access_key" + " = " + "b" * 40)

    def test_github_token(self):
        self.assertRule("github_token", "token " + "gh" + "p_" + "c" * 36)
        self.assertClean("gh" + "p_short")

    def test_telegram_bot_token(self):
        self.assertRule("telegram_bot_token", "url .../bot" + TG_SHAPED + "/sendMessage")
        self.assertClean("time 12:30")

    def test_monobank_token(self):
        self.assertRule("monobank_token", "x" + "-token: " + LONG20)

    def test_llm_api_key(self):
        self.assertRule("llm_api_key", "key " + "sk-" + "ant-" + "d" * 30)

    def test_google_api_key(self):
        self.assertRule("google_api_key", "key " + "AIza" + "e" * 35)

    def test_slack_token(self):
        self.assertRule("slack_token", "token " + "xox" + "b-" + "f" * 12)

    def test_jwt(self):
        self.assertRule("jwt", "authorization: Bearer " + JWT)

    def test_private_key(self):
        self.assertRule("private_key", "-----BEGIN " + "OPENSSH " + "PRIVATE KEY-----")

    def test_named_secret(self):
        self.assertRule("named_secret", "ADMIN_PASS" + "=" + ADMIN_VALUE)
        self.assertRule("named_secret", "IP_SALT" + "=" + ADMIN_VALUE)
        self.assertRule("named_secret", "EDGE_SECRET" + "=" + ADMIN_VALUE)

    def test_named_secret_placeholders_are_clean(self):
        self.assertClean("ADMIN_PASS" + "=")
        self.assertClean("ADMIN_PASS" + "=<set-me>")
        self.assertClean("IP_SALT" + "=${IP_SALT}")
        self.assertClean("EDGE_SECRET" + "=$EDGE_SECRET")
        self.assertClean("ADMIN_PASS" + " = os.environ.get('ADMIN_PASS', '')")

    def test_token_key_value(self):
        self.assertRule("token_key_value", "api" + "_key: " + LONG20)
        self.assertClean("api" + "_key: ${API_KEY}")

    def test_connection_string(self):
        self.assertRule("connection_string", "postgres" + "://user:" + PASS_WORD + "@host/db")
        self.assertClean("https" + "://example.org/path")

    def test_aws_arn_account(self):
        self.assertRule("aws_arn_account", "cert " + ARN)
        self.assertClean("arn:aws:acm:eu-central-1:" + "<account>" + ":certificate/x")

    # ── персональні дані
    def test_phone_il(self):
        self.assertRule("phone_il", "call " + PHONE_IL)
        self.assertClean("version 0.4.0 build 12")

    def test_phone_ua(self):
        self.assertRule("phone_ua", "call " + PHONE_UA)
        self.assertClean("id 2026-09-13")

    def test_email(self):
        self.assertRule("email", "write " + MAIL)

    def test_email_fake_domains_are_clean(self):
        for domain in ("example.com", "example.org", "aluma.invalid", "box.test", "localhost"):
            self.assertClean("write " + "person" + "@" + domain)

    def test_json_pii(self):
        self.assertRule("json_pii", json.dumps({"name": PERSON, "phone": PHONE_IL}))
        self.assertClean(json.dumps({"name": PERSON, "consent": True}))

    def test_passport_number(self):
        self.assertRule("passport_number", "passport " + "AB" + DIGITS6)
        self.assertClean("passport of the owner")

    def test_tax_number(self):
        self.assertRule("tax_number", "ІПН " + DIGITS10)
        self.assertClean("ІПН не зберігаємо")

    def test_iban_ua(self):
        self.assertRule("iban_ua", "рахунок " + IBAN)

    def test_card_pan(self):
        self.assertRule("card_pan", "картка " + CARD)
        self.assertClean("version 1.2.3.4")

    # ── машина і фізичний доступ
    def test_host_security_detail(self):
        for term in ["Administrator" + "Access", "NO" + "PASSWD", "sudo " + "без пароля",
                     "admin" + ".sock", ":2019/" + "config", "hetzner" + "-box",
                     "delete" + "_repo", "admin" + ":org", "паці" + "єнтів",
                     "паци" + "енты", "Pati" + "ents"]:
            self.assertRule("host_security_detail", "row " + term + " here")

    def test_near_words_are_not_host_details(self):
        for text in ("administrator of the patio", "sudo is forbidden", "admin panel",
                     "password protected", "delete the repo branch", "impatient reader"):
            self.assertClean(text)

    def test_door_code(self):
        """Код замка прозою — саме ця форма коштувала бек-офісу кодів від дверей у документах."""
        self.assertRule("door_code", "door " + "code " + DIGITS4)
        self.assertRule("door_code", "Код дверей — " + DIGITS4)
        self.assertRule("door_code", "Код дверей, " + DIGITS4)

    def test_door_code_ignores_code_parameters(self):
        """`apt_code` — ім'я параметра в коді, а не код від дверей: `code` через підкреслення."""
        self.assertClean("PaymentRequest.create(apt" + "_code, 1000, 48)")

    def test_access_code_field(self):
        self.assertRule("access_code_field", "door" + "_code: " + DIGITS4)
        self.assertRule("access_code_field", "wifi" + "_password: \"" + PASS_WORD + "\"")

    def test_access_code_field_placeholders_are_clean(self):
        self.assertClean("door" + "_code: <set-me>")
        self.assertClean("wifi" + "_password = os.environ.get('WIFI')")

    def test_wifi_credentials(self):
        self.assertRule("wifi_credentials", "Wi" + "Fi: Guests / " + PASS_WORD)
        self.assertRule("wifi_credentials", "SS" + "ID Guests, пароль " + PASS_WORD)

    def test_wifi_credentials_ignores_parenthesis(self):
        self.assertClean("Wi" + "Fi пароль (задається в редагуванні кімнати)")

    # ── правила шляху
    def test_path_rules(self):
        cases = {
            ".env": "path_env_file",
            "deploy/box.env": "path_env_file",
            "infra/samconfig.toml": "path_samconfig",
            ".claude/settings.local.json": "path_claude_local",
            "dump/leads.jsonl": "path_dump",
            "data/aluma.db": "path_sqlite_db",
            "deploy/server.key": "path_key_file",
            "keys/id_rsa": "path_key_file",
        }
        for path, rule in cases.items():
            self.assertEqual(MOD._path_rule(path), rule, path)

    def test_path_rules_do_not_catch_examples(self):
        for path in ("deploy/aluma.env.example", "infra/samconfig.toml.example",
                     "site/assets/app.js", "docs/DELIVERY.md"):
            self.assertIsNone(MOD._path_rule(path), path)


class ScanCliTests(unittest.TestCase):
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
        lead = json.dumps(dict(name=PERSON, phone=PHONE_IL))
        commit(self.repo, {
            "app/config.py": "x = 1\nkey = '" + AWS_KEY + "'\n",
            "deploy/box.env.txt": "TELEGRAM_BOT_TOKEN" + "=" + TG_VALUE + "\n"
                                  + "ADMIN_PASS" + "=" + ADMIN_VALUE + "\n",
            "notes.md": "line one\nline two\ncall " + PHONE_IL + "\n",
            "bot.py": "url = 'https://api.telegram.org/bot" + TG_SHAPED + "/sendMessage'\n",
            "fixtures/lead.txt": lead + "\n",
            "infra/samconfig.toml": "x = 1\n",
            "infra/example.toml": "cert = \"" + ARN + "\"\n",
            "dump/x.jsonl": "{}\n",
            "data/a.db": b"SQLite format 3\x00\x00\x01",
        }, "dirty")
        # Друга гілка — `--all` мусить її бачити, а --rev main — ні.
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
        for rule in ("aws_access_key_id", "telegram_bot_token", "named_secret", "phone_il",
                     "json_pii", "aws_arn_account", "path_samconfig", "path_dump",
                     "path_sqlite_db"):
            self.assertIn(rule, report, rule)

    def test_stdout_has_no_paths_and_no_commits(self):
        """Журнал прогону Actions публічного репозиторію читає будь-хто: у stdout — лише числа."""
        self.dirty_history()
        code, out = run_scan("--repo", str(self.repo), "--report", str(self.report))
        self.assertEqual(code, 1, out)
        for needle in ("app/config.py", "side.txt", "notes.md", "dump/", "commit"):
            self.assertNotIn(needle, out, needle)
        self.assertRegex(out, r"(?m)^aws_access_key_id: \d+$")

    def test_report_has_rule_short_sha_path_line(self):
        self.dirty_history()
        run_scan("--repo", str(self.repo), "--mode", "history", "--report", str(self.report))
        report = self.report.read_text(encoding="utf-8")
        sha = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "--short=10", "side"],
                             capture_output=True, text=True, check=True).stdout.strip()
        # Рядок таблиці: | правило | шлях | збігів | довжини | відбитки | <коротке sha>:<рядок> |
        self.assertRegex(report, r"\| aws_access_key_id \| side\.txt \| 1 \|.*\| " + sha[:7]
                         + r"[0-9a-f]*:1 \|")
        self.assertRegex(report, r"\| phone_il \| notes\.md \| 1 \|.*:3 \|")
        self.assertRegex(report, r"\| aws_access_key_id \| app/config\.py \| 1 \|.*:2 \|")

    def test_report_fingerprints_only_high_entropy(self):
        """Відбиток дає звірити «той самий ключ», не знаючи ключа; для ПД його немає свідомо:
        простір із дев'яти цифр перебирається за секунди."""
        self.dirty_history()
        run_scan("--repo", str(self.repo), "--mode", "history", "--report", str(self.report))
        report = self.report.read_text(encoding="utf-8")
        key_row = [r for r in report.splitlines() if r.startswith("| aws_access_key_id | side.txt")]
        phone_row = [r for r in report.splitlines() if r.startswith("| phone_il | notes.md")]
        self.assertRegex(key_row[0], r"\| [0-9a-f]{12} \|")
        self.assertRegex(phone_row[0], r"\| - \|")

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

    def test_mode_tree_sees_only_current_files(self):
        self.dirty_history()
        code, out = run_scan("--repo", str(self.repo), "--mode", "tree", "--report", str(self.report))
        self.assertEqual(code, 1, out)
        report = self.report.read_text(encoding="utf-8")
        self.assertIn("bot.py", report)            # лишився в дереві
        self.assertNotIn("app/config.py", report)  # прибраний з дерева, але є в історії
        self.assertNotIn("side.txt", report)       # інша гілка

    def test_mode_blobs_sees_a_branch_that_history_of_main_does_not(self):
        self.dirty_history()
        run_scan("--repo", str(self.repo), "--mode", "history", "--rev", "main",
                 "--report", str(self.report))
        self.assertNotIn("side.txt", self.report.read_text(encoding="utf-8"))
        run_scan("--repo", str(self.repo), "--mode", "blobs", "--report", str(self.report))
        self.assertIn("side.txt", self.report.read_text(encoding="utf-8"))

    def test_rev_limits_the_scope(self):
        """Так відокремлюється публічна історія від приватного архіву (docs/security/…)."""
        self.dirty_history()
        code, out = run_scan("--repo", str(self.repo), "--mode", "history", "--rev", "side",
                             "--report", str(self.report))
        self.assertEqual(code, 1, out)
        self.assertIn("side.txt", self.report.read_text(encoding="utf-8"))
        run_scan("--repo", str(self.repo), "--mode", "history", "--rev=--all", "--rev=--not",
                 "--rev", "side", "--report", str(self.report))
        self.assertNotIn("side.txt", self.report.read_text(encoding="utf-8"))

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
        code, out = run_scan("--repo", str(self.repo), "--mode", "tree", "--logs", str(logs),
                             "--report", str(self.report))
        self.assertEqual(code, 1, out)
        report = self.report.read_text(encoding="utf-8")
        self.assertRegex(report, r"\| aws_access_key_id \| logs/123\.log \| 1 \|.*\| -:2 \|")
        self.assert_no_values(out + report)

    def test_scanner_and_its_test_do_not_flag_themselves(self):
        # Шаблони в коді сканера й значення в цьому тесті розбиті на частини — у звіті їх бути не повинно.
        for rel in ("scripts/secret_scan.py", "tests/test_secret_scan.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for no, line in enumerate(text.splitlines(), 1):
                self.assertEqual(MOD.scan_line(line), set(), f"{rel}:{no}")


class BaselineTests(unittest.TestCase):
    """Базова лінія: перелік уже переглянутих місць, щоб обов'язкова перевірка ловила НОВЕ.

    Без неї шоста перевірка була б червоною завжди (у дереві ALUMA 119 переглянутих місць:
    синтетичні телефони фікстур, зразки в документації, регулярки самого застосунку), а
    завжди червону перевірку люди вимикають — тобто скану не було б знову.
    """

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-scan-base-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        commit(self.repo, {"tests/fixture.py": "PHONE = \"" + PHONE_IL + "\"\n"}, "fixture")
        self.report = self.tmp / "report.md"
        self.baseline = self.tmp / "baseline.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def scan(self, *extra):
        return run_scan("--repo", str(self.repo), "--mode", "tree",
                        "--report", str(self.report), *extra)

    def test_update_writes_reviewed_places_without_values(self):
        code, out = self.scan("--baseline", str(self.baseline), "--update-baseline")
        self.assertEqual(code, 1, out)          # оновлення переліку не робить дерево чистим
        data = json.loads(self.baseline.read_text(encoding="utf-8"))
        self.assertEqual([(e["rule"], e["path"], e["count"]) for e in data["entries"]],
                         [("phone_il", "tests/fixture.py", 1)])
        self.assertNotIn(PHONE_IL, self.baseline.read_text(encoding="utf-8"))

    def test_known_place_is_green(self):
        self.scan("--baseline", str(self.baseline), "--update-baseline")
        code, out = self.scan("--baseline", str(self.baseline))
        self.assertEqual(code, 0, out)
        self.assertIn("відомих за базовою лінією: 1", out)

    def test_new_place_is_red_even_in_a_known_file(self):
        self.scan("--baseline", str(self.baseline), "--update-baseline")
        commit(self.repo, {"tests/fixture.py": "PHONE = \"" + PHONE_IL + "\"\nP2 = \""
                           + PHONE_IL + "\"\n"}, "one more")
        code, out = self.scan("--baseline", str(self.baseline))
        self.assertEqual(code, 1, out)
        self.assertIn("phone_il: 1", out)
        self.assert_report_has_only_the_new_line()

    def assert_report_has_only_the_new_line(self):
        report = self.report.read_text(encoding="utf-8")
        self.assertRegex(report, r"\| phone_il \| tests/fixture\.py \| 1 \|")
        self.assertIn("відомих за базовою лінією (не показані нижче): 1", report)

    def test_new_file_is_red(self):
        self.scan("--baseline", str(self.baseline), "--update-baseline")
        commit(self.repo, {"docs/note.md": "call " + PHONE_IL + "\n"}, "new file")
        code, out = self.scan("--baseline", str(self.baseline))
        self.assertEqual(code, 1, out)
        self.assertIn("docs/note.md", self.report.read_text(encoding="utf-8"))

    def test_stale_entry_is_reported_not_fatal(self):
        self.scan("--baseline", str(self.baseline), "--update-baseline")
        commit(self.repo, {"tests/fixture.py": "PHONE = \"\"\n"}, "cleanup")
        code, out = self.scan("--baseline", str(self.baseline))
        self.assertEqual(code, 0, out)
        self.assertIn("яких у дереві вже немає", self.report.read_text(encoding="utf-8"))

    def test_broken_baseline_is_exit_2(self):
        self.baseline.write_text("{not json", encoding="utf-8")
        code, _ = self.scan("--baseline", str(self.baseline))
        self.assertEqual(code, 2)

    def test_update_without_baseline_is_exit_2(self):
        code, _ = self.scan("--update-baseline")
        self.assertEqual(code, 2)


class RepositoryBaselineTests(unittest.TestCase):
    """Базова лінія самого репозиторію — файл, а не магія в CI."""

    BASELINE = ROOT / ".github" / "secret-scan-baseline.json"

    def test_file_is_lf_valid_json_without_values(self):
        raw = self.BASELINE.read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertTrue(raw.endswith(b"\n"))
        data = json.loads(raw.decode("utf-8"))
        self.assertTrue(data["entries"])
        for entry in data["entries"]:
            self.assertEqual(set(entry), {"rule", "path", "count"}, entry)
            self.assertIsInstance(entry["count"], int)
            self.assertGreater(entry["count"], 0)

    def test_known_rules_only(self):
        """Правило, якого в сканері немає, означало б мертвий запис — і тиху дірку."""
        known = {rule for rule, _ in MOD.CONTENT_RULES} | {
            "path_env_file", "path_samconfig", "path_claude_local", "path_dump",
            "path_sqlite_db", "path_key_file"}
        data = json.loads(self.BASELINE.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            self.assertIn(entry["rule"], known, entry["rule"])

    def test_the_worst_classes_are_never_baselined(self):
        """Ключ, приватний ключ, файл .env чи база — у переліку переглянутих бути не може."""
        data = json.loads(self.BASELINE.read_text(encoding="utf-8"))
        forbidden = {"aws_access_key_id", "aws_secret_access_key", "github_token", "private_key",
                     "llm_api_key", "google_api_key", "slack_token", "jwt", "iban_ua",
                     "path_env_file", "path_samconfig", "path_claude_local", "path_dump",
                     "path_sqlite_db", "path_key_file", "access_code_field", "wifi_credentials",
                     "door_code", "passport_number"}
        for entry in data["entries"]:
            self.assertNotIn(entry["rule"], forbidden, entry["path"])


if __name__ == "__main__":
    unittest.main()
