# ALUMA — one-table landing (table.central-aparts.store)

**On any conflict, `~/maestro/OWNER-RULES.md` and `~/.claude/CLAUDE.md` win over this file.** Machine-wide invariants —
`.specify/memory/constitution.md`. How the project got here (AWS teardown, public re-publish, cutover) — `docs/HISTORY.md`.

Prelaunch storefront for the five pieces of `catalog/products.json`: Hebrew (RTL) at `/`, English at `/en/`, Russian at `/ru/`; lead form →
owner on Telegram → leads worked in `/admin`. **Prod is this box:** gunicorn + SQLite behind Caddy, user units
`ihor-aluma-{api.service,purge.timer,backup.timer,digest.timer,journal-watch.timer}` (leads never purged; copy :07 → `backups/`; funnel digest
→ Telegram 09:00/20:00 Jerusalem, `scripts/funnel_digest.py`; every 10 min `scripts/journal_watch.py` → conductor, OWNER-RULES п.42) run from the clone `/opt/ihor/aluma-table` (env `~/.config/aluma/aluma.env`, 127.0.0.1:8005), static `/srv/aluma`, health `GET /api/fx/health`.

## 1. Small-change path (text, number, small API fix)
1. Branch from `master`; edit `content.json` / `i18n/*.json` / `site/` / `api/`. No plan mode, no SDD, no subagents.
2. `tools/run_tests.py` (quick set, ~0.5 s). If `site/`, `i18n/`, `content.json` or `build.py` changed: `python3 build.py` exits 0.
3. Before the PR: `tools/run_tests.py --pr` and `ruff check .` and `scripts/secret_scan.py --repo . --mode tree --baseline .github/secret-scan-baseline.json` (`--pr` tests the scanner, it does not scan the tree) inside the frame of §8 (skill `/aluma-check`).
4. `git add <files>` → commit `type(scope): опис` → push → `gh pr create` → `gh pr merge --squash --auto`. CI runs on the PR only.
5. After the merge: `scripts/deploy-box.sh <sha>` (skill `/aluma-deploy`), check health and `/` live, report with the rollback line.

## 2. Core principles
- **Others' systems are untouchable**, Caddy included; deploys go by `docs/DELIVERY.md` and skill `/aluma-deploy` (§9).
- **One source for every fact.** Numbers in `content.json`, UI strings in `i18n/{he,en,ru}.json` (+ `legal.*`); templates in
  `site/` only reference them — never hardcode a number or a sentence in HTML/JS.
- **Same code, two runtimes.** `api/handler.py` runs unchanged under gunicorn (`api/wsgi.py`) and in a Lambda; storage is
  picked by `FX_STORAGE` — never add runtime-specific logic to the handler. **Build is byte-identical on any OS** (LF,
  UTF-8; `tests/test_build_eol.py`). **Secrets and lead data are never printed** — console, logs, commits, reports.

## 3. Stack and architecture
| Layer | What | Pinned in |
|---|---|---|
| Static site | `build.py` (stdlib; Pillow optional) → `dist/` (gitignored): home, `/catalog/`, `/p/<slug>/` from the catalog, `/cart/` + `/checkout/` (shop, closed payment — `specs/003-shop-funnel`), how, about, faq, privacy, terms, accessibility, 404; vanilla `site/assets/aluma.{js,css}` + `shop.js` + `tracking.js`; font faces of one language in `site/assets/fonts-<lang>.css`, inlined only into its pages (subsets — `tools/subset_locale_fonts.py`); 3D on click — `site/assets/products/aluma3d.js` + three 0.160.0 vendored in `site/assets/vendor/` (no CDN); design rationale `docs/REDESIGN-2026-10.md` | — |
| API | `api/handler.py` (`lambda_handler`), `api/wsgi.py` (gunicorn), `api/store.py` (SQLite twin of `fx_*`); server runtime gunicorn + boto3 (unconditional import) + requests | `api/requirements.txt`, `deploy/requirements-server.txt` |
| Browser tests | `@playwright/test` 1.62.1, chromium only; browsers in `/opt/ihor/aluma-table/ms-playwright`; `@axe-core/playwright` — `tests/a11y.spec.js` (no port, `playwright.a11y.config.js`; IL checklist `docs/COMPLIANCE-IL.md`) | `package.json`, `package-lock.json` |
| CI/CD | GitHub Actions: `ci.yml` on every PR to `master`, nightly, and from `release.yml` — six required checks `secret-scan`, `lint`, `test (3.12)`, `test (3.13)`, `build`, `browser`; release/deploy behind `RELEASES_ENABLED` (unset); `rollback.yml` manual | `.github/workflows/`, `docs/DELIVERY.md` |

