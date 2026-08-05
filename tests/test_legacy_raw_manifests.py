from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_legacy_raw_manifests import migrate_raw_manifests


class LegacyRawManifestMigrationTests(unittest.TestCase):
    def test_searched_at_becomes_retrieved_at_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "raw-manifests/2026/08/04/example.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "task_id": "task_example",
                "worker_run_id": "run_example",
                "searched_at": "2026-08-05T04:42:39Z",
                "window": {
                    "from": "2026-08-04T00:00:00Z",
                    "to": "2026-08-05T00:00:00Z",
                },
            }), encoding="utf-8")

            migrations = migrate_raw_manifests(root)
            self.assertEqual("searched_at", migrations[0]["source_field"])
            migrated = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("2026-08-05T04:42:39Z", migrated["retrieved_at"])
            self.assertEqual([], migrate_raw_manifests(root))

    def test_missing_retrieval_timestamp_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "raw-manifests/example.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"task_id": "task_example"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no timestamp suitable"):
                migrate_raw_manifests(root)


if __name__ == "__main__":
    unittest.main()
