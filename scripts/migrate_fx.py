#!/usr/bin/env python3
"""Переїзд трьох таблиць ALUMA з DynamoDB у SQLite (задача 1.3) — трьома фазами.

    python3 scripts/migrate_fx.py --phase dump      # знімок DynamoDB → dump/*.jsonl
    python3 scripts/migrate_fx.py --phase load      # dump/*.jsonl → SQLite через api/store.py
    python3 scripts/migrate_fx.py --phase verify    # база проти ЗНІМКА, а не проти DynamoDB
    python3 scripts/migrate_fx.py --phase verify --second-pass   # фінальний прохід у вікні

Три речі, заради яких скрипт написаний саме так, а не інакше.

1. Пише не «таблиця в таблицю», а ЧЕРЕЗ api/store.py — store.tables() і ті самі
   put_item()/batch_writer(), якими користується api/handler.py. Сенс вправи —
   перевірити прошарок SQLite (ADR-1), а не вміння скопіювати байти. Свого
   sqlite3.connect() для запису тут немає й бути не повинно.

2. verify звіряється зі ЗНІМКОМ (dump/manifest.json + самі JSONL), а не з новим
   scan. У fx_events і fx_sessions увімкнено TTL: DynamoDB тихо прибирає
   прострочене, тож повторний scan через годину дасть інші числа й verify
   «зачервоніє» на рівному місці. Джерело істини — момент знімка.

   Той самий TTL псує й ДРУГИЙ прохід переносу. Фінальний знімок знімається
   пізніше першого, і рядки, які перший прохід уже залив у SQLite, з DynamoDB
   за цей час зникають: у базі їх законно БІЛЬШЕ, ніж у знімку. Для цього
   випадку є --second-pass: знімок вважається ПІДМНОЖИНОЮ бази, а не рівним
   їй. Типово прапорця немає й рівність лишається строгою — послаблена
   перевірка не має вмикатися випадково на першому проході. Подробиці —
   relaxed_for_ttl() нижче й docs/CUTOVER-CHECKLIST.md, крок 7.5.

3. Ідемпотентність не обіцяна в докстрінгу, а забезпечена: dump пише через
   тимчасовий файл і rename, load спирається на INSERT OR REPLACE у store._write.
   Кожну фазу можна ганяти двічі поспіль — результат той самий.

У дампі персональні дані заявок. У консоль ідуть лічильники й вердикти, вміст
рядків — ніколи. Тека dump/ і база data/ у .gitignore; у git їде лише скрипт.

Прод не чіпається: єдина операція в AWS — читання (scan).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from api import store  # noqa: E402  — після sys.path, інакше не імпортується

DEFAULT_REGION = "eu-central-1"
MANIFEST = "manifest.json"

# Імена таблиць читаємо тими самими змінними, що й handler.py, — щоб знімок,
# база й хендлер не роз'їхалися, якщо колись з'явиться другий стенд.
TABLES = (
    (os.environ.get("EVENTS_TABLE", "fx_events"), ("pk", "sk")),
    (os.environ.get("LEADS_TABLE", "fx_leads"), ("pk", "sk")),
    (os.environ.get("SESSIONS_TABLE", "fx_sessions"), ("session_id",)),
)

EVENTS_TABLE, LEADS_TABLE, SESSIONS_TABLE = (name for name, _ in TABLES)
# Дві таблиці з увімкненим TTL — і рівно їм дозволено послаблення на другому проході.
TTL_TABLES = frozenset({EVENTS_TABLE, SESSIONS_TABLE})


def relaxed_for_ttl(name: str, second_pass: bool) -> bool:
    """Чи дозволено цій таблиці мати в базі БІЛЬШЕ рядків, ніж у знімку.

    Так — лише для fx_events і fx_sessions (там увімкнено TTL) і лише коли
    явно передано --second-pass. Без прапорця відповідь завжди «ні»: на
    першому проході база й знімок мусять збігатися рівно, і послаблена
    перевірка не має вмикатися сама.

    fx_leads сюди НЕ входить: у заявок немає TTL, тож «TTL прибрав» для них не
    пояснення. На другому проході в них своє правило — classify_extra_leads():
    ЖОДНОЇ пропажі (кожна заявка знімка є в базі з тим самим вмістом), а зайві
    заявки в базі законні лише двох родів — тестові (is_test) і ті, що прийшли
    на коробку ПІСЛЯ знімка (ts пізніший за taken_at). Решта — червоне.

    Чому пропажа заявки завжди справжня: в api/handler.py і api/store.py немає
    жодного шляху видалення заявки — ні delete_item, ні DELETE, ні ручки в
    адмінці; єдиний DELETE, purge_expired(), рубає лише рядки з ttl, якого в
    заявок немає. МЕЖА: щойно видалення заявки зʼявиться, це правило треба
    переглядати РАЗОМ з тією правкою — інакше його виявлять червоним verify у
    день переїзду.
    """
    return second_pass and name in TTL_TABLES


def _parse_ts(value) -> datetime | None:
    """ISO-час заявки/знімка → aware datetime; непридатне → None (тоді «не пояснено»)."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def classify_extra_leads(docs, taken_at: str) -> tuple[int, int, int, set]:
    """Зайві заявки бази (їх немає у знімку) → (тестові, після знімка, непояснені, id пояснених).

    Друга половина правила другого проходу для fx_leads (перша — «жодної
    пропажі» — перевіряється окремо). Звідки законно беруться зайві:
      * тестові — smoke_local.py пише заявку з x-test у живу базу коробки;
      * після знімка — справжня заявка, що прийшла на коробку після 7.1, у
        фінальному знімку DynamoDB її бути не може.
    Нетестова заявка з ts ДО знімка мала б бути в DynamoDB, а її там нема —
    це не пояснено нічим, тому червоне. Вміст — не друкується, лише лічильники.
    """
    snap = _parse_ts(taken_at)
    tests = after = unexplained = 0
    explained_ids = set()
    for doc in docs:
        if doc.get("is_test") is True:
            tests += 1
        else:
            ts = _parse_ts(doc.get("ts"))
            if not (ts and snap and ts > snap):
                unexplained += 1
                continue
            after += 1
        explained_ids.add(doc.get("id"))
    return tests, after, unexplained, explained_ids


