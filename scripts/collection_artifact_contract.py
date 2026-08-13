"""Dependency-free path contract for collection artifacts."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any


MANIFEST_SCHEMA = "war-reporter-collection-artifact-v1"
ALLOWED_ROOTS = {"data", "reports"}
NON_ARTIFACT_PREFIXES = {"reports/summary", "reports/weekly"}
MANIFEST_FIELDS = {
    "schema",
    "state_status",
    "last_run_at",
    "files",
    "file_count",
    "total_bytes",
}
FILE_FIELDS = {"path", "bytes", "sha256"}
RUN_STATUSES = {"ok", "idle", "partial", "blocked", "failed"}
HEX_64 = set("0123456789abcdef")
ARTIFACT_PATHS = {
    "state_file": "data/state.json",
    "raw_root": "data/raw",
    "error_root": "data/errors",
    "report_root": "reports/daily",
}


def safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("artifact path must be a non-empty POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        raise ValueError(f"artifact path is unsafe: {value}")
    return path.as_posix()


def configured_paths(settings: dict[str, Any]) -> dict[str, str]:
    values = {
        key: safe_relative_path(settings.get(key))
        for key in ARTIFACT_PATHS
    }
    for key, expected in ARTIFACT_PATHS.items():
        if values[key] != expected:
            raise ValueError(
                f"collection artifact v1 requires {key}={expected}"
            )
    return values


def artifact_path_ignored(relative: str) -> bool:
    """Return true for repository-owned files outside collector ownership."""
    try:
        path = safe_relative_path(relative)
    except ValueError:
        return False
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in NON_ARTIFACT_PREFIXES
    )


def artifact_path_allowed(relative: str, settings: dict[str, Any]) -> bool:
    try:
        path = safe_relative_path(relative)
        configured = configured_paths(settings)
    except ValueError:
        return False
    if path == configured["state_file"]:
        return True
    patterns = (
        rf"^{re.escape(configured['raw_root'])}/\d{{4}}/\d{{2}}/\d{{2}}/items\.ndjson$",
        rf"^{re.escape(configured['error_root'])}/\d{{4}}/\d{{2}}/\d{{2}}/errors\.ndjson$",
        rf"^{re.escape(configured['report_root'])}/\d{{4}}-\d{{2}}-\d{{2}}\.md$",
    )
    return any(re.fullmatch(pattern, path) for pattern in patterns)
