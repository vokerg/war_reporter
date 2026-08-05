#!/usr/bin/env python3
"""Validate per-source outcomes for effective watchlist-backed discovery scans."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from source_watchlist import iter_tasks, load_watchlist, task_is_watchlist_effective

ROOT = Path(__file__).resolve().parents[1]
VALID_OUTCOMES = {
    "item_retained",
    "checked_no_in_window_item",
    "candidate_time_uncertain",
    "inaccessible",
    "subscription_index_only",
    "excluded_out_of_window",
    "excluded_overlap",
    "not_checked",
}
COMPLETED_STATES = {"done", "merged", "completed"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def raw_manifest_path(root: Path, task: dict[str, Any]) -> Path | None:
    paths = task.get("allowed_output_paths", [])
    if not isinstance(paths, list):
        return None
    candidates = [value for value in paths if isinstance(value, str) and value.startswith("raw-manifests/") and value.endswith(".json")]
    if len(candidates) != 1:
        return None
    return root / candidates[0]


def coverage_errors(root: Path) -> list[str]:
    watchlist = load_watchlist(root)
    errors: list[str] = []
    for task_path, task in iter_tasks(root):
        if not task_is_watchlist_effective(task, watchlist):
            continue
        rel = task_path.relative_to(root).as_posix()
        expected = task.get("scope", {}).get("source_ids", [])
        if not isinstance(expected, list) or not expected:
            errors.append(f"{rel}: effective discovery task has no assigned source_ids")
            continue
        raw_path = raw_manifest_path(root, task)
        if raw_path is None:
            errors.append(f"{rel}: expected exactly one raw-manifests/*.json output path")
            continue
        if not raw_path.exists():
            if task.get("state") in COMPLETED_STATES:
                errors.append(f"{rel}: completed task has no raw manifest at {raw_path.relative_to(root)}")
            continue
        try:
            manifest = load_json(raw_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{raw_path.relative_to(root)}: {exc}")
            continue
        checks = manifest.get("source_checks") if isinstance(manifest, dict) else None
        if not isinstance(checks, list):
            errors.append(f"{raw_path.relative_to(root)}: source_checks must be an array")
            continue
        check_ids = [entry.get("source_entity_id") for entry in checks if isinstance(entry, dict)]
        counts = Counter(value for value in check_ids if isinstance(value, str))
        for source_id in expected:
            count = counts.get(source_id, 0)
            if count != 1:
                errors.append(
                    f"{raw_path.relative_to(root)}: assigned source {source_id} has {count} source_checks entries; expected 1"
                )
        for index, entry in enumerate(checks):
            if not isinstance(entry, dict):
                errors.append(f"{raw_path.relative_to(root)}: source_checks[{index}] must be an object")
                continue
            source_id = entry.get("source_entity_id")
            if source_id not in expected:
                continue
            outcome = entry.get("outcome")
            if outcome not in VALID_OUTCOMES:
                errors.append(
                    f"{raw_path.relative_to(root)}: source_checks[{index}] has invalid outcome {outcome!r}"
                )
            if outcome == "not_checked":
                explanation = entry.get("notes") or entry.get("coverage_gap") or entry.get("reason")
                if not isinstance(explanation, str) or not explanation.strip():
                    errors.append(
                        f"{raw_path.relative_to(root)}: not_checked source {source_id} requires notes, coverage_gap, or reason"
                    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    errors = coverage_errors(args.root.resolve())
    if errors:
        for error in errors:
            print(f"source scan coverage validation failed: {error}", file=sys.stderr)
        return 1
    print("source scan coverage valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
