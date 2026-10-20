"""site/assets/tracking.js за контрактом specs/002-meta-settings/contracts/tracking.md.

Скрипт виконується в node:vm із фальшивим DOM (tests/tracking_harness.js): без браузера, мережі й порту.
Доводиться головне для реклами й приватності: без pixel_id — жодного запиту до Meta, без згоди — жодного
стороннього коду, ?me=1 — нічого, а Lead несе той самий event_id, що й заявка (дедуплікація з CAPI).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "tracking_harness.js"
NODE = shutil.which("node")
PIXEL = "123456789012345"


def run(**scenario) -> dict:
    out = subprocess.run([NODE, str(HARNESS), json.dumps(scenario)], capture_output=True, text=True, timeout=20, check=True)
    return json.loads(out.stdout)


def meta_urls(r):
    return [u for u in r["scripts"] + r["fetches"] if "facebook" in u or "clarity" in u]


@unittest.skipUnless(NODE, "node не встановлено")
class TrackingJsTests(unittest.TestCase):
    def test_syntax_and_globals(self):
        subprocess.run([NODE, "--check", str(ROOT / "site/assets/tracking.js")], check=True, capture_output=True)
        r = run(config={})
        self.assertEqual(r["globals"], ["alumaTrack", "alumaEventId", "alumaConsent", "alumaConsentState",
                                        "alumaConsentReset", "alumaConfig"])
        self.assertEqual(r["dispatched"], "aluma:config")

    def test_no_pixel_no_third_party_at_all(self):
        for scenario in ({"config": {}, "consent": True}, {"config": "fail", "consent": True},
                         {"config": {"pixel_id": None, "clarity_id": None}, "consent": True, "consentAfter": True}):
            r = run(calls=[["Lead", {}]], **scenario)
            self.assertEqual(meta_urls(r), [], scenario)
            self.assertEqual(r["fbq"], [])
            self.assertIsNone(r["notice"])
            self.assertIn("Lead", [e["name"] for e in r["events"]])   # перша сторона працює й без пікселя

    def test_without_consent_nothing_loads_until_ok(self):
        r = run(config={"pixel_id": PIXEL, "clarity_id": "abcdef1234"}, calls=[["ViewContent", {"content_ids": ["x"]}]])
        self.assertEqual(meta_urls(r), [])
        self.assertEqual(r["notice"], "shown")
        self.assertIsNone(r["consent"])
        r = run(config={"pixel_id": PIXEL, "clarity_id": "abcdef1234"}, clickNotice=True,
                calls=[["ViewContent", {"content_ids": ["x"]}]])
        self.assertEqual(r["consent"], "1")
        self.assertEqual(r["notice"], "removed")
        self.assertIn("https://www.clarity.ms/tag/abcdef1234", r["scripts"])
        names = [c[1] for c in r["fbq"] if c[0] == "track"]
        self.assertEqual(names, ["PageView", "ViewContent"])         # черга до згоди не губиться

    def test_storefront_notice_is_respected(self):
        r = run(config={"pixel_id": PIXEL}, hasNotice=True)
        self.assertIsNone(r["notice"])
        self.assertEqual(meta_urls(r), [])
        r = run(config={"pixel_id": PIXEL}, hasNotice=True, consentAfter=True)
        self.assertEqual(r["fbq"][0], ["init", PIXEL])

    def test_notice_language_direction_and_choice(self):
        """Тексти банера — з i18n/legal.<lang>.json (cookies), дві рівноцінні кнопки вибору й посилання."""
        he = json.loads((ROOT / "i18n/legal.he.json").read_text(encoding="utf-8"))["cookies"]
        en = json.loads((ROOT / "i18n/legal.en.json").read_text(encoding="utf-8"))["cookies"]
        r = run(config={"pixel_id": PIXEL})
        self.assertEqual((r["noticeText"], r["noticeDir"]), (he["text"], "rtl"))
        self.assertEqual(r["buttons"], [he["accept"], he["decline"], he["more"]])
        r = run(config={"pixel_id": PIXEL}, lang="en")
        self.assertEqual((r["noticeText"], r["noticeDir"]), (en["text"], "ltr"))
        self.assertEqual(r["buttons"], [en["accept"], en["decline"], en["more"]])
        self.assertEqual(r["posts"][0]["ctx"]["lang"], "en")

    def test_decline_loads_nothing_and_is_not_asked_again(self):
        cfg = {"pixel_id": PIXEL, "clarity_id": "abcdef1234"}
        r = run(config=cfg, clickDecline=True, calls=[["ViewContent", {}]], callsAfter=["Lead"])
        self.assertEqual((r["consent"], r["state"], r["notice"]), ("0", "denied", "removed"))
        self.assertEqual(meta_urls(r), [])
        self.assertEqual(r["fbq"], [])
        self.assertEqual(r["consentEvents"], ["denied"])
        self.assertIn("Lead", [e["name"] for e in r["events"]])     # перша сторона без ідентифікаторів реклами
        r = run(config=cfg, stored="0", consentAfter=False)
        self.assertIsNone(r["notice"])                                 # наступна сторінка — не питаємо знову
        self.assertEqual(meta_urls(r), [])

    def test_consent_can_be_withdrawn_and_asked_again(self):
        cfg = {"pixel_id": PIXEL}
        r = run(config=cfg, consent=True, declineAfter=True)
        self.assertEqual(r["state"], "denied")
        r = run(config=cfg, stored="0", resetAfter=True)
        self.assertEqual((r["notice"], r["state"]), ("shown", None))
        self.assertEqual(meta_urls(r), [])
        r = run(config=cfg, stored="garbage")
        self.assertEqual((r["notice"], r["state"]), ("shown", None))

    def test_event_ids_shared_by_pixel_and_first_party(self):
        r = run(config={"pixel_id": PIXEL}, consent=True,
                calls=[["Lead", {"event_id": "lead.k1.abcdef"}], ["Contact", {"via": "whatsapp"}], ["Hover", {}]])
        self.assertEqual(r["ids"][0], "lead.k1.abcdef")
        fbq = {c[1]: c for c in r["fbq"] if c[0] in ("track", "trackCustom")}
        self.assertEqual(fbq["Lead"], ["track", "Lead", {}, {"eventID": "lead.k1.abcdef"}])
        self.assertEqual(fbq["Contact"][2], {"via": "whatsapp"})
        self.assertEqual(fbq["Hover"][0], "trackCustom")
        first = {e["name"]: e["id"] for e in r["events"]}
        self.assertEqual(first["Lead"], "lead.k1.abcdef")
        self.assertEqual(first["Contact"], r["ids"][1])
        self.assertEqual(first["PageView"], fbq["PageView"][3]["eventID"])
        for i in r["ids"]:
            self.assertRegex(i, r"^[A-Za-z0-9_.-]{8,64}$")             # формат event_id, що приймає /api/fx/lead

    def test_owner_is_never_tracked(self):
        for scenario in ({"me": True}, {"search": "?me=1"}):
            r = run(config={"pixel_id": PIXEL}, consent=True, calls=[["Lead", {}]], **scenario)
            self.assertEqual(r["posts"], [], scenario)
            self.assertEqual(meta_urls(r), [])
            self.assertEqual(r["fbq"], [])

    def test_attribution_reaches_events(self):
        r = run(config={}, search="?utm_source=fb&utm_campaign=goren-test&fbclid=AbC")
        ctx = r["posts"][0]["ctx"]
        self.assertEqual((ctx["utm_source"], ctx["utm_campaign"]), ("fb", "goren-test"))
        self.assertTrue(ctx["attributed_at"])
        self.assertEqual(ctx["fbclid"], "")                 # без згоди рекламний ідентифікатор не йде
        r = run(config={}, consent=True, search="?utm_source=fb&fbclid=AbC")
        self.assertEqual(r["posts"][0]["ctx"]["fbclid"], "AbC")

    def test_bad_ids_from_config_are_ignored(self):
        r = run(config={"pixel_id": "12ab<script>", "clarity_id": "x\"onload"}, consent=True)
        self.assertEqual(meta_urls(r), [])


if __name__ == "__main__":
    unittest.main()
