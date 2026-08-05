#!/usr/bin/env python3
"""Compare live work branches, task manifests, and open worker PRs.

Cleanup debt is reported but non-blocking by default. Use --strict-cleanup only for
an explicit janitor audit. Workers must never spend task time retrying branch
deletion through a connector that does not expose delete-ref.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from .harden_repository import GitHubClient, audit_or_delete_work_branches
except ImportError:
    from harden_repository import GitHubClient, audit_or_delete_work_branches

ROOT = Path(__file__).resolve().parents[1]


def audit(root: Path, repository: str, token: str | None, *, delete_stale: bool = False) -> dict[str, Any]:
    return audit_or_delete_work_branches(root, GitHubClient(repository, token), delete_stale)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--delete-stale", action="store_true")
    parser.add_argument("--strict-cleanup", action="store_true")
    args = parser.parse_args(argv)
    if not args.repo:
        print("--repo or GITHUB_REPOSITORY is required", file=sys.stderr)
        return 2
    try:
        result = audit(args.root.resolve(), args.repo, args.token, delete_stale=args.delete_stale)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"work-ref audit failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    stale = result.get("stale", [])
    if stale and not args.strict_cleanup:
        print(
            f"Work-ref cleanup debt: {len(stale)} stale branch(es). "
            "This is non-blocking and will be retried by the merge controller/reconciler.",
            file=sys.stderr,
        )
        return 0
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
