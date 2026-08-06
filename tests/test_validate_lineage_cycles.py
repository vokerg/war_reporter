from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_lineage_cycles import validate_repository


class ValidateLineageCyclesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_ndjson(self, relative_path: str, records: list[dict[str, object]]) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

    def write_json(self, relative_path: str, value: object) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_accepts_acyclic_lineage_graphs(self) -> None:
        self.write_ndjson(
            "data/source-items/items.ndjson",
            [
                {"source_item_id": "item_a"},
                {"source_item_id": "item_b", "upstream_item_ids": ["item_a"]},
                {"source_item_id": "item_c", "revision_of_item_id": "item_b"},
            ],
        )
        self.write_ndjson(
            "data/claims/claims.ndjson",
            [
                {"claim_id": "clm_a"},
                {"claim_id": "clm_b", "supersedes_claim_id": "clm_a"},
            ],
        )
        self.write_json(
            "data/reports/reports.json",
            [
                {"report_id": "rpt_a"},
                {"report_id": "rpt_b", "translation_of_report_id": "rpt_a"},
            ],
        )
        self.write_json(
            "maps/snapshots/snapshots.json",
            [
                {"snapshot_id": "map_a"},
                {"snapshot_id": "map_b", "previous_snapshot_id": "map_a"},
            ],
        )
        self.assertEqual([], validate_repository(self.root))

    def test_rejects_cycles_in_every_supported_graph(self) -> None:
        self.write_ndjson(
            "data/source-items/items.ndjson",
            [
                {"source_item_id": "item_a", "upstream_item_ids": ["item_b"]},
                {"source_item_id": "item_b", "revision_of_item_id": "item_a"},
            ],
        )
        self.write_ndjson(
            "data/claims/claims.ndjson",
            [
                {"claim_id": "clm_a", "supersedes_claim_id": "clm_b"},
                {"claim_id": "clm_b", "supersedes_claim_id": "clm_a"},
            ],
        )
        self.write_json(
            "data/reports/reports.json",
            [
                {"report_id": "rpt_a", "translation_of_report_id": "rpt_b"},
                {"report_id": "rpt_b", "translation_of_report_id": "rpt_a"},
            ],
        )
        self.write_json(
            "maps/snapshots/snapshots.json",
            [
                {"snapshot_id": "map_a", "previous_snapshot_id": "map_b"},
                {"snapshot_id": "map_b", "previous_snapshot_id": "map_a"},
            ],
        )
        errors = validate_repository(self.root)
        self.assertEqual(4, len(errors))
        self.assertTrue(any("source-item lineage cycle" in error for error in errors))
        self.assertTrue(any("claim supersession cycle" in error for error in errors))
        self.assertTrue(any("report translation cycle" in error for error in errors))
        self.assertTrue(any("map snapshot lineage cycle" in error for error in errors))

    def test_rejects_self_references(self) -> None:
        self.write_ndjson(
            "data/claims/claims.ndjson",
            [{"claim_id": "clm_a", "supersedes_claim_id": "clm_a"}],
        )
        errors = validate_repository(self.root)
        self.assertEqual(1, len(errors))
        self.assertIn("clm_a", errors[0])

    def test_rejects_duplicate_identifiers(self) -> None:
        self.write_ndjson(
            "data/source-items/items.ndjson",
            [{"source_item_id": "item_a"}, {"source_item_id": "item_a"}],
        )
        errors = validate_repository(self.root)
        self.assertEqual(1, len(errors))
        self.assertIn("duplicate source_item_id", errors[0])

    def test_reports_malformed_ndjson_with_path_and_line(self) -> None:
        path = self.root / "data/claims/claims.ndjson"
        path.parent.mkdir(parents=True)
        path.write_text('{"claim_id":"clm_a"}\nnot-json\n', encoding="utf-8")
        errors = validate_repository(self.root)
        self.assertEqual(1, len(errors))
        self.assertIn("claims.ndjson:2", errors[0])


if __name__ == "__main__":
    unittest.main()