def restrict_umask() -> None:
    """umask не ширший за 027: знімок і база — з персональними даними, «іншим» нуль.

    Правило машини (~/maestro/leads/_rules.md, «Общие ресурсы»): на машині чужі
    користувачі (caddy, bots). Строгіший umask, якщо вже стоїть, лишається —
    біти лише додаються. Без цього типовий 0002 дав би JSONL і базу 0664.
    """
    os.umask(os.umask(0o027) | 0o027)


def region_of(explicit: str | None) -> str:
    return (
        explicit
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or DEFAULT_REGION
    )


def key_of(item: dict, key_schema) -> tuple[str, str]:
    """(hk, rk) рівно так, як їх рахує store.SqliteTable._key_of.

    Для fx_sessions ключа сортування немає — rk порожній рядок, і в базі теж.
    """
    hk = str(item[key_schema[0]])
    rk = str(item[key_schema[1]]) if len(key_schema) > 1 else ""
    return hk, rk


def checksum(keys) -> str:
    """Контрольна сума по ВІДСОРТОВАНИХ (hk, rk): ловить не тільки «скільки», а й «що саме»."""
    digest = hashlib.sha256()
    for hk, rk in sorted(keys):
        digest.update(hk.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(rk.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def read_jsonl(path: str):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


# --------------------------------------------------------------------------- dump


def scan_all(table, name: str):
    """Посторінковий scan: ліміт відповіді в 1 МБ ріже видачу, один виклик усе не віддасть."""
    items, last, pages = [], None, 0
    while True:
        kwargs = {"ExclusiveStartKey": last} if last else {}
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        pages += 1
        last = response.get("LastEvaluatedKey")
        if not last:
            break
    print(f"  {name}: {len(items)} рядків за {pages} сторінок")
    return items


def phase_dump(args) -> int:
    import boto3

    region = region_of(args.region)
    os.makedirs(args.dump_dir, exist_ok=True)
    resource = boto3.resource("dynamodb", region_name=region)
    taken_at = datetime.now(timezone.utc).isoformat()

    print(f"dump: регіон {region}, тека {args.dump_dir}")
    manifest = {"taken_at": taken_at, "region": region, "tables": {}}
    total = 0
    for name, key_schema in TABLES:
        items = scan_all(resource.Table(name), name)
        path = os.path.join(args.dump_dir, f"{name}.jsonl")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for item in items:
                # default=store._plain: Decimal → int/float. bool json пише сам,
                # тож is_test лишається справжнім true/false, а не рядком "True".
                fh.write(json.dumps(item, ensure_ascii=False, default=store._plain))
                fh.write("\n")
        os.replace(tmp, path)  # атомарно: перерваний dump не лишає півфайлу
        manifest["tables"][name] = {
            "file": os.path.basename(path),
            "key_schema": list(key_schema),
            "count": len(items),
            "checksum": checksum(key_of(i, key_schema) for i in items),
        }
        total += len(items)

    manifest["total"] = total
    manifest_path = os.path.join(args.dump_dir, MANIFEST)
    tmp = manifest_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, manifest_path)
    print(f"dump: усього {total} рядків, знімок {taken_at}, мітка в {manifest_path}")
    return 0


def load_manifest(dump_dir: str) -> dict:
    path = os.path.join(dump_dir, MANIFEST)
    if not os.path.exists(path):
        raise SystemExit(f"немає {path} — спершу --phase dump")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- load


def phase_load(args) -> int:
    manifest = load_manifest(args.dump_dir)
    os.makedirs(os.path.dirname(os.path.abspath(args.db)) or ".", exist_ok=True)
    # Ті самі три таблиці й у тому ж порядку, що бачить handler._tables().
    handles = store.tables(args.db, *(name for name, _ in TABLES))

    print(f"load: база {args.db}, знімок від {manifest['taken_at']}")
    total, mismatched = 0, 0
    for (name, _key_schema), table in zip(TABLES, handles):
        path = os.path.join(args.dump_dir, manifest["tables"][name]["file"])
        written = 0
        # batch_writer() — рівно те, чим пише handler.put_events().
        # Дедуплікації тут немає свідомо: store._write робить INSERT OR REPLACE,
        # тож повторний прогін просто перезаписує ті самі рядки.
        with table.batch_writer() as batch:
            for item in read_jsonl(path):
                batch.put_item(Item=item)
                written += 1
        expected = manifest["tables"][name]["count"]
        print(f"  {name}: записано {written} з {expected} у знімку")
        # Обрізаний JSONL — єдине, що load здатен помітити сам; краще ненульовий
        # код одразу, ніж «успішний» прогін і червоний verify через хвилину.
        mismatched += 0 if written == expected else 1
        total += written
    print(f"load: усього записано {total} рядків")
    if mismatched:
        print(f"load: УВАГА — у {mismatched} таблицях JSONL не збігся з manifest.json")
        return 1
    return 0


# --------------------------------------------------------------------------- verify


class Report:
    """Кожна перевірка — окремий рядок; вердикт один на всіх."""

    def __init__(self):
        self.failed = 0

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        self.failed += 0 if ok else 1
        print(f"  [{'OK  ' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def phase_verify(args) -> int:
    manifest = load_manifest(args.dump_dir)
    if not os.path.exists(args.db):
        raise SystemExit(f"немає бази {args.db} — спершу --phase load")
    # store.tables() тут не для запису, а щоб схема напевно існувала перед SELECT.
    store.tables(args.db, *(name for name, _ in TABLES))
    db = store.SqliteStore(args.db)  # окреме з'єднання лише для читання сирих колонок
    report = Report()
    second = bool(getattr(args, "second_pass", False))
    # Поріг «прийшла на коробку» для зайвих нетестових заявок. Типово — час цього
    # знімка. У вікні фінальний знімок знімають ПІСЛЯ переключення DNS, і заявка,
    # що прийшла на коробку між 7.1 і 7.3, старша за нього — тому там передають
    # taken_at ПЕРШОГО знімка: усе, що новіше за нього й відсутнє у фінальному,
    # могло взятися лише з коробки (з DynamoDB заявки не видаляються).
    leads_since = getattr(args, "leads_since", None) if second else None
    if leads_since and _parse_ts(leads_since) is None:
        raise SystemExit(f"--leads-since {leads_since!r}: не схоже на ISO-час")
    after_label = "прийшли після --leads-since" if leads_since else "прийшли після знімка"

    print(f"verify: база {args.db} проти знімка від {manifest['taken_at']} ({args.dump_dir})")
    if second:
        print("verify: ДРУГИЙ ПРОХІД — знімок мусить бути ПІДМНОЖИНОЮ бази."
              f" Послаблення для {', '.join(sorted(TTL_TABLES))} (TTL);"
              f" {LEADS_TABLE}: жодної пропажі, зайві — лише тестові або після знімка.")

    print("1. Кількості по таблицях: SQLite проти знімка")
    snapshots = {}
    for name, key_schema in TABLES:
        expected = manifest["tables"][name]["count"]
        items = list(read_jsonl(os.path.join(args.dump_dir, manifest["tables"][name]["file"])))
        snapshots[name] = items
        report.check(
            len(items) == expected,
            f"{name}: JSONL проти manifest",
            f"{len(items)} проти {expected}",
        )
        actual = db.rows(f'SELECT COUNT(*) AS n FROM "{name}"')[0]["n"]
        if relaxed_for_ttl(name, second) or (second and name == LEADS_TABLE):
            why = ("TTL: не менше знімка" if name in TTL_TABLES
                   else "заявки: не менше знімка, зайві розібрано в пункті 2")
            report.check(
                actual >= expected,
                f"{name}: рядків у SQLite ({why})",
                f"{actual} проти {expected}, понад знімок {actual - expected}",
            )
        else:
            report.check(actual == expected, f"{name}: рядків у SQLite", f"{actual} проти {expected}")

    print("2. Ключі: контрольна сума (строго) або входження множин (другий прохід)")
    drift, docs = {}, {}
    lead_drift, explained_ids = (0, 0, 0, 0), set()
    for name, key_schema in TABLES:
        # doc беремо лише на другому проході — там ним звіряють вміст (пункт 2-біс).
        rows = db.rows(f'SELECT hk, rk{", doc" if second else ""} FROM "{name}"')
        if second:
            docs[name] = {(r["hk"], r["rk"]): r["doc"] for r in rows}
        if relaxed_for_ttl(name, second):
            # Контрольна сума по повному набору ключів тут непридатна за побудовою:
            # у базі законно є зайві рядки. Питання інше — чи все зі знімка доїхало.
            want_keys = {key_of(i, key_schema) for i in snapshots[name]}
            have_keys = {(r["hk"], r["rk"]) for r in rows}
            missing, extra = want_keys - have_keys, have_keys - want_keys
            drift[name] = (len(missing), len(extra))
            report.check(
                not missing,
                f"{name}: кожен ключ знімка є в базі",
                f"не доїхало {len(missing)}, понад знімок {len(extra)}",
            )
        elif second and name == LEADS_TABLE:
            want_keys = {key_of(i, key_schema) for i in snapshots[name]}
            have_keys = set(docs[name])
            missing = want_keys - have_keys
            extra_docs = [json.loads(docs[name][k]) for k in sorted(have_keys - want_keys)]
            tests, after, unexplained, explained_ids = classify_extra_leads(
                extra_docs, leads_since or manifest["taken_at"])
            lead_drift = (len(missing), tests, after, unexplained)
            report.check(not missing, f"{name}: кожна заявка знімка є в базі",
                         f"не доїхало {len(missing)}")
            report.check(
                unexplained == 0,
                f"{name}: зайві заявки бази — лише тестові або після знімка",
                f"тестові {tests}, {after_label} {after}, непояснених {unexplained}",
            )
        else:
            want = checksum(key_of(i, key_schema) for i in snapshots[name])
            got = checksum((r["hk"], r["rk"]) for r in rows)
            report.check(
                want == got,
                f"{name}: sha256 ключів" + (" (rk порожній)" if len(key_schema) == 1 else ""),
                f"{got[:16]}… проти {want[:16]}…",
            )

    if second:
        # Послаблення торкається КІЛЬКОСТІ, а не вмісту: рядок зі знімка мусить
        # лежати в базі байт у байт. Строгий прохід цю звірку робить сумою ключів
        # плюс рівністю кількостей; тут її треба зробити явно.
        print("2-біс. Вміст рядків знімка проти бази")
        for name, key_schema in TABLES:
            differing = 0
            for item in snapshots[name]:
                doc = docs[name].get(key_of(item, key_schema))
                if doc is None or json.loads(doc) != item:
                    differing += 1
            report.check(
                differing == 0,
                f"{name}: вміст рядків знімка збігається з базою",
                f"розбіжностей {differing} з {len(snapshots[name])}",
            )

    print("3. ttl лежить в окремій колонці, а не тільки в JSON-доці")
    for name, _key_schema in TABLES:
        # Те саме правило, що й store.SqliteTable._ttl_of: bool за число не рахуємо.
        expected = sum(
            1 for i in snapshots[name]
            if isinstance(i.get("ttl"), int) and not isinstance(i.get("ttl"), bool)
        )
        actual = db.rows(f'SELECT COUNT(*) AS n FROM "{name}" WHERE ttl IS NOT NULL')[0]["n"]
        if relaxed_for_ttl(name, second):
            report.check(
                actual >= expected,
                f"{name}: рядків з колонкою ttl (TTL: не менше знімка)",
                f"{actual} проти {expected}, понад знімок {actual - expected}",
            )
        else:
            report.check(actual == expected, f"{name}: рядків з колонкою ttl", f"{actual} проти {expected}")
        if expected:
            bad = db.rows(
                f'SELECT COUNT(*) AS n FROM "{name}" WHERE ttl IS NOT NULL'
                " AND typeof(ttl) <> 'integer'"
            )[0]["n"]
            report.check(bad == 0, f"{name}: ttl саме число, не рядок", f"нечислових {bad}")

    print("4. is_test у fx_leads лишився булевим")
    leads_name = TABLES[1][0]
    docs = [json.loads(r["doc"]) for r in db.rows(f'SELECT doc FROM "{leads_name}"')]
    booleans = [d.get("is_test") for d in docs]
    report.check(
        bool(booleans) and all(isinstance(v, bool) for v in booleans),
        f"{leads_name}: is_test булевий у всіх рядках",
        f"{sum(1 for v in booleans if isinstance(v, bool))} з {len(booleans)}",
    )
    tests = sum(1 for v in booleans if v is True)
    print(f"       довідка: тестових заявок {tests}, справжніх {len(booleans) - tests}"
          " (нуль справжніх — очікувано)")

    print("5. Заявки читаються через handler.load_leads() (шлях адмінки)")
    leads = read_leads_through_handler(args.db)
    # На другому проході в базі законно є зайві заявки — адмінка мусить бачити їх усі.
    expected_leads = (db.rows(f'SELECT COUNT(*) AS n FROM "{leads_name}"')[0]["n"] if second
                      else manifest["tables"][leads_name]["count"])
    report.check(
        len(leads) == expected_leads,
        "handler.load_leads() повернув усі заявки" + (" бази" if second else ""),
        f"{len(leads)} проти {expected_leads}",
    )
    sampled = leads[: args.sample]
    report.check(
        bool(sampled) and all(l.get("id") and l.get("ts") and "is_test" in l for l in sampled),
        f"перечитано {len(sampled)} заявок: id/ts/is_test на місці",
        f"перевірено {len(sampled)}",
    )
    snapshot_ids = {i.get("id") for i in snapshots[leads_name]}
    # load_leads() віддає найновіші першими — на другому проході це якраз зайві.
    known_ids = snapshot_ids | explained_ids if second else snapshot_ids
    report.check(
        all(l.get("id") in known_ids for l in sampled),
        "id перечитаних заявок є у знімку" + (" або серед пояснених зайвих" if second else ""),
        f"перевірено {len(sampled)}",
    )
    report.check(
        all(isinstance(l.get("is_test"), bool) for l in leads),
        "is_test булевий і після читання через handler",
        f"{len(leads)} заявок",
    )

    if second:
        # Мовчазне «ок» на другому проході марне: людині треба бачити, що розійшлося
        # саме на TTL-таблицях і саме в бік «база більша за знімок».
        print("Підсумок другого проходу — розбіжності допустимі ЛИШЕ тут:")
        for name, _key_schema in TABLES:
            if name in TTL_TABLES:
                missing, extra = drift.get(name, (0, 0))
                print(f"  {name} (TTL): зі знімка не доїхало {missing},"
                      f" у базі понад знімок {extra}")
            else:
                missing, tests, after, unexplained = lead_drift
                print(f"  {name}: зі знімка не доїхало {missing}; зайві в базі — тестові {tests},"
                      f" {after_label} {after}, непояснених {unexplained}")
                print("       вміст кожної заявки знімка звірено в пункті 2-біс;"
                      " «не доїхало» і «непояснених» мусять бути 0")
        print("       значення має лише «не доїхало» — воно мусить бути 0;"
              " «понад знімок» тут очікуване")

    db.close()
    if report.failed:
        print(f"verify: ЧЕРВОНО — {report.failed} перевірок не пройшло")
        return 1
    print("verify: ЗЕЛЕНО — усі перевірки пройшли")
    return 0


def read_leads_through_handler(db_path: str):
    """Той самий шлях, яким заявки бере адмінка: FX_STORAGE=sqlite + load_leads()."""
    os.environ["FX_STORAGE"] = "sqlite"
    os.environ["FX_DB_PATH"] = db_path
    from api import handler

    # Константи handler читає при імпорті, тож окрім env правимо і модуль —
    # _reset_tables() там саме для таких випадків.
    handler.FX_STORAGE = "sqlite"
    handler.FX_DB_PATH = db_path
    handler._reset_tables()
    return handler.load_leads()


# --------------------------------------------------------------------------- CLI


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Переїзд fx_events/fx_leads/fx_sessions з DynamoDB у SQLite",
    )
    parser.add_argument("--phase", required=True, choices=("dump", "load", "verify"))
    parser.add_argument("--region", default=None,
                        help=f"перевизначити AWS_REGION/AWS_DEFAULT_REGION (типово {DEFAULT_REGION})")
    parser.add_argument("--dump-dir", default=os.path.join(REPO_ROOT, "dump"),
                        help="тека знімка (типово dump/ у корені репозиторію)")
    parser.add_argument("--db", default=os.path.join(REPO_ROOT, "data", "aluma.db"),
                        help="файл SQLite (типово data/aluma.db — той самий дефолт, що й FX_DB_PATH)")
    parser.add_argument("--second-pass", action="store_true",
                        help="ФІНАЛЬНИЙ прохід у вікні: для fx_events і fx_sessions знімок"
                             " вважається підмножиною бази (TTL уже прибрав частину рядків"
                             " з DynamoDB). fx_leads і без прапорця, і з ним — строго")
    parser.add_argument("--leads-since", default=None,
                        help="лише з --second-pass: зайва НЕтестова заявка законна, якщо її ts"
                             " пізніший за цей ISO-час (типово — taken_at цього знімка). У вікні"
                             " передавати taken_at ПЕРШОГО знімка — docs/CUTOVER-CHECKLIST.md, 7.5")
    parser.add_argument("--sample", type=int, default=3,
                        help="скільки заявок перечитати через handler у verify")
    args = parser.parse_args(argv)
    restrict_umask()
    return {"dump": phase_dump, "load": phase_load, "verify": phase_verify}[args.phase](args)


if __name__ == "__main__":
    sys.exit(main())
