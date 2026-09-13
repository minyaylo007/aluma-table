"""Пошук секретів і персональних даних у репозиторії ALUMA — без друку значень.

Спільний сканер флоту: правила й рушій звірені з бек-офісом
(`~/repos/aparts/scripts/secret_scan.py`, 13.09.2026) — саме його правила знайшли в іншому
проєкті коди дверей і пароль WiFi, і знайшли їх у документах, а не в коді.

Чотири джерела (прапорець --mode, типово all):

    tree     робоче дерево: файли, які зараз під контролем git (git ls-files)
    history  уся історія: доданi рядки диффів комітів (git log <--rev> -p)
    blobs    усі досяжні об'єкти-файли (git rev-list --objects <--rev>) — ловить і те,
             що в дифф не потрапило: вміст, доданий лише при злитті, і гілки без комітів
    all      усе перелічене

Обсяг історії задає --rev (можна кілька разів, типово --all). Так відокремлюється
ПУБЛІЧНА історія від приватного архіву:

    --rev refs/remotes/origin/master                            # лише те, що бачить світ
    --rev=--all --rev=--not --rev refs/remotes/origin/master    # лише приватний архів

Значення, що саме починається з «-», передається через «=» — інакше argparse вважає його
прапорцем і завершується з кодом 2.

Запуск (звіт — ЛИШЕ поза репозиторієм, каталог 700):

    python3 scripts/secret_scan.py --repo . --mode all --report /tmp/…/scan.md
    python3 scripts/secret_scan.py --repo . --mode tree \\
        --baseline .github/secret-scan-baseline.json --report "$RUNNER_TEMP/tree.md"

У stdout іде ТІЛЬКИ підсумок за правилами — жодного шляху, коміта чи значення (журнал
Actions публічного репозиторію бачить увесь світ). У звіт — правило, коміт (коротке sha),
шлях, номер рядка, довжина збігу і незворотний відбиток sha256[:12] для класів із високою
ентропією. Саме значення — ключ, телефон, ім'я, код дверей — не потрапляє нікуди.

Базова лінія (--baseline) — перелік уже переглянутих місць виду «правило, шлях, скільки».
Знахідка, яка в ній є, у підсумку окремо позначена як відома; код виходу 1 дають лише НОВІ.
Оновити перелік після свідомого перегляду: --update-baseline.

Код виходу: 0 — нових знахідок немає; 1 — є; 2 — помилка запуску.
Лише stdlib.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

# ── Імена змінних і параметрів, значення яких є секретом.
# Разом форми з оточення (SNAKE_CASE) і параметри шаблону SAM (CamelCase). Перші два рядки —
# ALUMA, далі — решта флоту: сканер один на всі проєкти, зайве ім'я нічого не коштує.
_SECRET_NAMES = (
    r"(?:ADMIN_PASS|IP_SALT|EDGE_SECRET|TELEGRAM_BOT_TOKEN|TELEGRAM_WEBHOOK_SECRET"
    r"|AdminPass|IpSalt|EdgeSecret|TelegramBotToken|TelegramWebhookSecret"
    r"|SECRET_KEY|ADMIN_PASSWORD|HOUSEKEEPING_PASSWORD|MONOBANK_TOKEN|OPENWEATHER_API_KEY"
    r"|PUBLIC_API_KEY|TURBOSMS_TOKEN|CFO_WEBHOOK_TOKEN|BEDS24_TOKEN|BEDS24_REFRESH_TOKEN"
    r"|RESTIC_PASSWORD|ANTHROPIC_API_KEY|OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN"
    r"|DB_PASSWORD|SMTP_PASSWORD|TTLOCK_PASSWORD|WHATSAPP_TOKEN"
    r"|SecretKey|AdminPassword|HousekeepingPassword|MonobankToken|OpenWeatherApiKey"
    r"|PublicApiKey|TurbosmsToken|CfoWebhookToken)"
)

# Те, що стоїть праворуч від «=» і значенням не є:
#   порожньо, <set-me>, ${X}, $X, {{X}}, %X%, ..., ***, xxx, екранований кінець рядка;
#   слова-заглушки зі зразків (change-this-…, your-…-here, replace-me, dummy, sample);
#   вираз коду — виклик чи звертання через крапку (os.environ.get(...), Config.X, !Ref).
_PLACEHOLDER = (
    r"(?:<[^>]*>|\$\{[^}]*\}|\$[A-Za-z_]\w*|\{\{[^}]*\}\}|%[A-Za-z_]\w*%"
    r"|\.\.\.|…|\*{2,}|[xX]{3,}|\\[nrt]"
    r"|(?i:change|replace|your|put|set|todo|dummy|fake|sample|example|none|null)[\w-]*"
    r"|!?(?i:ref|sub|getatt|fn::)[\w:]*"
    r"|[A-Za-z_]\w*\s*\(|[A-Za-z_]\w*(?:\.\w+)+)"
)

# Домени, у яких адреса завідомо вигадана (приклади в документації й тестах).
# .invalid і .test зарезервовані RFC 2606 саме під це.
_FAKE_MAIL = (r"(?:example\.(?:com|org|net)|[A-Za-z0-9.-]*\.(?:invalid|test|local|localhost)"
              r"|localhost|sentry\.io)")

# Ключ у вигляді «назва: значення» всередині JSON/YAML, напр. заголовок X-Token.
_TOKEN_KEYS = r"(?:[Xx]-[Tt]oken|api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|bearer)"

CONTENT_RULES = [
    # ── Ключі й токени ─────────────────────────────────────────────────────────
    ("aws_access_key_id", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])")),
    ("aws_secret_access_key", re.compile(
        r"(?i)aws_secret_access_key\s*[=:]\s*[\"']?[A-Za-z0-9/+]{20,}")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})")),
    # У URL токен бота стоїть одразу після «bot» (…/bot<id>:<secret>/…), тож перед ним
    # дозволена літера.
    ("telegram_bot_token", re.compile(r"(?<![\d:])\d{6,12}:[A-Za-z0-9_-]{30,}")),
    # Особистий токен monobank — 43 знаки base64url; сам по собі непримітний,
    # тож ловимо його за іменем змінної або за заголовком запиту.
    ("monobank_token", re.compile(
        r"(?i)(?:monobank[_-]?token|x-token)[\"']?\s*[=:]\s*[\"']?[A-Za-z0-9_-]{20,}")),
    ("llm_api_key", re.compile(r"\bsk-(?:ant-|proj-|or-)?[A-Za-z0-9_-]{24,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
    ("named_secret", re.compile(
        r"(?<![A-Za-z0-9_])" + _SECRET_NAMES +
        r"\"?\s*[=:]\s*(?![\s\"'`]*(?:$|#|//|" + _PLACEHOLDER + r"))[\"']?[^\s\"'`,]{6,}")),
    ("token_key_value", re.compile(
        r"(?<![A-Za-z0-9_])" + _TOKEN_KEYS +
        r"\"?\s*[=:]\s*(?![\s\"'`]*(?:$|#|//|" + _PLACEHOLDER + r"))[\"']?[A-Za-z0-9_./+-]{16,}")),
    # Обліковий запис усередині рядка підключення: схема, далі ім'я, двокрапка,
    # пароль і равлик перед вузлом (postgres, mysql, mongodb, redis, amqp, ftp, http).
    ("connection_string", re.compile(
        r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|ftp|https?)://"
        r"[A-Za-z0-9._%-]+:(?!(?:" + _PLACEHOLDER + r")@)[^\s:@/\"']{4,}@")),
    ("aws_arn_account", re.compile(r"arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:\d{12}:")),

    # ── Персональні дані ───────────────────────────────────────────────────────
    # Ізраїльський номер — головна ПД ALUMA: заявка з лендінга це ім'я і телефон.
    ("phone_il", re.compile(
        r"(?<![\w+])(?:\+972[\s-]?\(?0?\)?[\s-]?[2-9]\d?|05\d)[\s-]?\d{3}[\s-]?\d{4}(?!\d)")),
    ("phone_ua", re.compile(
        r"(?<![\w+.])(?:\+?38[\s-]?\(?0\d{2}\)?|\(?0[3-9]\d\)?)[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?![\d-])")),
    ("email", re.compile(
        r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{2,}@(?!" + _FAKE_MAIL + r"\b)"
        r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # Ім'я і телефон поруч в одному рядку JSON — вивантаження заявок.
    ("json_pii", re.compile(
        r"\"(?:guest_)?name\"\s*:\s*\"[^\"]+\".*\"(?:guest_)?phone\"\s*:\s*\"[^\"]+\""
        r"|\"(?:guest_)?phone\"\s*:\s*\"[^\"]+\".*\"(?:guest_)?name\"\s*:\s*\"[^\"]+\"")),
    # Номер паспорта/ID-картки та податковий номер — лише поряд зі словом-контекстом,
    # інакше правило ловить будь-які цифри.
    ("passport_number", re.compile(
        r"(?i)(?:паспорт\w*|passport|посвідч\w*|id[_ -]?card)\W{0,12}"
        r"(?:[А-ЯЇІЄA-Z]{2}\s?\d{6}|\d{9})\b")),
    ("tax_number", re.compile(
        r"(?i)(?:\bІПН\b|\bИНН\b|\bРНОКПП\b|\bЄДРПОУ\b|\bedrpou\b|\btax[_ -]?(?:id|number)\b|\"inn\")"
        r"\W{0,12}\d{8,10}\b")),
    # Реквізити отримувача платежу: рахунок і банк власника бізнесу.
    ("iban_ua", re.compile(r"\bUA\d{2}[\dA-Z]{25}\b")),
    ("card_pan", re.compile(r"(?<![\d.-])(?:\d{4}[ -]?){3}\d{4}(?![\d.-])")),

    # ── Опис слабких місць машини (права, sudo, сокети, чужі бойові дані) ──────
    # Слова розбиті групами (?:…), щоб цей файл сам не спрацьовував на власний шаблон.
    ("host_security_detail", re.compile(
        r"(?i)Administrator(?:Access)|NOPASS(?:WD)|sudo\s+без\s+(?:пароля)"
        r"|admin(?:\.sock)|:2019/(?:config)|hetzner(?:-box)|delete(?:_repo)|admin(?::org)"
        # \b перед pati… обов'язковий: без нього правило ловить хвіст англійського
        # слова «im» + те саме коріння (нетерплячий) у звичайному тексті сторінки.
        r"|паці(?:єнт)|паци(?:ент)|\bpati(?:ent)s?\b")),
    # Код замка поруч зі словом «двері»/«під'їзд»/«квартира»/«entry»/«apartment» —
    # його друк дорівнює видачі ключа від квартири. Виняток `(?<!_)` перед словом-кодом
    # відрізняє параметр коду (`apt_code`, `door_code`) від прози: у коді слово `code`
    # приклеєне через `_`, у живому тексті — ніколи; поле конфігурації ловить
    # access_code_field нижче. Приклади справжніх форм (цифри тут — NNNN, щоб коментар
    # сам не був знахідкою): «code: NNNN», «Код дверей — NNNN», «code#NNNN», «Код дверей, NNNN».
    ("door_code", re.compile(
        r"(?i)(?:двер\w*|двор\w*|замк\w*|кімнат\w*|під'?їзд\w*|домофон\w*|квартир\w*|door|lock"
        r"|ttlock|entry|entrance|gate|intercom|apartment|apt|flat|room)"
        r"[^\n]{0,20}?(?<!_)(?:код\w*|code|pin)[^\w\n]{0,10}\d{4,8}"
        r"|(?<!_)(?:код\w*|code|pin)[^\n]{0,20}?(?:двер\w*|двор\w*|замк\w*|кімнат\w*|під'?їзд\w*"
        r"|домофон\w*|квартир\w*|door|lock|ttlock|entry|entrance|gate|intercom|apartment|apt|flat|room)"
        r"[^\w\n]{0,10}\d{4,8}")),
    # Те саме, але записане полем конфігурації чи фікстури: ім'я поля виду
    # yard-entry-code / door-code / wifi-password (через підкреслення) і значення
    # в лапках АБО голими цифрами (`door_code: NNNN` у YAML, JSON, журналі).
    # Ім'я поля тут і є контекстом, тому слово «двері» поруч не потрібне.
    ("access_code_field", re.compile(
        r"(?i)\b(?:yard_entry_code|entry_code|apartment_code|door_code|access_code|lock_code"
        r"|pin_code|gate_code|wifi_password|wifi_pass|wifi_key)"
        r"[\"\x27]?\s*[=:]\s*(?![\s\"\x27`]*(?:$|#|//|" + _PLACEHOLDER + r"))"
        r"(?:[\"\x27][^\"\x27\n]{4,}[\"\x27]|\d{4,})")),
    # Пароль мережі WiFi: «WiFi: <мережа> / <пароль>», «SSID … password …».
    # Значення в дужках («(задається в редагуванні кімнати)») паролем не є.
    ("wifi_credentials", re.compile(
        r"(?i)(?<![\w-])(?:wi-?fi|ssid)(?![\w-])[^\n]{0,40}?"
        r"(?:/|пароль|password|pass|ключ)(?![\w-])\s*:?\s*"
        r"(?![\s(<{\x27\"])(?![a-z]+(?:_[a-z]+)+(?![\w-]))[A-Za-z0-9._!@#$%^&*-]{6,}")),
]

# Класи з високою ентропією: для них у звіті безпечно показати незворотний відбиток
# значення — він дозволяє звірити «це той самий ключ у 30 комітах», не знаючи ключа.
# Для персональних даних відбиток НЕ рахується: простір значень малий (телефон — 9 цифр),
# і хеш від нього підбирається перебором за секунди.
_FINGERPRINTED = frozenset({
    "aws_access_key_id", "aws_secret_access_key", "github_token", "telegram_bot_token",
    "monobank_token", "llm_api_key", "google_api_key", "slack_token", "jwt",
    "named_secret", "token_key_value", "connection_string",
})


def _path_rule(path: str) -> str | None:
    """Файл, якого в git бути не мало — незалежно від вмісту."""
    name = path.rsplit("/", 1)[-1]
    low = path.lower()
    if (name == ".env" or name.startswith(".env.") or name.endswith(".env")) and not name.endswith(
            (".example", ".sample", ".template")):
        return "path_env_file"
    if name == "samconfig.toml":
        return "path_samconfig"
    if name == "settings.local.json" or low.endswith(".claude/settings.local.json"):
        return "path_claude_local"
    # Вивантаження заявок: dump/ і data/ заборонені .gitignore прямо — ім'я, телефон, згода.
    if re.match(r"(?:.*/)?dump[^/]*/", path) or (name.startswith("dump") and name.endswith(".jsonl")):
        return "path_dump"
    if path.startswith("data/") or name.endswith((".db", ".sqlite", ".sqlite3")):
        return "path_sqlite_db"
    if name.endswith((".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")) or name.startswith("id_rsa"):
        return "path_key_file"
    return None


Finding = collections.namedtuple("Finding", "rule origin path line length ident")

_COMMIT = re.compile(r"^commit ([0-9a-f]{40})")
_DIFF = re.compile(r"^diff --git a/(.*) b/(.*)$")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".woff", ".woff2",
             ".ttf", ".otf", ".eot", ".mp4", ".webp", ".avif", ".so", ".pyc")
_MAX_BYTES = 8 * 1024 * 1024


def _fingerprint(rule: str, value: str) -> str:
    if rule not in _FINGERPRINTED:
        return "-"
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:12]


def scan_line(text: str) -> set:
    """Множина правил, що спрацювали на рядку. Значення не повертається ніколи."""
    return {rule for rule, rx in CONTENT_RULES if rx.search(text)}


def _line_findings(text: str, origin: str, path: str, line: int) -> list:
    out = []
    for rule, rx in CONTENT_RULES:
        m = rx.search(text)
        if m:
            value = m.group(0)
            out.append(Finding(rule, origin, path, line, len(value), _fingerprint(rule, value)))
    return out


def _git(repo: pathlib.Path, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, **kw)


def _scan_path(path: str, origin: str, findings: list, seen: set) -> None:
    rule = _path_rule(path)
    if rule and (rule, origin, path) not in seen:
        seen.add((rule, origin, path))
        findings.append(Finding(rule, origin, path, 0, 0, "-"))


def scan_tree(repo: pathlib.Path, findings: list) -> int:
    """Файли, які зараз під контролем git у робочому дереві."""
    proc = _git(repo, "ls-files", "-z", check=True)
    paths = [p for p in proc.stdout.split("\0") if p]
    seen: set = set()
    for rel in paths:
        _scan_path(rel, "tree", findings, seen)
        file = repo / rel
        if not file.is_file() or file.is_symlink():
            continue
        if rel.lower().endswith(_SKIP_EXT) or file.stat().st_size > _MAX_BYTES:
            continue
        with file.open("rb") as fh:
            if b"\0" in fh.read(8192):
                continue
            fh.seek(0)
            for no, raw in enumerate(fh, 1):
                findings.extend(_line_findings(raw.decode("utf-8", "replace").rstrip("\n"),
                                               "tree", rel, no))
    return len(paths)


def scan_history(repo: pathlib.Path, revs: list, findings: list) -> None:
    """Додані рядки диффів комітів заданого обсягу (типово всіх посилань)."""
    proc = subprocess.Popen(
        ["git", "-C", str(repo), "log", *revs, "-p", "--no-color", "--no-ext-diff", "--no-textconv"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    sha, path, new_line, in_hunk = "", "", 0, False
    seen: set = set()
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        m = _COMMIT.match(line)
        if m:
            sha, path, in_hunk = m.group(1), "", False
            continue
        m = _DIFF.match(line)
        if m:
            path, in_hunk = _unquote(m.group(2)), False
            _scan_path(path, sha, findings, seen)
            continue
        m = _HUNK.match(line)
        if m:
            new_line, in_hunk = int(m.group(1)), True
            continue
        if not in_hunk:
            continue
        if line.startswith("+"):
            if not path.lower().endswith(_SKIP_EXT):
                findings.extend(_line_findings(line[1:], sha, path, new_line))
            new_line += 1
        elif line.startswith(" "):
            new_line += 1
        elif line.startswith(("-", "\\")):
            pass
        else:
            in_hunk = False
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"git log завершився з кодом {proc.returncode}")


def scan_blobs(repo: pathlib.Path, revs: list, findings: list) -> int:
    """Усі досяжні об'єкти-файли: ловить і те, що в дифф не потрапило (злиття, обірвані гілки)."""
    listing = subprocess.Popen(
        ["git", "-C", str(repo), "rev-list", "--objects", *revs],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    blobs: dict = {}
    for raw in listing.stdout:
        parts = raw.decode("utf-8", "replace").rstrip("\n").split(" ", 1)
        if len(parts) == 2 and parts[1]:
            blobs.setdefault(parts[0], parts[1])
    listing.wait()

    # Типи всіх об'єктів — одним викликом, інакше на кожен об'єкт окремий процес.
    kinds = {}
    check = _git(repo, "cat-file", "--batch-check", "--batch-all-objects")
    for row in check.stdout.splitlines():
        parts = row.split()
        if len(parts) >= 2:
            kinds[parts[0]] = parts[1]

    seen: set = set()
    count = 0
    for sha, path in blobs.items():
        if kinds.get(sha) != "blob":
            continue
        count += 1
        _scan_path(path, "blob", findings, seen)
        if path.lower().endswith(_SKIP_EXT):
            continue
        data = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", sha],
                              capture_output=True).stdout
        if len(data) > _MAX_BYTES or b"\0" in data[:8192]:
            continue
        for no, raw in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            findings.extend(_line_findings(raw, "blob:" + sha, path, no))
    return count


