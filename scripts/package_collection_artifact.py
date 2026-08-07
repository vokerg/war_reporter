#!/usr/bin/env python3
"""Safely validate and package a collection artifact manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .common import ROOT, atomic_json
    from .validate_collection_artifact import validate_artifact
except ImportError:
    from common import ROOT, atomic_json
    from validate_collection_artifact import validate_artifact


def manifest_path(root: Path, output: Path) -> Path:
    root = root.resolve()
    candidate = output if output.is_absolute() else root / output
    candidate = candidate.resolve()
    if candidate == root or root not in candidate.parents:
        raise ValueError("manifest output must stay inside the artifact checkout")
    relative = candidate.relative_to(root)
    if relative.parts[0] in {"data", "reports"}:
        raise ValueError("manifest must stay outside data/ and reports/")
    return candidate


def package_artifact(
    root: Path = ROOT,
    output: Path = Path("collection-artifact-manifest.json"),
) -> tuple[Path, dict]:
    root = root.resolve()
    destination = manifest_path(root, output)
    manifest = validate_artifact(root)
    atomic_json(destination, manifest)
    return destination, manifest


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
        destination, manifest = package_artifact(args.root, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc))
        return 1
    print(destination)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
