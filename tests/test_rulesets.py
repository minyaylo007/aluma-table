"""Правила репозиторію як файли: .github/rulesets/*.json.

Файли — це рівно те тіло, яке йде в `gh api -X POST repos/<owner>/<repo>/rulesets --input`.
Тест тримає їх разом з рештою дерева: обов'язкові перевірки master зіставляються з іменами
завдань `ci.yml`, тож перейменоване завдання не лишить правило з мертвою назвою.

П'ять правил, бо обхід у GitHub задається на весь ruleset, а не на окреме правило, а R4 вимагає
різного обходу для різних дій. Тому кожна пара розбита на «робоче» правило з обходом для
застосунку GitHub Actions і «замок» без обходу взагалі:

| ruleset           | цілі             | правила                    | обхід    |
|-------------------|------------------|----------------------------|----------|
| `master`          | `master`         | PR, перевірки, force, del  | немає    |
| `tags-v`          | `refs/tags/v*`   | `creation`                 | Actions  |
| `tags-v-lock`     | `refs/tags/v*`   | `update`, `deletion`       | немає    |
| `production`      | `production`     | `update`, `non_fast_forward` | Actions |
| `production-lock` | `production`     | `deletion`                 | немає    |

Тобто тег ставить лише конвеєр, а переписати чи видалити випущену версію не може НІХТО — навіть
зламаний workflow із вбудованим `GITHUB_TOKEN`. Те саме для видалення ветки `production`, тоді як
її перезапис назад (відкат) конвеєру лишається дозволеним.

Контракт — specs/001-release-pipeline/tasks.md T015, рішення — research.md R4.

    python -m unittest tests.test_rulesets -v
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

from tests.test_workflows import jobs, read

ROOT = pathlib.Path(__file__).resolve().parents[1]
RULESETS = ROOT / ".github" / "rulesets"

# Застосунок GitHub Actions: єдиний, кому взагалі дозволено обходити правила (вбудований
# GITHUB_TOKEN завдань release/deploy/rollback). id — стабільний у GitHub, gh api /apps/github-actions.
ACTIONS_APP_ID = 15368

# Хто має обхід, а хто ні. Замки без обходу — суть п'ятифайлової розкладки, тому це окремий факт.
WITH_BYPASS = ("tags-v", "production")
WITHOUT_BYPASS = ("master", "tags-v-lock", "production-lock")
ALL_NAMES = WITHOUT_BYPASS + WITH_BYPASS


def load(name: str) -> dict:
    return json.loads((RULESETS / f"{name}.json").read_text(encoding="utf-8"))


def rule_types(ruleset: dict) -> set:
    return {r["type"] for r in ruleset["rules"]}


def rule(ruleset: dict, type_: str) -> dict:
    found = [r for r in ruleset["rules"] if r["type"] == type_]
    if len(found) != 1:
        raise AssertionError(f"правило {type_}: знайдено {len(found)}, очікувалося 1")
    return found[0]


def ci_check_names() -> list:
    """Імена перевірок, які насправді віддає ci.yml: завдання, а матричні — «job (значення)»."""
    names = []
    for job, body in jobs(read("ci.yml")).items():
        matrix = re.search(r"python-version:\s*\[([^\]]*)\]", body)
        if matrix:
            names += [f"{job} ({v})" for v in re.findall(r"'([^']+)'", matrix.group(1))]
        else:
            names.append(job)
    return names


class HelperTests(unittest.TestCase):
    """Помічники самі мають червоні випадки — інакше зіставлення з ci.yml могло б зеленіти порожнім."""

    def test_ci_check_names_reads_the_matrix(self):
        self.assertEqual(sorted(ci_check_names()),
                         ["browser", "build", "lint", "test (3.12)", "test (3.13)"])

    def test_rule_demands_exactly_one(self):
        with self.assertRaises(AssertionError):
            rule({"rules": [{"type": "deletion"}, {"type": "deletion"}]}, "deletion")
        with self.assertRaises(AssertionError):
            rule({"rules": []}, "deletion")

    def test_rule_types_is_a_set_of_types(self):
        self.assertEqual(rule_types({"rules": [{"type": "a"}, {"type": "b"}]}), {"a", "b"})


class CommonTests(unittest.TestCase):

    def test_there_are_exactly_five_rulesets(self):
        """Файл, доданий без тесту, лишився б без перевірки — тому перелік закритий."""
        present = sorted(p.stem for p in RULESETS.glob("*.json"))
        self.assertEqual(present, sorted(ALL_NAMES))

    def test_files_are_lf_and_valid_json(self):
        for name in ALL_NAMES:
            raw = (RULESETS / f"{name}.json").read_bytes()
            self.assertNotIn(b"\r", raw, name)
            self.assertTrue(raw.endswith(b"\n"), name)
            json.loads(raw.decode("utf-8"))

    def test_name_matches_file_and_enforcement_is_active(self):
        for name in ALL_NAMES:
            data = load(name)
            self.assertEqual(data["name"], name)
            self.assertEqual(data["enforcement"], "active", name)

    def test_locks_have_no_bypass_at_all(self):
        """Замок без обходу — єдине, що зупиняє зламаний workflow. Порожній список тут обов'язковий."""
        for name in WITHOUT_BYPASS:
            self.assertEqual(load(name)["bypass_actors"], [], name)

    def test_the_only_bypass_anywhere_is_the_actions_app(self):
        """Ні адміністратор, ні роль, ні ключ розгортання — лише застосунок Actions, і лише де треба."""
        for name in ALL_NAMES:
            for actor in load(name)["bypass_actors"]:
                self.assertEqual(actor["actor_type"], "Integration", name)
                self.assertEqual(actor["actor_id"], ACTIONS_APP_ID, name)
                self.assertEqual(actor["bypass_mode"], "always", name)
        for name in WITH_BYPASS:
            self.assertEqual(len(load(name)["bypass_actors"]), 1, name)

    def test_a_pair_covers_the_same_refs(self):
        """Замок без тієї самої умови нічого не замикає."""
        for work, lock in (("tags-v", "tags-v-lock"), ("production", "production-lock")):
            self.assertEqual(load(work)["conditions"], load(lock)["conditions"])
            self.assertEqual(load(work)["target"], load(lock)["target"])

    def test_a_pair_does_not_repeat_the_same_rule(self):
        """Те саме правило в обох файлах пари зробило б обхід у «робочому» безглуздим."""
        for work, lock in (("tags-v", "tags-v-lock"), ("production", "production-lock")):
            self.assertEqual(rule_types(load(work)) & rule_types(load(lock)), set(),
                             f"{work} і {lock} перекриваються")


