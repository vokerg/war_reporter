from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReconcileWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (
            REPO_ROOT / ".github/workflows/reconcile-queue.yml"
        ).read_text(encoding="utf-8")

    def test_legacy_reconciler_has_no_automatic_trigger(self) -> None:
        workflow = self.workflow
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("workflow_run:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("push:", workflow)

    def test_legacy_reconciler_is_read_only_and_cannot_mutate_state(self) -> None:
        workflow = self.workflow
        self.assertIn("permissions:\n  contents: read", workflow)
        for forbidden in (
            "contents: write",
            "issues: write",
            "pull-requests: write",
            "gh issue create",
            "git add -- tasks",
            "git commit",
            "git push",
            "materialize",
            "reconcile_repository.py",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, workflow)

    def test_manual_run_fails_visibly_with_freeze_reason(self) -> None:
        workflow = self.workflow
        self.assertIn("Legacy task/queue reconciliation is frozen", workflow)
        self.assertIn("exit 1", workflow)


if __name__ == "__main__":
    unittest.main()
