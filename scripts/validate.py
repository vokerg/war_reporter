#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from .common import ROOT, parse_time, read_ndjson
except ImportError:
    from common import ROOT, parse_time, read_ndjson


REQUIRED_SOURCE = {
    "id",
    "name",
    "platform",
    "url",
    "group",
    "perspective",
    "trust",
    "priority",
    "enabled",
}
REQUIRED_ITEM = {
    "id",
    "source",
    "platform",
    "url",
    "collected_at",
    "text",
    "media",
    "tags",
}
PLATFORMS = {"telegram", "x", "rss", "web"}
TRUST_LEVELS = {"primary", "high", "medium", "low", "unknown"}
PERSPECTIVES = {"ukrainian", "russian", "mixed", "unknown"}
POSITIVE_INT_SETTINGS = {
    "poll_seconds",
    "workers",
    "request_timeout_seconds",
    "default_lookback_hours",
    "telegram_max_pages",
    "x_max_pages",
    "web_max_links",
    "public_excerpt_chars",
    "public_media_limit",
}
NONNEGATIVE_NUMBER_SETTINGS = {
    "collection_delay_hours",
    "site_publication_delay_hours",
    "site_sensitive_delay_hours",
}
DELAY_MAP_SETTINGS = {
    "collection_delay_by_group",
    "collection_delay_by_tag",
    "collection_delay_by_source",
}
PATH_SETTINGS = {
    "raw_root",
    "error_root",
    "state_file",
    "report_root",
    "site_root",
}


def safe_int(
    value: Any, label: str, errors: list[str]
) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be an integer")
        return None


