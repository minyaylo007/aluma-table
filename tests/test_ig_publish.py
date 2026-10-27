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
import time
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


REEL_MP4 = RAW + "docs/ig/reels/01-tavor-open.mp4"


class ReelTests(Base):
    """--reel: media_type=REELS, підпис, share_to_feed; ролик чекає до 300 с; результат — саме REELS."""

    def run_reel(self, graph, *args, head=(200, {"content-type": "video/mp4", "content-length": "2000000"})):
        heads = []

        def fake_head(url):
            heads.append(url)
            return head

        with mock.patch.object(ig_publish, "_head", fake_head):
            res = self.run_main(graph, "--reel", *args)
        return (*res, heads)

    def test_order_and_params(self):
        g = FakeGraph(product="REELS")
        code, out, err, _, heads = self.run_reel(g, "--video-url", REEL_MP4, "--caption-file", str(self.caption))
        self.assertEqual(code, 0, err)
        seq = [(m, p.split("/", 2)[-1]) for m, p, _ in g.calls]
        self.assertEqual(seq, [("POST", f"{USER}/media"), ("GET", "C1"),
                               ("POST", f"{USER}/media_publish"), ("GET", "M1")])
        media = g.calls[0][2]
        self.assertEqual(media["media_type"], "REELS")
        self.assertEqual(media["video_url"], REEL_MP4)
        self.assertEqual(media["share_to_feed"], "true")
        self.assertEqual(media["caption"], self.caption.read_text(encoding="utf-8").strip("\n"))
        self.assertNotIn("image_url", media)
        self.assertEqual(g.calls[3][2]["fields"], "media_product_type,permalink")
        self.assertIn("media_id=M1", out)
        self.assertIn("media_product_type=REELS", out)
        self.assertIn("permalink=https://www.instagram.com/p/XYZ/", out)
        self.assertEqual(heads, [])
        self.assertNotIn(TOKEN, out + err)

    def test_waits_up_to_300s(self):
        g = FakeGraph(statuses=("IN_PROGRESS",) * 40 + ("FINISHED",), product="REELS")
        clock = iter(range(0, 10000, 5))
        with mock.patch.object(ig_publish.time, "monotonic", lambda: next(clock)):
            code, _, err, sleeps, _ = self.run_reel(g, "--video-url", REEL_MP4, "--caption-file", str(self.caption))
        self.assertEqual(code, 0, err)
        self.assertEqual(len(sleeps), 40)

    def test_not_a_reel_is_error(self):
        code, _, err, _, _ = self.run_reel(FakeGraph(product="FEED"), "--video-url", REEL_MP4,
                                           "--caption-file", str(self.caption))
        self.assertEqual(code, 1)
        self.assertIn("не REELS", err)

    def refused(self, *args, text):
        g = FakeGraph(product="REELS")
        code, _, err, _, _ = self.run_reel(g, *args)
        self.assertEqual(code, 1)
        self.assertEqual(g.calls, [])
        self.assertIn(text, err)

    def test_refusals(self):
        cap = ("--caption-file", str(self.caption))
        self.refused(*cap, text="--video-url")
        self.refused("--video-url", REEL_MP4, text="--caption-file")
        self.refused("--video-url", REEL_MP4, "--image-url", IMG, *cap, text="без --image-url")
        self.refused("--video-url", IMG, *cap, text=".mp4")
        self.refused("--video-url", REEL_MP4.replace("https", "http"), *cap, text="https")
        self.refused("--video-url", REEL_MP4, "--story", *cap, text="разом")
        self.caption.write_text(" ".join(f"#תג{i}" for i in range(31)), encoding="utf-8")
        self.refused("--video-url", REEL_MP4, *cap, text="хештегів 31")

    def test_dry_run(self):
        g = FakeGraph()
        code, out, err, _, heads = self.run_reel(g, "--video-url", REEL_MP4, "--caption-file", str(self.caption),
                                                 "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(heads, [REEL_MP4])
        self.assertEqual([(m, p.rsplit("/", 1)[-1]) for m, p, _ in g.calls], [("GET", "me")])
        self.assertIn("reel", out)
        self.assertIn("нічого не створено", out)

    def test_dry_run_reel_bigger_than_story_limit_ok(self):
        size = str(150 * 1024 * 1024)  # > 100 МБ історії, < 300 МБ reel
        code, _, err, _, _ = self.run_reel(FakeGraph(), "--video-url", REEL_MP4, "--caption-file", str(self.caption),
                                           "--dry-run", head=(200, {"content-length": size}))
        self.assertEqual(code, 0, err)

    def test_local_duration_limit_90(self):
        f = self.dir / "r.mp4"
        f.write_bytes(b"x")

        def probe(seconds):
            out = json.dumps({"streams": [{"codec_name": "h264", "width": 1080, "height": 1920}],
                              "format": {"duration": str(seconds)}})
            return mock.Mock(stdout=out)

        with mock.patch.object(ig_publish.subprocess, "run", return_value=probe(75)):
            self.assertIn("75.0 с", ig_publish.check_story_local(f, True, which=lambda _: "/x/ffprobe",
                                                                  max_seconds=ig_publish.REEL_VIDEO_SECONDS))
            with self.assertRaises(ig_publish.IgError):  # історія: та сама тривалість — понад 60
                ig_publish.check_story_local(f, True, which=lambda _: "/x/ffprobe")
        with mock.patch.object(ig_publish.subprocess, "run", return_value=probe(95)):
            with self.assertRaises(ig_publish.IgError):
                ig_publish.check_story_local(f, True, which=lambda _: "/x/ffprobe",
                                             max_seconds=ig_publish.REEL_VIDEO_SECONDS)


NOW = 1793000000  # 2026-10-27, фіксований «зараз» для --insights


class InsightsGraph:
    """Graph для --insights: дві свіжі публікації й одна стара; метрика views поста — відмова, акаунт без website_clicks."""

    def __init__(self):
        self.calls = []

    def __call__(self, method, url, data):
        parts = urllib.parse.urlsplit(url)
        params = dict(urllib.parse.parse_qsl(parts.query))
        path = parts.path
        self.calls.append((method, path, params))
        if method != "GET":
            return 400, b'{"error": "read only"}'
        stamp = lambda days: time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(NOW - days * 86400))  # noqa: E731
        if path.endswith(f"/{USER}/media"):
            return 200, json.dumps({"data": [
                {"id": "R1", "media_type": "VIDEO", "media_product_type": "REELS", "timestamp": stamp(1),
                 "permalink": "https://www.instagram.com/reel/R1/"},
                {"id": "P1", "media_type": "IMAGE", "media_product_type": "FEED", "timestamp": stamp(3),
                 "permalink": "https://www.instagram.com/p/P1/"},
                {"id": "OLD", "media_type": "IMAGE", "media_product_type": "FEED", "timestamp": stamp(20),
                 "permalink": "https://www.instagram.com/p/OLD/"}]}).encode()
        metric = params.get("metric", "")
        if path.endswith("/R1/insights"):
            return 200, json.dumps({"data": [{"name": m, "values": [{"value": 10 + i}]}
                                             for i, m in enumerate(metric.split(","))]}).encode()
        if path.endswith("/P1/insights"):
            if "views" in metric.split(","):
                return 400, json.dumps({"error": {"message": f"views unsupported token {TOKEN}"}}).encode()
            return 200, json.dumps({"data": [{"name": metric, "values": [{"value": 2}]}]}).encode()
        if path.endswith(f"/{USER}/insights"):
            if "website_clicks" in metric.split(","):
                return 400, b'{"error": {"message": "no permission"}}'
            return 200, json.dumps({"data": [{"name": metric, "total_value": {"value": 7}}]}).encode()
        if path.endswith(f"/{USER}"):
            return 200, b'{"followers_count": 3, "id": "1"}'
        return 404, b'{"error": "unknown"}'


