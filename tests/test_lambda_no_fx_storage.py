"""Лямбда без FX_STORAGE=dynamodb: що насправді відповідає новий код. Без мережі, без AWS.

Питання. Код master типово бере SQLite (FX_STORAGE="sqlite", FX_DB_PATH="data/aluma.db",
api/handler.py). Якщо його залити в Lambda без змінної з infra/template.yaml, куди подінуться
заявки? Документи казали різне («200 і тиха втрата», «порожня база в /tmp», «500»). Тут це
доведено, а не описано.

Як імітується Lambda, і чому саме так.
  * Модуль handler.py завантажується НАНОВО, окремою копією, з оточенням без FX_STORAGE і
    FX_DB_PATH — отже типові значення беруться з коду, а не підставляються тестом.
  * Робоча папка — тимчасова тека з правами 0555, у неї робиться chdir. У Lambda робоча
    папка /var/task (код пакета) і вона тільки для читання; відносний data/aluma.db там
    розгортається в /var/task/data. Тут так само: справжні os.path.abspath і os.makedirs з
    api/store.py, справжня файлова система відмовляє. Нічого в store.py не підмінено.
  * Єдина різниця з Lambda — номер помилки: там EROFS (read-only файлова система), тут
    EACCES (немає права на запис). Обидва — OSError, і ні store.py, ні handler.py не
    дивляться на errno (перевірено grep: жодного errno/EROFS/EACCES в api/), тож гілка коду
    та сама. Підміна os.makedirs на «кинь EROFS» дала б точний номер, але перевіряла б
    нашу заглушку замість справжньої відмови — тому обрано чесний chdir.
  * Під root права 0555 не заважають писати — тоді тест не доводить нічого і пропускається.

Що доведено (див. тести нижче):
  * POST /api/fx/lead -> 500 {"ok": false, "error": "internal"}, notify() НЕ викликано,
    на диску нічого не створено: SqliteStore падає на os.makedirs ще до sqlite3.connect,
    put_lead ламається на першому ж рядку (_tables()), до put_item і notify не доходить.
  * POST /api/fx/event -> той самий 500 (put_events теж починається з _tables()).
  * GET /api/fx/health -> 200 {"ok": true, ...}: health у сховище не ходить, тож він
    зелений, поки форма лежить. Тому health не доводить, що викат вдався.
  * У журнал іде рядок {"event": "unhandled", ...} — отже помилка видима в CloudWatch.

Тест червоніє, якщо хтось зробить так, що заявка відповідає 200 без запису (запасна база
в пам'яті чи в /tmp, проковтнута помилка) — тоді треба переписати документи, а не тест:
docs/CUTOVER-CHECKLIST.md крок 3, docs/PROD-NOTIFY-DECISION.md §4.4, infra/template.yaml
(коментар над FX_STORAGE), CLAUDE.md §3.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import stat
import sys
import tempfile
import types
import unittest
import uuid
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if importlib.util.find_spec("boto3") is None:
    # handler.py імпортує boto3 безумовно; до DynamoDB тут справа не доходить
    from tests.test_handler import _install_fake_boto3

    _install_fake_boto3()

# Змінні, які не мають просочитися з оболонки розробника: без них модуль бачить
# рівно те оточення, що й лямбда без FX_STORAGE у шаблоні.
_CLEARED = ("FX_STORAGE", "FX_DB_PATH", "EDGE_SECRET", "TELEGRAM_BOT_TOKEN", "OWNER_TELEGRAM_CHAT_ID")


def _fresh_handler():
    """Окрема копія api/handler.py, прочитана з оточенням без FX_STORAGE/FX_DB_PATH."""
    env = {k: v for k, v in os.environ.items() if k not in _CLEARED}
    with mock.patch.dict(os.environ, env, clear=True):
        name = f"_aluma_handler_lambda_{uuid.uuid4().hex[:8]}"
        spec = importlib.util.spec_from_file_location(name, ROOT / "api" / "handler.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


def _request(method: str, path: str, body=None) -> dict:
    """Подія API Gateway payload v2.0 — як у tests/test_handler.py."""
    return {
        "requestContext": {"http": {"method": method, "path": path, "sourceIp": "203.0.113.7"}},
        "headers": {"user-agent": "Mozilla/5.0 (unit test)", "content-type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False) if body is not None else "",
        "isBase64Encoded": False,
    }


LEAD = {
    "name": "Test Lead",
    "phone": "050-123-4567",
    "city": "Tel Aviv",
    "color": "natural",
    "size": "220",
    "lang": "he",
    "comment": "",
    "consent": True,
    "consent_text_version": "v2",
    "session_id": "s-1",
}
EVENTS = {"session_id": "s-1", "events": [{"name": "page_view", "props": {}}], "ctx": {}}
INTERNAL = {"ok": False, "error": "internal"}


class LambdaWithoutFxStorageTests(unittest.TestCase):
    def setUp(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("під root права 0555 не забороняють запис — Lambda не імітується")

        self.h = _fresh_handler()
        # Сповіщення «увімкнені», як у проді: якщо код дійде до notify, ми це побачимо.
        self.h.TELEGRAM_BOT_TOKEN = "123:fake-token-for-test"
        self.h.OWNER_TELEGRAM_CHAT_ID = "1"
        self.notify = mock.patch.object(self.h, "notify", wraps=self.h.notify).start()
        if self.h.requests is not None:  # і все одно жодного запиту в мережу
            self.post = mock.patch.object(
                self.h.requests, "post",
                side_effect=AssertionError("Telegram не мав викликатися"),
            ).start()
        self.addCleanup(mock.patch.stopall)

        # /var/task: тека, в яку не можна писати, і вона — робоча папка процесу.
        tmp = tempfile.TemporaryDirectory(prefix="aluma-var-task-")
        self.addCleanup(tmp.cleanup)
        self.task_root = pathlib.Path(tmp.name)
        old_cwd = os.getcwd()
        os.chdir(self.task_root)
        self.addCleanup(os.chdir, old_cwd)
        os.chmod(self.task_root, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP
                 | stat.S_IROTH | stat.S_IXOTH)  # 0555
        self.addCleanup(os.chmod, self.task_root, stat.S_IRWXU)
        if os.access(self.task_root, os.W_OK):
            self.skipTest("тека 0555 все одно доступна на запис — Lambda не імітується")

    def call(self, method, path, body=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = self.h.lambda_handler(_request(method, path, body), None)
        logs = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        payload = json.loads(r["body"]) if r.get("body") else None
        return r["statusCode"], payload, logs

    def test_defaults_are_what_lambda_would_get(self):
        # Передумова всього файлу: без змінних код іде в SQLite з відносним шляхом.
        self.assertEqual(self.h.FX_STORAGE, "sqlite")
        self.assertEqual(self.h.FX_DB_PATH, "data/aluma.db")
        self.assertFalse(os.path.isabs(self.h.FX_DB_PATH))
        self.assertEqual(
            os.path.dirname(os.path.abspath(self.h.FX_DB_PATH)),
            os.path.join(os.path.realpath(self.task_root), "data"),
        )

    def test_lead_is_500_internal_and_nobody_is_notified(self):
        status, payload, logs = self.call("POST", "/api/fx/lead", LEAD)
        # Якщо тут 200 — заявка «прийнята» без запису в DynamoDB: це і є тиха втрата.
        self.assertEqual(status, 500, payload)
        self.assertEqual(payload, INTERNAL)
        self.notify.assert_not_called()
        # на «read-only» диску нічого не з'явилося: ні data/, ні файлу бази
        self.assertEqual(list(self.task_root.iterdir()), [])
        unhandled = [e for e in logs if e.get("event") == "unhandled"]
        self.assertEqual(len(unhandled), 1, logs)
        self.assertEqual(unhandled[0]["path"], "/api/fx/lead")
        self.assertIn("PermissionError", unhandled[0]["error"])  # EROFS у справжній лямбді

    def test_lead_stays_500_on_every_retry(self):
        # Невдале відкриття не кешується: кожна наступна заявка теж 500, а не «пусто і 200».
        for _ in range(3):
            status, payload, _ = self.call("POST", "/api/fx/lead", LEAD)
            self.assertEqual((status, payload), (500, INTERNAL))
        self.notify.assert_not_called()

    def test_event_is_500_internal(self):
        status, payload, logs = self.call("POST", "/api/fx/event", EVENTS)
        self.assertEqual((status, payload), (500, INTERNAL))
        self.assertEqual([e["path"] for e in logs if e.get("event") == "unhandled"], ["/api/fx/event"])

    def test_health_stays_green_because_it_never_touches_storage(self):
        status, payload, logs = self.call("GET", "/api/fx/health")
        self.assertEqual(status, 200)
        self.assertIs(payload["ok"], True)
        self.assertEqual(logs, [])
        self.assertEqual(list(self.task_root.iterdir()), [])

    def test_same_code_with_fx_storage_dynamodb_does_not_touch_the_disk(self):
        # Контроль: зі змінною з шаблону шлях SQLite не відкривається зовсім.
        # boto3.resource підмінено — до AWS не доходить.
        self.h.FX_STORAGE = "dynamodb"
        self.h._reset_tables()
        tables = [types.SimpleNamespace(name=n) for n in ("e", "l", "s")]
        fake = types.SimpleNamespace(Table=lambda name: tables.pop(0))
        with mock.patch.object(self.h.boto3, "resource", return_value=fake) as res:
            self.h._tables()
        res.assert_called_once_with("dynamodb")
        self.assertEqual(list(self.task_root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
