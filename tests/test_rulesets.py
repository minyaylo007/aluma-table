"""Правила репозиторію як файли: .github/rulesets/*.json.

Файли — це рівно те тіло, яке йде в `gh api -X POST repos/<owner>/<repo>/rulesets --input`.
Тест тримає їх разом з рештою дерева: обов'язкові перевірки master зіставляються з іменами
завдань `ci.yml`, тож перейменоване завдання не лишить правило з мертвою назвою.

Три правила, і в жодному немає обходу. Так вийшло не з вибору, а з відмови GitHub: у ЛИЧНОМУ
репозиторії застосунок GitHub Actions не можна дати в `bypass_actors` —
«Actor GitHub Actions integration must be part of the ruleset source or owner organization»
(422, перевірено 12.09.2026 обома файлами). Тому діє запасний варіант research.md R4:

| ruleset           | цілі                  | правила                              | обхід |
|-------------------|-----------------------|--------------------------------------|-------|
| `master`          | `refs/heads/master`   | PR, перевірки, `non_fast_forward`, `deletion` | немає |
| `tags-v-lock`     | `refs/tags/v*`        | `update`, `deletion`                 | немає |
| `production-lock` | `refs/heads/production` | `deletion`                         | немає |

Що це дає: у `master` нічого не потрапляє без PR і шести зелених перевірок; випущений тег `v*` не
перепише й не видалить НІХТО — навіть зламаний workflow; ветку `production` не видалить ніхто.
Конвеєр при цьому працює: `release.yml` тег **створює** (`creation` не обмежений), `deploy.yml`
двигає `refs/heads/production` (`update` і `non_fast_forward` не обмежені), і ні той, ні той нічого
не видаляє. Чого правила вже не тримають: людина може руками поставити тег `v*` і руками зсунути
`production` — це компенсує агент, який ставить лише коміт опублікованого тега `v*` з повним набором
файлів релізу й зійшлими сумами (`contracts/production-ref.md`, R4 «запасний варіант»).

Контракт — specs/001-release-pipeline/tasks.md T015, рішення — research.md R4,
живі докази — `verification.md`, розділ Phase 3.

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

ALL_NAMES = ("master", "tags-v-lock", "production-lock")


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
                         ["browser", "build", "lint", "secret-scan",
                          "test (3.12)", "test (3.13)"])

    def test_rule_demands_exactly_one(self):
        with self.assertRaises(AssertionError):
            rule({"rules": [{"type": "deletion"}, {"type": "deletion"}]}, "deletion")
        with self.assertRaises(AssertionError):
            rule({"rules": []}, "deletion")

    def test_rule_types_is_a_set_of_types(self):
        self.assertEqual(rule_types({"rules": [{"type": "a"}, {"type": "b"}]}), {"a", "b"})


class CommonTests(unittest.TestCase):

    def test_there_are_exactly_three_rulesets(self):
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

    def test_no_ruleset_has_any_bypass(self):
        """Обходу немає нікде — ні адміністратор, ні роль, ні ключ розгортання, ні застосунок.

        Це не суворість заради суворості: GitHub однаково не дає обходу для застосунку Actions в
        особистому репозиторії (422), а будь-який ІНШИЙ обхід тут означав би, що правило можна
        зняти руками — тобто правила немає.
        """
        for name in ALL_NAMES:
            self.assertEqual(load(name)["bypass_actors"], [], name)


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

    def test_nothing_can_demand_an_approval_behind_our_back(self):
        """GitHub підставляє require_extra_approval_for_unattributed_changes = true, якщо не задати.

        З ним PR, у якому є коміт із автором без прив'язаного акаунта GitHub (у нас це трейлер
        Co-Authored-By помічника), зависає в очікуванні схвалення — і авто-merge не спрацьовує,
        хоча схвалень потрібно нуль. Тому значення задане явно, а не лишене за замовчуванням.
        """
        params = rule(self.data, "pull_request")["parameters"]
        self.assertIs(params["require_extra_approval_for_unattributed_changes"], False)

    def test_required_status_checks_are_exactly_the_ci_jobs(self):
        params = rule(self.data, "required_status_checks")["parameters"]
        contexts = sorted(c["context"] for c in params["required_status_checks"])
        self.assertEqual(contexts, sorted(ci_check_names()))
        self.assertEqual(len(contexts), len(params["required_status_checks"]), "дублі контекстів")

    def test_secret_scan_is_a_required_check(self):
        """Названо явно: зіставлення з ci.yml вище зеленіло б і тоді, коли завдання прибрали з обох
        файлів одразу. Скан секретів — червона межа флоту, його не знімають ні тим, ні тим."""
        params = rule(self.data, "required_status_checks")["parameters"]
        contexts = {c["context"] for c in params["required_status_checks"]}
        self.assertIn("secret-scan", contexts)

    def test_smoke_is_not_a_required_check(self):
        """tests/smoke.spec.js пише в сховище — його в обов'язкових перевірках бути не може."""
        params = rule(self.data, "required_status_checks")["parameters"]
        for check in params["required_status_checks"]:
            self.assertNotIn("smoke", check["context"])

    def test_force_push_and_deletion_are_forbidden(self):
        self.assertIn("non_fast_forward", rule_types(self.data))
        self.assertIn("deletion", rule_types(self.data))


class TagsLockTests(unittest.TestCase):

    def setUp(self):
        self.data = load("tags-v-lock")

    def test_targets_version_tags(self):
        self.assertEqual(self.data["target"], "tag")
        self.assertEqual(self.data["conditions"]["ref_name"]["include"], ["refs/tags/v*"])
        self.assertEqual(self.data["conditions"]["ref_name"]["exclude"], [])

    def test_nobody_rewrites_or_deletes_a_released_tag(self):
        self.assertEqual(rule_types(self.data), {"update", "deletion"})

    def test_creation_is_not_restricted(self):
        """`creation` обмежувати НЕ можна: обходу для Actions немає, і конвеєр не поставив би тег."""
        self.assertNotIn("creation", rule_types(self.data))


class ProductionLockTests(unittest.TestCase):

    def setUp(self):
        self.data = load("production-lock")

    def test_targets_the_production_branch(self):
        self.assertEqual(self.data["target"], "branch")
        self.assertEqual(self.data["conditions"]["ref_name"]["include"], ["refs/heads/production"])
        self.assertEqual(self.data["conditions"]["ref_name"]["exclude"], [])

    def test_nobody_deletes_the_production_branch(self):
        self.assertEqual(rule_types(self.data), {"deletion"})

    def test_moving_the_ref_is_not_restricted(self):
        """`update` і `non_fast_forward` обмежувати НЕ можна: без обходу став би неможливим викат
        (і відкат, який є перезаписом назад). Захист переніс на себе агент — contracts/production-ref.md."""
        self.assertEqual(rule_types(self.data) & {"update", "non_fast_forward"}, set())


if __name__ == "__main__":
    unittest.main()
