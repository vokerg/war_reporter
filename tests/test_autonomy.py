from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from finalize_merged_task import finalize
from reconcile_repository import apply_plan, plan_duties, task_index
from validate_autonomy import proposal_output_allowed, validate_auto_merge_trust_boundary, validate_receipt
from validate_pr_scope import validate_scope


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class AutonomyTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for relative in ("config/autonomy.json", "schemas/self-review.schema.json"):
            source = REPO_ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, target)
        dump(root / "config/worker-routing.json", {
            "task_type_to_role": {
                "open_web_discovery": "open-web-discovery",
                "extract_observations": "extractor",
                "daily_report": "report-editor",
            }
        })
        (root / "tasks").mkdir()
        return root

    def test_proposals_cannot_grant_control_plane_paths(self) -> None:
        self.assertTrue(proposal_output_allowed("data/observations/example.ndjson"))
        self.assertTrue(proposal_output_allowed("catalogs/sources/example.json"))
        self.assertFalse(proposal_output_allowed("tasks/escalated.json"))
        self.assertFalse(proposal_output_allowed(".github/workflows/escalated.yml"))

    def test_write_capable_controller_uses_trusted_main_validators(self) -> None:
        root = self.make_root()
        workflow = root / ".github/workflows/auto-merge-reviewed.yml"
        finalizer = root / ".github/workflows/finalize-task-merge.yml"
        workflow.parent.mkdir(parents=True, exist_ok=True)
        valid_auto = (
            "actions: write\nref: main\npath: trusted\npath: pr-head\n"
            "validated_sha\n"
            "commits/$validated_sha/pulls\ncandidate_count\n"
            "python trusted/scripts/validate_autonomy.py\n"
            "python trusted/scripts/validate_pr_scope.py\n"
            "gh workflow run finalize-task-merge.yml\n"
            "-f pr_number=\n-f merge_sha=\n-f merged_at=\n-f head_ref=\n"
        )
        valid_finalizer = (
            "workflow_dispatch:\n"
            "FINALIZE_PR_NUMBER:\n"
            "FINALIZE_MERGE_SHA:\n"
            "FINALIZE_MERGED_AT:\n"
            "FINALIZE_HEAD_REF:\n"
        )
        workflow.write_text(valid_auto, encoding="utf-8")
        finalizer.write_text(valid_finalizer, encoding="utf-8")
        self.assertEqual(validate_auto_merge_trust_boundary(root), [])

        workflow.write_text(valid_auto.replace("commits/$validated_sha/pulls\n", ""), encoding="utf-8")
        errors = validate_auto_merge_trust_boundary(root)
        self.assertTrue(any("commits/$validated_sha/pulls" in error for error in errors))

        workflow.write_text("python scripts/validate_autonomy.py\n", encoding="utf-8")
        errors = validate_auto_merge_trust_boundary(root)
        self.assertTrue(any("may not execute validator from PR head" in error for error in errors))

        workflow.write_text(valid_auto, encoding="utf-8")
        finalizer.write_text("pull_request:\n", encoding="utf-8")
        errors = validate_auto_merge_trust_boundary(root)
        self.assertTrue(any("dispatch-finalizer" in error for error in errors))

    def test_finalizer_uses_serialized_trusted_main_push(self) -> None:
        text = (REPO_ROOT / ".github/workflows/finalize-task-merge.yml").read_text(encoding="utf-8")
        self.assertIn("group: finalize-merged-worker-task-main", text)
        self.assertIn("git fetch origin main", text)
        self.assertIn("git rebase origin/main", text)
        self.assertIn("git push origin HEAD:main", text)
        self.assertNotIn("gh pr create", text)

    def test_two_review_rounds_are_ordered_and_complete(self) -> None:
        root = self.make_root()
        checks = json.loads((root / "config/autonomy.json").read_text())["self_review"]["required_checks"]
        receipt = {
            "task_id": "task_example",
            "pr_number": 7,
            "rounds": [
                {"round": 1, "reviewed_at": "2026-08-05T09:00:00Z", "reviewer_run_id": "run_one", "checks": checks, "findings": ["one"], "repairs": ["fixed"], "outcome": "pass"},
                {"round": 2, "reviewed_at": "2026-08-05T09:10:00Z", "reviewer_run_id": "run_one", "checks": checks, "findings": [], "repairs": [], "outcome": "pass"},
            ],
            "exceptional_condition": False,
        }
        path = root / "review/self/task_example.json"
        dump(path, receipt)
        self.assertEqual(validate_receipt(root, path, expected_task_id="task_example", expected_pr_number=7, require_automerge_eligible=True), [])
        receipt["rounds"][1]["round"] = 1
        dump(path, receipt)
        self.assertTrue(any("ordered exactly" in error for error in validate_receipt(root, path)))

    def test_reconciler_creates_daily_discovery_and_snapshot(self) -> None:
        root = self.make_root()
        now = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
        plan = plan_duties(root, now)
        self.assertEqual([d["kind"] for d in plan["duties"]], ["discovery_campaign"])
        result = apply_plan(root, plan, parent_issue=12)
        self.assertEqual(len(result["created_task_ids"]), 10)
        tasks = task_index(root)
        for path, task in tasks.values():
            task["state"] = "merged"
            task["lease"] = None
            task["result"] = {"branch": f"work/{task['task_id']}", "pr_number": 1, "merge_sha": "a" * 40, "merged_at": "2026-08-07T08:00:00Z", "completed_at": "2026-08-07T08:00:00Z"}
            dump(path, task)
        snapshot_plan = plan_duties(root, now)
        self.assertIn("daily_snapshot", [d["kind"] for d in snapshot_plan["duties"]])

    def test_merged_proposal_materializes_next_task(self) -> None:
        root = self.make_root()
        now = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
        apply_plan(root, plan_duties(root, now), parent_issue=12)
        tasks = task_index(root)
        producer_id = sorted(tasks)[0]
        producer_path, producer = tasks[producer_id]
        producer["state"] = "merged"
        producer["lease"] = None
        dump(producer_path, producer)
        dump(root / f"queue/proposals/{producer_id}.json", {
            "producer_task_id": producer_id,
            "generated_at": "2026-08-07T09:00:00Z",
            "proposals": [{
                "task_type": "extract_observations",
                "priority": 60,
                "depends_on_task_ids": [producer_id],
                "window": producer["window"],
                "scope": producer["scope"],
                "exclusions": ["No new browsing"],
                "allowed_output_paths": ["data/observations/2026/08/06/example.ndjson"],
                "definition_of_done": ["Atomic observations extracted"],
                "idempotency_key": "extract:test:2026-08-06",
            }],
        })
        plan = plan_duties(root, now)
        proposal_duties = [d for d in plan["duties"] if d["kind"] == "task_proposal"]
        self.assertEqual(len(proposal_duties), 1)
        result = apply_plan(root, {"generated_at": plan["generated_at"], "duties": proposal_duties, "blockers": []})
        self.assertEqual(len(result["created_task_ids"]), 1)

    def test_finalizer_records_actual_merge_metadata(self) -> None:
        root = self.make_root()
        task_id = "task_example"
        dump(root / "tasks/task_example.json", {
            "task_id": task_id,
            "state": "review",
            "lease": {"worker_run_id": "run_x"},
            "result": {"branch": f"work/{task_id}", "pr_number": 9},
        })
        result = finalize(root, task_id, 9, "b" * 40, "2026-08-05T09:30:00Z", f"work/{task_id}")
        self.assertEqual(result["merge_sha"], "b" * 40)
        value = json.loads((root / "tasks/task_example.json").read_text())
        self.assertEqual(value["state"], "merged")
        self.assertIsNone(value["lease"])

    def test_scope_gate_rejects_control_plane_changes(self) -> None:
        root = self.make_root()
        subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        task_id = "task_example"
        dump(root / "tasks/task_example.json", {
            "task_id": task_id,
            "state": "ready",
            "allowed_output_paths": ["data/example.json"],
        })
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, stdout=subprocess.DEVNULL)
        base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dump(root / "data/example.json", {"ok": True})
        dump(root / "review/self/task_example.json", {"placeholder": True})
        dump(root / "tasks/task_example.json", {
            "task_id": task_id,
            "state": "review",
            "allowed_output_paths": ["data/example.json"],
            "result": {"branch": "work/task_example", "pr_number": 3},
        })
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "work"], cwd=root, check=True, stdout=subprocess.DEVNULL)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        self.assertEqual(validate_scope(root, task_id, 3, base, head), [])
        dump(root / "config/forbidden.json", {})
        widened = json.loads((root / "tasks/task_example.json").read_text())
        widened["allowed_output_paths"] = ["data/example.json", "config/**"]
        dump(root / "tasks/task_example.json", widened)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "bad"], cwd=root, check=True, stdout=subprocess.DEVNULL)
        bad_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        errors = validate_scope(root, task_id, 3, base, bad_head)
        self.assertTrue(any("outside base task scope" in error for error in errors))
        self.assertTrue(any("immutable task contract field changed: allowed_output_paths" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
