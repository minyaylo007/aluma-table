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
RAW = "https://raw.githubusercontent.com/minyaylo007/aluma-table/master/"
STORY_JPG = RAW + "docs/ig/stories/03-tones.jpg"
STORY_MP4 = RAW + "docs/ig/stories/01-tavor.mp4"


class FakeGraph:
    """Відповіді за (метод, шлях); записує кожен виклик з розібраними параметрами."""

    def __init__(self, statuses=("FINISHED",), refresh=None, fail=None, product="FEED"):
        self.calls = []
        self.product = product
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
            return 200, json.dumps({"permalink": "https://www.instagram.com/p/XYZ/", "id": "M1",
                                    "media_product_type": self.product}).encode()
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


class StoryTests(Base):
    """--story: media_type=STORIES, без підпису; ролик чекає довше; результат — саме STORY."""

    def run_story(self, graph, *args, head=(200, {"content-type": "image/jpeg", "content-length": "200000"})):
        heads = []

        def fake_head(url):
            heads.append(url)
            return head

        with mock.patch.object(ig_publish, "_head", fake_head):
            res = self.run_main(graph, "--story", *args)
        return (*res, heads)

    def test_image_story_order_and_params(self):
        g = FakeGraph(product="STORY")
        code, out, err, _, heads = self.run_story(g, "--image-url", STORY_JPG)
        self.assertEqual(code, 0, err)
        seq = [(m, p.split("/", 2)[-1]) for m, p, _ in g.calls]
        self.assertEqual(seq, [("POST", f"{USER}/media"), ("GET", "C1"),
                               ("POST", f"{USER}/media_publish"), ("GET", "M1")])
        media = g.calls[0][2]
        self.assertEqual(media["media_type"], "STORIES")
        self.assertEqual(media["image_url"], STORY_JPG)
        self.assertNotIn("caption", media)
        self.assertNotIn("video_url", media)
        self.assertEqual(g.calls[3][2]["fields"], "media_product_type,permalink")
        self.assertIn("media_product_type=STORY", out)
        self.assertEqual(heads, [])  # HEAD — лише в dry-run
        self.assertNotIn(TOKEN, out + err)

    def test_video_story_waits_up_to_300s(self):
        g = FakeGraph(statuses=("IN_PROGRESS",) * 40 + ("FINISHED",), product="STORY")
        clock = iter(range(0, 10000, 5))
        with mock.patch.object(ig_publish.time, "monotonic", lambda: next(clock)):
            code, _, err, sleeps, _ = self.run_story(g, "--video-url", STORY_MP4)
        self.assertEqual(code, 0, err)
        media = g.calls[0][2]
        self.assertEqual((media["media_type"], media["video_url"]), ("STORIES", STORY_MP4))
        self.assertNotIn("image_url", media)
        self.assertEqual(len(sleeps), 40)  # ~200 с очікування — за межею поста (60), у межі ролика (300)

    def test_video_story_wait_limit(self):
        g = FakeGraph(statuses=("IN_PROGRESS",), product="STORY")
        clock = iter(range(0, 10000, 10))
        with mock.patch.object(ig_publish.time, "monotonic", lambda: next(clock)):
            code, _, err, _, _ = self.run_story(g, "--video-url", STORY_MP4)
        self.assertEqual(code, 1)
        self.assertIn("не FINISHED за 300", err)
        self.assertFalse(any(p.endswith("media_publish") for _, p, _ in g.calls))

    def test_not_a_story_is_error(self):
        code, _, err, _, _ = self.run_story(FakeGraph(product="FEED"), "--image-url", STORY_JPG)
        self.assertEqual(code, 1)
        self.assertIn("не STORY", err)

    def refused(self, *args, text):
        g = FakeGraph(product="STORY")
        code, _, err, _, _ = self.run_story(g, *args)
        self.assertEqual(code, 1)
        self.assertEqual(g.calls, [])
        self.assertIn(text, err)

    def test_story_refusals(self):
        self.refused(text="рівно один")
        self.refused("--image-url", STORY_JPG, "--video-url", STORY_MP4, text="рівно один")
        self.refused("--image-url", STORY_JPG, "--caption-file", str(self.caption), text="підпису")
        self.refused("--image-url", STORY_MP4, text=".jpg")
        self.refused("--video-url", STORY_JPG, text=".mp4")
        self.refused("--video-url", STORY_MP4.replace("https", "http"), text="https")

    def test_video_url_without_story_refused(self):
        g = FakeGraph()
        code, _, _, _ = self.run_main(g, "--video-url", STORY_MP4, "--caption-file", str(self.caption))
        self.assertEqual(code, 1)
        self.assertEqual(g.calls, [])

    def test_dry_run_head_and_local_copy(self):
        g = FakeGraph()
        code, out, err, _, heads = self.run_story(g, "--image-url", STORY_JPG, "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(heads, [STORY_JPG])
        self.assertEqual([(m, p.rsplit("/", 1)[-1]) for m, p, _ in g.calls], [("GET", "me")])
        self.assertIn("URL 200", out)
        self.assertIn("нічого не створено", out)

    def test_dry_run_not_in_master_yet(self):
        g = FakeGraph()
        code, _, err, _, _ = self.run_story(g, "--image-url", STORY_JPG, "--dry-run", head=(404, {}))
        self.assertEqual(code, 1)
        self.assertIn("HTTP 404", err)
        self.assertEqual(g.calls, [])

    def test_dry_run_too_big(self):
        g = FakeGraph()
        code, _, err, _, _ = self.run_story(g, "--image-url", STORY_JPG, "--dry-run",
                                            head=(200, {"content-length": str(9 * 1024 * 1024)}))
        self.assertEqual(code, 1)
        self.assertIn("байт", err)

    def test_local_copy_only_inside_docs(self):
        self.assertIsNone(ig_publish._local_copy(RAW + "docs/../api/handler.py"))
        self.assertIsNone(ig_publish._local_copy("https://example.com/x/docs/ig/stories/03-tones.jpg"))
        self.assertEqual(ig_publish._local_copy(STORY_JPG), ig_publish.ROOT / "docs/ig/stories/03-tones.jpg")

    def test_local_check_without_tools(self):
        f = ig_publish.ROOT / "docs/ig/stories/01-tavor.mp4"
        self.assertIn("не перевірено", ig_publish.check_story_local(f, True, which=lambda _: None))
        with mock.patch.dict("sys.modules", {"PIL": None}):
            self.assertIn("не перевірено", ig_publish.check_story_local(f.with_suffix(".jpg"), False))

    def test_local_check_rejects_square(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow нема")
        sq = self.dir / "sq.jpg"
        Image.new("RGB", (1080, 1080)).save(sq, "JPEG")
        with self.assertRaises(ig_publish.IgError):
            ig_publish.check_story_local(sq, False)


class StoryFilesTests(unittest.TestCase):
    """docs/ig/stories/: кожна історія — NN-слаг.jpg (+ .mp4) + .txt; в описі «הדמיה» і дата виходу; без «знижок»."""
    DIR = pathlib.Path(__file__).resolve().parents[1] / "docs" / "ig" / "stories"

    def test_five_stories(self):
        notes = sorted(self.DIR.glob("[0-9][0-9]-*.txt"))
        self.assertEqual([t.name[:2] for t in notes], ["01", "02", "03", "04", "05"])
        for txt in notes:
            raw = txt.read_bytes()
            self.assertNotIn(b"\r", raw, txt.name)
            text = raw.decode("utf-8")
            self.assertIn("הדמיה", text, txt.name)
            self.assertRegex(text, r"2026-10-2\d", txt.name)
            self.assertNotRegex(text, r"נותרו|הנחה|מבצע", txt.name)
            jpg = txt.with_suffix(".jpg")
            self.assertEqual(jpg.read_bytes()[:3], b"\xff\xd8\xff", jpg.name)
            mp4 = txt.with_suffix(".mp4")
            if mp4.exists():
                self.assertEqual(mp4.read_bytes()[4:8], b"ftyp", mp4.name)
                self.assertLessEqual(mp4.stat().st_size, 4 * 1024 * 1024, mp4.name)

    def test_jpg_9x16(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow нема")
        for jpg in sorted(self.DIR.glob("[0-9][0-9]-*.jpg")):
            self.assertIn("1080×1920", ig_publish.check_story_local(jpg, False), jpg.name)


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
