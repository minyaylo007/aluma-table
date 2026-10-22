#!/usr/bin/env python3
"""Публікація одного поста в @aluma.il через Instagram API (вхід через Instagram, застосунок «ALUMA posts»).

ЧОМУ ЦЕ ІСНУЄ. Пости в Instagram публікуємо самі, за словом власника, без ручного копирування
картинки й підпису в телефон. Картинку Meta забирає сама за публічним https-URL (docs/ig/ на
raw.githubusercontent.com), підпис — з файлу UTF-8.

    python3 scripts/ig_publish.py --image-url https://…/docs/ig/01-tavor.jpg --caption-file docs/ig/01-tavor.txt --dry-run
    python3 scripts/ig_publish.py --image-url https://…/docs/ig/01-tavor.jpg --caption-file docs/ig/01-tavor.txt
    python3 scripts/ig_publish.py --refresh          # ihor-aluma-ig-refresh.timer, раз на ~2 тижні

Кроки Content Publishing API (graph.instagram.com):
    POST /{IG_USER_ID}/media (image_url, caption) → контейнер
    GET  /{container}?fields=status_code,status   → чекати FINISHED; ERROR/EXPIRED → код 1
    POST /{IG_USER_ID}/media_publish (creation_id) → id поста
    GET  /{media_id}?fields=permalink              → друкуємо media_id і permalink

--dry-run перевіряє все локально (підпис ≤ 2200 знаків, ≤ 30 хештегів, URL https на .jpg/.jpeg) і
робить рівно один GET /me — токен живий; нічого не створює.

Токен — з ~/.config/aluma/ig.env (IG_ENV або --env), KEY=VALUE без source. Його НІКОЛИ не друкуємо:
у повідомленнях про помилку тіло відповіді Meta проходить через _redact(), як у api/handler.py.
Код виходу ≠ 0 при будь-якій помилці.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

GRAPH_HOST = "https://graph.instagram.com"
GRAPH_VERSION = "v21.0"
DEFAULT_ENV = pathlib.Path.home() / ".config" / "aluma" / "ig.env"
HTTP_TIMEOUT_SECONDS = 30
POLL_SECONDS = 2.5
CAPTION_MAX = 2200     # межа Instagram на підпис
HASHTAGS_MAX = 30      # межа Instagram на хештеги в одному пості
BODY_CLIP = 500

_TOKEN_IN_TEXT = re.compile(r"(access_token=)[^&\s\"']+")


class IgError(Exception):
    """Відмова з текстом, у якому вже немає токена."""


def _redact(text, secrets=()) -> str:
    """Вирізати токен із тексту: і значення, і будь-який «access_token=…» (URL у тексті винятку)."""
    text = str(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return _TOKEN_IN_TEXT.sub(r"\1[redacted]", text)


def parse_env(path: pathlib.Path) -> dict:
    """KEY=VALUE по рядку; # — коментар; лапки навколо значення знімаються. Без source і без підстановок."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def _http(method: str, url: str, data: bytes | None) -> tuple[int, bytes]:
    """Один HTTP-запит → (статус, тіло). Тести підміняють саме цю функцію."""
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310 — лише https graph.instagram.com
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class Client:
    def __init__(self, user_id: str, token: str, version: str = GRAPH_VERSION):
        self.user_id = user_id
        self.token = token
        self.version = version

    def call(self, method: str, path: str, params: dict | None = None, versioned: bool = True) -> dict:
        """GET — параметри в query, POST — у тілі форми; токен в обох випадках лише через urlencode."""
        params = dict(params or {}, access_token=self.token)
        query = urllib.parse.urlencode(params)
        base = f"{GRAPH_HOST}/{self.version}/{path}" if versioned else f"{GRAPH_HOST}/{path}"
        try:
            if method == "GET":
                status, body = _http("GET", f"{base}?{query}", None)
            else:
                status, body = _http(method, base, query.encode("ascii"))
        except Exception as exc:  # мережа, таймаут: текст винятку може містити URL з токеном
            raise IgError(f"{method} /{path}: {_redact(repr(exc), (self.token,))}") from None
        text = body.decode("utf-8", "replace")
        if status >= 400:
            raise IgError(f"{method} /{path}: HTTP {status}: {_redact(text, (self.token,))[:BODY_CLIP]}")
        try:
            return json.loads(text)
        except ValueError:
            raise IgError(f"{method} /{path}: не JSON: {_redact(text, (self.token,))[:BODY_CLIP]}") from None


def check_caption(text: str) -> None:
    if not text.strip():
        raise IgError("підпис порожній")
    if len(text) > CAPTION_MAX:
        raise IgError(f"підпис {len(text)} знаків > {CAPTION_MAX}")
    tags = re.findall(r"#\w+", text)
    if len(tags) > HASHTAGS_MAX:
        raise IgError(f"хештегів {len(tags)} > {HASHTAGS_MAX}")


