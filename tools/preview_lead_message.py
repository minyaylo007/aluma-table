#!/usr/bin/env python3
"""Як виглядає заявка в Telegram — без мережі, без бази, з вигаданими даними.

    python3 tools/preview_lead_message.py            # заявка з оформлення (кошик), ru
    python3 tools/preview_lead_message.py --form     # заявка з форми, he

Друкує рівно той текст, який notify() надіслав би власнику (api/handler.py lead_message).
Нічого не надсилає: Telegram тут навіть не імпортується в справу. Ім'я й номер — вигадані.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from api import handler  # noqa: E402

FAKE_NAMES = ("Анна Тестова", "דנה בדיקה")   # вигадані
CHECKOUT = {
    "id": "a1b2c3d4e5f6", "ts": "2026-10-23T07:41:12+00:00", "lead_source": "checkout", "lang": "ru",
    "name": FAKE_NAMES[0], "phone": "+97250" + "1234567", "phone_raw": "050-" + "123-4567", "city": "חיפה",
    "timeframe": "now", "contact_pref": "whatsapp", "product_id": "tavor", "size_label": "160×90",
    "finish_id": "natural", "base_id": "oak", "cart": "tavor:160×90:natural:oak:1;saf:120:smoked:steel:2",
    "order_total": 9470, "comment": "", "page": "/ru/checkout/", "utm_source": "fb", "utm_campaign": "launch",
    "consent_marketing": False,
}
FORM = {
    "id": "f6e5d4c3b2a1", "ts": "2026-10-23T08:02:40+00:00", "lead_source": "form", "lang": "he",
    "name": FAKE_NAMES[1], "phone": "+97252" + "1112233", "phone_raw": "052-" + "111-2233", "city": "תל אביב",
    "timeframe": "1-3m", "contact_pref": "call", "product_id": "sahar", "size_label": "Ø115",
    "finish_id": "smoked", "base_id": "steel", "cart": "", "order_total": 0, "comment": "אחרי 18:00",
    "page": "/p/sahar/", "utm_source": "", "utm_campaign": "", "consent_marketing": True,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--form", action="store_true", help="заявка з форми замість оформлення")
    args = ap.parse_args()
    print(handler.lead_message(FORM if args.form else CHECKOUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
