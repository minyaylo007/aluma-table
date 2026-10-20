"""Налаштування власника, публічний конфіг сайту і Meta Conversions API — чиста логіка.

Тут немає ні мережі, ні сховища: перевірка полів форми, публічний конфіг із запису
налаштувань, нормалізація й хеші для CAPI, складання події Lead і HTML сторінки
/admin/settings. Ввід-вивід (база, requests, маршрути) — у handler.py, щоб у Lambda
і під gunicorn усе поводилося однаково. Специфікація — specs/002-meta-settings/.

Токен CAPI — секрет: жодна функція звідси не вставляє його в HTML чи публічний JSON.
"""

from __future__ import annotations

import hashlib
import re
import time

# --------------------------------------------------------------------------- поля

# Порядок = порядок на сторінці. public — потрапляє в GET /api/fx/config (через public_config).
FIELDS = (
    "contact_name", "contact_phone", "contact_email", "contact_city", "business_id", "address", "court_city",
    "a11y_name", "a11y_phone", "a11y_email",
    "wa_number", "pixel_id", "capi_token", "test_event_code", "clarity_id", "launch_mode",
)
SECRET_FIELDS = ("capi_token",)

DEFAULTS = {name: "" for name in FIELDS}
DEFAULTS["launch_mode"] = True

