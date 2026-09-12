"""deploy/agent/pullagent.py — агент деплою без облікових даних (contracts/agent-cli.md, production-ref.md,
release-artifact.md, data-model.md «Переходи агента»).

Без мережі й без systemd: git, HTTP, systemctl, rsync і venv підміняє світ-підробка (`World`), усе живе у
тимчасовій теці. Синтетичні релізи збирає той самий код, що й scripts/release_build.py (finalize + make_archive),
тож агент перевіряється рівно на форматі, який публікує конвеєр.

    python -m unittest tests.test_pull_agent -v
"""

from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import release_build as rb  # noqa: E402

AGENT_PATH = ROOT / "deploy" / "agent" / "pullagent.py"
_spec = importlib.util.spec_from_file_location("pullagent", AGENT_PATH)
pa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pa)

REPO = "https://github.com/minyaylo007/aluma-table"
HEALTH = "http://127.0.0.1:8005/api/fx/health"
RSYNC_FLAGS = ["-a", "--delete-after", "--delay-updates", "--chmod=D0755,F0644"]


def sha_of(n: int) -> str:
    return hashlib.sha1(str(n).encode()).hexdigest()


class World:
    """Підробка всього зовнішнього світу агента."""

    def __init__(self, tmp: pathlib.Path, keep=10):
        self.tmp = tmp
        self.base = tmp / "opt" / "aluma-table"
        self.static = tmp / "srv" / "aluma"
        self.units_home = tmp / "home" / ".config" / "systemd" / "user"
        self.base.mkdir(parents=True)
        self.static.mkdir(parents=True)
        self.units_home.mkdir(parents=True)
        self.keep = keep
        self.refs = {}                 # ім'я посилання → sha (рядки ls-remote)
        self.assets = {}               # url → байти
        self.calls = []                # (argv, env, cwd)
        self.fetches = []              # (url, headers)
        self.running = None            # (tag, sha), що «віддає» сервіс після restart
        self.health_broken = set()     # теги, на яких сервіс не відповідає правильно
        self.ls_remote_fail = False
        self.unreadable_after_rsync = None
        self.clock = 1_000_000.0

    # ── підміни ────────────────────────────────────────────────────────────────
    def runner(self, argv, env=None, cwd=None):
        self.calls.append((list(argv), dict(env) if env is not None else None, cwd))
        ok = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        prog = pathlib.Path(argv[0]).name
        if prog == "git":
            if self.ls_remote_fail:
                return types.SimpleNamespace(returncode=128, stdout="", stderr="fatal: unable to access")
            ok.stdout = "".join(f"{sha}\t{ref}\n" for ref, sha in self.refs.items())
            return ok
        if prog == "systemctl":
            if argv[1:3] == ["--user", "restart"]:
                cur = self.base / "current"
                env_file = (cur / "RELEASE.env").read_text() if cur.exists() else ""
                vals = dict(line.split("=", 1) for line in env_file.split())
                self.running = (vals.get("APP_VERSION"), vals.get("GIT_SHA"))
            return ok
        if prog == "rsync":
            src, dst = pathlib.Path(argv[-2]), pathlib.Path(argv[-1])
            for child in dst.iterdir():
                shutil.rmtree(child) if child.is_dir() else child.unlink()
            shutil.copytree(src, dst, dirs_exist_ok=True)
            for p in dst.rglob("*"):
                p.chmod(0o755 if p.is_dir() else 0o644)
            if self.unreadable_after_rsync:
                # лише один раз: повторна публікація (відкат) уже чиста
                (dst / self.unreadable_after_rsync).chmod(0o600)
                self.unreadable_after_rsync = None
            return ok
        if argv[1:3] == ["-m", "venv"]:
            (pathlib.Path(argv[3]) / "bin").mkdir(parents=True)
            return ok
        if prog == "pip" or argv[-3:-1] == ["install", "-r"] or "install" in argv:
            return ok
        raise AssertionError(f"неочікувана команда: {argv}")

    def fetch(self, url, headers=None, timeout=None):
        self.fetches.append((url, dict(headers or {})))
        if url == HEALTH:
            if self.running is None:
                raise pa.FetchError("connection refused")
            tag, sha = self.running
            if tag in self.health_broken:
                return json.dumps({"ok": True, "version": "0.4.0-box", "git_sha": None}).encode()
            return json.dumps({"ok": True, "version": tag, "git_sha": sha, "ts": "x"}).encode()
        if url not in self.assets:
            raise pa.FetchError("404")
        return self.assets[url]

    def sleep(self, seconds):
        self.clock += seconds

    def now(self):
        return self.clock

    # ── релізи ─────────────────────────────────────────────────────────────────
    def config(self, **over):
        cfg = {"repo_url": REPO, "ref": "refs/heads/production", "tag_glob": "refs/tags/v*",
               "asset_name": "aluma-{tag}.tar.gz", "base_dir": str(self.base), "keep_releases": self.keep,
               "requirements": "deploy/requirements-server.txt", "units_dir": "deploy/systemd/user",
               "restart_unit": "ihor-aluma-api.service", "health_url": HEALTH, "health_timeout_s": 60,
               "static_src": "dist/", "static_dst": str(self.static) + "/", "rsync_flags": RSYNC_FLAGS}
        cfg.update(over)
        return cfg

    def agent(self, **over):
        self.out = io.StringIO()
        with mock.patch.object(pa, "ALLOWED_BASE_DIRS", (str(self.tmp) + "/",)), \
                mock.patch.object(pa, "ALLOWED_STATIC_DIRS", (str(self.tmp) + "/",)):
            return pa.Agent(self.config(**over), runner=self.runner, fetch=self.fetch, sleep=self.sleep,
                            now=self.now, units_home=self.units_home, out=self.out)

    def release_files(self, tag, extra=None):
        files = {
            "api/handler.py": (f"# handler {tag}\n".encode(), 0o644, None),
            "deploy/requirements-server.txt": (b"gunicorn==26.2.0\n", 0o644, None),
            "deploy/systemd/user/ihor-aluma-api.service": (b"[Service]\nExecStart=x\n", 0o644, None),
            "dist/index.html": (f"<html>{tag}</html>\n".encode(), 0o644, None),
            "dist/assets/app.js": (f"var v='{tag}';\n".encode(), 0o644, None),
        }
        files.update(extra or {})
        return files

    def publish(self, tag, sha, annotated=False, extra=None, tamper=None):
        files = rb.finalize(tag, sha, "2026-09-12T10:00:00Z", self.release_files(tag, extra))
        if tamper:
            files[tamper] = (b"tampered\n", 0o644, None)
        archive = rb.make_archive(tag, sha, 1_788_000_000, files)
        name = f"aluma-{tag}.tar.gz"
        self.assets[f"{REPO}/releases/download/{tag}/{name}"] = archive
        self.assets[f"{REPO}/releases/download/{tag}/SHA256SUMS"] = \
            f"{hashlib.sha256(archive).hexdigest()}  {name}\n".encode()
        if annotated:
            self.refs[f"refs/tags/{tag}"] = sha_of(hash(tag))
            self.refs[f"refs/tags/{tag}^{{}}"] = sha
        else:
            self.refs[f"refs/tags/{tag}"] = sha
        return archive

    def point(self, sha):
        self.refs["refs/heads/production"] = sha

    def cycle(self, dry_run=False, **over):
        agent = self.agent(**over)
        with mock.patch.object(pa, "ALLOWED_BASE_DIRS", (str(self.tmp) + "/",)), \
                mock.patch.object(pa, "ALLOWED_STATIC_DIRS", (str(self.tmp) + "/",)):
            return agent.once(dry_run=dry_run)

    # ── спостереження ─────────────────────────────────────────────────────────
    def state(self):
        return json.loads((self.base / "state" / "state.json").read_text())

    def failed(self):
        p = self.base / "state" / "failed.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def current_tag(self):
        cur = self.base / "current"
        return os.readlink(cur).rsplit("/", 1)[-1] if cur.is_symlink() else None

    def events(self):
        log = self.base / "state" / "deploy.log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def last_event(self):
        return self.events()[-1]

    def restarts(self):
        return [c for c in self.calls if pathlib.Path(c[0][0]).name == "systemctl" and "restart" in c[0]]

    def rsyncs(self):
        return [c for c in self.calls if pathlib.Path(c[0][0]).name == "rsync"]


class AgentTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-agent-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w = World(self.tmp)

    def install(self, tag="v0.5.0", n=0, **kw):
        self.w.publish(tag, sha_of(n), **kw)
        self.w.point(sha_of(n))
        code = self.w.cycle()
        self.assertEqual(code, 0, self.w.out.getvalue())
        return code


class InstallTests(AgentTestCase):
    def test_b_new_version_full_path(self):
        self.install("v0.5.0", 0)
        w = self.w
        self.assertEqual(w.current_tag(), "v0.5.0")
        self.assertTrue((w.base / "releases" / "v0.5.0" / "dist" / "index.html").exists())
        # суми завантажено: спершу SHA256SUMS, потім архів
        urls = [u for u, _ in w.fetches if u != HEALTH]
        self.assertEqual(urls, [f"{REPO}/releases/download/v0.5.0/SHA256SUMS",
                                f"{REPO}/releases/download/v0.5.0/aluma-v0.5.0.tar.gz"])
        self.assertEqual([c[0] for c in w.restarts()], [["systemctl", "--user", "restart", "ihor-aluma-api.service"]])
        rs = w.rsyncs()
        self.assertEqual(len(rs), 1)
        self.assertEqual(rs[0][0][1:-2], RSYNC_FLAGS)
        self.assertTrue(rs[0][0][-2].endswith("/releases/v0.5.0/dist/"))
        self.assertEqual(rs[0][0][-1], str(w.static) + "/")
        self.assertEqual((w.static / "index.html").read_text(), "<html>v0.5.0</html>\n")
        st = w.state()
        self.assertEqual(st["current"], {"tag": "v0.5.0", "git_sha": sha_of(0)})
        self.assertIsNone(st["previous"])
        ev = w.last_event()
        self.assertEqual((ev["event"], ev["result"], ev["trigger"]), ("deploy_done", "ok", "production_ref"))
        self.assertEqual(ev["to"], {"tag": "v0.5.0", "sha": sha_of(0)[:7]})
        self.assertRegex(w.out.getvalue(), r"→ v0\.5\.0: ok \(\d+ s\)")
        # venv за хешем вимог і посилання .venv у каталозі версії
        venv_link = w.base / "releases" / "v0.5.0" / ".venv"
        self.assertTrue(venv_link.is_symlink())
        self.assertRegex(os.readlink(venv_link), r"^\.\./\.\./venvs/[0-9a-f]{12}$")
        # юніти версії скопійовано в менеджер користувача, daemon-reload викликано
        self.assertTrue((w.units_home / "ihor-aluma-api.service").exists())
        self.assertIn(["systemctl", "--user", "daemon-reload"], [c[0] for c in w.calls])

    def test_b_second_version_keeps_previous(self):
        self.install("v0.5.0", 0)
        self.w.publish("v0.5.1", sha_of(1))
        self.w.point(sha_of(1))
        self.assertEqual(self.w.cycle(), 0)
        st = self.w.state()
        self.assertEqual(st["current"]["tag"], "v0.5.1")
        self.assertEqual(st["previous"], {"tag": "v0.5.0", "git_sha": sha_of(0)})
        self.assertEqual(self.w.last_event()["from"], {"tag": "v0.5.0", "sha": sha_of(0)[:7]})

    def test_b_static_not_world_readable_is_a_failure(self):
        self.install("v0.5.0", 0)
        self.w.publish("v0.5.1", sha_of(1))
        self.w.point(sha_of(1))
        self.w.unreadable_after_rsync = "index.html"
        code = self.w.cycle()
        self.assertEqual(code, 1)
        self.assertEqual(self.w.current_tag(), "v0.5.0")
        self.assertIn("static_verify", json.dumps(self.w.failed()))

    def test_a_unchanged_does_nothing(self):
        self.install("v0.5.0", 0)
        before = len(self.w.fetches), len(self.w.calls)
        self.assertEqual(self.w.cycle(), 0)
        self.assertEqual(self.w.last_event()["event"], "unchanged")
        self.assertEqual(len(self.w.fetches), before[0])
        # лише ls-remote
        self.assertEqual([pathlib.Path(c[0][0]).name for c in self.w.calls[before[1]:]], ["git"])

    def test_no_production_ref_does_nothing(self):
        self.w.publish("v0.5.0", sha_of(0))
        self.assertEqual(self.w.cycle(), 0)
        self.assertEqual(self.w.last_event()["event"], "unchanged")
        self.assertIsNone(self.w.current_tag())

    def test_annotated_tag_is_peeled(self):
        self.install("v0.5.0", 0, annotated=True)
        self.assertEqual(self.w.current_tag(), "v0.5.0")

    def test_highest_semver_tag_on_same_sha(self):
        self.w.publish("v0.9.0", sha_of(0))
        self.w.publish("v0.10.0", sha_of(0))
        self.w.point(sha_of(0))
        self.assertEqual(self.w.cycle(), 0)
        self.assertEqual(self.w.current_tag(), "v0.10.0")

    def test_rollback_to_kept_version_needs_no_download(self):
        self.install("v0.5.0", 0)
        self.w.publish("v0.5.1", sha_of(1))
        self.w.point(sha_of(1))
        self.assertEqual(self.w.cycle(), 0)
        n = len([u for u, _ in self.w.fetches if u != HEALTH])
        self.w.point(sha_of(0))
        self.assertEqual(self.w.cycle(), 0)
        self.assertEqual(self.w.current_tag(), "v0.5.0")
        self.assertEqual(len([u for u, _ in self.w.fetches if u != HEALTH]), n)
        self.assertEqual((self.w.static / "index.html").read_text(), "<html>v0.5.0</html>\n")


