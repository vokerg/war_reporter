#!/usr/bin/env python3
"""Create or release deterministic GitHub work branches through the REST API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    from .worker_queue import deterministic_branch, generate_worker_run_id
except ImportError:
    from worker_queue import deterministic_branch, generate_worker_run_id


def request_json(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json"
    })
    with urlopen(request, timeout=30) as response:
        data = response.read()
    return {} if not data else json.loads(data)


def ref_url(api_url: str, repository: str, branch: str) -> str:
    return f"{api_url.rstrip('/')}/repos/{repository}/git/ref/heads/{quote(branch, safe='/')}"


def get_branch_sha(api_url: str, repository: str, branch: str, token: str) -> str:
    value = request_json("GET", ref_url(api_url, repository, branch), token)
    return str(value["object"]["sha"])


def claim(api_url: str, repository: str, task_id: str, base: str, token: str) -> dict:
    base_sha = get_branch_sha(api_url, repository, base, token)
    branch = deterministic_branch(task_id)
    request_json("POST", f"{api_url.rstrip('/')}/repos/{repository}/git/refs", token, {
        "ref": f"refs/heads/{branch}",
        "sha": base_sha
    })
    return {
        "task_id": task_id,
        "worker_run_id": generate_worker_run_id(),
        "branch": branch,
        "base_sha": base_sha
    }


def release(api_url: str, repository: str, task_id: str, token: str, expected_sha: str) -> None:
    branch = deterministic_branch(task_id)
    current_sha = get_branch_sha(api_url, repository, branch, token)
    if current_sha != expected_sha:
        raise RuntimeError(f"ref moved: expected {expected_sha}, found {current_sha}; refusing deletion")
    request_json("DELETE", ref_url(api_url, repository, branch), token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "vokerg/war_reporter"))
    parser.add_argument("--api-url", default=os.environ.get("GITHUB_API_URL", "https://api.github.com"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    claim_parser = subparsers.add_parser("claim")
    claim_parser.add_argument("task_id")
    claim_parser.add_argument("--base", default="main")
    release_parser = subparsers.add_parser("release")
    release_parser.add_argument("task_id")
    release_parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args(argv or sys.argv[1:])

    if not args.token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 2
    try:
        if args.command == "claim":
            print(json.dumps(claim(args.api_url, args.repository, args.task_id, args.base, args.token), ensure_ascii=False))
            return 0
        release(args.api_url, args.repository, args.task_id, args.token, args.expected_sha)
        return 0
    except HTTPError as exc:
        if args.command == "claim" and exc.code == 422:
            print("task branch already exists; another worker owns the task", file=sys.stderr)
            return 3
        print(f"GitHub API error {exc.code}: {exc.read().decode('utf-8', 'replace')}", file=sys.stderr)
        return 1
    except (KeyError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
