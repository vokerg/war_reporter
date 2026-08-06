from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class DeployPagesWorkflowTests(unittest.TestCase):
    def test_successful_finalization_triggers_pages_rebuild(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/deploy-pages.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('workflows: ["Finalize merged worker task"]', workflow)
        self.assertIn("types: [completed]", workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("ref: main", workflow)


if __name__ == "__main__":
    unittest.main()
