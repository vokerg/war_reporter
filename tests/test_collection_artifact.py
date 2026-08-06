from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.verify_collection_artifact import verify_artifact


class CollectionArtifactVerifierTests(unittest.TestCase):
    def make_root(self) -> tuple[Path, Path]:
        root = Path(tempfile.mkdtemp())
        (root / "data").mkdir()
        (root / "reports").mkdir()
        (root / "data/state.json").write_text('{"status":"partial"}\n')
        (root / "reports/day.md").write_text("# digest\n")
        rows = []
        total = 0
        for relative in ("data/state.json", "reports/day.md"):
            path = root / relative
            payload = path.read_bytes()
            total += len(payload)
            rows.append(
                {
                    "path": relative,
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        manifest = {
            "schema": "war-reporter-collection-artifact-v1",
            "state_status": "partial",
            "last_run_at": "2026-08-06T12:00:00Z",
            "files": rows,
            "file_count": len(rows),
            "total_bytes": total,
        }
        manifest_path = root / "collection-artifact-manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        return root, manifest_path

    def test_valid_manifest_passes(self) -> None:
        root, manifest = self.make_root()
        value = verify_artifact(root, manifest)
        self.assertEqual(value["state_status"], "partial")

    def test_modified_file_fails(self) -> None:
        root, manifest = self.make_root()
        (root / "reports/day.md").write_text("changed")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            verify_artifact(root, manifest)

    def test_extra_file_fails(self) -> None:
        root, manifest = self.make_root()
        (root / "data/extra.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "file set mismatch"):
            verify_artifact(root, manifest)

    def test_removed_file_fails(self) -> None:
        root, manifest = self.make_root()
        (root / "reports/day.md").unlink()
        with self.assertRaisesRegex(ValueError, "file set mismatch"):
            verify_artifact(root, manifest)

    def test_symlink_fails(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unsupported")
        root, manifest = self.make_root()
        target = root / "outside.txt"
        target.write_text("outside")
        link = root / "data/link"
        try:
            link.symlink_to(target)
        except OSError as exc:
            self.skipTest(str(exc))
        with self.assertRaisesRegex(ValueError, "symlink"):
            verify_artifact(root, manifest)

    def test_manifest_cannot_reference_outside_path(self) -> None:
        root, manifest_path = self.make_root()
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][0]["path"] = "../secret"
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "outside allowed roots"):
            verify_artifact(root, manifest_path)

    def test_manifest_must_be_inside_checkout(self) -> None:
        root, manifest = self.make_root()
        outside = Path(tempfile.mkdtemp()) / "manifest.json"
        outside.write_bytes(manifest.read_bytes())
        with self.assertRaisesRegex(ValueError, "inside the artifact checkout"):
            verify_artifact(root, outside)


if __name__ == "__main__":
    unittest.main()
