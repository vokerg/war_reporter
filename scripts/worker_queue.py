#!/usr/bin/env python3
"""Reference queue, lease, and bootstrap-backpressure implementation."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTING_PATH = REPOSITORY_ROOT / "config" / "worker-routing.json"
ACTIVE_STATES = {"leased", "collecting", "pr_open", "validating", "review"}
TERMINAL_STATES = {"merged", "rejected", "cancelled", "duplicate"}
DISCOVERY_TASK_TYPES = {"source_scan", "open_web_discovery"}
DOWNSTREAM_TASK_TYPES = {
    "extract_observations",
    "investigate_claim",
    "source_profile_review",
    "map_update",
    "daily_report",
    "weekly_report",
    "snapshot_report",
    "translate_report",
    "correction",
}


@dataclass(frozen=True)
class Task:
    path: Path
    value: dict[str, Any]

    @property
    def task_id(self) -> str:
        return str(self.value["task_id"])

    @property
    def priority(self) -> int:
        return int(self.value.get("priority", 50))

    @property
    def created_at(self) -> str:
        return str(self.value.get("created_at", "9999-12-31T23:59:59Z"))


@dataclass(frozen=True)
class QueueStatus:
    ready_tasks: int
    active_leases: int
    open_worker_prs: int
    nonterminal_backlog: int
    previous_campaign_closed: bool
    backlog_limit: int

    @property
    def bootstrap_allowed(self) -> bool:
        return not self.blocking_reasons

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.ready_tasks != 0:
            reasons.append("ready_tasks_nonzero")
        if self.active_leases != 0:
            reasons.append("active_leases_nonzero")
        if self.open_worker_prs != 0:
            reasons.append("open_worker_prs_nonzero")
        if not self.previous_campaign_closed:
            reasons.append("previous_campaign_open")
        if self.nonterminal_backlog >= self.backlog_limit:
            reasons.append("backlog_limit_reached")
        return tuple(reasons)


def utc_now() -> datetime:
    return datetime.now(UTC)


def generate_worker_run_id(now: datetime | None = None, entropy: str | None = None) -> str:
    instant = (now or utc_now()).astimezone(UTC)
    token = entropy or secrets.token_hex(4)
    return f"run_{instant:%Y%m%dT%H%M%SZ}_{token.lower()}"


def deterministic_branch(task_id: str) -> str:
    if not task_id.startswith("task_"):
        raise ValueError("task_id must start with task_")
    return f"work/{task_id}"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_task_documents(tasks_root: Path) -> Iterable[Task]:
    if not tasks_root.exists():
        return
    for path in sorted(tasks_root.rglob("*.json")):
        value = load_json(path)
        documents = value if isinstance(value, list) else [value]
        for document in documents:
            if isinstance(document, dict) and "task_id" in document:
                yield Task(path, document)


def load_routing(path: Path = DEFAULT_ROUTING_PATH) -> dict[str, str]:
    value = load_json(path)
    routing = value.get("task_type_to_role")
    if not isinstance(routing, dict):
        raise ValueError(f"{path}: task_type_to_role must be an object")
    return {str(key): str(role) for key, role in routing.items()}


def role_for_task(task_type: str, routing_path: Path = DEFAULT_ROUTING_PATH) -> str:
    routing = load_routing(routing_path)
    try:
        return routing[task_type]
    except KeyError as exc:
        raise ValueError(f"no worker role configured for task type {task_type}") from exc


def index_tasks(tasks_root: Path) -> dict[str, Task]:
    result: dict[str, Task] = {}
    for task in iter_task_documents(tasks_root):
        if task.task_id in result:
            raise ValueError(f"duplicate task_id: {task.task_id}")
        result[task.task_id] = task
    return result


def canonicalization_complete(root: Path = REPOSITORY_ROOT) -> bool:
    gate = root / "config" / "hardening-gate.json"
    if not gate.is_file():
        return False
    value = load_json(gate)
    return value.get("canonicalization_complete") is True


def ready_tasks(
    tasks_root: Path,
    supported_task_types: set[str] | None = None,
    *,
    canonicalization_is_complete: bool | None = None,
) -> list[Task]:
    tasks = index_tasks(tasks_root)
    gate = canonicalization_complete(tasks_root.resolve().parents[0]) if canonicalization_is_complete is None else canonicalization_is_complete
    eligible: list[Task] = []
    for task in tasks.values():
        value = task.value
        if value.get("state") != "ready":
            continue
        task_type = str(value.get("task_type"))
        if supported_task_types is not None and task_type not in supported_task_types:
            continue
        if task_type in DOWNSTREAM_TASK_TYPES and not gate:
            continue
        dependencies = value.get("depends_on_task_ids", [])
        if not isinstance(dependencies, list):
            continue
        if any(dependency not in tasks or tasks[dependency].value.get("state") != "merged" for dependency in dependencies):
            continue
        eligible.append(task)
    return sorted(eligible, key=lambda task: (-task.priority, task.created_at, task.task_id))


def queue_status(
    tasks_root: Path,
    *,
    open_worker_prs: int,
    previous_campaign_closed: bool,
    backlog_limit: int,
) -> QueueStatus:
    if backlog_limit < 1:
        raise ValueError("backlog_limit must be positive")
    tasks = index_tasks(tasks_root)
    ready = sum(1 for task in tasks.values() if task.value.get("state") == "ready")
    active = sum(1 for task in tasks.values() if task.value.get("state") in ACTIVE_STATES)
    nonterminal = sum(1 for task in tasks.values() if task.value.get("state") not in TERMINAL_STATES)
    return QueueStatus(
        ready_tasks=ready,
        active_leases=active,
        open_worker_prs=open_worker_prs,
        nonterminal_backlog=nonterminal,
        previous_campaign_closed=previous_campaign_closed,
        backlog_limit=backlog_limit,
    )


def _lease_path(state_dir: Path, task_id: str) -> Path:
    return state_dir / "leases" / f"{task_id}.json"


def claim_local(task: Task, state_dir: Path, worker_run_id: str, *, now: datetime | None = None, lease_minutes: int = 120) -> bool:
    if task.value.get("state") != "ready":
        return False
    instant = (now or utc_now()).astimezone(UTC)
    path = _lease_path(state_dir, task.task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": task.task_id,
        "worker_run_id": worker_run_id,
        "lease_branch": deterministic_branch(task.task_id),
        "leased_at": instant.isoformat().replace("+00:00", "Z"),
        "lease_until": (instant + timedelta(minutes=lease_minutes)).isoformat().replace("+00:00", "Z"),
    }
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return True


def read_local_claim(task_id: str, state_dir: Path) -> dict[str, Any] | None:
    path = _lease_path(state_dir, task_id)
    if not path.exists():
        return None
    value = load_json(path)
    return value if isinstance(value, dict) else None


def release_local(task_id: str, state_dir: Path, worker_run_id: str, *, force: bool = False) -> bool:
    path = _lease_path(state_dir, task_id)
    claim = read_local_claim(task_id, state_dir)
    if claim is None:
        return False
    if not force and claim.get("worker_run_id") != worker_run_id:
        raise PermissionError("worker_run_id does not own this lease")
    path.unlink()
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks-root", type=Path, default=REPOSITORY_ROOT / "tasks")
    parser.add_argument("--routing", type=Path, default=DEFAULT_ROUTING_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run-id")
    role = subparsers.add_parser("role")
    role.add_argument("task_type")
    next_task = subparsers.add_parser("next")
    next_task.add_argument("--limit", type=int, default=10)
    status = subparsers.add_parser("status")
    status.add_argument("--open-worker-prs", type=int, required=True)
    status.add_argument("--previous-campaign-closed", action="store_true")
    status.add_argument("--backlog-limit", type=int, default=100)
    can_bootstrap = subparsers.add_parser("can-bootstrap")
    can_bootstrap.add_argument("--open-worker-prs", type=int, required=True)
    can_bootstrap.add_argument("--previous-campaign-closed", action="store_true")
    can_bootstrap.add_argument("--backlog-limit", type=int, default=100)
    claim = subparsers.add_parser("claim-local")
    claim.add_argument("task_id")
    claim.add_argument("--state-dir", type=Path, default=REPOSITORY_ROOT / ".war-reporter")
    claim.add_argument("--worker-run-id")
    claim.add_argument("--lease-minutes", type=int, default=120)
    release = subparsers.add_parser("release-local")
    release.add_argument("task_id")
    release.add_argument("worker_run_id")
    release.add_argument("--state-dir", type=Path, default=REPOSITORY_ROOT / ".war-reporter")
    release.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.command == "run-id":
        print(generate_worker_run_id())
        return 0
    if args.command == "role":
        print(role_for_task(args.task_type, args.routing))
        return 0
    if args.command == "next":
        gate = canonicalization_complete(REPOSITORY_ROOT)
        for task in ready_tasks(args.tasks_root, canonicalization_is_complete=gate)[: args.limit]:
            print(json.dumps({
                "task_id": task.task_id,
                "task_type": task.value.get("task_type"),
                "role": role_for_task(str(task.value.get("task_type")), args.routing),
                "priority": task.priority,
                "branch": deterministic_branch(task.task_id),
                "path": str(task.path),
            }, ensure_ascii=False))
        return 0
    if args.command in {"status", "can-bootstrap"}:
        status = queue_status(
            args.tasks_root,
            open_worker_prs=args.open_worker_prs,
            previous_campaign_closed=args.previous_campaign_closed,
            backlog_limit=args.backlog_limit,
        )
        payload = {
            "ready_tasks": status.ready_tasks,
            "active_leases": status.active_leases,
            "open_worker_prs": status.open_worker_prs,
            "nonterminal_backlog": status.nonterminal_backlog,
            "previous_campaign_closed": status.previous_campaign_closed,
            "backlog_limit": status.backlog_limit,
            "bootstrap_allowed": status.bootstrap_allowed,
            "blocking_reasons": list(status.blocking_reasons),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if args.command == "status" or status.bootstrap_allowed else 3
    if args.command == "claim-local":
        task = index_tasks(args.tasks_root).get(args.task_id)
        if task is None:
            print(f"unknown task: {args.task_id}", file=sys.stderr)
            return 2
        worker_run_id = args.worker_run_id or generate_worker_run_id()
        if not claim_local(task, args.state_dir, worker_run_id, lease_minutes=args.lease_minutes):
            print(f"task already claimed or not ready: {args.task_id}", file=sys.stderr)
            return 3
        print(json.dumps({"task_id": task.task_id, "worker_run_id": worker_run_id, "branch": deterministic_branch(task.task_id)}))
        return 0
    if args.command == "release-local":
        try:
            released = release_local(args.task_id, args.state_dir, args.worker_run_id, force=args.force)
        except PermissionError as exc:
            print(str(exc), file=sys.stderr)
            return 4
        return 0 if released else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
