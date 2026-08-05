#!/usr/bin/env python3
"""Build the static public War Reporter site from approved repository records."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_REPORT_STATES = {"approved"}
PUBLIC_MAP_STATES = {"approved"}
PUBLICATION_STATUSES = {"public", "coarsened"}


@dataclass
class BuildResult:
    output: Path
    report_count: int
    map_feature_count: int
    map_snapshot_id: str | None
    warnings: list[str] = field(default_factory=list)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_time(explicit: str | None = None) -> datetime:
    if explicit:
        return parse_datetime(explicit)
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch:
        return datetime.fromtimestamp(int(source_date_epoch), tz=UTC)
    return datetime.now(UTC)


def safe_repository_path(root: Path, value: str) -> Path:
    if not value or value.startswith("/"):
        raise ValueError(f"unsafe repository path: {value!r}")
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {value!r}") from exc
    return candidate


def iter_json_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.json") if path.is_file())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def copy_site_shell(site_source: Path, output: Path) -> None:
    if not site_source.is_dir():
        raise FileNotFoundError(f"site source is missing: {site_source}")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(site_source, output)


def normalize_report(root: Path, manifest_path: Path, manifest: dict[str, Any], output: Path) -> dict[str, Any]:
    report_id = str(manifest["report_id"])
    content_path = safe_repository_path(root, str(manifest["content_path"]))
    if not content_path.is_file():
        raise FileNotFoundError(f"report content is missing: {manifest['content_path']}")

    public_content = Path("content/reports") / f"{report_id}.md"
    public_manifest = Path("content/manifests") / f"{report_id}.json"
    (output / public_content).parent.mkdir(parents=True, exist_ok=True)
    (output / public_manifest).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(content_path, output / public_content)
    write_json(output / public_manifest, manifest)

    period = manifest.get("period", {})
    return {
        "report_id": report_id,
        "report_type": manifest.get("report_type"),
        "language": manifest.get("language"),
        "period": {"start": period.get("start"), "end": period.get("end")},
        "as_of": manifest.get("as_of"),
        "generated_at": manifest.get("generated_at"),
        "record_status": manifest.get("record_status"),
        "claim_count": len(manifest.get("claim_ids", [])),
        "assessment_count": len(manifest.get("assessment_ids", [])),
        "claim_set_sha256": manifest.get("claim_set_sha256"),
        "translation_of_report_id": manifest.get("translation_of_report_id"),
        "source_commit": manifest.get("source_commit"),
        "content_url": public_content.as_posix(),
        "manifest_url": public_manifest.as_posix(),
        "repository_path": manifest_path.relative_to(root).as_posix(),
    }


def collect_reports(root: Path, output: Path, *, strict: bool, warnings: list[str]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in iter_json_files(root / "data/reports"):
        try:
            value = load_json(path)
            if not isinstance(value, dict) or "report_id" not in value:
                continue
            if value.get("record_status") not in PUBLIC_REPORT_STATES:
                continue
            report = normalize_report(root, path, value, output)
            report_id = report["report_id"]
            if report_id in seen_ids:
                raise ValueError(f"duplicate public report_id: {report_id}")
            seen_ids.add(report_id)
            reports.append(report)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            message = f"{path.relative_to(root)}: {exc}"
            if strict:
                raise ValueError(message) from exc
            warnings.append(message)
    reports.sort(
        key=lambda item: (
            str(item.get("as_of") or ""),
            str(item.get("generated_at") or ""),
            str(item.get("report_id") or ""),
        ),
        reverse=True,
    )
    return reports


def load_feature_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".ndjson":
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number} is not an object")
            records.append(value)
        return records

    value = load_json(path)
    if isinstance(value, dict) and value.get("type") == "FeatureCollection":
        features = value.get("features")
        if not isinstance(features, list):
            raise ValueError("FeatureCollection.features must be an array")
        return [feature for feature in features if isinstance(feature, dict)]
    if isinstance(value, dict) and value.get("type") == "Feature":
        return [value]
    if isinstance(value, list):
        return [feature for feature in value if isinstance(feature, dict)]
    raise ValueError("unsupported map feature file shape")


def feature_is_public(feature: dict[str, Any], now: datetime) -> bool:
    if feature.get("type") != "Feature" or feature.get("geometry") is None:
        return False
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        return False
    if properties.get("record_status") not in PUBLIC_MAP_STATES:
        return False
    if properties.get("publication_status") not in PUBLICATION_STATUSES:
        return False
    publish_not_before = properties.get("publish_not_before")
    if not isinstance(publish_not_before, str):
        return False
    try:
        return parse_datetime(publish_not_before) <= now
    except ValueError:
        return False


def approved_map_snapshots(root: Path, now: datetime) -> list[tuple[Path, dict[str, Any]]]:
    result: list[tuple[Path, dict[str, Any]]] = []
    for path in iter_json_files(root / "maps/snapshots"):
        value = load_json(path)
        if not isinstance(value, dict) or "snapshot_id" not in value:
            continue
        if value.get("record_status") not in PUBLIC_MAP_STATES:
            continue
        cutoff = value.get("publication_cutoff")
        if not isinstance(cutoff, str) or parse_datetime(cutoff) > now:
            continue
        result.append((path, value))
    result.sort(
        key=lambda item: (
            parse_datetime(str(item[1]["as_of"])),
            parse_datetime(str(item[1]["generated_at"])),
            str(item[1]["snapshot_id"]),
        ),
        reverse=True,
    )
    return result


def collect_map(
    root: Path,
    output: Path,
    *,
    now: datetime,
    strict: bool,
    warnings: list[str],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        snapshots = approved_map_snapshots(root, now)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        if strict:
            raise
        warnings.append(f"map snapshots: {exc}")
        snapshots = []

    if not snapshots:
        feature_collection = {"type": "FeatureCollection", "features": []}
        write_json(output / "data/map.geojson", feature_collection)
        return feature_collection, None

    snapshot_path, snapshot = snapshots[0]
    public_features: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for feature_file in snapshot.get("feature_files", []):
        try:
            path = safe_repository_path(root, str(feature_file))
            if not path.is_file():
                raise FileNotFoundError(f"feature file is missing: {feature_file}")
            for feature in load_feature_records(path):
                if not feature_is_public(feature, now):
                    continue
                feature_id = str(feature.get("id") or "")
                if not feature_id:
                    raise ValueError(f"public feature without id in {feature_file}")
                if feature_id in seen_ids:
                    raise ValueError(f"duplicate public map feature id: {feature_id}")
                seen_ids.add(feature_id)
                public_features.append(feature)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            message = f"{snapshot_path.relative_to(root)} -> {feature_file}: {exc}"
            if strict:
                raise ValueError(message) from exc
            warnings.append(message)

    public_features.sort(key=lambda item: str(item.get("id") or ""))
    metadata = {
        "snapshot_id": snapshot.get("snapshot_id"),
        "as_of": snapshot.get("as_of"),
        "generated_at": snapshot.get("generated_at"),
        "publication_cutoff": snapshot.get("publication_cutoff"),
        "claim_set_sha256": snapshot.get("claim_set_sha256"),
        "feature_count": len(public_features),
        "repository_path": snapshot_path.relative_to(root).as_posix(),
    }
    feature_collection = {"type": "FeatureCollection", "snapshot": metadata, "features": public_features}
    write_json(output / "data/map.geojson", feature_collection)
    return feature_collection, metadata


def build_site(
    root: Path = ROOT,
    output: Path | None = None,
    *,
    now: datetime | None = None,
    strict: bool = False,
) -> BuildResult:
    root = root.resolve()
    output = (output or root / "_site").resolve()
    now = (now or build_time()).astimezone(UTC)
    warnings: list[str] = []

    copy_site_shell(root / "site", output)
    reports = collect_reports(root, output, strict=strict, warnings=warnings)
    map_data, map_snapshot = collect_map(root, output, now=now, strict=strict, warnings=warnings)

    languages = sorted({str(report["language"]) for report in reports if report.get("language")})
    report_types = sorted({str(report["report_type"]) for report in reports if report.get("report_type")})
    catalog = {
        "schema_version": 1,
        "generated_at": iso(now),
        "reports": reports,
        "languages": languages,
        "report_types": report_types,
        "map": map_snapshot,
        "counts": {"reports": len(reports), "map_features": len(map_data["features"])},
    }
    write_json(output / "data/catalog.json", catalog)
    write_json(
        output / "data/build.json",
        {"generated_at": iso(now), "warnings": warnings, "counts": catalog["counts"]},
    )
    (output / ".nojekyll").write_text("", encoding="utf-8")

    return BuildResult(
        output=output,
        report_count=len(reports),
        map_feature_count=len(map_data["features"]),
        map_snapshot_id=str(map_snapshot["snapshot_id"]) if map_snapshot else None,
        warnings=warnings,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--now", help="Build time as an ISO-8601 timestamp")
    parser.add_argument("--strict", action="store_true", help="Fail on malformed public inputs")
    args = parser.parse_args(argv)

    try:
        result = build_site(args.root, args.output, now=build_time(args.now), strict=args.strict)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"site build failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "output": str(result.output),
                "reports": result.report_count,
                "map_features": result.map_feature_count,
                "map_snapshot_id": result.map_snapshot_id,
                "warnings": result.warnings,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
