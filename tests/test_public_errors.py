from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from scripts.collect import run_collection
from scripts.collector_common import CollectionError
from scripts.collector_runtime import public_error_summary


class PublicErrorTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        settings = {
            "poll_seconds": 900,
            "workers": 1,
            "request_timeout_seconds": 5,
            "user_agent": "test",
            "raw_root": "data/raw",
            "error_root": "data/errors",
            "state_file": "data/state.json",
            "default_lookback_hours": 24,
            "platform_cadence_minutes": {"web": 60},
            "collection_delay_hours": 0,
            "collection_delay_by_group": {},
            "collection_delay_by_tag": {},
            "collection_delay_by_source": {},
            "x_search_queries": [],
        }
        registry = {
            "version": 1,
            "sources": [
                {
                    "id": "source-a",
                    "name": "Source A",
                    "platform": "web",
                    "url": "https://example.com/news",
                    "group": "media",
                    "perspective": "mixed",
                    "trust": "high",
                    "priority": 10,
                    "enabled": True,
                }
            ],
        }
        (root / "config/settings.json").write_text(
            json.dumps(settings), encoding="utf-8"
        )
        (root / "config/sources.json").write_text(
            json.dumps(registry), encoding="utf-8"
        )
        return root

    def test_arbitrary_exception_details_do_not_enter_public_state(self) -> None:
        root = self.make_root()
        secret = "token=super-secret"
        with patch(
            "scripts.collect.collect_one",
            side_effect=RuntimeError(f"https://example.com/?{secret}"),
        ):
            state = run_collection(root, force=True)

        self.assertEqual(state["status"], "failed")
        state_text = (root / "data/state.json").read_text(encoding="utf-8")
        error_text = next((root / "data/errors").rglob("errors.ndjson")).read_text(
            encoding="utf-8"
        )
        self.assertNotIn(secret, state_text)
        self.assertNotIn(secret, error_text)
        self.assertIn("RuntimeError: unexpected_error", state_text)
        self.assertIn("RuntimeError: unexpected_error", error_text)

    def test_http_status_is_retained_without_exception_message(self) -> None:
        response = requests.Response()
        response.status_code = 403
        exc = requests.HTTPError(
            "https://example.com/?token=super-secret",
            response=response,
        )
        self.assertEqual(public_error_summary(exc), "HTTPError: http_403")
        self.assertNotIn("super-secret", public_error_summary(exc))

    def test_x_response_body_is_not_persisted(self) -> None:
        exc = CollectionError("X API 401: bearer token super-secret")
        self.assertEqual(
            public_error_summary(exc),
            "CollectionError: x_api_http_401",
        )
        self.assertNotIn("super-secret", public_error_summary(exc))


if __name__ == "__main__":
    unittest.main()
