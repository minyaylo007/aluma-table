"""scripts/next_version.py — наступний номер SemVer (research.md R5, contracts/workflows.md «release.yml»).

    python -m unittest tests.test_next_version -v
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import next_version as nv  # noqa: E402


class NextVersionTests(unittest.TestCase):
    def test_no_tags_gives_first_version(self):
        self.assertEqual(nv.next_version([], []), "v0.5.0")

    def test_patch_by_default(self):
        self.assertEqual(nv.next_version(["v0.5.3"], []), "v0.5.4")

    def test_minor_label(self):
        self.assertEqual(nv.next_version(["v0.5.3"], ["release:minor"]), "v0.6.0")

    def test_major_label(self):
        self.assertEqual(nv.next_version(["v0.5.3"], ["release:major"]), "v1.0.0")

    def test_both_labels_major_wins(self):
        self.assertEqual(nv.next_version(["v0.5.3"], ["release:minor", "release:major"]), "v1.0.0")

    def test_other_labels_ignored(self):
        self.assertEqual(nv.next_version(["v0.5.3"], ["docs", "release:minorish"]), "v0.5.4")

    def test_non_semver_tags_ignored(self):
        tags = ["v0.5.3", "0.9.0", "v1.0", "v2.0.0-rc1", "vX.Y.Z", "release-7", "v0.4.0-box"]
        self.assertEqual(nv.next_version(tags, []), "v0.5.4")

    def test_only_non_semver_tags_is_like_none(self):
        self.assertEqual(nv.next_version(["v0.4.0-box", "latest"], []), "v0.5.0")

    def test_numeric_not_lexical_order(self):
        self.assertEqual(nv.next_version(["v0.9.9", "v0.10.0", "v0.2.0"], []), "v0.10.1")

    def test_refs_prefix_accepted(self):
        self.assertEqual(nv.next_version(["refs/tags/v0.5.0", "refs/tags/v0.5.1^{}"], []), "v0.5.2")

    def test_cli(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "next_version.py"),
             "--tags", "v0.5.3\nv0.10.0", "--labels", "release:minor"],
            capture_output=True, text=True, check=True)
        self.assertEqual(proc.stdout, "v0.11.0\n")

    def test_cli_empty(self):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "next_version.py"),
                               "--tags", "", "--labels", ""], capture_output=True, text=True, check=True)
        self.assertEqual(proc.stdout, "v0.5.0\n")


if __name__ == "__main__":
    unittest.main()
