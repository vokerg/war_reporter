from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.collection_artifact_contract import (
    artifact_path_allowed,
    artifact_path_ignored,
    configured_paths,
)
from scripts.validate_collection_artifact import artifact_files


class CollectionArtifactContractTests(unittest.TestCase):
    def settings(self) -> dict:
        return {
            "state_file": "data/state.json",
            "raw_root": "data/raw",
            "error_root": "data/errors",
            "report_root": "reports/daily",
        }

    def test_only_configured_artifact_shapes_are_allowed(self) -> None:
        settings = self.settings()
        allowed = (
            "data/state.json",
            "data/raw/2026/08/06/items.ndjson",
            "data/errors/2026/08/06/errors.ndjson",
            "reports/daily/2026-08-06.md",
        )
        denied = (
            "data/debug-response.html",
            "data/raw/items.ndjson",
            "data/raw/2026/8/6/items.ndjson",
            "data/raw/2026/08/06/payload.json",
            "reports/daily/latest.md",
            "reports/summary/2026-08-06.md",
            "reports/weekly/2026-08-03_2026-08-09.md",
            "reports/../secret.md",
        )
        for path in allowed:
            with self.subTest(path=path):
                self.assertTrue(artifact_path_allowed(path, settings))
        for path in denied:
            with self.subTest(path=path):
                self.assertFalse(artifact_path_allowed(path, settings))

    def test_editorial_reports_are_explicitly_outside_artifact(self) -> None:
        self.assertTrue(artifact_path_ignored("reports/summary/2026-08-06.md"))
        self.assertTrue(
            artifact_path_ignored("reports/weekly/2026-08-03_2026-08-09.md")
        )
        self.assertFalse(artifact_path_ignored("reports/daily/2026-08-06.md"))
        self.assertFalse(artifact_path_ignored("data/debug-response.html"))

    def test_configured_roots_cannot_escape_public_payload_roots(self) -> None:
        cases = (
            {**self.settings(), "state_file": "state.json"},
            {**self.settings(), "raw_root": "raw"},
            {**self.settings(), "error_root": "errors"},
            {**self.settings(), "report_root": "daily"},
        )
        for settings in cases:
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    configured_paths(settings)

    def test_packager_ignores_editorial_reports_but_rejects_other_files(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "data").mkdir()
        (root / "reports/summary").mkdir(parents=True)
        (root / "reports/weekly").mkdir(parents=True)
        (root / "data/state.json").write_text("{}")
        summary = root / "reports/summary/2026-08-06.md"
        weekly = root / "reports/weekly/2026-08-03_2026-08-09.md"
        summary.write_text("# operator summary\n")
        weekly.write_text("# operator weekly\n")
        files = artifact_files(root, self.settings())
        self.assertEqual(files, [root / "data/state.json"])

        (root / "data/debug-response.html").write_text("secret")
        with self.assertRaisesRegex(ValueError, "unexpected artifact file"):
            artifact_files(root, self.settings())

    def test_collection_artifact_schema_is_present(self) -> None:
        root = Path(__file__).resolve().parents[1]
        schema = json.loads(
            (root / "schemas/collection-artifact.schema.json").read_text()
        )
        self.assertEqual(
            schema.get("title"),
            "War Reporter collection artifact manifest v1",
        )
        path_pattern = schema["properties"]["files"]["items"][
            "properties"
        ]["path"]["pattern"]
        self.assertIn("data/state", path_pattern)
        self.assertIn("reports/daily", path_pattern)


if __name__ == "__main__":
    unittest.main()
