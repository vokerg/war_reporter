from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_site import build_site
from scripts.build_weekly_site import build_weekly_site


class WeeklySiteTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        (root / "reports/daily").mkdir(parents=True)
        (root / "reports/summary").mkdir(parents=True)
        (root / "reports/weekly").mkdir(parents=True)
        settings = {
            "poll_seconds": 900,
            "report_timezone": "Europe/Kyiv",
            "raw_root": "data/raw",
            "state_file": "data/state.json",
            "report_root": "reports/daily",
            "site_root": "site",
            "status_stale_after_hours": 1,
            "site_publication_delay_hours": 0,
            "site_sensitive_delay_hours": 0,
            "sensitive_tags": [],
            "public_redact_tags": [],
            "x_search_queries": [],
        }
        (root / "config/settings.json").write_text(
            json.dumps(settings), encoding="utf-8"
        )
        (root / "config/sources.json").write_text(
            json.dumps({"version": 1, "sources": []}), encoding="utf-8"
        )
        (root / "data").mkdir()
        (root / "data/state.json").write_text(
            json.dumps(
                {
                    "status": "ok",
                    "last_run_at": "2026-08-09T23:00:00Z",
                    "last_successful_run_at": "2026-08-09T23:00:00Z",
                    "sources_configured": 0,
                    "sources_attempted": 0,
                    "sources_succeeded": 0,
                    "sources_skipped": 0,
                    "errors": 0,
                    "items_added": 0,
                    "per_source": {},
                }
            ),
            encoding="utf-8",
        )
        return root

    def test_weekly_reports_are_rendered_and_linked(self) -> None:
        root = self.make_root()
        day = "2026-08-03"
        week = "2026-08-03_2026-08-09"
        (root / f"reports/daily/{day}.md").write_text(
            "# Digest\n\nSource material.", encoding="utf-8"
        )
        (root / f"reports/summary/{day}.md").write_text(
            "# Summary\n\nEditorial daily summary.", encoding="utf-8"
        )
        (root / f"reports/weekly/{week}.md").write_text(
            "# Weekly\n\n[Day](../summary/2026-08-03.md)\n\n<script>alert(1)</script>",
            encoding="utf-8",
        )

        site = build_site(root)
        weekly_site = build_weekly_site(root)

        homepage = (site / "index.html").read_text(encoding="utf-8")
        daily_summary = (site / f"summaries/{day}.html").read_text(encoding="utf-8")
        weekly_index = (weekly_site / "index.html").read_text(encoding="utf-8")
        weekly = (weekly_site / f"{week}.html").read_text(encoding="utf-8")

        self.assertIn("id='weekly-reports'", homepage)
        self.assertIn(f"weekly/{week}.html", homepage)
        self.assertIn(f"{week}.html", weekly_index)
        self.assertIn("Недельные сводки", daily_summary)
        self.assertIn(f"../summaries/{day}.html", weekly)
        self.assertNotIn("<script>alert(1)</script>", weekly)

        build_weekly_site(root)
        homepage_again = (site / "index.html").read_text(encoding="utf-8")
        self.assertEqual(homepage_again.count("id='weekly-reports'"), 1)
        self.assertEqual(homepage_again.count(">Недельные сводки</a>"), 1)

    def test_pages_workflow_runs_weekly_builder(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/pages.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("python -m scripts.build_site", workflow)
        self.assertIn("python -m scripts.build_weekly_site", workflow)
        self.assertIn('"scripts/build_weekly_site.py"', workflow)


if __name__ == "__main__":
    unittest.main()