def parsed_public_url(value: Any):
    raw = str(value or "").strip()
    if not raw or any(ord(char) < 32 for char in raw):
        return None
    parsed = urlparse(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return parsed


def valid_url(value: Any) -> bool:
    return parsed_public_url(value) is not None


def safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and path != Path(".")


def expected_platform_suffix(source_id: str) -> str | None:
    suffixes = {
        "-tg": "telegram",
        "-x": "x",
        "-rss": "rss",
        "-web": "web",
    }
    for suffix, platform in suffixes.items():
        if source_id.endswith(suffix):
            return platform
    return None


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        registry = json.loads(
            (root / "config/sources.json").read_text(encoding="utf-8")
        )
        settings = json.loads(
            (root / "config/settings.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        return [f"configuration load failed: {exc}"]

    if not isinstance(registry, dict):
        return ["config/sources.json must contain an object"]
    if not isinstance(settings, dict):
        return ["config/settings.json must contain an object"]

    for key in POSITIVE_INT_SETTINGS:
        value = safe_int(settings.get(key), f"settings.{key}", errors)
        if value is not None and value < 1:
            errors.append(f"settings.{key} must be at least 1")
    for key in NONNEGATIVE_NUMBER_SETTINGS:
        try:
            value = float(settings.get(key))
        except (TypeError, ValueError):
            errors.append(f"settings.{key} must be a number")
        else:
            if value < 0:
                errors.append(f"settings.{key} must not be negative")
    for key in DELAY_MAP_SETTINGS:
        mapping = settings.get(key)
        if not isinstance(mapping, dict):
            errors.append(f"settings.{key} must be an object")
            continue
        for name, raw_value in mapping.items():
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                errors.append(f"settings.{key}.{name} must be a number")
            else:
                if value < 0:
                    errors.append(f"settings.{key}.{name} must not be negative")
    for key in PATH_SETTINGS:
        value = settings.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"settings.{key} must be a non-empty string")
        elif not safe_relative_path(value):
            errors.append(
                f"settings.{key} must be a safe repository-relative path"
            )
    try:
        ZoneInfo(str(settings.get("report_timezone")))
    except ZoneInfoNotFoundError:
        errors.append("settings.report_timezone is unknown")

    for key in ("sensitive_tags", "public_redact_tags", "x_search_queries"):
        if not isinstance(settings.get(key), list):
            errors.append(f"settings.{key} must be an array")

    if isinstance(settings.get("sensitive_tags"), list) and isinstance(
        settings.get("public_redact_tags"), list
    ):
        missing_sensitive = sorted(
            set(settings["public_redact_tags"])
            - set(settings["sensitive_tags"])
        )
        if missing_sensitive:
            errors.append(
                "settings.public_redact_tags must be a subset of sensitive_tags: "
                + ", ".join(missing_sensitive)
            )

    platform_cadence = settings.get("platform_cadence_minutes", {})
    if not isinstance(platform_cadence, dict):
        errors.append("settings.platform_cadence_minutes must be an object")
    else:
        for platform, value in platform_cadence.items():
            if platform not in PLATFORMS:
                errors.append(f"unknown cadence platform: {platform}")
            parsed = safe_int(
                value,
                f"platform_cadence_minutes.{platform}",
                errors,
            )
            if parsed is not None and parsed < 1:
                errors.append(
                    f"platform_cadence_minutes.{platform} must be at least 1"
                )

    sources = registry.get("sources", [])
    if not isinstance(sources, list):
        return errors + ["config/sources.json sources must be an array"]

    ids: set[str] = set()
    enabled_groups: Counter[str] = Counter()
    for index, source in enumerate(sources):
        label = f"source[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = REQUIRED_SOURCE - source.keys()
        if missing:
            errors.append(f"{label} missing {sorted(missing)}")
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            errors.append(f"{label} id must be a non-empty string")
            continue
        if source_id in ids:
            errors.append(f"duplicate source id: {source_id}")
        ids.add(source_id)
        platform = source.get("platform")
        if platform not in PLATFORMS:
            errors.append(f"{source_id}: unsupported platform")
        parsed_url = parsed_public_url(source.get("url"))
        if parsed_url is None:
            errors.append(f"{source_id}: invalid URL")
        elif parsed_url.scheme != "https":
            errors.append(f"{source_id}: source URL must use HTTPS")
        expected_platform = expected_platform_suffix(source_id)
        if expected_platform is not None and platform != expected_platform:
            errors.append(
                f"{source_id}: id suffix expects platform {expected_platform}"
            )
        if source.get("trust") not in TRUST_LEVELS:
            errors.append(f"{source_id}: invalid trust level")
        if source.get("perspective") not in PERSPECTIVES:
            errors.append(f"{source_id}: invalid perspective")
        priority = safe_int(
            source.get("priority"), f"{source_id}.priority", errors
        )
        if priority is not None and not 0 <= priority <= 100:
            errors.append(f"{source_id}: priority must be 0..100")
        if not isinstance(source.get("enabled"), bool):
            errors.append(f"{source_id}: enabled must be boolean")
        if "tags" in source and not isinstance(source["tags"], list):
            errors.append(f"{source_id}: tags must be an array")
        if "languages" in source and not isinstance(
            source["languages"], list
        ):
            errors.append(f"{source_id}: languages must be an array")
        if source.get("enabled") is True:
            enabled_groups[str(source.get("group"))] += 1

    source_delays = settings.get("collection_delay_by_source", {})
    if isinstance(source_delays, dict):
        for source_id in source_delays:
            if source_id not in ids:
                errors.append(
                    "collection_delay_by_source references unknown source: "
                    f"{source_id}"
                )

    queries = settings.get("x_search_queries", [])
    if not isinstance(queries, list):
        errors.append("x_search_queries must be an array")
        queries = []
    for index, query in enumerate(queries, 1):
        if not isinstance(query, str) or not query.strip():
            errors.append(
                f"x_search_queries[{index - 1}] must be a non-empty string"
            )
        generated_id = f"x-discovery-{index}"
        if generated_id in ids:
            errors.append(
                f"generated discovery id collides with registry: {generated_id}"
            )
        ids.add(generated_id)

    minimums = settings.get("minimum_group_counts", {})
    if not isinstance(minimums, dict):
        errors.append("minimum_group_counts must be an object")
    else:
        for group, minimum_value in minimums.items():
            minimum = safe_int(
                minimum_value,
                f"minimum_group_counts.{group}",
                errors,
            )
            if minimum is not None and enabled_groups[group] < minimum:
                errors.append(
                    f"group {group}: {enabled_groups[group]} enabled, "
                    f"minimum is {minimum}"
                )

    state_file_value = settings.get("state_file")
    if isinstance(state_file_value, str) and safe_relative_path(state_file_value):
        state_path = root / state_file_value
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{state_path}: {exc}")
            else:
                valid_statuses = {
                    "ok", "idle", "partial", "blocked", "failed"
                }
                if not isinstance(state, dict):
                    errors.append(f"{state_path}: must contain an object")
                elif state.get("status") not in valid_statuses:
                    errors.append(
                        f"{state_path}: invalid or missing status "
                        f"{state.get('status')}"
                    )
                per_source = (
                    state.get("per_source", {})
                    if isinstance(state, dict)
                    else {}
                )
                if not isinstance(per_source, dict):
                    errors.append(f"{state_path}: per_source must be an object")
                else:
                    valid_source_statuses = {
                        "ok", "error", "skipped_config", "skipped_cadence"
                    }
                    for source_id, row in per_source.items():
                        if source_id not in ids:
                            errors.append(
                                f"{state_path}: unknown per_source id {source_id}"
                            )
                        if not isinstance(row, dict):
                            errors.append(
                                f"{state_path}: per_source.{source_id} "
                                "must be an object"
                            )
                        elif row.get("status") not in valid_source_statuses:
                            errors.append(
                                f"{state_path}: invalid status for {source_id}: "
                                f"{row.get('status')}"
                            )

    seen_item_ids: dict[str, Path] = {}
    raw_root_value = settings.get("raw_root")
    if isinstance(raw_root_value, str) and safe_relative_path(raw_root_value):
        raw_root = root / raw_root_value
        for path in raw_root.glob("*/*/*/items.ndjson"):
            try:
                rows = read_ndjson([path])
            except ValueError as exc:
                errors.append(str(exc))
                continue
            for row in rows:
                missing = REQUIRED_ITEM - row.keys()
                if missing:
                    errors.append(
                        f"{path}: item missing {sorted(missing)}"
                    )
                item_id = str(row.get("id", ""))
                if not item_id:
                    errors.append(f"{path}: item id must not be empty")
                elif item_id in seen_item_ids:
                    errors.append(
                        f"duplicate item id {item_id}: "
                        f"{seen_item_ids[item_id]} and {path}"
                    )
                else:
                    seen_item_ids[item_id] = path
                if row.get("source") not in ids:
                    errors.append(
                        f"{path}: unknown source {row.get('source')}"
                    )
                if row.get("platform") not in PLATFORMS:
                    errors.append(
                        f"{path}: unsupported item platform "
                        f"{row.get('platform')}"
                    )
                if not valid_url(row.get("url")):
                    errors.append(f"{path}: invalid item URL")
                try:
                    collected = parse_time(row.get("collected_at"))
                    published = parse_time(row.get("published_at"))
                except (TypeError, ValueError) as exc:
                    errors.append(f"{path}: invalid timestamp: {exc}")
                    collected = None
                    published = None
                if collected is None:
                    errors.append(f"{path}: collected_at is required")
                stamp = published or collected
                if stamp is not None:
                    expected = (
                        raw_root
                        / f"{stamp:%Y/%m/%d}"
                        / "items.ndjson"
                    )
                    if expected != path:
                        errors.append(
                            f"{path}: item belongs in {expected}"
                        )
                if not isinstance(row.get("text"), str):
                    errors.append(f"{path}: text must be a string")
                if not isinstance(row.get("media"), list):
                    errors.append(f"{path}: media must be an array")
                if not isinstance(row.get("tags"), list):
                    errors.append(f"{path}: tags must be an array")

    error_root_value = settings.get("error_root")
    if isinstance(error_root_value, str) and safe_relative_path(error_root_value):
        error_root = root / error_root_value
        for path in error_root.glob("*/*/*/errors.ndjson"):
            try:
                rows = read_ndjson([path])
            except ValueError as exc:
                errors.append(str(exc))
                continue
            for row in rows:
                source_id = row.get("source")
                if source_id not in ids:
                    errors.append(f"{path}: unknown error source {source_id}")
                parsed_url = parsed_public_url(row.get("url"))
                if parsed_url is None:
                    errors.append(f"{path}: invalid public error URL")
                elif parsed_url.query or parsed_url.fragment:
                    errors.append(
                        f"{path}: error URL contains query or fragment"
                    )
                error_value = str(row.get("error") or "")
                if (
                    not error_value
                    or "http://" in error_value
                    or "https://" in error_value
                ):
                    errors.append(
                        f"{path}: unsafe or missing public error category"
                    )

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
