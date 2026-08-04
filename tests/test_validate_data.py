from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_data",
    REPOSITORY_ROOT / "scripts" / "validate_data.py",
)
assert SPEC and SPEC.loader
validate_data = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_data
SPEC.loader.exec_module(validate_data)


def write_json(root: Path, relative_path: str, value: object) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def source_profile() -> dict:
    return {
        "source_entity_id": "src_example",
        "display_name": "Example Source",
        "entity_type": "outlet",
        "languages": ["en"],
        "topics": ["military_operations"],
        "assessments": [],
        "record_status": "approved",
        "updated_at": "2026-08-04T10:00:00Z",
    }


def source_item() -> dict:
    return {
        "source_item_id": "item_example",
        "source_entity_id": "src_example",
        "canonical_url": "https://example.com/report",
        "published_at": "2026-08-04T09:00:00Z",
        "published_at_precision": "minute",
        "retrieved_at": "2026-08-04T10:00:00Z",
        "language": "en",
        "item_type": "report",
        "content_status": "available",
        "access_method": "public_web",
    }


def observation() -> dict:
    return {
        "observation_id": "obs_example",
        "source_item_id": "item_example",
        "observation_type": "reported_event",
        "original_excerpt": "Example source reports activity near location X.",
        "original_language": "en",
        "quote_locator": "paragraph 3",
        "statement": {
            "canonical": "Activity was reported near location X.",
            "language": "en",
        },
        "record_status": "approved",
        "created_at": "2026-08-04T10:05:00Z",
    }


def claim() -> dict:
    return {
        "claim_id": "clm_example",
        "statement": {
            "canonical": "Activity occurred near location X.",
            "language": "en",
        },
        "claim_type": "reported_activity",
        "record_status": "approved",
        "assessment": {
            "outcome": "unverified",
            "confidence": "high",
            "assessed_at": "2026-08-04T10:10:00Z",
            "rationale": "One attributable report and no independent corroboration.",
        },
        "evidence": [
            {"observation_id": "obs_example", "relation": "supports"}
        ],
        "created_at": "2026-08-04T10:08:00Z",
        "updated_at": "2026-08-04T10:10:00Z",
    }


def map_feature() -> dict:
    return {
        "type": "Feature",
        "id": "geo_example",
        "geometry": {"type": "Point", "coordinates": [37.0, 48.0]},
        "properties": {
            "feature_type": "reported_presence",
            "record_status": "approved",
            "assessment_outcome": "unverified",
            "valid_from": "2026-08-04T09:00:00Z",
            "assessed_at": "2026-08-04T10:10:00Z",
            "publish_not_before": "2026-08-05T10:10:00Z",
            "precision_m": 5000,
            "uncertainty_method": "reported_radius",
            "publication_status": "delayed",
            "claim_ids": ["clm_example"],
            "observation_ids": ["obs_example"],
        },
    }


class RepositoryValidationTests(unittest.TestCase):
    def validate(self, root: Path) -> list[str]:
        return validate_data.validate_repository(root, REPOSITORY_ROOT / "schemas")

    def populate_valid_graph(self, root: Path) -> None:
        write_json(root, "catalogs/sources/example.json", source_profile())
        write_json(root, "data/source-items/example.json", source_item())
        write_json(root, "data/observations/example.json", observation())
        write_json(root, "data/claims/example.json", claim())
        write_json(root, "maps/layers/example.geojson", map_feature())

    def test_valid_minimal_graph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.populate_valid_graph(root)
            self.assertEqual([], self.validate(root))

    def test_duplicate_and_unresolved_ids_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root, "data/source-items/a.json", source_item())
            write_json(root, "data/source-items/b.json", source_item())
            errors = self.validate(root)
            self.assertTrue(any("duplicate item_example" in error for error in errors))
            self.assertTrue(any("unresolved reference src_example" in error for error in errors))

    def test_invalid_geojson_coordinates_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.populate_valid_graph(root)
            feature = map_feature()
            feature["geometry"]["coordinates"] = [200.0, 95.0]
            write_json(root, "maps/layers/example.geojson", feature)
            errors = self.validate(root)
            self.assertTrue(any("not valid under any of the given schemas" in error for error in errors))

    def test_claim_record_status_is_not_assessment_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.populate_valid_graph(root)
            invalid_claim = claim()
            invalid_claim["record_status"] = "confirmed"
            write_json(root, "data/claims/example.json", invalid_claim)
            errors = self.validate(root)
            self.assertTrue(any("record_status" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
