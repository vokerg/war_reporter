from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.collector_runtime import run_collection


class RuntimeArchiveBoundaryTests(unittest.TestCase):
    def test_direct_runtime_call_cannot_bypass_hard_redaction(self) -> None:
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
            "public_excerpt_chars": 100,
            "public_media_limit": 2,
            "public_redact_tags": ["precise-location"],
            "x_search_queries": [],
        }
        source = {
            "id": "source-web",
            "name": "Source",
            "platform": "web",
            "url": "https://example.com/news",
            "group": "media",
            "perspective": "mixed",
            "trust": "high",
            "priority": 10,
            "enabled": True,
        }
        (root / "config/settings.json").write_text(json.dumps(settings))
        (root / "config/sources.json").write_text(
            json.dumps({"sources": [source]})
        )
        item = {
            "id": "item-1",
            "source": "source-web",
            "source_name": "Source",
            "platform": "web",
            "url": "https://example.com/story",
            "published_at": "2026-08-01T00:00:00Z",
            "collected_at": "2026-08-06T00:00:00Z",
            "title": "Exact unit location",
            "text": "secret",
            "html": "<p>secret</p>",
            "media": ["https://example.com/secret.jpg"],
            "author": "",
            "language": "en",
            "group": "media",
            "perspective": "mixed",
            "trust": "high",
            "tags": ["precise-location"],
            "raw": {"content_type": "text/html", "secret": "payload"},
        }
        with patch(
            "scripts.collector_runtime.collect_one", return_value=[item]
        ):
            state = run_collection(root, force=True)

        self.assertEqual(state["status"], "ok")
        path = next((root / "data/raw").rglob("items.ndjson"))
        stored = json.loads(path.read_text().strip())
        serialized = json.dumps(stored)
        for forbidden in (
            "Exact unit location",
            "secret",
            "content_sha256",
            "original_text_chars",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(
            stored["raw"]["archive_policy"], "public_redacted_v1"
        )


if __name__ == "__main__":
    unittest.main()
