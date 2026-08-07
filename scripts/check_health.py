#!/usr/bin/env python3
"""Safe current-state health probe for external monitoring."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

try:
    from .common import ROOT
    from .public_status import build_public_status
except ImportError:
    from common import ROOT
    from public_status import build_public_status


CLEAN_STATUSES = {"ok", "idle"}


def health_result(root: Path = ROOT, *, now: datetime | None = None) -> dict:
    status = build_public_status(root, now=now)
    run_status = status["run"]["status"]
    stale = bool(status["freshness"]["stale"])
    healthy = run_status in CLEAN_STATUSES and not stale
    reasons: list[str] = []
    if run_status not in CLEAN_STATUSES:
        reasons.append(f"run_{run_status}")
    if stale:
        reasons.append("state_stale")
    if status["degradation"]["source_errors"]:
        reasons.append("source_errors")
    if status["degradation"]["configuration_skips"]:
        reasons.append("configuration_skips")
    if status["degradation"]["unknown_sources"]:
        reasons.append("unknown_sources")
    return {
        "healthy": healthy,
        "reasons": sorted(set(reasons)),
        "run_status": run_status,
        "last_run_at": status["run"]["last_run_at"],
        "last_successful_run_at": status["run"][
            "last_successful_run_at"
        ],
        "stale": stale,
        "last_run_age_hours": status["freshness"][
            "last_run_age_hours"
        ],
        "source_errors": status["degradation"]["source_errors"],
        "configuration_skips": status["degradation"][
            "configuration_skips"
        ],
        "withheld_recent": status["withholding"]["recent"],
        "withheld_undated": status["withholding"]["undated"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        result = health_result(args.root, now=datetime.now(UTC))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"healthy": False, "reasons": ["invalid_state"]}))
        print(f"health check failed: {type(exc).__name__}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
