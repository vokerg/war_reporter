from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PostFinalizeDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (
            REPO_ROOT / ".github/workflows/finalize-task-merge.yml"
        ).read_text(encoding="utf-8")

    def test_finalizer_can_dispatch_follow_up_workflows(self) -> None:
        self.assertIn("permissions:\n  actions: write\n", self.workflow)
        self.assertIn(
            "gh workflow run reconcile-queue.yml --ref main",
            self.workflow,
        )
        self.assertIn(
            "gh workflow run deploy-pages.yml --ref main",
            self.workflow,
        )

    def test_finalizer_does_not_dispatch_itself(self) -> None:
        self.assertNotIn(
            "gh workflow run finalize-task-merge.yml",
            self.workflow,
        )

    def test_follow_up_dispatches_run_after_finalization_push(self) -> None:
        push = "git push origin HEAD:main"
        reconcile = "gh workflow run reconcile-queue.yml --ref main"
        deploy = "gh workflow run deploy-pages.yml --ref main"

        self.assertLess(self.workflow.index(push), self.workflow.index(reconcile))
        self.assertLess(self.workflow.index(reconcile), self.workflow.index(deploy))


if __name__ == "__main__":
    unittest.main()
