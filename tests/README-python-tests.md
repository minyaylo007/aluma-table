# Python unit tests for the fx-table API

Stdlib `unittest` test cases, no network, no AWS credentials, nothing touches
the real `fx_*` tables.

```
cd ~/repos/aluma-table
python -m pytest tests -q                # everything
python -m unittest tests.test_handler -v # one file, no pytest needed
```

Three files:

| File | What it covers | Extra requirement |
|---|---|---|
| `tests/test_handler.py` | routing, phone normalisation, lead capture, Telegram notification | none |
| `tests/test_store_sqlite.py` | `api/store.py` — the SQLite twin of the three DynamoDB tables | none |
| `tests/test_wsgi.py` | `api/wsgi.py` — the same handler under gunicorn | `werkzeug` |
| `tests/test_lambda_dynamodb.py` | the Lambda path: `FX_STORAGE=dynamodb` on moto, the live front's lead body, admin, client/server phone parity | `boto3`, `moto`, `node` (else skipped) |
| `tests/test_lambda_no_fx_storage.py` | Lambda **without** `FX_STORAGE`: read-only `/var/task` → lead and event 500, no notify, health 200 | not root (else skipped) |
| `tests/test_daily_report.py` | `scripts/daily_report.py` on the box SQLite (no DynamoDB, no boto3) | none |
| `tests/test_aws_inventory.py` | `scripts/aws_inventory.py`: every write verb and `get-secret-value` refused before a process starts; `compare` is red when a foreign resource vanished, an ALUMA one is left, the secret is not scheduled, SAM versions outside `fx-table/` changed, prod checks fail | none (no AWS) |

## Running the whole suite (417 tests, all green)

