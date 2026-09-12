"""docs/DELIVERY.md і зв'язані документи (FR-027, FR-028; вимоги диригента 2026-09-11 і 2026-09-12).

Документ процесу мусить описувати те, що є, і не видавати майбутню схему за діючу: два стани — «як зараз»
і «після установки агента (T040)», неперевірене — з позначкою. Секретів у ньому немає. Старого AWS більше
немає (docs/AWS-TEARDOWN.md) — жоден із цих документів не має казати, що він ще є або ще видаляється.

    python -m unittest tests.test_delivery_doc -v
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "DELIVERY.md"

SECTIONS = ("Оточення", "Гілки, PR, коміти", "Перевірки (CI)", "Релізи й версії", "Викат", "Секрети", "Ресурси",
            "Відкат", "Розрив зі стандартом флоту", "Хто що натискає", "Якщо щось зламалось")


def headings(text: str) -> list:
    return [m.group(1).strip() for m in re.finditer(r"^#{1,4}\s+(.+)$", text, re.M)]


class DeliveryDocTests(unittest.TestCase):
    def setUp(self):
        self.text = DOC.read_text(encoding="utf-8")
        self.heads = headings(self.text)

    def test_all_sections(self):
        for name in SECTIONS:
            self.assertTrue(any(name in h for h in self.heads), name)

    def test_required_mentions(self):
        for needle in ("docs/AWS-TEARDOWN.md", "ALUMA_HEALTH_URL", "rollback.yml", "actions/setup-python@v6",
                       "actions/checkout@v6", "actions/setup-node@v6", "RELEASES_ENABLED", "release.yml",
                       "deploy.yml", "ci.yml", "pullagent.py"):
            self.assertIn(needle, self.text, needle)

    def test_two_states_are_explicit(self):
        self.assertIn("Як зараз", self.text)
        self.assertIn("Після установки агента (T040)", self.text)
        self.assertIn("563edc8", self.text)          # клон, з якого сервіс працює зараз
        self.assertIn("не перевірено, після Phase 3", self.text)

    def test_rollback_always_available(self):
        self.assertRegex(self.text, r"(?i)відкат доступний завжди, коли агент установлений")

    def test_where_agent_failures_are_visible(self):
        for needle in ("state/deploy.log", "state/failed.json", "--status", "journalctl --user -u ihor-aluma-deploy",
                       "SuccessExitStatus"):
            self.assertIn(needle, self.text, needle)

    def test_relative_links_exist(self):
        links = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", self.text)
        local = [link for link in links if not re.match(r"^[a-z]+:", link)]
        self.assertTrue(local, "у документі мають бути посилання на файли репозиторію")
        for link in local:
            self.assertTrue((DOC.parent / link).resolve().exists(), link)

    def test_aws_is_gone_not_in_progress(self):
        """Розділ «Ресурси» — факт: старого AWS немає, а не «видаляється» (рішення диригента 12.09)."""
        self.assertNotIn("видаляється", self.text)
        self.assertIn("нічого не залишилось", self.text)
        self.assertIn("2026-09-19", self.text)          # секрет aluma/admin-credentials, вікно 7 днів

    def test_no_secret_assignments(self):
        for name in ("ADMIN_PASS", "IP_SALT", "TELEGRAM_BOT_TOKEN", "EDGE_SECRET", "OWNER_TELEGRAM_CHAT_ID"):
            self.assertNotRegex(self.text, rf"\b{name}\s*=\s*\S", name)


class RelatedDocsTests(unittest.TestCase):
    def test_claude_md_points_to_delivery_and_drops_old_claims(self):
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("docs/DELIVERY.md", text)
        self.assertNotIn("Deploy is owner-only", text)
        self.assertNotIn("it does **not** deploy", text)
        self.assertIn("Після установки агента (T040)", text.replace("After the agent is installed (T040)",
                                                                      "Після установки агента (T040)"))

    def test_deploy_readme_points_to_delivery(self):
        text = (ROOT / "deploy" / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/DELIVERY.md", text)
        self.assertIn("замінено", text)

    def test_cutover_checklist_points_to_delivery_and_health_url(self):
        text = (ROOT / "docs" / "CUTOVER-CHECKLIST.md").read_text(encoding="utf-8")
        self.assertIn("docs/DELIVERY.md", text)
        self.assertIn("ALUMA_HEALTH_URL", text)
        self.assertIn("gh variable set ALUMA_HEALTH_URL", text)

    def test_docs_do_not_claim_aws_is_still_there(self):
        """Шапки CUTOVER-CHECKLIST, deploy/README і CLAUDE.md — за фактом 12.09, без «видаляється»."""
        for rel in ("docs/CUTOVER-CHECKLIST.md", "deploy/README.md"):
            head = (ROOT / rel).read_text(encoding="utf-8")[:2000]
            self.assertNotIn("видаляється", head, rel)
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("is being deleted", claude)
        self.assertNotIn("Prod today: AWS stack", claude)


if __name__ == "__main__":
    unittest.main()
