#!/usr/bin/env python3
"""Validate temporal eligibility for frozen daily-report inputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import reconcile_repository as reconcile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_COMPLETE_STATES = {"validating", "review", "merged"}


def validate_reporting_periods(root: Path) -> list[str]:
    errors: list[str] = []
    for assessment in reconcile.iter_records(root, "data/assessments"):
        assessment_id = assessment.get("assessment_id", "<unknown>")
        period = assessment.get("reporting_period")
        if period is None:
            continue
        if not isinstance(period, dict):
            errors.append(f"assessment {assessment_id}: reporting_period must be an object")
            continue
        lower_value = period.get("start")
        upper_value = period.get("end")
        if not isinstance(lower_value, str) or not isinstance(upper_value, str):
            errors.append(f"assessment {assessment_id}: reporting_period requires start and end")
            continue
        try:
            lower = reconcile.parse(lower_value)
            upper = reconcile.parse(upper_value)
        except ValueError as exc:
            errors.append(f"assessment {assessment_id}: invalid reporting_period: {exc}")
            continue
        if lower >= upper:
            errors.append(f"assessment {assessment_id}: reporting_period.end must be after reporting_period.start")
    return errors


def validate_daily_report_dependencies(root: Path) -> list[str]:
    errors: list[str] = []
    tasks = reconcile.task_index(root)
    for task_id, (_, task) in tasks.items():
        if task.get("task_type") != "daily_report":
            continue
        dependencies = task.get("depends_on_task_ids")
        if not isinstance(dependencies, list) or not dependencies:
            continue
        dependency_tasks: list[dict[str, Any]] = []
        unresolved = False
        for dependency_id in dependencies:
            entry = tasks.get(str(dependency_id))
            if entry is None or entry[1].get("state") not in OUTPUT_COMPLETE_STATES:
                unresolved = True
                break
            dependency_tasks.append(entry[1])
        if unresolved:
            continue
        window = task.get("window")
        lower_value = window.get("from") if isinstance(window, dict) else None
        upper_value = window.get("to") if isinstance(window, dict) else None
        if not isinstance(lower_value, str) or not isinstance(upper_value, str):
            errors.append(f"daily report {task_id}: invalid frozen UTC window")
            continue
        try:
            report_inputs = reconcile.frozen_report_inputs(
                root,
                reconcile.parse(lower_value),
                reconcile.parse(upper_value),
            )
        except (ValueError, TypeError) as exc:
            errors.append(f"daily report {task_id}: cannot freeze report inputs: {exc}")
            continue
        if report_inputs is None:
            states = ", ".join(
                f"{dependency['task_id']}={dependency.get('state')}"
                for dependency in dependency_tasks
            )
            errors.append(
                f"daily report {task_id}: all dependencies are output-complete ({states}) "
                "but no approved claim or assessment overlaps the frozen UTC window"
            )
    return errors


def validate(root: Path) -> list[str]:
    return [
        *validate_reporting_periods(root),
        *validate_daily_report_dependencies(root),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv or sys.argv[1:])
    errors = validate(args.root.resolve())
    if errors:
        print("Report-input eligibility validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Report-input eligibility validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
