from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from continuous_loop import evaluate_loop


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ContinuousLoopTests(unittest.TestCase):
    def make_root(self, *, activation: str = "2099-01-01T00:00:00Z") -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for relative in ("config/autonomy.json", "config/worker-routing.json"):
            source = REPO_ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, target)
        config_path = root / "config/autonomy.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["activation_not_before"] = activation
        dump(config_path, config)
        dump(root / "config/hardening-gate.json", {"canonicalization_complete": True})
        (root / "tasks").mkdir(parents=True)
        return root

    def task(
        self,
        task_id: str,
        state: str = "ready",
        *,
        blocked_reason: str | None = None,
        priority: int = 80,
    ) -> dict[str, object]:
        task: dict[str, object] = {
            "task_id": task_id,
            "task_type": "open_web_discovery",
            "state": state,
            "priority": priority,
            "created_at": "2026-08-05T10:00:00Z",
            "depends_on_task_ids": [],
        }
        if blocked_reason is not None:
            task["blocked_reason"] = blocked_reason
        return task

    def test_ready_task_is_claimed(self) -> None:
        root = self.make_root()
        dump(root / "tasks/task_alpha.json", self.task("task_alpha"))
        decision = evaluate_loop(root, now=datetime(2026, 8, 5, 12, tzinfo=UTC))
        self.assertEqual(decision["action"], "claim")
        self.assertEqual(decision["task"]["task_id"], "task_alpha")
        self.assertEqual(decision["task"]["branch"], "work/task_alpha")

    def test_pending_proposal_reconciles_before_claiming(self) -> None:
        root = self.make_root()
        producer = self.task("task_producer", "merged")
        dump(root / "tasks/task_producer.json", producer)
        dump(root / "tasks/task_ready.json", self.task("task_ready"))
        dump(root / "queue/proposals/task_producer.json", {
            "producer_task_id": "task_producer",
            "generated_at": "2026-08-05T11:00:00Z",
            "proposals": [{
                "task_type": "extract_observations",
                "priority": 60,
                "depends_on_task_ids": ["task_producer"],
                "window": {"from": "2026-08-04T00:00:00Z", "to": "2026-08-05T00:00:00Z"},
                "scope": {
                    "source_ids": [],
                    "source_groups": [],
                    "regions": ["ukraine-war"],
                    "topics": ["example"],
                    "content_types": ["post"],
                },
                "exclusions": ["No browsing"],
                "allowed_output_paths": ["data/observations/example.ndjson"],
                "definition_of_done": ["Observations extracted"],
                "idempotency_key": "extract:continuous-loop:test",
            }],
        })
        decision = evaluate_loop(root, now=datetime(2026, 8, 5, 12, tzinfo=UTC))
        self.assertEqual(decision["action"], "reconcile")
        self.assertEqual(decision["duties"][0]["kind"], "task_proposal")

    def test_review_task_keeps_loop_waiting(self) -> None:
        root = self.make_root()
        dump(root / "tasks/task_review.json", self.task("task_review", "review"))
        decision = evaluate_loop(
            root,
            now=datetime(2026, 8, 5, 12, tzinfo=UTC),
            open_worker_prs=1,
            active_work_branches=1,
        )
        self.assertEqual(decision["action"], "wait")
        self.assertEqual(decision["reason"], "work_in_flight")

    def test_operational_block_does_not_preempt_ready_work(self) -> None:
        root = self.make_root()
        dump(
            root / "tasks/task_blocked.json",
            self.task("task_blocked", "blocked", blocked_reason="HTTP 403 from a source"),
        )
        dump(root / "tasks/task_ready.json", self.task("task_ready"))
        decision = evaluate_loop(root, now=datetime(2026, 8, 5, 12, tzinfo=UTC))
        self.assertEqual(decision["action"], "claim")
        self.assertEqual(decision["task"]["task_id"], "task_ready")

    def test_operational_block_without_ready_work_waits(self) -> None:
        root = self.make_root()
        dump(
            root / "tasks/task_blocked.json",
            self.task("task_blocked", "blocked", blocked_reason="HTTP 403 from a source"),
        )
        decision = evaluate_loop(root, now=datetime(2026, 8, 5, 12, tzinfo=UTC))
        self.assertEqual(decision["action"], "wait")
        self.assertEqual(decision["reason"], "nonterminal_queue_not_claimable")

    def test_exceptional_pr_telemetry_does_not_halt_loop(self) -> None:
        root = self.make_root()
        dump(root / "tasks/task_ready.json", self.task("task_ready"))
        decision = evaluate_loop(
            root,
            now=datetime(2026, 8, 5, 12, tzinfo=UTC),
            exceptional_prs=3,
        )
        self.assertEqual(decision["action"], "claim")
        self.assertEqual(decision["task"]["task_id"], "task_ready")
        self.assertEqual(decision["queue"]["exceptional_prs"], 3)

    def test_quiescence_requires_sweeps_and_elapsed_window(self) -> None:
        root = self.make_root()
        now = datetime(2026, 8, 5, 12, tzinfo=UTC)
        config = json.loads((root / "config/autonomy.json").read_text(encoding="utf-8"))
        loop = config["continuous_loop"]
        early = evaluate_loop(
            root,
            now=now,
            idle_sweeps=loop["minimum_idle_sweeps"] - 1,
            idle_since=now - timedelta(seconds=loop["minimum_idle_window_seconds"] + 1),
        )
        self.assertEqual(early["reason"], "quiescence_not_proven")
        done = evaluate_loop(
            root,
            now=now,
            idle_sweeps=loop["minimum_idle_sweeps"],
            idle_since=now - timedelta(seconds=loop["minimum_idle_window_seconds"] + 1),
        )
        self.assertEqual(done["action"], "quiescent")

    def test_upcoming_daily_boundary_prevents_exit(self) -> None:
        root = self.make_root(activation="2026-08-01T00:00:00Z")
        now = datetime(2026, 8, 7, 3, 30, tzinfo=UTC)
        config = json.loads((root / "config/autonomy.json").read_text(encoding="utf-8"))
        loop = config["continuous_loop"]
        decision = evaluate_loop(
            root,
            now=now,
            idle_sweeps=loop["minimum_idle_sweeps"],
            idle_since=now - timedelta(seconds=loop["minimum_idle_window_seconds"] + 1),
        )
        self.assertEqual(decision["action"], "wait")
        self.assertEqual(decision["reason"], "scheduled_duty_within_guard")


if __name__ == "__main__":
    unittest.main(verbosity=2)
