"""build.py gives the same bytes on every OS.

Prod of 09.09 was built on Windows: text-mode writes turned "\\n" into "\\r\\n", and a Windows checkout
(core.autocrlf) handed copytree CRLF sources. Every page, and the content hash of every CSS/JS/SVG,
then differed from a Linux build of the same commit.

Windows is simulated on any machine by doing the two things Windows does:
  * io.open / builtins.open in a text write mode with newline=None write "\\r\\n" (what CPython does
    on Windows; os.linesep cannot be patched for that — the C io layer decides at compile time);
  * the text sources in the working tree are CRLF (what core.autocrlf=true checks out).

Every build runs in a temporary copy of build.py + site/ + i18n/ + content.json; the project's own
dist/ and .build/ are never touched.
"""

from __future__ import annotations

import builtins
import contextlib
import importlib.util
import io
import itertools
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = pathlib.Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = (".html", ".css", ".js", ".svg", ".xml", ".txt", ".webmanifest", ".json")
_real_open = io.open
_counter = itertools.count()


def _windows_open(file, mode="r", buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
    if newline is None and "b" not in mode and any(c in mode for c in "wax+"):
        newline = "\r\n"
    return _real_open(file, mode, buffering, encoding, errors, newline, closefd, opener)


@contextlib.contextmanager
def windows():
    with mock.patch.object(io, "open", _windows_open), mock.patch.object(builtins, "open", _windows_open):
        yield


def is_text(f: pathlib.Path) -> bool:
    # extensionless files are the pretty-URL copies of pages (next, privacy, en/404, ...)
    return f.suffix.lower() in TEXT_SUFFIXES or f.suffix == ""


def make_tree(dst: pathlib.Path, crlf_sources: bool) -> pathlib.Path:
    for name in ("build.py", "content.json"):
        shutil.copy2(PROJECT / name, dst / name)
    for name in ("site", "i18n"):
        shutil.copytree(PROJECT / name, dst / name)
    if crlf_sources:
        for f in [dst / "content.json", *(dst / "site").rglob("*"), *(dst / "i18n").rglob("*")]:
            if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES:
                data = f.read_bytes().replace(b"\r\n", b"\n")
                f.write_bytes(data.replace(b"\n", b"\r\n"))
    return dst


def run_build(tree: pathlib.Path, as_windows: bool) -> pathlib.Path:
    spec = importlib.util.spec_from_file_location(f"build_under_test_{next(_counter)}", tree / "build.py")
    module = importlib.util.module_from_spec(spec)
    with contextlib.ExitStack() as stack:
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        stack.enter_context(mock.patch.object(sys, "argv", ["build.py"]))
        if as_windows:
            stack.enter_context(windows())
        spec.loader.exec_module(module)
        module.main()
    return tree / "dist"


def snapshot(dist: pathlib.Path) -> dict:
    return {f.relative_to(dist).as_posix(): f.read_bytes() for f in sorted(dist.rglob("*")) if f.is_file()}


class BuildEolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-build-eol-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def build(self, name: str, as_windows: bool) -> pathlib.Path:
        tree = self.tmp / name
        tree.mkdir()
        make_tree(tree, crlf_sources=as_windows)
        return run_build(tree, as_windows)

    def test_simulation_really_writes_crlf(self):
        # guards the other tests against passing vacuously: the patched open must behave like Windows
        f = self.tmp / "probe.txt"
        with windows():
            f.write_text("a\nb\n", encoding="utf-8")
        self.assertEqual(f.read_bytes(), b"a\r\nb\r\n")
        f.write_text("a\nb\n", encoding="utf-8")
        self.assertEqual(f.read_bytes(), b"a\nb\n")

    def test_windows_build_has_no_cr_in_any_text_file(self):
        dist = self.build("win", as_windows=True)
        texts = [f for f in sorted(dist.rglob("*")) if f.is_file() and is_text(f)]
        self.assertGreater(len(texts), 20, "the build published suspiciously few text files")
        suffixes = {f.suffix.lower() for f in texts}
        for s in (".html", ".css", ".js", ".svg", ".xml", ".txt", ""):
            self.assertIn(s, suffixes, f"no {s or 'extensionless'} file in the build — the check would be blind to it")
        with_cr = [f.relative_to(dist).as_posix() for f in texts if b"\r" in f.read_bytes()]
        self.assertEqual(with_cr, [], f"CR in {len(with_cr)} text files of a Windows build")
        asset_map = dist.parent / ".build" / "asset-map.json"
        self.assertNotIn(b"\r", asset_map.read_bytes())

    def test_windows_build_is_byte_identical_to_linux_build(self):
        win = snapshot(self.build("win", as_windows=True))
        lin = snapshot(self.build("lin", as_windows=False))
        self.assertEqual(sorted(win), sorted(lin), "file names differ, i.e. content hashes differ")
        differ = [p for p in lin if win[p] != lin[p]]
        self.assertEqual(differ, [])

    def test_two_builds_are_byte_identical(self):
        a = snapshot(self.build("a", as_windows=False))
        b = snapshot(self.build("b", as_windows=False))
        self.assertEqual(sorted(a), sorted(b))
        self.assertEqual([p for p in a if a[p] != b[p]], [])


if __name__ == "__main__":
    unittest.main()
