from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from source_watchlist import load_watchlist, source_ids_for_shard
from validate_source_scan_coverage import coverage_errors


class SourceScanCoverageTests(unittest.TestCase):
    def build_repo(self, checks: list[dict[str, str]]) -> Path:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory)
        (directory / "config/source-watchlist").mkdir(parents=True)
        shutil.copy(ROOT / "config/source-watchlist.json", directory / "config/source-watchlist.json")
        for relative in load_watchlist(ROOT)["source_files"]:
            destination = directory / "config" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / "config" / relative, destination)
        source_ids = source_ids_for_shard(load_watchlist(ROOT), "military-analysts")[:2]
        task_path = directory / "tasks/2026/08/06/task_example.json"
        raw_path = directory / "raw-manifests/2026/08/06/military-analysts.json"
        task_path.parent.mkdir(parents=True)
        raw_path.parent.mkdir(parents=True)
        task = {
            "task_id": "task_example",
            "task_type": "open_web_discovery",
            "state": "merged",
            "window": {"from": "2026-08-06T00:00:00Z", "to": "2026-08-07T00:00:00Z"},
            "scope": {"source_ids": source_ids, "source_groups": ["military-analysts"]},
            "allowed_output_paths": ["raw-manifests/2026/08/06/military-analysts.json"],
        }
        task_path.write_text(json.dumps(task), encoding="utf-8")
        raw_path.write_text(json.dumps({"source_checks": checks or [
            {"source_entity_id": source_ids[0], "outcome": "checked_no_in_window_item"},
            {"source_entity_id": source_ids[1], "outcome": "inaccessible"},
        ]}), encoding="utf-8")
        return directory

    def test_complete_source_checks_pass(self) -> None:
        root = self.build_repo([])
        self.assertEqual(coverage_errors(root), [])

    def test_missing_source_check_fails(self) -> None:
        source_ids = source_ids_for_shard(load_watchlist(ROOT), "military-analysts")[:2]
        root = self.build_repo([
            {"source_entity_id": source_ids[0], "outcome": "checked_no_in_window_item"},
        ])
        errors = coverage_errors(root)
        self.assertTrue(any(source_ids[1] in error for error in errors))


if __name__ == "__main__":
    unittest.main()
