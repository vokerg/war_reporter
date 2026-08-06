from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.build_site import build_site
from scripts.public_status import (
    STATUS_SCHEMA,
    build_public_status,
    render_public_status,
)


NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


class PublicStatusTests(unittest.TestCase):
    def make_root(self, state: dict) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        (root / "data").mkdir()
        settings = {
            "poll_seconds": 900,
            "state_file": "data/state.json",
            "raw_root": "data/raw",
            "report_root": "reports/daily",
            "site_root": "site",
            "site_publication_delay_hours": 24,
            "site_sensitive_delay_hours": 72,
            "sensitive_tags": ["frontline", "precise-location"],
            "public_redact_tags": ["precise-location"],
            "x_search_queries": ["ukraine war -is:retweet"],
        }
        sources = [
            {
                "id": "source-web",
                "platform": "web",
                "group": "media",
                "enabled": True,
            },
            {
                "id": "source-tg",
                "platform": "telegram",
                "group": "official",
                "enabled": True,
            },
        ]
        (root / "config/settings.json").write_text(json.dumps(settings))
        (root / "config/sources.json").write_text(
            json.dumps({"sources": sources})
        )
        (root / "data/state.json").write_text(json.dumps(state))
        return root

    def state(self, status: str) -> dict:
        return {
            "status": status,
            "last_run_at": "2026-08-06T11:50:00Z",
            "since": "2026-08-05T11:50:00Z",
            "sources_configured": 3,
            "sources_attempted": 2,
            "sources_succeeded": 1,
            "sources_skipped": 1,
            "items_added": 4,
            "items_withheld_recent": 0,
            "items_withheld_undated": 0,
            "errors": 1 if status in {"partial", "failed"} else 0,
            "configuration_errors": [
                "X_BEARER_TOKEN is not configured: super-secret"
            ],
            "per_source": {
                "source-web": {
                    "status": "ok",
                    "last_success_at": "2026-08-06T11:49:00Z",
                },
                "source-tg": {
                    "status": (
                        "error" if status in {"partial", "failed"}
                        else "skipped_cadence"
                    ),
                    "error": "RuntimeError: secret response body",
                },
                "x-discovery-1": {
                    "status": "skipped_config",
                    "reason": "X_BEARER_TOKEN is not configured",
                },
            },
        }

    def test_complete_current_projection(self) -> None:
        root = self.make_root(self.state("ok"))
        status = build_public_status(root, now=NOW)
        self.assertEqual(status["schema"], STATUS_SCHEMA)
        self.assertEqual(status["scope"], "current-state-only")
        self.assertFalse(status["freshness"]["stale"])
        self.assertEqual(status["registry"]["configured_enabled"], 3)
        self.assertEqual(status["source_status_counts"]["ok"], 1)
        self.assertEqual(
            status["source_status_counts"]["skipped_config"], 1
        )

    def test_idle_state_remains_distinct(self) -> None:
        root = self.make_root(self.state("idle"))
        status = build_public_status(root, now=NOW)
        self.assertEqual(status["run"]["status"], "idle")
        self.assertIn("cadence", render_public_status(status))

    def test_partial_state_remains_distinct(self) -> None:
        root = self.make_root(self.state("partial"))
        status = build_public_status(root, now=NOW)
        self.assertEqual(status["run"]["status"], "partial")
        self.assertEqual(status["degradation"]["source_errors"], 1)

    def test_blocked_state_remains_distinct(self) -> None:
        root = self.make_root(self.state("blocked"))
        status = build_public_status(root, now=NOW)
        self.assertEqual(status["run"]["status"], "blocked")

    def test_failed_state_remains_distinct(self) -> None:
        root = self.make_root(self.state("failed"))
        status = build_public_status(root, now=NOW)
        self.assertEqual(status["run"]["status"], "failed")

    def test_stale_is_calculated_from_timestamp(self) -> None:
        state = self.state("ok")
        state["last_run_at"] = "2026-08-06T08:00:00Z"
        root = self.make_root(state)
        status = build_public_status(root, now=NOW)
        self.assertTrue(status["freshness"]["stale"])
        self.assertEqual(status["freshness"]["last_run_age_hours"], 4.0)

    def test_embargo_only_is_not_reported_as_failure(self) -> None:
        state = self.state("ok")
        state["errors"] = 0
        state["items_added"] = 0
        state["items_withheld_recent"] = 7
        state["items_withheld_undated"] = 2
        root = self.make_root(state)
        status = build_public_status(root, now=NOW)
        self.assertEqual(status["run"]["status"], "ok")
        self.assertEqual(status["withholding"], {"recent": 7, "undated": 2})
        self.assertIn("recent: 7; undated: 2", render_public_status(status))

    def test_secret_and_raw_error_text_are_omitted(self) -> None:
        root = self.make_root(self.state("partial"))
        status = build_public_status(root, now=NOW)
        public_text = json.dumps(status) + render_public_status(status)
        for forbidden in (
            "X_BEARER_TOKEN",
            "super-secret",
            "secret response body",
            "RuntimeError",
        ):
            self.assertNotIn(forbidden, public_text)

    def test_site_writes_html_json_and_navigation(self) -> None:
        root = self.make_root(self.state("partial"))
        site = build_site(root)
        status_json = json.loads((site / "status.json").read_text())
        status_html = (site / "status/index.html").read_text()
        index = (site / "index.html").read_text()
        self.assertEqual(status_json["schema"], STATUS_SCHEMA)
        self.assertIn("Статус сбора", status_html)
        self.assertIn("status/index.html", index)
        self.assertNotIn("X_BEARER_TOKEN", status_html)


if __name__ == "__main__":
    unittest.main()
