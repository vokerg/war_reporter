#!/usr/bin/env python3
"""Create or update repository labels from config/github-labels.json."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def request_json(method: str, url: str, token: str, payload: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json"
    })
    with urlopen(request, timeout=30) as response:
        data = response.read()
    return None if not data else json.loads(data)


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY", "vokerg/war_reporter")
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 2

    config = json.loads((ROOT / "config" / "github-labels.json").read_text(encoding="utf-8"))
    for label in config["labels"]:
        endpoint = f"{api_url}/repos/{repository}/labels/{quote(label['name'], safe='')}"
        try:
            request_json("PATCH", endpoint, token, {
                "new_name": label["name"],
                "color": label["color"],
                "description": label["description"]
            })
            print(f"updated {label['name']}")
        except HTTPError as exc:
            if exc.code != 404:
                print(f"failed {label['name']}: HTTP {exc.code}", file=sys.stderr)
                return 1
            request_json("POST", f"{api_url}/repos/{repository}/labels", token, {
                "name": label["name"],
                "color": label["color"],
                "description": label["description"]
            })
            print(f"created {label['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
