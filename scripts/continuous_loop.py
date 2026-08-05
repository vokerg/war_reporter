#!/usr/bin/env python3
"""Deterministic decision engine for the long-running Continuous Loop supervisor."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    from .reconcile_repository import plan_duties, task_index
    from .worker_queue import (
        canonicalization_complete,
        deterministic_branch,
        ready_tasks,
        role_for_task,
    )
except ImportError:
    from reconcile_repository import plan_duties, task_index
    from worker_queue import (
        canonicalization_complete,
        deterministic_branch,
        ready_tasks,
        role_for_task,
    )

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_STATES = {"leased", "collecting", "pr_open", "validating", "review"}
TERMINAL_STATES = {"merged", "rejected", "cancelled", "duplicate"}
HUMAN_REVIEW_PREFIX = "HUMAN_REVIEW_REQUIRED:"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include an offset")
    return parsed.astimezone(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _scheduled_duty_candidates(now: datetime, config: dict[str, Any]) -> list[datetime]:
    """Return future daily controller boundaries that can create work."""

    local_tz = ZoneInfo(config["timezone"])
    local_now = now.astimezone(local_tz)
    activation = parse_time(config["activation_not_before"])
    cycle = config["daily_cycle"]
    candidates: list[datetime] = []
    for offset in range(0, 4):
        local_day = local_now.date() + timedelta(days=offset)
        target_day = local_day - timedelta(days=1)
        target_start = datetime.combine(target_day, time.min, tzinfo=UTC)
        if target_start < activation:
            continue
        for hour in (
            cycle["discovery_due_local_hour"],
            cycle["snapshot_due_local_hour"],
        ):
            candidate = datetime.combine(local_day, time(hour), tzinfo=local_tz).astimezone(UTC)
            if candidate > now:
                candidates.append(candidate)
    return sorted(set(candidates))


def next_scheduled_duty_at(now: datetime, config: dict[str, Any]) -> datetime | None:
    candidates = _scheduled_duty_candidates(now, config)
    return candidates[0] if candidates else None


def _task_payload(task: Any, root: Path) -> dict[str, Any]:
    task_type = str(task.value.get("task_type"))
    routing = root / "config/worker-routing.json"
    return {
        "task_id": task.task_id,
        "task_type": task_type,
        "role": role_for_task(task_type, routing),
        "priority": task.priority,
        "branch": deterministic_branch(task.task_id),
        "path": task.path.relative_to(root).as_posix(),
    }


def _requires_human_gate(task: dict[str, Any]) -> bool:
    return (
        task.get("state") == "blocked"
        and str(task.get("blocked_reason", "")).startswith(HUMAN_REVIEW_PREFIX)
    )


def evaluate_loop(
    root: Path,
    *,
    now: datetime | None = None,
    open_worker_prs: int = 0,
    active_work_branches: int = 0,
    exceptional_prs: int = 0,
    idle_sweeps: int = 0,
    idle_since: datetime | None = None,
) -> dict[str, Any]:
    """Choose the supervisor's next action from repository and runtime state."""

    root = root.resolve()
    now = (now or datetime.now(UTC)).astimezone(UTC)
    if min(open_worker_prs, active_work_branches, exceptional_prs, idle_sweeps) < 0:
        raise ValueError("runtime counters cannot be negative")

    config = load(root / "config/autonomy.json")
    loop_config = config["continuous_loop"]
    plan = plan_duties(root, now)
    tasks = task_index(root)
    state_counts: dict[str, int] = {}
    human_gate_task_ids: list[str] = []
    for task_id, (_, task) in tasks.items():
        state = str(task.get("state"))
        state_counts[state] = state_counts.get(state, 0) + 1
        if _requires_human_gate(task):
            human_gate_task_ids.append(task_id)

    nonterminal_tasks = sum(
        count for state, count in state_counts.items() if state not in TERMINAL_STATES
    )
    queue = {
        "total_tasks": len(tasks),
        "nonterminal_tasks": nonterminal_tasks,
        "open_worker_prs": open_worker_prs,
        "active_work_branches": active_work_branches,
        "exceptional_prs": exceptional_prs,
        "human_gate_task_ids": sorted(human_gate_task_ids),
        "states": dict(sorted(state_counts.items())),
    }
    common = {
        "generated_at": iso(now),
        "duties": plan.get("duties", []),
        "reconciliation_blockers": plan.get("blockers", []),
        "queue": queue,
    }

    if exceptional_prs or human_gate_task_ids:
        return {
            **common,
            "action": "human_gate",
            "reason": "exceptional_work_present",
            "next_poll_seconds": None,
            "task": None,
        }

    if plan.get("duties"):
        return {
            **common,
            "action": "reconcile",
            "reason": "repository_duties_due",
            "next_poll_seconds": 0,
            "task": None,
        }

    eligible = ready_tasks(
        root / "tasks",
        canonicalization_is_complete=canonicalization_complete(root),
    )
    if eligible:
        return {
            **common,
            "action": "claim",
            "reason": "eligible_task_available",
            "next_poll_seconds": 0,
            "task": _task_payload(eligible[0], root),
        }

    work_in_flight = (
        sum(state_counts.get(state, 0) for state in ACTIVE_STATES)
        + open_worker_prs
        + active_work_branches
    )
    if work_in_flight:
        return {
            **common,
            "action": "wait",
            "reason": "work_in_flight",
            "next_poll_seconds": loop_config["merge_poll_seconds"],
            "task": None,
        }

    if nonterminal_tasks:
        return {
            **common,
            "action": "wait",
            "reason": "nonterminal_queue_not_claimable",
            "next_poll_seconds": loop_config["idle_poll_seconds"],
            "task": None,
        }

    if plan.get("blockers"):
        return {
            **common,
            "action": "wait",
            "reason": "reconciliation_blocked",
            "next_poll_seconds": loop_config["idle_poll_seconds"],
            "task": None,
        }

    next_due = next_scheduled_duty_at(now, config)
    guard_seconds = loop_config["scheduled_duty_guard_seconds"]
    if next_due is not None and next_due <= now + timedelta(seconds=guard_seconds):
        return {
            **common,
            "action": "wait",
            "reason": "scheduled_duty_within_guard",
            "next_poll_seconds": min(
                loop_config["idle_poll_seconds"],
                max(1, int((next_due - now).total_seconds())),
            ),
            "task": None,
            "next_scheduled_duty_at": iso(next_due),
        }

    idle_elapsed = (
        max(0, int((now - idle_since.astimezone(UTC)).total_seconds()))
        if idle_since is not None
        else 0
    )
    quiescence = {
        "idle_sweeps": idle_sweeps,
        "required_idle_sweeps": loop_config["minimum_idle_sweeps"],
        "idle_seconds": idle_elapsed,
        "required_idle_seconds": loop_config["minimum_idle_window_seconds"],
        "next_scheduled_duty_at": iso(next_due) if next_due else None,
    }
    if (
        idle_sweeps < loop_config["minimum_idle_sweeps"]
        or idle_elapsed < loop_config["minimum_idle_window_seconds"]
    ):
        return {
            **common,
            "action": "wait",
            "reason": "quiescence_not_proven",
            "next_poll_seconds": loop_config["idle_poll_seconds"],
            "task": None,
            "quiescence": quiescence,
        }

    return {
        **common,
        "action": "quiescent",
        "reason": "no_work_after_quiescence_proof",
        "next_poll_seconds": None,
        "task": None,
        "quiescence": quiescence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--now")
    parser.add_argument("--open-worker-prs", type=int, default=0)
    parser.add_argument("--active-work-branches", type=int, default=0)
    parser.add_argument("--exceptional-prs", type=int, default=0)
    parser.add_argument("--idle-sweeps", type=int, default=0)
    parser.add_argument("--idle-since")
    args = parser.parse_args(argv)

    try:
        result = evaluate_loop(
            args.root,
            now=parse_time(args.now) if args.now else None,
            open_worker_prs=args.open_worker_prs,
            active_work_branches=args.active_work_branches,
            exceptional_prs=args.exceptional_prs,
            idle_sweeps=args.idle_sweeps,
            idle_since=parse_time(args.idle_since) if args.idle_since else None,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"continuous loop evaluation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
