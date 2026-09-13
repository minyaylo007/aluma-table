# ALUMA — one-table landing (table.central-aparts.store)

**On any conflict, `~/maestro/OWNER-RULES.md` and `~/.claude/CLAUDE.md` win over this file.** Machine-wide invariants
(tests before push, secrets, ports, others' territory, git) are in `.specify/memory/constitution.md`; this file keeps
what is specific to ALUMA.

Landing page for one extendable oak dining table (ALUMA / GOREN). Hebrew (RTL) at `/`, English at `/en/`. Lead form →
owner notified on Telegram → leads worked in `/admin`. Prod: this machine (gunicorn + SQLite + Caddy) — `table` points
here since 2026-09-11 12:42:31Z (`a7e9c64`); the old AWS of ALUMA is **gone** — stack `fx-table` and the `fx_*` tables
deleted 2026-09-11, everything else 2026-09-12, nothing of ALUMA left in AWS (`docs/AWS-TEARDOWN.md`, `3789f0c`).
**Now:** the API runs from the clone `/opt/ihor/aluma-table` (detached `563edc8`) as **user** units installed by hand
(`systemctl --user`, 127.0.0.1:8005, env `~/.config/aluma/aluma.env`), static in `/srv/aluma`, health `0.4.0-box`.
**After the agent is installed (T040):** GitHub releases land in `releases/vX.Y.Z` + `current`, installed by the pull
agent `deploy/agent/pullagent.py` — `docs/DELIVERY.md` (both states, and what is not verified yet).
**Repository:** `minyaylo007/aluma-table` is **public since 2026-09-12**, with a clean history — the tree as one
snapshot commit. Everything older, and every old sha, lives in the private archive
`minyaylo007/aluma-table-archive-2026-09` (its Actions are off): the old history describes weak spots of this machine,
and stripping that out would mean rewriting history, which is forbidden. The repository name did not change, so
`origin` stayed the same; links to Actions runs from before 12.09 point at the archive.

## 1. Core Principles
- **Others' systems are untouchable**, Caddy included; **deploys go through the pipeline** (`docs/DELIVERY.md`),
  outside it only with the owner's «да» — rules in §9.
- **One source for every fact.** Numbers live in `content.json`, UI strings in `i18n/he.json` + `i18n/en.json`;
  templates in `site/` only reference them. Never hardcode a number or a sentence in HTML/JS.
- **Same code, two runtimes.** `api/handler.py` runs unchanged in Lambda and under gunicorn; the storage is picked by
  `FX_STORAGE`. Never add runtime-specific logic to the handler.
- **Build is byte-identical on any OS** (LF, UTF-8) — guarded by `tests/test_build_eol.py`.
- **Secrets and lead data are never printed** — not in the console, logs, commits or reports.

## 2. Tech Stack
| Layer | What | Where it is pinned |
|---|---|---|
| Static site | `build.py` (stdlib; Pillow optional), plain HTML/CSS/JS, three.js viewer `site/assets/goren3d.js` | — |
| API | Python, one module `api/handler.py`; `requests` for Telegram | `api/requirements.txt` |
| Storage | DynamoDB (Lambda) or SQLite via `api/store.py` (server) | — |
| Server runtime | gunicorn 26.2.0, boto3 1.34.46, requests 2.31.0 (boto3 is needed even for SQLite: unconditional import) | `deploy/requirements-server.txt` |
| Lambda runtime | python3.13, SAM | `infra/template.yaml` |
| Browser tests | `@playwright/test` 1.62.1 exactly, chromium only; `node_modules/` per worktree, browsers in `/opt/ihor/aluma-table/ms-playwright` | `package.json`, `package-lock.json` |
| CI/CD | GitHub Actions (`docs/DELIVERY.md` §3): `ci.yml` on push to any branch but `master` and on PRs — `secret-scan` (`scripts/secret_scan.py` over the tree, always, no path filters), `lint` (ruff E9+F, `node --check` of built JS), `test (3.12)`, `test (3.13)`, `build` (twice, same bytes), `browser` (`redesign.spec.js`, 8007); on `master` `release.yml` runs the same checks, then release → deploy behind `RELEASES_ENABLED` (not set yet); `rollback.yml` manual — 395 OK locally on 2026-09-12 | `.github/workflows/`, `requirements-lint.txt`, `tests/requirements.txt` |

## 3. Architecture
```
content.json, i18n/{he,en}.json ─┐
site/ (templates, assets)  ──────┴─ build.py ─► dist/   (gitignored; + .build/asset-map.json)
api/handler.py  ── lambda_handler(event)   ← Lambda (FX_STORAGE=dynamodb, set in infra/template.yaml)
api/wsgi.py     ── application = WSGI wrapper around lambda_handler  ← gunicorn (FX_STORAGE=sqlite)
api/store.py    ── SQLite twin of fx_events / fx_leads / fx_sessions (FX_DB_PATH, default data/aluma.db)
scripts/        ── smoke_local, compare_sites, migrate_fx, purge, daily_report (box SQLite), aws_inventory, secret_scan,
                   next_version + release_build (release archive), prod_notify_params, deploy.sh (owner only, AWS)
deploy/         ── agent/pullagent.py + aluma.json (pull agent), systemd units (user/; the current/ layout applies
                   after T040), nginx/Caddy blocks, env example
.github/        ── workflows: ci, release (checks → release → deploy), deploy, rollback
infra/          ── SAM template of the deleted fx-table stack (history; the stack no longer exists)
```
- **`build.py`**: substitutes `{{TOKENS}}` from `content.json` and `{{t.key}}` from `i18n/<loc>.json`, draws the
  technical SVGs from the same numbers, content-hashes every asset name (`name.<sha256[:10]>.ext`), publishes only
  referenced files. `python build.py` = preview (owner blanks shown as markers); `--production` refuses while an
  owner fact is missing. Every text file is written with `newline="\n"` (`write_text_lf`, `normalise_eol`).
- **Routes** (`api/handler.py`): `GET /api/fx/health`, `POST /api/fx/event`, `POST /api/fx/lead`, `GET /admin`,
  `/admin/login`, `/admin/logout`, `POST /admin/status`. Health returns `version` and `git_sha` (`RELEASE.env`).
- **`FX_STORAGE`**: `sqlite` is the code default and the only one in use (the Lambda is gone). The dynamodb branch
  and its trap stay tested, not deployed: without `FX_STORAGE=dynamodb` a Lambda writes nothing and stays 200 on
  health — `tests/test_lambda_no_fx_storage.py`, `docs/PROD-NOTIFY-DECISION.md` §4.4.
- **Notifications**: `notify()` → Telegram `sendMessage` (`TELEGRAM_BOT_TOKEN`, `OWNER_TELEGRAM_CHAT_ID`). Best effort:
  the lead is stored first; a failure prints `{"event":"notify_failed",...}` with the token cut out by `_redact()`.
  **A request with header `x-test: 1` stores the lead with `is_test` and sends NO notification**; it also uses its
  own rate bucket (`RLL#T#…`, 60/h instead of 5/h).
- **`EDGE_SECRET`**: when set, every request without the matching `x-fx-edge` header gets 403 — before routing.
  Only CloudFront sends that header.
- **TTL**: DynamoDB expires rows by itself; SQLite does not. `scripts/purge.py` + `deploy/systemd/aluma-purge.timer`
  do it on the server (leads are never purged).

## 4. Code Style
- Python: `snake_case`, module-level `UPPER_SNAKE` config read from env at import. Stdlib first; the only runtime
  third-party deps are `requests` and `boto3`.
- Comments, docstrings and commit messages are in **Ukrainian** (see `api/*.py`, `git log`); code identifiers in English.
- Commit messages: `type(scope): короткий опис` — `feat`, `fix`, `test`, `docs` (e.g. `fix(notify): …`, `docs(deploy): …`).
- Dual import is intentional — do not "simplify": `try: from api import store` (repo root: tests, gunicorn)
  `except ImportError: import store` (in the Lambda bundle `api/` IS the root).
- `api/` is a namespace package (no `__init__.py`, Lambda layout `CodeUri: ../api/`); `tests/__init__.py` is required.
- Hebrew: numeric ranges and LTR fragments inside Hebrew go in `<bdi dir="ltr">`; copy rules and past edits —
  `docs/night-2026-09-01/HEBREW-EDIT.md`, `HEBREW-EDIT-2.md`.

## 5. Logging
No logging library: one JSON line to stdout per event (journald / CloudWatch), e.g. `print(json.dumps({"event":
"notify_failed", "id": item.get("id"), "error": _redact(repr(exc))}))`. Events: `notify_failed`, `unhandled`,
`wsgi_unhandled`, `purge_skipped`. Never put secrets, phone numbers, names or response bodies in a log line; anything
that can contain a URL with the bot token goes through `_redact()`. The public 500 is always
`{"ok": false, "error": "internal"}` — no stack traces to the internet.

## 6. Testing
Full guide: **`tests/README-python-tests.md`**. Python tests are stdlib `unittest`, no network, no AWS credentials:
Telegram is patched, DynamoDB is a fake or moto, `FX_DB_PATH` is forced to `:memory:`.
- **Venv OUTSIDE the project tree** — nothing may show up in `git status`. System Python lacks `werkzeug`, so a bare
  run fails (`test_wsgi` import error).
- `tests/test_lambda_dynamodb.py` needs `boto3` + `moto` (+ `node` for the phone-parity test), else it is skipped.
- Playwright: `tests/redesign.spec.js` (`playwright.local.config.js`) is fully mocked; it starts `tools/serve-preview.py`
  on `127.0.0.1:$PREVIEW_PORT` (default 4173 — not ALUMA's; here always 8007, §8). `tests/smoke.spec.js` is **not run**
  against prod or table-new: it writes to storage (a real `is_test` lead via `route.fetch`, `page_view` without
  `X-Test` on every `goto`, events via `route.continue`) — safe only against a full local stack with a throwaway DB.
  That stack is `tools/serve-local-stack.py` (§8): one process on 8007, `dist/` served like Caddy + `api.wsgi` in the
  same process, one-off SQLite in a 0700 temp dir removed on exit, `TELEGRAM_*` stripped. It is covered by
  `tests/test_serve_local_stack.py` (22 tests, WSGI called directly — no sockets bar two that need a live process).
  `BASE_URL` decides the origin the spec asserts against; an HTTPS-only check stays on for a public name.
- Proving a test can fail: break the code **in memory**, not on disk (the pattern used throughout the README).

## 7. Common Patterns
- **`api/store.py` is a shim, not a DynamoDB emulator.** It implements exactly the calls `handler.py` makes
  (`Key(...).eq()`, `SET` with `if_not_exists`, `ADD` counters, `batch_writer`, `scan`); anything else raises
  `ValueError` on purpose. Need a new expression? First check it is really needed, then add it with a test.
  boto3 returns `Decimal`; `store.py` serialises with `default=_plain`.
- Scripts that talk to `/admin` must not follow redirects (`scripts/smoke_local.py` uses a `redirect_request → None`
  opener), otherwise you test urllib, not the server.
- `scripts/smoke_local.py` refuses any host other than `127.0.0.1`/`localhost` (exit 2) — it writes a lead.
- `scripts/compare_sites.py` is GET-only, refuses `/api/` and `/admin`, throttles ≥0.5 s; side B may be `dist/`.
- `scripts/migrate_fx.py` writes only through `api/store.py`; `verify` compares with the dump, and the final pass
  needs `--second-pass` (TTL) — `docs/CUTOVER-CHECKLIST.md` step 7.5.
- Lossy WebP/AVIF shift a flat ground by 1–3 levels: compare render colours with a tolerance, never byte-equal.

## 8. Development Commands
Verified on this box (Python 3.12.3): lint, the Python tests and `build.py` re-run 2026-09-12, the rest on
2026-09-11 unless marked otherwise; venv/DB paths are arbitrary, outside the repo.
```bash
git pull --rebase                                   # always first
# Python tests — venv outside the tree
python3 -m venv /tmp/aluma-venv-$USER
/tmp/aluma-venv-$USER/bin/pip install -r api/requirements.txt -r tests/requirements.txt -r requirements-lint.txt
/tmp/aluma-venv-$USER/bin/ruff check .                                   # → All checks passed!
/tmp/aluma-venv-$USER/bin/python -m unittest discover -s tests -t .      # → Ran 417 tests … OK
# Build (preview) → dist/, gitignored
python3 build.py                                     # → exit 0, "PREVIEW build" + list of owner blanks
# Local stack smoke: gunicorn ONLY on 127.0.0.1:8005, ALWAYS --no-control-socket, invented secrets
/tmp/aluma-venv-$USER/bin/pip install -r deploy/requirements-server.txt
ss -ltnp | grep ':8005 '                             # must print nothing
env FX_STORAGE=sqlite FX_DB_PATH=/tmp/aluma-smoke.db APP_VERSION=0.4.0-smoke \
    ADMIN_USER=x ADMIN_PASS=throwaway IP_SALT=throwaway \
    /tmp/aluma-venv-$USER/bin/gunicorn -w 2 --threads 4 --timeout 60 \
    --no-control-socket -b 127.0.0.1:8005 api.wsgi:application
python3 scripts/smoke_local.py                       # → 4/4 зелених, exit 0
kill -TERM <master pid>                              # pid from "Listening at: … (<pid>)" or ss -ltnp
ss -ltn | grep ':8005 '                              # must print nothing again
# Playwright redesign spec: browsers only in the project dir (never ~/.cache), chromium, no install-deps / sudo
npm ci                                               # node_modules in this worktree
PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright npx playwright install chromium
ss -ltn | grep ':8007 '                              # must print nothing; dist/ built by python3 build.py
PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright PREVIEW_PORT=8007 PYTHON=python3 \
    npx playwright test --config playwright.local.config.js   # → 39 passed; webServer stops, 8007 free again
# Playwright smoke spec: FULL local stack only (it writes leads) — never prod, never table-new
python3 tools/serve-local-stack.py &                 # 8007: dist/ like Caddy + api.wsgi, one-off SQLite
PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright BASE_URL=http://127.0.0.1:8007 \
    npx playwright test tests/smoke.spec.js          # → 30 passed
kill -TERM <pid>                                     # pid printed at start / ss -ltnp; temp DB removed with it
# Lighthouse against PROD (GET only, no forms) — package from node_modules, chromium from the project dir
export CHROME_PATH=/opt/ihor/aluma-table/ms-playwright/chromium-1234/chrome-linux64/chrome
node_modules/.bin/lighthouse https://table.central-aparts.store/ --quiet \
    --chrome-flags='--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage' \
    --only-categories=performance,accessibility,best-practices,seo \
    --output=json --output=html --output-path=docs/lighthouse/<date>/he-mobile.report
    # add --preset=desktop for the desktop pass; 2026-09-12: 100/100/100/100 on / and /en/,
    # both presets — docs/lighthouse/2026-09-12/README.md (raw reports gitignored)
# NOT verified here (network / AWS) — read the linked docs before running:
python3 scripts/compare_sites.py https://table.central-aparts.store dist --assets   # hits prod (GET only)
python3 scripts/migrate_fx.py --phase dump|load|verify [--second-pass]             # dump READS DynamoDB
python3 /opt/ihor/aluma-table/current/deploy/agent/pullagent.py --config …/aluma.json --dry-run|--status  # after T040
```
**Ports** (`~/maestro/PORTS.md`): **8005** — ALUMA gunicorn, **8007** — ALUMA nginx (request only) and the Playwright preview.
Listen **only on `127.0.0.1`**, never `0.0.0.0` / `*`. Without `--no-control-socket` gunicorn 26 deletes and replaces
the per-user control socket and breaks the central-aparts-site gunicorn running as the same user
(`deploy/systemd/aluma-api.service` comment). Stop processes **only by PID** — never `pkill`, `killall`, `pkill -f`.

## 9. AI Coding Assistant Instructions
**Git.** Branch `master`, and since 2026-09-12 it is protected for everyone: **branch → PR → auto-merge only**. A
fast-forward push to `master` is refused by the server (`GH013: Changes must be made through a pull request`), so do
not try — open a PR and `gh pr merge --squash --auto`; it merges itself once `secret-scan`, `lint`, `test (3.12)`,
`test (3.13)`, `build` and `browser` are green, and GitHub removes the branch. Release and deploy stay off (`RELEASES_ENABLED` not
set). `git pull --rebase` first; `git add <explicit files>`, never `-A`; commit per step, push at once; never
`git push --force` (constitution VI). The rulesets live in the repo as `.github/rulesets/*.json` — change a rule by
editing the file and re-applying it, not in the web UI, or `tests/test_rulesets.py` will drift from reality.
Process — `docs/DELIVERY.md`.

**Caddy.** By default hands off. Any session may run `caddy validate`, `caddy adapt`, `caddy fmt` — on a copy with a
global `admin off` block (`deploy/README.md`, `deploy/caddy/aluma.Caddyfile`). Never, with any config, including
your own: `caddy run`, `caddy start`, `caddy stop`, `caddy reload`, `systemctl stop|restart caddy`, the admin socket,
anything on port 2019 (the shared admin API stops live Caddy without root). Writing to `/etc/caddy/` and
`sudo systemctl reload caddy` — ONLY a session whose task carries explicit «разрешено sudo» lines
(`~/maestro/OWNER-RULES.md` п.20–21), by `deploy/caddy/REQUEST-DENIS.md` §6: backup copy, one own `import` line,
validate, announce to the main conductor, others' sites checked before/after, rollback on any difference.
Reason: on 2026-09-10 an ALUMA session stopped the live Caddy; four other businesses (incl. a medical practice)
were down 15+ minutes.

**Others' territory.** Do not read or write `/opt/iiko`, `/opt/uzd`, `/opt/uzd-legacy`, `/opt/atmo`, `/opt/tennis`,
`/opt/bots`, or others' units and containers. ALUMA's own server path is `/opt/ihor/aluma-table`; edit code only in
`~/repos/aluma-table` (or a worktree of it). Need a live foreign service to test something — ask the owner instead.

**Deploy.** Rollout goes by `docs/DELIVERY.md` (constitution VI, constitution-base 2.1.0): auto-deploy after a merge
into the target branch is allowed and preferred (OWNER-RULES п.22) when the CI checks are green and rollback is proven;
a rollout to prod outside that pipeline — including the box itself today — still needs the owner's «да».
**AWS stays hands-off, read-only, no exceptions:** ALUMA has nothing left there (`docs/AWS-TEARDOWN.md`), but the
account is shared with other projects, and the admin key on the box stops nothing — only this rule does. So no
`sam deploy`, `aws cloudformation …`, `aws lambda update-function-*`, `aws s3 sync/cp`, DNS change, or any other AWS
write. `scripts/deploy.sh`, `docs/PROD-NOTIFY-DECISION.md` and `infra/` describe the deleted Lambda stack — history.

**Secret scan.** `scripts/secret_scan.py` is a required check on every commit — `--mode tree` against
`.github/secret-scan-baseline.json`, the reviewed-places list; a NEW finding is what turns it red. Values are never
printed: stdout carries per-rule totals only, the report with paths stays in `$RUNNER_TEMP`. Reviewed a finding on
purpose? `--baseline … --update-baseline`; keys, `.env` files, databases and access codes may never go in the list
(`tests/test_secret_scan.py`). The one-off scan of the whole history, public and archive, and what was found in it —
`docs/security/secret-scan-2026-09-13.md`. No `gitleaks`, no `trufflehog`, no new binaries from the network.

**Secrets.** `IP_SALT` and `ADMIN_PASS` move to the server **unchanged** (they sign the admin cookie and salt
`ip_hash`). `EDGE_SECRET` is **not** moved to the server (otherwise 403 on everything, admin included). Check
presence by count, never print values (`docs/CUTOVER-CHECKLIST.md` step 2). Only `deploy/aluma.env.example` is in
git. `dump/` and `data/` hold live lead data (gitignored): never commit them, never print their contents.

**Shell text.** Pass long text (task, report, docs) through a file or in **single** quotes. Heredoc only with a
quoted delimiter: `<<'EOF'`. Backticks or `$(` inside double quotes execute — on 2026-09-10 that sent a real
request to port 2019 from a sentence *about* not touching Caddy. Grep long text for a backtick and `$(` before sending.

**Sessions.** Remote Control only — never `claude -p`, `--print` or any headless session.

**Where things are** (tests — §6, ports — §8):
| Topic | File |
|---|---|
| Machine-wide invariants checked by `/speckit-analyze` | `.specify/memory/constitution.md` |
| Delivery: branches, CI, releases, deploy, rollback, who presses what (now / after T040) | `docs/DELIVERY.md` |
| Move to this server, step by step (secrets, FX_STORAGE, DNS window, rollback) | `docs/CUTOVER-CHECKLIST.md` |
| Units, nginx, Caddy, env — what goes where, what was checked | `deploy/README.md`, `deploy/systemd/`, `deploy/nginx/`, `deploy/caddy/` |
| Old AWS stack: Lambda rollout recipe and the teardown — both history, the stack is deleted | `docs/PROD-NOTIFY-DECISION.md`, `docs/AWS-TEARDOWN.md` |
| Repository rules as files (what is applied, and why no bypass anywhere) | `.github/rulesets/*.json`, `tests/test_rulesets.py` |

**Before marking done:** tests green (§8); `python3 build.py` exits 0 if `site/`, `i18n/`, `content.json` or
`build.py` changed; `git status` shows only your files.

## 10. Keeping This File Updated
The session that changes a fact stated here (command, port, env var, route, rule) updates this file in the same
commit — gotcha → §7, command → §8 (re-run it; mark anything not run as not verified), architecture → §3, dependency
→ §2; the conductor checks it on acceptance; owner rule changes land first in OWNER-RULES. Edit in place, link instead
of copying, keep it under ~200 lines, check every claim against the code. `.claude/cc10x/*` is not authoritative and
is no longer tracked (untracked on 2026-09-12, before the repository was published; the old copies stay in the private
archive `aluma-table-archive-2026-09`).

## SDD (Spec Kit)
Features larger than ~1 day, or touching data, money, sign-in or security, go through Spec-Driven Development:
GitHub Spec Kit 1.0.6, skills `/speckit-*`. Specs live in `specs/NNN-short-name/` (the conductor assigns the number,
short-name in Latin), principles in `.specify/memory/constitution.md`. Small edits and operations — without SDD, as a
regular task. The Spec Kit git extension is not installed: it creates no branches and no commits by itself.
Reference copy and procedure — `~/maestro/sdd/`.
