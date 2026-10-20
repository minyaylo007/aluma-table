"""Інваріанти конвеєра — 15 тестів замість 78 «дзеркальних» (рішення власника 13.10.2026, P-2026-10-13-03).

Було: tests/test_workflows.py (46), tests/test_rulesets.py (20), tests/test_delivery_doc.py (12) — вони
повторювали YAML і JSON рядок у рядок, і кожна правка CI починалася з правки тестів. Лишилося те, що
справді не можна зламати непомітно: master захищений і без обходу, скан секретів іде завжди, перевірки
ruleset збігаються з завданнями ci.yml, права тільки на читання, actions закріплені, жодних секретів у
workflow, smoke не в CI, документ викату чесний. Старі файли — в історії: `git checkout <sha>^ -- tests/…`.

    python -m unittest tests.test_pipeline -v
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RULESETS = ROOT / ".github" / "rulesets"
DELIVERY = ROOT / "docs" / "DELIVERY.md"

ALLOWED_ACTIONS = {"actions/checkout@v6", "actions/setup-node@v6", "actions/setup-python@v6"}
LOCAL_WORKFLOWS = {"./.github/workflows/ci.yml", "./.github/workflows/deploy.yml"}
REQUIRED_CHECKS = ["browser", "build", "lint", "secret-scan", "test (3.12)", "test (3.13)"]


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def code(text: str) -> str:
    """Без рядків-коментарів: пояснення «smoke сюди не входить» — не порушення."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def top_block(text: str, key: str) -> str:
    """Блок верхнього рівня `key:` — до наступного ключа без відступу."""
    m = re.search(rf"^{re.escape(key)}:.*?(?=^\S)", text + "\nEND:\n", re.M | re.S)
    return m.group(0) if m else ""


