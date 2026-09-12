"""scripts/aws_inventory.py — лише читання AWS і чесне порівняння «до»/«після».

AWS тут не кличеться: перевіряється шлюз check_readonly() (до запуску процесу)
і compare() на синтетичних знімках.

    python -m unittest discover -s tests -p 'test_aws_inventory.py' -t .
"""

from __future__ import annotations

import copy
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import aws_inventory as inv  # noqa: E402


def before_snapshot():
    shared = {
        "stacks": ["aparts", "aparts-v2", "aparts-monitor", "aws-sam-cli-managed-default", inv.STACK],
        "cloudfront_distributions": ["E80XDWDORZKYP", "E3A58MFOU2LI12", inv.DISTRIBUTION],
        "cloudfront_distribution_detail": ["E80XDWDORZKYP cv.central-aparts.store Deployed True",
                                           "E3A58MFOU2LI12 www.central-aparts.store Deployed True",
                                           f"{inv.DISTRIBUTION} table.central-aparts.store Deployed True"],
        "cloudfront_functions": ["chernivtsi-guide-strip-prefix", inv.CF_FUNCTION],
        "cloudfront_oac": ["EOTHER", inv.OAC],
        "cloudfront_origin_request_policies": [inv.ORP],
        "lambda_functions": ["aparts-api", inv.FUNCTION],
        "iam_roles": ["aparts-role", inv.ROLE],
        # Імена синтетичні: справжні імена користувачів IAM сусідніх проєктів у публічний репозиторій не йдуть.
        "iam_users": ["aparts-deploy", "other-deploy-user"],
        "apigw_apis": [inv.API],
        "dynamodb_tables": ["aparts-bookings", *inv.TABLES],
        "log_groups": ["/aws/lambda/aparts-api", inv.LOG_GROUP],
        "acm_us_east_1": ["arn:other", inv.CERT],
        "acm_eu_central_1": [],
        "route53_records": ["central-aparts.store. A", "table.central-aparts.store. A",
                            "table-new.central-aparts.store. A", f"{inv.CNAME_NAME} CNAME"],
        "s3_buckets": [inv.SAM_BUCKET, inv.SITE_BUCKET],
        "secrets": ["aparts/x", inv.SECRET],
        "secrets_planned_deletion": [],
        "eventbridge_rules": [],
        "scheduler_schedules": ["aparts-monitor-daily-scan"],
        "budgets": ["aparts-monthly-10usd"],
        "sam_bucket_other_versions": {"count": 641, "sha256": "abc", "delete_markers": 0,
                                      "delete_markers_sha256": "e3b0"},
    }
    aluma = {
        "stack": {"name": inv.STACK}, "stack_resources": [], "site_bucket": {"name": inv.SITE_BUCKET},
        "distribution": {"id": inv.DISTRIBUTION}, "lambda": {"name": inv.FUNCTION},
        "iam_role": {"name": inv.ROLE}, "api": {"id": inv.API},
        "tables": {t: {"name": t} for t in inv.TABLES}, "log_group": {"name": inv.LOG_GROUP},
        "certificate": {"arn": inv.CERT}, "validation_cname": {"Name": inv.CNAME_NAME},
        "sam_artifacts": {"versions": [{"key": "fx-table/x"}], "delete_markers": []},
        "secret": {"name": inv.SECRET, "deleted_date": None},
    }
    http = [
        {"url": "https://central-aparts.store/", "status": 200},
        {"url": "https://table.central-aparts.store/", "status": 200},
        {"url": "https://table.central-aparts.store/api/fx/health", "status": 200, "version": "0.4.0-box"},
        {"url": "https://table.central-aparts.store/admin", "status": 303, "location": "/admin/login"},
    ]
    snap = {"shared": shared, "aluma": aluma, "http": http}
    snap["marker_hits"] = inv.marker_hits(shared)
    return snap


def after_snapshot(before):
    after = copy.deepcopy(before)
    for section, gone in inv.EXPECTED_GONE.items():
        after["shared"][section] = [v for v in after["shared"][section] if v not in gone]
    after["shared"]["cloudfront_distribution_detail"] = [
        d for d in after["shared"]["cloudfront_distribution_detail"] if not d.startswith(inv.DISTRIBUTION)]
    after["shared"]["secrets_planned_deletion"] = [inv.SECRET]
    a = after["aluma"]
    for k in ("stack", "site_bucket", "distribution", "lambda", "iam_role", "api", "log_group",
              "certificate", "validation_cname"):
        a[k] = None
    a["stack_resources"] = None
    a["tables"] = {t: None for t in inv.TABLES}
    a["sam_artifacts"] = {"versions": [], "delete_markers": []}
    a["secret"] = {"name": inv.SECRET, "deleted_date": "2026-09-11T20:00:00+03:00"}
    after["marker_hits"] = inv.marker_hits(after["shared"])
    return after