class InsightsTests(Base):
    def run_insights(self, *args):
        g = InsightsGraph()
        with mock.patch.object(ig_publish.time, "time", lambda: NOW):
            code, out, err, _ = self.run_main(g, "--insights", *args)
        return g, code, out, err

    def test_table_and_fallbacks(self):
        g, code, out, err = self.run_insights("--days", "7")
        self.assertEqual(code, 0, err)
        self.assertIn("публікацій: 2", out)
        self.assertIn("https://www.instagram.com/reel/R1/", out)
        self.assertNotIn("OLD", out)  # поза вікном 7 днів — без метрик
        self.assertFalse(any("/OLD/" in p for _, p, _ in g.calls))
        reel_row = next(line for line in out.splitlines() if "/reel/R1/" in line)
        self.assertEqual(reel_row.split()[2:8], ["10", "11", "14", "15", "12", "13"])  # reach views likes comments saved shares
        post_row = next(line for line in out.splitlines() if "/p/P1/" in line)
        self.assertEqual(post_row.split()[2:4], ["2", "—"])
        self.assertIn("підписників 3", out)
        self.assertIn("переглядів профілю 7", out)
        self.assertIn("переходів на сайт недоступно", out)
        self.assertIn("недоступно від API (акаунт): website_clicks", out)
        self.assertIn("views", out.splitlines()[-1])
        self.assertTrue(all(m == "GET" for m, _, _ in g.calls))  # звіт нічого не створює
        self.assertNotIn(TOKEN, out + err)

    def test_account_window_params(self):
        g, code, _, err = self.run_insights("--days", "45")
        self.assertEqual(code, 0, err)
        acc = [p for _, path, p in g.calls if path.endswith(f"/{USER}/insights")][0]
        self.assertEqual(acc["metric_type"], "total_value")
        self.assertEqual(acc["period"], "day")
        self.assertEqual(int(acc["until"]) - int(acc["since"]), 30 * 86400)  # API: вікно до 30 днів

    def test_bad_days(self):
        g, code, _, err = self.run_insights("--days", "0")
        self.assertEqual(code, 1)
        self.assertEqual(g.calls, [])

    def test_insight_values_shapes(self):
        self.assertEqual(ig_publish._insight_values({"data": [
            {"name": "reach", "values": [{"value": 5}]}, {"name": "profile_views", "total_value": {"value": 4}},
            {"name": "bad", "values": [{"value": "x"}]}]}), {"reach": 5, "profile_views": 4})


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
    """docs/ig/: кожен пост — пара NN-слаг.jpg + .txt; без цін, у межах Instagram. «הדמיה» — лише в уже
    опублікованих 01–03 (їх не правимо); з 04 слова нема (слово власника 24.10: «не пиши, что это визуализация»)."""
    DIR = pathlib.Path(__file__).resolve().parents[1] / "docs" / "ig"

    def test_pairs_and_captions(self):
        captions = sorted(self.DIR.glob("*.txt"))
        self.assertEqual(len(captions), 5)
        for txt in captions:
            raw = txt.read_bytes()
            self.assertNotIn(b"\r", raw, txt.name)
            text = raw.decode("utf-8")
            ig_publish.check_caption(text)
            if txt.name[:2] in ("01", "02", "03"):
                self.assertIn("הדמיה", text, txt.name)
            else:
                self.assertNotIn("הדמיה", text, txt.name)
                self.assertIn("הפריט בייצור.", text, txt.name)
            self.assertNotRegex(text, r"₪|\bNIS\b|ש״ח|шек", txt.name)
            jpg = txt.with_suffix(".jpg")
            self.assertEqual(jpg.read_bytes()[:3], b"\xff\xd8\xff", jpg.name)


if __name__ == "__main__":
    unittest.main()