- `build.py` substitutes `{{TOKENS}}` from `content.json` and `{{t.key}}` from `i18n/<loc>.json`, draws the technical
  SVGs from the same numbers, content-hashes asset names, publishes only referenced files. `python build.py` = preview
  (owner blanks shown as markers; **prod is built this way today**); `--production` refuses while an owner fact is missing.
- Routes: `GET /api/fx/health`, `GET /api/fx/config` (public, 60 s), `POST /api/fx/event`, `POST /api/fx/lead` (+ CAPI Lead), `GET /admin`
  (+ `login`, `logout`, `POST status`, `settings`, `settings/test`, `leads.csv`, `funnel` — shop funnel + card «ask» clicks `cta_ask`, «call us» `cta_call` + `lead_source=callback` leads, text twin `tools/funnel_report.py`, `specs/003-shop-funnel`). `FX_STORAGE=sqlite` is the only one in use; dynamodb stays tested, not deployed (`test_lambda_no_fx_storage.py`).
- Notifications: `notify()` → Telegram plain text `lead_message()` (preview `tools/preview_lead_message.py`), best effort: lead
  stored first; failure → `notify_failed`, token cut by `_redact()`. `x-test: 1` stores `is_test`, sends nothing, own rate bucket. `EDGE_SECRET` (unset on the box): when set, a request without `x-fx-edge` gets 403 before routing.
