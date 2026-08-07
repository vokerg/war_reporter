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
        (root / "config").mkdir()
        (root / "data").mkdir()
        (root / "reports/daily").mkdir(parents=True)
        settings = {
            "state_file": "data/state.json",
            "raw_root": "data/raw",
            "error_root": "data/errors",
            "report_root": "reports/daily",
        }
        (root / "config/settings.json").write_text(json.dumps(settings))
        state = {
            "status": "partial",
            "last_run_at": "2026-08-06T12:00:00Z",
        }
        (root / "data/state.json").write_text(json.dumps(state) + "\n")
        report = root / "reports/daily/2026-08-06.md"
        report.write_text("# digest\n")
        rows = []
        total = 0
        for relative in (
            "data/state.json",
            "reports/daily/2026-08-06.md",
        ):
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
        (root / "reports/daily/2026-08-06.md").write_text("changed")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            verify_artifact(root, manifest)

    def test_unexpected_file_under_allowed_root_fails(self) -> None:
        root, manifest = self.make_root()
        (root / "data/debug-response.html").write_text("secret response")
        with self.assertRaisesRegex(ValueError, "unexpected artifact file"):
            verify_artifact(root, manifest)

    def test_removed_file_fails(self) -> None:
        root, manifest = self.make_root()
        (root / "reports/daily/2026-08-06.md").unlink()
        with self.assertRaisesRegex(ValueError, "file set mismatch"):
            verify_artifact(root, manifest)

    def test_symlink_fails(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unsupported")
        root, manifest = self.make_root()
        target = root / "outside.txt"
        target.write_text("outside")
        link = root / "data/raw"
        try:
            link.symlink_to(target)
        except OSError as exc:
            self.skipTest(str(exc))
        with self.assertRaisesRegex(ValueError, "symlink"):
            verify_artifact(root, manifest)

    def test_top_level_artifact_root_symlink_fails(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unsupported")
        root, manifest = self.make_root()
        data = root / "data"
        backup = root / "real-data"
        data.rename(backup)
        try:
            data.symlink_to(backup, target_is_directory=True)
        except OSError as exc:
            self.skipTest(str(exc))
        with self.assertRaisesRegex(ValueError, "artifact root is a symlink"):
            verify_artifact(root, manifest)

    def test_manifest_symlink_fails(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unsupported")
        root, manifest = self.make_root()
        target = root / "real-manifest.json"
        manifest.rename(target)
        try:
            manifest.symlink_to(target)
        except OSError as exc:
            self.skipTest(str(exc))
        with self.assertRaisesRegex(ValueError, "regular non-symlink"):
            verify_artifact(root, manifest)

    def test_manifest_cannot_reference_outside_contract(self) -> None:
        root, manifest_path = self.make_root()
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][0]["path"] = "data/secret.json"
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "not allowed"):
            verify_artifact(root, manifest_path)

    def test_manifest_must_be_inside_checkout(self) -> None:
        root, manifest = self.make_root()
        outside = Path(tempfile.mkdtemp()) / "manifest.json"
        outside.write_bytes(manifest.read_bytes())
        with self.assertRaisesRegex(ValueError, "inside the artifact checkout"):
            verify_artifact(root, outside)

    def test_manifest_extra_fields_fail(self) -> None:
        root, manifest_path = self.make_root()
        manifest = json.loads(manifest_path.read_text())
        manifest["debug"] = "not allowed"
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "unexpected or missing"):
            verify_artifact(root, manifest_path)

    def test_manifest_state_metadata_must_match_state_file(self) -> None:
        root, manifest_path = self.make_root()
        manifest = json.loads(manifest_path.read_text())
        manifest["state_status"] = "ok"
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "does not match"):
            verify_artifact(root, manifest_path)


if __name__ == "__main__":
    unittest.main()
