"""fx-table API — analytics events, lead capture, admin dashboard.

Two ways to run the same code, chosen by env:
  * Lambda behind CloudFront — FX_STORAGE=dynamodb, entry point lambda_handler;
  * gunicorn on an ordinary server — FX_STORAGE=sqlite (default), entry point
    api/wsgi.py, storage api/store.py.

Dependencies: boto3 (ships with the python3.13 runtime) and requests, which is
needed only to notify the owner on Telegram. See api/requirements.txt.

Routes
    GET  /api/fx/health
    POST /api/fx/event      batched client events (also the sendBeacon target)
    POST /api/fx/lead       lead capture
    GET  /admin             dashboard (signed-cookie auth)
    GET/POST /admin/login   sign in
    POST /admin/status      change a lead's status
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import boto3
from boto3.dynamodb.conditions import Key

try:  # єдина стороння залежність, і лише заради сповіщень у Telegram
    import requests
except ImportError:  # pragma: no cover - notify() тоді просто мовчки не спрацює
    requests = None

try:  # з кореня репозиторію (тести, gunicorn api.wsgi:application)
    from api import store
except ImportError:  # у бандлі лямбди api/ САМЕ і є коренем
    import store

# --------------------------------------------------------------------------- config

EVENTS_TABLE = os.environ.get("EVENTS_TABLE", "fx_events")
LEADS_TABLE = os.environ.get("LEADS_TABLE", "fx_leads")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "fx_sessions")
ADMIN_USER = os.environ.get("ADMIN_USER", "")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")
IP_SALT = os.environ.get("IP_SALT", "")
# Сповіщення про лід ідуть у Telegram. Обидві змінні порожні = сповіщення вимкнені.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OWNER_TELEGRAM_CHAT_ID = os.environ.get("OWNER_TELEGRAM_CHAT_ID", "")
TELEGRAM_TIMEOUT_SECONDS = 5
SITE_DOMAIN = os.environ.get("SITE_DOMAIN", "table.central-aparts.store")
EDGE_SECRET = os.environ.get("EDGE_SECRET", "")
APP_VERSION = os.environ.get("APP_VERSION", "0.0.0")
# Повний git sha версії (RELEASE.env юніта на машині); немає або порожній — None (Lambda, локально).
GIT_SHA = os.environ.get("GIT_SHA") or None

# "sqlite" — типово: свій сервер, файл на диску. Будь-що інше — DynamoDB.
FX_STORAGE = os.environ.get("FX_STORAGE", "sqlite").strip().lower()
FX_DB_PATH = os.environ.get("FX_DB_PATH", "data/aluma.db")

EVENT_TTL_DAYS = 180
SESSION_TTL_DAYS = 400
MAX_EVENTS_PER_REQUEST = 40
MAX_PROPS_BYTES = 2000
LEADS_PER_IP_PER_HOUR = 5
LEADS_PER_IP_PER_HOUR_TEST = 60   # the smoke suite must not eat a real visitor's quota
EVENTS_PER_IP_PER_MINUTE = 120

VALID_STATUSES = ("new", "called", "interested", "not_interested", "deposit", "spam")
VALID_COLORS = ("natural", "smoked", "white")
VALID_SIZES = ("160", "220")      # cm; the client sends the string as-is
VALID_LANGS = ("he", "en")        # <html lang> of the page the lead came from

BOT_UA = re.compile(
    r"bot|crawler|spider|crawling|facebookexternalhit|slurp|bingpreview|"
    r"headlesschrome|phantomjs|python-requests|curl/|wget|lighthouse|"
    r"pingdom|uptimerobot|semrush|ahrefs|petalbot|gptbot|claudebot",
    re.I,
)

_ddb = None
_sqlite_tables = None


def _tables():
    """Єдиний шов між хендлером і сховищем.

    FX_STORAGE=sqlite (типово) — локальний файл через api/store.py.
    Будь-що інше — DynamoDB, щоб та сама лямбда працювала без змін, поки DNS
    ще дивиться на CloudFront. Лямбда вмикає це через FX_STORAGE=dynamodb
    в infra/template.yaml.
    """
    global _ddb, _sqlite_tables
    if FX_STORAGE == "sqlite":
        if _sqlite_tables is None:
            _sqlite_tables = store.tables(FX_DB_PATH, EVENTS_TABLE, LEADS_TABLE, SESSIONS_TABLE)
        return _sqlite_tables
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    return (
        _ddb.Table(EVENTS_TABLE),
        _ddb.Table(LEADS_TABLE),
        _ddb.Table(SESSIONS_TABLE),
    )


def _reset_tables():
    """Скинути кеш сховища — потрібно тестам, які міняють FX_STORAGE/FX_DB_PATH."""
    global _ddb, _sqlite_tables
    _ddb = None
    _sqlite_tables = None


# --------------------------------------------------------------------------- helpers


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def day_key(d: str) -> str:
    return f"D#{d}"


def resp(status: int, body, headers=None, is_json=True):
    h = {"cache-control": "no-store"}
    if is_json:
        h["content-type"] = "application/json; charset=utf-8"
        payload = json.dumps(body, ensure_ascii=False)
    else:
        h["content-type"] = "text/html; charset=utf-8"
        payload = body
    if headers:
        h.update(headers)
    return {"statusCode": status, "headers": h, "body": payload}


def client_ip(event) -> str:
    h = event.get("headers") or {}
    xff = h.get("x-forwarded-for") or ""
    if xff:
        return xff.split(",")[0].strip()
    return (event.get("requestContext", {}).get("http", {}) or {}).get("sourceIp", "")


def hash_ip(ip: str) -> str:
    if not ip:
        return ""
    return hashlib.sha256((IP_SALT + "|" + ip).encode("utf-8")).hexdigest()[:32]


def cookies_of(event) -> dict:
    out = {}
    for c in event.get("cookies") or []:
        if "=" in c:
            k, _, v = c.partition("=")
            out[k.strip()] = v.strip()
    raw = (event.get("headers") or {}).get("cookie") or ""
    for part in raw.split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


def is_excluded(event) -> tuple[bool, str]:
    """Owner traffic and bots must not pollute a 20-lead dataset."""
    ua = (event.get("headers") or {}).get("user-agent", "") or ""
    if BOT_UA.search(ua):
        return True, "bot_ua"
    if not ua:
        return True, "no_ua"
    if cookies_of(event).get("fx_me") == "1":
        return True, "self"
    return False, ""


def body_of(event) -> dict:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8", "replace")
        except Exception:
            return {}
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def form_of(event) -> dict:
    """Parse an application/x-www-form-urlencoded body (admin forms only)."""
    from urllib.parse import parse_qs

    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8", "replace")
        except Exception:
            return {}
    return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}


def clip(value, limit: int) -> str:
    if value is None:
        return ""
    s = str(value)
    return s[:limit]


def rate_ok(sessions, bucket: str, limit: int, window_seconds: int) -> bool:
    """Counter with TTL in the sessions table. Fails open — a broken counter
    must never stop a real lead from being recorded."""
    try:
        r = sessions.update_item(
            Key={"session_id": bucket},
            UpdateExpression="ADD #n :one SET #t = if_not_exists(#t, :ttl)",
            ExpressionAttributeNames={"#n": "n", "#t": "ttl"},
            ExpressionAttributeValues={
                ":one": 1,
                ":ttl": int(time.time()) + window_seconds + 60,
            },
            ReturnValues="UPDATED_NEW",
        )
        return int(r["Attributes"]["n"]) <= limit
    except Exception:
        return True


# --------------------------------------------------------------------------- phone


PHONE_MAX_DIGITS = 15  # ITU E.164 ceiling; anything longer is garbage, not a typo

# National significant number (what follows +972). Exactly one of:
#   5\d{8}      mobile      05x-xxx-xxxx
#   [23489]\d{7} landline   02/03/04/08/09-xxx-xxxx
#   7[2-9]\d{7} VoIP/07x    072..079-xxx-xxxx
PHONE_NATIONAL = re.compile(r"5[0-9]{8}|[23489][0-9]{7}|7[2-9][0-9]{7}")


def normalize_phone(raw: str) -> tuple[str, bool]:
    """Canonical Israeli phone rule, shared 1:1 with the client (app-next.js phoneOk).

    Returns ``(e164, plausible)``. The lead is accepted only when ``plausible``
    is True; ``e164`` is then ``"+972" + national`` and is what gets stored.

    Algorithm (order matters — mirror it exactly in JavaScript):
      1. Keep ASCII digits ``0-9`` only. Spaces, dashes, dots, parentheses, a
         leading ``+``, RTL/LTR marks all vanish. Non-ASCII digits are NOT
         converted (out of scope) — they are dropped like any other character.
      2. Empty -> ``("", False)``. More than 15 digits -> ``("+"+digits, False)``.
      3. Strip ONE leading international prefix ``00``.
      4. If it now starts with ``972``: drop it, then strip ALL leading zeros of
         the remainder (people type ``+972-050-…``).
         Else if it starts with ``0``: drop that single zero.
         Else: not an Israeli number -> ``("+"+digits, False)``.
      5. The remainder must fully match ``5\\d{8}`` (mobile) or ``[23489]\\d{7}``
         (landline) or ``7[2-9]\\d{7}`` (07x). Anything else -> not plausible.
      6. Output ``"+972" + remainder``.

    Accepted-format table (input -> normalized -> plausible):
        050-123-4567        -> +972501234567   True
        0501234567          -> +972501234567   True
        +972 50-123-4567    -> +972501234567   True
        972501234567        -> +972501234567   True
        00972501234567      -> +972501234567   True
        +972-050-1234567    -> +972501234567   True   (zero after country code)
        03-1234567          -> +97231234567    True   (landline)
        072-1234567         -> +972721234567   True   (07x)
        12345               -> +12345          False  (no 0/972 prefix)
        +1 212 555 0100     -> +12125550100    False  (foreign)
        05012345678         -> +9725012345678  False  (too long)
        501234567           -> +501234567      False  (no leading zero)
        ""                  -> ""              False
    """
    digits = re.sub(r"[^0-9]", "", str(raw or ""))
    if not digits:
        return "", False
    if len(digits) > PHONE_MAX_DIGITS:
        return "+" + digits, False
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("972"):
        national = digits[3:].lstrip("0")
    elif digits.startswith("0"):
        national = digits[1:]
    else:
        return "+" + digits, False
    return "+972" + national, PHONE_NATIONAL.fullmatch(national) is not None


# --------------------------------------------------------------------------- events


def put_events(event):
    events_t, _, sessions_t = _tables()
    excluded, why = is_excluded(event)
    if excluded:
        return resp(202, {"ok": True, "skipped": why})

    data = body_of(event)
    items = data.get("events") or []
    if not isinstance(items, list):
        return resp(400, {"ok": False, "error": "events must be a list"})
    items = items[:MAX_EVENTS_PER_REQUEST]

    ip = client_ip(event)
    iph = hash_ip(ip)
    minute = int(time.time() // 60)
    if not rate_ok(sessions_t, f"RLE#{iph}#{minute}", EVENTS_PER_IP_PER_MINUTE, 60):
        return resp(429, {"ok": False, "error": "rate"})

    session_id = clip(data.get("session_id"), 64) or "anon"
    ctx = data.get("ctx") or {}
    ts_now = now_iso()
    ttl = int(time.time()) + EVENT_TTL_DAYS * 86400
    is_test = (event.get("headers") or {}).get("x-test") == "1"

    written = 0
    with events_t.batch_writer() as batch:
        for e in items:
            if not isinstance(e, dict):
                continue
            name = clip(e.get("name"), 60)
            if not name:
                continue
            props = e.get("props") or {}
            props_json = json.dumps(props, ensure_ascii=False)[:MAX_PROPS_BYTES]
            batch.put_item(
                Item={
                    "pk": day_key(today()),
                    "sk": f"{ts_now}#{uuid.uuid4().hex[:10]}",
                    "session_id": session_id,
                    "ts": clip(e.get("ts"), 40) or ts_now,
                    "event_name": name,
                    "props_json": props_json,
                    "page": clip(e.get("page") or ctx.get("page"), 300),
                    "referrer": clip(ctx.get("referrer"), 300),
                    "utm_source": clip(ctx.get("utm_source"), 100),
                    "utm_medium": clip(ctx.get("utm_medium"), 100),
                    "utm_campaign": clip(ctx.get("utm_campaign"), 120),
                    "utm_content": clip(ctx.get("utm_content"), 120),
                    "utm_term": clip(ctx.get("utm_term"), 120),
                    "fbclid": clip(ctx.get("fbclid"), 200),
                    # when the UTM set above arrived, so a stored campaign is never a mix of visits
                    "attributed_at": clip(ctx.get("attributed_at"), 40),
                    "device": clip(ctx.get("device"), 20),
                    "viewport": clip(ctx.get("viewport"), 20),
                    "lang": clip(ctx.get("lang"), 20),
                    "ip_hash": iph,
                    "user_agent": clip((event.get("headers") or {}).get("user-agent"), 300),
                    "is_test": is_test,
                    "ttl": ttl,
                }
            )
            written += 1

    if session_id != "anon":
        touch_session(sessions_t, session_id, ctx, event, iph, is_test)

    return resp(200, {"ok": True, "written": written})


def touch_session(sessions_t, session_id, ctx, event, iph, is_test):
    h = event.get("headers") or {}
    try:
        sessions_t.update_item(
            Key={"session_id": session_id},
            UpdateExpression=(
                "SET first_seen = if_not_exists(first_seen, :now), last_seen = :now, "
                "landing_url = if_not_exists(landing_url, :landing), "
                "utm_source = if_not_exists(utm_source, :us), "
                "utm_medium = if_not_exists(utm_medium, :um), "
                "utm_campaign = if_not_exists(utm_campaign, :uc), "
                "utm_content = if_not_exists(utm_content, :uct), "
                "utm_term = if_not_exists(utm_term, :ut), "
                "device = :dev, country = :country, ip_hash = :iph, "
                "is_test = :test, #t = :ttl"
            ),
            ExpressionAttributeNames={"#t": "ttl"},
            ExpressionAttributeValues={
                ":now": now_iso(),
                ":landing": clip(ctx.get("landing_url") or ctx.get("page"), 300),
                ":us": clip(ctx.get("utm_source"), 100),
                ":um": clip(ctx.get("utm_medium"), 100),
                ":uc": clip(ctx.get("utm_campaign"), 120),
                ":uct": clip(ctx.get("utm_content"), 120),
                ":ut": clip(ctx.get("utm_term"), 120),
                ":dev": clip(ctx.get("device"), 20),
                ":country": clip(h.get("cloudfront-viewer-country"), 4),
                ":iph": iph,
                ":test": is_test,
                ":ttl": int(time.time()) + SESSION_TTL_DAYS * 86400,
            },
        )
    except Exception:
        pass


# --------------------------------------------------------------------------- leads


def put_lead(event):
    _, leads_t, sessions_t = _tables()
    data = body_of(event)

    # Honeypot: a real human never fills a field that is hidden from humans.
    if clip(data.get("website"), 200).strip():
        return resp(200, {"ok": True, "id": "hp"})

    is_test = (event.get("headers") or {}).get("x-test") == "1"
    ip = client_ip(event)
    iph = hash_ip(ip)
    hour = int(time.time() // 3600)
    # Test traffic gets its own counter: a smoke run must never lock out a real
    # visitor from the same office IP, and a bot that sets X-Test only reaches
    # rows that are already excluded from every funnel.
    bucket = f"RLL#{'T' if is_test else 'R'}#{iph}#{hour}"
    cap = LEADS_PER_IP_PER_HOUR_TEST if is_test else LEADS_PER_IP_PER_HOUR
    if not rate_ok(sessions_t, bucket, cap, 3600):
        return resp(429, {"ok": False, "error": "rate", "field": "form"})

    name = clip(data.get("name"), 80).strip()
    phone_raw = clip(data.get("phone"), 40).strip()
    city = clip(data.get("city"), 80).strip()
    color = clip(data.get("color"), 20).strip()
    size = clip(data.get("size"), 8).strip()
    lang = clip(data.get("lang"), 8).strip()
    comment = clip(data.get("comment"), 1000).strip()
    consent = bool(data.get("consent"))

    errors = {}
    if len(name) < 2:
        errors["name"] = "required"
    phone, plausible = normalize_phone(phone_raw)
    if not plausible:
        errors["phone"] = "invalid"
    if not consent:
        errors["consent"] = "required"
    # Configuration fields are never a reason to refuse a lead — an unknown
    # value is simply recorded as "" so the report cannot be polluted.
    if color and color not in VALID_COLORS:
        color = ""
    if size not in VALID_SIZES:
        size = ""
    if lang not in VALID_LANGS:
        lang = ""
    if errors:
        return resp(422, {"ok": False, "errors": errors})

    lead_id = uuid.uuid4().hex[:12]
    ts = now_iso()
    item = {
        "pk": "LEAD",
        "sk": f"{ts}#{lead_id}",
        "id": lead_id,
        "ts": ts,
        "name": name,
        "phone": phone,
        "phone_raw": phone_raw,
        "city": city,
        "color": color,
        "size": size,
        "lang": lang,
        "comment": comment,
        "consent": consent,
        "consent_marketing": bool(data.get("consent_marketing")),
        "consent_text_version": clip(data.get("consent_text_version"), 20) or "v1",
        "session_id": clip(data.get("session_id"), 64),
        "utm_source": clip(data.get("utm_source"), 100),
        "utm_medium": clip(data.get("utm_medium"), 100),
        "utm_campaign": clip(data.get("utm_campaign"), 120),
        "utm_content": clip(data.get("utm_content"), 120),
        "utm_term": clip(data.get("utm_term"), 120),
        "fbclid": clip(data.get("fbclid"), 200),
        "attributed_at": clip(data.get("attributed_at"), 40),
        "page": clip(data.get("page"), 300),
        "referrer": clip(data.get("referrer"), 300),
        "device": clip(data.get("device"), 20),
        "ip_hash": iph,
        "status": "new",
        "is_test": is_test,
    }
    leads_t.put_item(Item=item)

    if not is_test:
        notify(item)

    return resp(200, {"ok": True, "id": lead_id})


def notify(item):
    """Сповіщення власнику в Telegram. Було SES — мінус один сервіс Amazon.

    Best effort і нічого більше: лід уже в базі, і жодна помилка тут не має
    права його втратити. Але й мовчати не можна — про невдачу пишемо в stdout,
    звідки її забирає journald (і journal_watch, коли він з'явиться).
    """
    if not (TELEGRAM_BOT_TOKEN and OWNER_TELEGRAM_CHAT_ID):
        return
    text = (
        f"ליד חדש — {SITE_DOMAIN}\n\n"
        f"Name:    {item['name']}\n"
        f"Phone:   {item['phone']}\n"
        f"City:    {item['city']}\n"
        f"Colour:  {item['color']}\n"
        f"Size:    {item.get('size', '')}\n"
        f"Lang:    {item.get('lang', '')}\n"
        f"Page:    {item.get('page', '')}\n"
        f"Comment: {item['comment']}\n\n"
        f"consent_marketing={'yes' if item.get('consent_marketing') else 'no'}\n"
        f"utm_source={item['utm_source']} utm_campaign={item['utm_campaign']}\n"
        f"time={item['ts']}  id={item['id']}\n"
    )
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": OWNER_TELEGRAM_CHAT_ID,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=TELEGRAM_TIMEOUT_SECONDS,
        )
        if r.status_code >= 400:
            print(json.dumps({"event": "notify_failed", "id": item.get("id"),
                              "status": r.status_code, "body": clip(_redact(r.text), 300)}))
    except Exception as exc:
        print(json.dumps({"event": "notify_failed", "id": item.get("id"), "error": _redact(repr(exc))}))


def _redact(text: str) -> str:
    """Прибрати токен бота з тексту, що йде в журнал.

    Токен живе в URL запиту (.../bot<token>/sendMessage), а requests кладе цей URL
    у текст винятку ("Max retries exceeded with url: /bot<token>/..."). Журнал
    лямбди в CloudWatch зберігається безстроково — токену там не місце.
    Спершу вирізаємо, потім обрізаємо: clip() міг би розрізати токен навпіл.
    """
    text = str(text)
    if TELEGRAM_BOT_TOKEN:
        for form in (TELEGRAM_BOT_TOKEN, quote(TELEGRAM_BOT_TOKEN, safe="")):
            text = text.replace(form, "<token>")
    return text


# --------------------------------------------------------------------------- admin


# CloudFront's Origin Access Control signs every origin request with SigV4 and
# owns the Authorization header, so HTTP Basic cannot survive the hop. The admin
# uses a short-lived signed cookie instead.

SESSION_HOURS = 12


def _session_secret() -> bytes:
    return (ADMIN_PASS + "|" + IP_SALT + "|fx-admin").encode("utf-8")


def make_token() -> str:
    exp = str(int(time.time()) + SESSION_HOURS * 3600)
    sig = hmac.new(_session_secret(), exp.encode(), hashlib.sha256).hexdigest()
    return exp + "." + sig


def token_valid(token: str) -> bool:
    if not token or "." not in token:
        return False
    exp, _, sig = token.partition(".")
    expected = hmac.new(_session_secret(), exp.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        return int(exp) > time.time()
    except ValueError:
        return False


def check_auth(event) -> bool:
    if not ADMIN_USER or not ADMIN_PASS:
        return False
    return token_valid(cookies_of(event).get("fx_adm", ""))


def need_auth():
    return {
        "statusCode": 303,
        "headers": {"location": "/admin/login", "cache-control": "no-store"},
        "body": "",
    }


LOGIN_PAGE = """<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>כניסה · fx-table</title>
<style>
 body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#12100e;color:#f0ece6;
   font:15px/1.6 system-ui,-apple-system,"Segoe UI",Arial,sans-serif}}
 form{{background:#1c1916;border:1px solid #2e2924;border-radius:12px;padding:26px;width:min(92vw,22rem)}}
 h1{{font-size:17px;margin:0 0 18px}}
 label{{display:block;margin-bottom:12px}}
 span{{display:block;font-size:13px;color:#9a9088;margin-bottom:5px}}
 input{{width:100%;box-sizing:border-box;padding:11px;font:inherit;background:#241f1a;color:#f0ece6;
   border:1px solid #2e2924;border-radius:7px}}
 button{{width:100%;padding:12px;margin-top:8px;font:inherit;font-weight:600;cursor:pointer;
   background:#c98b34;color:#12100e;border:0;border-radius:7px}}
 p.e{{color:#e08a7a;font-size:13px;margin:0 0 12px}}
</style></head><body>
<form method="post" action="/admin/login">
  <h1>fx-table · כניסה</h1>
  {err}
  <label><span>משתמש</span><input name="user" autocomplete="username" autofocus></label>
  <label><span>סיסמה</span><input name="pass" type="password" autocomplete="current-password"></label>
  <button type="submit">כניסה</button>
</form></body></html>"""


def admin_login(event):
    method = ((event.get("requestContext") or {}).get("http") or {}).get("method", "GET").upper()
    if method != "POST":
        return resp(200, LOGIN_PAGE.format(err=""), is_json=False)

    form = form_of(event)
    ok = (
        ADMIN_USER
        and ADMIN_PASS
        and hmac.compare_digest(form.get("user", ""), ADMIN_USER)
        and hmac.compare_digest(form.get("pass", ""), ADMIN_PASS)
    )
    if not ok:
        # Slow down credential stuffing without holding the request open long.
        time.sleep(0.6)
        return resp(401, LOGIN_PAGE.format(err='<p class="e">משתמש או סיסמה לא נכונים.</p>'), is_json=False)

    return {
        "statusCode": 303,
        "headers": {"location": "/admin", "cache-control": "no-store"},
        "cookies": [
            f"fx_adm={make_token()}; Path=/admin; Max-Age={SESSION_HOURS * 3600}; "
            "HttpOnly; Secure; SameSite=Lax"
        ],
        "body": "",
    }


def admin_logout(event):
    return {
        "statusCode": 303,
        "headers": {"location": "/admin/login", "cache-control": "no-store"},
        "cookies": ["fx_adm=; Path=/admin; Max-Age=0; HttpOnly; Secure; SameSite=Lax"],
        "body": "",
    }


def scan_events(days: int):
    events_t, _, _ = _tables()
    out = []
    start = datetime.now(timezone.utc).date()
    span = days if days > 0 else 120
    for i in range(span):
        d = (start - timedelta(days=i)).strftime("%Y-%m-%d")
        last = None
        while True:
            kwargs = {"KeyConditionExpression": Key("pk").eq(day_key(d)), "Limit": 1000}
            if last:
                kwargs["ExclusiveStartKey"] = last
            try:
                r = events_t.query(**kwargs)
            except Exception:
                break
            out.extend(r.get("Items", []))
            last = r.get("LastEvaluatedKey")
            if not last or len(out) > 60000:
                break
        if len(out) > 60000:
            break
    return out


def load_leads():
    _, leads_t, _ = _tables()
    out, last = [], None
    while True:
        kwargs = {
            "KeyConditionExpression": Key("pk").eq("LEAD"),
            "ScanIndexForward": False,
            "Limit": 500,
        }
        if last:
            kwargs["ExclusiveStartKey"] = last
        r = leads_t.query(**kwargs)
        out.extend(r.get("Items", []))
        last = r.get("LastEvaluatedKey")
        if not last or len(out) >= 2000:
            break
    return out


def esc(s) -> str:
    return (
        str(s if s is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def admin_page(event):
    if not check_auth(event):
        return need_auth()

    qs = event.get("queryStringParameters") or {}
    rng = qs.get("range", "7")
    days = {"1": 1, "7": 7, "all": 0}.get(rng, 7)
    show_test = qs.get("test") == "1"
    # Тег релізу вже з «v» (v0.5.0) — без подвійної «vv»; старі номери (0.4.0-box) — з префіксом, як було.
    version_label = APP_VERSION if APP_VERSION.startswith("v") else "v" + APP_VERSION

    events = scan_events(days)
    leads = load_leads()
    if not show_test:
        events = [e for e in events if not e.get("is_test")]
        leads = [l for l in leads if not l.get("is_test")]

    if days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        leads_in_range = [l for l in leads if l.get("ts", "") >= cutoff]
    else:
        leads_in_range = leads

    def sessions_with(pred):
        return {e.get("session_id") for e in events if pred(e) and e.get("session_id")}

    def props(e):
        try:
            return json.loads(e.get("props_json") or "{}")
        except Exception:
            return {}

    visits = sessions_with(lambda e: e.get("event_name") == "page_view")
    price_seen = sessions_with(
        lambda e: e.get("event_name") == "section_view" and props(e).get("section") in ("hero", "price")
    )
    interacted = sessions_with(
        lambda e: e.get("event_name") in ("color_select", "size_toggle", "room_fit_check", "viewer_open")
    )
    # viewer_open belongs to the 3D viewer, which no longer ships. Historical rows still count in
    # "interacted" above; the funnel no longer shows a step that can only ever read zero.
    viewer = sessions_with(lambda e: e.get("event_name") == "viewer_open")
    form_started = sessions_with(lambda e: e.get("event_name") == "form_start")
    lead_ok = sessions_with(lambda e: e.get("event_name") == "lead_success")
    wa = sessions_with(lambda e: e.get("event_name") in ("whatsapp_click", "hero_cta_whatsapp", "sticky_whatsapp"))

    def pct(a, b):
        return f"{(100.0 * a / b):.0f}%" if b else "—"

    n_visits = len(visits)
    funnel = [
        ("ביקורים", n_visits, "100%"),
        ("ראו מחיר", len(price_seen), pct(len(price_seen), n_visits)),
        ("שיחקו בצבע/גודל", len(interacted), pct(len(interacted), n_visits)),
    ] + ([("פתחו תלת־ממד (היסטורי)", len(viewer), pct(len(viewer), n_visits))] if viewer else []) + [
        ("התחילו טופס", len(form_started), pct(len(form_started), n_visits)),
        ("השאירו פרטים", len(lead_ok), pct(len(lead_ok), n_visits)),
        ("לחצו וואטסאפ", len(wa), pct(len(wa), n_visits)),
    ]

    def tally(key_fn, filter_fn=lambda e: True):
        d = {}
        for e in events:
            if not filter_fn(e):
                continue
            k = key_fn(e)
            if k:
                d[k] = d.get(k, 0) + 1
        return sorted(d.items(), key=lambda kv: -kv[1])

    by_utm = tally(lambda e: f"{e.get('utm_source') or 'direct'} / {e.get('utm_campaign') or '—'}",
                   lambda e: e.get("event_name") == "page_view")
    by_device = tally(lambda e: e.get("device"), lambda e: e.get("event_name") == "page_view")
    by_color = tally(lambda e: props(e).get("color"), lambda e: e.get("event_name") == "color_select")
    by_faq = tally(lambda e: props(e).get("q"), lambda e: e.get("event_name") == "faq_open")
    by_size = tally(lambda e: str(props(e).get("size")), lambda e: e.get("event_name") == "size_toggle")

    fits = [props(e) for e in events if e.get("event_name") == "room_fit_check"]
    fit_rows = tally(
        lambda e: f"{props(e).get('room_length')} ס\"מ → {props(e).get('result')}",
        lambda e: e.get("event_name") == "room_fit_check",
    )

    def rows(pairs, limit=12):
        if not pairs:
            return '<tr><td colspan="2" class="muted">אין נתונים</td></tr>'
        return "".join(
            f"<tr><td>{esc(k)}</td><td class='n'>{v}</td></tr>" for k, v in pairs[:limit]
        )

    lead_rows = []
    for l in leads_in_range[:300]:
        opts = "".join(
            f"<option value='{s}'{' selected' if l.get('status') == s else ''}>{s}</option>"
            for s in VALID_STATUSES
        )
        lead_rows.append(
            "<tr>"
            f"<td class='mono'>{esc((l.get('ts') or '')[:16].replace('T',' '))}</td>"
            f"<td>{esc(l.get('name'))}</td>"
            f"<td class='mono' dir='ltr'><a href='tel:{esc(l.get('phone'))}'>{esc(l.get('phone'))}</a></td>"
            f"<td>{esc(l.get('city'))}</td>"
            f"<td>{esc(l.get('color'))}</td>"
            f"<td>{esc(l.get('comment'))[:120]}</td>"
            f"<td class='mono'>{esc(l.get('utm_source') or 'direct')}</td>"
            "<td><form method='post' action='/admin/status'>"
            f"<input type='hidden' name='sk' value='{esc(l.get('sk'))}'>"
            f"<input type='hidden' name='range' value='{esc(rng)}'>"
            f"<select name='status'>{opts}</select>"
            "<button type='submit'>שמור</button></form></td>"
            "</tr>"
        )
    if not lead_rows:
        lead_rows.append("<tr><td colspan='8' class='muted'>אין לידים בטווח הזה</td></tr>")

    status_counts = {}
    for l in leads:
        status_counts[l.get("status", "new")] = status_counts.get(l.get("status", "new"), 0) + 1

    funnel_html = "".join(
        f"<div class='step'><div class='bar' style='width:{(100.0*n/n_visits) if n_visits else 0:.0f}%'></div>"
        f"<span class='lbl'>{esc(label)}</span><span class='val'>{n} <em>{p}</em></span></div>"
        for label, n, p in funnel
    )

    html = f"""<!doctype html>
<html lang="he" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>fx-table · אדמין</title>
<style>
 :root{{--bg:#12100e;--card:#1c1916;--line:#2e2924;--ink:#f0ece6;--mut:#9a9088;--acc:#c98b34}}
 *{{box-sizing:border-box}}
 body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Arial,sans-serif}}
 header{{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}}
 h1{{font-size:18px;margin:0}} h2{{font-size:15px;margin:0 0 10px;color:var(--mut);font-weight:600}}
 a{{color:var(--acc)}} .muted,.mono em{{color:var(--mut)}}
 nav a{{margin-inline-start:12px;text-decoration:none}} nav a.on{{color:var(--ink);font-weight:700;text-decoration:underline}}
 main{{padding:20px;display:grid;gap:18px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}}
 .card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}}
 .wide{{grid-column:1/-1}}
 table{{width:100%;border-collapse:collapse;font-size:13px}}
 th,td{{text-align:start;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
 td.n{{text-align:end;font-variant-numeric:tabular-nums;width:60px}}
 .mono{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px}}
 .step{{position:relative;padding:9px 12px;margin-bottom:6px;border-radius:8px;background:#232019;overflow:hidden}}
 .bar{{position:absolute;inset-block:0;inset-inline-start:0;background:rgba(201,139,52,.28)}}
 .step .lbl,.step .val{{position:relative}} .step .val{{float:left;font-variant-numeric:tabular-nums}}
 .step .val em{{font-style:normal;color:var(--mut);margin-inline-start:6px}}
 select,button{{background:#241f1a;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:3px 6px;font:inherit;font-size:12px}}
 button{{cursor:pointer;margin-inline-start:4px}}
 form{{display:flex;gap:2px}}
</style></head><body>
<header>
  <h1>fx-table · לוח בקרה</h1>
  <nav>
    <a href="?range=1" class="{'on' if rng=='1' else ''}">היום</a>
    <a href="?range=7" class="{'on' if rng=='7' else ''}">7 ימים</a>
    <a href="?range=all" class="{'on' if rng=='all' else ''}">הכול</a>
    <a href="?range={esc(rng)}&amp;test={'0' if show_test else '1'}">{'הסתר בדיקות' if show_test else 'הצג בדיקות'}</a>
    <a href="/admin/logout">יציאה</a>
  </nav>
  <span class="muted mono">{esc(version_label)} · {esc(len(events))} events · {esc(len(leads))} leads</span>
</header>
<main>
  <section class="card wide"><h2>משפך</h2>{funnel_html}</section>

  <section class="card"><h2>מקורות תנועה</h2><table>{rows(by_utm)}</table></section>
  <section class="card"><h2>מכשירים</h2><table>{rows(by_device)}</table></section>
  <section class="card"><h2>צבעים שנבחרו</h2><table>{rows(by_color)}</table></section>
  <section class="card"><h2>גודל שנבחר</h2><table>{rows(by_size)}</table></section>
  <section class="card"><h2>שאלות נפוצות שנפתחו</h2><table>{rows(by_faq)}</table></section>
  <section class="card"><h2>בדיקת "ייכנס אצלי?" ({len(fits)})</h2><table>{rows(fit_rows)}</table></section>
  <section class="card"><h2>סטטוס לידים</h2><table>{rows(sorted(status_counts.items(), key=lambda kv:-kv[1]))}</table></section>

  <section class="card wide"><h2>לידים ({len(leads_in_range)})</h2>
    <table><thead><tr><th>מתי</th><th>שם</th><th>טלפון</th><th>עיר</th><th>צבע</th><th>הערה</th><th>מקור</th><th>סטטוס</th></tr></thead>
    <tbody>{''.join(lead_rows)}</tbody></table>
  </section>
</main></body></html>"""
    return resp(200, html, is_json=False)


def admin_status(event):
    if not check_auth(event):
        return need_auth()
    form = form_of(event)
    sk = form.get("sk", "")
    status = form.get("status", "")
    rng = form.get("range", "7")
    if not sk or status not in VALID_STATUSES:
        return resp(400, {"ok": False, "error": "bad input"})
    _, leads_t, _ = _tables()
    leads_t.update_item(
        Key={"pk": "LEAD", "sk": sk},
        UpdateExpression="SET #s = :s, status_changed_at = :t",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status, ":t": now_iso()},
    )
    return {
        "statusCode": 303,
        "headers": {"location": f"/admin?range={rng}", "cache-control": "no-store"},
        "body": "",
    }


# --------------------------------------------------------------------------- router


def lambda_handler(event, context):
    http = (event.get("requestContext") or {}).get("http") or {}
    method = (http.get("method") or "GET").upper()
    path = (http.get("path") or "/").rstrip("/") or "/"

    if method == "OPTIONS":
        return resp(204, "", is_json=False)

    # The execute-api hostname is public. Only CloudFront knows the shared secret,
    # so a caller who skips the CDN also skips nothing useful.
    if EDGE_SECRET:
        sent = (event.get("headers") or {}).get("x-fx-edge", "")
        if not hmac.compare_digest(sent, EDGE_SECRET):
            return resp(403, {"ok": False, "error": "forbidden"})

    try:
        if path == "/api/fx/health":
            return resp(200, {"ok": True, "version": APP_VERSION, "git_sha": GIT_SHA, "ts": now_iso()})
        if path == "/api/fx/event" and method == "POST":
            return put_events(event)
        if path == "/api/fx/lead" and method == "POST":
            return put_lead(event)
        if path == "/admin/login":
            return admin_login(event)
        if path == "/admin/logout":
            return admin_logout(event)
        if path == "/admin" and method == "GET":
            return admin_page(event)
        if path == "/admin/status" and method == "POST":
            return admin_status(event)
    except Exception as exc:  # never leak a stack trace to the public internet
        print(json.dumps({"event": "unhandled", "path": path, "error": repr(exc)}))
        return resp(500, {"ok": False, "error": "internal"})

    return resp(404, {"ok": False, "error": "not found"})
