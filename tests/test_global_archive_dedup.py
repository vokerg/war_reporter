from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.collect import run_collection
from scripts.validate import validate


class GlobalArchiveDedupTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        settings = {
            "poll_seconds": 900,
            "workers": 1,
            "request_timeout_seconds": 5,
            "user_agent": "test",
            "report_timezone": "Europe/Kyiv",
            "raw_root": "data/raw",
            "error_root": "data/errors",
            "state_file": "data/state.json",
            "report_root": "reports/daily",
            "site_root": "site",
            "default_lookback_hours": 48,
            "telegram_max_pages": 2,
            "x_max_pages": 2,
            "web_max_links": 4,
            "public_excerpt_chars": 1200,
            "public_media_limit": 2,
            "platform_cadence_minutes": {
                "telegram": 15,
                "x": 15,
                "rss": 60,
                "web": 1440,
            },
            "collection_delay_hours": 0,
            "site_publication_delay_hours": 0,
            "site_sensitive_delay_hours": 0,
            "sensitive_tags": [],
            "public_redact_tags": [],
            "collection_delay_by_group": {},
            "collection_delay_by_tag": {},
            "collection_delay_by_source": {},
            "minimum_group_counts": {},
            "x_search_queries": [],
        }
        source = {
            "id": "source-a",
            "name": "Source A",
            "platform": "telegram",
            "url": "https://t.me/source_a",
            "group": "osint",
            "perspective": "mixed",
            "trust": "high",
            "priority": 80,
            "languages": ["en"],
            "tags": [],
            "enabled": True,
        }
        (root / "config/settings.json").write_text(
            json.dumps(settings), encoding="utf-8"
        )
        (root / "config/sources.json").write_text(
            json.dumps({"version": 1, "sources": [source]}),
            encoding="utf-8",
        )
        return root

    @staticmethod
    def item(collected_at: str) -> dict:
        return {
            "id": "same-undated-publication",
            "source": "source-a",
            "source_name": "Source A",
            "platform": "telegram",
            "url": "https://t.me/source_a/1",
            "published_at": None,
            "collected_at": collected_at,
            "title": "Undated snapshot",
            "text": "same source publication",
            "html": "",
            "media": [],
            "author": "Source A",
            "language": "en",
            "group": "osint",
            "perspective": "mixed",
            "trust": "high",
            "tags": [],
            "raw": {"post": "source_a/1"},
        }

    def test_undated_recollection_stays_in_first_seen_shard(self) -> None:
        root = self.make_root()
        first = self.item("2026-08-07T12:00:00Z")
        repeated = self.item("2026-08-09T12:00:00Z")

        with patch(
            "scripts.collect.collect_one",
            side_effect=[[first], [repeated]],
        ):
            first_state = run_collection(root, force=True)
            repeated_state = run_collection(root, force=True)

        first_path = root / "data/raw/2026/08/07/items.ndjson"
        repeated_path = root / "data/raw/2026/08/09/items.ndjson"

        self.assertEqual(first_state["items_added"], 1)
        self.assertEqual(repeated_state["items_added"], 0)
        self.assertTrue(first_path.exists())
        self.assertFalse(repeated_path.exists())
        self.assertEqual(len(first_path.read_text().splitlines()), 1)
        self.assertEqual(validate(root), [])


if __name__ == "__main__":
    unittest.main()
