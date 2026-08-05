from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import reconcile_repository as reconcile


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class ReportingPeriodInputTests(unittest.TestCase):
    start = datetime(2026, 8, 4, tzinfo=UTC)
    end = datetime(2026, 8, 5, tzinfo=UTC)

    def make_root(self, reporting_period: dict[str, str]) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        dump(
            root / "data/claims/claim.json",
            {
                "claim_id": "clm_reporting_period_fixture",
                "record_status": "approved",
            },
        )
        dump(
            root / "data/assessments/assessment.json",
            {
                "assessment_id": "asm_reporting_period_fixture",
                "record_status": "approved",
                "as_of": "2026-08-05T19:25:00Z",
                "reporting_period": reporting_period,
                "claim_ids": ["clm_reporting_period_fixture"],
            },
        )
        return root

    def test_reporting_period_selects_assessment_without_rewriting_as_of(self) -> None:
        root = self.make_root(
            {
                "start": "2026-08-04T00:00:00Z",
                "end": "2026-08-05T00:00:00Z",
            }
        )

        frozen = reconcile.frozen_report_inputs(root, self.start, self.end)

        self.assertIsNotNone(frozen)
        assert frozen is not None
        self.assertEqual(frozen["claim_ids"], ["clm_reporting_period_fixture"])
        self.assertEqual(frozen["assessment_ids"], ["asm_reporting_period_fixture"])

    def test_non_overlapping_reporting_period_is_not_selected(self) -> None:
        root = self.make_root(
            {
                "start": "2026-08-05T00:00:00Z",
                "end": "2026-08-06T00:00:00Z",
            }
        )

        self.assertIsNone(reconcile.frozen_report_inputs(root, self.start, self.end))

    def test_reversed_reporting_period_is_not_selected(self) -> None:
        root = self.make_root(
            {
                "start": "2026-08-05T00:00:00Z",
                "end": "2026-08-04T00:00:00Z",
            }
        )

        self.assertIsNone(reconcile.frozen_report_inputs(root, self.start, self.end))

    def test_existing_4_august_backfill_is_reportable(self) -> None:
        frozen = reconcile.frozen_report_inputs(REPO_ROOT, self.start, self.end)

        self.assertIsNotNone(frozen)
        assert frozen is not None
        self.assertEqual(len(frozen["claim_ids"]), 19)
        self.assertEqual(len(frozen["assessment_ids"]), 7)

        plan = reconcile.plan_duties(
            REPO_ROOT,
            datetime(2026, 8, 5, 20, 0, tzinfo=UTC),
        )
        promotion = next(
            duty
            for duty in plan["duties"]
            if duty["kind"] == "promote_tasks"
            and "task_backfill_20260804_daily_report_en" in duty["task_ids"]
        )
        report_inputs = promotion["report_inputs_by_task"]["task_backfill_20260804_daily_report_en"]
        self.assertEqual(report_inputs, frozen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