def check_image_url(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise IgError("image-url має бути https://…")
    if not parts.path.lower().endswith((".jpg", ".jpeg")):
        raise IgError("image-url має закінчуватися на .jpg або .jpeg (Instagram приймає лише JPEG)")


def read_caption(path: pathlib.Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise IgError(f"підпис не прочитано: {exc}") from None
    return text.strip("\n")


def wait_finished(client: Client, container_id: str, wait: float, sleep=time.sleep, clock=None) -> None:
    clock = clock or time.monotonic
    deadline = clock() + wait
    while True:
        info = client.call("GET", container_id, {"fields": "status_code,status"})
        code = info.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise IgError(f"контейнер {container_id}: {code}: {info.get('status', '')}")
        if clock() >= deadline:
            raise IgError(f"контейнер {container_id}: не FINISHED за {wait:g} с (останній статус {code})")
        sleep(POLL_SECONDS)


def publish(client: Client, image_url: str, caption: str, wait: float, sleep=time.sleep) -> tuple[str, str]:
    container = client.call("POST", f"{client.user_id}/media", {"image_url": image_url, "caption": caption})
    container_id = container.get("id")
    if not container_id:
        raise IgError("POST /media: немає id контейнера")
    wait_finished(client, container_id, wait, sleep=sleep)
    post = client.call("POST", f"{client.user_id}/media_publish", {"creation_id": container_id})
    media_id = post.get("id")
    if not media_id:
        raise IgError("POST /media_publish: немає id поста")
    link = client.call("GET", media_id, {"fields": "permalink"}).get("permalink", "")
    return media_id, link


def write_token(env_path: pathlib.Path, new_token: str) -> None:
    """Замінити IG_ACCESS_TOKEN у файлі атомарно: тимчасовий файл поруч (0600) + os.replace. Решта рядків — як були."""
    lines = env_path.read_text(encoding="utf-8").splitlines()
    out, done = [], False
    for line in lines:
        if line.strip().startswith("IG_ACCESS_TOKEN="):
            out.append(f"IG_ACCESS_TOKEN={new_token}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"IG_ACCESS_TOKEN={new_token}")
    fd, tmp = tempfile.mkstemp(prefix=".ig.env.", dir=str(env_path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, env_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def refresh(client: Client, env_path: pathlib.Path) -> int:
    """Новий 60-денний токен → у файл. Повертає expires_in у днях."""
    data = client.call("GET", "refresh_access_token", {"grant_type": "ig_refresh_token"}, versioned=False)
    new_token = data.get("access_token", "")
    if not new_token or not re.fullmatch(r"[A-Za-z0-9_\-.|]+", new_token):
        raise IgError("refresh_access_token: немає придатного access_token у відповіді")
    write_token(env_path, new_token)
    return int(data.get("expires_in", 0)) // 86400


def main(argv=None, sleep=time.sleep) -> int:
    ap = argparse.ArgumentParser(description="Пост в @aluma.il через Instagram API (див. docstring).")
    ap.add_argument("--env", default=os.environ.get("IG_ENV", str(DEFAULT_ENV)), help="файл з IG_USER_ID і IG_ACCESS_TOKEN")
    ap.add_argument("--image-url")
    ap.add_argument("--caption-file")
    ap.add_argument("--dry-run", action="store_true", help="лише перевірки й один GET /me, нічого не створює")
    ap.add_argument("--wait", type=float, default=60, help="скільки секунд чекати FINISHED (типово 60)")
    ap.add_argument("--refresh", action="store_true", help="оновити токен і записати його назад у --env")
    args = ap.parse_args(argv)

    env_path = pathlib.Path(args.env).expanduser()
    try:
        try:
            env = parse_env(env_path)
        except OSError as exc:
            raise IgError(f"{env_path}: {exc.strerror}") from None
        user_id, token = env.get("IG_USER_ID", ""), env.get("IG_ACCESS_TOKEN", "")
        if not user_id or not token:
            raise IgError(f"{env_path}: немає IG_USER_ID або IG_ACCESS_TOKEN")
        client = Client(user_id, token)

        if args.refresh:
            days = refresh(client, env_path)
            print(json.dumps({"event": "ig_token_refreshed", "expires_in_days": days}))
            return 0

        if not args.image_url or not args.caption_file:
            raise IgError("потрібні --image-url і --caption-file (або --refresh)")
        check_image_url(args.image_url)
        caption = read_caption(pathlib.Path(args.caption_file))
        check_caption(caption)

        if args.dry_run:
            me = client.call("GET", "me", {"fields": "username"})
            tags = len(re.findall(r"#\w+", caption))
            print(f"dry-run ok: @{me.get('username', '?')}, підпис {len(caption)} знаків, "
                  f"хештегів {tags}, нічого не створено")
            return 0

        media_id, link = publish(client, args.image_url, caption, args.wait, sleep=sleep)
        print(f"media_id={media_id}")
        print(f"permalink={link}")
        return 0
    except IgError as exc:
        print(f"ig_publish: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
