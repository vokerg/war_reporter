from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_repository_metadata.py"
SPEC = importlib.util.spec_from_file_location("validate_repository_metadata", MODULE_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class MetadataValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.original_root = validator.ROOT
        validator.ROOT = self.root
        (self.root / ".github/ISSUE_TEMPLATE").mkdir(parents=True)
        (self.root / ".github/workflows").mkdir(parents=True)
        (self.root / ".github/agents").mkdir(parents=True)

    def tearDown(self) -> None:
        validator.ROOT = self.original_root
        self.tempdir.cleanup()

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def valid_fixture(self) -> None:
        self.write(
            ".github/ISSUE_TEMPLATE/task.yml",
            "name: Task\ndescription: Work item\nbody:\n  - type: input\n    id: objective\n    attributes:\n      label: Objective\n",
        )
        self.write(
            ".github/workflows/check.yml",
            "name: Check\non: [pull_request]\njobs:\n  validate:\n    runs-on: ubuntu-latest\n    steps: []\n",
        )
        self.write(".github/CODEOWNERS", "* @owner\n/scripts/ @owner/team\n")
        self.write(
            ".github/agents/source-reader.agent.md",
            "---\nname: source-reader\ndescription: Reads sources.\ntarget: github-copilot\ntools: [read]\n---\n\nRead bounded source material.\n",
        )

    def run_all(self) -> list[str]:
        errors: list[str] = []
        validator.validate_issue_forms(errors)
        validator.validate_workflows(errors)
        validator.validate_codeowners(errors)
        validator.validate_agents(errors)
        return errors

    def test_valid_metadata_passes(self) -> None:
        self.valid_fixture()
        self.assertEqual([], self.run_all())

    def test_reports_path_specific_failures(self) -> None:
        self.write(".github/ISSUE_TEMPLATE/task.yml", "name: Broken\nbody: {}\n")
        self.write(".github/workflows/check.yml", "name: Check\njobs: {}\n")
        self.write(".github/CODEOWNERS", "/scripts/ owner\n")
        self.write(
            ".github/agents/wrong.agent.md",
            "---\nname: another-name\ndescription: ''\ntarget: github-copilot\ntools: read\n---\n",
        )
        errors = self.run_all()
        joined = "\n".join(errors)
        self.assertIn(".github/ISSUE_TEMPLATE/task.yml", joined)
        self.assertIn("body must be a list", joined)
        self.assertIn(".github/workflows/check.yml", joined)
        self.assertIn("missing on trigger", joined)
        self.assertIn("missing catch-all", joined)
        self.assertIn("invalid owner", joined)
        self.assertIn("name must match filename", joined)
        self.assertIn("tools must be a non-empty list", joined)
        self.assertIn("instructions body must be non-empty", joined)

    def test_rejects_malformed_yaml(self) -> None:
        self.valid_fixture()
        self.write(".github/workflows/check.yml", "name: [unterminated\n")
        errors = self.run_all()
        self.assertTrue(any("invalid YAML" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
