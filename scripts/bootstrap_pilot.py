#!/usr/bin/env python3
"""Generate ten independent first-layer tasks for a ChatGPT Project pilot campaign."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from .worker_queue import role_for_task
except ImportError:
    from worker_queue import role_for_task

TASK_SPECS = (
    ("ua-official", "source_scan", 90, ["ukrainian-official"], ["frontline", "strikes"]),
    ("ua-analysis", "source_scan", 80, ["ukrainian-analysts-media"], ["frontline", "capabilities"]),
    ("ru-official", "source_scan", 80, ["russian-official"], ["frontline", "strikes"]),
    ("ru-milbloggers-a", "source_scan", 80, ["russian-milbloggers-a"], ["frontline", "strikes"]),
    ("ru-milbloggers-b", "source_scan", 80, ["russian-milbloggers-b"], ["frontline", "strikes"]),
    ("international-media", "source_scan", 70, ["international-media"], ["operations", "support"]),
    ("military-analysts", "source_scan", 70, ["military-analysts"], ["operations", "capabilities"]),
    ("new-reports", "open_web_discovery", 65, [], ["new-reports", "papers"]),
    ("visual-osint", "open_web_discovery", 65, [], ["visual-osint", "maps"]),
    ("reactions", "open_web_discovery", 60, [], ["reactions", "criticism"]),
)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_tasks(day: date, parent_issue: int | None, region: str) -> list[dict[str, Any]]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    created_at = iso(datetime.now(UTC))
    tasks: list[dict[str, Any]] = []
    for index, (slug, task_type, priority, groups, topics) in enumerate(TASK_SPECS, 1):
        task_id = f"task_{day:%Y%m%d}_{index:02d}_{slug.replace('-', '_')}"
        tasks.append({
            "task_id": task_id,
            "task_type": task_type,
            "role": role_for_task(task_type),
            "state": "ready",
            "priority": priority,
            "created_at": created_at,
            "parent_issue": parent_issue,
            "issue_number": None,
            "depends_on_task_ids": [],
            "window": {"from": iso(start), "to": iso(end)},
            "scope": {
                "source_ids": [],
                "source_groups": groups,
                "regions": [region],
                "topics": topics,
                "content_types": ["post", "article", "report", "map"]
            },
            "exclusions": [
                "Items already represented by canonical URL, platform ID, or content hash",
                "Exact current operational positions and unsafe non-public geodata"
            ],
            "allowed_output_paths": [
                f"data/source-items/{day:%Y/%m/%d}/{slug}.ndjson",
                f"data/artifacts/{day:%Y/%m/%d}/{slug}.ndjson",
                f"raw-manifests/{day:%Y/%m/%d}/{slug}.json"
            ],
            "definition_of_done": [
                "Entire assigned UTC window and source/discovery shard checked",
                "URLs, timestamps, language, quote locators, and upstream lineage recorded",
                "Access failures and coverage gaps recorded",
                "No final truth assessment or report narrative added"
            ],
            "idempotency_key": f"{task_type}:{slug}:{start:%Y%m%dT%H%MZ}:{end:%Y%m%dT%H%MZ}:{region}",
            "lease": None
        })
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="UTC day in YYYY-MM-DD")
    parser.add_argument("--parent-issue", type=int)
    parser.add_argument("--region", default="ukraine-war")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    tasks = build_tasks(date.fromisoformat(args.date), args.parent_issue, args.region)
    args.output.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        path = args.output / f"{task['task_id']}.json"
        path.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(tasks)} ready tasks in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
