"""Текстові інваріанти workflow GitHub Actions (contracts/workflows.md) — без бібліотеки YAML.

Перевіряється те, що легко зламати непомітно: права, тригери, закріплені версії actions,
залежності лише з файлів, імена завдань (їх чекає ruleset master), відсутність smoke і секретів.

    python -m unittest tests.test_workflows -v
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

ALLOWED_ACTIONS = {"actions/checkout@v6", "actions/setup-node@v6", "actions/setup-python@v6"}


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def top_block(text: str, key: str) -> str:
    """Блок верхнього рівня `key:` — до наступного ключа без відступу."""
    m = re.search(rf"^{re.escape(key)}:.*?(?=^\S)", text + "\nEND:\n", re.M | re.S)
    return m.group(0) if m else ""


def jobs(text: str) -> dict:
    """Імена завдань (відступ 2 під `jobs:`) → їхній текст."""
    block = top_block(text, "jobs")
    parts = re.split(r"^  ([A-Za-z_][\w-]*):\s*$", block, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def code(text: str) -> str:
    """Текст без рядків-коментарів: пояснення в коментарі («smoke сюди не входить») — не порушення."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def uses(text: str) -> list:
    return re.findall(r"^\s*(?:-\s*)?uses:\s*['\"]?([^\s'\"#]+)", text, re.M)


def pip_installs(text: str) -> list:
    return [m.group(1).strip() for m in re.finditer(r"pip install(.*)$", text, re.M)]


def only_requirement_files(args: str) -> bool:
    tokens = args.split()
    tokens = [t for t in tokens if t not in ("-q", "--quiet", "--disable-pip-version-check")]
    if not tokens or len(tokens) % 2:
        return False
    return all(tokens[i] == "-r" and not tokens[i + 1].startswith("-") for i in range(0, len(tokens), 2))


class HelperTests(unittest.TestCase):
    """Помічники самі мають червоні випадки — інакше тести нижче могли б зеленіти порожньо."""

    def test_pip_args(self):
        self.assertTrue(only_requirement_files("-r api/requirements.txt -r tests/requirements.txt"))
        self.assertFalse(only_requirement_files("-r api/requirements.txt werkzeug"))
        self.assertFalse(only_requirement_files("'werkzeug>=2.3' boto3"))
        self.assertFalse(only_requirement_files(""))

    def test_jobs_parser(self):
        text = "on: push\njobs:\n  a:\n    runs-on: x\n  b-c:\n    steps: []\n"
        self.assertEqual(set(jobs(text)), {"a", "b-c"})


