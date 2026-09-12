"""Перевірка всієї історії git (і журналів Actions) на секрети й персональні дані.

Контракт — specs/001-release-pipeline/contracts/secret-scan.md, шаблони — research.md R8.

    python3 scripts/secret_scan.py --repo <дзеркало> [--logs <тека журналів>] --report <звіт.md>

Друкує й пише у звіт ЛИШЕ: правило, коміт (коротке sha), шлях, номер рядка, кількість.
Значення, фрагмент рядка, сусідній текст — ніколи. Лише stdlib.

Код виходу: 0 — знахідок немає; 1 — є знахідки; 2 — помилка запуску (немає репозиторію тощо).
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import os
import pathlib
import re
import subprocess
import sys

# ── Правила вмісту: (id, regex). Шукаються лише в ДОДАНИХ рядках диффів і в рядках журналів.
_ENV_NAMES = r"(?:ADMIN_PASS|IP_SALT|EDGE_SECRET|TELEGRAM_BOT_TOKEN|AdminPass|IpSalt|EdgeSecret|TelegramBotToken)"
# Заглушки, що не є значенням: порожньо, <set-me>, ${X}, $X, ..., ***, а також екранований кінець рядка
# у коді («ADMIN_PASS=\n» у рядковому літералі — порожнє значення).
_PLACEHOLDER = r"(?:<[^>]*>|\$\{[^}]*\}|\$[A-Za-z_]\w*|\.\.\.|…|\*+|\\[nrt])"

CONTENT_RULES = [
    ("aws_access_key_id", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])")),
    ("aws_secret_access_key", re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*[\"']?[A-Za-z0-9/+]{20,}")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})")),
    # У URL токен стоїть одразу після «bot» (…/bot<id>:<secret>/…), тож перед ним дозволена літера.
    ("telegram_bot_token", re.compile(r"(?<![\d:])\d{6,12}:[A-Za-z0-9_-]{30,}")),
    ("env_secret", re.compile(
        r"(?<![A-Za-z0-9_])" + _ENV_NAMES + r"=(?![\s\"'`]*(?:$|#|" + _PLACEHOLDER + r"))[\"']?[^\s\"'`]+")),
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
    ("phone_il", re.compile(r"(?<![\w+])(?:\+972[\s-]?\(?0?\)?[\s-]?[2-9]\d?|05\d)[\s-]?\d{3}[\s-]?\d{4}(?!\d)")),
    ("phone_ua", re.compile(r"(?<![\w+])(?:\+?380[\s-]?\(?\d{2}\)?|\(?0[3-9]\d\)?)[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")),
    ("json_pii", re.compile(
        r"\"name\"\s*:\s*\"[^\"]+\".*\"phone\"\s*:\s*\"[^\"]+\"|\"phone\"\s*:\s*\"[^\"]+\".*\"name\"\s*:\s*\"[^\"]+\"")),
    ("aws_arn_account", re.compile(r"arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:\d{12}:")),
    # Опис слабких місць машини (права, sudo, сокети, чужі дані) — разом з IP це карта для атакувальника.
    # Слова розбиті групами (?:…), щоб цей рядок сам не спрацьовував на власний шаблон.
    ("host_security_detail", re.compile(
        r"(?i)Administrator(?:Access)|NOPASS(?:WD)|sudo\s+без\s+(?:пароля)|admin(?:\.sock)"
        r"|hetzner(?:-box)|delete(?:_repo)|admin(?::org)|паці(?:єнт)|паци(?:ент)|pati(?:ent)s?\b")),
]

# ── Правила шляхів: файл, який узагалі не мав потрапити в git (додано чи змінено — однаково).
def _path_rule(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    if (name == ".env" or name.startswith(".env.") or name.endswith(".env")) and not name.endswith(".example"):
        return "path_env_file"
    if path == "infra/samconfig.toml" or path.endswith("/samconfig.toml"):
        return "path_samconfig"
    if re.match(r"(?:.*/)?dump[^/]*/", path) or (name.startswith("dump") and name.endswith(".jsonl")):
        return "path_dump"
    if path.startswith("data/") or name.endswith((".db", ".sqlite", ".sqlite3")):
        return "path_sqlite_db"
    return None


Finding = collections.namedtuple("Finding", "rule commit path line")

_COMMIT = re.compile(r"^commit ([0-9a-f]{40})")
_DIFF = re.compile(r"^diff --git a/(.*) b/(.*)$")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _unquote(path: str) -> str:
    if len(path) >= 2 and path[0] == path[-1] == '"':
        return path[1:-1]
    return path


def scan_line(text: str):
    """Повертає множину правил, що спрацювали на рядку. Значення не повертається."""
    return {rule for rule, rx in CONTENT_RULES if rx.search(text)}


def scan_git(repo: pathlib.Path, findings: list) -> None:
    proc = subprocess.Popen(
        ["git", "-C", str(repo), "log", "--all", "-p", "--no-color", "--no-ext-diff", "--no-textconv"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    sha, path, new_line, in_hunk = "", "", 0, False
    seen_paths = set()
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        m = _COMMIT.match(line)
        if m:
            sha, path, in_hunk = m.group(1), "", False
            continue
        m = _DIFF.match(line)
        if m:
            path, in_hunk = _unquote(m.group(2)), False
            rule = _path_rule(path)
            if rule and (rule, sha, path) not in seen_paths:
                seen_paths.add((rule, sha, path))
                findings.append(Finding(rule, sha, path, 0))
            continue
        m = _HUNK.match(line)
        if m:
            new_line, in_hunk = int(m.group(1)), True
            continue
        if not in_hunk:
            continue
        if line.startswith("+"):
            for rule in sorted(scan_line(line[1:])):
                findings.append(Finding(rule, sha, path, new_line))
            new_line += 1
        elif line.startswith(" "):
            new_line += 1
        elif line.startswith("-") or line.startswith("\\"):
            pass
        else:
            in_hunk = False
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"git log завершився з кодом {proc.returncode}")


def scan_logs(logs: pathlib.Path, findings: list) -> int:
    count = 0
    for file in sorted(p for p in logs.rglob("*") if p.is_file()):
        count += 1
        rel = file.relative_to(logs).as_posix()
        with file.open("rb") as fh:
            for no, raw in enumerate(fh, 1):
                for rule in sorted(scan_line(raw.decode("utf-8", "replace"))):
                    findings.append(Finding(rule, "-", "logs/" + rel, no))
    return count


def _is_repo_root(repo: pathlib.Path) -> bool:
    """Корінь робочої копії або голе дзеркало — але не тека всередині чужого репозиторію."""
    def rev_parse(flag):
        p = subprocess.run(["git", "-C", str(repo), "rev-parse", flag], capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None

    if rev_parse("--is-bare-repository") == "true":
        git_dir = rev_parse("--absolute-git-dir")
        return bool(git_dir) and os.path.samefile(git_dir, repo)
    top = rev_parse("--show-toplevel")
    return bool(top) and os.path.samefile(top, repo)


def _git_count(repo, *args) -> int:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout
    return len([x for x in out.splitlines() if x.strip()])


def render(findings, scope) -> str:
    lines = [
        "# Звіт secret_scan.py",
        "",
        f"Дата: {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "## Охоплення",
        "",
    ]
    lines += [f"- {k}: {v}" for k, v in scope.items()]
    lines += ["", "## Знахідки (без значень)", ""]
    if not findings:
        lines += ["Знахідок немає.", ""]
        return "\n".join(lines)
    groups = collections.OrderedDict()
    for f in sorted(findings, key=lambda f: (f.rule, f.path, f.commit, f.line)):
        groups.setdefault((f.rule, f.path), []).append(f)
    lines += ["| правило | шлях | збігів | коміти:рядки |", "|---|---|---|---|"]
    for (rule, path), items in groups.items():
        locs = sorted({f"{f.commit[:10]}:{f.line}" for f in items})
        shown = ", ".join(locs[:20]) + (f", … (+{len(locs) - 20})" if len(locs) > 20 else "")
        lines.append(f"| {rule} | {path} | {len(items)} | {shown} |")
    lines += ["", "## Разом за правилами", ""]
    for rule, n in sorted(collections.Counter(f.rule for f in findings).items()):
        lines.append(f"- {rule}: {n}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Пошук секретів і ПД в історії git без друку значень.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--logs")
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)

    repo = pathlib.Path(args.repo)
    if not repo.is_dir():
        print(f"помилка: немає теки {repo}", file=sys.stderr)
        return 2
    if not _is_repo_root(repo):
        print(f"помилка: {repo} — не корінь репозиторію git", file=sys.stderr)
        return 2
    if args.logs and not pathlib.Path(args.logs).is_dir():
        print(f"помилка: немає теки журналів {args.logs}", file=sys.stderr)
        return 2

    findings: list = []
    try:
        scan_git(repo, findings)
        scope = collections.OrderedDict([
            ("комітів (git rev-list --all)", _git_count(repo, "rev-list", "--all")),
            ("посилань (git for-each-ref)", _git_count(repo, "for-each-ref")),
        ])
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"помилка: {type(exc).__name__}", file=sys.stderr)
        return 2
    if args.logs:
        scope["файлів журналів"] = scan_logs(pathlib.Path(args.logs), findings)

    report = render(findings, scope)
    pathlib.Path(args.report).write_text(report, encoding="utf-8", newline="\n")

    by_rule = collections.Counter(f.rule for f in findings)
    for f in sorted(findings, key=lambda f: (f.rule, f.path, f.commit, f.line))[:200]:
        print(f"{f.rule}\t{f.commit[:10]}\t{f.path}:{f.line}")
    if len(findings) > 200:
        print(f"… ще {len(findings) - 200} — див. звіт")
    print(f"знахідок: {len(findings)}" + (" (" + ", ".join(f"{r}={n}" for r, n in sorted(by_rule.items())) + ")"
                                         if by_rule else ""))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
