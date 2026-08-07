#!/usr/bin/env python3
"""Audit configured source health without exposing raw failure details."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .common import ROOT, load_json, parse_time
except ImportError:
    from common import ROOT, load_json, parse_time


HEALTHY = {"healthy", "cadence_wait"}


def _age_hours(value: Any, now: datetime) -> float | None:
    try:
        stamp = parse_time(value)
    except (TypeError, ValueError):
        return None
    if stamp is None:
        return None
    return round(max(0.0, (now - stamp).total_seconds() / 3600), 2)


def configured_sources(
    registry: dict[str, Any], settings: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for source in registry.get("sources", []):
        if not isinstance(source, dict) or not source.get("id"):
            continue
        source_id = str(source["id"])
        rows[source_id] = {
            "enabled": source.get("enabled") is True,
            "platform": str(source.get("platform", "unknown")),
            "group": str(source.get("group", "other")),
            "virtual": False,
        }
    queries = settings.get("x_search_queries", [])
    if isinstance(queries, list):
        for index, query in enumerate(queries, 1):
            if isinstance(query, str) and query.strip():
                rows[f"x-discovery-{index}"] = {
                    "enabled": True,
                    "platform": "x",
                    "group": "x-discovery",
                    "virtual": True,
                }
    return rows


def audit_source_health(
    root: Path = ROOT,
    *,
    now: datetime | None = None,
    stale_after_hours: float = 48,
) -> dict[str, Any]:
    if stale_after_hours <= 0:
        raise ValueError("stale_after_hours must be positive")
    settings = load_json(root / "config/settings.json", default={})
    registry = load_json(root / "config/sources.json", default={})
    if not isinstance(settings, dict) or not isinstance(registry, dict):
        raise ValueError("missing config/settings.json or config/sources.json")
    state_file = settings.get("state_file", "data/state.json")
    state = load_json(root / str(state_file), default={})
    if not isinstance(state, dict):
        raise ValueError("state file must contain an object")
    per_source = state.get("per_source", {})
    if not isinstance(per_source, dict):
        raise ValueError("state.per_source must contain an object")

    current = (now or datetime.now(UTC)).astimezone(UTC)
    configured = configured_sources(registry, settings)
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    for source_id, metadata in sorted(configured.items()):
        if not metadata["enabled"]:
            classification = "disabled"
            row = per_source.get(source_id, {})
            age = _age_hours(
                row.get("last_success_at") if isinstance(row, dict) else None,
                current,
            )
        else:
            row = per_source.get(source_id)
            if not isinstance(row, dict):
                classification = "never_seen"
                age = None
            else:
                status = row.get("status")
                age = _age_hours(row.get("last_success_at"), current)
                if status == "error":
                    classification = "current_error"
                elif status == "skipped_config":
                    classification = "configuration_blocked"
                elif age is None:
                    classification = "never_succeeded"
                elif age > stale_after_hours:
                    classification = "stale_success"
                elif status == "skipped_cadence":
                    classification = "cadence_wait"
                elif status == "ok":
                    classification = "healthy"
                else:
                    classification = "unknown_state"
        counts[classification] = counts.get(classification, 0) + 1
        rows.append(
            {
                "source_id": source_id,
                "platform": metadata["platform"],
                "group": metadata["group"],
                "virtual": metadata["virtual"],
                "classification": classification,
                "last_success_age_hours": age,
            }
        )

    orphans = sorted(set(per_source) - set(configured))
    if orphans:
        counts["orphan_state"] = len(orphans)
        rows.extend(
            {
                "source_id": source_id,
                "platform": "unknown",
                "group": "unknown",
                "virtual": False,
                "classification": "orphan_state",
                "last_success_age_hours": None,
            }
            for source_id in orphans
        )

    enabled_unhealthy = sum(
        1
        for row in rows
        if row["classification"] not in HEALTHY | {"disabled"}
    )
    return {
        "schema": "war-reporter-source-health-audit-v1",
        "generated_at": current.isoformat().replace("+00:00", "Z"),
        "stale_after_hours": stale_after_hours,
        "summary": dict(sorted(counts.items())),
        "enabled_unhealthy": enabled_unhealthy,
        "sources": rows,
        "semantics": {
            "fetch_success_does_not_validate_claims": True,
            "raw_error_details_omitted": True,
            "single_snapshot_not_uptime_history": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--stale-after-hours", type=float, default=48)
    parser.add_argument(
        "--include-healthy",
        action="store_true",
        help="include healthy/cadence rows in JSON output",
    )
    args = parser.parse_args(argv)
    try:
        result = audit_source_health(
            args.root,
            stale_after_hours=args.stale_after_hours,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": type(exc).__name__}))
        return 2
    if not args.include_healthy:
        result = dict(result)
        result["sources"] = [
            row
            for row in result["sources"]
            if row["classification"] not in HEALTHY
        ]
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if result["enabled_unhealthy"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