def scan_logs(logs: pathlib.Path, findings: list) -> int:
    """Журнали прогонів Actions, вивантажені окремо (`gh run view <id> --log`)."""
    count = 0
    for file in sorted(p for p in logs.rglob("*") if p.is_file()):
        count += 1
        rel = file.relative_to(logs).as_posix()
        with file.open("rb") as fh:
            for no, raw in enumerate(fh, 1):
                findings.extend(_line_findings(raw.decode("utf-8", "replace").rstrip("\n"),
                                               "-", "logs/" + rel, no))
    return count


def _unquote(path: str) -> str:
    if len(path) >= 2 and path[0] == path[-1] == '"':
        return path[1:-1]
    return path


def _is_repo_root(repo: pathlib.Path) -> bool:
    """Корінь робочої копії або голе дзеркало — але не тека всередині чужого репозиторію."""
    def rev_parse(flag):
        p = _git(repo, "rev-parse", flag)
        return p.stdout.strip() if p.returncode == 0 else None

    if rev_parse("--is-bare-repository") == "true":
        git_dir = rev_parse("--absolute-git-dir")
        return bool(git_dir) and os.path.samefile(git_dir, repo)
    top = rev_parse("--show-toplevel")
    return bool(top) and os.path.samefile(top, repo)


def _git_count(repo, *args) -> int:
    out = _git(repo, *args, check=True).stdout
    return len([x for x in out.splitlines() if x.strip()])


