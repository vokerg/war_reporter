#!/usr/bin/env python3
"""Validate and describe a collection artifact before a write-capable job."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

try:
    from .common import ROOT, atomic_json, load_json
    from .validate import validate
except ImportError:
    from common import ROOT, atomic_json, load_json
    from validate import validate


MANIFEST_SCHEMA = "war-reporter-collection-artifact-v1"
ALLOWED_ROOTS = {"data", "reports"}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for name in sorted(ALLOWED_ROOTS):
        base = root / name
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(root)
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError(f"artifact contains symlink: {relative}")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError(f"artifact contains special file: {relative}")
            files.append(path)
    return files


def validate_artifact(root: Path = ROOT) -> dict[str, Any]:
    errors = validate(root)
    if errors:
        raise ValueError("artifact validation failed:\n" + "\n".join(errors))

    settings = load_json(root / "config/settings.json", default={})
    if not isinstance(settings, dict):
        raise ValueError("missing config/settings.json")
    state_file = settings.get("state_file", "data/state.json")
    state = load_json(root / str(state_file), default={})
    if not isinstance(state, dict):
        raise ValueError("state file must contain an object")

    rows: list[dict[str, Any]] = []
    total_bytes = 0
    for path in artifact_files(root):
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        total_bytes += size
        rows.append(
            {
                "path": relative,
                "bytes": size,
                "sha256": _file_sha256(path),
            }
        )

    if not any(row["path"] == str(state_file) for row in rows):
        raise ValueError("validated artifact is missing the configured state file")

    return {
        "schema": MANIFEST_SCHEMA,
        "state_status": state.get("status"),
        "last_run_at": state.get("last_run_at"),
        "files": rows,
        "file_count": len(rows),
        "total_bytes": total_bytes,
    }


def write_manifest(root: Path, output: Path) -> dict[str, Any]:
    manifest = validate_artifact(root)
    output_path = output if output.is_absolute() else root / output
    if output_path == root or root not in output_path.parents:
        raise ValueError("manifest output must stay inside the artifact root")
    if output_path.parts[: len(root.parts) + 1] == (*root.parts, "data"):
        raise ValueError("manifest must not be written inside data/")
    if output_path.parts[: len(root.parts) + 1] == (*root.parts, "reports"):
        raise ValueError("manifest must not be written inside reports/")
    atomic_json(output_path, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("collection-artifact-manifest.json"),
    )
    args = parser.parse_args(argv)
    try:
        manifest = write_manifest(args.root.resolve(), args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc))
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
