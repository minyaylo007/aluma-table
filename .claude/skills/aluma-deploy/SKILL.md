---
name: "aluma-deploy"
description: "ALUMA: put a merged master commit on prod (this box) with scripts/deploy-box.sh, verify it live, and roll back with the same script."
argument-hint: "<sha> | --status | rollback <previous sha>"
user-invocable: true
disable-model-invocation: false
---

# /aluma-deploy — merge = deploy, by script

Owner rule п.31: a session that finished a change deploys it itself and reports **after**, with the rollback line.
No question to the owner or the conductor. Boundaries that never move: Caddy is not touched at all (no reload, stop,
run, start, admin socket, port 2019); only ALUMA's own user units `ihor-aluma-*` are restarted; `/opt/{iiko,uzd,atmo,
tennis,bots}` are not touched; nothing is fixed on prod by hand — a bad deploy is rolled back, then fixed in a PR.

## Where prod lives

| What | Where |
|---|---|
| Code the API runs from | clone `/opt/ihor/aluma-table` (detached checkout; `origin` = GitHub), venv `.venv` inside it |
| API unit | `ihor-aluma-api.service` (user unit; gunicorn 127.0.0.1:8005; env `~/.config/aluma/aluma.env`) |
| Purge timer | `ihor-aluma-purge.timer` |
| Static | `/srv/aluma` (Caddy serves it; files must be world-readable — the script's rsync sets `D0755,F0644`) |
| Health | `GET http://127.0.0.1:8005/api/fx/health` → `{"ok": true, "version": …}`; public: `https://table.central-aparts.store/api/fx/health` |
| Deploy log | `/opt/ihor/aluma-table/tmp/deploy-box.log` — one line per attempt: time, previous sha, new sha, result |

## Deploy

```bash
scripts/deploy-box.sh --status                 # sha on prod now, health, last log lines — WRITE THE SHA DOWN: it is your rollback
scripts/deploy-box.sh <merged master sha>      # fetch → checkout → pip (pinned server deps) → build → rsync → restart → health
```

What the script does, in order, and where it stops:
1. refuses a sha that is not on `origin/master`, a dirty tracked tree in the clone, or a missing unit;
2. `git fetch` + detached checkout of the sha in `/opt/ihor/aluma-table`;
3. `.venv/bin/pip install -r deploy/requirements-server.txt` (pinned; no-op when unchanged);
4. `build.py --production`; **if it refuses** (an owner fact is missing — 5 fields on 2026-10-13) the script restores
   the previous checkout and exits 3 without touching `/srv/aluma` or the units. Prod today serves a preview build;
   `--preview` deploys exactly that way — use it only when the conductor's task says so, and say so in the report;
5. `rsync -a --delete-after --delay-updates --chmod=D0755,F0644 dist/ /srv/aluma/`, then `find /srv/aluma ! -perm -o=r`
   must be empty;
6. `systemctl --user restart ihor-aluma-api.service` (only this unit; the purge timer keeps running);
7. health on 127.0.0.1:8005 must answer 200 with `"ok": true` within 30 s; otherwise the script **rolls back by itself**
   to the previous sha (steps 2–6 again) and exits 4.

## Verify live (GET only — no forms, no leads, no `smoke.spec.js`)

```bash
curl -s https://table.central-aparts.store/api/fx/health          # {"ok": true, "version": …}
curl -s -o /dev/null -w '%{http_code}\n' https://table.central-aparts.store/
curl -s -o /dev/null -w '%{http_code}\n' https://table.central-aparts.store/en/
```

## Rollback — the same script with the previous sha

```bash
scripts/deploy-box.sh <previous sha>            # e.g. the sha --status printed before the deploy
```
Rollback of **code** in the repository is still `git revert` + PR; the box just follows the sha you name.

## Report (to the conductor, after)

Sha on prod before and after, health line, the three GET codes, and the exact rollback command. If the deploy was
refused or rolled back: say which step, exit code, and that nothing was touched by hand.
