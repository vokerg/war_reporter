from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.check_health import health_result


NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


class HealthProbeTests(unittest.TestCase):
    def make_root(self, status: str = "ok") -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        (root / "data").mkdir()
        settings = {
            "state_file": "data/state.json",
            "raw_root": "data/raw",
            "report_root": "reports/daily",
            "poll_seconds": 900,
            "status_stale_after_hours": 1,
            "x_search_queries": [],
        }
        registry = {
            "sources": [
                {
                    "id": "source-web",
                    "platform": "web",
                    "group": "media",
                    "enabled": True,
                }
            ]
        }
        state = {
            "status": status,
            "last_run_at": "2026-08-06T11:45:00Z",
            "last_successful_run_at": (
                "2026-08-06T11:45:00Z"
                if status in {"ok", "idle"}
                else "2026-08-06T10:00:00Z"
            ),
            "since": "2026-08-05T11:45:00Z",
            "sources_configured": 1,
            "sources_attempted": 1,
            "sources_succeeded": 1 if status != "failed" else 0,
            "sources_skipped": 0,
            "items_added": 0,
            "items_withheld_recent": 0,
            "items_withheld_undated": 0,
            "errors": 1 if status in {"partial", "failed"} else 0,
            "configuration_errors": ["secret-provider-name"],
            "per_source": {
                "source-web": {
                    "status": "error" if status in {"partial", "failed"} else "ok",
                    "checked_at": "2026-08-06T11:44:00Z",
                    "last_success_at": "2026-08-06T10:00:00Z",
                    "error": "RuntimeError: secret-body",
                }
            },
        }
        (root / "config/settings.json").write_text(json.dumps(settings))
        (root / "config/sources.json").write_text(json.dumps(registry))
        (root / "data/state.json").write_text(json.dumps(state))
        return root

    def test_fresh_ok_and_idle_are_healthy(self) -> None:
        for status in ("ok", "idle"):
            result = health_result(self.make_root(status), now=NOW)
            self.assertTrue(result["healthy"])
            self.assertEqual(result["reasons"], [])

    def test_partial_and_failed_are_unhealthy(self) -> None:
        for status in ("partial", "failed"):
            result = health_result(self.make_root(status), now=NOW)
            self.assertFalse(result["healthy"])
            self.assertIn(f"run_{status}", result["reasons"])
            self.assertIn("source_errors", result["reasons"])

    def test_stale_clean_state_is_unhealthy(self) -> None:
        root = self.make_root("ok")
        state_path = root / "data/state.json"
        state = json.loads(state_path.read_text())
        state["last_run_at"] = "2026-08-06T09:00:00Z"
        state_path.write_text(json.dumps(state))
        result = health_result(root, now=NOW)
        self.assertFalse(result["healthy"])
        self.assertIn("state_stale", result["reasons"])

    def test_healthy_embargo_is_not_failure(self) -> None:
        root = self.make_root("ok")
        state_path = root / "data/state.json"
        state = json.loads(state_path.read_text())
        state["items_withheld_recent"] = 12
        state["items_withheld_undated"] = 2
        state_path.write_text(json.dumps(state))
        result = health_result(root, now=NOW)
        self.assertTrue(result["healthy"])
        self.assertEqual(result["withheld_recent"], 12)
        self.assertEqual(result["withheld_undated"], 2)

    def test_probe_never_exposes_raw_state_messages(self) -> None:
        result = health_result(self.make_root("partial"), now=NOW)
        payload = json.dumps(result)
        self.assertNotIn("secret-provider-name", payload)
        self.assertNotIn("secret-body", payload)


if __name__ == "__main__":
    unittest.main()
