from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import reconcile_repository as reconcile


class AugustFiveBackfillTests(unittest.TestCase):
    def test_activation_includes_the_full_reporting_day(self) -> None:
        config = json.loads((REPO_ROOT / "config/autonomy.json").read_text(encoding="utf-8"))
        start, _ = reconcile.utc_day_window(date(2026, 8, 5))
        self.assertLessEqual(reconcile.parse(config["activation_not_before"]), start)

    def test_pilot_and_backfill_tasks_cover_every_shard_for_the_full_day(self) -> None:
        tasks = reconcile.task_index(REPO_ROOT)
        by_shard, covered = reconcile.discovery_coverage_for_day(
            tasks,
            date(2026, 8, 5),
            "ukraine-war",
        )
        self.assertEqual(set(covered), {slug for slug, _, _ in reconcile.DISCOVERY_SHARDS})
        self.assertTrue(all(covered.values()))
        for slug, shard_tasks in by_shard.items():
            self.assertTrue(
                any(str(task["task_id"]).startswith("task_backfill_20260805_") for task in shard_tasks),
                f"{slug} has no explicit recovery task",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
