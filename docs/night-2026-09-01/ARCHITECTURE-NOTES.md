# Phase 0 — Reconnaissance (night run 2026-09-01)

> **Masked on 2026-09-12, before the repository was published.** The AWS account number is replaced by
> `000000000000` where it stands alone and by `<account>` inside an ARN. The stack described here was
> deleted on 2026-09-11/12 (`docs/AWS-TEARDOWN.md`); the original values are in the private archive
> `aluma-table-archive-2026-09`.

## AWS account & credentials
- Account `000000000000`, IAM user `arn:aws:iam::<account>:user/aparts-deploy`.
- Default region `eu-central-1` (from `~/.aws/config`). Credentials come from the shared credentials file, not env vars.
- Rights: verified in practice — can request ACM certs, write Route53 records, create CloudFormation/SAM stacks. Full IAM policy not readable by this user; capability was established by doing, not by reading the policy.

## DNS
- Single Route53 public hosted zone: `central-aparts.store.` → `Z05565972H1DV59U5PO4I` (13 records, moved off inhostedns 2026-08-27).
- Existing records: apex + `www` + `v2` → CloudFront `d33uf8v0bjha42` (dist `E3A58MFOU2LI12`); `cv` → `do1uhas0kqi4t` (dist `E80XDWDORZKYP`); `bill.cv` → dist `E392KOWPAV5V11`. MX points at `mx.services.` (looks vestigial — **not touched**).
- `table.central-aparts.store` was free. Taken for this project.

## Certificates
- Pre-existing ACM (us-east-1): apex, `www`, `v2`, `cv`, `bill.cv` — all ISSUED. Not touched.
- **New:** `table.central-aparts.store` → `arn:aws:acm:us-east-1:<account>:certificate/d2a264f2-b347-4ba3-8e58-d2139eda0c69`, DNS-validated via a CNAME added to the zone, status **ISSUED** within ~2 minutes.

## Existing apartments system (the thing we must not break)
- Repo `gosha/aparts` (git), Python 3.13 + Flask + Jinja2, structlog, pytest.
- Runtime: AWS Lambda behind a Function URL, DynamoDB + S3, fronted by CloudFront `E80XDWDORZKYP` (`cv.central-aparts.store`).
- IaC: AWS SAM (`aparts/infra/template.yaml` + `samconfig.toml`), stack name `aparts`, region `eu-central-1`. SAM CLI 1.152.0 present.
- Deploy quirk documented in the repo and in project memory: CloudFront serves the Lambda **alias `live`**, so `sam deploy` alone only updates `$LATEST` — a real deploy also needs publish-version + update-alias. Not our problem tonight, but it explains why we must not reuse that stack.
- Second repo `gosha/aparts-v2` (guest-facing site, Bitbucket pipeline, own CloudFront).
- `samconfig.toml` carries ~30 production secrets as plaintext `parameter_overrides`. We will **not** add anything to that file.

## Tooling available
`sam 1.152.0`, `python 3.13.5`, `node v20.19.0`, `npm 10.8.2`, `aws` CLI v2, git. No Playwright installed yet (will install locally into `furniture/` only).

## Decision: stack for the new project
Same stack family as the existing system — Python 3.13 Lambda + DynamoDB + S3 + CloudFront, deployed with AWS SAM. Nothing new is introduced.

Split of responsibilities:

```
                      table.central-aparts.store
                                 │
                        CloudFront (new dist)
                        cert: table.* (ACM us-east-1)
                     ┌───────────┴────────────┐
        default (/*) │                        │ /api/fx/*  and  /admin*
                     ▼                        ▼
             S3 (private, OAC)        Lambda Function URL  (fx-table-api)
             static site: HTML,       Python 3.13, zero deps
             CSS, JS, SVG                       │
                                                ▼
                                   DynamoDB: fx_events / fx_leads / fx_sessions
                                   (PAY_PER_REQUEST, TTL on events)
```

Why static-on-S3 rather than rendering from Lambda: the page must hit Lighthouse Performance ≥ 90 on mobile with LCP < 2.5 s. A cold Lambda cannot promise that; a cached S3 object behind CloudFront can. The API surface is small enough (2 POST endpoints + an admin page) to be one small function. This is the exception the brief allows, and it still reuses the exact stack the apartments system uses.

## Isolation guarantees
| Shared | Not shared |
|---|---|
| AWS account | CloudFormation stack (`fx-table`, separate) |
| Route53 hosted zone (one new subdomain record set) | DynamoDB tables (`fx_*` prefix, new) |
| SAM managed artifact bucket | S3 site bucket (new) |
| | CloudFront distribution (new) |
| | Lambda function (new) |
| | IAM roles (new, scoped to the `fx_*` tables) |
| | Code, tests, deploy script (`furniture/`, new) |

The apartments test suite is run before and after the night to prove nothing moved.

## Chosen subdomain
`table.central-aparts.store` — first preference from the brief, and it was free.
Caveat recorded for the owner: the parent domain says "central-aparts", which has nothing to do with furniture. For a real launch the brand needs its own domain. For a smoke test it is fine — Meta ads send people to a link, and the link is HTTPS and works.
