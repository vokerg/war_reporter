from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"


class WorkflowBoundaryTests(unittest.TestCase):
    def test_collector_separates_untrusted_execution_from_write_token(self) -> None:
        text = (WORKFLOWS / "collect.yml").read_text()
        collect_block, persist_block = text.split("\n  persist:\n", 1)
        self.assertIn("pip install -r requirements.txt", collect_block)
        self.assertIn("permissions:\n      contents: read", collect_block)
        self.assertIn("persist-credentials: false", collect_block)
        self.assertNotIn("contents: write", collect_block)
        self.assertIn("contents: write", persist_block)
        self.assertNotIn("pip install", persist_block)
        self.assertIn("persist-credentials: false", persist_block)
        self.assertIn("GH_TOKEN: ${{ github.token }}", persist_block)

    def test_pages_deploy_job_does_not_build_or_install(self) -> None:
        text = (WORKFLOWS / "pages.yml").read_text()
        build_block, deploy_block = text.split("\n  deploy:\n", 1)
        self.assertIn("pip install -r requirements.txt", build_block)
        self.assertIn("python -m scripts.validate", build_block)
        self.assertNotIn("pages: write", build_block)
        self.assertNotIn("id-token: write", build_block)
        self.assertIn("pages: write", deploy_block)
        self.assertIn("id-token: write", deploy_block)
        self.assertNotIn("pip install", deploy_block)
        self.assertNotIn("actions/checkout", deploy_block)


if __name__ == "__main__":
    unittest.main()
