from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_task_changed_paths.py"
SPEC = importlib.util.spec_from_file_location("validate_task_changed_paths", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TaskChangedPathsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        self.git("init", "-b", "main")
        self.git("config", "user.email", "tests@example.invalid")
        self.git("config", "user.name", "Validator Tests")
        self.write("README.md", "base\n")
        self.git("add", ".")
        self.git("commit", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return completed.stdout

    def write(self, path: str, content: str) -> None:
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def add_task_commit(self, *, changed_path: str, allowed_path: str) -> str:
        task_id = "task_example"
        manifest_path = f"tasks/2026/08/06/{task_id}.json"
        manifest = {
            "task_id": task_id,
            "allowed_output_paths": [allowed_path],
        }
        self.write(manifest_path, json.dumps(manifest))
        self.write(changed_path, "result\n")
        self.git("add", ".")
        self.git("commit", "-m", "task work")
        return self.git("rev-parse", "HEAD").strip()

    def test_allows_declared_output_and_manifest(self) -> None:
        head = self.add_task_commit(
            changed_path="data/results/example.ndjson",
            allowed_path="data/results/example.ndjson",
        )
        manifest, changed, violations = MODULE.validate(
            repo=self.repo,
            base=self.base,
            head=head,
            head_ref="work/task_example",
        )
        self.assertEqual(manifest, "tasks/2026/08/06/task_example.json")
        self.assertEqual(
            set(changed),
            {manifest, "data/results/example.ndjson"},
        )
        self.assertEqual(violations, [])

    def test_allows_recursive_glob_output(self) -> None:
        head = self.add_task_commit(
            changed_path="data/results/2026/08/example.ndjson",
            allowed_path="data/results/**",
        )
        _, _, violations = MODULE.validate(
            repo=self.repo,
            base=self.base,
            head=head,
            head_ref="work/task_example",
        )
        self.assertEqual(violations, [])

    def test_allows_single_level_glob_output(self) -> None:
        head = self.add_task_commit(
            changed_path="data/results/example.ndjson",
            allowed_path="data/results/*.ndjson",
        )
        _, _, violations = MODULE.validate(
            repo=self.repo,
            base=self.base,
            head=head,
            head_ref="work/task_example",
        )
        self.assertEqual(violations, [])

    def test_glob_does_not_authorize_sibling_path(self) -> None:
        head = self.add_task_commit(
            changed_path="data/other/example.ndjson",
            allowed_path="data/results/**",
        )
        _, _, violations = MODULE.validate(
            repo=self.repo,
            base=self.base,
            head=head,
            head_ref="work/task_example",
        )
        self.assertEqual(violations, ["data/other/example.ndjson"])

    def test_single_level_glob_does_not_match_nested_path(self) -> None:
        head = self.add_task_commit(
            changed_path="data/results/nested/example.ndjson",
            allowed_path="data/results/*.ndjson",
        )
        _, _, violations = MODULE.validate(
            repo=self.repo,
            base=self.base,
            head=head,
            head_ref="work/task_example",
        )
        self.assertEqual(violations, ["data/results/nested/example.ndjson"])

    def test_allows_mandatory_derived_receipts_without_contract_mutation(self) -> None:
        task_id = "task_example"
        manifest_path = f"tasks/2026/08/06/{task_id}.json"
        self.write(
            manifest_path,
            json.dumps(
                {
                    "task_id": task_id,
                    "allowed_output_paths": ["data/results/example.ndjson"],
                }
            ),
        )
        self.write("data/results/example.ndjson", "result\n")
        self.write(f"review/self/{task_id}.json", "{}\n")
        self.write(f"queue/proposals/{task_id}.json", "{}\n")
        self.git("add", ".")
        self.git("commit", "-m", "task work with derived receipts")
        head = self.git("rev-parse", "HEAD").strip()

        manifest, changed, violations = MODULE.validate(
            repo=self.repo,
            base=self.base,
            head=head,
            head_ref=f"work/{task_id}",
        )

        self.assertEqual(manifest, manifest_path)
        self.assertEqual(
            set(changed),
            {
                manifest_path,
                "data/results/example.ndjson",
                f"review/self/{task_id}.json",
                f"queue/proposals/{task_id}.json",
            },
        )
        self.assertEqual(violations, [])

    def test_rejects_undeclared_output(self) -> None:
        head = self.add_task_commit(
            changed_path="reports/unauthorized.md",
            allowed_path="data/results/example.ndjson",
        )
        _, _, violations = MODULE.validate(
            repo=self.repo,
            base=self.base,
            head=head,
            head_ref="work/task_example",
        )
        self.assertEqual(violations, ["reports/unauthorized.md"])

    def test_skips_non_task_branch(self) -> None:
        manifest, changed, violations = MODULE.validate(
            repo=self.repo,
            base=self.base,
            head=self.base,
            head_ref="hardening/example",
        )
        self.assertIsNone(manifest)
        self.assertEqual(changed, [])
        self.assertEqual(violations, [])

    def test_requires_unique_matching_manifest(self) -> None:
        self.write(
            "tasks/2026/08/06/task_example.json",
            json.dumps({"task_id": "task_example", "allowed_output_paths": ["data/a"]}),
        )
        self.write(
            "tasks/2026/08/07/task_example.json",
            json.dumps({"task_id": "task_example", "allowed_output_paths": ["data/b"]}),
        )
        self.git("add", ".")
        self.git("commit", "-m", "duplicates")
        head = self.git("rev-parse", "HEAD").strip()
        with self.assertRaisesRegex(MODULE.ValidationError, "multiple task manifests"):
            MODULE.validate(
                repo=self.repo,
                base=self.base,
                head=head,
                head_ref="work/task_example",
            )

    def test_rejects_unsafe_declared_path(self) -> None:
        head = self.add_task_commit(
            changed_path="data/results/example.ndjson",
            allowed_path="../outside",
        )
        with self.assertRaisesRegex(MODULE.ValidationError, "unsafe path"):
            MODULE.validate(
                repo=self.repo,
                base=self.base,
                head=head,
                head_ref="work/task_example",
            )


if __name__ == "__main__":
    unittest.main()
