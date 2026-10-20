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
  "wa_number": "972501234567",
  "clarity_id": "abc123defg",
  "contact": {"name": "ALUMA", "phone": "+972501234567", "email": "hello@example.com", "city": "תל אביב"},
  "launch_mode": true
}
```

- Любое незаданное значение — `null` (в `contact` — тоже `null` у поля). Ключи присутствуют всегда.
- `wa_number` — только цифры с кодом страны, без `+` — готов для `https://wa.me/<wa_number>`.
- `contact.phone` — `+` и цифры (для `tel:`).
- `launch_mode` — `true` по умолчанию (настройки ещё не сохранялись).
- НИКОГДА не содержит: токен CAPI, test event code, служебные поля (`updated_by` и т. п.).
- Ошибка чтения настроек → 200 с дефолтами (все `null`, `launch_mode: true`): сайт не должен ломаться.
