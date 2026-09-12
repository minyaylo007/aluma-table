#!/usr/bin/env python3
"""Прод проти коробки: кожен URL із sitemap з обох сторін, нормалізація, порівняння.

    python3 scripts/compare_sites.py https://table.central-aparts.store dist
    python3 scripts/compare_sites.py https://table.central-aparts.store https://box-table.central-aparts.store
    python3 scripts/compare_sites.py A B --sitemap dist/sitemap.xml --assets --ignore-eol

План переїзду (aparts/docs/plans/2026-09-10-exit-aws-services-plan.md, Task 1.3 п.5):
перед переключенням DNS — нуль різниць між продом і машиною.

Сторона A — завжди URL (прод). Сторона B — URL або ТЕКА зібраного сайту (dist/). Тека
читається так, як її віддасть nginx з `try_files $uri $uri/ $uri/index.html`: шлях,
потім шлях/index.html. Тож прод можна звірити зі свіжою локальною збіркою, не відкривши
жодного порту.

Список URL — з sitemap.xml (build.py пише його з site/sitemap.xml, підставляючи
{{SITE_URL}}). За замовчуванням береться <A>/sitemap.xml; --sitemap — файл або URL.
До сторінок sitemap додаються /sitemap.xml і /robots.txt: їх теж віддає сайт.
Із loc береться тільки шлях — хост підставляється свій для кожної сторони.

Нормалізація — рівно те, що міняється між збірками (build.py, а не здогадки):
  * хеш вмісту в іменах під /assets/: digest_bytes() -> 10 hex, name.<hash>.ext.
    Інший байт у файлі -> інший хеш -> інше посилання в кожній сторінці.
Дат, nonce чи id збірки build.py не пише: дві збірки одного коміту однакові байт у байт
(перевірено `diff -r`). Тому більше нічого не вирізається.

Кінці рядків НЕ нормалізуються за замовчуванням. Збірка на Windows пише CRLF
(read_text/write_text у текстовому режимі), на Linux — LF. Така різниця показується
окремим рядком «лише кінці рядків»; --ignore-eol свідомо її гасить.

--assets: ще й ассети, на які посилаються сторінки (CSS/JS — рекурсивно). Нормалізація
хешу в HTML чесна тільки тоді, коли за різними іменами лежать однакові файли; --assets
це перевіряє.

Вивід: по кожному URL «збігається / різниться / немає» і короткий фрагмент різниці.
Код виходу: 0 — нуль різниць, 1 — є різниці, 2 — помилка (битий sitemap, мережа, аргументи).

Тільки GET, редиректів не слідуємо. Шляхи /api/ і /admin відмовляємося запитувати навіть
із sitemap. Між мережевими запитами — пауза DELAY (менше двох запитів на секунду).
Лише стандартна бібліотека.
"""

from __future__ import annotations

import argparse
import difflib
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Callable, NamedTuple

DELAY = 0.6          # секунд між мережевими запитами; менше MIN_DELAY не дозволяємо
MIN_DELAY = 0.5
TIMEOUT = 20
USER_AGENT = "aluma-compare-sites/1"
EXTRA_PATHS = ("/sitemap.xml", "/robots.txt")
FORBIDDEN = re.compile(r"^/(api|admin)(/|$)", re.IGNORECASE)
SNIPPET_LINES = 8
SNIPPET_WIDTH = 160

# build.py: f.with_name(f"{f.stem}.{digest_bytes(...)}{f.suffix}"), digest = sha256[:10]
HASH_RE = re.compile(r"(/assets/[\w\-./]*?)\.[0-9a-f]{10}(\.[A-Za-z0-9]+)(?![\w\-])")
HASH_MARK = r"\1.<hash>\2"
# build.py REF плюс хеш у імені — посилання на ассет у сторінці, CSS або JS
REF_RE = re.compile(r"/assets/[\w\-./]+?\.(?:avif|webp|png|jpe?g|gif|ico|svg|woff2?|css|js)(?![\w\-.])")
TEXT_SUFFIXES = {".html", ".css", ".js", ".svg", ".xml", ".txt", ".json", ".webmanifest"}
FOLLOW_SUFFIXES = {".css", ".js"}

