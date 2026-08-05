#!/usr/bin/env python3
"""Run the complete repository hardening migration as one idempotent transaction."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import harden_repository
from migrate_legacy_raw_manifests import migrate_raw_manifests


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=harden_repository.REPOSITORY_ROOT)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--delete-stale-branches", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = args.root.resolve()
    try:
        payload = harden_repository.run(root, args.repo, args.token, args.delete_stale_branches)
        payload["raw_manifest_timestamp_migrations"] = migrate_raw_manifests(root)
        harden_repository.write_audit(root, payload)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"hardening migration failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
