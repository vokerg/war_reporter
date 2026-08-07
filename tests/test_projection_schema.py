from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate import validate


class ProjectionSchemaTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        settings = {
            "poll_seconds": 900,
            "workers": 1,
            "request_timeout_seconds": 5,
            "default_lookback_hours": 24,
            "telegram_max_pages": 1,
            "x_max_pages": 1,
            "web_max_links": 1,
            "public_excerpt_chars": 100,
            "public_media_limit": 2,
            "collection_delay_hours": 0,
            "site_publication_delay_hours": 0,
            "site_sensitive_delay_hours": 0,
            "collection_delay_by_group": {},
            "collection_delay_by_tag": {},
            "collection_delay_by_source": {},
            "raw_root": "data/raw",
            "error_root": "data/errors",
            "state_file": "data/state.json",
            "report_root": "reports/daily",
            "site_root": "site",
            "report_timezone": "UTC",
            "sensitive_tags": ["precise-location"],
            "public_redact_tags": ["precise-location"],
            "x_search_queries": [],
            "platform_cadence_minutes": {"web": 60},
            "minimum_group_counts": {},
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
        return root

    def write_item(self, root: Path, item: dict) -> None:
        path = root / "data/raw/2026/08/01/items.ndjson"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(item) + "\n")

    def redacted_item(self) -> dict:
        return {
            "id": "item-1",
            "source": "source-web",
            "platform": "web",
            "url": "https://example.com/story",
            "published_at": "2026-08-01T00:00:00Z",
            "collected_at": "2026-08-06T00:00:00Z",
            "title": "",
            "text": "",
            "html": "",
            "media": [],
            "tags": ["precise-location"],
            "raw": {
                "archive_policy": "public_redacted_v1",
                "redacted": True,
                "platform": {"content_type": "text/html"},
            },
        }

    def test_redacted_projection_is_valid(self) -> None:
        root = self.make_root()
        self.write_item(root, self.redacted_item())
        self.assertEqual(validate(root), [])

    def test_redacted_projection_rejects_content(self) -> None:
        root = self.make_root()
        item = self.redacted_item()
        item["title"] = "Exact unit location"
        self.write_item(root, item)
        self.assertTrue(
            any(
                "redacted projection contains public content" in error
                for error in validate(root)
            )
        )

    def test_excerpt_projection_rejects_invalid_digest(self) -> None:
        root = self.make_root()
        item = self.redacted_item()
        item["tags"] = []
        item["text"] = "public excerpt"
        item["raw"] = {
            "archive_policy": "public_excerpt_v1",
            "content_sha256": "not-a-digest",
            "original_text_chars": 14,
            "original_html_chars": 0,
            "text_truncated": False,
            "media_count": 0,
            "platform": {},
        }
        self.write_item(root, item)
        self.assertTrue(
            any("invalid content_sha256" in error for error in validate(root))
        )


if __name__ == "__main__":
    unittest.main()
