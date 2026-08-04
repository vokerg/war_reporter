#!/usr/bin/env python3
"""Generate ten independent, catalog-free discovery tasks for a ChatGPT Project campaign."""

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


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_tasks(day: date, parent_issue: int | None, region: str) -> list[dict[str, Any]]:
    """Build a full UTC-day campaign. Kept as the stable test/API entry point."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return build_tasks_for_window(start, start + timedelta(days=1), parent_issue, region)


def build_tasks_for_window(
    start: datetime,
    end: datetime,
    parent_issue: int | None,
    region: str,
) -> list[dict[str, Any]]:
    if end <= start:
        raise ValueError("campaign end must be after start")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    created_at = iso(datetime.now(UTC))
    day_path = start.strftime("%Y/%m/%d")
    day_id = start.strftime("%Y%m%d")
    tasks: list[dict[str, Any]] = []

    for index, (slug, priority, topics) in enumerate(DISCOVERY_SHARDS, 1):
        task_id = f"task_{day_id}_{index:02d}_{slug.replace('-', '_')}"
        tasks.append({
            "task_id": task_id,
            "task_type": "open_web_discovery",
            "role": role_for_task("open_web_discovery"),
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
                f"catalogs/sources/{day_path}/{slug}.json",
                f"data/source-items/{day_path}/{slug}.ndjson",
                f"data/artifacts/{day_path}/{slug}.ndjson",
                f"raw-manifests/{day_path}/{slug}.json",
            ],
            "definition_of_done": [
                "The assigned public-web discovery shard and UTC window were searched",
                "Primary publications were preferred and upstream lineage was recorded",
                "Canonical URLs, timestamps, language, quote locators, and access failures were recorded",
                "Candidate source profiles and follow-up task proposals were persisted when justified",
                "No final truth assessment, territorial conclusion, or report narrative was added",
            ],
            "idempotency_key": (
                f"open_web_discovery:{slug}:{start:%Y%m%dT%H%MZ}:"
                f"{end:%Y%m%dT%H%MZ}:{region}"
            ),
            "lease": None,
        })
    return tasks


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset")
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser()
    window = parser.add_mutually_exclusive_group(required=True)
    window.add_argument("--date", help="full UTC day in YYYY-MM-DD")
    window.add_argument("--from", dest="window_from", help="window start as an ISO-8601 timestamp")
    parser.add_argument("--to", dest="window_to", help="window end; required with --from")
    parser.add_argument("--parent-issue", type=int)
    parser.add_argument("--region", default="ukraine-war")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.date:
        tasks = build_tasks(date.fromisoformat(args.date), args.parent_issue, args.region)
    else:
        if not args.window_to:
            parser.error("--to is required with --from")
        tasks = build_tasks_for_window(
            parse_utc(args.window_from),
            parse_utc(args.window_to),
            args.parent_issue,
            args.region,
        )

    args.output.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        path = args.output / f"{task['task_id']}.json"
        path.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(tasks)} ready tasks in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
