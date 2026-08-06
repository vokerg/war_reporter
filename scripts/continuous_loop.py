#!/usr/bin/env python3
"""Run collection forever; lack of tasks or source failures never ends the loop."""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

try:
    from .build_report import build_report
    from .build_site import build_site
    from .collect import run_collection
    from .common import ROOT, env_int, load_json
except ImportError:
    from build_report import build_report
    from build_site import build_site
    from collect import run_collection
    from common import ROOT, env_int, load_json

LOG = logging.getLogger("war-reporter.loop")


def run_loop(root: Path, *, once: bool = False, poll_seconds: int | None = None) -> int:
    settings = load_json(root / "config/settings.json")
    interval = poll_seconds or env_int(
        "WAR_REPORTER_POLL_SECONDS", int(settings["poll_seconds"])
    )
    stop = threading.Event()

    def request_stop(signum: int, _frame: object) -> None:
        LOG.info("received signal %s; finishing current iteration", signum)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    while not stop.is_set():
        try:
            state = run_collection(root)
            LOG.info(
                "collection complete: sources=%s items=%s errors=%s",
                state["sources_attempted"], state["items_added"], state["errors"],
            )
        except Exception:
            LOG.exception("collection iteration failed; loop will continue")

        today = datetime.now(UTC).date()
        for day in (today - timedelta(days=1), today):
            try:
                build_report(root, day.isoformat())
            except Exception:
                LOG.exception("report build failed for %s; loop will continue", day)
        try:
            build_site(root)
        except Exception:
            LOG.exception("site build failed; loop will continue")

        if once:
            return 0
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
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return run_loop(args.root, once=args.once, poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
