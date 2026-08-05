#!/usr/bin/env python3
"""Plan and materialize due repository duties without performing research."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
COMPLETE_STATES = {"merged", "blocked", "rejected", "cancelled", "duplicate"}
TERMINAL_STATES = {"merged", "rejected", "cancelled", "duplicate"}
DISCOVERY_SHARDS = (
    ("ua-official", 90, ["ukrainian-official-statements", "frontline", "strikes"]),
    ("ru-official", 90, ["russian-official-statements", "frontline", "strikes"]),
    ("ua-analysis-media", 85, ["ukrainian-analysis", "ukrainian-media", "operations"]),
    ("ru-milbloggers", 85, ["russian-milbloggers", "operations", "claims"]),
    ("international-media", 80, ["international-media", "operations", "external-support"]),
    ("military-analysts", 80, ["military-analysis", "capabilities", "logistics"]),
    ("strikes-infrastructure", 80, ["strikes", "air-defense", "infrastructure"]),
    ("visual-osint-maps", 75, ["visual-osint", "geolocation", "maps"]),
    ("diplomacy-support-sanctions", 70, ["diplomacy", "military-support", "sanctions"]),
    ("reactions-corrections", 70, ["reactions", "criticism", "corrections", "retractions"]),
)
DISCOVERY_DATA_ROOTS = (
    "catalogs/sources/",
    "data/source-items/",
    "data/artifacts/",
    "raw-manifests/",
)
INACTIVE_COVERAGE_STATES = {"rejected", "cancelled", "duplicate"}
ROLE_FALLBACK = {
    "open_web_discovery": "open-web-discovery",
    "extract_observations": "extractor",
    "investigate_claim": "corroborator",
    "source_profile_review": "source-analyst",
    "map_update": "geo-verifier",
    "daily_report": "report-editor",
    "translate_report": "translator",
    "correction": "correction-editor",
    "validation": "release-validator",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iter_tasks(root: Path) -> Iterable[tuple[Path, dict[str, Any]]]:
    tasks_root = root / "tasks"
    if not tasks_root.exists():
        return
    for path in sorted(tasks_root.rglob("*.json")):
        value = load(path)
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict) and isinstance(item.get("task_id"), str):
                yield path, item


def task_index(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    result: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path, task in iter_tasks(root):
        task_id = str(task["task_id"])
        if task_id in result:
            raise ValueError(f"duplicate task_id: {task_id}")
        result[task_id] = (path, task)
    return result


def routing(root: Path) -> dict[str, str]:
    path = root / "config/worker-routing.json"
    if path.is_file():
        value = load(path).get("task_type_to_role", {})
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
    return dict(ROLE_FALLBACK)


def normalized_scope(scope: Any) -> dict[str, Any]:
    value = dict(scope) if isinstance(scope, dict) else {}
    value.setdefault("source_ids", [])
    value.setdefault("source_groups", [])
    value.setdefault("regions", [])
    value.setdefault("topics", [])
    value.setdefault("content_types", [])
    return value


def duty_day(now: datetime, timezone_name: str) -> date:
    return now.astimezone(ZoneInfo(timezone_name)).date() - timedelta(days=1)


def utc_day_window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def daily_key(day: date, slug: str, region: str) -> str:
    return f"daily_discovery:{day.isoformat()}:{slug}:{region}"


def daily_report_key(day: date, region: str) -> str:
    return f"daily_report:{day.isoformat()}:{region}"


def task_path(root: Path, day: date, task_id: str) -> Path:
    return root / "tasks" / f"{day:%Y/%m/%d}" / f"{task_id}.json"


def nonterminal_count(tasks: dict[str, tuple[Path, dict[str, Any]]]) -> int:
    return sum(1 for _, task in tasks.values() if task.get("state") not in TERMINAL_STATES)


def discovery_data_paths(day: date, slug: str) -> tuple[str, str, str, str]:
    dated = f"{day:%Y/%m/%d}"
    return (
        f"catalogs/sources/{dated}/{slug}.json",
        f"data/source-items/{dated}/{slug}.ndjson",
        f"data/artifacts/{dated}/{slug}.ndjson",
        f"raw-manifests/{dated}/{slug}.json",
    )


def discovery_shard_slug(task: dict[str, Any]) -> str | None:
    if task.get("task_type") != "open_web_discovery":
        return None
    paths = task.get("allowed_output_paths", [])
    if isinstance(paths, list):
        for path in paths:
            if not isinstance(path, str) or not path.startswith(DISCOVERY_DATA_ROOTS):
                continue
            stem = Path(path).stem
            for slug, _, _ in DISCOVERY_SHARDS:
                if stem == slug:
                    return slug
    key = task.get("idempotency_key")
    key_parts = key.split(":") if isinstance(key, str) else []
    for slug, _, _ in DISCOVERY_SHARDS:
        if slug in key_parts:
            return slug
    task_id = task.get("task_id")
    if isinstance(task_id, str):
        for slug, _, _ in DISCOVERY_SHARDS:
            if slug.replace("-", "_") in task_id:
                return slug
    return None


def intervals_cover_window(intervals: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> bool:
    cursor = start
    for lower, upper in sorted(intervals):
        if upper <= cursor:
            continue
        if lower > cursor:
            return False
        cursor = max(cursor, upper)
        if cursor >= end:
            return True
    return cursor >= end


def discovery_coverage_for_day(
    tasks: dict[str, tuple[Path, dict[str, Any]]], day: date, region: str
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bool]]:
    start, end = utc_day_window(day)
    by_shard: dict[str, list[dict[str, Any]]] = {slug: [] for slug, _, _ in DISCOVERY_SHARDS}
    intervals: dict[str, list[tuple[datetime, datetime]]] = {slug: [] for slug, _, _ in DISCOVERY_SHARDS}
    for _, task in tasks.values():
        if task.get("state") in INACTIVE_COVERAGE_STATES:
            continue
        slug = discovery_shard_slug(task)
        if slug is None:
            continue
        scope = task.get("scope")
        regions = scope.get("regions", []) if isinstance(scope, dict) else []
        if isinstance(regions, list) and regions and region not in regions:
            continue
        window = task.get("window")
        if not isinstance(window, dict):
            continue
        lower_value = window.get("from")
        upper_value = window.get("to")
        if not isinstance(lower_value, str) or not isinstance(upper_value, str):
            continue
        lower = max(parse(lower_value), start)
        upper = min(parse(upper_value), end)
        if lower >= upper:
            continue
        by_shard[slug].append(task)
        intervals[slug].append((lower, upper))
    covered = {
        slug: intervals_cover_window(intervals[slug], start, end)
        for slug, _, _ in DISCOVERY_SHARDS
    }
    return by_shard, covered


def discovery_tasks_for_day(tasks: dict[str, tuple[Path, dict[str, Any]]], day: date, region: str) -> list[dict[str, Any]]:
    by_shard, _ = discovery_coverage_for_day(tasks, day, region)
    result: dict[str, dict[str, Any]] = {}
    for shard_tasks in by_shard.values():
        for task in shard_tasks:
            result[str(task["task_id"])] = task
    return [result[task_id] for task_id in sorted(result)]


def discovery_output_collisions(
    tasks: dict[str, tuple[Path, dict[str, Any]]], day: date
) -> dict[str, list[str]]:
    expected = {
        path
        for slug, _, _ in DISCOVERY_SHARDS
        for path in discovery_data_paths(day, slug)
    }
    owners: dict[str, list[str]] = {}
    for task_id, (_, task) in tasks.items():
        paths = task.get("allowed_output_paths", [])
        if not isinstance(paths, list):
            continue
        for path in paths:
            if isinstance(path, str) and path in expected:
                owners.setdefault(path, []).append(task_id)
    return {path: sorted(task_ids) for path, task_ids in sorted(owners.items())}


def summarize_output_collisions(collisions: dict[str, list[str]]) -> str:
    entries = [f"{path} ({', '.join(task_ids)})" for path, task_ids in collisions.items()]
    preview = "; ".join(entries[:4])
    if len(entries) > 4:
        preview += f"; +{len(entries) - 4} more"
    return preview


def pending_proposals(root: Path, tasks: dict[str, tuple[Path, dict[str, Any]]], config: dict[str, Any]) -> list[dict[str, Any]]:
    duties: list[dict[str, Any]] = []
    existing_keys = {str(task.get("idempotency_key")) for _, task in tasks.values()}
    allowed_types = set(config["queue"]["allowed_proposal_task_types"])
    proposal_root = root / config["queue"]["proposal_root"]
    if not proposal_root.exists():
        return duties
    seen: set[str] = set()
    for path in sorted(proposal_root.rglob("*.json")):
        value = load(path)
        producer = value.get("producer_task_id") if isinstance(value, dict) else None
        producer_entry = tasks.get(str(producer))
        if producer_entry is None or producer_entry[1].get("state") != "merged":
            continue
        for proposal in value.get("proposals", []):
            key = proposal.get("idempotency_key")
            if not isinstance(key, str) or key in existing_keys or key in seen:
                continue
            if proposal.get("task_type") not in allowed_types:
                continue
            if producer not in proposal.get("depends_on_task_ids", []):
                continue
            seen.add(key)
            duties.append({
                "kind": "task_proposal",
                "producer_task_id": producer,
                "proposal_path": path.relative_to(root).as_posix(),
                "proposal": proposal,
            })
    return duties


def plan_duties(root: Path, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    config = load(root / "config/autonomy.json")
    tasks = task_index(root)
    day = duty_day(now, config["timezone"])
    start, end = utc_day_window(day)
    activation = parse(config["activation_not_before"])
    local_now = now.astimezone(ZoneInfo(config["timezone"]))
    discovery_due = datetime.combine(local_now.date(), time(config["daily_cycle"]["discovery_due_local_hour"]), tzinfo=local_now.tzinfo)
    snapshot_due = datetime.combine(local_now.date(), time(config["daily_cycle"]["snapshot_due_local_hour"]), tzinfo=local_now.tzinfo)
    duties: list[dict[str, Any]] = []
    blockers: list[str] = []

    proposal_duties = pending_proposals(root, tasks, config)
    duties.extend(proposal_duties)

    promotable = []
    for task_id, (_, task) in tasks.items():
        dependencies = task.get("depends_on_task_ids", [])
        if task.get("state") == "planned" and dependencies and all(
            dependency in tasks and tasks[dependency][1].get("state") == "merged"
            for dependency in dependencies
        ):
            promotable.append(task_id)
    if promotable:
        duties.append({"kind": "promote_tasks", "task_ids": sorted(promotable)})

    region = config["daily_cycle"]["region"]
    coverage_by_shard, covered_shards = discovery_coverage_for_day(tasks, day, region)
    coverage_complete = all(covered_shards.values())
    coverage_tasks: dict[str, dict[str, Any]] = {}
    for shard_tasks in coverage_by_shard.values():
        for task in shard_tasks:
            coverage_tasks[str(task["task_id"])] = task

    cycle_activated = end > activation
    if cycle_activated and local_now >= discovery_due and not coverage_complete:
        collisions = discovery_output_collisions(tasks, day)
        covered_or_partial = sorted(slug for slug, shard_tasks in coverage_by_shard.items() if shard_tasks)
        backlog = nonterminal_count(tasks)
        limit = config["daily_cycle"]["maximum_nonterminal_backlog"]
        if collisions:
            blockers.append(
                f"daily discovery {day} deferred: generated output paths already owned: "
                f"{summarize_output_collisions(collisions)}"
            )
        elif covered_or_partial:
            blockers.append(
                f"daily discovery {day} deferred: partial legacy/incremental coverage exists for shards "
                f"{', '.join(covered_or_partial)}; a full-day campaign would overlap existing work"
            )
        elif backlog >= limit:
            blockers.append(f"daily discovery {day} deferred: nonterminal backlog {backlog} >= {limit}")
        else:
            duties.append({
                "kind": "discovery_campaign",
                "day": day.isoformat(),
                "window": {"from": iso(start), "to": iso(end)},
                "region": region,
                "shards": len(DISCOVERY_SHARDS),
            })

    report_exists = any(task.get("idempotency_key") == daily_report_key(day, region) for _, task in tasks.values())
    proposal_for_day = any(
        parse(duty["proposal"]["window"]["from"]) < end and parse(duty["proposal"]["window"]["to"]) > start
        for duty in proposal_duties
    )
    if cycle_activated and local_now >= snapshot_due and coverage_complete and not report_exists and not proposal_for_day:
        if coverage_tasks and all(task.get("state") in COMPLETE_STATES for task in coverage_tasks.values()):
            related = [
                task for _, task in tasks.values()
                if isinstance(task.get("window"), dict)
                and isinstance(task["window"].get("from"), str)
                and isinstance(task["window"].get("to"), str)
                and parse(task["window"]["from"]) < end
                and parse(task["window"]["to"]) > start
                and task.get("task_type") != "daily_report"
            ]
            if related and all(task.get("state") in COMPLETE_STATES for task in related):
                merged_dependencies = sorted(task["task_id"] for task in related if task.get("state") == "merged")
                if merged_dependencies:
                    duties.append({
                        "kind": "daily_snapshot",
                        "day": day.isoformat(),
                        "window": {"from": iso(start), "to": iso(end)},
                        "region": region,
                        "depends_on_task_ids": merged_dependencies,
                    })
                else:
                    blockers.append(f"daily snapshot {day} skipped: no merged inputs")
    return {
        "generated_at": iso(now),
        "target_day": day.isoformat(),
        "duties": duties,
        "blockers": blockers,
    }


def build_discovery_tasks(root: Path, duty: dict[str, Any], parent_issue: int | None, created_at: str) -> list[tuple[Path, dict[str, Any]]]:
    day = date.fromisoformat(duty["day"])
    start = parse(duty["window"]["from"])
    end = parse(duty["window"]["to"])
    region = duty["region"]
    routes = routing(root)
    result: list[tuple[Path, dict[str, Any]]] = []
    for index, (slug, priority, topics) in enumerate(DISCOVERY_SHARDS, 1):
        task_id = f"task_daily_{day:%Y%m%d}_{index:02d}_{slug.replace('-', '_')}"
        task = {
            "task_id": task_id,
            "task_type": "open_web_discovery",
            "role": routes.get("open_web_discovery", "open-web-discovery"),
            "state": "ready",
            "priority": priority,
            "created_at": created_at,
            "parent_issue": parent_issue,
            "issue_number": None,
            "depends_on_task_ids": [],
            "window": {"from": iso(start), "to": iso(end)},
            "scope": {
                "source_ids": [],
                "source_groups": [],
                "regions": [region],
                "topics": topics,
                "content_types": ["post", "article", "report", "briefing", "document", "image", "video", "map"],
            },
            "exclusions": [
                "Items already represented by canonical URL, platform ID, or content hash",
                "Access-control bypass, private material, and unsafe non-public geodata",
                "Precise current operational positions or targeting-enabling detail",
            ],
            "allowed_output_paths": [
                *discovery_data_paths(day, slug),
                f"queue/proposals/{task_id}.json",
                f"review/self/{task_id}.json",
            ],
            "definition_of_done": [
                "The assigned public-web discovery shard and UTC window were searched",
                "Primary publications were preferred and upstream lineage was recorded",
                "Canonical URLs, timestamps, language, quote locators, and access failures were recorded",
                "A queue proposal file was persisted, containing bounded downstream tasks or an explicit empty proposals list",
                "Two separate self-review rounds passed and a receipt was persisted",
                "No final truth assessment, territorial conclusion, or targeting-enabling detail was added",
            ],
            "idempotency_key": daily_key(day, slug, region),
            "lease": None,
        }
        result.append((task_path(root, day, task_id), task))
    return result


def unique_strings(values: list[str]) -> list[str]:
    """Preserve order while enforcing JSON Schema uniqueItems semantics."""
    return list(dict.fromkeys(values))


def task_from_proposal(root: Path, duty: dict[str, Any], created_at: str, tasks: dict[str, tuple[Path, dict[str, Any]]]) -> tuple[Path, dict[str, Any]]:
    proposal = dict(duty["proposal"])
    key = proposal["idempotency_key"]
    task_id = proposal.get("task_id") or f"task_auto_{hashlib.sha256(key.encode()).hexdigest()[:16]}"
    dependencies = list(proposal["depends_on_task_ids"])
    state = "ready" if all(dep in tasks and tasks[dep][1].get("state") == "merged" for dep in dependencies) else "planned"
    producer = tasks[duty["producer_task_id"]][1]
    routes = routing(root)
    task = {
        "task_id": task_id,
        "task_type": proposal["task_type"],
        "role": routes.get(proposal["task_type"], ROLE_FALLBACK.get(proposal["task_type"], "dispatcher")),
        "state": state,
        "priority": proposal["priority"],
        "created_at": created_at,
        "parent_issue": producer.get("parent_issue"),
        "issue_number": None,
        "depends_on_task_ids": dependencies,
        "window": proposal["window"],
        "scope": normalized_scope(proposal["scope"]),
        "exclusions": proposal["exclusions"],
        "allowed_output_paths": unique_strings(list(proposal["allowed_output_paths"]) + [
            f"queue/proposals/{task_id}.json",
            f"review/self/{task_id}.json",
        ]),
        "definition_of_done": unique_strings(list(proposal["definition_of_done"]) + [
            "Two separate self-review rounds passed and a receipt was persisted",
        ]),
        "idempotency_key": key,
        "lease": None,
    }
    day = parse(task["window"]["from"]).date()
    return task_path(root, day, task_id), task


def build_daily_snapshot(root: Path, duty: dict[str, Any], created_at: str) -> tuple[Path, dict[str, Any]]:
    day = date.fromisoformat(duty["day"])
    task_id = f"task_daily_{day:%Y%m%d}_90_snapshot"
    routes = routing(root)
    task = {
        "task_id": task_id,
        "task_type": "daily_report",
        "role": routes.get("daily_report", "report-editor"),
        "state": "ready",
        "priority": 65,
        "created_at": created_at,
        "parent_issue": None,
        "issue_number": None,
        "depends_on_task_ids": duty["depends_on_task_ids"],
        "window": duty["window"],
        "scope": {
            "source_ids": [],
            "source_groups": [],
            "regions": [duty["region"]],
            "topics": ["daily-snapshot"],
            "content_types": ["report"],
        },
        "exclusions": [
            "Unmerged or unreviewed evidence",
            "New web browsing by the report editor",
            "Precise current operational locations or targeting-enabling detail",
        ],
        "allowed_output_paths": [
            f"data/reports/{day:%Y/%m/%d}/daily.json",
            f"reports/daily/{day.isoformat()}.md",
            f"queue/proposals/{task_id}.json",
            f"review/self/{task_id}.json",
        ],
        "definition_of_done": [
            "Only merged repository inputs for the frozen UTC day were used",
            "Material changes, confidence changes, contested claims, corrections, unresolved questions, and coverage gaps were represented",
            "No new evidence was introduced during editing",
            "Two separate self-review rounds passed and a receipt was persisted",
        ],
        "idempotency_key": daily_report_key(day, duty["region"]),
        "lease": None,
    }
    return task_path(root, day, task_id), task


def apply_plan(root: Path, plan: dict[str, Any], parent_issue: int | None = None) -> dict[str, Any]:
    created: list[str] = []
    promoted: list[str] = []
    tasks = task_index(root)
    created_at = plan["generated_at"]
    for duty in plan.get("duties", []):
        kind = duty["kind"]
        if kind == "promote_tasks":
            for task_id in duty["task_ids"]:
                path, task = tasks[task_id]
                task["state"] = "ready"
                task["lease"] = None
                dump(path, task)
                promoted.append(task_id)
        elif kind == "task_proposal":
            path, task = task_from_proposal(root, duty, created_at, tasks)
            if task["task_id"] not in tasks:
                dump(path, task)
                tasks[task["task_id"]] = (path, task)
                created.append(task["task_id"])
        elif kind == "discovery_campaign":
            for path, task in build_discovery_tasks(root, duty, parent_issue, created_at):
                if task["task_id"] not in tasks:
                    dump(path, task)
                    tasks[task["task_id"]] = (path, task)
                    created.append(task["task_id"])
        elif kind == "daily_snapshot":
            path, task = build_daily_snapshot(root, duty, created_at)
            if task["task_id"] not in tasks:
                dump(path, task)
                tasks[task["task_id"]] = (path, task)
                created.append(task["task_id"])
    return {"created_task_ids": created, "promoted_task_ids": promoted, "blockers": plan.get("blockers", [])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--now")
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--plan-file", type=Path, required=True)
    apply_parser.add_argument("--parent-issue", type=int)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "plan":
            now = parse(args.now) if args.now else None
            result = plan_duties(root, now)
        else:
            result = apply_plan(root, load(args.plan_file), args.parent_issue)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"repository reconciliation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
