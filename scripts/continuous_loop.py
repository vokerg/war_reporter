#!/usr/bin/env python3
"""Run collection forever; source failures never terminate service mode."""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from .build_report import (
        build_report,
        local_today,
        raw_paths_for_local_day,
        report_timezone,
    )
    from .build_site import build_site
    from .collect import run_collection
    from .common import ROOT, env_int, load_json
except ImportError:
    from build_report import (
        build_report,
        local_today,
        raw_paths_for_local_day,
        report_timezone,
    )
    from build_site import build_site
    from collect import run_collection
    from common import ROOT, env_int, load_json

LOG = logging.getLogger("war-reporter.loop")


def report_days_to_build(
    root: Path,
    settings: dict[str, Any],
    today: date,
    *,
    recovery_days: int = 7,
) -> list[date]:
    """Return yesterday/today plus recent missing daily reports backed by raw data."""
    report_root = root / str(settings["report_root"])
    raw_root = str(settings["raw_root"])
    timezone = report_timezone(settings)
    days = {today - timedelta(days=1), today}
    for offset in range(2, recovery_days + 1):
        day = today - timedelta(days=offset)
        report = report_root / f"{day.isoformat()}.md"
        if report.exists():
            continue
        raw_paths = raw_paths_for_local_day(
            root,
            raw_root,
            day.isoformat(),
            timezone,
        )
        if any(path.exists() and path.stat().st_size > 0 for path in raw_paths):
            days.add(day)
    return sorted(days)


def run_loop(
    root: Path,
    *,
    once: bool = False,
    poll_seconds: int | None = None,
) -> int:
    settings = load_json(root / "config/settings.json")
    if not isinstance(settings, dict):
        LOG.error("missing config/settings.json")
        return 1
    interval = (
        poll_seconds
        if poll_seconds is not None
        else env_int(
            "WAR_REPORTER_POLL_SECONDS",
            int(settings["poll_seconds"]),
        )
    )
    if interval < 1:
        LOG.error("poll interval must be at least one second")
        return 1

    stop = threading.Event()

    def request_stop(signum: int, _frame: object) -> None:
        LOG.info(
            "received signal %s; finishing current iteration", signum
        )
        stop.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)

    while not stop.is_set():
        iteration_failed = False
        try:
            state = run_collection(root)
            LOG.info(
                (
                    "collection complete: status=%s attempted=%s "
                    "succeeded=%s added=%s errors=%s skipped=%s"
                ),
                state["status"],
                state["sources_attempted"],
                state["sources_succeeded"],
                state["items_added"],
                state["errors"],
                state["sources_skipped"],
            )
            if state["status"] in {"failed", "blocked", "partial"}:
                iteration_failed = True
        except Exception:
            iteration_failed = True
            LOG.exception(
                "collection iteration failed; service mode will continue"
            )

        today = local_today(settings, datetime.now(UTC))
        for day in report_days_to_build(root, settings, today):
            try:
                build_report(root, day.isoformat())
            except Exception:
                iteration_failed = True
                LOG.exception(
                    "report build failed for %s; service mode will continue",
                    day,
                )
        try:
            build_site(root)
        except Exception:
            iteration_failed = True
            LOG.exception(
                "site build failed; service mode will continue"
            )

        if once:
            return 1 if iteration_failed else 0
        stop.wait(interval)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(
            logging, args.log_level.upper(), logging.INFO
        ),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return run_loop(
        args.root,
        once=args.once,
        poll_seconds=args.poll_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
