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

from source_watchlist import assignment_errors, load_watchlist, source_ids_for_shard, write_assignments
from validate_source_watchlist import validate


class SourceWatchlistTests(unittest.TestCase):
    def test_repository_watchlist_validates(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_anchor_sources_are_assigned(self) -> None:
        watchlist = load_watchlist(ROOT)
        military = set(source_ids_for_shard(watchlist, "military-analysts"))
        visual = set(source_ids_for_shard(watchlist, "visual-osint-maps"))
        self.assertTrue(
            {
                "src_michael_kofman",
                "src_rob_lee",
                "src_dara_massicot",
                "src_russia_contingency",
                "src_cit",
                "src_isw",
            }.issubset(military)
        )
        self.assertTrue(
            {
                "src_deepstateua",
                "src_geoconfirmed",
                "src_bellingcat",
                "src_cir_eyes_on_russia",
                "src_black_bird_group",
                "src_frontelligence_insight",
                "src_oryx",
            }.issubset(visual)
        )

    def test_write_assignments_populates_effective_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "tasks/2026/08/06").mkdir(parents=True)
            shutil.copy(ROOT / "config/source-watchlist.json", root / "config/source-watchlist.json")
            for relative in load_watchlist(ROOT)["source_files"]:
                destination = root / "config" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / "config" / relative, destination)
            task_path = root / "tasks/2026/08/06/task_daily_20260806_06_military_analysts.json"
            task = {
                "task_id": "task_daily_20260806_06_military_analysts",
                "task_type": "open_web_discovery",
                "window": {
                    "from": "2026-08-06T00:00:00Z",
                    "to": "2026-08-07T00:00:00Z",
                },
                "scope": {
                    "source_ids": [],
                    "source_groups": [],
                    "regions": ["ukraine-war"],
                    "topics": ["military-analysis"],
                    "content_types": ["article"],
                },
                "allowed_output_paths": [
                    "catalogs/sources/2026/08/06/military-analysts.json",
                    "raw-manifests/2026/08/06/military-analysts.json",
                ],
                "idempotency_key": "daily_discovery:2026-08-05:military-analysts:ukraine-war",
            }
            task_path.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
            changed = write_assignments(root)
            self.assertEqual(
                changed,
                ["tasks/2026/08/06/task_daily_20260806_06_military_analysts.json"],
            )
            self.assertEqual(assignment_errors(root), [])
            updated = json.loads(task_path.read_text(encoding="utf-8"))
            self.assertIn("src_michael_kofman", updated["scope"]["source_ids"])
            self.assertIn("src_cit", updated["scope"]["source_ids"])
            self.assertEqual(updated["scope"]["source_groups"], ["military-analysts"])


if __name__ == "__main__":
    unittest.main()
