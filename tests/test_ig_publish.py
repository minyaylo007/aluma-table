"""scripts/ig_publish.py — публікація в @aluma.il без мережі: HTTP підмінено, токен вигаданий.

    python -m unittest tests.test_ig_publish -v
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import stat
import tempfile
import unittest
import urllib.parse
from unittest import mock

from scripts import ig_publish

TOKEN = "IGAAfakeTOKEN1234567890abc"
NEW_TOKEN = "IGAAnewTOKEN0987654321xyz"
USER = "17841400000000000"
IMG = "https://raw.githubusercontent.com/minyaylo007/aluma-table/master/docs/ig/01-tavor.jpg"


class FakeGraph:
    """Відповіді за (метод, шлях); записує кожен виклик з розібраними параметрами."""

    def __init__(self, statuses=("FINISHED",), refresh=None, fail=None):
        self.calls = []
        self.statuses = list(statuses)
        self.refresh = refresh or {"access_token": NEW_TOKEN, "token_type": "bearer", "expires_in": 5183944}
        self.fail = fail  # (метод, хвіст шляху, статус, тіло)

    def __call__(self, method, url, data):
        parts = urllib.parse.urlsplit(url)
        raw = parts.query if method == "GET" else data.decode("ascii")
        params = dict(urllib.parse.parse_qsl(raw))
        path = parts.path
        self.calls.append((method, path, params))
        if self.fail and method == self.fail[0] and path.endswith(self.fail[1]):
            return self.fail[2], self.fail[3].encode()
        if path.endswith("/me"):
            return 200, b'{"username": "aluma.il", "id": "1"}'
        if path.endswith("/refresh_access_token"):
            return 200, json.dumps(self.refresh).encode()
        if method == "POST" and path.endswith(f"/{USER}/media"):
            return 200, b'{"id": "C1"}'
        if method == "POST" and path.endswith("/media_publish"):
            return 200, b'{"id": "M1"}'
        if method == "GET" and path.endswith("/C1"):
            code = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return 200, json.dumps({"status_code": code, "status": f"{code}: details"}).encode()
        if method == "GET" and path.endswith("/M1"):
            return 200, b'{"permalink": "https://www.instagram.com/p/XYZ/", "id": "M1"}'
        return 404, b'{"error": {"message": "unknown"}}'


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.env = self.dir / "ig.env"
        self.env.write_text(f"# коментар лишається\nIG_USER_ID={USER}\nIG_ACCESS_TOKEN={TOKEN}\n", encoding="utf-8")
        os.chmod(self.env, 0o600)
        self.caption = self.dir / "01.txt"
        self.caption.write_text("תבור. שולחן.\n\nTAVOR.\n\n#aluma #שולחןאוכל\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, graph, *args):
        out, err = io.StringIO(), io.StringIO()
        sleeps = []
        with mock.patch.object(ig_publish, "_http", graph), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ig_publish.main(["--env", str(self.env), *args], sleep=sleeps.append)
        return code, out.getvalue(), err.getvalue(), sleeps

    def post_args(self):
        return ["--image-url", IMG, "--caption-file", str(self.caption)]


class PublishTests(Base):
    def test_order_and_params(self):
        g = FakeGraph(statuses=("IN_PROGRESS", "FINISHED"))
        code, out, err, sleeps = self.run_main(g, *self.post_args())
        self.assertEqual(code, 0, err)
        seq = [(m, p.split("/", 2)[-1]) for m, p, _ in g.calls]
        self.assertEqual(seq, [("POST", f"{USER}/media"), ("GET", "C1"), ("GET", "C1"),
                               ("POST", f"{USER}/media_publish"), ("GET", "M1")])
        self.assertTrue(all(p.startswith("/v") for _, p, _ in g.calls))
        media = g.calls[0][2]
        self.assertEqual(media["image_url"], IMG)
        self.assertEqual(media["caption"], self.caption.read_text(encoding="utf-8").strip("\n"))
        self.assertEqual(media["access_token"], TOKEN)
        self.assertEqual(g.calls[1][2]["fields"], "status_code,status")
        self.assertEqual(g.calls[3][2]["creation_id"], "C1")
        self.assertEqual(g.calls[4][2]["fields"], "permalink")
        self.assertEqual(len(sleeps), 1)
        self.assertIn("media_id=M1", out)
        self.assertIn("permalink=https://www.instagram.com/p/XYZ/", out)
        self.assertNotIn(TOKEN, out + err)

    def test_post_token_in_body_not_url(self):
        seen = []

        def spy(method, url, data):
            seen.append((method, url))
            return FakeGraph()(method, url, data)

        self.run_main(spy, *self.post_args())
        for method, url in seen:
            if method == "POST":
                self.assertNotIn(TOKEN, url)

    def test_error_status_stops_before_publish(self):
        g = FakeGraph(statuses=("ERROR",))
        code, out, err, _ = self.run_main(g, *self.post_args())
        self.assertEqual(code, 1)
        self.assertIn("ERROR: details", err)
        self.assertFalse(any(p.endswith("media_publish") for _, p, _ in g.calls))

    def test_expired_status(self):
        code, _, err, _ = self.run_main(FakeGraph(statuses=("EXPIRED",)), *self.post_args())
        self.assertEqual(code, 1)
        self.assertIn("EXPIRED", err)

    def test_wait_limit(self):
        g = FakeGraph(statuses=("IN_PROGRESS",))
        clock = iter(range(0, 1000, 10))
        with mock.patch.object(ig_publish.time, "monotonic", lambda: next(clock)):
            code, _, err, _ = self.run_main(g, *self.post_args(), "--wait", "25")
        self.assertEqual(code, 1)
        self.assertIn("не FINISHED", err)
        self.assertFalse(any(p.endswith("media_publish") for _, p, _ in g.calls))


class DryRunTests(Base):
    def test_one_get_me_no_post(self):
        g = FakeGraph()
        code, out, err, _ = self.run_main(g, *self.post_args(), "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual([(m, p.rsplit("/", 1)[-1]) for m, p, _ in g.calls], [("GET", "me")])
        self.assertIn("@aluma.il", out)
        self.assertNotIn(TOKEN, out + err)

    def check_refused(self, *args, text=None):
        g = FakeGraph()
        code, _, err, _ = self.run_main(g, *args, "--dry-run")
        self.assertEqual(code, 1)
        self.assertEqual(g.calls, [])
        if text:
            self.assertIn(text, err)

    def test_http_url_refused(self):
        self.check_refused("--image-url", IMG.replace("https", "http"), "--caption-file", str(self.caption))

    def test_png_refused(self):
        self.check_refused("--image-url", IMG[:-4] + ".png", "--caption-file", str(self.caption))

    def test_long_caption_refused(self):
        self.caption.write_text("א" * 2201, encoding="utf-8")
        self.check_refused(*self.post_args(), text="2200")

    def test_too_many_hashtags_refused(self):
        self.caption.write_text(" ".join(f"#תג{i}" for i in range(31)), encoding="utf-8")
        self.check_refused(*self.post_args(), text="хештегів 31")

    def test_missing_caption_file(self):
        self.check_refused("--image-url", IMG, "--caption-file", str(self.dir / "nope.txt"))

    def test_missing_token(self):
        self.env.write_text(f"IG_USER_ID={USER}\n", encoding="utf-8")
        self.check_refused(*self.post_args(), text="IG_ACCESS_TOKEN")


class RedactionTests(Base):
    def test_meta_error_body_redacted(self):
        body = json.dumps({"error": {"message": f"bad url ?access_token={TOKEN}&x=1 token {TOKEN}"}})
        g = FakeGraph(fail=("POST", "/media", 400, body))
        code, out, err, _ = self.run_main(g, *self.post_args())
        self.assertEqual(code, 1)
        self.assertIn("HTTP 400", err)
        self.assertIn("bad url", err)
        self.assertNotIn(TOKEN, out + err)

    def test_network_exception_redacted(self):
        def boom(method, url, data):
            raise OSError(f"timed out: {url}")

        code, out, err, _ = self.run_main(boom, *self.post_args(), "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("timed out", err)
        self.assertNotIn(TOKEN, out + err)

    def test_redact_unknown_token_in_url(self):
        self.assertEqual(ig_publish._redact("x?access_token=SECRET&y=1"), "x?access_token=[redacted]&y=1")


class RefreshTests(Base):
    def test_writes_file_600_and_hides_token(self):
        g = FakeGraph()
        code, out, err, _ = self.run_main(g, "--refresh")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(g.calls), 1)
        method, path, params = g.calls[0]
        self.assertEqual((method, path), ("GET", "/refresh_access_token"))
        self.assertEqual(params, {"grant_type": "ig_refresh_token", "access_token": TOKEN})
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)
        text = self.env.read_text(encoding="utf-8")
        self.assertIn(f"IG_ACCESS_TOKEN={NEW_TOKEN}\n", text)
        self.assertNotIn(TOKEN, text)
        self.assertIn("# коментар лишається", text)
        self.assertIn(f"IG_USER_ID={USER}", text)
        self.assertEqual(json.loads(out), {"event": "ig_token_refreshed", "expires_in_days": 59})
        self.assertNotIn(NEW_TOKEN, out + err)
        self.assertNotIn(TOKEN, out + err)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["01.txt", "ig.env"])  # тимчасового не лишилось

    def test_bad_response_keeps_old_file(self):
        before = self.env.read_text(encoding="utf-8")
        code, _, err, _ = self.run_main(FakeGraph(refresh={"expires_in": 1}), "--refresh")
        self.assertEqual(code, 1)
        self.assertEqual(self.env.read_text(encoding="utf-8"), before)

    def test_meta_error_keeps_old_file(self):
        before = self.env.read_text(encoding="utf-8")
        g = FakeGraph(fail=("GET", "/refresh_access_token", 400, f'{{"error": "{TOKEN} too early"}}'))
        code, out, err, _ = self.run_main(g, "--refresh")
        self.assertEqual(code, 1)
        self.assertEqual(self.env.read_text(encoding="utf-8"), before)
        self.assertNotIn(TOKEN, out + err)


class PostFilesTests(unittest.TestCase):
    """docs/ig/: кожен пост — пара NN-слаг.jpg + .txt; підпис чесний («הדמיה»), без цін, у межах Instagram."""
    DIR = pathlib.Path(__file__).resolve().parents[1] / "docs" / "ig"

    def test_pairs_and_captions(self):
        captions = sorted(self.DIR.glob("*.txt"))
        self.assertEqual(len(captions), 5)
        for txt in captions:
            raw = txt.read_bytes()
            self.assertNotIn(b"\r", raw, txt.name)
            text = raw.decode("utf-8")
            ig_publish.check_caption(text)
            self.assertIn("הדמיה", text, txt.name)
            self.assertNotRegex(text, r"₪|\bNIS\b|ש״ח|шек", txt.name)
            jpg = txt.with_suffix(".jpg")
            self.assertEqual(jpg.read_bytes()[:3], b"\xff\xd8\xff", jpg.name)


if __name__ == "__main__":
    unittest.main()
