#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    from .common import ROOT, read_ndjson
except ImportError:
    from common import ROOT, read_ndjson


REQUIRED_SOURCE = {"id", "name", "platform", "url", "group", "trust", "priority", "enabled"}
REQUIRED_ITEM = {"id", "source", "platform", "url", "collected_at", "text", "media", "tags"}


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    registry = json.loads((root / "config/sources.json").read_text(encoding="utf-8"))
    sources = registry.get("sources", [])
    ids: set[str] = set()
    for index, source in enumerate(sources):
        missing = REQUIRED_SOURCE - source.keys()
        if missing:
            errors.append(f"source[{index}] missing {sorted(missing)}")
        source_id = source.get("id")
        if source_id in ids:
            errors.append(f"duplicate source id: {source_id}")
        ids.add(source_id)
        if source.get("platform") not in {"telegram", "x", "rss", "web"}:
            errors.append(f"{source_id}: unsupported platform")
        if urlparse(str(source.get("url", ""))).scheme not in {"http", "https"}:
            errors.append(f"{source_id}: invalid URL")
        if not 0 <= int(source.get("priority", -1)) <= 100:
            errors.append(f"{source_id}: priority must be 0..100")

    for path in (root / "data/raw").glob("*/*/*/items.ndjson"):
        for row in read_ndjson([path]):
            missing = REQUIRED_ITEM - row.keys()
            if missing:
                errors.append(f"{path}: item missing {sorted(missing)}")
            if row.get("source") not in ids:
                errors.append(f"{path}: unknown source {row.get('source')}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
