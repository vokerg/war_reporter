from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.package_collection_artifact import manifest_path, package_artifact


class ArtifactPackagerTests(unittest.TestCase):
    def test_manifest_path_stays_inside_checkout(self) -> None:
        root = Path(tempfile.mkdtemp()).resolve()
        self.assertEqual(
            manifest_path(root, Path("manifest.json")),
            root / "manifest.json",
        )
        with self.assertRaisesRegex(ValueError, "inside the artifact checkout"):
            manifest_path(root, Path("../outside.json"))
        with self.assertRaisesRegex(ValueError, "inside the artifact checkout"):
            manifest_path(root, Path("."))

    def test_manifest_cannot_be_written_inside_payload_roots(self) -> None:
        root = Path(tempfile.mkdtemp()).resolve()
        for relative in ("data/manifest.json", "reports/manifest.json"):
            with self.assertRaisesRegex(ValueError, "outside data"):
                manifest_path(root, Path(relative))

    def test_packager_writes_validated_manifest_atomically(self) -> None:
        root = Path(tempfile.mkdtemp()).resolve()
        manifest = {
            "schema": "war-reporter-collection-artifact-v1",
            "state_status": "partial",
            "last_run_at": "2026-08-06T12:00:00Z",
            "files": [],
            "file_count": 0,
            "total_bytes": 0,
        }
        with patch(
            "scripts.package_collection_artifact.validate_artifact",
            return_value=manifest,
        ):
            destination, value = package_artifact(root)
        self.assertEqual(value, manifest)
        self.assertEqual(json.loads(destination.read_text()), manifest)

    def test_validation_failure_does_not_create_manifest(self) -> None:
        root = Path(tempfile.mkdtemp()).resolve()
        destination = root / "collection-artifact-manifest.json"
        with patch(
            "scripts.package_collection_artifact.validate_artifact",
            side_effect=ValueError("invalid artifact"),
        ):
            with self.assertRaisesRegex(ValueError, "invalid artifact"):
                package_artifact(root)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
