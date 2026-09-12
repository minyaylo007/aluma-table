"""scripts/release_build.py — відтворюваний архів релізу + SHA256SUMS (contracts/release-artifact.md).

Позитивні випадки збирають поточний коміт (HEAD) цього ж репозиторію: `git archive` читає базу об'єктів, клон
не потрібен (і працює на неглибокому checkout у CI). Заборонені шляхи — на крихітному синтетичному репозиторії:
відмова має статися ДО запуску build.py.

    python -m unittest tests.test_release_build -v
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_build.py"
TAG = "v0.0.1"

GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "Synthetic",
    "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
    "GIT_COMMITTER_NAME": "Synthetic",
    "GIT_COMMITTER_EMAIL": "synthetic@example.invalid",
}


def git(repo, *args) -> str:
    env = dict(os.environ, **GIT_ENV)
    return subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


def run_build(repo, sha, out, tag=TAG):
    env = dict(os.environ, **GIT_ENV)
    return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo), "--tag", tag, "--sha", sha,
                           "--out", str(out)], env=env, capture_output=True, text=True, timeout=600)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReleaseBuildTests(unittest.TestCase):
    """Одна пара збірок на весь клас — збірка займає секунди."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-release-test-"))
        cls.sha = git(ROOT, "rev-parse", "HEAD")
        cls.runs = []
        for n in (1, 2):
            out = cls.tmp / f"out{n}"
            cls.runs.append((run_build(ROOT, cls.sha, out), out))
        proc, out = cls.runs[0]
        cls.archive_bytes = (out / f"aluma-{TAG}.tar.gz").read_bytes() if proc.returncode == 0 else b""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        for proc, _ in self.runs:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def members(self):
        with tarfile.open(fileobj=io.BytesIO(self.archive_bytes), mode="r:gz") as tar:
            return {m.name: (m, tar.extractfile(m).read() if m.isfile() else None) for m in tar.getmembers()}

    def test_two_builds_are_byte_identical(self):
        a = (self.runs[0][1] / f"aluma-{TAG}.tar.gz").read_bytes()
        b = (self.runs[1][1] / f"aluma-{TAG}.tar.gz").read_bytes()
        self.assertEqual(sha256(a), sha256(b))
        self.assertEqual((self.runs[0][1] / "SHA256SUMS").read_bytes(), (self.runs[1][1] / "SHA256SUMS").read_bytes())

    def test_sha256sums_format(self):
        text = (self.runs[0][1] / "SHA256SUMS").read_text(encoding="utf-8")
        self.assertEqual(text, f"{sha256(self.archive_bytes)}  aluma-{TAG}.tar.gz\n")
        self.assertRegex(text, r"^[0-9a-f]{64}  \S+\n$")

    def test_only_the_two_release_files(self):
        self.assertEqual(sorted(p.name for p in self.runs[0][1].iterdir()), ["SHA256SUMS", f"aluma-{TAG}.tar.gz"])

    def test_archive_layout(self):
        names = self.members()
        prefix = f"aluma-{TAG}/"
        self.assertTrue(all(n.startswith(prefix) for n in names), [n for n in names if not n.startswith(prefix)][:3])
        for rel in ("api/handler.py", "build.py", "deploy/requirements-server.txt", "dist/index.html",
                    "RELEASE.json", "RELEASE.env", "MANIFEST.sha256"):
            self.assertIn(prefix + rel, names, rel)
        self.assertFalse([n for n in names if "/.build/" in n or "__pycache__" in n or n.endswith(".pyc")])

    def test_release_json_and_env(self):
        names = self.members()
        prefix = f"aluma-{TAG}/"
        info = json.loads(names[prefix + "RELEASE.json"][1])
        self.assertEqual(info["version"], TAG)
        self.assertEqual(info["git_sha"], self.sha)
        self.assertEqual(info["build_mode"], "preview")
        self.assertRegex(info["committed_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(names[prefix + "RELEASE.env"][1].decode(), f"APP_VERSION={TAG}\nGIT_SHA={self.sha}\n")

    def test_manifest_covers_every_file(self):
        names = self.members()
        prefix = f"aluma-{TAG}/"
        manifest = names[prefix + "MANIFEST.sha256"][1].decode()
        listed = {}
        for line in manifest.splitlines():
            m = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
            self.assertIsNotNone(m, line)
            listed[m.group(2)] = m.group(1)
        files = {n[len(prefix):]: data for n, (m, data) in names.items() if m.isfile()}
        files.pop("MANIFEST.sha256")
        self.assertEqual(set(listed), set(files))
        for rel, data in files.items():
            self.assertEqual(listed[rel], sha256(data), rel)
        self.assertEqual(list(listed), sorted(listed))

    def test_deterministic_headers(self):
        committed = int(git(ROOT, "show", "-s", "--format=%ct", self.sha))
        for name, (m, _) in self.members().items():
            self.assertEqual((m.uid, m.gid, m.uname, m.gname), (0, 0, "", ""), name)
            self.assertEqual(m.mtime, committed, name)
            if m.isfile():
                self.assertIn(m.mode, (0o644, 0o755), name)
        # gzip без імені файлу й часу
        self.assertEqual(self.archive_bytes[4:8], b"\x00\x00\x00\x00")
        self.assertFalse(self.archive_bytes[3] & 0x08, "FNAME у заголовку gzip")

    def test_no_forbidden_paths(self):
        for name in self.members():
            rel = name.split("/", 1)[1]
            self.assertFalse(re.match(r"(data/|dump|node_modules/|ms-playwright/|\.venv/)", rel), rel)
            self.assertFalse(rel.endswith(".db"), rel)
            self.assertNotEqual(rel, "infra/samconfig.toml")


class ReleaseBuildRefusalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-release-refuse-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        # build.py, що впав би гучно, — відмова має бути раніше
        (self.repo / "build.py").write_text("raise SystemExit('build.py must not run')\n", encoding="utf-8")
        git(self.repo, "add", "build.py")
        git(self.repo, "commit", "-q", "-m", "init")
        self.out = self.tmp / "out"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def commit_file(self, rel):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"synthetic\x00")
        git(self.repo, "add", "-f", rel)
        git(self.repo, "commit", "-q", "-m", "add " + rel)
        return git(self.repo, "rev-parse", "HEAD")

    def assert_refused(self, rel):
        sha = self.commit_file(rel)
        proc = run_build(self.repo, sha, self.out)
        self.assertNotEqual(proc.returncode, 0, rel)
        self.assertIn(rel, proc.stdout + proc.stderr)
        self.assertNotIn("build.py must not run", proc.stdout + proc.stderr)
        self.assertFalse(self.out.exists() and any(self.out.iterdir()), rel)

    def test_tracked_db_refused(self):
        self.assert_refused("data/x.db")

    def test_dump_refused(self):
        self.assert_refused("dump/leads.jsonl")

    def test_env_refused(self):
        self.assert_refused("deploy/.env")

    def test_samconfig_refused(self):
        self.assert_refused("infra/samconfig.toml")

    def test_bad_tag_and_sha(self):
        sha = git(self.repo, "rev-parse", "HEAD")
        for tag, s in (("0.5.0", sha), ("v0.5", sha), (TAG, "abc"), (TAG, "f" * 40)):
            proc = run_build(self.repo, s, self.out, tag=tag)
            self.assertEqual(proc.returncode, 2, (tag, s))


if __name__ == "__main__":
    unittest.main()
