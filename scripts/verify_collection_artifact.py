#!/usr/bin/env python3
"""Dependency-free verification for a validated collection artifact manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA = "war-reporter-collection-artifact-v1"
ALLOWED_ROOTS = {"data", "reports"}
HEX_64 = set("0123456789abcdef")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_paths(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for name in sorted(ALLOWED_ROOTS):
        base = root / name
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError(f"artifact contains symlink: {relative}")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError(f"artifact contains special file: {relative}")
            result[relative] = path
    return result


def _manifest_rows(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("manifest.files must be an array")
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise ValueError(f"manifest.files[{index}] must be an object")
        if set(row) != {"path", "bytes", "sha256"}:
            raise ValueError(f"manifest.files[{index}] has unexpected fields")
        relative = row.get("path")
        size = row.get("bytes")
        digest = row.get("sha256")
        if not isinstance(relative, str) or not relative:
            raise ValueError(f"manifest.files[{index}].path is invalid")
        path = Path(relative)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not path.parts
            or path.parts[0] not in ALLOWED_ROOTS
        ):
            raise ValueError(f"manifest path is outside allowed roots: {relative}")
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
    manifest_path = manifest_path.resolve()
    if root not in manifest_path.parents:
        raise ValueError("manifest must be inside the artifact checkout")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest load failed: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("manifest must contain an object")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("unsupported artifact manifest schema")

    expected = _manifest_rows(manifest.get("files"))
    actual = _artifact_paths(root)
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

    if manifest.get("file_count") != len(actual):
        raise ValueError("artifact file_count mismatch")
    if manifest.get("total_bytes") != total_bytes:
        raise ValueError("artifact total_bytes mismatch")
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
    manifest = (
        args.manifest
        if args.manifest.is_absolute()
        else args.root / args.manifest
    )
    try:
        value = verify_artifact(args.root, manifest)
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
