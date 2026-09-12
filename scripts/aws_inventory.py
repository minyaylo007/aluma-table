#!/usr/bin/env python3
"""Опис старого AWS ALUMA «до» і «після» видалення — лише читанням.

    python3 scripts/aws_inventory.py snapshot --label before --out docs/aws-teardown/before-<дата>.json
    python3 scripts/aws_inventory.py snapshot --label after  --out docs/aws-teardown/after-<дата>.json
    python3 scripts/aws_inventory.py compare docs/aws-teardown/before-<дата>.json docs/aws-teardown/after-<дата>.json

snapshot знімає дві частини:

  * aluma — усе, що підлягає видаленню, з ідентифікаторами (docs/AWS-TEARDOWN.md);
  * shared — усе спільне поруч, списками імен/id, щоб «після» можна було звірити
    рівністю: зі списків мають зникнути рівно id ALUMA і більше нічого.

Плюс пошук за маркерами ALUMA (fx-table, fx_, aluma, table.central-aparts.store,
E21KNA4YOX9CIB, r7jel27uma, d2a264f2) по всіх зібраних іменах.

compare друкує вердикт: кожен id ALUMA зник (секрет — лише «заплановано до
видалення»), кожне спільне ім'я на місці. Код 0 — ЗЕЛЕНО, 1 — ЧЕРВОНО.

Запис у AWS цей скрипт не робить ніколи: кожен виклик проходить через aws(),
яка пускає лише list-*/describe-*/get-* і забороняє get-secret-value. Значення
секретів не читаються; з get-function береться лише кілька полів, а з Environment —
тільки APP_VERSION (решта змінних — секрети, їх запит не вибирає).
Потрібен AWS CLI v2 з обліковими даними на читання.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Обліковий запис AWS замаскований перед публікацією репозиторію (12.09.2026): стек fx-table
# видалений, скрипт лишається як історія. Справжнє значення — в архіві aluma-table-archive-2026-09.
ACCOUNT = "000000000000"
REGION = "eu-central-1"
ZONE = "Z05565972H1DV59U5PO4I"
STACK = "fx-table"
SITE_BUCKET = f"fx-table-site-{ACCOUNT}"
SAM_BUCKET = "aws-sam-cli-managed-default-samclisourcebucket-tqh5bzqhj11n"
SAM_PREFIX = "fx-table/"
DISTRIBUTION = "E21KNA4YOX9CIB"
CF_FUNCTION = "fx-table-index-rewrite"
OAC = "E2KHW7MW8K25XT"
ORP = "a121b12a-5351-48b8-bc6d-c54e85b46b77"
FUNCTION = "fx-table-api"
ROLE = "fx-table-FxApiRole-BiE09PLkm3Zy"
API = "r7jel27uma"
TABLES = ("fx_events", "fx_leads", "fx_sessions")
LOG_GROUP = "/aws/lambda/fx-table-api"
# В ARN обліковий запис замаскований як <account>, а не 12 нулями: 12 цифр в ARN ловить правило
# aws_arn_account у scripts/secret_scan.py. Такий самий вигляд — у знімках docs/aws-teardown/*.json.
CERT = "arn:aws:acm:us-east-1:<account>:certificate/d2a264f2-b347-4ba3-8e58-d2139eda0c69"
CNAME_NAME = "_76330d86a537e3871c91496e2f84668a.table.central-aparts.store."
CNAME_VALUE = "_899f0cee4466647eed6cd591e1093e6a.jkddzztszm.acm-validations.aws."
SECRET = "aluma/admin-credentials"

MARKERS = ("fx-table", "fx_", "aluma", "table.central-aparts.store", DISTRIBUTION, API, "d2a264f2")

# Що має зникнути з кожного спільного списку — і нічого більше.
EXPECTED_GONE = {
    "stacks": [STACK],
    "cloudfront_distributions": [DISTRIBUTION],
    "cloudfront_functions": [CF_FUNCTION],
    "cloudfront_oac": [OAC],
    "cloudfront_origin_request_policies": [ORP],
    "lambda_functions": [FUNCTION],
    "iam_roles": [ROLE],
    "apigw_apis": [API],
    "dynamodb_tables": list(TABLES),
    "log_groups": [LOG_GROUP],
    "acm_us_east_1": [CERT],
    "route53_records": [f"{CNAME_NAME} CNAME"],
    "s3_buckets": [SITE_BUCKET],
}

# Імена з маркером, які ЛИШАЮТЬСЯ і не є старим AWS: A-записи на коробку.
MARKER_KEEP = {
    "route53_records": {"table.central-aparts.store. A", "table-new.central-aparts.store. A"},
}

HTTP_CHECKS = (
    ("central-aparts.store", "/"),
    ("www.central-aparts.store", "/"),
    ("v2.central-aparts.store", "/"),
    ("cv.central-aparts.store", "/"),
    ("table.central-aparts.store", "/"),
    ("table.central-aparts.store", "/api/fx/health"),
    ("table.central-aparts.store", "/admin"),
)


class NotFound(Exception):
    pass


def check_readonly(args) -> None:
    """Пропускає лише читання. Будь-яка інша дія — помилка до запуску процесу."""
    if len(args) < 2:
        raise ValueError(f"незрозумілий виклик: {args!r}")
    op = args[1]
    if op == "get-secret-value" or not op.startswith(("list-", "describe-", "get-")):
        raise ValueError(f"лише читання: {args[0]} {op} заборонено")


def aws(*args, region=REGION):
    check_readonly(args)
    cmd = ["aws", *args, "--output", "json"]
    if region:
        cmd += ["--region", region]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = proc.stderr.strip()
        for sign in ("does not exist", "NotFound", "NoSuch", "ResourceNotFound",
                     "cannot be found", "not found"):
            if sign in err:
                raise NotFound(err.splitlines()[-1][:300])
        raise RuntimeError(f"aws {args[0]} {args[1]}: {err[-500:]}")
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def maybe(fn):
    """None, якщо ресурсу нема; інші помилки — вгору, мовчки не ковтаємо."""
    try:
        return fn()
    except NotFound:
        return None


def sha(lines) -> str:
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()


def http(host: str, path: str):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(f"https://{host}{path}", method="GET",
                                 headers={"user-agent": "aluma-teardown-check"})
    out = {"url": f"https://{host}{path}"}
    try:
        with opener.open(req, timeout=15) as r:
            out["status"] = r.status
            body = r.read(4096)
    except urllib.error.HTTPError as exc:
        out["status"] = exc.code
        out["location"] = exc.headers.get("location")
        return out
    except Exception as exc:  # мережа — фіксуємо, не падаємо
        out["error"] = type(exc).__name__
        return out
    if path.endswith("/health"):
        try:
            out["version"] = json.loads(body).get("version")
        except ValueError:
            out["version"] = None
    return out


# ------------------------------------------------------------------ snapshot


def collect_aluma():
    a = {}
    a["stack"] = maybe(lambda: aws("cloudformation", "describe-stacks", "--stack-name", STACK,
                                   "--query", "Stacks[0].{name:StackName,status:StackStatus,"
                                   "termination_protection:EnableTerminationProtection,"
                                   "last_updated:LastUpdatedTime}"))
    a["stack_resources"] = maybe(lambda: aws(
        "cloudformation", "list-stack-resources", "--stack-name", STACK, "--query",
        "StackResourceSummaries[].{logical:LogicalResourceId,physical:PhysicalResourceId,"
        "type:ResourceType,status:ResourceStatus}"))
    if a["stack"]:
        tpl = maybe(lambda: aws("cloudformation", "get-template", "--stack-name", STACK,
                                "--template-stage", "Processed", "--query", "TemplateBody"))
        if isinstance(tpl, str):
            try:
                tpl = json.loads(tpl)
            except ValueError:
                tpl = None
        if isinstance(tpl, dict):
            policies = {k: v.get("DeletionPolicy", "Delete")
                        for k, v in (tpl.get("Resources") or {}).items()}
            for r in a["stack_resources"] or []:
                r["deletion_policy"] = policies.get(r["logical"], "Delete")

    objs = maybe(lambda: aws("s3api", "list-object-versions", "--bucket", SITE_BUCKET, "--query",
                             "{v: Versions[].Size, d: length(DeleteMarkers || `[]`)}", region=None))
    a["site_bucket"] = None if objs is None else {
        "name": SITE_BUCKET,
        "versions": len(objs.get("v") or []),
        "bytes": sum(objs.get("v") or []),
        "delete_markers": objs.get("d") or 0,
        "versioning": (maybe(lambda: aws("s3api", "get-bucket-versioning", "--bucket", SITE_BUCKET,
                                         region=None)) or {}).get("Status", "Disabled"),
    }
    a["distribution"] = maybe(lambda: aws(
        "cloudfront", "get-distribution", "--id", DISTRIBUTION, "--query",
        "Distribution.{id:Id,domain:DomainName,status:Status,enabled:DistributionConfig.Enabled,"
        "aliases:DistributionConfig.Aliases.Items,cert:DistributionConfig.ViewerCertificate.ACMCertificateArn}",
        region=None))
    a["lambda"] = maybe(lambda: aws(
        "lambda", "get-function", "--function-name", FUNCTION, "--query",
        "Configuration.{name:FunctionName,arn:FunctionArn,runtime:Runtime,role:Role,"
        "last_modified:LastModified,version_env:Environment.Variables.APP_VERSION}"))
    a["iam_role"] = maybe(lambda: aws("iam", "get-role", "--role-name", ROLE,
                                      "--query", "Role.{name:RoleName,arn:Arn}", region=None))
    a["api"] = maybe(lambda: aws("apigatewayv2", "get-api", "--api-id", API,
                                 "--query", "{id:ApiId,name:Name,endpoint:ApiEndpoint}"))
    a["tables"] = {}
    for t in TABLES:
        a["tables"][t] = maybe(lambda t=t: aws(
            "dynamodb", "describe-table", "--table-name", t, "--query",
            "Table.{name:TableName,arn:TableArn,status:TableStatus,item_count:ItemCount,"
            "bytes:TableSizeBytes,deletion_protection:DeletionProtectionEnabled}"))
    groups = aws("logs", "describe-log-groups", "--log-group-name-prefix", LOG_GROUP, "--query",
                 "logGroups[].{name:logGroupName,bytes:storedBytes,retention:retentionInDays}")
    a["log_group"] = next((g for g in groups or [] if g["name"] == LOG_GROUP), None)
    a["certificate"] = maybe(lambda: aws(
        "acm", "describe-certificate", "--certificate-arn", CERT, "--query",
        "Certificate.{arn:CertificateArn,domain:DomainName,sans:SubjectAlternativeNames,"
        "status:Status,in_use_by:InUseBy,not_after:NotAfter,"
        "validation:DomainValidationOptions[].ResourceRecord}", region="us-east-1"))
    records = aws("route53", "list-resource-record-sets", "--hosted-zone-id", ZONE, "--query",
                  f"ResourceRecordSets[?Name=='{CNAME_NAME}']", region=None) or []
    a["validation_cname"] = records[0] if records else None
    versions = aws("s3api", "list-object-versions", "--bucket", SAM_BUCKET, "--prefix", SAM_PREFIX,
                   "--query", "{v: Versions[].{key:Key,version_id:VersionId,size:Size,latest:IsLatest},"
                   " d: DeleteMarkers[].{key:Key,version_id:VersionId}}", region=None) or {}
    a["sam_artifacts"] = {"bucket": SAM_BUCKET, "prefix": SAM_PREFIX,
                          "versions": sorted(versions.get("v") or [], key=lambda x: (x["key"], x["version_id"])),
                          "delete_markers": versions.get("d") or []}
    a["secret"] = maybe(lambda: aws(
        "secretsmanager", "describe-secret", "--secret-id", SECRET, "--query",
        "{name:Name,arn:ARN,created:CreatedDate,last_accessed:LastAccessedDate,"
        "deleted_date:DeletedDate,rotation:RotationEnabled}"))
    return a


def collect_shared():
    s = {}
    s["stacks"] = sorted(x["name"] for x in aws(
        "cloudformation", "list-stacks", "--query",
        "StackSummaries[?StackStatus!='DELETE_COMPLETE'].{name:StackName}") or [])
    dists = aws("cloudfront", "list-distributions", "--query",
                "DistributionList.Items[].{id:Id,aliases:Aliases.Items,status:Status,enabled:Enabled}",
                region=None) or []
    s["cloudfront_distributions"] = sorted(d["id"] for d in dists)
    s["cloudfront_distribution_detail"] = sorted(
        f"{d['id']} {','.join(d.get('aliases') or [])} {d['status']} {d['enabled']}" for d in dists)
    # list-functions віддає кожну функцію двічі — стадії DEVELOPMENT і LIVE.
    s["cloudfront_functions"] = sorted(set(aws("cloudfront", "list-functions", "--query",
                                               "FunctionList.Items[].Name", region=None) or []))
    s["cloudfront_oac"] = sorted(aws("cloudfront", "list-origin-access-controls", "--query",
                                     "OriginAccessControlList.Items[].Id", region=None) or [])
    s["cloudfront_origin_request_policies"] = sorted(aws(
        "cloudfront", "list-origin-request-policies", "--type", "custom", "--query",
        "OriginRequestPolicyList.Items[].OriginRequestPolicy.Id", region=None) or [])
    s["lambda_functions"] = sorted(aws("lambda", "list-functions", "--query",
                                       "Functions[].FunctionName") or [])
    s["iam_roles"] = sorted(aws("iam", "list-roles", "--query", "Roles[].RoleName", region=None) or [])
    s["iam_users"] = sorted(aws("iam", "list-users", "--query", "Users[].UserName", region=None) or [])
    s["apigw_apis"] = sorted(aws("apigatewayv2", "get-apis", "--query", "Items[].ApiId") or [])
    s["dynamodb_tables"] = sorted(aws("dynamodb", "list-tables", "--query", "TableNames") or [])
    s["log_groups"] = sorted(aws("logs", "describe-log-groups", "--query",
                                 "logGroups[].logGroupName") or [])
    key_types = "keyTypes=RSA_1024,RSA_2048,RSA_3072,RSA_4096,EC_prime256v1,EC_secp384r1,EC_secp521r1"
    s["acm_us_east_1"] = sorted(aws("acm", "list-certificates", "--includes", key_types, "--query",
                                    "CertificateSummaryList[].CertificateArn", region="us-east-1") or [])
    s["acm_eu_central_1"] = sorted(aws("acm", "list-certificates", "--includes", key_types, "--query",
                                       "CertificateSummaryList[].CertificateArn") or [])
    s["route53_records"] = sorted(f"{r['n']} {r['t']}" for r in aws(
        "route53", "list-resource-record-sets", "--hosted-zone-id", ZONE, "--query",
        "ResourceRecordSets[].{n:Name,t:Type}", region=None) or [])
    s["s3_buckets"] = sorted(aws("s3api", "list-buckets", "--query", "Buckets[].Name", region=None) or [])
    secrets = aws("secretsmanager", "list-secrets", "--include-planned-deletion", "--query",
                  "SecretList[].{name:Name,deleted:DeletedDate}") or []
    s["secrets"] = sorted(x["name"] for x in secrets)
    s["secrets_planned_deletion"] = sorted(x["name"] for x in secrets if x.get("deleted"))
    s["eventbridge_rules"] = sorted(aws("events", "list-rules", "--query", "Rules[].Name") or [])
    s["scheduler_schedules"] = sorted(aws("scheduler", "list-schedules", "--query",
                                          "Schedules[].Name") or [])
    s["budgets"] = sorted(aws("budgets", "describe-budgets", "--account-id", ACCOUNT, "--query",
                              "Budgets[].BudgetName", region="us-east-1") or [])
    allv = aws("s3api", "list-object-versions", "--bucket", SAM_BUCKET, "--query",
               "{v: Versions[].[Key,VersionId], d: DeleteMarkers[].[Key,VersionId]}", region=None) or {}
    other = [f"{k} {v}" for k, v in (allv.get("v") or []) if not k.startswith(SAM_PREFIX)]
    other_dm = [f"{k} {v}" for k, v in (allv.get("d") or []) if not k.startswith(SAM_PREFIX)]
    s["sam_bucket_other_versions"] = {"count": len(other), "sha256": sha(other),
                                      "delete_markers": len(other_dm), "delete_markers_sha256": sha(other_dm)}
    return s


def marker_hits(shared: dict) -> dict:
    hits = {}
    for section, values in shared.items():
        if not isinstance(values, list):
            continue
        found = [v for v in values if any(m.lower() in v.lower() for m in MARKERS)]
        if found:
            hits[section] = found
    return hits


def snapshot(label: str) -> dict:
    ident = aws("sts", "get-caller-identity", "--query", "Account", region=None)
    if ident != ACCOUNT:
        raise SystemExit(f"не той акаунт: {ident}")
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data = {
        "label": label,
        "taken_at": started,
        "account": ACCOUNT,
        "aluma": collect_aluma(),
        "shared": collect_shared(),
        "http": [http(h, p) for h, p in HTTP_CHECKS],
    }
    data["marker_hits"] = marker_hits(data["shared"])
    data["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return data


# ------------------------------------------------------------------ compare


def compare(before: dict, after: dict) -> tuple[list, list]:
    """(рядки звіту, провали). Чисте порівняння двох знімків — без AWS."""
    lines, failed = [], []

    def check(ok, text):
        lines.append(("OK   " if ok else "FAIL ") + text)
        if not ok:
            failed.append(text)

    b, a = before["shared"], after["shared"]
    for section in sorted(set(b) | set(a)):
        if section in ("sam_bucket_other_versions", "secrets_planned_deletion",
                       "cloudfront_distribution_detail"):
            continue
        bs, as_ = set(b.get(section) or []), set(a.get(section) or [])
        gone, new = sorted(bs - as_), sorted(as_ - bs)
        expected = sorted(set(EXPECTED_GONE.get(section, [])) & bs)
        check(gone == expected,
              f"{section}: зникло {gone or '—'}; очікувано {expected or '—'}")
        if new:
            lines.append(f"     {section}: нове після «до» (не наше, для відома): {new}")

    keep = {d for d in b.get("cloudfront_distribution_detail", []) if not d.startswith(DISTRIBUTION)}
    check(keep <= set(a.get("cloudfront_distribution_detail", [])),
          "чужі дистрибуції: id, аліаси, статус і Enabled без змін")
    so_b, so_a = b["sam_bucket_other_versions"], a["sam_bucket_other_versions"]
    check(so_b == so_a, f"SAM-бакет поза {SAM_PREFIX}: версій {so_b['count']} → {so_a['count']},"
                        f" sha256 {'той самий' if so_b['sha256'] == so_a['sha256'] else 'ІНШИЙ'}")

    al = after["aluma"]
    check(al["stack"] is None, f"стек {STACK} відсутній")
    check(al["distribution"] is None, f"дистрибуція {DISTRIBUTION} не знайдена")
    check(al["lambda"] is None, f"лямбда {FUNCTION} не знайдена")
    check(al["api"] is None, f"API {API} не знайдено")
    check(al["iam_role"] is None, f"роль {ROLE} не знайдена")
    check(al["site_bucket"] is None, f"бакет {SITE_BUCKET} не знайдено")
    check(all(v is None for v in al["tables"].values()), f"таблиць {', '.join(TABLES)} нема")
    check(al["log_group"] is None, f"група логів {LOG_GROUP} не знайдена")
    check(al["certificate"] is None, "сертифікат d2a264f2… не знайдено")
    check(al["validation_cname"] is None, f"CNAME {CNAME_NAME} не знайдено")
    check(not al["sam_artifacts"]["versions"] and not al["sam_artifacts"]["delete_markers"],
          f"у {SAM_BUCKET} під {SAM_PREFIX}: версій {len(al['sam_artifacts']['versions'])},"
          f" delete-маркерів {len(al['sam_artifacts']['delete_markers'])}")
    sec = al["secret"]
    check(sec is None or bool(sec.get("deleted_date")),
          f"секрет {SECRET}: " + ("не знайдено" if sec is None
                                  else f"заплановано до видалення {sec.get('deleted_date')}"))

    leftovers = {}
    for section, values in after["marker_hits"].items():
        rest = [v for v in values if v not in MARKER_KEEP.get(section, set())
                and not (section.startswith("secrets") and v == SECRET and sec and sec.get("deleted_date"))]
        if rest:
            leftovers[section] = rest
    check(not leftovers, f"пошук за маркерами {', '.join(MARKERS)}: лишилось {leftovers or 'нічого'}"
                         f" (крім A-записів table/table-new на коробку і секрету в статусі видалення)")

    hb = {h["url"]: h for h in before["http"]}
    for h in after["http"]:
        was = hb.get(h["url"], {})
        if h["url"].endswith("table.central-aparts.store/api/fx/health"):
            check(h.get("status") == 200 and h.get("version") == "0.4.0-box",
                  f"{h['url']}: {h.get('status')} {h.get('version')}")
        elif h["url"].endswith("table.central-aparts.store/admin"):
            check(h.get("status") == 303, f"{h['url']}: {h.get('status')} → {h.get('location')}")
        else:
            check(h.get("status") == was.get("status"),
                  f"{h['url']}: {was.get('status')} → {h.get('status')}")
    return lines, failed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sn = sub.add_parser("snapshot")
    sn.add_argument("--label", required=True, choices=("before", "after", "check"))
    sn.add_argument("--out", required=True)
    cp = sub.add_parser("compare")
    cp.add_argument("before")
    cp.add_argument("after")
    args = ap.parse_args(argv)

    if args.cmd == "snapshot":
        data = snapshot(args.label)
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"{args.label}: {args.out}, {data['taken_at']} … {data['finished_at']}")
        for section, values in sorted(data["marker_hits"].items()):
            print(f"  маркери в {section}: {len(values)}")
        return 0

    with open(args.before, encoding="utf-8") as fh:
        before = json.load(fh)
    with open(args.after, encoding="utf-8") as fh:
        after = json.load(fh)
    lines, failed = compare(before, after)
    print("\n".join(lines))
    print("compare: " + ("ЗЕЛЕНО" if not failed else f"ЧЕРВОНО — {len(failed)} перевірок не пройшло"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
