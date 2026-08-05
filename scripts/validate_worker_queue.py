#!/usr/bin/env python3
"""Validate queue lifecycle, bootstrap backpressure, and configured trust boundaries."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

try:
    from .worker_queue import ACTIVE_STATES, REPOSITORY_ROOT, TERMINAL_STATES, deterministic_branch, index_tasks, load_routing
except ImportError:
    from worker_queue import ACTIVE_STATES, REPOSITORY_ROOT, TERMINAL_STATES, deterministic_branch, index_tasks, load_routing

NO_LEASE_STATES = TERMINAL_STATES | {"planned", "ready", "blocked", "lease_expired"}
RESULT_STATES = {"pr_open", "validating", "review", "merged"}


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def find_cycle(edges: dict[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            start = stack.index(node)
            return stack[start:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for dependency in edges.get(node, []):
            cycle = visit(dependency)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in edges:
        cycle = visit(node)
        if cycle:
            return cycle
    return None


def validate_trust_boundary(root: Path) -> list[str]:
    errors: list[str] = []
    path = root / "config" / "trust-boundary.json"
    schema_path = root / "schemas" / "trust-boundary.schema.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"trust boundary configuration unavailable: {exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in validator.iter_errors(value):
        field = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{path}: {field}: {error.message}")
    mode = value.get("review_mode")
    worker = value.get("worker_identity")
    controller = value.get("merge_controller_identity")
    distinct = worker != controller
    if mode == "independent" and not distinct:
        errors.append(f"{path}: independent review requires distinct authenticated identities")
    if mode == "independent" and value.get("require_distinct_identities") is not True:
        errors.append(f"{path}: independent review must require distinct identities")
    if mode == "administrative" and value.get("require_distinct_identities") is True and not distinct:
        errors.append(f"{path}: cannot require distinct identities while configuring the same identity")
    return errors


def validate_queue(tasks_root: Path, routing_path: Path) -> list[str]:
    errors: list[str] = []
    root = routing_path.resolve().parents[1]
    try:
        tasks = index_tasks(tasks_root)
        routing_document = json.loads(routing_path.read_text(encoding="utf-8"))
        routing_schema_path = root / "schemas" / "worker-routing.schema.json"
        routing_schema = json.loads(routing_schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(routing_schema)
        routing_validator = Draft202012Validator(routing_schema)
        routing_errors = list(routing_validator.iter_errors(routing_document))
        if routing_errors:
            return [f"{routing_path}: {'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}" for error in routing_errors]
        routing = load_routing(routing_path)
        task_schema_path = root / "schemas" / "task-manifest.schema.json"
        task_schema = json.loads(task_schema_path.read_text(encoding="utf-8"))
        schema_task_types = set(task_schema["properties"]["task_type"]["enum"])
        routing_task_types = set(routing)
        for task_type in sorted(schema_task_types - routing_task_types):
            errors.append(f"{routing_path}: missing route for schema task_type {task_type}")
        for task_type in sorted(routing_task_types - schema_task_types):
            errors.append(f"{routing_path}: route exists for unknown task_type {task_type}")
        agent_files = routing_document.get("agent_files", {})
        for role in set(routing.values()):
            relative_path = agent_files.get(role)
            if not isinstance(relative_path, str):
                errors.append(f"{routing_path}: no agent file configured for role {role}")
            elif not (root / relative_path).is_file():
                errors.append(f"{routing_path}: agent file does not exist for role {role}: {relative_path}")
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        return [str(exc)]

    idempotency: dict[str, str] = {}
    edges: dict[str, list[str]] = {}
    for task_id, task in tasks.items():
        value = task.value
        location = str(task.path)
        key = value.get("idempotency_key")
        if isinstance(key, str):
            previous = idempotency.get(key)
            if previous:
                errors.append(f"{location}: duplicate idempotency_key also used by {previous}")
            else:
                idempotency[key] = location

        task_type = value.get("task_type")
        expected_role = routing.get(str(task_type))
        if expected_role is None:
            errors.append(f"{location}: no route for task_type {task_type}")
        elif value.get("role") not in (None, expected_role):
            errors.append(f"{location}: role {value.get('role')} does not match routing role {expected_role}")

        dependencies = value.get("depends_on_task_ids", [])
        if not isinstance(dependencies, list):
            continue
        edges[task_id] = [str(item) for item in dependencies]
        for dependency in dependencies:
            if dependency == task_id:
                errors.append(f"{location}: task cannot depend on itself")
            elif dependency not in tasks:
                errors.append(f"{location}: unknown dependency {dependency}")
        if value.get("state") == "ready":
            unmet = [dependency for dependency in dependencies if dependency in tasks and tasks[dependency].value.get("state") != "merged"]
            if unmet:
                errors.append(f"{location}: ready task has unmet dependencies: {', '.join(unmet)}")

        lease = value.get("lease")
        state = value.get("state")
        if state in ACTIVE_STATES and not isinstance(lease, dict):
            errors.append(f"{location}: state {state} requires lease metadata")
        if state in NO_LEASE_STATES and lease is not None:
            errors.append(f"{location}: state {state} must not have a lease")
        if isinstance(lease, dict):
            expected_branch = deterministic_branch(task_id)
            if lease.get("lease_branch") != expected_branch:
                errors.append(f"{location}: lease_branch must be {expected_branch}")
            leased_at, lease_until = lease.get("leased_at"), lease.get("lease_until")
            if isinstance(leased_at, str) and isinstance(lease_until, str):
                try:
                    if parse_datetime(lease_until) <= parse_datetime(leased_at):
                        errors.append(f"{location}: lease_until must be after leased_at")
                except ValueError:
                    pass

        result = value.get("result")
        if state in RESULT_STATES and not isinstance(result, dict):
            errors.append(f"{location}: state {state} requires result metadata")
        if isinstance(result, dict):
            if result.get("branch") != deterministic_branch(task_id):
                errors.append(f"{location}: result.branch must be {deterministic_branch(task_id)}")
            if state == "merged":
                merge_sha = result.get("merge_sha")
                merged_at = result.get("merged_at")
                if not isinstance(merge_sha, str) or len(merge_sha) != 40:
                    errors.append(f"{location}: merged task requires actual result.merge_sha")
                if not isinstance(merged_at, str):
                    errors.append(f"{location}: merged task requires result.merged_at")
                if result.get("completed_at") != merged_at:
                    errors.append(f"{location}: merged task completed_at must equal merged_at")
        if state == "blocked" and not value.get("blocked_reason"):
            errors.append(f"{location}: blocked task requires blocked_reason")

    cycle = find_cycle(edges)
    if cycle:
        errors.append(f"task dependency cycle: {' -> '.join(cycle)}")
    errors.extend(validate_trust_boundary(root))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks-root", type=Path, default=REPOSITORY_ROOT / "tasks")
    parser.add_argument("--routing", type=Path, default=REPOSITORY_ROOT / "config" / "worker-routing.json")
    args = parser.parse_args(argv or sys.argv[1:])
    errors = validate_queue(args.tasks_root, args.routing)
    if errors:
        print("Worker queue validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Worker queue validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
