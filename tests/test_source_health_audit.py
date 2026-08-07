from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.audit_source_health import audit_source_health


NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


class SourceHealthAuditTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        (root / "data").mkdir()
        settings = {
            "state_file": "data/state.json",
            "x_search_queries": ["one query"],
        }
        sources = [
            {
                "id": "healthy-web",
                "enabled": True,
                "platform": "web",
                "group": "media",
            },
            {
                "id": "error-rss",
                "enabled": True,
                "platform": "rss",
                "group": "media",
            },
            {
                "id": "stale-tg",
                "enabled": True,
                "platform": "telegram",
                "group": "official",
            },
            {
                "id": "never-web",
                "enabled": True,
                "platform": "web",
                "group": "media",
            },
            {
                "id": "disabled-web",
                "enabled": False,
                "platform": "web",
                "group": "media",
            },
        ]
        state = {
            "per_source": {
                "healthy-web": {
                    "status": "ok",
                    "last_success_at": "2026-08-06T11:30:00Z",
                    "error": "secret healthy detail",
                },
                "error-rss": {
                    "status": "error",
                    "last_success_at": "2026-08-06T10:00:00Z",
                    "error": "RuntimeError: secret body",
                },
                "stale-tg": {
                    "status": "skipped_cadence",
                    "last_success_at": "2026-08-01T10:00:00Z",
                },
                "x-discovery-1": {
                    "status": "skipped_config",
                    "reason": "secret credential name",
                },
                "removed-web": {
                    "status": "error",
                    "error": "secret orphan detail",
                },
            }
        }
        (root / "config/settings.json").write_text(json.dumps(settings))
        (root / "config/sources.json").write_text(json.dumps({"sources": sources}))
        (root / "data/state.json").write_text(json.dumps(state))
        return root

    def test_classifies_current_snapshot(self) -> None:
        result = audit_source_health(
            self.make_root(), now=NOW, stale_after_hours=48
        )
        by_id = {row["source_id"]: row for row in result["sources"]}
        self.assertEqual(by_id["healthy-web"]["classification"], "healthy")
        self.assertEqual(by_id["error-rss"]["classification"], "current_error")
        self.assertEqual(by_id["stale-tg"]["classification"], "stale_success")
        self.assertEqual(by_id["never-web"]["classification"], "never_seen")
        self.assertEqual(by_id["disabled-web"]["classification"], "disabled")
        self.assertEqual(
            by_id["x-discovery-1"]["classification"],
            "configuration_blocked",
        )
        self.assertEqual(by_id["removed-web"]["classification"], "orphan_state")

    def test_safe_output_omits_raw_failure_details(self) -> None:
        result = audit_source_health(self.make_root(), now=NOW)
        payload = json.dumps(result)
        for forbidden in (
            "secret healthy detail",
            "secret body",
            "secret credential name",
            "secret orphan detail",
            "RuntimeError",
        ):
            self.assertNotIn(forbidden, payload)
        self.assertTrue(result["semantics"]["raw_error_details_omitted"])

    def test_disabled_sources_do_not_count_as_unhealthy(self) -> None:
        result = audit_source_health(self.make_root(), now=NOW)
        classifications = [row["classification"] for row in result["sources"]]
        expected_unhealthy = sum(
            value not in {"healthy", "cadence_wait", "disabled"}
            for value in classifications
        )
        self.assertEqual(result["enabled_unhealthy"], expected_unhealthy)

    def test_threshold_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be positive"):
            audit_source_health(self.make_root(), now=NOW, stale_after_hours=0)

    def test_audit_does_not_claim_history(self) -> None:
        result = audit_source_health(self.make_root(), now=NOW)
        self.assertTrue(
            result["semantics"]["single_snapshot_not_uptime_history"]
        )


if __name__ == "__main__":
    unittest.main()
