#!/usr/bin/env python3
"""Validate the canonical source watchlist and its semantic coverage guarantees."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from source_watchlist import DISCOVERY_SHARDS, load_watchlist, load_watchlist_manifest, watchlist_path
from validate_source_scan_coverage import coverage_errors

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def semantic_errors(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sources = value.get("sources", [])
    ids = [source.get("source_entity_id") for source in sources if isinstance(source, dict)]
    duplicates = sorted(source_id for source_id, count in Counter(ids).items() if count > 1)
    for source_id in duplicates:
        errors.append(f"duplicate source_entity_id: {source_id}")

    source_by_id = {
        source["source_entity_id"]: source
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("source_entity_id"), str)
    }
    for source_id in value.get("anchor_source_ids", []):
        source = source_by_id.get(source_id)
        if source is None:
            errors.append(f"anchor source is missing: {source_id}")
        elif not source.get("active"):
            errors.append(f"anchor source is inactive: {source_id}")

    coverage_policy = value.get("coverage_policy", {})
    policy_shards = set(coverage_policy)
    expected_shards = set(DISCOVERY_SHARDS)
    if policy_shards != expected_shards:
        missing = sorted(expected_shards - policy_shards)
        extra = sorted(policy_shards - expected_shards)
        if missing:
            errors.append(f"coverage_policy missing shards: {', '.join(missing)}")
        if extra:
            errors.append(f"coverage_policy has unknown shards: {', '.join(extra)}")

    active_counts: Counter[str] = Counter()
    core_counts: Counter[str] = Counter()
    included_tiers = set(value.get("assignment_policy", {}).get("include_priority_tiers", []))
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_entity_id", "<unknown>")
        unknown_shards = sorted(set(source.get("shards", [])) - expected_shards)
        if unknown_shards:
            errors.append(f"{source_id}: unknown shards: {', '.join(unknown_shards)}")
        collection = source.get("collection", [])
        endpoints = [
            (entry.get("kind"), entry.get("url"))
            for entry in collection
            if isinstance(entry, dict)
        ]
        duplicate_endpoints = sorted(
            f"{kind}:{url}" for (kind, url), count in Counter(endpoints).items() if count > 1
        )
        if duplicate_endpoints:
            errors.append(f"{source_id}: duplicate collection endpoints: {', '.join(duplicate_endpoints)}")
        if source.get("active"):
            if source.get("priority_tier") not in included_tiers:
                errors.append(
                    f"{source_id}: active source priority tier is excluded by assignment_policy"
                )
            required = [
                entry for entry in collection
                if isinstance(entry, dict) and entry.get("required")
            ]
            if not required:
                errors.append(f"{source_id}: active source has no required collection endpoint")
            if source.get("priority_tier") == "core" and not any(
                entry.get("cadence") in {"hourly", "daily"} for entry in required
            ):
                errors.append(f"{source_id}: core source has no hourly or daily required endpoint")
            for shard in source.get("shards", []):
                active_counts[shard] += 1
                if source.get("priority_tier") == "core":
                    core_counts[shard] += 1

    for shard, rule in coverage_policy.items():
        min_active = int(rule["min_active_sources"])
        min_core = int(rule["min_core_sources"])
        if active_counts[shard] < min_active:
            errors.append(
                f"{shard}: active coverage {active_counts[shard]} is below minimum {min_active}"
            )
        if core_counts[shard] < min_core:
            errors.append(
                f"{shard}: core coverage {core_counts[shard]} is below minimum {min_core}"
            )
    return errors


def validate(root: Path) -> list[str]:
    path = watchlist_path(root)
    schema_path = root / "schemas" / "source-watchlist.schema.json"
    try:
        manifest = load_watchlist_manifest(root)
        value = load_watchlist(root)
        schema = load_json(schema_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [str(exc)]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        f"{path.relative_to(root)}:{'/'.join(str(part) for part in error.absolute_path)}: {error.message}"
        for error in sorted(validator.iter_errors(manifest), key=lambda item: list(item.absolute_path))
    ]
    source_validator = Draft202012Validator(
        schema["$defs"]["source"], format_checker=FormatChecker()
    )
    for relative in manifest.get("source_files", []):
        shard_path = root / "config" / relative
        try:
            items = load_json(shard_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
            continue
        if not isinstance(items, list):
            errors.append(f"{shard_path.relative_to(root)}: must be a JSON array")
            continue
        for index, item in enumerate(items):
            for error in source_validator.iter_errors(item):
                location = "/".join(str(part) for part in error.absolute_path)
                errors.append(
                    f"{shard_path.relative_to(root)}:{index}/{location}: {error.message}"
                )
    errors.extend(semantic_errors(value))
    errors.extend(coverage_errors(root))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    errors = validate(args.root.resolve())
    if errors:
        for error in errors:
            print(f"source watchlist validation failed: {error}", file=sys.stderr)
        return 1
    value = load_watchlist(args.root.resolve())
    print(f"source watchlist valid: {len(value['sources'])} sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
