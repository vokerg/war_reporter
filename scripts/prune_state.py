#!/usr/bin/env python3
"""Detect or atomically prune runtime health rows for removed sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import ROOT, atomic_json, load_json
except ImportError:
    from common import ROOT, atomic_json, load_json


def configured_source_ids(
    registry: dict[str, Any], settings: dict[str, Any]
) -> set[str]:
    ids = {
        str(source.get("id"))
        for source in registry.get("sources", [])
        if isinstance(source, dict) and source.get("id")
    }
    queries = settings.get("x_search_queries", [])
    if isinstance(queries, list):
        ids.update(
            f"x-discovery-{index}"
            for index, query in enumerate(queries, 1)
            if isinstance(query, str) and query.strip()
        )
    return ids


def orphaned_state_ids(root: Path = ROOT) -> list[str]:
    settings = load_json(root / "config/settings.json", default={})
    registry = load_json(root / "config/sources.json", default={})
    if not isinstance(settings, dict) or not isinstance(registry, dict):
        raise ValueError("missing config/settings.json or config/sources.json")
    state_file = settings.get("state_file")
    if not isinstance(state_file, str) or not state_file:
        raise ValueError("settings.state_file is missing")
    state = load_json(root / state_file, default={})
    if not isinstance(state, dict):
        raise ValueError("state file must contain an object")
    per_source = state.get("per_source", {})
    if not isinstance(per_source, dict):
        raise ValueError("state.per_source must contain an object")
    valid = configured_source_ids(registry, settings)
    return sorted(set(per_source) - valid)


def prune_state(root: Path = ROOT) -> list[str]:
    settings = load_json(root / "config/settings.json", default={})
    if not isinstance(settings, dict):
        raise ValueError("missing config/settings.json")
    state_file = settings.get("state_file")
    if not isinstance(state_file, str) or not state_file:
        raise ValueError("settings.state_file is missing")
    path = root / state_file
    state = load_json(path, default={})
    if not isinstance(state, dict):
        raise ValueError("state file must contain an object")
    per_source = state.get("per_source", {})
    if not isinstance(per_source, dict):
        raise ValueError("state.per_source must contain an object")
    orphans = orphaned_state_ids(root)
    if not orphans:
        return []
    blocked = set(orphans)
    updated = dict(state)
    updated["per_source"] = {
        source_id: row
        for source_id, row in per_source.items()
        if source_id not in blocked
    }
    atomic_json(path, updated)
    return orphans


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--write",
        action="store_true",
        help="atomically remove orphaned per_source rows",
    )
    args = parser.parse_args(argv)
    try:
        orphans = (
            prune_state(args.root)
            if args.write
            else orphaned_state_ids(args.root)
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"state prune failed: {exc}")
        return 2
    if not orphans:
        print("no orphaned source state")
        return 0
    action = "removed" if args.write else "found"
    print(f"{action} orphaned source state: {', '.join(orphans)}")
    return 0 if args.write else 1


if __name__ == "__main__":
    raise SystemExit(main())