Measured 2026-09-12 in the venv from CLAUDE.md §8: `Ran 417 tests — OK`, `ruff check .`
clean. 417 = 395 (the count CLAUDE.md §8 carried before this run) + 22 in
`tests/test_serve_local_stack.py` (added 2026-09-12; see "Browser suite against a full
local stack"). The breakdown below stops at 218 and describes the state on 2026-09-11;
files added since are described in their own sections at the end.

218 = 212 + 6 in `tests/test_lambda_no_fx_storage.py` (added 2026-09-11; see "Lambda
without FX_STORAGE" at the end). 212 = the 116 described below + 2 token-redaction tests in `tests/test_handler.py`
(added 2026-09-11) + 15 in `tests/test_prod_notify_params.py` (added 2026-09-11;
see "Deploy parameters" at the end) + 7 added to `tests/test_migrate_fx.py` by
`f15bcdf` (`--second-pass`) + 24 in `tests/test_smoke_local.py` (added
2026-09-11; see "Local stack smoke" at the end) + 32 in
`tests/test_compare_sites.py` (added 2026-09-11; see "Prod vs box" at the end)
+ 4 in `tests/test_build_eol.py` (added 2026-09-11; see "Build is the same on
every OS" at the end) + 12 in `tests/test_lambda_dynamodb.py` (added 2026-09-11;
see "Lambda path on moto" at the end). Measured 2026-09-11 in a throw-away venv
with `pip install -r api/requirements.txt werkzeug boto3 moto`: `Ran 212 tests — OK`.
Without `moto` the Lambda-path file is reported as skipped and the rest stays at 200.

`werkzeug` is not installed system-wide on ace-main, so a bare
`python3 -m unittest discover -s tests -t .` reports `Ran 90 tests,
FAILED (errors=1)`: the 90th "test" is unittest's placeholder for
`tests/test_wsgi.py` failing to import, and its 27 real tests never run.

Throw-away venv **outside the project tree** (nothing may appear in
`git status`):

```
python3 -m venv /tmp/aluma-venv
cd ~/repos/aluma-table
/tmp/aluma-venv/bin/pip install -r api/requirements.txt -r tests/requirements.txt   # те самі файли, що в CI
/tmp/aluma-venv/bin/python -m unittest discover -s tests -t .
```

Test-only dependencies are pinned in `tests/requirements.txt` (werkzeug, boto3, moto) since 2026-09-11 —
CI installs exactly these files, never a list typed into the workflow. The historical counts below were measured
with the older ad-hoc install (`pip install werkzeug requests pytest`).

116, not 117: the 90 of the broken run already counted the import placeholder,
so it is 89 real tests + 27 from `test_wsgi`.

| Package | Verified | Note |
|---|---|---|
| `werkzeug` | **3.1.8**, floor **>= 2.3** | only `werkzeug.test.Client`. Measured: 3.1.8 and 2.3.8 pass all 27; **2.2.3 fails** — `client.set_cookie("fx_adm", "tok.en", domain="localhost")` raises `ValueError: Setting 'domain' for a cookie on a server running locally ... is not supported`. The keyword-first `set_cookie(key, value, domain=...)` signature is 2.3+. |
| `requests` | 2.31.0 | **needed even though nothing goes to the network.** `test_handler` patches `api.handler.requests.post`; without the package `handler.py` sets `requests = None` and `mock.patch.object` raises `AttributeError: None does not have the attribute 'post'` — 10 errors in `NotifyTests`. |
| `pytest` | 9.1.1 | optional; `unittest` runs everything. |
| `boto3` | not needed | the fake boto3 tree covers it (see below). |

`api/` is imported as a namespace package (Python 3.3+), so it has no
`__init__.py` and the Lambda `CodeUri: ../api/` /
`Handler: handler.lambda_handler` layout is untouched.

`tests/__init__.py` (empty) IS required: on this machine a stray
`site-packages/tests/__init__.py` (shipped by `pyrootutils`) shadows any
namespace `tests/` directory, so `python -m unittest tests.test_handler` would
report "No module named 'tests.test_handler'" without it. A regular package in
the project root (`sys.path[0]`) wins. Playwright only matches `*.spec.js`, so
the `.py` files are invisible to the JS suites.

Fallback if the module path ever misbehaves: `python tests/test_handler.py`.

## How AWS stays out

| Concern | Mechanism |
|---|---|
| `import boto3` on a machine without the SDK | A fake `boto3` module tree (`boto3`, `boto3.dynamodb`, `boto3.dynamodb.conditions.Key`) is injected into `sys.modules` before `api.handler` is imported. If boto3 *is* installed the real module is used but never called. `test_wsgi.py` imports `tests.test_handler` for that side effect — otherwise `python -m unittest tests.test_wsgi` alone dies with `ModuleNotFoundError: No module named 'boto3'`, and the full run survives only because `test_handler` is imported first alphabetically. |
| DynamoDB | `api.handler._tables` is patched to three `FakeTable` objects (`put_item`, `update_item` returning `{"Attributes": {"n": N}}`). `N` is the simulated rate counter. |
| Telegram (replaced SES) | `api.handler.requests.post` is patched to a `TelegramRecorder` that stores the payload, returns a chosen status code, or raises on demand. |
| Env | `EDGE_SECRET`, `TELEGRAM_BOT_TOKEN`, `OWNER_TELEGRAM_CHAT_ID` are cleared and `FX_DB_PATH` is forced to `:memory:` before import, then patched per test — the developer's shell cannot change outcomes and no test can leave a `.db` file behind. |

## What is covered

- `normalize_phone`: the full accepted-format table (see the function
  docstring in `api/handler.py` — the frontend mirrors that table), absurd
  length (>15 digits), RTL/LTR marks and punctuation, non-ASCII digits dropped,
  only one `00` prefix stripped, `None`/non-string input.
- `POST /api/fx/lead` through `lambda_handler`: 200 with a 12-hex id and the
  stored item (`phone`, `lang`, `size`, key set); 422 error keys for
  name/phone/consent; honeypot (`website` filled) returns `{"ok":true,"id":"hp"}`
  and stores nothing; unknown `lang`/`size`/`color` stored as `""`; numeric
  `size` coerced to string; 429 when the counter exceeds `LEADS_PER_IP_PER_HOUR`;
  counter failure fails open; `x-test: 1` marks the row and uses the `RLL#T#`
  bucket; non-dict / invalid JSON bodies give 422 not 500; base64 bodies; the
  80/80/1000 clips for name/city/comment; unhandled exceptions become a JSON 500.
- `GET /api/fx/health` smoke.
- `notify()`: exactly one Telegram `sendMessage` per lead, to
  `OWNER_TELEGRAM_CHAT_ID`, with a timeout; text carries `Size:`, `Lang:`,
  `Page:` and `consent_marketing=yes|no`; never raises when Telegram is down,
  answers 4xx, or `requests` is missing, and a failure is printed as
  `{"event": "notify_failed", ...}` rather than swallowed. **The bot token never
  reaches that line.** requests puts the URL (`.../bot<token>/sendMessage`) into
  its exception text, so `_redact()` cuts the token out before `clip()`. This is
  proven with the real `requests.post`, where the connection fails before a socket
  opens, and with a 4xx body that echoes the URL. With `_redact` disabled in
  memory, both tests go red. **The lead is still
  stored when the notification explodes**; real leads notify, `x-test` traffic
  does not, nothing is sent when the token is empty; no boto3 client is ever
  built for a notification.
- `api/store.py`: put/get round trip, `query` by `Key(...).eq(...)` in both key
  shapes, `ScanIndexForward=False`, `Limit` + `ExclusiveStartKey` pagination,
  `scan`, `batch_writer`, `ADD` counters (what `rate_ok` needs),
  `if_not_exists` (what `touch_session` needs), TTL purge, a file database
  reopened by a second worker, and 8 threads writing at once without
  `database is locked`. Expressions the handler never writes raise `ValueError`.
- `api/wsgi.py`: the event shape (`rawPath`, `requestContext.http.method`,
  lower-cased `headers`, `body`, `cookies`, `rawQueryString`,
  `queryStringParameters`), the response shape (status line with a reason
  phrase, `Set-Cookie` per entry of `cookies`, base64 bodies, UTF-8
  `Content-Length`), `wsgiref.validate` compliance, and a lead posted over WSGI
  ending up readable through `load_leads()`.
- `scripts/daily_report.py::analyse` lead rows include `lang` (and every
  previous field), with `""` for legacy rows written before `lang` existed.
- `scripts/daily_report.py` reads the box SQLite through `api/store.py`
  (`tests/test_daily_report.py`, 7 tests, added 2026-09-11 when the DynamoDB
  `fx_*` tables were deleted): the day window and `--include-test`, paging past
  the 1000-event / 500-lead query pages, leads newest-first and events
  oldest-first (as DynamoDB returned them), import and run with `boto3` blocked,
  a missing `FX_DB_PATH` → exit 2 without creating a database or a report,
  `main --no-ai` writes the same funnel/raw report, table names from env like the
  handler. One-off parity check at the switch (not in the suite): the old
  DynamoDB `load()` on moto and the new SQLite `load()` on the same 1500 events /
  620 leads gave identical `analyse()` output and row order for 1/3/7/10 days,
  with and without test rows.

## Not covered (on purpose)

`/admin*` HTML rendering in detail. That is exercised by the Playwright smoke suite
(`tests/smoke.spec.js`) — those specs need a browser, so they are not part of
`python -m unittest discover -s tests -t .`. `tests/test_lambda_dynamodb.py` only walks
the admin flow (login → dashboard shows the lead → status change) on moto.

## Browser suite against a full local stack (`tests/smoke.spec.js`)

**Never against prod, never against `table-new`.** This suite WRITES to storage: an
`is_test` lead via `route.fetch`, a `page_view` without `X-Test` on every `goto`, and
events via `route.continue`. It is only safe against a throwaway stack.

`tools/serve-local-stack.py` is that stack: one process on `127.0.0.1:8007` that serves
`dist/` exactly the way Caddy does (`deploy/caddy/aluma-site-body.caddyfile` — clean URLs,
`/en` → `/en/` 308, 404 page with status 404, the same headers) and routes `/api/fx/*`
and `/admin*` into `api.wsgi:application` **in the same process**, on a one-off SQLite
database in a 0700 temp dir. `TELEGRAM_*` are stripped, so nothing is ever notified, and
`EDGE_SECRET` is left unset (with it the handler answers 403 to everything, admin included).

```bash
python3 build.py                                      # dist/ must exist
ss -ltn | grep ':8007 '                               # must print nothing
python3 tools/serve-local-stack.py &                  # prints its pid and the temp db path
PLAYWRIGHT_BROWSERS_PATH=/opt/ihor/aluma-table/ms-playwright BASE_URL=http://127.0.0.1:8007 \
    npx playwright test tests/smoke.spec.js           # → 30 passed
kill -TERM <pid>                                      # by PID only, never pkill
ss -ltn | grep ':8007 '                               # nothing again; the temp db is gone
```

Measured 2026-09-12: **30 passed**, and the temp database directory is removed on exit.

The tool itself is covered by `tests/test_serve_local_stack.py` (22 tests). All but one
call the WSGI application directly — no sockets, no network:

- routing: every `/api/fx/*` and `/admin*` path reaches the application (and `/admin*` is
  a *prefix* there, as in Caddy), while static paths never do;
- static parity with Caddy: clean URLs, directory → `index.html`, `/en` → 308, a missing
  page → the site's own 404 page with status 404 (not the landing), the three
  `Cache-Control` buckets, the security headers, gzip only when asked and only for text;
- a path that climbs out of `dist/` gets 404 — with a real file planted next to `dist/`,
  so the test has something it could actually leak;
- the throwaway environment: `FX_STORAGE=sqlite`, the db outside the repo and outside
  `/srv`, and `TELEGRAM_*` / `EDGE_SECRET` removed;
- `--host` anything but `127.0.0.1` exits 2, and so does a missing build — both before a
  socket is opened.

Two tests do start a process, and each earns it. One checks that the **real**
`api/handler.py` is wired in (health reports the version it was given, a lead comes back
`ok` and lands in the one-off db) — it runs in a subprocess because `handler` reads its
config at import, so a shared-suite run would otherwise measure another test's import.
The other kills the server with `SIGTERM` and checks the temp directory is gone; it takes
a kernel-assigned port (`--port 0`) so it can never collide with a Playwright run on 8007.

Proving they can fail: four in-memory mutations of the tool. Dropping the `/en` redirect,
serving the landing page instead of the 404 page, and returning a non-HTML type for
extensionless paths each turned their test red immediately. Removing the root check in
`resolve()` at first turned **nothing** red — `dist/` was a bare temp dir with nothing
above it to leak, so the test was decorative; the fixture now plants a file beside `dist/`
and the mutation goes red. The `SIGTERM` test needed no mutation: the first version of the
tool genuinely failed it, because Python's default `SIGTERM` handler skips `finally` and
left the database directory in `/tmp`.

## Local stack smoke (`scripts/smoke_local.py`)

This is one command for the four checks from `deploy/README.md` ("Що перевірено
руками"), run against gunicorn on this machine:

```
python3 scripts/smoke_local.py                        # default http://127.0.0.1:8005
python3 scripts/smoke_local.py http://localhost:8005
```

The script needs only the stdlib. It prints one `PASS`/`FAIL` line with a
reason for each check. Exit code `0` means all green, `1` means at least one
check is red, `2` means it refused to run.

| Check | Green only if |
|---|---|
| `GET /api/fx/health` | 200, `ok: true`, `version` non-empty **and not `0.3.0`**. `0.3.0` is the old Lambda: if health says `0.3.0`, you cannot tell which stack answered. |
| `GET /__smoke_nope__` | 404 |
| `GET /admin`, no cookie | 303. Redirects are **not** followed. |
| `POST /api/fx/lead`, `x-test: 1` | 200 with a lead `id`. The data is obviously fake (`SMOKE TEST (fake)`, `050-000-0000`). `"hp"` (honeypot) does not count. |

**It writes a lead, so it only talks to `127.0.0.1` / `localhost`.** Any other
host exits with code `2` before the first request. There is deliberately no
flag to allow a remote host, so this script never writes a lead to prod, not
even a test lead. Response bodies (the admin page included) are never printed.
The output shows only the status, the version and the lead id.

To run it against a throw-away stack, use the same command as `ExecStart`,
with every path outside the repo and invented secrets:

```
python3 -m venv /tmp/aluma-smoke-XXXX/venv
/tmp/aluma-smoke-XXXX/venv/bin/pip install -r deploy/requirements-server.txt
ss -ltnp | grep ':8005 '          # must print nothing: 8005 is ALUMA's port (~/maestro/PORTS.md)
env FX_STORAGE=sqlite FX_DB_PATH=/tmp/aluma-smoke-XXXX/aluma.db APP_VERSION=0.4.0-smoke \
    ADMIN_USER=x ADMIN_PASS=throwaway IP_SALT=throwaway \
    /tmp/aluma-smoke-XXXX/venv/bin/gunicorn -w 2 --threads 4 --timeout 60 \
    --no-control-socket -b 127.0.0.1:8005 api.wsgi:application
python3 scripts/smoke_local.py    # 4/4, exit 0
kill -TERM <master pid>           # the pid from ss -ltnp / "Listening at" — never pkill
```

Measured on 2026-09-11 (gunicorn 26.2.0, Python 3.12.3): `APP_VERSION=0.4.0-smoke`
gave 4/4 and exit 0. The same stack restarted with `APP_VERSION=0.3.0` gave
`FAIL GET /api/fx/health: version=0.3.0 — це стара Lambda`, 3/4 and exit 1.

`tests/test_smoke_local.py` (24 tests) needs no sockets. The transport is a
function, and the tests swap it for a fake. Most of the tests are the red
cases: `0.3.0`, an empty or missing version, `/admin` answering 200 or 302, a
lead without an id or with the honeypot id, 422, a closed port, and remote
hosts (the prod domain, the server IP, `0.0.0.0`, a `127.0.0.1@evil`
userinfo trick, `localhost.evil…`), which must give code 2 with zero
requests. To prove the tests can fail, the `0.3.0` check was switched off on
purpose: `test_lambda_version_is_red` went red. The check was then restored.

**Never start gunicorn here without `--no-control-socket`.** By default
gunicorn 26 opens a control socket at `$XDG_RUNTIME_DIR/gunicorn.ctl`
(`/run/user/<uid>/gunicorn.ctl`). If `XDG_RUNTIME_DIR` is not set, it uses
`~/.gunicorn/gunicorn.ctl`. Either way the path is per user, not per process. On start, gunicorn 26.2.0 deletes any
socket already there and puts its own in its place. On stop, it deletes
whatever socket is there. So a throw-away run as `ihor` would silently break
the control socket of the other gunicorn that runs as `ihor`
(`central-aparts-site`). The unit uses the flag for the same reason (see the
comment in `deploy/systemd/aluma-api.service`). The earlier measurements
above were taken before the flag was added. Those runs created the socket
and removed it on `kill -TERM`, and no other gunicorn was running as `ihor`
at the time.

## Prod vs box (`scripts/compare_sites.py`)

Before the DNS switch the migration plan (`aparts/docs/plans/2026-09-10-exit-aws-services-plan.md`,
Task 1.3 item 5) asks for zero differences between prod and the box. This is the command:

```
python3 build.py                                                   # dist/ and .build/ are gitignored
python3 scripts/compare_sites.py https://table.central-aparts.store dist
python3 scripts/compare_sites.py https://table.central-aparts.store https://box-table.central-aparts.store
python3 scripts/compare_sites.py A B --assets              # also every asset the pages reference
python3 scripts/compare_sites.py A B --ignore-eol          # CRLF vs LF is not a difference
python3 scripts/compare_sites.py A B --sitemap dist/sitemap.xml
```

Side A is always a URL. Side B is a URL **or a built folder**. A folder is read the way nginx
`try_files $uri $uri/ $uri/index.html` would serve it, so prod can be checked against a fresh
local build without opening a port. The URL list comes from `<A>/sitemap.xml` (or `--sitemap`),
plus `/sitemap.xml` and `/robots.txt` themselves. Only the path of each `<loc>` is used.

The output is one line per URL: `збігається` (same), `різниться` (differs), or `немає` (missing),
plus a short diff fragment. Exit code `0` means zero differences, `1` means differences,
`2` means an error: a broken or missing sitemap, a network error, or bad arguments.

**What is normalised: only the content hash in `/assets/` filenames.** `build.py` renames every
asset to `name.<sha256[:10]>.ext`, so one changed byte changes every page that links to it.
Nothing else varies between builds. `build.py` writes no dates, nonces or build ids, and two
builds of the same commit are byte-identical (checked with `diff -r`).

**Line endings are not normalised by default.** Before 2026-09-11 a build on Windows wrote CRLF
(`build.py` used text-mode `write_text`, and copytree kept the CRLF of an autocrlf checkout), and
a build on Linux wrote LF. Now `build.py` writes every text file with `newline="\n"` and UTF-8, and
normalises copied text sources to LF, so the same commit gives the same bytes on any OS
(`tests/test_build_eol.py`, below). The script reports a CRLF-only difference as its own line,
`лише кінці рядків` ("line endings only"). `--ignore-eol` switches it off, and only when you ask
for it. `--assets` is what makes hash normalisation honest: it checks that the files
behind the different hashed names are actually the same (CSS and JS are followed recursively,
so fonts are included).

Safety: GET only, and redirects are not followed. `/api/` and `/admin` are refused even if the
sitemap lists them (exit `2` before any page request). There is at least 0.6 s between network
requests, and `--delay` below 0.5 is refused.

Measured on 2026-09-11, prod against a local build of `master` in `dist/`:

| Run | Pages | Assets | Exit |
|---|---|---|---|
| default | 10: 0 same, 10 differ, **all "line endings only"** | — | 1 |
| `--assets` | same as above | 91: 88 same, 3 differ (`app-next.js`, `styles-next.css`, `favicon.svg`), all line endings only | 1 |
| `--assets --ignore-eol` | 10 same | 91 same | **0** |

So the content of prod equals the current `master` build. Every difference is CRLF: prod
(HTML `Last-Modified: 2026-09-09 16:14 UTC`, i.e. commit `8296742`) was built on Windows. That
is also why the CSS, JS and favicon hashes in prod differ from a Linux build. Images and fonts
are byte-identical. For the switch, either upload the same `dist/` to both sides (then a plain
run must give `0`), or accept CRLF explicitly with `--ignore-eol`.

`tests/test_compare_sites.py` (32 tests) uses no network: the transport and the clock are
injected. The required red cases are all there: a text difference after normalisation gives
`1`, a page on one side only gives `1` (404 and S3's 403), a difference in the build hash only
gives `0`, and a broken, empty or missing sitemap gives `2`. To prove the tests can fail,
normalisation was broken in memory (the file was not edited) and the suite re-run. With the
hash regex never matching, 6 tests went red, `test_only_build_hash_differs_exits_0` among them.
With a regex that erases the whole asset name, 3 went red, including
`test_hash_normalisation_is_not_a_blanket_wildcard`. With CRLF silently folded,
`test_crlf_only_is_a_difference_by_default` went red. The unbroken control run had 0 red.

## Build is the same on every OS (`tests/test_build_eol.py`)

`build.py` writes every text file with `newline="\n"` and UTF-8 (`write_text_lf`). After the copy
from `site/`, it rewrites the copied text sources (`.html .css .js .svg .xml .txt .webmanifest
.json`) to LF (`normalise_eol`). Images and fonts are not touched.

The 4 tests simulate Windows on any machine. First, text-mode writes with `newline=None` write
CRLF: `io.open` and `builtins.open` are patched. Patching `os.linesep` would not work, because
CPython's C io layer picks the Windows newline at compile time. Second, the text sources are CRLF,
the way a `core.autocrlf=true` checkout leaves them. Each build runs in a temporary copy of
`build.py`, `site/`, `i18n/` and `content.json`. The project's own `dist/` and `.build/` are not
touched.

| Test | Green only if |
|---|---|
| `test_simulation_really_writes_crlf` | the patched `open` really writes `\r\n`, so the other tests cannot pass vacuously |
| `test_windows_build_has_no_cr_in_any_text_file` | there is no CR byte in any `.html .css .js .svg .xml .txt`, in any extensionless page, or in `.build/asset-map.json` |
| `test_windows_build_is_byte_identical_to_linux_build` | the same file names (the same content hashes) and the same bytes |
| `test_two_builds_are_byte_identical` | two builds of one tree match byte for byte |

To prove the tests can fail, three broken versions of `build.py` were run. Each one made the two
Windows tests red. They were: the old `build.py` (text mode, no normalisation), the fixed one
without `normalise_eol`, and the fixed one without `newline="\n"`. The restored fix was 4/4 green.

Measured on 2026-09-11 on Linux. Two builds are identical under `diff -r`. The new build is
byte-identical to the build made before the fix, so nothing changed on Linux. The new build has 0
text files with CR. Prod (still the 09.09 Windows build) against this `dist/`: `--assets` gives
exit `1`, where all 10 pages and 3 assets are "line endings only". `--assets --ignore-eol` gives
exit `0`. This stays the same until prod is re-deployed from a build with the fix.

## Lambda path on moto (`tests/test_lambda_dynamodb.py`)

The question it answers: if only the backend of `master` goes to the existing Lambda
(`FX_STORAGE=dynamodb`) and the static site stays as it is, does the live form still work?
See `docs/PROD-NOTIFY-DECISION.md`.

- `prod_front_body()` builds the lead body the way `site/assets/app-next.js` does. On
  2026-09-11 that file was the same file as prod's `/assets/app-next.ba26d2a9fb.js` apart
  from CRLF. `test_builder_matches_the_shipped_form_exactly` reads the `var data = {...}`
  keys from the JS, so a new field in the form turns it red. Keys that are `undefined`
  (no UTM in the URL) are left out, the same as `JSON.stringify` does.
- `put_lead` on moto tables: 200 with `{ok, id}` only, the row in `fx_leads`, exactly one
  Telegram call. It also checks the English ad-click variant with attribution, and that
  an unknown `size`/`lang` from a stale tab is still 200. The 422 `errors` shape and the
  429 on the 6th lead per IP-hour are the two the front renders. `x-test: 1` is stored
  with **no** Telegram message. No `x-fx-edge` gives 403.
- `/api/fx/event` writes the batch and touches the session. Admin: 303 without a cookie,
  login, the dashboard shows the lead and `v<APP_VERSION>`, and the status change is
  stored. Health reports the version from the parameter.
- `ClientServerPhoneParityTests` runs `normalizePhone` from the JS under `node` against
  `normalize_phone` over 29 inputs: separators, `+972 (0)`, 07x, Arabic-Indic and
  full-width digits, more than 15 digits, foreign numbers. The result must be the same
  e164 and the same verdict.

The AWS credentials are replaced with fakes (`AWS_CONFIG_FILE` and
`AWS_SHARED_CREDENTIALS_FILE` point nowhere), and `mock_aws` intercepts botocore. The real
`fx_*` tables cannot be reached from here.

To prove the tests can fail, the handler was broken in memory with 5 mutations (no file
was edited). The control run had 0 red. "400 on an unknown size/lang" gave 3 red. "notify
is a no-op" gave 3 red. "The server phone rule lets 071 through" turned the parity test red
on `071-1234567`. "notify fires for x-test" gave 4 red.

## Lambda without FX_STORAGE (`tests/test_lambda_no_fx_storage.py`)

The question: if `master` reaches Lambda without `FX_STORAGE: dynamodb` from
`infra/template.yaml`, what happens to leads? The docs used to disagree ("200 and a silent
loss", "an empty db in /tmp", "500"). The answer is now a test.

- A fresh copy of `api/handler.py` is loaded with `FX_STORAGE` and `FX_DB_PATH` removed from
  the environment, so the defaults come from the code (`sqlite`, `data/aluma.db`).
- The working directory is a temp dir with mode `0555` (chdir into it) — the stand-in for the
  read-only `/var/task`. Nothing in `api/store.py` is patched: the real `os.makedirs` is
  refused by the real filesystem. The only difference from Lambda is the errno (`EACCES`
  here, `EROFS` there); both are `OSError` and nothing in `api/` looks at errno. As root
  `0555` does not block writes, so the file skips itself.
- Result: `POST /api/fx/lead` → 500 `{"ok": false, "error": "internal"}` on every try, no
  `notify()`, nothing on disk, one `{"event": "unhandled"}` log line. `POST /api/fx/event` →
  the same 500. `GET /api/fx/health` → 200: it never touches storage, so it stays green
  while the form is down. Control: with `FX_STORAGE=dynamodb` the disk is never touched.

To prove it can fail, two in-memory mutations (no file edited): the control run had 0 red of 6.
"`SqliteStore` falls back to `:memory:` on `OSError`" gave 3 red. "`put_lead` swallows the error
and answers 200" gave 2 red.

## Deploy parameters (`scripts/prod_notify_params.py`)

This script writes the CloudFormation parameters file for rolling the `master` backend out to
the `fx-table` stack (`docs/PROD-NOTIFY-DECISION.md`). No secret is ever printed.
`TelegramBotToken` and `OwnerTelegramChatId` are read from the `aparts-api` Lambda env.
`AppVersion` comes from the flag. Every other parameter already in the stack is written as
`UsePreviousValue`. The file is created with mode 0600 and never overwritten.

`tests/test_prod_notify_params.py` (15 tests) replaces aws-cli with a fake. The tests check:

- the parameter names read from the real `infra/template.yaml`;
- the file content: 10 entries, and `AdminPass`, `IpSalt`, `EdgeSecret` plus 4 more are
  `UsePreviousValue`. `LeadNotifyEmail` is gone. Every entry has exactly one of
  `ParameterValue` / `UsePreviousValue`;
- mode 0600;
- stdout never has the token, the chat id or any other env value;
- exactly two read calls. Write verbs are refused before they reach the runner;
- refusals, each with no file written and no value echoed: `0.3.0`, a malformed version,
  a missing token, an empty chat id, a malformed token, a new template parameter with no
  known source, `EdgeSecret` missing from the stack, `EdgeSecret` missing from the
  template (that would strip `x-fx-edge` from CloudFront), and an existing output file
  (left untouched).

To prove the tests can fail, the script was broken in memory with 5 mutations. The control
run had 0 red. "The report prints the values" turned `test_no_secret_on_stdout` red. "The
token shape accepts anything" turned the malformed-token test red. "Write verbs allowed"
turned the write-call test red. "0.3.0 allowed" turned the old-version test red. "No
MUST_KEEP guard" at first turned nothing red: the only test for it removed `EdgeSecret`
from the stack, and that case is already refused as "new parameter, no source". So a test
that removes `EdgeSecret` from the template was added, and with that test the mutation goes
red.
