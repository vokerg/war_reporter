#!/usr/bin/env python3
"""Populate canonical retrieval timestamps on legacy raw-manifest records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

CANDIDATE_FIELDS = (
    "searched_at",
    "scan_completed_at",
    "completed_at",
    "generated_at",
    "updated_at",
    "created_at",
)
NESTED_RETRIEVAL_FIELDS = {
    "retrieved_at",
    "searched_at",
    "checked_at",
    "accessed_at",
}


def _nested_timestamp_candidates(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in NESTED_RETRIEVAL_FIELDS and isinstance(item, str):
                yield item
            yield from _nested_timestamp_candidates(item)
    elif isinstance(value, list):
        for item in value:
            yield from _nested_timestamp_candidates(item)


def derive_retrieved_at(record: dict[str, Any]) -> tuple[str, str]:
    for field in CANDIDATE_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value:
            return value, field
    nested = sorted(set(_nested_timestamp_candidates(record)))
    if nested:
        return nested[-1], "nested_retrieval_timestamp"
    raise ValueError("raw manifest has no timestamp suitable for retrieved_at migration")


def migrate_raw_manifests(root: Path) -> list[dict[str, str]]:
    base = root / "raw-manifests"
    if not base.exists():
        return []
    migrations: list[dict[str, str]] = []
    for path in sorted(base.rglob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        records = value if isinstance(value, list) else [value]
        modified = False
        for index, record in enumerate(records):
            if not isinstance(record, dict) or isinstance(record.get("retrieved_at"), str):
                continue
            timestamp, source_field = derive_retrieved_at(record)
            record["retrieved_at"] = timestamp
            migrations.append({
                "path": str(path.relative_to(root)),
                "record_index": str(index),
                "source_field": source_field,
                "retrieved_at": timestamp,
            })
            modified = True
        if modified:
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return migrations


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(migrate_raw_manifests(args.root.resolve()), ensure_ascii=False, indent=2))
