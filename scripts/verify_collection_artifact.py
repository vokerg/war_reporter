#!/usr/bin/env python3
"""Dependency-free verification for a validated collection artifact manifest."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import stat
from pathlib import Path
from typing import Any

try:
    from .collection_artifact_contract import (
        ALLOWED_ROOTS,
        FILE_FIELDS,
        HEX_64,
        MANIFEST_FIELDS,
        MANIFEST_SCHEMA,
        RUN_STATUSES,
        artifact_path_allowed,
        configured_paths,
    )
except ImportError:
    contract_path = Path(__file__).resolve().with_name(
        "collection_artifact_contract.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_war_reporter_collection_artifact_contract",
        contract_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError("cannot load collection artifact contract")
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    ALLOWED_ROOTS = contract.ALLOWED_ROOTS
    FILE_FIELDS = contract.FILE_FIELDS
    HEX_64 = contract.HEX_64
    MANIFEST_FIELDS = contract.MANIFEST_FIELDS
    MANIFEST_SCHEMA = contract.MANIFEST_SCHEMA
    RUN_STATUSES = contract.RUN_STATUSES
    artifact_path_allowed = contract.artifact_path_allowed
    configured_paths = contract.configured_paths


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} load failed: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object")
    return value


def _artifact_paths(
    root: Path, settings: dict[str, Any]
) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for name in sorted(ALLOWED_ROOTS):
        base = root / name
        try:
            base_mode = base.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(base_mode):
            raise ValueError(f"artifact root is a symlink: {name}")
        if not stat.S_ISDIR(base_mode):
            raise ValueError(f"artifact root is not a directory: {name}")
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError(f"artifact contains symlink: {relative}")
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                raise ValueError(f"artifact contains special file: {relative}")
            if not artifact_path_allowed(relative, settings):
                raise ValueError(f"unexpected artifact file: {relative}")
            result[relative] = path
    return result


def _manifest_rows(
    value: Any, settings: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("manifest.files must be an array")
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise ValueError(f"manifest.files[{index}] must be an object")
        if set(row) != FILE_FIELDS:
            raise ValueError(f"manifest.files[{index}] has unexpected fields")
        relative = row.get("path")
        size = row.get("bytes")
        digest = row.get("sha256")
        if not isinstance(relative, str) or not artifact_path_allowed(
            relative, settings
        ):
            raise ValueError(f"manifest path is not allowed: {relative}")
        if relative in result:
            raise ValueError(f"duplicate manifest path: {relative}")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"manifest size is invalid: {relative}")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in HEX_64 for char in digest)
        ):
            raise ValueError(f"manifest digest is invalid: {relative}")
        result[relative] = row
    return result


def verify_artifact(root: Path, manifest_path: Path) -> dict[str, Any]:
    root = root.resolve()
    candidate = manifest_path if manifest_path.is_absolute() else root / manifest_path
    try:
        manifest_mode = candidate.lstat().st_mode
    except FileNotFoundError as exc:
        raise ValueError("manifest load failed: file does not exist") from exc
    if stat.S_ISLNK(manifest_mode) or not stat.S_ISREG(manifest_mode):
        raise ValueError("manifest must be a regular non-symlink file")
    manifest_path = candidate.resolve()
    if root not in manifest_path.parents:
        raise ValueError("manifest must be inside the artifact checkout")

    settings = _load_object(root / "config/settings.json", "settings")
    configured = configured_paths(settings)
    manifest = _load_object(manifest_path, "manifest")
    if set(manifest) != MANIFEST_FIELDS:
        raise ValueError("manifest has unexpected or missing fields")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("unsupported artifact manifest schema")
    if manifest.get("state_status") not in RUN_STATUSES:
        raise ValueError("manifest state_status is invalid")
    if manifest.get("last_run_at") is not None and not isinstance(
        manifest.get("last_run_at"), str
    ):
        raise ValueError("manifest last_run_at is invalid")

    expected = _manifest_rows(manifest.get("files"), settings)
    actual = _artifact_paths(root, settings)
    if set(expected) != set(actual):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ValueError(
            f"artifact file set mismatch; missing={missing}; extra={extra}"
        )

    total_bytes = 0
    for relative, path in actual.items():
        expected_row = expected[relative]
        size = path.stat().st_size
        total_bytes += size
        if size != expected_row["bytes"]:
            raise ValueError(f"artifact size mismatch: {relative}")
        if _sha256(path) != expected_row["sha256"]:
            raise ValueError(f"artifact digest mismatch: {relative}")

    file_count = manifest.get("file_count")
    declared_bytes = manifest.get("total_bytes")
    if isinstance(file_count, bool) or file_count != len(actual):
        raise ValueError("artifact file_count mismatch")
    if isinstance(declared_bytes, bool) or declared_bytes != total_bytes:
        raise ValueError("artifact total_bytes mismatch")

    state_path = configured["state_file"]
    if state_path not in actual:
        raise ValueError("artifact is missing the configured state file")
    state = _load_object(actual[state_path], "state")
    if manifest["state_status"] != state.get("status"):
        raise ValueError("manifest state_status does not match state file")
    if manifest["last_run_at"] != state.get("last_run_at"):
        raise ValueError("manifest last_run_at does not match state file")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("collection-artifact-manifest.json"),
    )
    args = parser.parse_args(argv)
    try:
        value = verify_artifact(args.root, args.manifest)
    except ValueError as exc:
        print(str(exc))
        return 1
    print(
        f"verified {value['file_count']} files / "
        f"{value['total_bytes']} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