SAME, DIFF, MISSING, ERROR = "збігається", "різниться", "немає", "ПОМИЛКА"


class Response(NamedTuple):
    status: int
    body: bytes


# transport(url) -> Response. Завжди GET. У тестах підміняється.
Transport = Callable[[str], Response]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urllib_transport(url: str) -> Response:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": USER_AGENT})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            return Response(r.status, r.read())
    except urllib.error.HTTPError as e:
        return Response(e.code, e.read() or b"")


class Pacer:
    """Між двома мережевими запитами (будь-якої сторони) — щонайменше delay секунд."""

    def __init__(self, delay: float, sleep: Callable[[float], None], clock: Callable[[], float]):
        self.delay, self.sleep, self.clock = delay, sleep, clock
        self.last: float | None = None

    def __call__(self, fn: Callable[[], Response]) -> Response:
        if self.last is not None:
            wait = self.delay - (self.clock() - self.last)
            if wait > 0:
                self.sleep(wait)
        try:
            return fn()
        finally:
            self.last = self.clock()


class HttpSide:
    def __init__(self, base: str, transport: Transport, pacer: Pacer):
        self.base = base.rstrip("/")
        self.label = self.base
        self.transport, self.pacer = transport, pacer

    def get(self, path: str) -> Response:
        if FORBIDDEN.match(path):
            raise ValueError(f"відмова: {path} — /api/ і /admin не запитуємо")
        url = self.base + path
        return self.pacer(lambda: self.transport(url))


class DirSide:
    """Тека зібраного сайту, як її віддасть nginx: try_files $uri $uri/ $uri/index.html."""

    def __init__(self, root: str | pathlib.Path):
        self.root = pathlib.Path(root).resolve()
        self.label = f"{root} (тека, try_files)"

    def get(self, path: str) -> Response:
        rel = urllib.parse.unquote(urllib.parse.urlsplit(path).path).lstrip("/")
        base = (self.root / rel).resolve()
        if base != self.root and self.root not in base.parents:
            return Response(404, b"")
        # "/privacy/" — nginx шукає теку privacy/, а не файл privacy
        candidates = ([] if path.endswith("/") else [base]) + [base / "index.html"]
        for c in candidates:
            if c.is_file():
                return Response(200, c.read_bytes())
        return Response(404, b"")


class Row(NamedTuple):
    path: str
    state: str
    detail: list


class SitemapError(Exception):
    pass


def parse_sitemap(data: bytes) -> list:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise SitemapError(f"sitemap не розбирається як XML: {e}") from None
    if root.tag.rsplit("}", 1)[-1] != "urlset":
        raise SitemapError(f"sitemap: корінь <{root.tag}>, очікувався <urlset>")
    paths = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] != "loc":
            continue
        loc = (el.text or "").strip()
        parts = urllib.parse.urlsplit(loc)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise SitemapError(f"sitemap: loc не абсолютний URL: {loc!r}")
        p = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if FORBIDDEN.match(p):
            raise SitemapError(f"sitemap містить {p} — /api/ і /admin не запитуємо")
        if p not in paths:
            paths.append(p)
    if not paths:
        raise SitemapError("sitemap без жодного <loc>")
    return paths


def normalise(body: bytes) -> str:
    return HASH_RE.sub(HASH_MARK, body.decode("utf-8", errors="replace"))


def _lines(text: str) -> list:
    return re.sub(r">\s*<", ">\n<", text.replace("\r\n", "\n")).splitlines()


def snippet(a: str, b: str) -> list:
    out = []
    for line in difflib.unified_diff(_lines(a), _lines(b), "A", "B", n=0, lineterm=""):
        if line.startswith(("---", "+++")):
            continue
        out.append(line if len(line) <= SNIPPET_WIDTH else line[:SNIPPET_WIDTH] + " …")
        if len(out) >= SNIPPET_LINES:
            out.append("…")
            break
    return out


def compare_bodies(a: bytes, b: bytes, text: bool, ignore_eol: bool) -> tuple:
    if not text:
        if a == b:
            return SAME, []
        return DIFF, [f"байти різні: A {len(a)} Б, B {len(b)} Б"]
    na, nb = normalise(a), normalise(b)
    if na == nb:
        return SAME, []
    if na.replace("\r\n", "\n") == nb.replace("\r\n", "\n"):
        if ignore_eol:
            return SAME, []
        return DIFF, [f"лише кінці рядків: CR у A {na.count(chr(13))}, у B {nb.count(chr(13))}"]
    return DIFF, snippet(na, nb)


