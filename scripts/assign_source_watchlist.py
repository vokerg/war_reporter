#!/usr/bin/env python3
"""Apply or verify canonical source assignments on discovery task manifests."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from source_watchlist import assignment_errors, write_assignments

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.write:
            changed = write_assignments(root)
            print(json.dumps({"changed_paths": changed}, indent=2))
        errors = assignment_errors(root)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"source assignment failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"source assignment failed: {error}", file=sys.stderr)
        return 1
    if args.check:
        print("source assignments valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