def jobs(text: str) -> dict:
    """Імена завдань (відступ 2 під `jobs:`) → їхній текст."""
    block = top_block(text, "jobs")
    parts = re.split(r"^  ([A-Za-z_][\w-]*):\s*$", block, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def uses(text: str) -> set:
    return set(re.findall(r"^\s*(?:-\s*)?uses:\s*['\"]?([^\s'\"#]+)", text, re.M))


def ruleset(name: str) -> dict:
    return json.loads((RULESETS / f"{name}.json").read_text(encoding="utf-8"))


def rule(data: dict, type_: str) -> dict:
    found = [r for r in data["rules"] if r["type"] == type_]
    assert len(found) == 1, f"правило {type_}: {len(found)}"
    return found[0]


def ci_check_names() -> list:
    """Імена перевірок, які насправді віддає ci.yml: завдання, а матричні — «job (значення)»."""
    names = []
    for job, body in jobs(read("ci.yml")).items():
        matrix = re.search(r"python-version:\s*\[([^\]]*)\]", body)
        names += [f"{job} ({v})" for v in re.findall(r"'([^']+)'", matrix.group(1))] if matrix else [job]
    return sorted(names)


def git_ls_files(*args: str) -> list:
    out = subprocess.run(["git", "ls-files", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.split()


class CiTests(unittest.TestCase):
    def setUp(self):
        self.ci = read("ci.yml")
        self.jobs = jobs(self.ci)
        self.on = code(top_block(self.ci, "on"))

    def test_ci_runs_on_pull_request_nightly_and_from_release_only(self):
        """Один прогін на PR, нічний за розкладом, і виклик із release.yml — без дубля на push у гілку."""
        self.assertRegex(self.on, r"pull_request:\s*\n\s+branches:\s*\[\s*master\s*\]")
        self.assertIn("workflow_call:", self.on)
        self.assertRegex(self.on, r"schedule:\s*\n\s+-\s*cron:")
        self.assertNotRegex(self.on, r"^\s+push:", "push дублював би прогін PR")
        self.assertNotIn("workflow_dispatch", self.on)

    def test_every_master_commit_is_checked_by_release(self):
        """master без PR не буває, а кожен push у master проганяє ті самі перевірки через release.yml."""
        release = read("release.yml")
        self.assertRegex(code(top_block(release, "on")), r"push:\s*\n\s+branches:\s*\[\s*master\s*\]")
        self.assertRegex(jobs(release)["checks"], r"uses:\s*\./\.github/workflows/ci\.yml")
        self.assertRegex(jobs(release)["release"], r"needs:\s*\[?\s*checks\s*\]?\s*\n")

    def test_job_names_are_the_required_checks(self):
        self.assertEqual(ci_check_names(), REQUIRED_CHECKS)
        # Ім'я `test (3.12)` / `test (3.13)` дає GitHub сам — поле name перебило б його.
        self.assertNotRegex(self.jobs["test"], r"^    name:", "name перейменовує перевірку в ruleset")

    def test_secret_scan_always_own_scanner_report_private(self):
        """Правило флоту 13.09: скан секретів іде ЗАВЖДИ — без умови, без фільтра шляхів; сканер свій,
        звіт зі шляхами лишається в $RUNNER_TEMP (журнал публічного репозиторію читає весь світ)."""
        body = self.jobs["secret-scan"]
        self.assertNotRegex(body, r"^    if:", "умова вимкнула б скан")
        self.assertNotRegex(self.on, r"paths(-ignore)?:")
        for needle in ("scripts/secret_scan.py", "--mode tree", "--baseline .github/secret-scan-baseline.json",
                       '--report "$RUNNER_TEMP/'):
            self.assertIn(needle, body, needle)
        self.assertNotIn("upload-artifact", body)
        for tool in ("gitleaks", "trufflehog", "detect-secrets", "curl ", "wget "):
            self.assertNotIn(tool, code(self.ci).lower(), tool)

    def test_test_job_runs_the_whole_suite_from_pinned_files(self):
        body = self.jobs["test"]
        self.assertRegex(body, r"python-version:\s*\[\s*'3\.12'\s*,\s*'3\.13'\s*\]")
        self.assertIn("pip install -r api/requirements.txt -r tests/requirements.txt", body)
        self.assertIn("python -m unittest discover -s tests -t . -v", body)
        for args in re.findall(r"pip install(.*)$", code(self.ci), re.M):
            tokens = [t for t in args.split() if t not in ("-q", "--quiet")]
            self.assertTrue(tokens and len(tokens) % 2 == 0 and all(
                tokens[i] == "-r" for i in range(0, len(tokens), 2)), args)

    def test_browser_is_the_mocked_spec_and_smoke_is_nowhere(self):
        """tests/smoke.spec.js пише в сховище — ні в CI, ні в обов'язкових перевірках."""
        body = self.jobs["browser"]
        self.assertIn("--config playwright.local.config.js", body)
        self.assertIn("PREVIEW_PORT: '8007'", body)
        for name in ("ci.yml", "release.yml", "deploy.yml", "rollback.yml"):
            self.assertNotIn("smoke", code(read(name)), name)
        checks = rule(ruleset("master"), "required_status_checks")["parameters"]["required_status_checks"]
        self.assertFalse([c for c in checks if "smoke" in c["context"]])

    def test_build_twice_same_bytes_without_pillow(self):
        body = self.jobs["build"]
        self.assertGreaterEqual(body.count("python build.py"), 2)
        self.assertIn("sha256sum", body)
        self.assertNotRegex(code(self.ci), r"(?i)pillow|\bPIL\b")

    def test_browser_runs_the_a11y_spec(self):
        """Доступність (ת"י 5568, תקנה 35) — крок обов'язкової перевірки browser, а не окреме завдання."""
        body = code(self.jobs["browser"])
        self.assertIn("--config playwright.a11y.config.js", body)
        self.assertLess(body.index("python build.py"), body.index("playwright.a11y.config.js"))

    def test_browser_runs_the_responsive_spec(self):
        """Верстка на всіх ширинах (WCAG 1.4.10, 2.5.8, 2.4.7) — теж крок browser, після збірки."""
        body = code(self.jobs["browser"])
        self.assertIn("--config playwright.responsive.config.js", body)
        self.assertLess(body.index("python build.py"), body.index("playwright.responsive.config.js"))


class WorkflowSafetyTests(unittest.TestCase):
    NAMES = ("ci.yml", "release.yml", "deploy.yml", "rollback.yml")

    def test_read_only_pinned_actions_no_secrets(self):
        """Права лише читання (write — тільки в release/deploy за вимикачем), actions закріплені на v6,
        жодного `secrets.` у жодному workflow."""
        for name in self.NAMES:
            text = read(name)
            self.assertRegex(top_block(text, "permissions"), r"contents:\s*read", name)
            self.assertNotIn("write", top_block(text, "permissions"), name)
            self.assertLessEqual(uses(text) - LOCAL_WORKFLOWS, ALLOWED_ACTIONS, name)
            self.assertNotIn("secrets.", code(text), name)
            for job, body in jobs(text).items():
                if job not in ("release", "deploy"):
                    self.assertNotRegex(body, r":\s*write", f"{name}:{job}")

    def test_release_and_deploy_stay_behind_the_switch(self):
        """Без RELEASES_ENABLED=true після checks нічого не відбувається: ні тега, ні викату."""
        rel = jobs(read("release.yml"))
        self.assertRegex(rel["release"], r"(?m)^    if:\s*vars\.RELEASES_ENABLED == 'true'\s*$")
        self.assertRegex(rel["deploy"], r"needs:\s*\[?\s*release\s*\]?\s*\n")
        self.assertRegex(rel["deploy"], r"uses:\s*\./\.github/workflows/deploy\.yml")
        on = code(top_block(read("deploy.yml"), "on"))
        self.assertRegex(on, r"workflow_call:\s*\n\s+inputs:\s*\n\s+tag:")
        self.assertNotRegex(on, r"^\s*(push|pull_request|workflow_dispatch|schedule):")

    def test_rollback_is_manual_with_version_and_not_behind_the_switch(self):
        text = read("rollback.yml")
        on = code(top_block(text, "on"))
        self.assertRegex(on, r"workflow_dispatch:\s*\n\s+inputs:\s*\n\s+version:")
        for other in ("push", "pull_request", "workflow_call", "schedule"):
            self.assertNotRegex(on, rf"^\s+{other}:", other)
        self.assertNotIn("RELEASES_ENABLED", code(text))

    def test_no_tracked_file_is_ignored_and_npm_lock_is_tracked(self):
        """12.09.2026: package-lock.json був у .gitignore, `add -A` його викинув, browser упав на npm ci."""
        self.assertEqual(git_ls_files("-i", "-c", "--exclude-standard"), [])
        self.assertEqual(git_ls_files("package-lock.json"), ["package-lock.json"])


class RulesetTests(unittest.TestCase):
    """Правила репозиторію як файли — рівно те тіло, що йде в `gh api … /rulesets`."""

    def test_three_active_rulesets_and_no_bypass_anywhere(self):
        """Обходу немає нікому: GitHub не дає його для Actions в особистому репозиторії (422, 12.09),
        а будь-який інший означав би, що правило можна зняти руками."""
        self.assertEqual(sorted(p.stem for p in RULESETS.glob("*.json")),
                         ["master", "production-lock", "tags-v-lock"])
        for name in ("master", "tags-v-lock", "production-lock"):
            data = ruleset(name)
            self.assertEqual(data["name"], name)
            self.assertEqual(data["enforcement"], "active", name)
            self.assertEqual(data["bypass_actors"], [], name)

    def test_master_only_through_pr_with_the_six_ci_checks(self):
        data = ruleset("master")
        self.assertEqual(data["conditions"]["ref_name"]["include"], ["refs/heads/master"])
        pr = rule(data, "pull_request")["parameters"]
        self.assertEqual(pr["required_approving_review_count"], 0)
        self.assertEqual(pr["allowed_merge_methods"], ["squash"])
        # Без явного False GitHub вимагав би схвалення за трейлер Co-Authored-By — авто-merge зависав би.
        self.assertIs(pr["require_extra_approval_for_unattributed_changes"], False)
        checks = rule(data, "required_status_checks")["parameters"]["required_status_checks"]
        self.assertEqual(sorted(c["context"] for c in checks), ci_check_names())
        self.assertEqual(sorted(c["context"] for c in checks), REQUIRED_CHECKS)
        types = {r["type"] for r in data["rules"]}
        self.assertLessEqual({"non_fast_forward", "deletion"}, types)

    def test_released_tags_and_production_ref_are_locked_but_creatable(self):
        tags = ruleset("tags-v-lock")
        self.assertEqual(tags["conditions"]["ref_name"]["include"], ["refs/tags/v*"])
        self.assertEqual({r["type"] for r in tags["rules"]}, {"update", "deletion"})
        prod = ruleset("production-lock")
        self.assertEqual(prod["conditions"]["ref_name"]["include"], ["refs/heads/production"])
        self.assertEqual({r["type"] for r in prod["rules"]}, {"deletion"})


class DeliveryDocTests(unittest.TestCase):
    def test_delivery_doc_is_honest_linked_and_secret_free(self):
        """Два стани («Як зараз» / після T040), клон прода названий, посилання живі, старий AWS — факт,
        а не «видаляється», і жодного присвоєння секрету."""
        text = DELIVERY.read_text(encoding="utf-8")
        for needle in ("Як зараз", "Після установки агента (T040)", "563edc8", "rollback.yml", "ci.yml",
                       "release.yml", "pullagent.py", "docs/AWS-TEARDOWN.md"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("видаляється", text)
        for link in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
            if not re.match(r"^[a-z]+:", link):
                self.assertTrue((DELIVERY.parent / link).resolve().exists(), link)
        for name in ("ADMIN_PASS", "IP_SALT", "TELEGRAM_BOT_TOKEN", "EDGE_SECRET", "OWNER_TELEGRAM_CHAT_ID"):
            self.assertNotRegex(text, rf"\b{name}\s*=\s*\S", name)


if __name__ == "__main__":
    unittest.main()
