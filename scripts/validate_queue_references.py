#!/usr/bin/env python3
"""Validate source and source-item references carried by task and proposal scopes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]


def load_records(path: Path) -> Iterable[dict[str, Any]]:
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
    values = value if isinstance(value, list) else [value]
    for index, record in enumerate(values):
        if not isinstance(record, dict):
            raise ValueError(f"{path}[{index}]: JSON record must be an object")
        yield record


def collect_ids(root: Path, relative_root: str, id_field: str) -> tuple[set[str], list[str]]:
    identifiers: set[str] = set()
    errors: list[str] = []
    directory = root / relative_root
    if not directory.exists():
        return identifiers, errors
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".ndjson"}:
            continue
        try:
            records = load_records(path)
            for record in records:
                value = record.get(id_field)
                if isinstance(value, str):
                    identifiers.add(value)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(str(exc))
    return identifiers, errors


def validate_scope(
    errors: list[str],
    location: str,
    scope: Any,
    source_ids: set[str],
    source_item_ids: set[str],
) -> None:
    if not isinstance(scope, dict):
        return
    references = (
        ("source_ids", source_ids),
        ("source_item_ids", source_item_ids),
    )
    for field, known in references:
        values = scope.get(field, [])
        if not isinstance(values, list):
            continue
        for index, value in enumerate(values):
            if isinstance(value, str) and value not in known:
                errors.append(f"{location} scope.{field}[{index}]: unresolved reference {value}")


def validate_repository(root: Path) -> list[str]:
    source_ids, errors = collect_ids(root, "catalogs/sources", "source_entity_id")
    source_item_ids, item_errors = collect_ids(root, "data/source-items", "source_item_id")
    errors.extend(item_errors)

    tasks_root = root / "tasks"
    if tasks_root.exists():
        for path in sorted(tasks_root.rglob("*.json")):
            try:
                for index, task in enumerate(load_records(path)):
                    validate_scope(errors, f"{path.relative_to(root)}[{index}]", task.get("scope"), source_ids, source_item_ids)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                errors.append(str(exc))

    proposals_root = root / "queue/proposals"
    if proposals_root.exists():
        for path in sorted(proposals_root.rglob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(str(exc))
                continue
            proposals = value.get("proposals", []) if isinstance(value, dict) else []
            if not isinstance(proposals, list):
                continue
            for index, proposal in enumerate(proposals):
                if isinstance(proposal, dict):
                    validate_scope(
                        errors,
                        f"{path.relative_to(root)} proposals[{index}]",
                        proposal.get("scope"),
                        source_ids,
                        source_item_ids,
                    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    errors = validate_repository(args.root.resolve())
    if errors:
        print("Queue reference validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Queue reference validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
