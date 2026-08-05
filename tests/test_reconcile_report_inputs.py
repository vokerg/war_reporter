from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import reconcile_repository as reconcile


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class ReconcileReportInputTests(unittest.TestCase):
    day = date(2026, 8, 5)
    now = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)

    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        dump(
            root / "config/autonomy.json",
            {
                "activation_not_before": "2026-08-05T00:00:00Z",
                "timezone": "Europe/Copenhagen",
                "daily_cycle": {
                    "discovery_due_local_hour": 6,
                    "snapshot_due_local_hour": 8,
                    "region": "ukraine-war",
                    "maximum_nonterminal_backlog": 40,
                },
                "queue": {
                    "proposal_root": "queue/proposals",
                    "allowed_proposal_task_types": [],
                },
            },
        )
        dump(
            root / "config/worker-routing.json",
            {
                "task_type_to_role": {
                    "open_web_discovery": "open-web-discovery",
                    "investigate_claim": "corroborator",
                    "daily_report": "report-editor",
                }
            },
        )
        for index, (slug, _priority, _topics) in enumerate(reconcile.DISCOVERY_SHARDS, 1):
            task_id = f"task_daily_20260805_{index:02d}_{slug.replace('-', '_')}"
            dump(
                root / "tasks/2026/08/05" / f"{task_id}.json",
                {
                    "task_id": task_id,
                    "task_type": "open_web_discovery",
                    "state": "merged",
                    "window": {
                        "from": "2026-08-05T00:00:00Z",
                        "to": "2026-08-06T00:00:00Z",
                    },
                    "scope": {"regions": ["ukraine-war"]},
                    "allowed_output_paths": list(reconcile.discovery_data_paths(self.day, slug)),
                    "idempotency_key": reconcile.daily_key(self.day, slug, "ukraine-war"),
                },
            )
        return root

    @staticmethod
    def approved_claim(claim_id: str = "clm_reportable") -> dict[str, object]:
        return {
            "claim_id": claim_id,
            "record_status": "approved",
            "event_time": {
                "start": "2026-08-05T12:00:00Z",
                "precision": "hour",
            },
            "statement": {"canonical": "A reportable event occurred.", "language": "en"},
            "claim_type": "event",
            "assessment": {
                "outcome": "probable",
                "confidence": "medium",
                "assessed_at": "2026-08-05T18:00:00Z",
                "rationale": "Fixture",
            },
            "evidence": [{"observation_id": "obs_fixture", "relation": "supports"}],
            "created_at": "2026-08-05T18:00:00Z",
            "updated_at": "2026-08-05T18:00:00Z",
        }

    def test_empty_approved_set_defers_report_and_materializes_assessment_task(self) -> None:
        root = self.make_root()
        plan = reconcile.plan_duties(root, self.now)

        kinds = [duty["kind"] for duty in plan["duties"]]
        self.assertNotIn("daily_snapshot", kinds)
        self.assertEqual(kinds.count("report_input_assessment"), 1)
        self.assertTrue(any("no approved claims or assessments" in blocker for blocker in plan["blockers"]))

        result = reconcile.apply_plan(root, plan)
        self.assertEqual(result["created_task_ids"], ["task_daily_20260805_80_report_inputs"])
        self.assertFalse((root / "tasks/2026/08/05/task_daily_20260805_90_snapshot.json").exists())
        assessment_task = json.loads(
            (root / "tasks/2026/08/05/task_daily_20260805_80_report_inputs.json").read_text(encoding="utf-8")
        )
        self.assertEqual(assessment_task["task_type"], "investigate_claim")
        self.assertIn("data/claims/2026/08/05/**", assessment_task["allowed_output_paths"])
        self.assertIn("data/assessments/2026/08/05/**", assessment_task["allowed_output_paths"])

    def test_approved_claim_creates_snapshot_with_frozen_contract(self) -> None:
        root = self.make_root()
        claim = self.approved_claim()
        dump(root / "data/claims/2026/08/05/claim.json", claim)

        plan = reconcile.plan_duties(root, self.now)
        snapshot = next(duty for duty in plan["duties"] if duty["kind"] == "daily_snapshot")
        self.assertEqual(snapshot["report_inputs"]["claim_ids"], ["clm_reportable"])
        self.assertEqual(snapshot["report_inputs"]["assessment_ids"], [])
        self.assertRegex(snapshot["report_inputs"]["claim_set_sha256"], r"^[a-f0-9]{64}$")
        self.assertNotIn("report_input_assessment", [duty["kind"] for duty in plan["duties"]])

        result = reconcile.apply_plan(root, plan)
        self.assertEqual(result["created_task_ids"], ["task_daily_20260805_90_snapshot"])
        task = json.loads(
            (root / "tasks/2026/08/05/task_daily_20260805_90_snapshot.json").read_text(encoding="utf-8")
        )
        self.assertEqual(task["report_inputs"], snapshot["report_inputs"])

    def test_unapproved_claim_is_not_report_input(self) -> None:
        root = self.make_root()
        claim = self.approved_claim()
        claim["record_status"] = "in_review"
        dump(root / "data/claims/2026/08/05/claim.json", claim)

        plan = reconcile.plan_duties(root, self.now)
        self.assertNotIn("daily_snapshot", [duty["kind"] for duty in plan["duties"]])
        self.assertIn("report_input_assessment", [duty["kind"] for duty in plan["duties"]])

    def planned_report(self, root: Path) -> Path:
        dependency_id = "task_backfill_claims"
        dump(
            root / "tasks/2026/08/05/task_backfill_claims.json",
            {
                "task_id": dependency_id,
                "task_type": "investigate_claim",
                "state": "merged",
                "depends_on_task_ids": [],
                "window": {"from": "2026-08-05T00:00:00Z", "to": "2026-08-06T00:00:00Z"},
                "idempotency_key": "backfill_claims:2026-08-05",
            },
        )
        path = root / "tasks/2026/08/05/task_backfill_report.json"
        dump(
            path,
            {
                "task_id": "task_backfill_report",
                "task_type": "daily_report",
                "state": "planned",
                "depends_on_task_ids": [dependency_id],
                "window": {"from": "2026-08-05T00:00:00Z", "to": "2026-08-06T00:00:00Z"},
                "idempotency_key": reconcile.daily_report_key(self.day, "ukraine-war"),
                "lease": None,
            },
        )
        return path

    def test_planned_report_waits_until_approved_inputs_exist(self) -> None:
        root = self.make_root()
        report_path = self.planned_report(root)

        plan = reconcile.plan_duties(root, self.now)
        promoted = [
            task_id
            for duty in plan["duties"]
            if duty["kind"] == "promote_tasks"
            for task_id in duty["task_ids"]
        ]
        self.assertNotIn("task_backfill_report", promoted)
        self.assertTrue(any("task_backfill_report remains planned" in value for value in plan["blockers"]))
        self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["state"], "planned")

    def test_planned_report_freezes_inputs_during_promotion(self) -> None:
        root = self.make_root()
        report_path = self.planned_report(root)
        dump(root / "data/claims/2026/08/05/claim.json", self.approved_claim())

        plan = reconcile.plan_duties(root, self.now)
        promotion = next(
            duty
            for duty in plan["duties"]
            if duty["kind"] == "promote_tasks" and "task_backfill_report" in duty["task_ids"]
        )
        frozen = promotion["report_inputs_by_task"]["task_backfill_report"]
        self.assertEqual(frozen["claim_ids"], ["clm_reportable"])

        result = reconcile.apply_plan(root, plan)
        self.assertIn("task_backfill_report", result["promoted_task_ids"])
        task = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(task["state"], "ready")
        self.assertEqual(task["report_inputs"], frozen)

    def test_hash_is_deterministic_across_file_order(self) -> None:
        root = self.make_root()
        first = self.approved_claim("clm_alpha")
        second = self.approved_claim("clm_beta")
        dump(root / "data/claims/z.json", second)
        dump(root / "data/claims/a.json", first)

        frozen = reconcile.frozen_report_inputs(
            root,
            datetime(2026, 8, 5, tzinfo=UTC),
            datetime(2026, 8, 6, tzinfo=UTC),
        )
        self.assertIsNotNone(frozen)
        assert frozen is not None
        payload = {"claims": [first, second], "assessments": []}
        expected = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(frozen["claim_ids"], ["clm_alpha", "clm_beta"])
        self.assertEqual(frozen["claim_set_sha256"], expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
