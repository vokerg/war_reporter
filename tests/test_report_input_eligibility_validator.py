from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_report_input_eligibility as validator


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class ReportInputEligibilityValidatorTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        dump(
            root / "tasks/2026/08/04/task_producer.json",
            {
                "task_id": "task_producer",
                "task_type": "investigate_claim",
                "state": "review",
                "window": {
                    "from": "2026-08-04T00:00:00Z",
                    "to": "2026-08-05T00:00:00Z",
                },
            },
        )
        dump(
            root / "tasks/2026/08/04/task_report.json",
            {
                "task_id": "task_report",
                "task_type": "daily_report",
                "state": "planned",
                "depends_on_task_ids": ["task_producer"],
                "window": {
                    "from": "2026-08-04T00:00:00Z",
                    "to": "2026-08-05T00:00:00Z",
                },
            },
        )
        return root

    def add_reportable_records(self, root: Path) -> None:
        dump(
            root / "data/claims/claim.json",
            {
                "claim_id": "clm_validator_fixture",
                "record_status": "approved",
            },
        )
        dump(
            root / "data/assessments/assessment.json",
            {
                "assessment_id": "asm_validator_fixture",
                "record_status": "approved",
                "as_of": "2026-08-05T19:25:00Z",
                "reporting_period": {
                    "start": "2026-08-04T00:00:00Z",
                    "end": "2026-08-05T00:00:00Z",
                },
                "claim_ids": ["clm_validator_fixture"],
            },
        )

    def test_output_complete_dependency_without_inputs_fails(self) -> None:
        errors = validator.validate(self.make_root())

        self.assertTrue(any("no approved claim or assessment" in error for error in errors))

    def test_reportable_assessment_satisfies_dependency_contract(self) -> None:
        root = self.make_root()
        self.add_reportable_records(root)

        self.assertEqual(validator.validate(root), [])

    def test_incomplete_dependency_does_not_require_frozen_inputs_yet(self) -> None:
        root = self.make_root()
        producer_path = root / "tasks/2026/08/04/task_producer.json"
        producer = json.loads(producer_path.read_text(encoding="utf-8"))
        producer["state"] = "collecting"
        dump(producer_path, producer)

        self.assertEqual(validator.validate(root), [])

    def test_reversed_reporting_period_fails(self) -> None:
        root = self.make_root()
        self.add_reportable_records(root)
        assessment_path = root / "data/assessments/assessment.json"
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        assessment["reporting_period"] = {
            "start": "2026-08-05T00:00:00Z",
            "end": "2026-08-04T00:00:00Z",
        }
        dump(assessment_path, assessment)

        errors = validator.validate(root)
        self.assertTrue(any("reporting_period.end must be after" in error for error in errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