class CiYmlTests(unittest.TestCase):
    def setUp(self):
        self.text = read("ci.yml")
        self.jobs = jobs(self.text)

    def test_default_permissions_read_only(self):
        block = top_block(self.text, "permissions")
        self.assertRegex(block, r"contents:\s*read")
        self.assertNotRegex(block, r"write")
        for name, body in self.jobs.items():
            self.assertNotRegex(body, r":\s*write", name)

    def test_triggers(self):
        on = code(top_block(self.text, "on"))
        self.assertRegex(on, r"pull_request:\s*\n\s+branches:\s*\[\s*master\s*\]")
        self.assertRegex(on, r"workflow_call:")
        self.assertNotIn("workflow_dispatch", on)

    def test_every_master_push_is_checked(self):
        """Жоден коміт у master без перевірок: або release.yml викликає ci.yml (тоді ci.yml сам master
        пропускає, щоб не ганяти двічі), або — поки release.yml немає — push ci.yml без фільтра гілок."""
        on = code(top_block(self.text, "on"))
        release = WORKFLOWS / "release.yml"
        if release.exists() and "uses: ./.github/workflows/ci.yml" in read("release.yml"):
            self.assertRegex(on, r"push:\s*\n\s+branches-ignore:\s*\[\s*master\s*\]")
        else:
            push = re.search(r"^  push:(.*?)(?=^  \S|\Z)", on, re.M | re.S)
            self.assertIsNotNone(push, "без release.yml ci.yml мусить ловити push")
            self.assertNotRegex(push.group(1), r"branches", "без release.yml master має перевірятися ci.yml")

    def test_concurrency_cancels_only_outside_master(self):
        block = top_block(self.text, "concurrency")
        self.assertIn("group: ci-${{ github.workflow }}-${{ github.ref }}", block)
        self.assertIn("cancel-in-progress: ${{ github.ref != 'refs/heads/master' }}", block)

    def test_only_pinned_v6_actions(self):
        found = uses(self.text)
        self.assertTrue(found)
        self.assertLessEqual(set(found), ALLOWED_ACTIONS)
        self.assertIn("actions/setup-python@v6", found)

    def test_pip_installs_only_from_files(self):
        installs = pip_installs(self.text)
        self.assertTrue(installs)
        for args in installs:
            self.assertTrue(only_requirement_files(args), args)

    def test_job_names_are_the_required_checks(self):
        self.assertEqual(set(self.jobs), {"lint", "test", "build", "browser"})
        self.assertRegex(self.jobs["test"], r"python-version:\s*\[\s*['\"]3\.12['\"]\s*,\s*['\"]3\.13['\"]\s*\]")
        # Ім'я `test (3.12)` / `test (3.13)` дає GitHub сам — поле name перебило б його.
        self.assertNotRegex(self.jobs["test"], r"^    name:", "name перейменовує перевірку в ruleset")

    def test_lint_job(self):
        body = self.jobs["lint"]
        self.assertIn("-r requirements-lint.txt", body)
        self.assertIn("ruff check .", body)
        self.assertIn("node --check", body)

    def test_test_job_runs_full_suite(self):
        self.assertIn("-r api/requirements.txt -r tests/requirements.txt", self.jobs["test"])
        self.assertIn("python -m unittest discover -s tests -t . -v", self.jobs["test"])

    def test_build_job_twice_same_sums_no_pillow(self):
        body = self.jobs["build"]
        self.assertGreaterEqual(body.count("python build.py"), 2)
        self.assertIn("sha256sum", body)
        self.assertNotRegex(code(self.text), r"(?i)pillow|\bPIL\b")

    def test_browser_job_mocked_spec_on_8007(self):
        body = self.jobs["browser"]
        self.assertIn("npm ci", body)
        self.assertIn("PREVIEW_PORT: '8007'", body)
        self.assertIn("--config playwright.local.config.js", body)

    def test_no_smoke_and_no_secrets(self):
        self.assertNotIn("smoke.spec.js", code(self.text))
        self.assertNotIn("smoke", self.jobs)
        self.assertNotIn("secrets.", code(self.text))


