---
name: "aluma-check"
description: "ALUMA: how to run tests, lint, build, local-stack smoke, Playwright and Lighthouse on ace-main — the frame, the venv, the ports, what is verified."
argument-hint: "quick | pr | full | browser | smoke | lighthouse (default: quick)"
user-invocable: true
disable-model-invocation: false
---

# /aluma-check — checks for ALUMA on this box

Everything below runs from the repository root (`~/repos/aluma-table` or a worktree of it). Rules that apply to every
command: ports only on `127.0.0.1`, processes stopped only by PID, `TMPDIR` outside the tree, venv outside the tree,
secrets never printed (CLAUDE.md §7, §9).

## The frame — every run goes inside it

Fleet rule after the 14.09 incident (pytest 38 h, 10 GB, the whole user down):

```bash
TMPDIR=/tmp timeout 30m systemd-run --user --scope -q \
  --slice='app-ihor\x2dconductor.slice' -p MemoryMax=2G <command>
```

The full Python set and anything with Playwright go additionally through the heavy queue:
`heavy --label aluma --max-wait 600 -- systemd-run …`. `TMPDIR` inside the tree turns `test_serve_local_stack` red —
that is its job.

## Venv — outside the tree, not in /tmp

`/tmp` gets wiped (2026-10-13: the old `/tmp` venv had lost its site-packages, every run was red, a rebuild costs 83 s).

```bash
python3 -m venv /opt/ihor/aluma-table/tmp/venv
/opt/ihor/aluma-table/tmp/venv/bin/pip install -r api/requirements.txt -r tests/requirements.txt -r requirements-lint.txt
```

## Python tests — three modes

```bash
V=/opt/ihor/aluma-table/tmp/venv/bin
$V/python tools/run_tests.py          # quick set (tests/QUICK.txt): logic only — ~140 tests, ~0.5 s quiet
$V/python tools/run_tests.py --pr     # before a PR (tests/CRITICAL.txt): + build byte-for-byte, secret scan, prod units — ~190, ~12 s
$V/python tools/run_tests.py --full   # before a merge: everything (unittest discover) — ~310 tests; heavy queue
$V/ruff check .                       # → All checks passed!
```

Measured 2026-10-13 (load 24–28 on 8 threads): quick 138 in 0.6 s, `--pr` 193 in 14 s. Quiet machine: divide by ~3.
Pick the mode by the change: text/number/API logic → quick; anything in `build.py`, `scripts/`, `deploy/` → `--pr`;
before a merge → `--full`. Proving a test can fail: break the code in memory, not on disk
(`tests/README-python-tests.md`).

## Secret scan — the same check CI runs

```bash
python3 scripts/secret_scan.py --repo . --mode tree --baseline .github/secret-scan-baseline.json --report "$TMPDIR/secret-scan.md"
```
Exit 1 only on a NEW place; stdout carries per-rule totals, never values. Reviewed on purpose → `--update-baseline`.

## Build

```bash
python3 build.py                  # preview → dist/ (gitignored); exit 0, lists the owner blanks — this is what prod serves today
python3 build.py --production     # refuses while an owner fact is missing (2026-10-13: 5 fields — address, email, phone, accessibility contact, court city)
```
Required before push when `site/`, `i18n/`, `content.json` or `build.py` changed.

## Local stack smoke (writes a lead into a throw-away DB)

```bash
/opt/ihor/aluma-table/tmp/venv/bin/pip install -r deploy/requirements-server.txt
ss -ltnp | grep ':8005 '                             # must print nothing (8005 is prod's port — it is free only on a box without the unit)
env FX_STORAGE=sqlite FX_DB_PATH=/tmp/aluma-smoke.db APP_VERSION=0.4.0-smoke \
    ADMIN_USER=x ADMIN_PASS=throwaway IP_SALT=throwaway \
    /opt/ihor/aluma-table/tmp/venv/bin/gunicorn -w 2 --threads 4 --timeout 60 \
    --no-control-socket -b 127.0.0.1:8005 api.wsgi:application
python3 scripts/smoke_local.py                       # → 4/4 зелених, exit 0; refuses any host but localhost
kill -TERM <master pid>                              # pid from "Listening at: … (<pid>)" or ss -ltnp
```
On ace-main prod already holds 8005 — use `tools/serve-local-stack.py` on 8007 instead (below). **Always**
`--no-control-socket`: without it gunicorn 26 replaces the per-user control socket and breaks the other gunicorn of
this user. Invented secrets only.

## Playwright

Browsers only in the project dir (never `~/.cache`), chromium, no `install-deps`, no sudo.

```bash
npm ci                                               # node_modules in this worktree
PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright npx playwright install chromium
ss -ltn | grep ':8007 '                              # must print nothing; dist/ built by python3 build.py
# redesign.spec.js — fully mocked, same as the CI job `browser`:
PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright PREVIEW_PORT=8007 PYTHON=python3 \
    npx playwright test --config playwright.local.config.js   # → 39 passed; webServer stops, 8007 free again
# smoke.spec.js — FULL local stack only (it writes leads): never prod, never any public name
python3 tools/serve-local-stack.py &                 # 8007: dist/ like Caddy + api.wsgi, one-off SQLite in a 0700 temp dir
PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright BASE_URL=http://127.0.0.1:8007 \
    npx playwright test tests/smoke.spec.js          # → 30 passed
kill -TERM <pid>                                     # pid printed at start / ss -ltnp; temp DB removed with it
```

## Lighthouse against prod (GET only, no forms)

```bash
export CHROME_PATH=/opt/ihor/aluma-table/ms-playwright/chromium-1234/chrome-linux64/chrome   # check the real dir name
node_modules/.bin/lighthouse https://table.central-aparts.store/ --quiet \
    --chrome-flags='--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage' \
    --only-categories=performance,accessibility,best-practices,seo \
    --output=json --output=html --output-path=docs/lighthouse/<date>/he-mobile.report
```
Add `--preset=desktop` for the desktop pass. Raw reports are gitignored; commit `summary.json` + `README.md` only.
2026-09-12: 100/100/100/100 on `/` and `/en/`, both presets.

## Not verified on this box (network / AWS) — read the docs before running

- `python3 scripts/compare_sites.py https://table.central-aparts.store dist --assets` — hits prod (GET only).
- `python3 scripts/migrate_fx.py --phase dump|load|verify` — history; `dump` READS DynamoDB, which no longer exists.
- `pullagent.py --dry-run|--status` — after the agent is installed (T040), `docs/DELIVERY.md`.