- Instagram @aluma.il: `scripts/ig_publish.py` (post = `docs/ig/NN-*.jpg|txt`, only on the conductor's word; `--dry-run` safe), token `~/.config/aluma/ig.env`, `ihor-aluma-ig-refresh.timer` (1st/15th) — `deploy/README.md`.

## 4. Code style and logging
- Python `snake_case`, module-level `UPPER_SNAKE` config read from env at import; stdlib first; runtime deps only
  `requests` and `boto3`. Comments, docstrings, commit messages in **Ukrainian**; identifiers in English.
- Dual import is intentional — do not "simplify": `try: from api import store` / `except ImportError: import store`.
  `api/` is a namespace package (no `__init__.py`); `tests/__init__.py` is required. Hebrew: LTR fragments in `<bdi dir="ltr">`.
- Logging: one JSON line to stdout per event (`notify_failed`, `unhandled`, `wsgi_unhandled`, `purge_skipped`); never a secret,
  phone, name or response body in a log line. The public 500 is always `{"ok": false, "error": "internal"}` — no traces.

## 5. Testing
Guide: `tests/README-python-tests.md`. Stdlib `unittest`, no network, no AWS: Telegram patched, DynamoDB faked,
`FX_DB_PATH` forced to `:memory:`. Venv and `TMPDIR` **outside the tree** (`/opt/ihor/aluma-table/tmp/venv`; `/tmp` gets wiped).
Three modes: `tools/run_tests.py` (quick, `tests/QUICK.txt`), `--pr` (`tests/CRITICAL.txt`: + build, scanner tests, prod units),
`--full` (everything — what a merge needs). Playwright: `tests/redesign.spec.js`, `tests/shop.spec.js` are fully mocked (preview on 8007);
`tests/smoke.spec.js` (current funnel he+ru, lead → local SQLite) **writes leads**, not in CI: `--config tests/playwright.smoke.config.js`
starts its own `tools/serve-local-stack.py` on a free 8007, never prod. Proving a test can fail: break the code in memory, not on disk.

## 6. Gotchas
- `api/store.py` is a shim, not a DynamoDB emulator: unknown expressions raise `ValueError` on purpose — add one only
  with a proof it is needed and a test. boto3 returns `Decimal`; `store.py` serialises with `default=_plain`.
- Scripts that talk to `/admin` must not follow redirects. `scripts/smoke_local.py` refuses any host but localhost.
- `rsync` to `/srv/aluma` needs `--chmod=D0755,F0644`, or Caddy serves 403 on part of the pages (`deploy/README.md`).
  Lossy WebP/AVIF shift a flat ground by 1–3 levels: compare render colours with a tolerance, never byte-equal.

## 7. Ports and processes
**8005** — ALUMA gunicorn, **8007** — Playwright preview / local stack (`~/maestro/PORTS.md`). Listen **only on
`127.0.0.1`**, never `0.0.0.0` / `*`; gunicorn always with `--no-control-socket` (without it gunicorn 26 replaces the
per-user control socket and breaks the other gunicorn of this user). Stop processes **only by PID** (`ss -ltnp` →
`kill -TERM <pid>`) — never `pkill`, `killall`, `pkill -f`: the same binaries serve other businesses on this box.

## 8. Commands
```bash
tools/run_tests.py            # quick set — the default: logic only, ~140 tests, ~0.5 s quiet
tools/run_tests.py --pr       # before a PR: + build byte-for-byte, scanner tests, prod units — ~190 tests, ~12 s
tools/run_tests.py --full     # before a merge: everything, via the heavy queue
gh pr merge --squash --auto   # deploy of code = merge into master; then scripts/deploy-box.sh <sha> (/aluma-deploy)
```
Every run goes inside this frame (fleet rule, 14.09 incident); full set and Playwright also via `heavy --label aluma --`. The rest — `/aluma-check`.
```bash
TMPDIR=/tmp timeout 30m systemd-run --user --scope -q --slice='app-ihor\x2dconductor.slice' -p MemoryMax=2G <command>
```

## 9. Rules for every session
- **Git.** `master` is protected for everyone: **branch → PR → `gh pr merge --squash --auto`**; a direct push is refused
  (`GH013`). `git pull --rebase` first; `git add <explicit files>`, never `-A`; commit per step, push at once; never
  `git push --force`. Rulesets live in `.github/rulesets/*.json` — change the file and re-apply it, never the web UI.
- **Caddy — hands off.** Allowed: `caddy validate`, `caddy adapt`, `caddy fmt` on a copy with a global `admin off`
  (`deploy/caddy/aluma.Caddyfile`). **Never, with any config, including your own:** `caddy run`, `caddy start`,
  `caddy stop`, `caddy reload`, `systemctl stop|restart caddy`, the admin socket, anything on port 2019. Writing to
  `/etc/caddy/` and `sudo systemctl reload caddy` — ONLY a session whose task carries explicit «разрешено sudo» lines
  (OWNER-RULES п.20–21), by `deploy/caddy/REQUEST-DENIS.md` §6. Why: 2026-09-10, four businesses down 15+ min (HISTORY).
- **Others' territory.** Do not read or write `/opt/iiko`, `/opt/uzd`, `/opt/uzd-legacy`, `/opt/atmo`, `/opt/tennis`,
  `/opt/bots`, others' units and containers. ALUMA's server path is `/opt/ihor/aluma-table`; edit code only in
  `~/repos/aluma-table` or a worktree of it. Need a live foreign service to test something — ask the owner.
- **Deploy.** Merge into `master` = code accepted; prod follows by `scripts/deploy-box.sh` (`/aluma-deploy`; OWNER-RULES
  п.31: deploy without asking, report after with the rollback line); only own units `ihor-aluma-*` restart. **AWS stays
  hands-off, read-only, no exceptions** (shared account): no `sam deploy`, `aws cloudformation`, `aws lambda update-function-*`,
  `aws s3 sync/cp`, DNS change, or any other write.
- **Secret scan.** `scripts/secret_scan.py --mode tree` against `.github/secret-scan-baseline.json` is a required check
  on every PR; a NEW finding turns it red, values are never printed. Reviewed on purpose → `--update-baseline`; keys,
  `.env` files, databases and access codes may never go in the list. No `gitleaks`/`trufflehog`/new binaries.
- **Secrets.** `IP_SALT` and `ADMIN_PASS` stay unchanged on the server (cookie signature, `ip_hash`); `EDGE_SECRET` is
  not set on the box. Check presence by count, never print values. Only `deploy/aluma.env.example` is in git; `dump/`
  and `data/` hold live lead data — never commit, never print.
- **Shell text.** Long text (task, report, docs) goes through a file or in **single** quotes. Heredoc only with a quoted
  delimiter: `<<'EOF'`. Backticks or `$(` inside double quotes execute — on 2026-09-10 that sent a real request to
  port 2019 from a sentence *about* not touching Caddy. Grep long text for a backtick and `$(` before sending.
- **Sessions.** Remote Control only — never `claude -p`, `--print` or any headless session. No subagents on small tasks.
- **Before marking done:** tests green (§8); `python3 build.py` exits 0 if site/i18n/content/build changed; only your files in `git status`.

## 10. Where things are, keeping this file, SDD
| Topic | File |
|---|---|
| Delivery: branches, CI, releases, deploy, rollback, who presses what; repository rules as files | `docs/DELIVERY.md`, `.github/rulesets/*.json`, `tests/test_pipeline.py` |
| Units, Caddy block, env, publishing static (rsync flags) | `deploy/README.md`, `deploy/systemd/`, `deploy/caddy/` |
| History: AWS teardown, cutover, public repo + private archive, incidents, old reports; Hebrew copy rules | `docs/HISTORY.md` |

The session that changes a fact stated here updates this file in the same commit, keeps it **under 120 lines**, moves history
to `docs/HISTORY.md`. Features over ~1 day or touching data, money, sign-in, security → Spec Kit (`/speckit-*`, `specs/`); small edits — §1.