class ReadOnlyGateTests(unittest.TestCase):

    def test_reads_pass(self):
        for args in (("s3api", "list-object-versions"), ("cloudformation", "describe-stacks"),
                     ("lambda", "get-function"), ("secretsmanager", "describe-secret")):
            inv.check_readonly(args)

    def test_writes_and_secret_values_are_refused_before_any_process(self):
        with mock.patch.object(inv.subprocess, "run", side_effect=AssertionError("процес запущено")):
            for args in (("secretsmanager", "get-secret-value", "--secret-id", "x"),
                         ("cloudformation", "delete-stack", "--stack-name", "fx-table"),
                         ("s3", "rm", "s3://x", "--recursive"),
                         ("s3api", "delete-objects"), ("dynamodb", "delete-table"),
                         ("route53", "change-resource-record-sets"), ("acm", "delete-certificate"),
                         ("lambda", "update-function-code"), ("logs", "delete-log-group"),
                         ("s3api", "put-object"), ("sts",)):
                with self.assertRaises(ValueError, msg=args):
                    inv.aws(*args)

    def test_every_aws_call_in_the_script_is_a_read(self):
        text = (ROOT / "scripts" / "aws_inventory.py").read_text(encoding="utf-8")
        self.assertNotIn('"get-secret-value"', text.replace('op == "get-secret-value"', ""))
        for word in ("delete-", "put-", "update-", "create-", "change-", '"rm"', '"cp"', '"sync"'):
            self.assertNotIn(f'"{word}' if not word.startswith('"') else word, text, word)


class CompareTests(unittest.TestCase):

    def setUp(self):
        self.before = before_snapshot()
        self.after = after_snapshot(self.before)

    def run_compare(self):
        return inv.compare(self.before, self.after)

    def test_clean_teardown_is_green(self):
        lines, failed = self.run_compare()
        self.assertEqual(failed, [], "\n".join(lines))

    def test_foreign_resource_gone_is_red(self):
        self.after["shared"]["stacks"].remove("aparts")
        _, failed = self.run_compare()
        self.assertTrue(any(f.startswith("stacks:") for f in failed))

    def test_foreign_route53_record_gone_is_red(self):
        self.after["shared"]["route53_records"].remove("table.central-aparts.store. A")
        _, failed = self.run_compare()
        self.assertTrue(any(f.startswith("route53_records:") for f in failed))

    def test_aluma_leftover_is_red(self):
        self.after["shared"]["lambda_functions"].append(inv.FUNCTION)
        self.after["aluma"]["lambda"] = {"name": inv.FUNCTION}
        self.after["marker_hits"] = inv.marker_hits(self.after["shared"])
        _, failed = self.run_compare()
        self.assertTrue(any("лямбда" in f for f in failed))
        self.assertTrue(any("маркерами" in f for f in failed))

    def test_secret_must_be_scheduled_not_just_present(self):
        self.after["aluma"]["secret"]["deleted_date"] = None
        _, failed = self.run_compare()
        self.assertTrue(any("секрет" in f for f in failed))

    def test_other_sam_versions_changed_is_red(self):
        self.after["shared"]["sam_bucket_other_versions"] = dict(
            self.before["shared"]["sam_bucket_other_versions"], count=640, sha256="zzz")
        _, failed = self.run_compare()
        self.assertTrue(any("SAM" in f for f in failed))

    def test_foreign_distribution_state_changed_is_red(self):
        detail = self.after["shared"]["cloudfront_distribution_detail"]
        detail[detail.index("E80XDWDORZKYP cv.central-aparts.store Deployed True")] = \
            "E80XDWDORZKYP cv.central-aparts.store InProgress True"
        _, failed = self.run_compare()
        self.assertTrue(any("дистрибуції" in f for f in failed))

    def test_prod_checks(self):
        for h in self.after["http"]:
            if h["url"].endswith("/api/fx/health"):
                h["version"] = "0.4.0"
        _, failed = self.run_compare()
        self.assertTrue(any("health" in f for f in failed))

    def test_new_foreign_items_are_reported_not_failed(self):
        self.after["shared"]["log_groups"].append("/aws/lambda/aparts-new")
        lines, failed = self.run_compare()
        self.assertEqual(failed, [])
        self.assertTrue(any("aparts-new" in l for l in lines))


if __name__ == "__main__":
    unittest.main(verbosity=2)