class ReleaseYmlTests(unittest.TestCase):
    def setUp(self):
        self.text = read("release.yml")
        self.jobs = jobs(self.text)

    def test_trigger_push_to_master_only(self):
        on = code(top_block(self.text, "on"))
        self.assertRegex(on, r"push:\s*\n\s+branches:\s*\[\s*master\s*\]")
        self.assertNotIn("pull_request", on)
        self.assertNotIn("workflow_dispatch", on)

    def test_checks_call_ci(self):
        self.assertRegex(self.jobs["checks"], r"uses:\s*\./\.github/workflows/ci\.yml")

    def test_release_needs_checks(self):
        self.assertRegex(self.jobs["release"], r"needs:\s*\[?\s*checks\s*\]?\s*\n")

    def test_write_rights_only_in_release_job(self):
        self.assertRegex(top_block(self.text, "permissions"), r"contents:\s*read")
        self.assertNotIn("write", top_block(self.text, "permissions"))
        body = self.jobs["release"]
        self.assertRegex(body, r"permissions:\s*\n\s+contents:\s*write\s*\n\s+pull-requests:\s*read")
        for name, other in self.jobs.items():
            if name not in ("release", "deploy"):
                self.assertNotRegex(other, r":\s*write", name)

    def test_release_concurrency_without_cancel(self):
        body = self.jobs["release"]
        self.assertRegex(body, r"concurrency:\s*\n\s+group:\s*release-production\s*\n\s+cancel-in-progress:\s*false")

    def test_release_uses_project_scripts(self):
        body = code(self.jobs["release"])
        self.assertIn("scripts/next_version.py", body)
        self.assertIn("scripts/release_build.py", body)
        self.assertIn("--sha \"$GITHUB_SHA\"", body)
        self.assertIn("gh release create", body)
        self.assertIn("repos/$GITHUB_REPOSITORY/commits/$GITHUB_SHA/pulls", body)

    def test_release_switch(self):
        """Вимикач релізів: без змінної RELEASES_ENABLED=true виконується лише checks — release (і все, що після
        нього) у GitHub показується skipped, тег не створюється."""
        self.assertRegex(self.jobs["release"], re.compile(r"^    if:\s*vars\.RELEASES_ENABLED == 'true'\s*$", re.M))
        for name, body in self.jobs.items():
            if name in ("checks", "release"):
                continue
            gated = re.search(r"^    if:\s*vars\.RELEASES_ENABLED == 'true'", body, re.M) or \
                re.search(r"^    needs:.*\brelease\b", body, re.M)
            self.assertTrue(gated, f"{name} мусить стояти за вимикачем або за release")

    def test_switch_regex_is_not_vacuous(self):
        self.assertIsNone(re.search(r"^    if:\s*vars\.RELEASES_ENABLED == 'true'", "    if: always()", re.M))

    def test_only_pinned_actions_and_no_secrets(self):
        found = set(uses(self.text)) - {"./.github/workflows/ci.yml", "./.github/workflows/deploy.yml"}
        self.assertLessEqual(found, ALLOWED_ACTIONS)
        self.assertNotIn("secrets.", code(self.text))
        for args in pip_installs(self.text):
            self.assertTrue(only_requirement_files(args), args)


class DeployYmlTests(unittest.TestCase):
    def setUp(self):
        self.text = read("deploy.yml")
        self.jobs = jobs(self.text)
        self.release = jobs(read("release.yml"))

    def test_called_with_tag(self):
        on = code(top_block(self.text, "on"))
        self.assertRegex(on, r"workflow_call:\s*\n\s+inputs:\s*\n\s+tag:")
        self.assertNotRegex(on, r"^\s*(push|pull_request|workflow_dispatch):", )

    def test_single_deploy_job_in_production(self):
        self.assertEqual(set(self.jobs), {"deploy"})
        self.assertRegex(self.jobs["deploy"], r"environment:\s*\n\s+name:\s*production")

    def test_concurrency_cancels_older_deploy(self):
        self.assertRegex(self.jobs["deploy"],
                         r"concurrency:\s*\n\s+group:\s*deploy-production\s*\n\s+cancel-in-progress:\s*true")

    def test_only_contents_write(self):
        self.assertRegex(top_block(self.text, "permissions"), r"contents:\s*read")
        perms = re.search(r"^    permissions:\s*\n((?:      .*\n)+)", self.jobs["deploy"], re.M)
        self.assertIsNotNone(perms)
        self.assertEqual(perms.group(1).split(), ["contents:", "write"])

    def test_moves_production_ref(self):
        self.assertRegex(code(self.jobs["deploy"]), r"git push --force origin \S+:refs/heads/production")

    def test_watches_public_health_for_version_and_sha(self):
        body = code(self.jobs["deploy"])
        self.assertIn("vars.ALUMA_HEALTH_URL", body)
        self.assertIn("version", body)
        self.assertIn("git_sha", body)
        self.assertRegex(body, r"\b900\b", "таймаут наглядача — 15 хв (900 с)")
        self.assertRegex(self.jobs["deploy"], r"timeout-minutes:\s*20")

    def test_checks_release_files_before_moving_ref(self):
        body = code(self.jobs["deploy"])
        self.assertIn("SHA256SUMS", body)
        self.assertLess(body.index("SHA256SUMS"), body.index("refs/heads/production"))

    def test_release_yml_calls_deploy_after_release(self):
        body = self.release["deploy"]
        self.assertRegex(body, r"needs:\s*\[?\s*release\s*\]?\s*\n")
        self.assertRegex(body, r"uses:\s*\./\.github/workflows/deploy\.yml")
        self.assertRegex(body, r"tag:\s*\$\{\{\s*needs\.release\.outputs\.tag\s*\}\}")

    def test_only_pinned_actions_and_no_secrets(self):
        self.assertLessEqual(set(uses(self.text)), ALLOWED_ACTIONS)
        self.assertNotIn("secrets.", code(self.text))


