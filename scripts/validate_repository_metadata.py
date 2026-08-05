#!/usr/bin/env python3
"""Validate GitHub-facing repository metadata with path-specific diagnostics."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
OWNER_RE = re.compile(r"^@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})|[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+)$")
AGENT_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def error(errors: list[str], path: Path, message: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {message}")


def load_yaml(path: Path, errors: list[str]) -> Any | None:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        error(errors, path, f"invalid YAML: {exc}")
        return None


def validate_issue_forms(errors: list[str]) -> None:
    for path in sorted((ROOT / ".github/ISSUE_TEMPLATE").glob("*.yml")):
        data = load_yaml(path, errors)
        if data is None:
            continue
        if path.name == "config.yml":
            if not isinstance(data, dict):
                error(errors, path, "configuration must be a mapping")
            continue
        if not isinstance(data, dict):
            error(errors, path, "issue form must be a mapping")
            continue
        for key in ("name", "description", "body"):
            if key not in data:
                error(errors, path, f"missing required key {key!r}")
        if "body" in data and not isinstance(data["body"], list):
            error(errors, path, "body must be a list")
        for index, item in enumerate(data.get("body", []) if isinstance(data.get("body"), list) else []):
            if not isinstance(item, dict):
                error(errors, path, f"body[{index}] must be a mapping")
                continue
            if item.get("type") not in {"markdown", "input", "textarea", "dropdown", "checkboxes"}:
                error(errors, path, f"body[{index}] has unsupported type")
            if item.get("type") != "markdown" and not item.get("id"):
                error(errors, path, f"body[{index}] requires a non-empty id")


def validate_workflows(errors: list[str]) -> None:
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        data = load_yaml(path, errors)
        if data is None:
            continue
        if not isinstance(data, dict):
            error(errors, path, "workflow must be a mapping")
            continue
        if not isinstance(data.get("name"), str) or not data["name"].strip():
            error(errors, path, "missing non-empty name")
        # YAML 1.1 parses unquoted 'on' as True; accept either representation.
        trigger = data.get("on", data.get(True))
        if trigger is None:
            error(errors, path, "missing on trigger")
        jobs = data.get("jobs")
        if not isinstance(jobs, dict) or not jobs:
            error(errors, path, "jobs must be a non-empty mapping")
            continue
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                error(errors, path, f"job {job_name!r} must be a mapping")
            elif "uses" not in job and "runs-on" not in job:
                error(errors, path, f"job {job_name!r} requires runs-on or uses")


def validate_codeowners(errors: list[str]) -> None:
    path = ROOT / ".github/CODEOWNERS"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        error(errors, path, f"cannot read: {exc}")
        return
    catch_all = False
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            error(errors, path, f"line {number}: pattern requires at least one owner")
            continue
        if parts[0] == "*":
            catch_all = True
        for owner in parts[1:]:
            if not OWNER_RE.fullmatch(owner):
                error(errors, path, f"line {number}: invalid owner {owner!r}")
    if not catch_all:
        error(errors, path, "missing catch-all '*' ownership rule")


def split_front_matter(path: Path, errors: list[str]) -> tuple[dict[str, Any] | None, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        error(errors, path, "missing YAML front matter")
        return None, text
    end = text.find("\n---\n", 4)
    if end < 0:
        error(errors, path, "unterminated YAML front matter")
        return None, ""
    try:
        metadata = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        error(errors, path, f"invalid front matter YAML: {exc}")
        return None, text[end + 5 :]
    if not isinstance(metadata, dict):
        error(errors, path, "front matter must be a mapping")
        return None, text[end + 5 :]
    return metadata, text[end + 5 :]


def validate_agents(errors: list[str]) -> None:
    required = {"name", "description", "target", "tools"}
    for path in sorted((ROOT / ".github/agents").glob("*.agent.md")):
        metadata, body = split_front_matter(path, errors)
        if metadata is None:
            continue
        missing = sorted(required - metadata.keys())
        if missing:
            error(errors, path, f"missing required keys: {', '.join(missing)}")
        expected_name = path.name.removesuffix(".agent.md")
        name = metadata.get("name")
        if name != expected_name:
            error(errors, path, f"name must match filename ({expected_name!r})")
        if not isinstance(name, str) or not AGENT_NAME_RE.fullmatch(name):
            error(errors, path, "name must be lowercase kebab-case")
        if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
            error(errors, path, "description must be non-empty")
        tools = metadata.get("tools")
        if not isinstance(tools, list) or not tools or any(not isinstance(tool, str) or not tool for tool in tools):
            error(errors, path, "tools must be a non-empty list of strings")
        if not body.strip():
            error(errors, path, "instructions body must be non-empty")


def main() -> int:
    errors: list[str] = []
    validate_issue_forms(errors)
    validate_workflows(errors)
    validate_codeowners(errors)
    validate_agents(errors)
    if errors:
        print("Repository metadata validation failed:", file=sys.stderr)
        for item in errors:
            print(f"- {item}", file=sys.stderr)
        return 1
    print("Repository metadata validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
