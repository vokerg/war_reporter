from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CollectionWorkflowGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (
            ROOT / ".github/workflows/collect.yml"
        ).read_text(encoding="utf-8")

    def test_generated_output_is_validated_before_upload(self) -> None:
        workflow = self.workflow
        package = workflow.index(
            "python -m scripts.package_collection_artifact"
        )
        upload = workflow.index("uses: actions/upload-artifact@v4")
        self.assertLess(package, upload)
        self.assertIn("if: always()", workflow[:upload])
        self.assertIn(
            "if: steps.package.outcome == 'success'",
            workflow,
        )
        self.assertIn("collection-artifact-manifest.json", workflow)

    def test_upload_and_persist_do_not_own_operator_summaries(self) -> None:
        workflow = self.workflow
        self.assertIn("            reports/daily\n", workflow)
        self.assertNotIn("            reports\n", workflow)
        self.assertIn("git add data reports/daily", workflow)
        self.assertNotIn("git add data reports\n", workflow)

    def test_write_job_verifies_before_git_add(self) -> None:
        workflow = self.workflow
        persist = workflow.index("  persist:")
        verify = workflow.index(
            "python -I scripts/verify_collection_artifact.py",
            persist,
        )
        git_add = workflow.index("git add data reports/daily", persist)
        self.assertLess(verify, git_add)
        self.assertNotIn("pip install", workflow[persist:])

    def test_rebase_result_is_validated_before_push(self) -> None:
        workflow = self.workflow
        persist = workflow.index("  persist:")
        pull = workflow.index("pull --rebase", persist)
        validate = workflow.index("python -m scripts.validate", pull)
        push = workflow.index("push origin", validate)
        self.assertLess(pull, validate)
        self.assertLess(validate, push)

    def test_write_permission_is_scoped_to_persist_job(self) -> None:
        self.assertEqual(self.workflow.count("contents: write"), 1)
        persist = self.workflow.index("  persist:")
        write = self.workflow.index("contents: write")
        self.assertGreater(write, persist)

    def test_partial_collection_can_upload_without_masking_terminal_failures(self) -> None:
        workflow = self.workflow
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("Enforce collector terminal status", workflow)
        self.assertIn('status == "partial"', workflow)
        self.assertIn('status in {"blocked", "failed"}', workflow)
        upload = workflow.index("uses: actions/upload-artifact@v4")
        enforce = workflow.index("Enforce collector terminal status")
        self.assertLess(upload, enforce)


if __name__ == "__main__":
    unittest.main()
