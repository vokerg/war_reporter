#!/usr/bin/env python3
"""Validate that a worker PR stays inside its immutable base task contract."""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MUTABLE_TASK_FIELDS = {"state", "lease", "result", "blocked_reason", "issue_number"}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def task_from_document(value: Any, task_id: str) -> dict[str, Any] | None:
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, dict) and item.get("task_id") == task_id:
            return item
    return None


def find_task(root: Path, task_id: str) -> tuple[Path, dict[str, Any]]:
    for path in sorted((root / "tasks").rglob("*.json")):
        task = task_from_document(load(path), task_id)
        if task is not None:
            return path, task
    raise ValueError(f"task manifest not found: {task_id}")


def task_at_revision(root: Path, revision: str, relative_path: str, task_id: str) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    task = task_from_document(json.loads(result.stdout), task_id)
    if task is None:
        raise ValueError(f"base task manifest does not contain {task_id}: {relative_path}")
    return task


def changed_files(root: Path, base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def path_allowed(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**") and path.startswith(pattern[:-3].rstrip("/") + "/"):
            return True
        if fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def validate_immutable_contract(base_task: dict[str, Any], head_task: dict[str, Any], manifest_path: Path) -> list[str]:
    errors: list[str] = []
    fields = sorted((set(base_task) | set(head_task)) - MUTABLE_TASK_FIELDS)
    for field in fields:
        if head_task.get(field) != base_task.get(field):
            errors.append(f"{manifest_path}: immutable task contract field changed: {field}")
    return errors


def validate_scope(root: Path, task_id: str, pr_number: int, base: str, head: str) -> list[str]:
    errors: list[str] = []
    manifest_path, head_task = find_task(root, task_id)
    relative_manifest = manifest_path.relative_to(root).as_posix()
    base_task = task_at_revision(root, base, relative_manifest, task_id)
    errors.extend(validate_immutable_contract(base_task, head_task, manifest_path))

    if head_task.get("state") != "review":
        errors.append(f"{manifest_path}: auto-merge requires state review")
    result = head_task.get("result")
    if not isinstance(result, dict) or result.get("pr_number") != pr_number:
        errors.append(f"{manifest_path}: result.pr_number must be {pr_number}")
    expected_branch = f"work/{task_id}"
    if not isinstance(result, dict) or result.get("branch") != expected_branch:
        errors.append(f"{manifest_path}: result.branch must be {expected_branch}")

    allowed = list(base_task.get("allowed_output_paths", []))
    allowed.extend([
        relative_manifest,
        f"review/self/{task_id}.json",
        f"queue/proposals/{task_id}.json",
    ])
    for path in changed_files(root, base, head):
        if not path_allowed(path, allowed):
            errors.append(f"changed path is outside base task scope: {path}")
    receipt = root / "review/self" / f"{task_id}.json"
    if not receipt.is_file():
        errors.append(f"missing self-review receipt: {receipt.relative_to(root)}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    try:
        errors = validate_scope(args.root.resolve(), args.task_id, args.pr_number, args.base, args.head)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        errors = [str(exc)]
    if errors:
        print("Worker PR scope validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Worker PR scope validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
