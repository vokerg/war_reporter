#!/usr/bin/env python3
"""Shared source-watchlist loading, assignment, and task-scope checks."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

DISCOVERY_SHARDS = (
    "ua-official",
    "ru-official",
    "ua-analysis-media",
    "ru-milbloggers",
    "international-media",
    "military-analysts",
    "strikes-infrastructure",
    "visual-osint-maps",
    "diplomacy-support-sanctions",
    "reactions-corrections",
)
DISCOVERY_DATA_ROOTS = (
    "catalogs/sources/",
    "data/source-items/",
    "data/artifacts/",
    "raw-manifests/",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def watchlist_path(root: Path) -> Path:
    return root / "config" / "source-watchlist.json"


def load_watchlist_manifest(root: Path) -> dict[str, Any]:
    value = load_json(watchlist_path(root))
    if not isinstance(value, dict):
        raise ValueError("source watchlist manifest must be a JSON object")
    return value


def load_watchlist(root: Path) -> dict[str, Any]:
    manifest = load_watchlist_manifest(root)
    source_files = manifest.get("source_files")
    if not isinstance(source_files, list) or not source_files:
        raise ValueError("source watchlist manifest must declare source_files")
    sources: list[dict[str, Any]] = []
    for relative in source_files:
        if not isinstance(relative, str):
            raise ValueError("source_files entries must be strings")
        path = root / "config" / relative
        value = load_json(path)
        if not isinstance(value, list):
            raise ValueError(f"{path}: source shard must be a JSON array")
        for source in value:
            if not isinstance(source, dict):
                raise ValueError(f"{path}: source shard entries must be objects")
            sources.append(source)
    combined = dict(manifest)
    combined["sources"] = sources
    return combined


def included_priority_tiers(watchlist: dict[str, Any]) -> set[str]:
    policy = watchlist.get("assignment_policy", {})
    values = policy.get("include_priority_tiers", [])
    return {str(value) for value in values}


def source_ids_for_shard(watchlist: dict[str, Any], shard: str) -> list[str]:
    tiers = included_priority_tiers(watchlist)
    result: list[str] = []
    for source in watchlist.get("sources", []):
        if not isinstance(source, dict):
            continue
        if not source.get("active"):
            continue
        if source.get("priority_tier") not in tiers:
            continue
        shards = source.get("shards", [])
        if shard in shards:
            result.append(str(source["source_entity_id"]))
    return result


def iter_tasks(root: Path) -> Iterable[tuple[Path, dict[str, Any]]]:
    tasks_root = root / "tasks"
    if not tasks_root.exists():
        return
    for path in sorted(tasks_root.rglob("*.json")):
        value = load_json(path)
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict) and isinstance(item.get("task_id"), str):
                yield path, item


def infer_discovery_shard(task: dict[str, Any]) -> str | None:
    if task.get("task_type") != "open_web_discovery":
        return None
    paths = task.get("allowed_output_paths", [])
    if isinstance(paths, list):
        for value in paths:
            if not isinstance(value, str) or not value.startswith(DISCOVERY_DATA_ROOTS):
                continue
            stem = Path(value).stem
            if stem in DISCOVERY_SHARDS:
                return stem
    key = task.get("idempotency_key")
    parts = key.split(":") if isinstance(key, str) else []
    for shard in DISCOVERY_SHARDS:
        if shard in parts:
            return shard
    task_id = task.get("task_id")
    if isinstance(task_id, str):
        for shard in DISCOVERY_SHARDS:
            if shard.replace("-", "_") in task_id:
                return shard
    return None


def task_is_watchlist_effective(task: dict[str, Any], watchlist: dict[str, Any]) -> bool:
    if task.get("task_type") != "open_web_discovery":
        return False
    window = task.get("window")
    if not isinstance(window, dict) or not isinstance(window.get("from"), str):
        return False
    return parse_time(window["from"]) >= parse_time(str(watchlist["effective_from"]))


def expected_scope(watchlist: dict[str, Any], shard: str) -> tuple[list[str], list[str]]:
    source_ids = source_ids_for_shard(watchlist, shard)
    if not source_ids:
        raise ValueError(f"watchlist assigns no sources to discovery shard {shard}")
    return source_ids, [shard]


def assignment_errors(root: Path) -> list[str]:
    watchlist = load_watchlist(root)
    errors: list[str] = []
    for path, task in iter_tasks(root):
        if not task_is_watchlist_effective(task, watchlist):
            continue
        shard = infer_discovery_shard(task)
        rel = path.relative_to(root).as_posix()
        if shard is None:
            errors.append(f"{rel}: cannot infer discovery shard")
            continue
        expected_ids, expected_groups = expected_scope(watchlist, shard)
        scope = task.get("scope")
        if not isinstance(scope, dict):
            errors.append(f"{rel}: scope must be an object")
            continue
        actual_ids = scope.get("source_ids")
        actual_groups = scope.get("source_groups")
        if actual_ids != expected_ids:
            errors.append(
                f"{rel}: source_ids differ from config/source-watchlist.json for shard {shard}"
            )
        if actual_groups != expected_groups:
            errors.append(f"{rel}: source_groups must be exactly {expected_groups!r}")
    return errors


def write_assignments(root: Path) -> list[str]:
    watchlist = load_watchlist(root)
    changed: list[str] = []
    for path, task in iter_tasks(root):
        if not task_is_watchlist_effective(task, watchlist):
            continue
        shard = infer_discovery_shard(task)
        if shard is None:
            raise ValueError(f"{path}: cannot infer discovery shard")
        expected_ids, expected_groups = expected_scope(watchlist, shard)
        scope = task.setdefault("scope", {})
        dirty = scope.get("source_ids") != expected_ids or scope.get("source_groups") != expected_groups
        if not dirty:
            continue
        scope["source_ids"] = expected_ids
        scope["source_groups"] = expected_groups
        value = load_json(path)
        if isinstance(value, list):
            replaced = False
            for index, item in enumerate(value):
                if isinstance(item, dict) and item.get("task_id") == task.get("task_id"):
                    value[index] = task
                    replaced = True
                    break
            if not replaced:
                raise ValueError(f"{path}: task disappeared while applying watchlist")
            dump_json(path, value)
        else:
            dump_json(path, task)
        changed.append(path.relative_to(root).as_posix())
    return changed
