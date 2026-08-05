#!/usr/bin/env python3
"""Finalize a merged worker task with actual GitHub merge metadata."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_task(root: Path, task_id: str) -> tuple[Path, dict[str, Any]]:
    for path in sorted((root / "tasks").rglob("*.json")):
        value = load(path)
        if isinstance(value, dict) and value.get("task_id") == task_id:
            return path, value
    raise ValueError(f"task manifest not found: {task_id}")


def finalize(root: Path, task_id: str, pr_number: int, merge_sha: str, merged_at: str, branch: str) -> dict[str, Any]:
    path, task = find_task(root, task_id)
    expected_branch = f"work/{task_id}"
    if branch != expected_branch:
        raise ValueError(f"branch must be {expected_branch}")
    if len(merge_sha) != 40:
        raise ValueError("merge SHA must be 40 hexadecimal characters")
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    if result.get("pr_number") not in (None, pr_number):
        raise ValueError("PR number does not match task result")
    result.update({
        "branch": branch,
        "pr_number": pr_number,
        "merge_sha": merge_sha,
        "merged_at": merged_at,
        "completed_at": merged_at,
    })
    task["state"] = "merged"
    task["lease"] = None
    task["result"] = result
    task.pop("blocked_reason", None)
    dump(path, task)
    return {
        "task_id": task_id,
        "task_path": path.relative_to(root).as_posix(),
        "issue_number": task.get("issue_number"),
        "merge_sha": merge_sha,
        "merged_at": merged_at,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--merge-sha", required=True)
    parser.add_argument("--merged-at", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args(argv)
    try:
        result = finalize(args.root.resolve(), args.task_id, args.pr_number, args.merge_sha, args.merged_at, args.branch)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"task finalization failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
