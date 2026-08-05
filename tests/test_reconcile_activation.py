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


class ReconcileActivationTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        dump(
            root / "config/autonomy.json",
            {
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
            },
        )
        (root / "tasks").mkdir(parents=True, exist_ok=True)
        return root

    def test_utc_day_that_started_before_activation_is_not_scheduled(self) -> None:
        root = self.make_root()
        plan = reconcile.plan_duties(
            root,
            datetime(2026, 8, 6, 10, 0, tzinfo=UTC),
        )
        self.assertEqual(plan["target_day"], "2026-08-05")
        self.assertEqual(plan["duties"], [])
        self.assertEqual(plan["blockers"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