class RefusalTests(AgentTestCase):
    def test_c_checksum_mismatch(self):
        self.install("v0.5.0", 0)
        self.w.publish("v0.5.1", sha_of(1))
        self.w.assets[f"{REPO}/releases/download/v0.5.1/SHA256SUMS"] = b"0" * 64 + b"  aluma-v0.5.1.tar.gz\n"
        self.w.point(sha_of(1))
        self.assertEqual(self.w.cycle(), 3)
        self.assertEqual(self.w.current_tag(), "v0.5.0")
        self.assertEqual((self.w.last_event()["event"], self.w.last_event()["reason"]), ("refused", "checksum"))
        self.assertFalse((self.w.base / "releases" / "v0.5.1").exists())

    def test_c_manifest_mismatch(self):
        self.install("v0.5.0", 0)
        self.w.publish("v0.5.1", sha_of(1), tamper="dist/index.html")
        self.w.point(sha_of(1))
        self.assertEqual(self.w.cycle(), 3)
        self.assertEqual(self.w.last_event()["reason"], "checksum")
        self.assertEqual(self.w.current_tag(), "v0.5.0")

    def test_c_release_json_must_match_ref(self):
        self.install("v0.5.0", 0)
        # архів v0.5.1 зібраний для іншого sha
        self.w.publish("v0.5.1", sha_of(99))
        self.w.refs["refs/tags/v0.5.1"] = sha_of(1)
        self.w.point(sha_of(1))
        self.assertEqual(self.w.cycle(), 3)
        self.assertEqual(self.w.last_event()["reason"], "checksum")

    def test_c_missing_release_file_is_source_problem_not_install(self):
        self.install("v0.5.0", 0)
        self.w.refs["refs/tags/v0.5.1"] = sha_of(1)
        self.w.point(sha_of(1))
        self.assertIn(self.w.cycle(), (3, 4))
        self.assertEqual(self.w.current_tag(), "v0.5.0")

    def test_e_dirty_current_refuses(self):
        self.install("v0.5.0", 0)
        (self.w.base / "releases" / "v0.5.0" / "api" / "handler.py").write_text("# hand edit\n")
        self.w.publish("v0.5.1", sha_of(1))
        self.w.point(sha_of(1))
        self.assertEqual(self.w.cycle(), 3)
        ev = self.w.last_event()
        self.assertEqual((ev["event"], ev["reason"]), ("refused", "dirty_current"))
        self.assertIn("api/handler.py", ev.get("paths", []))
        self.assertEqual(self.w.current_tag(), "v0.5.0")

    def test_f_no_release_tag(self):
        self.install("v0.5.0", 0)
        self.w.point(sha_of(7))
        self.assertEqual(self.w.cycle(), 3)
        self.assertEqual(self.w.last_event()["reason"], "no_release_tag")
        self.assertEqual(self.w.current_tag(), "v0.5.0")

    def test_g_dry_run_changes_nothing(self):
        self.install("v0.5.0", 0)
        restarts = len(self.w.restarts())
        self.w.publish("v0.5.1", sha_of(1))
        self.w.point(sha_of(1))
        self.assertEqual(self.w.cycle(dry_run=True), 0)
        self.assertEqual(self.w.current_tag(), "v0.5.0")
        self.assertEqual(len(self.w.restarts()), restarts)
        self.assertEqual(self.w.state()["current"]["tag"], "v0.5.0")
        self.assertEqual(self.w.last_event()["event"], "dry_run")
        self.assertIn("v0.5.0 → v0.5.1", self.w.out.getvalue())
        self.assertFalse((self.w.base / "releases" / "v0.5.1").exists())

    def test_h_lock_busy(self):
        self.install("v0.5.0", 0)
        with open(self.w.base / "state" / "agent.lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.w.cycle(), 5)
        self.assertEqual(self.w.last_event()["event"], "lock_busy")

    def test_source_unavailable_backs_off(self):
        self.install("v0.5.0", 0)
        self.w.ls_remote_fail = True
        self.assertEqual(self.w.cycle(), 4)
        self.assertEqual(self.w.last_event()["event"], "source_unavailable")
        gits = len([c for c in self.w.calls if c[0][0] == "git"])
        self.w.clock += 30
        self.assertEqual(self.w.cycle(), 4)      # у межах паузи — git не кличеться
        self.assertEqual(len([c for c in self.w.calls if c[0][0] == "git"]), gits)
        self.w.ls_remote_fail = False
        self.w.clock += 700
        self.assertEqual(self.w.cycle(), 0)
        self.assertEqual(self.w.current_tag(), "v0.5.0")


class RevertTests(AgentTestCase):
    def test_d_local_health_timeout_reverts_and_remembers(self):
        self.install("v0.5.0", 0)
        self.w.publish("v0.5.1", sha_of(1),
                       extra={"deploy/systemd/user/ihor-aluma-api.service": (b"[Service]\nExecStart=new\n", 0o644, None)})
        self.w.health_broken.add("v0.5.1")
        self.w.point(sha_of(1))
        self.assertEqual(self.w.cycle(), 1)
        self.assertEqual(self.w.current_tag(), "v0.5.0")
        self.assertEqual(self.w.running, ("v0.5.0", sha_of(0)))
        # статика прежньої версії опублікована ще раз, юніти повернуто
        self.assertEqual((self.w.static / "index.html").read_text(), "<html>v0.5.0</html>\n")
        self.assertEqual((self.w.units_home / "ihor-aluma-api.service").read_bytes(), b"[Service]\nExecStart=x\n")
        self.assertEqual(self.w.failed()[sha_of(1)]["reason"], "local_health_timeout")
        self.assertEqual(self.w.state()["current"]["tag"], "v0.5.0")
        self.assertEqual(self.w.last_event()["event"], "revert_done")
        # повторний цикл із тим самим sha — нічого не ставить
        fetches = len(self.w.fetches)
        self.assertEqual(self.w.cycle(), 0)
        self.assertEqual(self.w.last_event()["event"], "unchanged")
        self.assertEqual(len(self.w.fetches), fetches)

    def test_failed_mark_cleared_when_ref_moves_on(self):
        self.test_d_local_health_timeout_reverts_and_remembers()
        self.w.point(sha_of(0))
        self.assertEqual(self.w.cycle(), 0)
        self.assertEqual(self.w.failed(), {})

    def test_revert_failure_is_code_2(self):
        self.install("v0.5.0", 0)
        self.w.publish("v0.5.1", sha_of(1))
        self.w.point(sha_of(1))
        self.w.health_broken.update({"v0.5.0", "v0.5.1"})
        self.assertEqual(self.w.cycle(), 2)
        self.assertEqual(self.w.last_event()["event"], "revert_failed")
        self.assertIn(sha_of(1), self.w.failed())

    def test_i_interrupted_after_switch_is_finished(self):
        self.install("v0.5.0", 0)
        self.w.publish("v0.5.1", sha_of(1))
        self.w.point(sha_of(1))
        # «перезавантаження посеред установки»: v0.5.1 розпакована і current уже на ній, state — ще на v0.5.0
        self.w.cycle(dry_run=True)
        rel = self.w.base / "releases" / "v0.5.1"
        archive = self.w.assets[f"{REPO}/releases/download/v0.5.1/aluma-v0.5.1.tar.gz"]
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(self.w.tmp / "x", filter="data")
        shutil.move(str(self.w.tmp / "x" / "aluma-v0.5.1"), str(rel))
        os.symlink("../../venvs/" + os.readlink(self.w.base / "releases" / "v0.5.0" / ".venv").rsplit("/", 1)[-1],
                   rel / ".venv")
        (self.w.base / "current").unlink()
        os.symlink("releases/v0.5.1", self.w.base / "current")
        self.assertEqual(self.w.cycle(), 0)
        self.assertEqual(self.w.state()["current"]["tag"], "v0.5.1")
        self.assertEqual(self.w.running, ("v0.5.1", sha_of(1)))
        self.assertEqual((self.w.static / "index.html").read_text(), "<html>v0.5.1</html>\n")


class HousekeepingTests(AgentTestCase):
    def test_o_keeps_limited_releases_but_never_current_or_previous(self):
        self.w.keep = 3
        for n in range(5):
            self.w.publish(f"v0.5.{n}", sha_of(n))
            self.w.point(sha_of(n))
            self.assertEqual(self.w.cycle(), 0)
        kept = sorted(p.name for p in (self.w.base / "releases").iterdir() if not p.name.startswith("."))
        self.assertEqual(kept, ["v0.5.2", "v0.5.3", "v0.5.4"])
        # відкат на старішу за previous — теж дозволений, і previous не видаляється
        self.w.point(sha_of(3))
        self.assertEqual(self.w.cycle(), 0)
        kept = sorted(p.name for p in (self.w.base / "releases").iterdir() if not p.name.startswith("."))
        self.assertIn("v0.5.4", kept)
        self.assertIn("v0.5.3", kept)
        self.assertLessEqual(len(kept), 3)

    def test_status(self):
        self.install("v0.5.0", 0)
        agent = self.w.agent()
        self.assertEqual(agent.status(), 0)
        out = self.w.out.getvalue()
        self.assertIn('"v0.5.0"', out)
        self.assertIn("deploy_done", out)


class SafetyTests(AgentTestCase):
    def test_j_no_credentials_and_no_rest_api(self):
        self.install("v0.5.0", 0)
        self.w.publish("v0.5.1", sha_of(1))
        self.w.point(sha_of(1))
        self.w.cycle()
        self.assertTrue(self.w.fetches)
        for url, headers in self.w.fetches:
            self.assertNotIn("authorization", {k.lower() for k in headers}, url)
            host = url.split("/")[2]
            self.assertIn(host, ("github.com", "127.0.0.1:8005"), url)
            self.assertNotIn("api.github.com", url)

    def test_j_redirect_policy(self):
        for ok in ("https://github.com/x", "https://objects.githubusercontent.com/y",
                   "https://release-assets.githubusercontent.com/z"):
            self.assertTrue(pa.redirect_allowed(ok), ok)
        for bad in ("https://api.github.com/repos/x", "http://github.com/x", "https://evil.example/x",
                    "https://github.com.evil.example/x", "https://user:pw@github.com/x"):
            self.assertFalse(pa.redirect_allowed(bad), bad)

    def test_k_git_is_isolated(self):
        with mock.patch.dict(os.environ, {"GH_TOKEN": "gho_fake", "GITHUB_TOKEN": "fake", "GIT_ASKPASS": "x"}):
            self.install("v0.5.0", 0)
        gits = [c for c in self.w.calls if c[0][0] == "git"]
        self.assertTrue(gits)
        for argv, env, _ in gits:
            self.assertEqual(argv[:6], ["git", "-c", "credential.helper=", "-c", "protocol.version=2", "ls-remote"])
            self.assertEqual(argv[6], REPO)
            self.assertEqual(argv[7:], ["refs/heads/production", "refs/tags/v*"])
            self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
            self.assertEqual(env["GIT_CONFIG_GLOBAL"], "/dev/null")
            self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
            self.assertEqual(env["GIT_ASKPASS"], "/bin/false")
            for leaked in ("GH_TOKEN", "GITHUB_TOKEN"):
                self.assertNotIn(leaked, env)

    def test_l_source_has_no_forbidden_calls(self):
        src = AGENT_PATH.read_text(encoding="utf-8")
        for bad in ("sudo", "caddy", "2019", ".bind(", ".listen(", "api.github.com", "aluma.env", "Authorization"):
            self.assertNotIn(bad, src, bad)

    def test_m_bad_config_refuses_to_start(self):
        bad = [
            {"health_url": "http://10.0.0.1:8005/api/fx/health"},
            {"health_url": "https://127.0.0.1.evil.example/api"},
            {"base_dir": "/etc/aluma"},
            {"static_dst": "/var/www/"},
            {"repo_url": "https://gitlab.com/x/y"},
            {"repo_url": "https://user:token@github.com/minyaylo007/aluma-table"},
            {"restart_unit": "caddy.service".replace("caddy", "nginx")},
            {"keep_releases": 1},
        ]
        for over in bad:
            with self.assertRaises(pa.ConfigError, msg=str(over)):
                self.w.agent(**over)
        # з типовими дозволеними шляхами тимчасова тека теж заборонена
        with self.assertRaises(pa.ConfigError):
            pa.Agent(self.w.config(), runner=self.w.runner, fetch=self.w.fetch)

    def test_n_log_has_no_env_or_bodies(self):
        with mock.patch.dict(os.environ, {"SOME_SECRET": "s3cr3t-value-xyz"}):
            self.install("v0.5.0", 0)
            self.w.publish("v0.5.1", sha_of(1))
            self.w.health_broken.add("v0.5.1")
            self.w.point(sha_of(1))
            self.w.cycle()
        log = (self.w.base / "state" / "deploy.log").read_text()
        self.assertNotIn("s3cr3t-value-xyz", log + self.w.out.getvalue())
        self.assertNotIn("0.4.0-box", log)          # тіло відповіді health не потрапляє в журнал
        allowed = {"event", "at", "trigger", "from", "to", "result", "secs", "reason", "paths"}
        for ev in self.w.events():
            self.assertLessEqual(set(ev), allowed, ev)
            self.assertLessEqual(len(ev.get("reason", "")), 200)

    def test_p_never_touches_data_or_secrets(self):
        data = self.w.base / "data"
        data.mkdir()
        db = data / "aluma.db"
        db.write_bytes(b"live")
        env = self.w.tmp / "home" / ".config" / "aluma" / "aluma.env"
        env.parent.mkdir(parents=True)
        env.write_text("X=1\n")
        for p in (db, env):
            p.chmod(0o400)
        data.chmod(0o500)
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (db, env)}
        try:
            self.install("v0.5.0", 0)
            self.w.publish("v0.5.1", sha_of(1))
            self.w.health_broken.add("v0.5.1")
            self.w.point(sha_of(1))
            self.w.cycle()                        # установка + відкат
            for n in range(2, 5):                 # і прибирання старих версій
                self.w.publish(f"v0.5.{n}", sha_of(n))
                self.w.point(sha_of(n))
                self.w.cycle()
        finally:
            data.chmod(0o700)
        for p, (content, mtime) in before.items():
            self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns), (content, mtime), p)
        self.assertEqual(sorted(x.name for x in data.iterdir()), ["aluma.db"])

    def test_state_dir_is_private(self):
        self.install("v0.5.0", 0)
        mode = stat.S_IMODE((self.w.base / "state").stat().st_mode)
        self.assertEqual(mode, 0o700)


if __name__ == "__main__":
    unittest.main()
