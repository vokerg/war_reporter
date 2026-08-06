from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.common import append_unique, atomic_json


class AtomicStorageTests(unittest.TestCase):
    def test_append_unique_preserves_rows_and_deduplicates(self) -> None:
        root = Path(tempfile.mkdtemp())
        path = root / "items.ndjson"
        path.write_text(json.dumps({"id": "one", "text": "a"}) + "\n")
        added = append_unique(
            path,
            [
                {"id": "one", "text": "duplicate"},
                {"id": "two", "text": "b"},
            ],
        )
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(added, 1)
        self.assertEqual([row["id"] for row in rows], ["one", "two"])
        self.assertEqual(rows[0]["text"], "a")

    def test_corrupt_archive_blocks_append_without_modifying_file(self) -> None:
        root = Path(tempfile.mkdtemp())
        path = root / "items.ndjson"
        original = '{"id":"one"}\n{"id":'
        path.write_text(original)
        with self.assertRaises(ValueError):
            append_unique(path, [{"id": "two"}])
        self.assertEqual(path.read_text(), original)

    def test_duplicate_existing_ids_block_append(self) -> None:
        root = Path(tempfile.mkdtemp())
        path = root / "items.ndjson"
        original = '{"id":"one"}\n{"id":"one"}\n'
        path.write_text(original)
        with self.assertRaisesRegex(ValueError, "duplicate existing item id"):
            append_unique(path, [{"id": "two"}])
        self.assertEqual(path.read_text(), original)

    def test_replace_failure_leaves_previous_json_intact(self) -> None:
        root = Path(tempfile.mkdtemp())
        path = root / "state.json"
        path.write_text('{"old":true}\n')
        with patch("scripts.common.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                atomic_json(path, {"new": True})
        self.assertEqual(path.read_text(), '{"old":true}\n')
        leftovers = [entry for entry in root.iterdir() if entry != path]
        self.assertEqual(leftovers, [])

    def test_ndjson_rows_must_be_objects(self) -> None:
        root = Path(tempfile.mkdtemp())
        path = root / "items.ndjson"
        original = '[1,2,3]\n'
        path.write_text(original)
        with self.assertRaisesRegex(ValueError, "row must be an object"):
            append_unique(path, [{"id": "two"}])
        self.assertEqual(path.read_text(), original)


if __name__ == "__main__":
    unittest.main()
