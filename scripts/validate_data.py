#!/usr/bin/env python3
"""Validate JSON and GeoJSON documents against repository schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
TARGETS = {
    "source-items": "source-item.schema.json",
    "observations": "observation.schema.json",
    "claims": "claim.schema.json",
    "layers": "map-feature.schema.json",
    "snapshots": "map-feature.schema.json",
}


def iter_documents(path: Path):
    if path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("type") == "FeatureCollection":
            yield from value.get("features", [])
        elif isinstance(value, list):
            yield from value
        else:
            yield value
    elif path.suffix == ".ndjson":
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{number}: {exc}") from exc


def main() -> int:
    errors: list[str] = []
    validators = {}
    for directory, schema_name in TARGETS.items():
        schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
        validators[directory] = Draft202012Validator(schema, format_checker=FormatChecker())

    for directory, validator in validators.items():
        roots = [ROOT / "data" / directory, ROOT / "maps" / directory]
        for root in roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if path.suffix not in {".json", ".ndjson"}:
                    continue
                try:
                    documents = list(iter_documents(path))
                except (json.JSONDecodeError, ValueError) as exc:
                    errors.append(str(exc))
                    continue
                for index, document in enumerate(documents):
                    for error in validator.iter_errors(document):
                        location = ".".join(str(part) for part in error.absolute_path)
                        errors.append(f"{path}[{index}] {location}: {error.message}")

    if errors:
        print("Validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Structured data validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
