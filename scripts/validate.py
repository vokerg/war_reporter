#!/usr/bin/env python3
"""Validate configuration, runtime state and public persisted artifacts."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from .common import ROOT, parse_time, read_ndjson
except ImportError:
    from common import ROOT, parse_time, read_ndjson


REQUIRED_SOURCE = {
    "id", "name", "platform", "url", "group", "perspective", "trust",
    "priority", "enabled",
}
REQUIRED_ITEM = {
    "id", "source", "platform", "url", "collected_at", "title", "text",
    "html", "media", "tags", "raw",
}
PLATFORMS = {"telegram", "x", "rss", "web"}
TRUST_LEVELS = {"primary", "high", "medium", "low", "unknown"}
PERSPECTIVES = {"ukrainian", "russian", "mixed", "unknown"}
RUN_STATUSES = {"ok", "idle", "partial", "blocked", "failed"}
SOURCE_STATUSES = {"ok", "error", "skipped_config", "skipped_cadence"}
POSITIVE_INT_SETTINGS = {
    "poll_seconds", "workers", "request_timeout_seconds",
    "default_lookback_hours", "telegram_max_pages", "x_max_pages",
    "web_max_links", "public_excerpt_chars", "public_media_limit",
}
NONNEGATIVE_NUMBER_SETTINGS = {
    "collection_delay_hours", "site_publication_delay_hours",
    "site_sensitive_delay_hours",
}
DELAY_MAP_SETTINGS = {
    "collection_delay_by_group", "collection_delay_by_tag",
    "collection_delay_by_source",
}
PATH_SETTINGS = {"raw_root", "error_root", "state_file", "report_root", "site_root"}
STATE_COUNTERS = {
    "sources_configured", "sources_attempted", "sources_succeeded",
    "sources_skipped", "items_added", "items_withheld_recent",
    "items_withheld_undated", "errors",
}
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ERROR = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*: [a-z0-9_]+$")
DOMAIN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


def safe_int(value: Any, label: str, errors: list[str]) -> int | None:
    if isinstance(value, bool):
        errors.append(f"{label} must be an integer")
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be an integer")
        return None


def nonnegative_int(value: Any, label: str, errors: list[str]) -> int | None:
    parsed = safe_int(value, label, errors)
    if parsed is not None and parsed < 0:
        errors.append(f"{label} must not be negative")
    return parsed


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


def safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and path != Path(".")


def expected_platform_suffix(source_id: str) -> str | None:
    for suffix, platform in {
        "-tg": "telegram", "-x": "x", "-rss": "rss", "-web": "web",
    }.items():
        if source_id.endswith(suffix):
            return platform
    return None


def timestamp(
    value: Any,
    label: str,
    errors: list[str],
    *,
    nullable: bool = True,
) -> datetime | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value:
        errors.append(f"{label} must be an ISO timestamp")
        return None
    try:
        parsed = parse_time(value)
    except (TypeError, ValueError) as exc:
        errors.append(f"{label} invalid timestamp: {exc}")
        return None
    if parsed is None:
        errors.append(f"{label} must be an ISO timestamp")
    return parsed


def validate_settings(settings: dict[str, Any], errors: list[str]) -> None:
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

    stale_after = settings.get("status_stale_after_hours")
    if stale_after is not None:
        try:
            parsed_stale = float(stale_after)
        except (TypeError, ValueError):
            errors.append("settings.status_stale_after_hours must be a number")
        else:
            if parsed_stale <= 0:
                errors.append("settings.status_stale_after_hours must be positive")

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
            errors.append(f"settings.{key} must be a safe repository-relative path")

    try:
        ZoneInfo(str(settings.get("report_timezone")))
    except ZoneInfoNotFoundError:
        errors.append("settings.report_timezone is unknown")

    for key in ("sensitive_tags", "public_redact_tags", "x_search_queries"):
        if not isinstance(settings.get(key), list):
            errors.append(f"settings.{key} must be an array")

    sensitive = settings.get("sensitive_tags")
    redacted = settings.get("public_redact_tags")
    if isinstance(sensitive, list) and isinstance(redacted, list):
        missing = sorted(set(redacted) - set(sensitive))
        if missing:
            errors.append(
                "settings.public_redact_tags must be a subset of sensitive_tags: "
                + ", ".join(missing)
            )

    cadence = settings.get("platform_cadence_minutes")
    if not isinstance(cadence, dict):
        errors.append("settings.platform_cadence_minutes must be an object")
    else:
        for platform, value in cadence.items():
            if platform not in PLATFORMS:
                errors.append(f"unknown cadence platform: {platform}")
            parsed = safe_int(value, f"platform_cadence_minutes.{platform}", errors)
            if parsed is not None and parsed < 1:
                errors.append(
                    f"platform_cadence_minutes.{platform} must be at least 1"
                )

    allowlist = settings.get("article_host_allowlist", {})
    if not isinstance(allowlist, dict):
        errors.append("settings.article_host_allowlist must be an object")
    else:
        for source_id, hosts in allowlist.items():
            if not isinstance(source_id, str) or not source_id:
                errors.append("article_host_allowlist keys must be source ids")
                continue
            if not isinstance(hosts, list) or not hosts:
                errors.append(
                    f"article_host_allowlist.{source_id} must be a non-empty array"
                )
                continue
            for index, host in enumerate(hosts):
                if (
                    not isinstance(host, str)
                    or host != host.lower().rstrip(".")
                    or not DOMAIN.fullmatch(host)
                ):
                    errors.append(
                        f"article_host_allowlist.{source_id}[{index}] "
                        "must be a lowercase domain"
                    )


def validate_registry(
    registry: dict[str, Any],
    settings: dict[str, Any],
    errors: list[str],
) -> set[str]:
    sources = registry.get("sources")
    if not isinstance(sources, list):
        errors.append("config/sources.json sources must be an array")
        return set()

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

        expected = expected_platform_suffix(source_id)
        if expected is not None and platform != expected:
            errors.append(f"{source_id}: id suffix expects platform {expected}")
        if source.get("trust") not in TRUST_LEVELS:
            errors.append(f"{source_id}: invalid trust level")
        if source.get("perspective") not in PERSPECTIVES:
            errors.append(f"{source_id}: invalid perspective")
        priority = safe_int(source.get("priority"), f"{source_id}.priority", errors)
        if priority is not None and not 0 <= priority <= 100:
            errors.append(f"{source_id}: priority must be 0..100")
        if not isinstance(source.get("enabled"), bool):
            errors.append(f"{source_id}: enabled must be boolean")
        for key in ("tags", "languages", "article_hosts"):
            if key in source and not isinstance(source[key], list):
                errors.append(f"{source_id}: {key} must be an array")
        if source.get("enabled") is True:
            enabled_groups[str(source.get("group"))] += 1

    for setting_name in ("collection_delay_by_source", "article_host_allowlist"):
        mapping = settings.get(setting_name, {})
        if isinstance(mapping, dict):
            for source_id in mapping:
                if source_id not in ids:
                    errors.append(
                        f"{setting_name} references unknown source: {source_id}"
                    )

    queries = settings.get("x_search_queries", [])
    if isinstance(queries, list):
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

    minimums = settings.get("minimum_group_counts")
    if not isinstance(minimums, dict):
        errors.append("minimum_group_counts must be an object")
    else:
        for group, raw_minimum in minimums.items():
            minimum = safe_int(
                raw_minimum, f"minimum_group_counts.{group}", errors
            )
            if minimum is not None and enabled_groups[group] < minimum:
                errors.append(
                    f"group {group}: {enabled_groups[group]} enabled, "
                    f"minimum is {minimum}"
                )
    return ids


def validate_state(
    root: Path,
    settings: dict[str, Any],
    ids: set[str],
    errors: list[str],
) -> None:
    state_value = settings.get("state_file")
    if not isinstance(state_value, str) or not safe_relative_path(state_value):
        return
    path = root / state_value
    if not path.exists():
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: {exc}")
        return
    if not isinstance(state, dict):
        errors.append(f"{path}: must contain an object")
        return

    status = state.get("status")
    if status not in RUN_STATUSES:
        errors.append(f"{path}: invalid or missing status {status}")
    for key in STATE_COUNTERS:
        if key in state:
            nonnegative_int(state.get(key), f"{path}:{key}", errors)

    last_run = timestamp(state.get("last_run_at"), f"{path}:last_run_at", errors)
    last_clean = timestamp(
        state.get("last_successful_run_at"),
        f"{path}:last_successful_run_at",
        errors,
    )
    since = timestamp(state.get("since"), f"{path}:since", errors)
    if last_clean is not None and last_run is None:
        errors.append(f"{path}: last_successful_run_at requires last_run_at")
    if last_clean is not None and last_run is not None and last_clean > last_run:
        errors.append(f"{path}: last_successful_run_at is after last_run_at")
    if since is not None and last_run is not None and since > last_run:
        errors.append(f"{path}: since is after last_run_at")
    if status in {"ok", "idle"} and last_run is not None and last_clean != last_run:
        errors.append(
            f"{path}: clean run must set last_successful_run_at to last_run_at"
        )

    configuration_errors = state.get("configuration_errors", [])
    if not isinstance(configuration_errors, list) or not all(
        isinstance(value, str) for value in configuration_errors
    ):
        errors.append(f"{path}: configuration_errors must be an array of strings")

    per_source = state.get("per_source", {})
    if not isinstance(per_source, dict):
        errors.append(f"{path}: per_source must be an object")
        return
    for source_id, row in per_source.items():
        label = f"{path}:per_source.{source_id}"
        if source_id not in ids:
            errors.append(f"{path}: unknown per_source id {source_id}")
        if not isinstance(row, dict):
            errors.append(f"{label} must be an object")
            continue
        source_status = row.get("status")
        if source_status not in SOURCE_STATUSES:
            errors.append(f"{label}: invalid status {source_status}")
        checked = timestamp(row.get("checked_at"), f"{label}.checked_at", errors)
        successful = timestamp(
            row.get("last_success_at"), f"{label}.last_success_at", errors
        )
        next_due = timestamp(
            row.get("next_due_at"), f"{label}.next_due_at", errors
        )
        for name, value in (("checked_at", checked), ("last_success_at", successful)):
            if value is not None and last_run is not None and value > last_run:
                errors.append(f"{label}.{name} is after run last_run_at")
        if source_status == "skipped_cadence" and next_due is None:
            errors.append(f"{label}: skipped_cadence requires next_due_at")
        if source_status == "error":
            error_value = row.get("error")
            if not isinstance(error_value, str) or not SAFE_ERROR.fullmatch(error_value):
                errors.append(f"{label}: unsafe or missing public error category")


def validate_public_projection(
    row: dict[str, Any], path: Path, errors: list[str]
) -> None:
    if not isinstance(row.get("title"), str):
        errors.append(f"{path}: title must be a string")
    if not isinstance(row.get("text"), str):
        errors.append(f"{path}: text must be a string")
    if row.get("html") != "":
        errors.append(f"{path}: public html must be empty")
    media = row.get("media")
    if not isinstance(media, list):
        errors.append(f"{path}: media must be an array")
        media = []
    else:
        for value in media:
            if parsed_public_url(value) is None:
                errors.append(f"{path}: invalid public media URL")
    if not isinstance(row.get("tags"), list):
        errors.append(f"{path}: tags must be an array")

    raw = row.get("raw")
    if not isinstance(raw, dict):
        errors.append(f"{path}: raw must be an object")
        return
    policy = raw.get("archive_policy")
    if policy == "public_excerpt_v1":
        required = {
            "archive_policy", "content_sha256", "original_text_chars",
            "original_html_chars", "text_truncated", "media_count", "platform",
        }
        if set(raw) != required:
            errors.append(f"{path}: invalid public_excerpt_v1 fields")
        digest = raw.get("content_sha256")
        if not isinstance(digest, str) or not HEX_64.fullmatch(digest):
            errors.append(f"{path}: invalid content_sha256")
        for key in ("original_text_chars", "original_html_chars", "media_count"):
            nonnegative_int(raw.get(key), f"{path}:{key}", errors)
        if not isinstance(raw.get("text_truncated"), bool):
            errors.append(f"{path}: text_truncated must be boolean")
        if not isinstance(raw.get("platform"), dict):
            errors.append(f"{path}: raw.platform must be an object")
    elif policy == "public_redacted_v1":
        required = {"archive_policy", "redacted", "platform"}
        if set(raw) != required:
            errors.append(f"{path}: invalid public_redacted_v1 fields")
        if raw.get("redacted") is not True:
            errors.append(f"{path}: redacted must be true")
        if not isinstance(raw.get("platform"), dict):
            errors.append(f"{path}: raw.platform must be an object")
        if row.get("title") or row.get("text") or row.get("html") or media:
            errors.append(f"{path}: redacted projection contains public content")
    else:
        errors.append(f"{path}: unsupported archive policy {policy}")


def validate_archive(
    root: Path,
    settings: dict[str, Any],
    ids: set[str],
    errors: list[str],
) -> None:
    raw_value = settings.get("raw_root")
    if not isinstance(raw_value, str) or not safe_relative_path(raw_value):
        return
    raw_root = root / raw_value
    seen: dict[str, Path] = {}
    for path in raw_root.glob("*/*/*/items.ndjson"):
        try:
            rows = read_ndjson([path])
        except ValueError as exc:
            errors.append(str(exc))
            continue
        for row in rows:
            missing = REQUIRED_ITEM - row.keys()
            if missing:
                errors.append(f"{path}: item missing {sorted(missing)}")
            item_id = str(row.get("id", ""))
            if not item_id:
                errors.append(f"{path}: item id must not be empty")
            elif item_id in seen:
                errors.append(f"duplicate item id {item_id}: {seen[item_id]} and {path}")
            else:
                seen[item_id] = path
            if row.get("source") not in ids:
                errors.append(f"{path}: unknown source {row.get('source')}")
            if row.get("platform") not in PLATFORMS:
                errors.append(
                    f"{path}: unsupported item platform {row.get('platform')}"
                )
            if parsed_public_url(row.get("url")) is None:
                errors.append(f"{path}: invalid item URL")
            collected = timestamp(
                row.get("collected_at"), f"{path}:collected_at", errors,
                nullable=False,
            )
            published = timestamp(
                row.get("published_at"), f"{path}:published_at", errors
            )
            stamp = published or collected
            if stamp is not None:
                expected = raw_root / f"{stamp:%Y/%m/%d}" / "items.ndjson"
                if expected != path:
                    errors.append(f"{path}: item belongs in {expected}")
            validate_public_projection(row, path, errors)


def validate_error_archive(
    root: Path,
    settings: dict[str, Any],
    ids: set[str],
    errors: list[str],
) -> None:
    root_value = settings.get("error_root")
    if not isinstance(root_value, str) or not safe_relative_path(root_value):
        return
    for path in (root / root_value).glob("*/*/*/errors.ndjson"):
        try:
            rows = read_ndjson([path])
        except ValueError as exc:
            errors.append(str(exc))
            continue
        for row in rows:
            source_id = row.get("source")
            if source_id not in ids:
                errors.append(f"{path}: unknown error source {source_id}")
            parsed = parsed_public_url(row.get("url"))
            if parsed is None:
                errors.append(f"{path}: invalid public error URL")
            elif parsed.query or parsed.fragment:
                errors.append(f"{path}: error URL contains query or fragment")
            error_value = row.get("error")
            if not isinstance(error_value, str) or not SAFE_ERROR.fullmatch(error_value):
                errors.append(f"{path}: unsafe or missing public error category")
            timestamp(
                row.get("collected_at"), f"{path}:collected_at", errors,
                nullable=False,
            )


def validate_schema_files(root: Path, errors: list[str]) -> None:
    schema_root = root / "schemas"
    if not schema_root.exists():
        return
    expected = {
        "raw-item.schema.json": "War Reporter public source projection",
        "public-status.schema.json": "War Reporter public collection status v1",
    }
    for name, title in expected.items():
        path = schema_root / name
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: schema load failed: {exc}")
            continue
        if not isinstance(value, dict) or value.get("title") != title:
            errors.append(f"{path}: unexpected schema title")


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

    validate_settings(settings, errors)
    ids = validate_registry(registry, settings, errors)
    validate_state(root, settings, ids, errors)
    validate_archive(root, settings, ids, errors)
    validate_error_archive(root, settings, ids, errors)
    validate_schema_files(root, errors)
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
