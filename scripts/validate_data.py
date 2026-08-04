#!/usr/bin/env python3
"""Validate repository records, schemas, identifiers, references, and key temporal invariants."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_SUFFIXES = {".json", ".geojson", ".ndjson"}


@dataclass(frozen=True)
class Dataset:
    name: str
    relative_root: str
    schema_name: str
    id_field: str


DATASETS = (
    Dataset("sources", "catalogs/sources", "source-profile.schema.json", "source_entity_id"),
    Dataset("source_items", "data/source-items", "source-item.schema.json", "source_item_id"),
    Dataset("artifacts", "data/artifacts", "artifact.schema.json", "artifact_id"),
    Dataset("observations", "data/observations", "observation.schema.json", "observation_id"),
    Dataset("claims", "data/claims", "claim.schema.json", "claim_id"),
    Dataset("events", "data/events", "event.schema.json", "event_id"),
    Dataset("reactions", "data/reactions", "reaction.schema.json", "reaction_id"),
    Dataset("assessments", "data/assessments", "assessment.schema.json", "assessment_id"),
    Dataset("corrections", "data/corrections", "correction.schema.json", "correction_id"),
    Dataset("reports", "data/reports", "report.schema.json", "report_id"),
    Dataset("map_features", "maps/layers", "map-feature.schema.json", "id"),
    Dataset("map_snapshots", "maps/snapshots", "map-snapshot.schema.json", "snapshot_id"),
    Dataset("tasks", "tasks", "task-manifest.schema.json", "task_id"),
)

AFFECTED_RECORD_TARGETS = {
    "source_item": "source_items",
    "observation": "observations",
    "claim": "claims",
    "event": "events",
    "assessment": "assessments",
    "reaction": "reactions",
    "map_feature": "map_features",
    "report": "reports",
}


@dataclass(frozen=True)
class Record:
    dataset: str
    path: Path
    index: int
    value: dict[str, Any]

    @property
    def location(self) -> str:
        return f"{self.path}[{self.index}]"


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iter_documents(path: Path) -> Iterable[dict[str, Any]]:
    """Yield object records from JSON, GeoJSON, or newline-delimited JSON."""
    if path.suffix == ".ndjson":
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{number}: NDJSON record must be an object")
            yield value
        return

    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        for index, record in enumerate(value):
            if not isinstance(record, dict):
                raise ValueError(f"{path}[{index}]: array record must be an object")
            yield record
        return

    if isinstance(value, dict) and value.get("type") == "FeatureCollection":
        features = value.get("features")
        if not isinstance(features, list):
            raise ValueError(f"{path}: FeatureCollection.features must be an array")
        for index, feature in enumerate(features):
            if not isinstance(feature, dict):
                raise ValueError(f"{path}.features[{index}]: feature must be an object")
            yield feature
        return

    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level JSON value must be an object or array")
    yield value


def load_validators(schema_dir: Path) -> tuple[dict[str, Draft202012Validator], list[str]]:
    validators: dict[str, Draft202012Validator] = {}
    errors: list[str] = []
    for dataset in DATASETS:
        path = schema_dir / dataset.schema_name
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            validators[dataset.name] = Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            )
        except (OSError, json.JSONDecodeError, Exception) as exc:
            errors.append(f"{path}: invalid schema: {exc}")
    return validators, errors


def load_records(
    root: Path,
    validators: dict[str, Draft202012Validator],
) -> tuple[dict[str, list[Record]], list[str]]:
    records: dict[str, list[Record]] = {dataset.name: [] for dataset in DATASETS}
    errors: list[str] = []

    for dataset in DATASETS:
        directory = root / dataset.relative_root
        if not directory.exists():
            continue
        validator = validators.get(dataset.name)
        if validator is None:
            continue

        for path in sorted(directory.rglob("*")):
            if path.suffix not in SUPPORTED_SUFFIXES:
                continue
            try:
                documents = list(iter_documents(path))
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                errors.append(str(exc))
                continue

            for index, document in enumerate(documents):
                record = Record(dataset.name, path.relative_to(root), index, document)
                records[dataset.name].append(record)
                schema_errors = sorted(
                    validator.iter_errors(document),
                    key=lambda error: tuple(str(part) for part in error.absolute_path),
                )
                for error in schema_errors:
                    field = ".".join(str(part) for part in error.absolute_path) or "<root>"
                    errors.append(f"{record.location} {field}: {error.message}")
    return records, errors


def build_indexes(
    records: dict[str, list[Record]],
) -> tuple[dict[str, dict[str, Record]], list[str]]:
    indexes: dict[str, dict[str, Record]] = {dataset.name: {} for dataset in DATASETS}
    errors: list[str] = []

    dataset_by_name = {dataset.name: dataset for dataset in DATASETS}
    for name, values in records.items():
        id_field = dataset_by_name[name].id_field
        for record in values:
            record_id = record.value.get(id_field)
            if not isinstance(record_id, str):
                continue
            previous = indexes[name].get(record_id)
            if previous:
                errors.append(
                    f"{record.location} {id_field}: duplicate {record_id}; "
                    f"first defined at {previous.location}"
                )
            else:
                indexes[name][record_id] = record
    return indexes, errors


def require_reference(
    errors: list[str],
    record: Record,
    field: str,
    value: Any,
    target: str,
    indexes: dict[str, dict[str, Record]],
) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        return
    if value not in indexes[target]:
        errors.append(f"{record.location} {field}: unresolved reference {value}")


def require_reference_list(
    errors: list[str],
    record: Record,
    field: str,
    values: Any,
    target: str,
    indexes: dict[str, dict[str, Record]],
) -> None:
    if not isinstance(values, list):
        return
    for index, value in enumerate(values):
        require_reference(errors, record, f"{field}[{index}]", value, target, indexes)


def check_range(
    errors: list[str],
    record: Record,
    start_field: str,
    start: Any,
    end_field: str,
    end: Any,
) -> None:
    if not isinstance(start, str) or not isinstance(end, str):
        return
    try:
        if parse_datetime(end) < parse_datetime(start):
            errors.append(f"{record.location}: {end_field} precedes {start_field}")
    except ValueError:
        return


def check_event_time(errors: list[str], record: Record) -> None:
    event_time = record.value.get("event_time")
    if isinstance(event_time, dict):
        check_range(errors, record, "event_time.start", event_time.get("start"), "event_time.end", event_time.get("end"))


def check_references_and_invariants(
    root: Path,
    records: dict[str, list[Record]],
    indexes: dict[str, dict[str, Record]],
) -> list[str]:
    errors: list[str] = []

    for record in records["sources"]:
        for assessment_index, assessment in enumerate(record.value.get("assessments", [])):
            require_reference_list(
                errors, record, f"assessments[{assessment_index}].evidence_claim_ids",
                assessment.get("evidence_claim_ids"), "claims", indexes
            )

    for record in records["source_items"]:
        require_reference(errors, record, "source_entity_id", record.value.get("source_entity_id"), "sources", indexes)
        require_reference_list(errors, record, "upstream_item_ids", record.value.get("upstream_item_ids"), "source_items", indexes)
        require_reference(errors, record, "revision_of_item_id", record.value.get("revision_of_item_id"), "source_items", indexes)
        require_reference_list(errors, record, "artifact_ids", record.value.get("artifact_ids"), "artifacts", indexes)
        published_at = record.value.get("published_at")
        retrieved_at = record.value.get("retrieved_at")
        check_range(errors, record, "published_at", published_at, "retrieved_at", retrieved_at)
        if record.value.get("source_item_id") in set(record.value.get("upstream_item_ids", [])):
            errors.append(f"{record.location} upstream_item_ids: item cannot cite itself as upstream")

    for record in records["artifacts"]:
        require_reference(errors, record, "source_item_id", record.value.get("source_item_id"), "source_items", indexes)

    for record in records["observations"]:
        require_reference(errors, record, "source_item_id", record.value.get("source_item_id"), "source_items", indexes)
        require_reference(errors, record, "speaker_entity_id", record.value.get("speaker_entity_id"), "sources", indexes)
        require_reference_list(errors, record, "artifact_ids", record.value.get("artifact_ids"), "artifacts", indexes)
        check_event_time(errors, record)

    for record in records["claims"]:
        evidence = record.value.get("evidence", [])
        for index, relation in enumerate(evidence if isinstance(evidence, list) else []):
            if isinstance(relation, dict):
                require_reference(
                    errors, record, f"evidence[{index}].observation_id",
                    relation.get("observation_id"), "observations", indexes
                )
        require_reference_list(errors, record, "event_ids", record.value.get("event_ids"), "events", indexes)
        require_reference(errors, record, "supersedes_claim_id", record.value.get("supersedes_claim_id"), "claims", indexes)
        if record.value.get("supersedes_claim_id") == record.value.get("claim_id"):
            errors.append(f"{record.location} supersedes_claim_id: claim cannot supersede itself")
        check_event_time(errors, record)
        check_range(errors, record, "created_at", record.value.get("created_at"), "updated_at", record.value.get("updated_at"))

    for record in records["events"]:
        require_reference_list(errors, record, "claim_ids", record.value.get("claim_ids"), "claims", indexes)
        check_event_time(errors, record)
        check_range(errors, record, "created_at", record.value.get("created_at"), "updated_at", record.value.get("updated_at"))

    for record in records["reactions"]:
        require_reference(errors, record, "reacting_entity_id", record.value.get("reacting_entity_id"), "sources", indexes)
        require_reference(errors, record, "target_item_id", record.value.get("target_item_id"), "source_items", indexes)
        require_reference(errors, record, "target_claim_id", record.value.get("target_claim_id"), "claims", indexes)
        require_reference(errors, record, "observation_id", record.value.get("observation_id"), "observations", indexes)

    for record in records["assessments"]:
        require_reference_list(errors, record, "claim_ids", record.value.get("claim_ids"), "claims", indexes)
        require_reference(errors, record, "supersedes_assessment_id", record.value.get("supersedes_assessment_id"), "assessments", indexes)
        if record.value.get("supersedes_assessment_id") == record.value.get("assessment_id"):
            errors.append(f"{record.location} supersedes_assessment_id: assessment cannot supersede itself")

    for record in records["corrections"]:
        require_reference_list(
            errors, record, "evidence_observation_ids",
            record.value.get("evidence_observation_ids"), "observations", indexes
        )
        for index, affected in enumerate(record.value.get("affected_records", [])):
            if not isinstance(affected, dict):
                continue
            target = AFFECTED_RECORD_TARGETS.get(affected.get("record_type"))
            if target:
                require_reference(
                    errors, record, f"affected_records[{index}].record_id",
                    affected.get("record_id"), target, indexes
                )
        check_range(errors, record, "published_at", record.value.get("published_at"), "corrected_at", record.value.get("corrected_at"))

    for record in records["reports"]:
        require_reference_list(errors, record, "claim_ids", record.value.get("claim_ids"), "claims", indexes)
        require_reference_list(errors, record, "assessment_ids", record.value.get("assessment_ids"), "assessments", indexes)
        require_reference(errors, record, "translation_of_report_id", record.value.get("translation_of_report_id"), "reports", indexes)
        period = record.value.get("period")
        if isinstance(period, dict):
            check_range(errors, record, "period.start", period.get("start"), "period.end", period.get("end"))

    for record in records["map_features"]:
        properties = record.value.get("properties")
        if not isinstance(properties, dict):
            continue
        require_reference_list(errors, record, "properties.claim_ids", properties.get("claim_ids"), "claims", indexes)
        require_reference_list(errors, record, "properties.observation_ids", properties.get("observation_ids"), "observations", indexes)
        require_reference(errors, record, "properties.supersedes_feature_id", properties.get("supersedes_feature_id"), "map_features", indexes)
        if properties.get("supersedes_feature_id") == record.value.get("id"):
            errors.append(f"{record.location} properties.supersedes_feature_id: feature cannot supersede itself")
        check_range(errors, record, "properties.valid_from", properties.get("valid_from"), "properties.valid_to", properties.get("valid_to"))
        check_range(errors, record, "properties.assessed_at", properties.get("assessed_at"), "properties.publish_not_before", properties.get("publish_not_before"))

    for record in records["map_snapshots"]:
        require_reference(errors, record, "previous_snapshot_id", record.value.get("previous_snapshot_id"), "map_snapshots", indexes)
        check_range(errors, record, "publication_cutoff", record.value.get("publication_cutoff"), "as_of", record.value.get("as_of"))
        for index, relative_path in enumerate(record.value.get("feature_files", [])):
            if isinstance(relative_path, str) and not (root / relative_path).is_file():
                errors.append(f"{record.location} feature_files[{index}]: file does not exist: {relative_path}")

    for record in records["tasks"]:
        scope = record.value.get("scope")
        if isinstance(scope, dict):
            require_reference_list(errors, record, "scope.source_ids", scope.get("source_ids"), "sources", indexes)
        window = record.value.get("window")
        if isinstance(window, dict):
            check_range(errors, record, "window.from", window.get("from"), "window.to", window.get("to"))
        lease = record.value.get("lease")
        if isinstance(lease, dict):
            check_range(errors, record, "lease.leased_at", lease.get("leased_at"), "lease.lease_until", lease.get("lease_until"))

    return errors


def validate_repository(root: Path, schema_dir: Path | None = None) -> list[str]:
    schema_dir = schema_dir or root / "schemas"
    validators, errors = load_validators(schema_dir)
    records, record_errors = load_records(root, validators)
    errors.extend(record_errors)
    indexes, index_errors = build_indexes(records)
    errors.extend(index_errors)
    errors.extend(check_references_and_invariants(root, records, indexes))
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--schema-dir", type=Path)
    args = parser.parse_args()

    errors = validate_repository(args.root.resolve(), args.schema_dir.resolve() if args.schema_dir else None)
    if errors:
        print("Repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Repository schemas, records, references, and invariants passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
