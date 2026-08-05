from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/build_site.py"
SPEC = importlib.util.spec_from_file_location("build_site", MODULE_PATH)
assert SPEC and SPEC.loader
build_site = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = build_site
SPEC.loader.exec_module(build_site)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class BuildSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "site/assets").mkdir(parents=True)
        (self.root / "site/index.html").write_text("<html></html>\n", encoding="utf-8")
        (self.root / "site/assets/app.js").write_text("console.log('ok');\n", encoding="utf-8")
        self.now = datetime(2026, 8, 5, 16, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def report_manifest(self, *, report_id: str, status: str = "approved") -> dict[str, object]:
        return {
            "report_id": report_id,
            "report_type": "daily",
            "language": "en",
            "period": {"start": "2026-08-04T00:00:00Z", "end": "2026-08-05T00:00:00Z"},
            "as_of": "2026-08-05T00:00:00Z",
            "content_path": f"reports/daily/{report_id}.md",
            "claim_ids": ["clm_alpha"],
            "assessment_ids": ["asm_alpha"],
            "claim_set_sha256": "a" * 64,
            "record_status": status,
            "generated_at": "2026-08-05T01:00:00Z",
        }

    def map_feature(
        self,
        feature_id: str,
        *,
        record_status: str = "approved",
        publication_status: str = "public",
        publish_not_before: str = "2026-08-05T10:00:00Z",
    ) -> dict[str, object]:
        return {
            "type": "Feature",
            "id": feature_id,
            "geometry": {"type": "Point", "coordinates": [31.0, 49.0]},
            "properties": {
                "feature_type": "strike_assessment",
                "record_status": record_status,
                "assessment_outcome": "confirmed",
                "valid_from": "2026-08-04T12:00:00Z",
                "assessed_at": "2026-08-05T09:00:00Z",
                "publish_not_before": publish_not_before,
                "precision_m": 5000,
                "uncertainty_method": "generalized",
                "publication_status": publication_status,
                "claim_ids": ["clm_alpha"],
                "observation_ids": ["obs_alpha"],
            },
        }

    def test_empty_repository_builds_explicit_empty_catalog(self) -> None:
        output = self.root / "_site"
        result = build_site.build_site(self.root, output, now=self.now, strict=True)
        self.assertEqual(result.report_count, 0)
        self.assertEqual(result.map_feature_count, 0)
        self.assertTrue((output / ".nojekyll").exists())
        catalog = json.loads((output / "data/catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["reports"], [])
        self.assertIsNone(catalog["map"])

    def test_only_approved_reports_are_published(self) -> None:
        approved = self.report_manifest(report_id="rpt_approved")
        draft = self.report_manifest(report_id="rpt_draft", status="draft")
        write_json(self.root / "data/reports/2026/08/04/daily.json", approved)
        write_json(self.root / "data/reports/2026/08/04/draft.json", draft)
        for manifest in (approved, draft):
            content = self.root / str(manifest["content_path"])
            content.parent.mkdir(parents=True, exist_ok=True)
            content.write_text(f"# {manifest['report_id']}\n", encoding="utf-8")

        output = self.root / "_site"
        result = build_site.build_site(self.root, output, now=self.now, strict=True)
        catalog = json.loads((output / "data/catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(result.report_count, 1)
        self.assertEqual([item["report_id"] for item in catalog["reports"]], ["rpt_approved"])
        self.assertTrue((output / "content/reports/rpt_approved.md").exists())
        self.assertFalse((output / "content/reports/rpt_draft.md").exists())

    def test_map_build_filters_embargoed_withheld_and_unapproved_features(self) -> None:
        features = {
            "type": "FeatureCollection",
            "features": [
                self.map_feature("geo_public"),
                self.map_feature("geo_embargoed", publish_not_before="2026-08-06T10:00:00Z"),
                self.map_feature("geo_withheld", publication_status="withheld"),
                self.map_feature("geo_draft", record_status="draft"),
            ],
        }
        write_json(self.root / "maps/layers/2026-08-04.geojson", features)
        snapshot = {
            "snapshot_id": "map_20260805",
            "as_of": "2026-08-05T12:00:00Z",
            "generated_at": "2026-08-05T13:00:00Z",
            "publication_cutoff": "2026-08-05T14:00:00Z",
            "feature_files": ["maps/layers/2026-08-04.geojson"],
            "claim_set_sha256": "b" * 64,
            "record_status": "approved",
        }
        write_json(self.root / "maps/snapshots/2026-08-05.json", snapshot)

        output = self.root / "_site"
        result = build_site.build_site(self.root, output, now=self.now, strict=True)
        public_map = json.loads((output / "data/map.geojson").read_text(encoding="utf-8"))
        self.assertEqual(result.map_snapshot_id, "map_20260805")
        self.assertEqual(result.map_feature_count, 1)
        self.assertEqual([item["id"] for item in public_map["features"]], ["geo_public"])

    def test_strict_build_rejects_report_path_escape(self) -> None:
        manifest = self.report_manifest(report_id="rpt_escape")
        manifest["content_path"] = "../secret.md"
        write_json(self.root / "data/reports/escape.json", manifest)
        with self.assertRaises(ValueError):
            build_site.build_site(self.root, self.root / "_site", now=self.now, strict=True)


if __name__ == "__main__":
    unittest.main()
