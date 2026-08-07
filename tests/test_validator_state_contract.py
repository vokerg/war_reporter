from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate import validate


class ValidatorStateContractTests(unittest.TestCase):
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
            "sensitive_tags": [],
            "public_redact_tags": [],
            "x_search_queries": [],
            "platform_cadence_minutes": {"web": 60},
            "minimum_group_counts": {},
            "article_host_allowlist": {},
            "status_stale_after_hours": 1,
        }
        source = {
            "id": "source-web",
            "name": "Source",
            "platform": "web",
            "url": "https://news.example.com/",
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

    def write_state(self, root: Path, state: dict) -> None:
        path = root / "data/state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state))

    def clean_state(self) -> dict:
        return {
            "status": "ok",
            "last_run_at": "2026-08-06T12:00:00Z",
            "last_successful_run_at": "2026-08-06T12:00:00Z",
            "since": "2026-08-05T12:00:00Z",
            "sources_configured": 1,
            "sources_attempted": 1,
            "sources_succeeded": 1,
            "sources_skipped": 0,
            "items_added": 0,
            "items_withheld_recent": 0,
            "items_withheld_undated": 0,
            "errors": 0,
            "configuration_errors": [],
            "per_source": {
                "source-web": {
                    "status": "ok",
                    "checked_at": "2026-08-06T11:59:59Z",
                    "last_success_at": "2026-08-06T11:59:59Z",
                }
            },
        }

    def test_valid_clean_state_passes(self) -> None:
        root = self.make_root()
        self.write_state(root, self.clean_state())
        self.assertEqual(validate(root), [])

    def test_clean_run_timestamp_must_match_last_run(self) -> None:
        root = self.make_root()
        state = self.clean_state()
        state["last_successful_run_at"] = "2026-08-06T11:00:00Z"
        self.write_state(root, state)
        self.assertTrue(
            any("clean run must set" in error for error in validate(root))
        )

    def test_last_successful_run_cannot_be_in_future(self) -> None:
        root = self.make_root()
        state = self.clean_state()
        state["status"] = "partial"
        state["last_successful_run_at"] = "2026-08-06T13:00:00Z"
        self.write_state(root, state)
        self.assertTrue(
            any("last_successful_run_at is after" in error for error in validate(root))
        )

    def test_source_timestamp_cannot_exceed_run_completion(self) -> None:
        root = self.make_root()
        state = self.clean_state()
        state["per_source"]["source-web"]["checked_at"] = (
            "2026-08-06T12:00:01Z"
        )
        self.write_state(root, state)
        self.assertTrue(
            any("checked_at is after" in error for error in validate(root))
        )

    def test_publisher_allowlist_must_reference_known_source(self) -> None:
        root = self.make_root()
        path = root / "config/settings.json"
        settings = json.loads(path.read_text())
        settings["article_host_allowlist"] = {
            "missing-rss": ["publisher.example.org"]
        }
        path.write_text(json.dumps(settings))
        self.assertTrue(
            any(
                "article_host_allowlist references unknown source" in error
                for error in validate(root)
            )
        )

    def test_publisher_allowlist_rejects_urls_and_mixed_case(self) -> None:
        root = self.make_root()
        path = root / "config/settings.json"
        settings = json.loads(path.read_text())
        settings["article_host_allowlist"] = {
            "source-web": ["https://Publisher.Example.org/path"]
        }
        path.write_text(json.dumps(settings))
        self.assertTrue(
            any("must be a lowercase domain" in error for error in validate(root))
        )


if __name__ == "__main__":
    unittest.main()
