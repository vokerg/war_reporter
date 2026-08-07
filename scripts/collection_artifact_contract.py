"""Dependency-free path contract for collection artifacts."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any


MANIFEST_SCHEMA = "war-reporter-collection-artifact-v1"
ALLOWED_ROOTS = {"data", "reports"}
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


def safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("artifact path must be a non-empty POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        raise ValueError(f"artifact path is unsafe: {value}")
    return path.as_posix()


def configured_paths(settings: dict[str, Any]) -> dict[str, str]:
    values = {
        "state_file": safe_relative_path(settings.get("state_file")),
        "raw_root": safe_relative_path(settings.get("raw_root")),
        "error_root": safe_relative_path(settings.get("error_root")),
        "report_root": safe_relative_path(settings.get("report_root")),
    }
    if PurePosixPath(values["state_file"]).parts[0] != "data":
        raise ValueError("configured state_file must stay under data/")
    for key in ("raw_root", "error_root"):
        if PurePosixPath(values[key]).parts[0] != "data":
            raise ValueError(f"configured {key} must stay under data/")
    if PurePosixPath(values["report_root"]).parts[0] != "reports":
        raise ValueError("configured report_root must stay under reports/")
    return values


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
