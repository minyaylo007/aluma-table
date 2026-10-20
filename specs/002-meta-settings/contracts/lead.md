# Контракт: POST /api/fx/lead — новые поля (ночь 20→21.10)

Старые поля (`name`, `phone`, `city`, `color`, `size`, `lang`, `comment`, `consent`, `consent_marketing`,
`consent_text_version`, `session_id`, `utm_*`, `fbclid`, `attributed_at`, `page`, `referrer`, `device`, `website`
— honeypot) и их проверки НЕ меняются. Лимиты 5/час (реальные) и 60/час (`x-test: 1`) — без изменений.

Новые необязательные поля. Неверное значение → записывается `""`, заявку НЕ отклоняет.

| Поле | Формат | Пример |
|---|---|---|
| `product_id` | `[a-z0-9-]{1,40}` (id из `catalog/products.json`) | `extending-table` |
| `size_label` | ≤ 40 символов, буквы/цифры/пробел/`×x-–/.` | `180×90` |
| `finish_id` | `[a-z0-9-]{1,30}` | `natural` |
| `base_id` | `[a-z0-9-]{1,30}` | `steel-black` |
| `timeframe` | `now` \| `1-3m` \| `later` | `1-3m` |
| `contact_pref` | `whatsapp` \| `call` | `whatsapp` |
| `email` | e-mail ≤ 120 | `a@b.co` |
| `event_id` | `[A-Za-z0-9_.-]{8,64}` — тот же, что ушёл в пиксель (`alumaTrack('Lead')`) | `lead.lx3k9a.f81c2d` |
| `fbp` | `fb.1.<ts>.<rand>` ≤ 200 | из cookie `_fbp` |
| `fbc` | `fb.1.<ts>.<fbclid>` ≤ 300 | из cookie `_fbc` |

- `city` уже есть (≤ 80) — остаётся.
- `fbp`/`fbc` можно не передавать: сервер возьмёт cookie `_fbp`/`_fbc` запроса (тот же домен).
- Нет `event_id` — сервер создаёт свой (дедупликации с пикселем тогда не будет, но Lead в CAPI уйдёт).
- Ответ без изменений: `200 {"ok": true, "id": "<id>"}`, `422 {"ok": false, "errors": {...}}`, `429`.

Как форма должна вызывать (сессия 1):

```js
var eventId = window.alumaEventId ? window.alumaEventId("lead") : "";
var data = { /* старые поля */, product_id: "...", size_label: "...", finish_id: "...", base_id: "...",
             timeframe: "1-3m", contact_pref: "whatsapp", event_id: eventId };
// после ответа ok:
if (window.alumaTrack) window.alumaTrack("Lead", { content_ids: [data.product_id], event_id: eventId });
```
