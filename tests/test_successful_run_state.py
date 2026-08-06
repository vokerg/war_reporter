from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.collector_runtime import run_collection


class SuccessfulRunStateTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        settings = {
            "poll_seconds": 900,
            "workers": 2,
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
            "public_excerpt_chars": 100,
            "public_media_limit": 2,
            "public_redact_tags": [],
            "x_search_queries": [],
        }
        sources = [
            {
                "id": "one-web",
                "name": "One",
                "platform": "web",
                "url": "https://one.example/news",
                "group": "media",
                "perspective": "mixed",
                "trust": "high",
                "priority": 20,
                "enabled": True,
            },
            {
                "id": "two-web",
                "name": "Two",
                "platform": "web",
                "url": "https://two.example/news",
                "group": "media",
                "perspective": "mixed",
                "trust": "high",
                "priority": 10,
                "enabled": True,
            },
        ]
        (root / "config/settings.json").write_text(json.dumps(settings))
        (root / "config/sources.json").write_text(
            json.dumps({"sources": sources})
        )
        return root

    def test_partial_run_preserves_last_successful_run_time(self) -> None:
        root = self.make_root()
        with patch("scripts.collector_runtime.collect_one", return_value=[]):
            clean = run_collection(root, force=True)
        self.assertEqual(clean["status"], "ok")
        successful_at = clean["last_successful_run_at"]
        self.assertIsNotNone(successful_at)
        self.assertEqual(clean["last_run_at"], successful_at)

        def partial(source, _settings, _since):
            if source["id"] == "two-web":
                raise RuntimeError("untrusted diagnostic detail")
            return []

        with patch("scripts.collector_runtime.collect_one", side_effect=partial):
            degraded = run_collection(root, force=True)
        self.assertEqual(degraded["status"], "partial")
        self.assertEqual(
            degraded["last_successful_run_at"], successful_at
        )
        self.assertNotEqual(degraded["last_run_at"], successful_at)

    def test_first_failed_run_has_no_successful_timestamp(self) -> None:
        root = self.make_root()
        with patch(
            "scripts.collector_runtime.collect_one",
            side_effect=RuntimeError("failure"),
        ):
            failed = run_collection(root, force=True)
        self.assertEqual(failed["status"], "failed")
        self.assertIsNone(failed["last_successful_run_at"])


if __name__ == "__main__":
    unittest.main()
