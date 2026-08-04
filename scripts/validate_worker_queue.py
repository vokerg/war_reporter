#!/usr/bin/env python3
"""Validate ChatGPT Project queue semantics beyond individual JSON Schemas."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

try:
    from .worker_queue import ACTIVE_STATES, REPOSITORY_ROOT, deterministic_branch, index_tasks, load_routing
except ImportError:
    from worker_queue import ACTIVE_STATES, REPOSITORY_ROOT, deterministic_branch, index_tasks, load_routing


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


def validate_queue(tasks_root: Path, routing_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        tasks = index_tasks(tasks_root)
        routing_document = json.loads(routing_path.read_text(encoding="utf-8"))
        routing_schema_path = REPOSITORY_ROOT / "schemas" / "worker-routing.schema.json"
        routing_schema = json.loads(routing_schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(routing_schema)
        routing_errors = list(Draft202012Validator(routing_schema).iter_errors(routing_document))
        if routing_errors:
            return [f"{routing_path}: {'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}" for error in routing_errors]
        routing = load_routing(routing_path)
        agent_files = routing_document.get("agent_files", {})
        for role in set(routing.values()):
            relative_path = agent_files.get(role)
            if not isinstance(relative_path, str):
                errors.append(f"{routing_path}: no agent file configured for role {role}")
            elif not (REPOSITORY_ROOT / relative_path).is_file():
                errors.append(f"{routing_path}: agent file does not exist for role {role}: {relative_path}")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
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
        if state in {"planned", "ready"} and lease is not None:
            errors.append(f"{location}: state {state} must not have a lease")
        if isinstance(lease, dict):
            expected_branch = deterministic_branch(task_id)
            if lease.get("lease_branch") != expected_branch:
                errors.append(f"{location}: lease_branch must be {expected_branch}")
            leased_at = lease.get("leased_at")
            lease_until = lease.get("lease_until")
            if isinstance(leased_at, str) and isinstance(lease_until, str):
                try:
                    if parse_datetime(lease_until) <= parse_datetime(leased_at):
                        errors.append(f"{location}: lease_until must be after leased_at")
                except ValueError:
                    pass

        result = value.get("result")
        if state in {"pr_open", "validating", "review", "merged"} and not isinstance(result, dict):
            errors.append(f"{location}: state {state} requires result metadata")
        if isinstance(result, dict) and result.get("branch") != deterministic_branch(task_id):
            errors.append(f"{location}: result.branch must be {deterministic_branch(task_id)}")
        if state == "blocked" and not value.get("blocked_reason"):
            errors.append(f"{location}: blocked task requires blocked_reason")

    cycle = find_cycle(edges)
    if cycle:
        errors.append(f"task dependency cycle: {' -> '.join(cycle)}")
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
