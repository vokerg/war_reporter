from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReconcileWorkflowTests(unittest.TestCase):
    def test_materialization_stages_tasks_before_empty_commit_check(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/reconcile-queue.yml").read_text(encoding="utf-8")
        stage = "git add -- tasks"
        empty_check = "if git diff --cached --quiet; then"
        commit = 'git commit -m "[queue] Reconcile due repository duties"'

        self.assertIn(stage, workflow)
        self.assertIn(empty_check, workflow)
        self.assertNotIn("if git diff --quiet; then", workflow)
        self.assertLess(workflow.index(stage), workflow.index(empty_check))
        self.assertLess(workflow.index(empty_check), workflow.index(commit))

    def test_reconciliation_pushes_validated_commit_directly_to_main(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/reconcile-queue.yml").read_text(encoding="utf-8")

        self.assertIn('workflows: ["Finalize merged worker task"]', workflow)
        self.assertIn("git rebase origin/main", workflow)
        self.assertIn("git push origin HEAD:main", workflow)
        self.assertNotIn("gh pr create", workflow)
        self.assertNotIn("control/reconcile/", workflow)
        self.assertNotIn("git push origin \"HEAD:$branch\"", workflow)


if __name__ == "__main__":
    unittest.main()