def compare_path(path: str, a, b, ignore_eol: bool, text: bool = True) -> tuple:
    """-> (Row, тіло A або None, тіло B або None)."""
    try:
        ra = a.get(path)
        rb = b.get(path)
    except Exception as e:  # мережа, таймаут, відмова — висновку про сторінку нема
        return Row(path, ERROR, [f"{type(e).__name__}: {e}"]), None, None
    if ra.status == 200 and rb.status == 200:
        state, detail = compare_bodies(ra.body, rb.body, text, ignore_eol)
        return Row(path, state, detail), ra.body, rb.body
    if ra.status != 200 and rb.status != 200:
        return Row(path, MISSING, [f"на обох сторонах: A {ra.status}, B {rb.status}"]), None, None
    if ra.status != 200:
        return Row(path, MISSING, [f"на A (статус {ra.status})"]), None, rb.body
    return Row(path, MISSING, [f"на B (статус {rb.status})"]), ra.body, None


def asset_refs(body: bytes) -> dict:
    """нормалізоване імʼя -> справжнє посилання цієї сторони."""
    text = body.decode("utf-8", errors="replace")
    return {HASH_RE.sub(HASH_MARK, r): r for r in REF_RE.findall(text)}


def compare_assets(bodies_a: list, bodies_b: list, a, b, ignore_eol: bool) -> list:
    refs_a, refs_b = {}, {}
    for body in bodies_a:
        refs_a.update(asset_refs(body))
    for body in bodies_b:
        refs_b.update(asset_refs(body))
    rows, done = [], set()
    while True:
        pending = [n for n in sorted(set(refs_a) | set(refs_b)) if n not in done]
        if not pending:
            return rows
        for name in pending:
            done.add(name)
            if name not in refs_b:
                rows.append(Row(refs_a[name], MISSING, ["посилання тільки на A"]))
                continue
            if name not in refs_a:
                rows.append(Row(refs_b[name], MISSING, ["посилання тільки на B"]))
                continue
            suffix = pathlib.PurePosixPath(name).suffix.lower()
            try:
                ra, rb = a.get(refs_a[name]), b.get(refs_b[name])
            except Exception as e:
                rows.append(Row(name, ERROR, [f"{type(e).__name__}: {e}"]))
                continue
            if ra.status != 200 or rb.status != 200:
                rows.append(Row(name, MISSING, [f"A {refs_a[name]} -> {ra.status}, B {refs_b[name]} -> {rb.status}"]))
                continue
            state, detail = compare_bodies(ra.body, rb.body, suffix in TEXT_SUFFIXES, ignore_eol)
            rows.append(Row(name, state, detail))
            if suffix in FOLLOW_SUFFIXES:
                refs_a.update({k: v for k, v in asset_refs(ra.body).items() if k not in refs_a})
                refs_b.update({k: v for k, v in asset_refs(rb.body).items() if k not in refs_b})


def load_sitemap(src: str | None, side_a: HttpSide, transport: Transport, pacer: Pacer) -> tuple:
    try:
        if src is None:
            r = side_a.get("/sitemap.xml")
            where = f"{side_a.base}/sitemap.xml"
        elif src.startswith(("http://", "https://")):
            r = pacer(lambda: transport(src))
            where = src
        else:
            r = Response(200, pathlib.Path(src).read_bytes())
            where = src
    except SitemapError:
        raise
    except Exception as e:
        raise SitemapError(f"sitemap не отримано: {type(e).__name__}: {e}") from None
    if r.status != 200:
        raise SitemapError(f"sitemap {where}: статус {r.status}")
    return parse_sitemap(r.body), where


def origin_refusal(base: str) -> str | None:
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return f"{base!r}: потрібен http(s)://хост"
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        return f"{base!r}: тільки корінь сайту, без шляху"
    return None


