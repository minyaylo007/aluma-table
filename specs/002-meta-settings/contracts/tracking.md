# Контракт: site/assets/tracking.js

Пишет сессия (3). Подключает витрина (сессия 1) одной строкой на каждой странице (he и en), лучше в `<head>`:

```html
<script src="/assets/tracking.js" defer></script>
```

(Если build.py хеширует имена ассетов — подключать через его механизм; файл самодостаточен, без зависимостей.)

## Глобальные функции

| Функция | Что делает |
|---|---|
| `alumaTrack(event, params?)` → `event_id` | Пишет событие в `/api/fx/event` (`props` = params + `event_id`); если пиксель загружен — `fbq('track', event, params, {eventID})`. Стандартные события Meta — `track`, остальные — `trackCustom`. Безопасно вызывать до загрузки конфига: события копятся в очереди. |
| `alumaEventId(prefix?)` → строка | Новый `event_id` (для заявки: создать до отправки формы, передать в `/api/fx/lead` и в `alumaTrack('Lead', {event_id})`). |
| `alumaConsent()` | Посетитель согласился: сохраняет `fx_notice_v1=1`, грузит Pixel/Clarity. Вызывает кнопка «ОК» уведомления, если витрина делает своё. |
| `alumaConfig()` → Promise\<config\> | Конфиг из `/api/fx/config` (контракт `config.md`), один запрос на страницу. |

Событие `document` `aluma:config` (`detail` = конфиг) — когда конфиг получен (витрина показывает контакты/WhatsApp).

## События

`PageView` (tracking.js шлёт сам), `ViewContent` (`{content_ids:[id], content_type:"product", value, currency:"ILS"}`),
`Lead` (после успешной заявки), `Contact` (клик WhatsApp/телефон), `CustomizeProduct` (`{content_ids, size, finish}`).

## Правила

- Нет `pixel_id` — ни одного запроса к доменам Meta. Нет `clarity_id` — к Clarity.
- `?me=1` / cookie `fx_me=1` — ничего не пишем и сторонний код не грузим.
- Сторонний код — только после согласия (`localStorage fx_notice_v1 = "1"`). Если на странице есть `#notice` —
  витрина ведёт его сама и вызывает `alumaConsent()`; если нет — tracking.js показывает свой минимальный блок
  (иврит RTL / английский по `<html lang>`).
- Ошибки сети/конфига — тихо, сайт не ломается.
- Сессия аналитики — тот же `sessionStorage fx_sid`, что и у app-next.js; атрибуция — `localStorage fx_attr`.
