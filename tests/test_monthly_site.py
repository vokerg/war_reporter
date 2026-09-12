from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_monthly_site import build_monthly_site
from scripts.build_site import build_site
from scripts.build_weekly_site import build_weekly_site


class MonthlySiteTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        (root / "reports/daily").mkdir(parents=True)
        (root / "reports/summary").mkdir(parents=True)
        (root / "reports/weekly").mkdir(parents=True)
        (root / "reports/monthly").mkdir(parents=True)
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
                    "last_run_at": "2026-08-31T23:00:00Z",
                    "last_successful_run_at": "2026-08-31T23:00:00Z",
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

    def test_monthly_reports_are_rendered_and_linked(self) -> None:
        root = self.make_root()
        day = "2026-08-31"
        week = "2026-08-31_2026-09-06"
        month = "2026-08"
        (root / f"reports/daily/{day}.md").write_text(
            "# Digest\n\nSource material.", encoding="utf-8"
        )
        (root / f"reports/summary/{day}.md").write_text(
            "# Summary\n\nEditorial daily summary.", encoding="utf-8"
        )
        (root / f"reports/weekly/{week}.md").write_text(
            "# Weekly\n\nEditorial weekly summary.", encoding="utf-8"
        )
        (root / f"reports/monthly/{month}.md").write_text(
            "# Monthly\n\n<script>alert(1)</script>", encoding="utf-8"
        )

        site = build_site(root)
        build_weekly_site(root)
        monthly_site = build_monthly_site(root)

        homepage = (site / "index.html").read_text(encoding="utf-8")
        monthly_index = (monthly_site / "index.html").read_text(encoding="utf-8")
        monthly = (monthly_site / f"{month}.html").read_text(encoding="utf-8")

        self.assertIn("id='monthly-reports'", homepage)
        self.assertIn(f"monthly/{month}.html", homepage)
        self.assertIn(f"{month}.html", monthly_index)
        self.assertIn(f"../summaries/{day}.html", monthly)
        self.assertIn(f"../weekly/{week}.html", monthly)
        self.assertNotIn("<script>alert(1)</script>", monthly)
        self.assertEqual(homepage.count(">Месячные сводки</a>"), 1)

        build_monthly_site(root)
        homepage_again = (site / "index.html").read_text(encoding="utf-8")
        self.assertEqual(homepage_again.count("id='monthly-reports'"), 1)

    def test_pages_and_ci_run_monthly_builder(self) -> None:
        root = Path(__file__).resolve().parents[1]
        pages = (root / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python -m scripts.build_monthly_site", pages)
        self.assertIn('"scripts/build_monthly_site.py"', pages)
        self.assertIn("python -m scripts.build_monthly_site", ci)


if __name__ == "__main__":
    unittest.main()