class MasterTests(unittest.TestCase):

    def setUp(self):
        self.data = load("master")

    def test_targets_only_master(self):
        self.assertEqual(self.data["target"], "branch")
        self.assertEqual(self.data["conditions"]["ref_name"]["include"], ["refs/heads/master"])
        self.assertEqual(self.data["conditions"]["ref_name"]["exclude"], [])

    def test_pull_request_with_zero_approvals_and_squash_only(self):
        params = rule(self.data, "pull_request")["parameters"]
        self.assertEqual(params["required_approving_review_count"], 0)
        self.assertEqual(params["allowed_merge_methods"], ["squash"])

    def test_required_status_checks_are_exactly_the_ci_jobs(self):
        params = rule(self.data, "required_status_checks")["parameters"]
        contexts = sorted(c["context"] for c in params["required_status_checks"])
        self.assertEqual(contexts, sorted(ci_check_names()))
        self.assertEqual(len(contexts), len(params["required_status_checks"]), "дублі контекстів")

    def test_smoke_is_not_a_required_check(self):
        """tests/smoke.spec.js пише в сховище — його в обов'язкових перевірках бути не може."""
        params = rule(self.data, "required_status_checks")["parameters"]
        for check in params["required_status_checks"]:
            self.assertNotIn("smoke", check["context"])

    def test_force_push_and_deletion_are_forbidden(self):
        self.assertIn("non_fast_forward", rule_types(self.data))
        self.assertIn("deletion", rule_types(self.data))


class TagsTests(unittest.TestCase):

    def test_both_rulesets_target_version_tags(self):
        for name in ("tags-v", "tags-v-lock"):
            data = load(name)
            self.assertEqual(data["target"], "tag", name)
            self.assertEqual(data["conditions"]["ref_name"]["include"], ["refs/tags/v*"], name)
            self.assertEqual(data["conditions"]["ref_name"]["exclude"], [], name)

    def test_only_the_pipeline_creates_a_version_tag(self):
        self.assertEqual(rule_types(load("tags-v")), {"creation"})

    def test_nobody_rewrites_or_deletes_a_released_tag(self):
        self.assertEqual(rule_types(load("tags-v-lock")), {"update", "deletion"})


class ProductionTests(unittest.TestCase):

    def test_both_rulesets_target_the_production_branch(self):
        for name in ("production", "production-lock"):
            data = load(name)
            self.assertEqual(data["target"], "branch", name)
            self.assertEqual(data["conditions"]["ref_name"]["include"], ["refs/heads/production"], name)
            self.assertEqual(data["conditions"]["ref_name"]["exclude"], [], name)

    def test_only_the_pipeline_moves_the_ref_in_either_direction(self):
        """Відкат — це перезапис назад, тому обхід non_fast_forward конвеєру потрібен."""
        self.assertEqual(rule_types(load("production")), {"update", "non_fast_forward"})

    def test_nobody_deletes_the_production_branch(self):
        self.assertEqual(rule_types(load("production-lock")), {"deletion"})


if __name__ == "__main__":
    unittest.main()
