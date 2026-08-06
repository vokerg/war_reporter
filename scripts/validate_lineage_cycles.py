#!/usr/bin/env python3
"""Validate that repository lineage relationships form directed acyclic graphs."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


@dataclass(frozen=True)
class Record:
    path: Path
    line: int
    data: dict[str, object]


@dataclass(frozen=True)
class GraphSpec:
    name: str
    roots: tuple[str, ...]
    id_field: str
    edge_fields: tuple[str, ...]


GRAPH_SPECS = (
    GraphSpec(
        name="source-item lineage",
        roots=("data/source-items",),
        id_field="source_item_id",
        edge_fields=("upstream_item_ids", "revision_of_item_id"),
    ),
    GraphSpec(
        name="claim supersession",
        roots=("data/claims",),
        id_field="claim_id",
        edge_fields=("supersedes_claim_id",),
    ),
    GraphSpec(
        name="report translation",
        roots=("data/reports",),
        id_field="report_id",
        edge_fields=("translation_of_report_id",),
    ),
    GraphSpec(
        name="map snapshot lineage",
        roots=("maps/snapshots",),
        id_field="snapshot_id",
        edge_fields=("previous_snapshot_id",),
    ),
)


def iter_json_records(path: Path) -> Iterator[Record]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{path}: cannot read file: {exc}") from exc

    if path.suffix == ".ndjson":
        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no}: record must be a JSON object")
            yield Record(path, line_no, value)
        return

    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}:{exc.lineno}: invalid JSON: {exc.msg}") from exc

    values: Iterable[object]
    if isinstance(value, list):
        values = value
    else:
        values = (value,)
    for index, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: record {index} must be a JSON object")
        yield Record(path, index, item)


def iter_records(root: Path, roots: tuple[str, ...]) -> Iterator[Record]:
    for relative_root in roots:
        directory = root / relative_root
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix in {".json", ".ndjson"}:
                yield from iter_json_records(path)


def relation_targets(value: object, path: Path, line: int, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raise ValueError(
        f"{path}:{line}: {field} must be a string, null, or an array of strings"
    )


def canonical_cycle(cycle: list[str]) -> tuple[str, ...]:
    nodes = cycle[:-1]
    rotations = [tuple(nodes[index:] + nodes[:index]) for index in range(len(nodes))]
    best = min(rotations)
    return best + (best[0],)


def find_cycles(adjacency: dict[str, set[str]]) -> list[tuple[str, ...]]:
    state: dict[str, int] = {}
    stack: list[str] = []
    stack_index: dict[str, int] = {}
    cycles: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        stack_index[node] = len(stack)
        stack.append(node)
        for target in sorted(adjacency.get(node, ())):
            if target not in adjacency:
                continue
            if state.get(target, 0) == 0:
                visit(target)
            elif state.get(target) == 1:
                cycle = stack[stack_index[target] :] + [target]
                cycles.add(canonical_cycle(cycle))
        stack.pop()
        stack_index.pop(node, None)
        state[node] = 2

    for node in sorted(adjacency):
        if state.get(node, 0) == 0:
            visit(node)
    return sorted(cycles)


def validate_graph(root: Path, spec: GraphSpec) -> list[str]:
    errors: list[str] = []
    records: dict[str, Record] = {}
    adjacency: dict[str, set[str]] = defaultdict(set)

    try:
        graph_records = list(iter_records(root, spec.roots))
    except ValueError as exc:
        return [str(exc)]

    for record in graph_records:
        identifier = record.data.get(spec.id_field)
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"{record.path}:{record.line}: missing or invalid {spec.id_field}")
            continue
        if identifier in records:
            first = records[identifier]
            errors.append(
                f"{record.path}:{record.line}: duplicate {spec.id_field} {identifier!r}; "
                f"first seen at {first.path}:{first.line}"
            )
            continue
        records[identifier] = record
        adjacency.setdefault(identifier, set())

        for field in spec.edge_fields:
            if field not in record.data:
                continue
            try:
                targets = relation_targets(record.data[field], record.path, record.line, field)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            adjacency[identifier].update(targets)

    for cycle in find_cycles(adjacency):
        locations = [
            f"{node} ({records[node].path}:{records[node].line})"
            for node in cycle[:-1]
        ]
        errors.append(f"{spec.name} cycle: " + " -> ".join(locations + [cycle[0]]))
    return errors


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    for spec in GRAPH_SPECS:
        errors.extend(validate_graph(root, spec))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    errors = validate_repository(args.root.resolve())
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Lineage graphs are acyclic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
