from __future__ import annotations

import json
import tempfile
import threading
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.bootstrap_pilot import build_tasks
from scripts.validate_worker_queue import validate_queue
from scripts.worker_queue import Task, claim_local, deterministic_branch, generate_worker_run_id, ready_tasks, release_local, role_for_task

ROOT = Path(__file__).resolve().parents[1]
ROUTING = ROOT / "config" / "worker-routing.json"


class WorkerQueueTests(unittest.TestCase):
    def test_all_bootstrap_task_types_have_roles(self) -> None:
        tasks = build_tasks(datetime(2026, 8, 4, tzinfo=UTC).date(), 10, "donetsk")
        self.assertEqual(10, len(tasks))
        for task in tasks:
            self.assertEqual(task["role"], role_for_task(task["task_type"], ROUTING))
            self.assertEqual("ready", task["state"])
            self.assertIsNone(task["lease"])

    def test_worker_run_id_and_branch_are_deterministic_shape(self) -> None:
        run_id = generate_worker_run_id(datetime(2026, 8, 4, 12, 30, tzinfo=UTC), "abcdef12")
        self.assertEqual("run_20260804T123000Z_abcdef12", run_id)
        self.assertEqual("work/task_example", deterministic_branch("task_example"))

    def test_ready_tasks_respect_dependencies_and_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            merged = {
                "task_id": "task_a", "task_type": "validation", "state": "merged", "priority": 1,
                "window": {"from": "2026-08-04T00:00:00Z", "to": "2026-08-04T01:00:00Z"},
                "scope": {"source_ids": [], "source_groups": [], "regions": [], "topics": [], "content_types": []},
                "exclusions": [], "allowed_output_paths": ["data/a.json"], "definition_of_done": ["done"],
                "idempotency_key": "validation:a",
                "result": {"branch": "work/task_a", "pr_number": 1, "completed_at": "2026-08-04T02:00:00Z"}
            }
            high = dict(merged)
            high.update({"task_id": "task_b", "state": "ready", "priority": 90, "depends_on_task_ids": ["task_a"], "idempotency_key": "validation:b"})
            high.pop("result", None)
            low = dict(high)
            low.update({"task_id": "task_c", "priority": 10, "idempotency_key": "validation:c"})
            blocked = dict(high)
            blocked.update({"task_id": "task_d", "depends_on_task_ids": ["task_missing"], "idempotency_key": "validation:d"})
            for item in (merged, high, low, blocked):
                (root / f"{item['task_id']}.json").write_text(json.dumps(item), encoding="utf-8")
            self.assertEqual(["task_b", "task_c"], [task.task_id for task in ready_tasks(root)])

    def test_ten_parallel_workers_only_one_claims(self) -> None:
        task = Task(Path("task.json"), {"task_id": "task_race", "state": "ready"})
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory)
            barrier = threading.Barrier(10)
            results: list[bool] = []
            lock = threading.Lock()

            def worker(index: int) -> None:
                barrier.wait()
                claimed = claim_local(task, state_dir, f"run_worker_{index}", now=datetime(2026, 8, 4, tzinfo=UTC))
                with lock:
                    results.append(claimed)

            threads = [threading.Thread(target=worker, args=(index,)) for index in range(10)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(1, sum(results))
            owner = json.loads((state_dir / "leases" / "task_race.json").read_text())
            with self.assertRaises(PermissionError):
                release_local("task_race", state_dir, "run_not_owner")
            self.assertTrue(release_local("task_race", state_dir, owner["worker_run_id"]))

    def test_queue_validator_detects_duplicate_key_and_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = {
                "task_type": "validation", "role": "release-validator", "state": "planned", "priority": 50,
                "window": {"from": "2026-08-04T00:00:00Z", "to": "2026-08-04T01:00:00Z"},
                "scope": {"source_ids": [], "source_groups": [], "regions": [], "topics": [], "content_types": []},
                "exclusions": [], "allowed_output_paths": ["data/a.json"], "definition_of_done": ["done"],
                "idempotency_key": "same-key", "lease": None
            }
            (root / "a.json").write_text(json.dumps(dict(base, task_id="task_a", depends_on_task_ids=["task_b"])), encoding="utf-8")
            (root / "b.json").write_text(json.dumps(dict(base, task_id="task_b", depends_on_task_ids=["task_a"])), encoding="utf-8")
            errors = validate_queue(root, ROUTING)
            self.assertTrue(any("duplicate idempotency_key" in error for error in errors))
            self.assertTrue(any("dependency cycle" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