def run(side_a: str, side_b: str, *, sitemap: str | None = None, assets: bool = False,
        ignore_eol: bool = False, transport: Transport = urllib_transport, delay: float = DELAY,
        sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
        out=None) -> int:
    out = out or sys.stdout

    def say(line: str = "") -> None:
        print(line, file=out)

    if delay < MIN_DELAY:
        say(f"ПОМИЛКА: --delay {delay} < {MIN_DELAY} — прод так часто не смикаємо")
        return 2
    refusal = origin_refusal(side_a)
    if refusal:
        say(f"ПОМИЛКА: сторона A {refusal}")
        return 2
    pacer = Pacer(delay, sleep, clock)
    a = HttpSide(side_a, transport, pacer)
    if side_b.startswith(("http://", "https://")):
        refusal = origin_refusal(side_b)
        if refusal:
            say(f"ПОМИЛКА: сторона B {refusal}")
            return 2
        b = HttpSide(side_b, transport, pacer)
    else:
        if not pathlib.Path(side_b).is_dir():
            say(f"ПОМИЛКА: сторона B {side_b!r} — не URL і не тека")
            return 2
        b = DirSide(side_b)

    say(f"A = {a.label}")
    say(f"B = {b.label}")
    try:
        paths, where = load_sitemap(sitemap, a, transport, pacer)
    except SitemapError as e:
        say(f"ПОМИЛКА: {e}")
        return 2
    paths += [p for p in EXTRA_PATHS if p not in paths]
    say(f"sitemap: {where} — {len(paths) - len(EXTRA_PATHS)} URL (+ {', '.join(EXTRA_PATHS)})")
    say()

    rows, bodies_a, bodies_b = [], [], []
    for p in paths:
        row, ba, bb = compare_path(p, a, b, ignore_eol)
        rows.append(row)
        if ba is not None:
            bodies_a.append(ba)
        if bb is not None:
            bodies_b.append(bb)
    asset_rows = compare_assets(bodies_a, bodies_b, a, b, ignore_eol) if assets else []

    for title, group in (("сторінки", rows), ("ассети", asset_rows)):
        if not group:
            continue
        say(f"— {title}:")
        for r in group:
            if r.state == SAME and title == "ассети":
                continue   # сотня однакових картинок нічого не каже; рахуються в підсумку
            say(f"{r.state:<11} {r.path}")
            for d in r.detail:
                say(f"{'':<11}   {d}")
    say()
    every = rows + asset_rows

    def count(state, group):
        return sum(1 for r in group if r.state == state)

    say(f"Підсумок: сторінок {len(rows)} — {count(SAME, rows)} збігається, {count(DIFF, rows)} різниться, "
        f"{count(MISSING, rows)} немає на одній стороні, {count(ERROR, rows)} помилок")
    if assets:
        say(f"          ассетів {len(asset_rows)} — {count(SAME, asset_rows)} збігається, "
            f"{count(DIFF, asset_rows)} різниться, {count(MISSING, asset_rows)} немає, "
            f"{count(ERROR, asset_rows)} помилок")
    if count(ERROR, every):
        say("Код 2: є помилки — висновку нема.")
        return 2
    if count(DIFF, every) or count(MISSING, every):
        say("Код 1: є різниці.")
        return 1
    say("Код 0: нуль різниць.")
    return 0


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Порівняти дві копії сайту ALUMA по sitemap (тільки GET).")
    ap.add_argument("side_a", help="URL проду, напр. https://table.central-aparts.store")
    ap.add_argument("side_b", help="URL коробки або тека зібраного сайту (dist)")
    ap.add_argument("--sitemap", help="файл або URL sitemap.xml (за замовчуванням <A>/sitemap.xml)")
    ap.add_argument("--assets", action="store_true", help="порівняти й ассети, на які посилаються сторінки")
    ap.add_argument("--ignore-eol", action="store_true", help="не вважати різницею CRLF проти LF")
    ap.add_argument("--delay", type=float, default=DELAY, help=f"пауза між запитами, с (>= {MIN_DELAY})")
    args = ap.parse_args(argv)
    return run(args.side_a, args.side_b, sitemap=args.sitemap, assets=args.assets,
               ignore_eol=args.ignore_eol, delay=args.delay)


if __name__ == "__main__":
    sys.exit(main())
