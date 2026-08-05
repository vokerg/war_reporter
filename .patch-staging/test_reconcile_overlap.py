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

CONFIG = {
    "activation_not_before": "2026-08-05T09:00:00Z",
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
}


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class ReconcileOverlapTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        dump(root / "config/autonomy.json", CONFIG)
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
        (root / "tasks").mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def now() -> datetime:
        return datetime(2026, 8, 7, 10, 0, tzinfo=UTC)

    def add_task(
        self,
        root: Path,
        task_id: str,
        slug: str,
        start: str,
        end: str,
        output_day: str,
        state: str = "merged",
    ) -> None:
        day_path = output_day.replace("-", "/")
        task = {
            "task_id": task_id,
            "task_type": "open_web_discovery",
            "role": "open-web-discovery",
            "state": state,
            "priority": 80,
            "created_at": "2026-08-05T00:00:00Z",
            "parent_issue": 1,
            "issue_number": 2,
            "depends_on_task_ids": [],
            "window": {"from": start, "to": end},
            "scope": {
                "source_ids": [],
                "source_groups": [],
                "regions": ["ukraine-war"],
                "topics": [],
                "content_types": [],
            },
            "exclusions": [],
            "allowed_output_paths": [
                f"catalogs/sources/{day_path}/{slug}.json",
                f"data/source-items/{day_path}/{slug}.ndjson",
                f"data/artifacts/{day_path}/{slug}.ndjson",
                f"raw-manifests/{day_path}/{slug}.json",
            ],
            "definition_of_done": [],
            "idempotency_key": f"legacy:{slug}:{start}:{end}",
            "lease": None,
        }
        if state == "merged":
            task["result"] = {
                "branch": f"work/{task_id}",
                "pr_number": 1,
                "merge_sha": "a" * 40,
                "merged_at": "2026-08-07T08:00:00Z",
                "completed_at": "2026-08-07T08:00:00Z",
            }
        dump(root / f"tasks/{task_id}.json", task)

    @staticmethod
    def add_approved_claim(root: Path) -> None:
        dump(
            root / "data/claims/2026/08/06/clm_fixture.json",
            {
                "claim_id": "clm_fixture",
                "record_status": "approved",
                "event_time": {
                    "start": "2026-08-06T12:00:00Z",
                    "precision": "hour",
                },
            },
        )

    def test_clean_day_still_materializes_daily_campaign(self) -> None:
        root = self.make_root()
        plan = reconcile.plan_duties(root, self.now())
        self.assertEqual([duty["kind"] for duty in plan["duties"]], ["discovery_campaign"])
        self.assertEqual(plan["blockers"], [])
        result = reconcile.apply_plan(root, plan, parent_issue=12)
        self.assertEqual(len(result["created_task_ids"]), 10)

    def test_adjacent_legacy_windows_suppress_duplicate_campaign_and_allow_snapshot(self) -> None:
        root = self.make_root()
        for index, (slug, _, _) in enumerate(reconcile.DISCOVERY_SHARDS, 1):
            self.add_task(
                root,
                f"task_legacy_{index:02d}_{slug.replace('-', '_')}",
                slug,
                "2026-08-05T18:00:00Z",
                "2026-08-06T18:00:00Z",
                "2026-08-06",
            )
            self.add_task(
                root,
                f"task_incremental_{index:02d}_{slug.replace('-', '_')}",
                slug,
                "2026-08-06T18:00:00Z",
                "2026-08-07T05:00:00Z",
                "2026-08-07",
            )
        self.add_approved_claim(root)
        plan = reconcile.plan_duties(root, self.now())
        kinds = [duty["kind"] for duty in plan["duties"]]
        self.assertNotIn("discovery_campaign", kinds)
        self.assertIn("daily_snapshot", kinds)
        self.assertEqual(plan["blockers"], [])
        snapshot = next(duty for duty in plan["duties"] if duty["kind"] == "daily_snapshot")
        self.assertEqual(len(snapshot["depends_on_task_ids"]), 20)
        self.assertEqual(snapshot["report_inputs"]["claim_ids"], ["clm_fixture"])

    def test_partial_legacy_coverage_with_owned_outputs_blocks_full_day_campaign(self) -> None:
        root = self.make_root()
        self.add_task(
            root,
            "task_legacy_01_ua_official",
            "ua-official",
            "2026-08-05T18:00:00Z",
            "2026-08-06T18:00:00Z",
            "2026-08-06",
        )
        plan = reconcile.plan_duties(root, self.now())
        self.assertNotIn("discovery_campaign", [duty["kind"] for duty in plan["duties"]])
        self.assertTrue(
            any("generated output paths already owned" in blocker for blocker in plan["blockers"])
        )
        self.assertTrue(any("task_legacy_01_ua_official" in blocker for blocker in plan["blockers"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
