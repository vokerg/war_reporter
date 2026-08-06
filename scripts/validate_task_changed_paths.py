#!/usr/bin/env python3
"""Enforce pull-request changed paths against a worker task manifest.

Only branches named ``work/<task_id>`` are task-scoped. Other branches are
intentionally ignored so repository-maintenance pull requests can change
control-plane files without inventing a task manifest.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable

WORK_PREFIX = "work/"


class ValidationError(Exception):
    """Raised when task path-scope validation cannot safely succeed."""


def run_git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValidationError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def normalize_path(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must contain non-empty repository paths")
    candidate = value.replace("\\", "/").strip()
    path = PurePosixPath(candidate)
    if path.is_absolute() or ".." in path.parts or candidate.startswith("./"):
        raise ValidationError(f"{field} contains unsafe path: {value!r}")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise ValidationError(f"{field} contains invalid path: {value!r}")
    return normalized


def task_id_from_head_ref(head_ref: str) -> str | None:
    if not head_ref.startswith(WORK_PREFIX):
        return None
    task_id = head_ref[len(WORK_PREFIX) :].strip()
    if not task_id or "/" in task_id or task_id in {".", ".."}:
        raise ValidationError(
            "task branches must use the exact form work/<task_id> with no nested path"
        )
    return task_id


def list_task_manifest_paths(repo: Path, head: str, task_id: str) -> list[str]:
    output = run_git("ls-tree", "-r", "--name-only", head, "--", "tasks", cwd=repo)
    suffix = f"/{task_id}.json"
    return [line for line in output.splitlines() if line.endswith(suffix)]


def load_manifest(repo: Path, head: str, manifest_path: str) -> dict:
    raw = run_git("show", f"{head}:{manifest_path}", cwd=repo)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{manifest_path}: invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{manifest_path}: manifest root must be an object")
    return value


def changed_paths(repo: Path, base: str, head: str) -> list[str]:
    output = run_git("diff", "--name-only", "--diff-filter=ACMRDTUXB", f"{base}...{head}", cwd=repo)
    return [
        normalize_path(line, field="git diff")
        for line in output.splitlines()
        if line.strip()
    ]


def validate(
    *, repo: Path, base: str, head: str, head_ref: str
) -> tuple[str | None, list[str], list[str]]:
    task_id = task_id_from_head_ref(head_ref)
    if task_id is None:
        return None, [], []

    matches = list_task_manifest_paths(repo, head, task_id)
    if not matches:
        raise ValidationError(
            f"no task manifest named {task_id}.json exists under tasks/ at {head}"
        )
    if len(matches) > 1:
        raise ValidationError(
            f"multiple task manifests match {task_id}: {', '.join(sorted(matches))}"
        )

    manifest_path = matches[0]
    manifest = load_manifest(repo, head, manifest_path)
    if manifest.get("task_id") != task_id:
        raise ValidationError(
            f"{manifest_path}: task_id must equal branch task id {task_id!r}"
        )

    declared = manifest.get("allowed_output_paths")
    if not isinstance(declared, list) or not declared:
        raise ValidationError(
            f"{manifest_path}: allowed_output_paths must be a non-empty array"
        )
    allowed = {
        normalize_path(item, field=f"{manifest_path}: allowed_output_paths")
        for item in declared
    }
    allowed.add(manifest_path)

    changed = changed_paths(repo, base, head)
    violations = sorted(path for path in changed if path not in allowed)
    return manifest_path, changed, violations


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base commit/ref")
    parser.add_argument("--head", required=True, help="head commit/ref")
    parser.add_argument("--head-ref", required=True, help="pull-request head branch")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest_path, changed, violations = validate(
            repo=args.repo.resolve(),
            base=args.base,
            head=args.head,
            head_ref=args.head_ref,
        )
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if manifest_path is None:
        print(f"Skipping task path-scope validation for non-task branch {args.head_ref!r}.")
        return 0

    if violations:
        print(
            f"ERROR: {manifest_path} does not authorize these changed paths:",
            file=sys.stderr,
        )
        for path in violations:
            print(f"  - {path}", file=sys.stderr)
        return 1

    print(
        f"Validated {len(changed)} changed path(s) against {manifest_path}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