# ── Базова лінія: перелік уже переглянутих місць ────────────────────────────────
def load_baseline(path: pathlib.Path) -> dict:
    """{(правило, шлях): скільки збігів там дозволено}. Формат — див. --update-baseline."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(e["rule"], e["path"]): int(e["count"]) for e in data["entries"]}


def split_by_baseline(findings: list, baseline: dict):
    """Ділить знахідки на нові й відомі: відомі — перші `count` збігів пари (правило, шлях)."""
    left = dict(baseline)
    new, known = [], []
    for f in sorted(findings, key=lambda f: (f.rule, f.path, f.origin, f.line)):
        key = (f.rule, f.path)
        if left.get(key, 0) > 0:
            left[key] -= 1
            known.append(f)
        else:
            new.append(f)
    stale = sorted(key for key, rest in left.items() if rest > 0)
    return new, known, stale


def render_baseline(findings: list) -> str:
    counts = collections.Counter((f.rule, f.path) for f in findings)
    data = {
        "comment": "Переглянуті місця: значень немає, тільки правило, шлях і кількість збігів. "
                   "Оновлювати лише свідомо — див. docs/security/secret-scan-2026-09-13.md.",
        "updated": dt.date.today().isoformat(),
        "entries": [{"rule": r, "path": p, "count": n} for (r, p), n in sorted(counts.items())],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def render(findings, scope, known=(), stale=()) -> str:
    lines = [
        "# Звіт secret_scan.py",
        "",
        f"Дата: {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "Значень тут немає за побудовою: лише правило, місце, довжина збігу і незворотний",
        "відбиток (для класів із високою ентропією).",
        "",
        "## Охоплення",
        "",
    ]
    lines += [f"- {k}: {v}" for k, v in scope.items()]
    if known:
        lines += [f"- відомих за базовою лінією (не показані нижче): {len(known)}"]
    if stale:
        lines += ["", "Записи базової лінії, яких у дереві вже немає (можна прибрати): "
                      + ", ".join(f"{rule}:{path}" for rule, path in stale)]
    lines += ["", "## Знахідки (без значень)", ""]
    if not findings:
        lines += ["Знахідок немає.", ""]
        return "\n".join(lines)
    groups: dict = collections.OrderedDict()
    for f in sorted(findings, key=lambda f: (f.rule, f.path, f.origin, f.line)):
        groups.setdefault((f.rule, f.path), []).append(f)
    lines += ["| правило | шлях | збігів | довжини | відбитки | місця |", "|---|---|---|---|---|---|"]
    for (rule, path), items in groups.items():
        locs = sorted({f"{f.origin[:10]}:{f.line}" for f in items})
        shown = ", ".join(locs[:12]) + (f", … (+{len(locs) - 12})" if len(locs) > 12 else "")
        lengths = ", ".join(str(n) for n in sorted({f.length for f in items})[:6])
        idents = sorted({f.ident for f in items if f.ident != "-"})
        ident = ", ".join(idents[:4]) + (f", … (+{len(idents) - 4})" if len(idents) > 4 else "")
        lines.append(f"| {rule} | {path} | {len(items)} | {lengths} | {ident or '-'} | {shown} |")
    lines += ["", "## Разом за правилами", ""]
    for rule, n in sorted(collections.Counter(f.rule for f in findings).items()):
        lines.append(f"- {rule}: {n}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Пошук секретів і персональних даних у git без друку значень.")
    ap.add_argument("--repo", required=True, help="корінь репозиторію або голе дзеркало")
    ap.add_argument("--mode", choices=("tree", "history", "blobs", "all"), default="all")
    ap.add_argument("--rev", action="append", default=None,
                    help="обсяг історії для history/blobs (можна кілька разів); типово --all")
    ap.add_argument("--logs", help="тека з вивантаженими журналами Actions")
    ap.add_argument("--baseline", help="перелік уже переглянутих місць (JSON)")
    ap.add_argument("--update-baseline", action="store_true",
                    help="переписати файл --baseline поточними знахідками")
    ap.add_argument("--report", required=True, help="файл звіту — поза репозиторієм, у каталозі 700")
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
    if args.update_baseline and not args.baseline:
        print("помилка: --update-baseline без --baseline", file=sys.stderr)
        return 2

    revs = args.rev or ["--all"]
    findings: list = []
    scope: dict = collections.OrderedDict([("режим", args.mode), ("обсяг історії", " ".join(revs))])
    try:
        if args.mode in ("tree", "all"):
            bare = _git(repo, "rev-parse", "--is-bare-repository").stdout.strip() == "true"
            scope["файлів у дереві"] = 0 if bare else scan_tree(repo, findings)
        if args.mode in ("history", "all"):
            scan_history(repo, revs, findings)
            scope["комітів (rev-list)"] = _git_count(repo, "rev-list", *revs)
            scope["посилань (for-each-ref)"] = _git_count(repo, "for-each-ref")
        if args.mode in ("blobs", "all"):
            scope["об'єктів-файлів"] = scan_blobs(repo, revs, findings)
        if args.logs:
            scope["файлів журналів"] = scan_logs(pathlib.Path(args.logs), findings)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"помилка: {type(exc).__name__}", file=sys.stderr)
        return 2

    known: list = []
    stale: list = []
    if args.update_baseline:
        pathlib.Path(args.baseline).write_text(render_baseline(findings), encoding="utf-8", newline="\n")
    elif args.baseline:
        try:
            baseline = load_baseline(pathlib.Path(args.baseline))
        except (OSError, ValueError, KeyError) as exc:
            print(f"помилка: базова лінія не читається ({type(exc).__name__})", file=sys.stderr)
            return 2
        findings, known, stale = split_by_baseline(findings, baseline)

    report = pathlib.Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    old = os.umask(0o077)
    try:
        report.write_text(render(findings, scope, known, stale), encoding="utf-8", newline="\n")
    finally:
        os.umask(old)

    # У stdout — тільки підсумок за правилами: ні шляхів, ні комітів, ні значень.
    # Журнал прогону Actions публічного репозиторію читає будь-хто.
    for rule, n in sorted(collections.Counter(f.rule for f in findings).items()):
        print(f"{rule}: {n}")
    if known:
        print(f"відомих за базовою лінією: {len(known)}")
    print(f"знахідок: {len(findings)}; подробиці — {report}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
