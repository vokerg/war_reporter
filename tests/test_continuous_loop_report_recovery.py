from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.continuous_loop import report_days_to_build


class ContinuousLoopReportRecoveryTests(unittest.TestCase):
    def settings(self) -> dict:
        return {
            "raw_root": "data/raw",
            "report_root": "reports/daily",
            "report_timezone": "Europe/Kyiv",
        }

    def test_missing_recent_report_is_recovered_when_raw_exists(self) -> None:
        root = Path(tempfile.mkdtemp())
        raw = root / "data/raw/2026/08/11/items.ndjson"
        raw.parent.mkdir(parents=True)
        raw.write_text('{"id":"one"}\n', encoding="utf-8")
        reports = root / "reports/daily"
        reports.mkdir(parents=True)
        (reports / "2026-08-10.md").write_text("# existing\n", encoding="utf-8")

        days = report_days_to_build(root, self.settings(), date(2026, 8, 13))

        self.assertEqual(
            days,
            [date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13)],
        )

    def test_existing_old_report_is_not_rebuilt_by_recovery_scan(self) -> None:
        root = Path(tempfile.mkdtemp())
        raw = root / "data/raw/2026/08/11/items.ndjson"
        raw.parent.mkdir(parents=True)
        raw.write_text('{"id":"one"}\n', encoding="utf-8")
        reports = root / "reports/daily"
        reports.mkdir(parents=True)
        (reports / "2026-08-11.md").write_text("# existing\n", encoding="utf-8")

        days = report_days_to_build(root, self.settings(), date(2026, 8, 13))

        self.assertEqual(days, [date(2026, 8, 12), date(2026, 8, 13)])

    def test_missing_report_without_raw_is_not_synthesized(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "reports/daily").mkdir(parents=True)

        days = report_days_to_build(root, self.settings(), date(2026, 8, 13))

        self.assertEqual(days, [date(2026, 8, 12), date(2026, 8, 13)])


if __name__ == "__main__":
    unittest.main()
