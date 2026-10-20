# Контракт: GET /api/fx/config

Публичный рантайм-конфиг сайта. Пишет сессия (3), читают `site/assets/tracking.js` и витрина (сессия 1).

```
GET /api/fx/config
200 application/json; charset=utf-8
Cache-Control: public, max-age=60
```

```json
{
  "pixel_id": "123456789012345",
  "wa_number": "9725XXXXXXXX",
  "clarity_id": "abc123defg",
  "contact": {
    "name": "ALUMA",
    "phone": "+9725XXXXXXXX",
    "email": "hello@example.com",
    "city": "תל אביב",
    "business_id": null,
    "address": null,
    "court_city": null
  },
  "accessibility_contact": {
    "name": "ALUMA",
    "phone": "+9725XXXXXXXX",
    "email": "hello@example.com"
  },
  "launch_mode": true
}
```

- Любое незаданное значение — `null` (в `contact` — тоже `null` у поля). Ключи присутствуют всегда.
- `wa_number` — только цифры с кодом страны, без `+` — готов для `https://wa.me/<wa_number>`.
- `contact.phone` — `+` и цифры (для `tel:`).
- `contact.business_id` — ח.פ./ע.מ. (9 цифр), пока фирмы нет — `null`; для תקנון и футера.
- `contact.address` — адрес продавца для תקנון (до 120 символов); `null` — витрина скрывает пункт.
- `contact.court_city` — город суда для споров по תקנון (до 120 символов); `null` — пункт скрыт.
- `accessibility_contact` — רכז/ת נגישות для הצהרת נגישות (תקנה 35). Незаданное поле берётся из `contact`.
- `launch_mode` — `true` по умолчанию (настройки ещё не сохранялись).
- НИКОГДА не содержит: токен CAPI, test event code, служебные поля (`updated_by` и т. п.).
- Ошибка чтения настроек → 200 с дефолтами (все `null`, `launch_mode: true`): сайт не должен ломаться.
