#!/usr/bin/env python3
"""Public-source collector facade and CLI."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from . import collector_adapters as _adapters
from . import collector_runtime as _runtime
from .common import ROOT
from .collector_common import (
    CollectionError,
    discover_article_urls,
    ensure_public_url,
    extract_article,
    extract_publication_time,
    json_safe,
    make_item,
    public_projection as _base_public_projection,
    safe_get,
    session_for,
)
from .collector_adapters import (
    COLLECTORS,
    collect_rss,
    collect_telegram,
    collect_web,
    collect_x,
    x_api_get,
    x_discovery_sources,
)
from .collector_runtime import (
    append_errors,
    collect_one,
    item_is_storable,
    item_storage_delay_hours,
    item_storage_state,
    source_cadence_minutes,
    source_is_due,
)
from .public_archive import harden_public_projection

LOG = logging.getLogger("war-reporter.collect")


def public_projection(
    item: dict[str, Any], settings: dict[str, Any]
) -> dict[str, Any]:
    """Return the final record permitted to enter the public archive."""
    return harden_public_projection(
        _base_public_projection(item, settings), item, settings
    )


def _x_pages(
    session: Any,
    endpoint: str,
    params: dict[str, Any],
    max_pages: int,
    *,
    token_param: str,
) -> list[dict[str, Any]]:
    """Compatibility wrapper preserving the historical patch point."""
    original = _adapters.x_api_get
    _adapters.x_api_get = x_api_get
    try:
        return _adapters._x_pages(
            session,
            endpoint,
            params,
            max_pages,
            token_param=token_param,
        )
    finally:
        _adapters.x_api_get = original


def run_collection(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Compatibility wrapper preserving the historical patch points."""
    original_collect_one = _runtime.collect_one
    original_projection = _runtime.public_projection
    _runtime.collect_one = collect_one
    _runtime.public_projection = public_projection
    try:
        return _runtime.run_collection(*args, **kwargs)
    finally:
        _runtime.collect_one = original_collect_one
        _runtime.public_projection = original_projection


def parse_set(value: str | None) -> set[str] | None:
    return (
        {part.strip() for part in value.split(",") if part.strip()}
        if value
        else None
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--lookback-hours", type=int)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--groups", help="comma-separated source groups")
    parser.add_argument(
        "--platforms", help="comma-separated platforms"
    )
    parser.add_argument(
        "--sources", help="comma-separated source ids"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="ignore per-source cadence and collect selected sources now",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        result = run_collection(
            args.root,
            lookback_hours=args.lookback_hours,
            workers=args.workers,
            groups=parse_set(args.groups),
            platforms=parse_set(args.platforms),
            source_ids=parse_set(args.sources),
            force=args.force,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        LOG.error("%s", exc)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] in {"failed", "blocked"}:
        return 1
    if result["status"] == "partial":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