_DIGITS = re.compile(r"[^0-9]")
_PHONE_CHARS = re.compile(r"^[0-9+\s().\-]*$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
_PIXEL = re.compile(r"^[0-9]{10,20}$")
_TOKEN = re.compile(r"^\S{20,400}$")
_TEST_CODE = re.compile(r"^[A-Za-z0-9]{3,40}$")
_CLARITY = re.compile(r"^[a-z0-9]{6,20}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_BUSINESS_ID = re.compile(r"^[0-9]{9}$")


def _text(value, limit: int) -> str:
    return _CONTROL.sub("", str(value or "")).strip()[:limit]


def _international(raw: str, normalize_phone):
    """Номер у міжнародному форматі → цифри з кодом країни або None.

    Ізраїльський місцевий запис (050-…) приймаємо через normalize_phone з handler.py —
    власник може вставити номер так, як звик. Інакше: 8–15 цифр, перша не 0
    (код країни), «00» на початку — міжнародний префікс.
    """
    raw = str(raw or "").strip()
    if not raw or not _PHONE_CHARS.match(raw):
        return None
    e164, plausible = normalize_phone(raw)
    if plausible:
        return e164[1:]
    digits = _DIGITS.sub("", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    elif not raw.startswith("+"):
        return None  # без «+» і не ізраїльський — не знаємо коду країни
    if 8 <= len(digits) <= 15 and not digits.startswith("0"):
        return digits
    return None


def parse_form(form: dict, current: dict, normalize_phone):
    """Форма /admin/settings → (нові налаштування, помилки {поле: текст по-російськи}).

    Порожнє поле токена = «не міняти»; capi_token_clear=1 — стерти. Помилка хоч в одному
    полі — handler не зберігає нічого (FR-003).
    """
    new = {name: current.get(name, DEFAULTS[name]) for name in FIELDS}
    errors = {}

    new["contact_name"] = _text(form.get("contact_name"), 80)
    new["contact_city"] = _text(form.get("contact_city"), 60)

    def phone_field(name):
        phone = _text(form.get(name), 40)
        if not phone:
            new[name] = ""
            return
        digits = _international(phone, normalize_phone)
        if digits is None:
            errors[name] = "Телефон в международном формате: +972 5X XXX XXXX или 05X-XXX-XXXX."
        new[name] = "+" + digits if digits else phone

    def email_field(name):
        email = _text(form.get(name), 120).lower()
        if email and not _EMAIL.match(email):
            errors[name] = "Неверный e-mail."
        new[name] = email

    phone_field("contact_phone")
    email_field("contact_email")

    business = _DIGITS.sub("", _text(form.get("business_id"), 20))
    if business and not _BUSINESS_ID.match(business):
        errors["business_id"] = "ח.פ. / ע.מ. — 9 цифр."
    new["business_id"] = business

    # Адреса продавця й місто суду для תקנון — довільний текст, але не довший за 120 знаків.
    for name in ("address", "court_city"):
        value = _CONTROL.sub("", str(form.get(name) or "")).strip()
        if len(value) > 120:
            errors[name] = "Не длиннее 120 символов."
        new[name] = value[:120]

    new["a11y_name"] = _text(form.get("a11y_name"), 80)
    phone_field("a11y_phone")
    email_field("a11y_email")

    wa = _text(form.get("wa_number"), 40)
    if wa:
        digits = _international(wa, normalize_phone)
        if digits is None:
            errors["wa_number"] = "Номер WhatsApp в международном формате: +972 5X XXX XXXX (8–15 цифр с кодом страны)."
        new["wa_number"] = digits or wa
    else:
        new["wa_number"] = ""

    pixel = re.sub(r"\s", "", _text(form.get("pixel_id"), 40))
    if pixel and not _PIXEL.match(pixel):
        errors["pixel_id"] = "Pixel ID — только цифры, обычно 15–16."
    new["pixel_id"] = pixel

    code = _text(form.get("test_event_code"), 60)
    if code and not _TEST_CODE.match(code):
        errors["test_event_code"] = "Код теста — латинские буквы и цифры, например TEST12345."
    new["test_event_code"] = code

    clarity = _text(form.get("clarity_id"), 40).lower()
    if clarity and not _CLARITY.match(clarity):
        errors["clarity_id"] = "Clarity ID — 6–20 латинских букв и цифр."
    new["clarity_id"] = clarity

    new["launch_mode"] = str(form.get("launch_mode", "")).lower() in ("1", "on", "true", "yes")

    token = str(form.get("capi_token") or "").strip()
    if str(form.get("capi_token_clear", "")) in ("1", "on"):
        new["capi_token"] = ""
    elif token:
        if not _TOKEN.match(token):
            errors["capi_token"] = "Токен — одна строка без пробелов, обычно 150–250 символов."
        else:
            new["capi_token"] = token
    return new, errors


def changes(old: dict, new: dict):
    """[(поле, "set"|"cleared")] — для журналу, без значень."""
    out = []
    for name in FIELDS:
        before, after = old.get(name, DEFAULTS[name]), new.get(name, DEFAULTS[name])
        if before == after:
            continue
        if name == "launch_mode":
            out.append((name, "on" if after else "off"))
        else:
            out.append((name, "set" if after else "cleared"))
    return out


def public_config(settings: dict) -> dict:
    """Контракт specs/002-meta-settings/contracts/config.md. Лише публічні поля."""
    def v(name):
        value = settings.get(name)
        return value if value else None

    launch = settings.get("launch_mode")
    return {
        "pixel_id": v("pixel_id"),
        "wa_number": v("wa_number"),
        "clarity_id": v("clarity_id"),
        "contact": {
            "name": v("contact_name"),
            "phone": v("contact_phone"),
            "email": v("contact_email"),
            "city": v("contact_city"),
            "business_id": v("business_id"),
            "address": v("address"),
            "court_city": v("court_city"),
        },
        # רכז/ת נגישות для הצהרת נגישות; порожнє поле — береться загальний контакт
        "accessibility_contact": {
            "name": v("a11y_name") or v("contact_name"),
            "phone": v("a11y_phone") or v("contact_phone"),
            "email": v("a11y_email") or v("contact_email"),
        },
        "launch_mode": True if launch is None else bool(launch),
    }


# --------------------------------------------------------------------------- CAPI


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _norm_name(value: str) -> str:
    """Правило Meta для fn/ln/ct: нижній регістр, без пробілів і пунктуації, UTF-8."""
    return re.sub(r"[\W_]+", "", str(value or "").lower())


def user_data(phone_e164="", email="", name="", city="", fbp="", fbc="", ip="", ua="") -> dict:
    """user_data для CAPI. Телефон: лише цифри з кодом країни (без «+» і нулів спереду);
    e-mail: нижній регістр без пробілів; країна — «il». Все особисте — лише SHA-256."""
    out = {"country": [sha256("il")]}
    digits = _DIGITS.sub("", phone_e164 or "").lstrip("0")
    if digits:
        out["ph"] = [sha256(digits)]
    mail = str(email or "").strip().lower()
    if mail:
        out["em"] = [sha256(mail)]
    words = [w for w in (_norm_name(p) for p in str(name or "").split()) if w]
    if words:
        out["fn"] = [sha256(words[0])]
        if len(words) > 1:
            out["ln"] = [sha256(words[-1])]
    ct = _norm_name(city)
    if ct:
        out["ct"] = [sha256(ct)]
    if fbp:
        out["fbp"] = fbp
    if fbc:
        out["fbc"] = fbc
    if ip:
        out["client_ip_address"] = ip
    if ua:
        out["client_user_agent"] = ua
    return out


def source_url(page: str, domain: str) -> str:
    page = str(page or "")
    if page.startswith("https://") or page.startswith("http://"):
        return page[:500]
    return f"https://{domain}{page if page.startswith('/') else '/' + page}"[:500]


def lead_event(item: dict, user: dict, domain: str, now: float | None = None) -> dict:
    """Подія Lead для CAPI. event_id той самий, що в пікселі браузера, — Meta склеює дві в одну."""
    custom = {"currency": "ILS"}
    if item.get("product_id"):
        custom["content_ids"] = [item["product_id"]]
        custom["content_type"] = "product"
    for key in ("size_label", "finish_id", "base_id", "timeframe"):
        if item.get(key):
            custom[key] = item[key]
    return {
        "event_name": "Lead",
        "event_time": int(now if now is not None else time.time()),
        "event_id": item.get("event_id") or "",
        "action_source": "website",
        "event_source_url": source_url(item.get("page"), domain),
        "user_data": user,
        "custom_data": custom,
    }


def test_event(domain: str, now: float | None = None) -> dict:
    """Подія для кнопки «Проверить». Без жодних даних людей — лише країна і синтетичний UA."""
    ts = int(now if now is not None else time.time())
    return {
        "event_name": "PageView",
        "event_time": ts,
        "event_id": f"settings-check-{ts}",
        "action_source": "website",
        "event_source_url": f"https://{domain}/",
        "user_data": {"country": [sha256("il")], "client_ip_address": "203.0.113.1",
                      "client_user_agent": "aluma-settings-check"},
    }


# --------------------------------------------------------------------------- сторінка /admin/settings


def esc(s) -> str:
    return (
        str(s if s is not None else "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&#39;")
    )


# (ключ, підпис, тип, підказка). Підказки — для власника, по-російськи (FR-006).
FORM = (
    ("Контакты на сайте", "Показываются в футере сайта. Пустое поле — этот пункт на сайте скрыт.", (
        ("contact_name", "Имя для сайта / футера", "text", "Например: ALUMA · Игорь."),
        ("contact_phone", "Телефон", "tel", "Международный формат: +972 5X XXX XXXX (05X-XXX-XXXX тоже можно)."),
        ("contact_email", "E-mail", "email", ""),
        ("contact_city", "Город", "text", "Например: תל אביב."),
        ("business_id", "ח.פ. / ע.מ. (когда будет)", "text",
         "9 цифр. Пока фирмы нет — оставьте пустым; появится в תקנון и в футере само."),
        ("address", "Адрес продавца", "text",
         "Для תקנון, на иврите, до 120 символов. Например: רחוב הרצל 1, תל אביב. Пусто — пункт в תקנון скрыт."),
        ("court_city", "Город суда (для תקנון)", "text",
         "Суд, к которому относятся споры по תקנון, на иврите. Например: תל אביב-יפו. Пусто — пункт скрыт."),
    )),
    ("Доступность — רכז/ת נגישות", "Обязателен по закону (תקנה 35): контакт для обращений по доступности, "
     "показывается на странице הצהרת נגישות. Пустые поля — берутся контакты сайта выше.", (
        ("a11y_name", "Имя רכז/ת נגישות", "text", "Обычно сам владелец. Например: Игорь Миняйло."),
        ("a11y_phone", "Телефон", "tel", "Международный формат: +972 5X XXX XXXX."),
        ("a11y_email", "E-mail", "email", "Ответ на обращение — по закону в разумный срок; держите ящик живым."),
    )),
    ("WhatsApp", "", (
        ("wa_number", "Номер WhatsApp", "tel",
         "Номер, на котором стоит WhatsApp Business (в приложении: Настройки → Инструменты для бизнеса → "
         "Профиль). Международный формат: +972 5X XXX XXXX. Сайт делает из него кнопку wa.me."),
    )),
    ("Meta (Facebook / Instagram)", "", (
        ("pixel_id", "Meta Pixel ID", "text",
         "business.facebook.com → Events Manager → Источники данных → ваш пиксель (набор данных) → "
         "Настройки: число из 15–16 цифр. Пикселя нет — «Подключить источник данных» → «Веб» → имя ALUMA → "
         "сайт table.central-aparts.store → «вручную». Код на сайт ставить не надо — сайт поставит сам."),
        ("capi_token", "Conversions API — маркер доступа (токен)", "secret",
         "Events Manager → ваш пиксель → Настройки → блок Conversions API → «Сгенерировать маркер доступа» "
         "(Generate access token). Копируйте сразу: Meta показывает его один раз. Здесь после сохранения он "
         "не показывается — только «задан»; заменить — вставить новый, стереть — флажок."),
        ("test_event_code", "Test event code (необязательно)", "text",
         "Events Manager → пиксель → «Тестирование событий» (Test events): код вида TEST12345. Нужен только "
         "кнопке «Проверить» ниже — настоящие заявки уходят без него, иначе Meta не засчитает их в рекламу."),
    )),
    ("Microsoft Clarity (необязательно)", "", (
        ("clarity_id", "Clarity Project ID", "text",
         "clarity.microsoft.com → проект → Settings → Overview → Project ID (около 10 знаков). "
         "Бесплатно: записи визитов и тепловые карты."),
    )),
    ("Режим", "", (
        ("launch_mode", "Режим предзапуска", "checkbox",
         "Вкл. — сайт работает как лист ожидания («הרשמה מוקדמת»), денег и заказов не принимаем. "
         "Выключать, только когда фабрика подтвердит цены и сроки."),
    )),
)

FIELD_LABELS = {key: label for _, _, fields in FORM for key, label, _, _ in fields}

STYLE = """
 :root{--bg:#12100e;--card:#1c1916;--line:#2e2924;--ink:#f0ece6;--mut:#9a9088;--acc:#c98b34;--ok:#7fbf7f;--bad:#e08a7a}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Arial,sans-serif}
 header{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
 h1{font-size:18px;margin:0} h2{font-size:15px;margin:0 0 10px;color:var(--mut);font-weight:600}
 a{color:var(--acc)} .muted{color:var(--mut)}
 main{padding:20px;max-width:880px;margin:0 auto;display:grid;gap:18px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
 label{display:block;margin:12px 0 4px;font-weight:600}
 input[type=text],input[type=tel],input[type=email],input[type=password]{width:100%;padding:10px;font:inherit;
   background:#241f1a;color:var(--ink);border:1px solid var(--line);border-radius:7px}
 .hint{font-size:13px;color:var(--mut);margin:4px 0 0}
 .err{font-size:13px;color:var(--bad);margin:4px 0 0}
 .has-err input{border-color:var(--bad)}
 button{padding:10px 18px;font:inherit;font-weight:600;cursor:pointer;background:var(--acc);color:#12100e;border:0;border-radius:7px}
 button.ghost{background:#241f1a;color:var(--ink);border:1px solid var(--line)}
 ul.check{list-style:none;padding:0;margin:0} ul.check li{padding:4px 0}
 .y{color:var(--ok);font-weight:700} .n{color:var(--bad);font-weight:700}
 .flash{padding:10px 14px;border-radius:8px;background:#22301f;border:1px solid #3a5a35}
 .flash.bad{background:#3a201c;border-color:#6a3a32}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{text-align:start;padding:6px 8px;border-bottom:1px solid var(--line)}
 .mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px}
 .secret{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
"""


def _mark(ok: bool) -> str:
    return '<span class="y">✓</span>' if ok else '<span class="n">✗</span>'


def checklist(settings: dict, last: dict) -> list:
    """[(пункт, ok, деталь)] — FR-008. last: page_view, lead_event, lead_at, capi {ts, ok, status, source}."""
    contacts_ok = bool(settings.get("contact_name") and (settings.get("contact_phone") or settings.get("contact_email")))
    a11y_ok = bool((settings.get("a11y_name") or settings.get("contact_name"))
                   and (settings.get("a11y_phone") or settings.get("a11y_email")
                        or settings.get("contact_phone") or settings.get("contact_email")))
    capi = last.get("capi") or {}
    if capi.get("ts"):
        capi_detail = f"{capi['ts'][:16].replace('T', ' ')} UTC — {'ок' if capi.get('ok') else 'ошибка'}" \
                      f" (HTTP {capi.get('status') or '—'}, {'проверка' if capi.get('source') == 'test' else 'заявка'})"
    else:
        capi_detail = "ещё не было"

    def when(ts):
        return f"{ts[:16].replace('T', ' ')} UTC" if ts else "ещё не было"

    return [
        ("Meta Pixel ID", bool(settings.get("pixel_id")), "задан" if settings.get("pixel_id") else "не задан"),
        ("Токен Conversions API", bool(settings.get("capi_token")), "задан" if settings.get("capi_token") else "не задан"),
        ("WhatsApp", bool(settings.get("wa_number")), "задан" if settings.get("wa_number") else "не задан"),
        ("Контакты (имя + телефон или e-mail)", contacts_ok, "заполнены" if contacts_ok else "не заполнены"),
        ("Контакт רכז/ת נגישות", a11y_ok, "заполнен" if a11y_ok else "не заполнен (נגישות — обязателен)"),
        ("Последний PageView на сайте", bool(last.get("page_view")), when(last.get("page_view"))),
        ("Последнее событие Lead на сайте", bool(last.get("lead_event")), when(last.get("lead_event"))),
        ("Последняя заявка (не тестовая)", bool(last.get("lead_at")), when(last.get("lead_at"))),
        ("Последняя отправка в Conversions API", bool(capi.get("ok")), capi_detail),
    ]


def render_settings(settings: dict, *, errors=None, form=None, flash="", flash_bad=False,
                    last=None, audit=(), version="") -> str:
    """HTML сторінки. settings — збережені; form — введене (при помилці). Токен не виводиться НІКОЛИ."""
    errors = errors or {}
    shown = dict(settings)
    if form is not None:
        shown.update({k: v for k, v in form.items() if k in FIELDS and k not in SECRET_FIELDS})
    token_set = bool(settings.get("capi_token"))

    sections = []
    for title, intro, fields in FORM:
        parts = [f"<section class='card'><h2>{esc(title)}</h2>"]
        if intro:
            parts.append(f"<p class='hint'>{esc(intro)}</p>")
        for key, label, kind, hint in fields:
            err = errors.get(key)
            cls = " class='has-err'" if err else ""
            parts.append(f"<div{cls}>")
            if kind == "checkbox":
                checked = " checked" if (shown.get(key) in (True, "on", "1", "true")) else ""
                parts.append(f"<label><input type='checkbox' name='{key}' value='on'{checked}> {esc(label)}</label>")
            elif kind == "secret":
                state = "<span class='y'>задан</span>" if token_set else "<span class='n'>не задан</span>"
                parts.append(f"<label for='f-{key}'>{esc(label)} — {state}</label>")
                placeholder = "вставьте новый, чтобы заменить" if token_set else "вставьте токен"
                parts.append(f"<input type='password' id='f-{key}' name='{key}' autocomplete='off' "
                             f"spellcheck='false' placeholder='{esc(placeholder)}' value=''>")
                if token_set:
                    parts.append(f"<label class='muted'><input type='checkbox' name='{key}_clear' value='1'> "
                                 "стереть токен</label>")
            else:
                parts.append(f"<label for='f-{key}'>{esc(label)}</label>")
                parts.append(f"<input type='{kind}' id='f-{key}' name='{key}' value='{esc(shown.get(key, ''))}' "
                             "autocomplete='off' dir='auto'>")
            if hint:
                parts.append(f"<p class='hint'>{esc(hint)}</p>")
            if err:
                parts.append(f"<p class='err'>{esc(err)}</p>")
            parts.append("</div>")
        parts.append("</section>")
        sections.append("".join(parts))

    check_rows = "".join(
        f"<li>{_mark(ok)} {esc(item)} — <span class='muted'>{esc(detail)}</span></li>"
        for item, ok, detail in checklist(settings, last or {})
    )
    audit_rows = "".join(
        f"<tr><td class='mono'>{esc((a.get('ts') or '')[:19].replace('T', ' '))}</td><td>{esc(a.get('who'))}</td>"
        f"<td>{esc(FIELD_LABELS.get(a.get('field'), a.get('field')))}</td><td>{esc(a.get('action'))}</td></tr>"
        for a in audit
    ) or "<tr><td colspan='4' class='muted'>изменений ещё не было</td></tr>"
    flash_html = f"<div class='flash{' bad' if flash_bad else ''}'>{esc(flash)}</div>" if flash else ""

    return f"""<!doctype html>
<html lang="ru" dir="ltr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>ALUMA · настройки</title>
<style>{STYLE}</style></head><body>
<header>
  <h1>ALUMA · настройки</h1>
  <nav><a href="/admin">← заявки и аналитика</a> · <a href="/admin/logout">выйти</a></nav>
  <span class="muted mono">{esc(version)}</span>
</header>
<main>
  {flash_html}
  <section class="card"><h2>Готовность к тесту</h2><ul class="check">{check_rows}</ul>
    <p class="hint">Сайт подхватывает изменения сам, в течение минуты — пересобирать ничего не нужно.</p></section>
  <form method="post" action="/admin/settings" autocomplete="off">
    {''.join(sections)}
    <p><button type="submit">Сохранить</button></p>
  </form>
  <section class="card"><h2>Проверка связи с Meta</h2>
    <p class="hint">Отправляет в Conversions API одно тестовое событие (без данных людей). Если задан test event
    code — событие видно в Events Manager → «Тестирование событий». Нужны Pixel ID и токен.</p>
    <form method="post" action="/admin/settings/test"><button class="ghost" type="submit">Проверить</button></form>
  </section>
  <section class="card"><h2>Журнал изменений (последние 20, без значений)</h2>
    <table><thead><tr><th>когда (UTC)</th><th>кто</th><th>поле</th><th>действие</th></tr></thead>
    <tbody>{audit_rows}</tbody></table></section>
</main></body></html>"""