class RollbackYmlTests(unittest.TestCase):
    """Відкат — одна дія (FR-022…FR-024). Рішення диригента 2026-09-11: відкат НЕ за вимикачем випуску (вимикач
    вимикають саме при поганій версії), а щось робить лише коли refs/heads/production уже існує."""

    def setUp(self):
        self.text = read("rollback.yml")
        self.jobs = jobs(self.text)

    def test_manual_dispatch_only_with_required_version(self):
        on = code(top_block(self.text, "on"))
        self.assertRegex(on, r"workflow_dispatch:\s*\n\s+inputs:\s*\n\s+version:")
        self.assertRegex(on, r"required:\s*true")
        for other in ("push", "pull_request", "workflow_call", "schedule"):
            self.assertNotRegex(on, rf"^\s+{other}:", other)

    def test_jobs(self):
        self.assertEqual(set(self.jobs), {"validate", "deploy"})

    def test_version_pattern_checked_first(self):
        body = code(self.jobs["validate"])
        pattern = r"^v[0-9]+\.[0-9]+\.[0-9]+$"
        self.assertIn(pattern, body)
        self.assertLess(body.index(pattern), body.index("heads/production"))

    def test_without_production_ref_nothing_happens(self):
        body = code(self.jobs["validate"])
        self.assertIn("git/ref/heads/production", body)
        self.assertIn("ready=false", body)
        # «відкатувати нічого» — завершення з кодом 0 ДО перевірок тегу й будь-якого деплою
        missing = body.index("ready=false")
        self.assertRegex(body[missing:missing + 80], r"exit 0")
        self.assertLess(missing, body.index("git/ref/tags"))
        self.assertRegex(self.jobs["deploy"], r"^    if:\s*needs\.validate\.outputs\.ready == 'true'\s*$".replace("^", "(?m)^"))

    def test_validate_checks_tag_and_both_files_before_deploy(self):
        body = code(self.jobs["validate"])
        self.assertIn("git/ref/tags/", body)
        self.assertIn("SHA256SUMS", body)
        self.assertIn("aluma-$VERSION.tar.gz", body)
        self.assertRegex(self.jobs["deploy"], r"needs:\s*\[?\s*validate\s*\]?\s*\n")
        self.assertRegex(self.jobs["deploy"], r"uses:\s*\./\.github/workflows/deploy\.yml")
        self.assertRegex(self.jobs["deploy"], r"tag:\s*\$\{\{\s*needs\.validate\.outputs\.tag\s*\}\}")

    def test_validate_cannot_write(self):
        self.assertRegex(top_block(self.text, "permissions"), r"contents:\s*read")
        self.assertNotIn("write", top_block(self.text, "permissions"))
        self.assertNotRegex(self.jobs["validate"], r":\s*write")
        self.assertNotIn("git push", code(self.jobs["validate"]))

    def test_not_behind_release_switch(self):
        self.assertNotIn("RELEASES_ENABLED", code(self.text))

    def test_no_secrets_no_foreign_actions(self):
        self.assertNotIn("secrets.", code(self.text))
        self.assertLessEqual(set(uses(self.text)) - {"./.github/workflows/deploy.yml"}, ALLOWED_ACTIONS)


if __name__ == "__main__":
    unittest.main()
