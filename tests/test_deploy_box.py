"""scripts/deploy-box.sh — викат на прод і відкат тією самою командою: інваріанти без запуску на проді.

Скрипт перевіряється статично (bash -n + текст) і на порожньому стенді з підміненими шляхами: справжній
клон, /srv/aluma, юніт і порт 8005 тут не чіпаються. Чого скрипт НЕ сміє: Caddy, pkill, чужі юніти,
rsync без --chmod (deploy/README.md — пастка з 403).
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "deploy-box.sh"
TEXT = SCRIPT.read_text(encoding="utf-8")


class DeployBoxTextTests(unittest.TestCase):
    def test_executable_strict_and_parses(self) -> None:
        self.assertTrue(SCRIPT.stat().st_mode & stat.S_IXUSR, "скрипт має бути виконуваним")
        self.assertTrue(TEXT.startswith("#!/bin/bash\n"))
        self.assertIn("set -euo pipefail", TEXT)
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_touches_only_own_unit_and_never_caddy_or_names(self) -> None:
        # Перезапуск — лише власного user-юніта, через змінну UNIT (типово ihor-aluma-api.service).
        restarts = re.findall(r"systemctl\s+--user\s+restart\s+(\S+)", TEXT)
        self.assertEqual(restarts, ['"$UNIT"'])
        self.assertIn('UNIT="${ALUMA_UNIT:-ihor-aluma-api.service}"', TEXT)
        for forbidden in ("caddy", "2019", "pkill", "killall", "systemctl restart", "systemctl stop", "sudo "):
            code_lines = [ln for ln in TEXT.splitlines() if not ln.lstrip().startswith("#")]
            self.assertFalse(
                any(forbidden in ln for ln in code_lines), f"у коді скрипта не може бути «{forbidden}»"
            )

    def test_health_gets_git_sha_from_own_dropin(self) -> None:
        # git_sha у health був null: юніт на ящику не мав GIT_SHA; drop-in лише для свого юніта
        self.assertIn('DROPIN_DIR="${ALUMA_DROPIN_DIR:-$HOME/.config/systemd/user/$UNIT.d}"', TEXT)
        self.assertIn("printf 'GIT_SHA=%s\\n'", TEXT)
        self.assertLess(TEXT.index('mark_release "$(git'), TEXT.index('systemctl --user restart "$UNIT"'))

    def test_static_is_published_with_chmod_and_trailing_slash(self) -> None:
        m = re.search(r"rsync (.+?) \"\$CLONE/dist/\" \"\$STATIC/\"", TEXT)
        self.assertIsNotNone(m, "rsync має брати dist/ зі скісною рискою і класти в /srv/aluma/")
        for flag in ("-a", "--delete-after", "--delay-updates", "--chmod=D0755,F0644"):
            self.assertIn(flag, m.group(1))
        self.assertIn("find \"$STATIC\" ! -perm -o=r", TEXT)

    def test_build_is_production_by_default_and_refusal_restores(self) -> None:
        self.assertIn('local sha="" mode=production', TEXT)
        self.assertIn("--preview) mode=preview", TEXT)
        self.assertIn("return 3", TEXT)
        self.assertIn('3) git -C "$CLONE" checkout -q --detach "$prev"', TEXT)

    def test_only_merged_master_commits_and_clean_clone(self) -> None:
        self.assertIn('merge-base --is-ancestor "$sha" origin/master', TEXT)
        self.assertIn("status --porcelain --untracked-files=no", TEXT)


class DeployBoxStandTests(unittest.TestCase):
    """Стенд: порожній «клон» без .venv — скрипт мусить відмовити кодом 2 до будь-яких змін."""

    def run_script(self, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        full = {**os.environ, **env}
        return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, env=full, timeout=60)

    def test_without_args_prints_usage_and_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            r = self.run_script(env={"ALUMA_CLONE": td})
        self.assertEqual(r.returncode, 2)
        self.assertIn("deploy-box.sh <sha>", r.stdout)

    def test_bad_sha_and_missing_clone_refuse_before_changes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = {"ALUMA_CLONE": td, "ALUMA_STATIC": td}
            r = self.run_script("not-a-sha", env=env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("sha", r.stderr)
            r = self.run_script("563edc8", env=env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("клон", r.stderr)
            self.assertFalse((Path(td) / "tmp" / "deploy-box.log").exists(), "до відмови журнал не пишеться")

    def test_status_on_empty_stand_does_not_fail_hard(self) -> None:
        # --status на порожньому стенді: git-команди падають, але це не викат — важливо, що нічого не змінено.
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git", "init", "-q", td], check=True)
            r = self.run_script("--status", env={"ALUMA_CLONE": td, "ALUMA_HEALTH_URL": "http://127.0.0.1:9/x"})
        self.assertIn("deploy-box:", r.stdout + r.stderr)
        self.assertFalse((Path(td) / "tmp" / "deploy-box.log").exists())


if __name__ == "__main__":
    unittest.main()
