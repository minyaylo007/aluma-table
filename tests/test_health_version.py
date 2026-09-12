"""GET /api/fx/health — `version` і `git_sha` (contracts/health.md); підпис версії в /admin без «vv».

Номер і sha приходять з оточення (RELEASE.env юніта після aluma.env), тому кожен випадок читає окрему копію
api/handler.py з потрібним оточенням — так само, як tests/test_lambda_no_fx_storage.py.

    python -m unittest tests.test_health_version -v
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import pathlib
import sys
import unittest
import uuid
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Імпорт ставить фейковий boto3 (якщо його немає), чистить оточення розробника і FX_DB_PATH=:memory:.
from tests.test_handler import request  # noqa: E402

SHA = "0123456789abcdef" * 2 + "01234567"
ISO = r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d"


def fresh_handler(**env):
    base = {k: v for k, v in os.environ.items() if k not in ("APP_VERSION", "GIT_SHA", "EDGE_SECRET")}
    base.update(env)
    with mock.patch.dict(os.environ, base, clear=True):
        spec = importlib.util.spec_from_file_location(f"_aluma_health_{uuid.uuid4().hex[:8]}",
                                                      ROOT / "api" / "handler.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


def text_of(response) -> str:
    body = response["body"]
    return base64.b64decode(body).decode("utf-8") if response.get("isBase64Encoded") else body


def health(mod):
    r = mod.lambda_handler(request("GET", "/api/fx/health"), None)
    return r, json.loads(text_of(r))


class HealthVersionTests(unittest.TestCase):
    def test_version_and_full_sha(self):
        r, b = health(fresh_handler(APP_VERSION="v0.5.0", GIT_SHA=SHA))
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(set(b), {"ok", "version", "git_sha", "ts"})
        self.assertIs(b["ok"], True)
        self.assertEqual(b["version"], "v0.5.0")
        self.assertEqual(b["git_sha"], SHA)
        self.assertRegex(b["ts"], ISO)

    def test_missing_sha_is_null(self):
        r, b = health(fresh_handler(APP_VERSION="v0.5.0"))
        self.assertIsNone(b["git_sha"])
        self.assertIn('"git_sha": null', text_of(r))

    def test_empty_sha_is_null(self):
        _, b = health(fresh_handler(APP_VERSION="v0.5.0", GIT_SHA=""))
        self.assertIsNone(b["git_sha"])

    def test_default_version_unchanged(self):
        _, b = health(fresh_handler())
        self.assertEqual(b["version"], "0.0.0")
        self.assertIsNone(b["git_sha"])

    def test_cache_and_content_type_as_before(self):
        r, _ = health(fresh_handler(APP_VERSION="v0.5.0", GIT_SHA=SHA))
        self.assertEqual(r["headers"]["content-type"], "application/json; charset=utf-8")
        self.assertEqual(r["headers"].get("cache-control"), "no-store")


class AdminVersionLabelTests(unittest.TestCase):
    def label_page(self, version):
        mod = fresh_handler(APP_VERSION=version)
        with mock.patch.object(mod, "check_auth", return_value=True), \
                mock.patch.object(mod, "scan_events", return_value=[]), \
                mock.patch.object(mod, "load_leads", return_value=[]):
            return text_of(mod.admin_page(request("GET", "/admin")))

    def test_release_tag_has_single_v(self):
        page = self.label_page("v0.5.0")
        self.assertIn("v0.5.0 ·", page)
        self.assertNotIn("vv0.5.0", page)

    def test_old_style_version_still_prefixed(self):
        page = self.label_page("0.4.0-box")
        self.assertIn("v0.4.0-box ·", page)


if __name__ == "__main__":
    unittest.main()
