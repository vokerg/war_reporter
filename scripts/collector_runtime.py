"""Collection orchestration, cadence, embargo and persistence."""

from __future__ import annotations

from .collector_common import *  # noqa: F401,F403
from .collector_adapters import *  # noqa: F401,F403


_TRANSIENT_SOURCE_STATE_KEYS = {"error", "reason", "next_due_at"}


def collect_one(
    source: dict[str, Any],
    settings: dict[str, Any],
    since: datetime,
) -> list[dict[str, Any]]:
    collector = COLLECTORS.get(source.get("platform"))
    if collector is None:
        raise CollectionError(
            f"unsupported platform: {source.get('platform')}"
        )
    return collector(source, settings, since)


def append_errors(root: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    day = utc_now().strftime("%Y/%m/%d")
    path = root / day / "errors.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row, ensure_ascii=False, separators=(",", ":")
                )
                + "\n"
            )


def public_error_summary(exc: Exception) -> str:
    """Return a stable public-safe category without exception details."""
    if isinstance(exc, requests.exceptions.Timeout):
        code = "timeout"
    elif isinstance(exc, requests.exceptions.TooManyRedirects):
        code = "redirect_error"
    elif isinstance(exc, requests.exceptions.SSLError):
        code = "tls_error"
    elif isinstance(exc, requests.exceptions.ConnectionError):
        code = "connection_error"
    elif isinstance(exc, requests.exceptions.HTTPError):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        code = f"http_{status}" if isinstance(status, int) else "http_error"
    elif isinstance(exc, json.JSONDecodeError):
        code = "invalid_json"
    elif isinstance(exc, CollectionError):
        text = str(exc).lower()
        if text.startswith("x api "):
            match = re.match(r"x api (\d{3})", text)
            code = f"x_api_http_{match.group(1)}" if match else "x_api_error"
        elif "dns lookup" in text:
            code = "dns_error"
        elif "private destination" in text or "unsafe url" in text:
            code = "unsafe_destination"
        elif "cross-host redirect" in text:
            code = "cross_host_redirect"
        elif "too many redirects" in text:
            code = "redirect_error"
        elif "not configured" in text:
            code = "missing_configuration"
        else:
            code = "collection_error"
    else:
        code = "unexpected_error"
    return f"{type(exc).__name__}: {code}"


def public_source_url(value: Any) -> str:
    """Remove userinfo, query and fragment from persisted source metadata."""
    parsed = urlparse(str(value or ""))
    if not parsed.scheme or not parsed.hostname:
        return ""
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = host if port is None else f"{host}:{port}"
    return parsed._replace(
        netloc=netloc,
        params="",
        query="",
        fragment="",
    ).geturl()


def next_source_state(
    previous: dict[str, Any], **updates: Any
) -> dict[str, Any]:
    """Preserve durable health fields while clearing stale transient details."""
    state = {
        key: value
        for key, value in previous.items()
        if key not in _TRANSIENT_SOURCE_STATE_KEYS
    }
    state.update(updates)
    return state


def item_storage_delay_hours(
    item: dict[str, Any], settings: dict[str, Any]
) -> float:
    delays = [float(settings.get("collection_delay_hours", 0))]
    by_group = settings.get("collection_delay_by_group", {})
    by_tag = settings.get("collection_delay_by_tag", {})
    by_source = settings.get("collection_delay_by_source", {})
    if isinstance(by_group, dict):
        delays.append(float(by_group.get(str(item.get("group", "")), 0)))
    if isinstance(by_tag, dict):
        delays.extend(
            float(by_tag.get(str(tag), 0))
            for tag in item.get("tags", [])
        )
    if isinstance(by_source, dict):
        delays.append(float(by_source.get(str(item.get("source", "")), 0)))
    return max(delays)


def item_storage_state(
    item: dict[str, Any], settings: dict[str, Any], now: datetime
) -> str:
    delay = item_storage_delay_hours(item, settings)
    if delay <= 0:
        return "storable"
    published = parse_time(item.get("published_at"))
    if published is None:
        return "withheld_undated"
    if published > now - timedelta(hours=delay):
        return "withheld_recent"
    return "storable"


def item_is_storable(
    item: dict[str, Any], settings: dict[str, Any], now: datetime
) -> bool:
    return item_storage_state(item, settings, now) == "storable"


def source_cadence_minutes(
    source: dict[str, Any], settings: dict[str, Any]
) -> int:
    explicit = source.get("cadence_minutes")
    if explicit is not None:
        return max(1, int(explicit))
    platform_cadence = settings.get("platform_cadence_minutes", {})
    fallback = max(1, int(settings.get("poll_seconds", 900)) // 60)
    return max(
        1, int(platform_cadence.get(source.get("platform"), fallback))
    )


def source_is_due(
    source: dict[str, Any],
    previous: dict[str, Any],
    settings: dict[str, Any],
    now: datetime,
    *,
    force: bool,
) -> tuple[bool, str | None]:
    if force:
        return True, None
    last_success = parse_time(previous.get("last_success_at"))
    if last_success is None:
        return True, None
    next_due = last_success + timedelta(
        minutes=source_cadence_minutes(source, settings)
    )
    return now >= next_due, iso(next_due)


def run_collection(
    root: Path = ROOT,
    *,
    lookback_hours: int | None = None,
    workers: int | None = None,
    groups: set[str] | None = None,
    platforms: set[str] | None = None,
    source_ids: set[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    settings = load_json(root / "config/settings.json")
    registry = load_json(root / "config/sources.json")
    if not isinstance(settings, dict) or not isinstance(registry, dict):
        raise ValueError(
            "missing config/settings.json or config/sources.json"
        )
    settings = dict(settings)
    settings["_x_sources_by_handle"] = {
        source_handle(str(row.get("url", ""))).lower(): row
        for row in registry.get("sources", [])
        if isinstance(row, dict)
        and row.get("platform") == "x"
        and source_handle(str(row.get("url", "")))
    }
    lookback = (
        lookback_hours
        if lookback_hours is not None
        else int(settings["default_lookback_hours"])
    )
    if lookback < 1:
        raise ValueError("lookback_hours must be at least 1")
    now = utc_now()
    since = now - timedelta(hours=lookback)
    all_sources = list(registry.get("sources", [])) + (
        x_discovery_sources(settings)
    )
    known_source_ids = {str(row.get("id")) for row in all_sources}
    if source_ids:
        unknown = sorted(source_ids - known_source_ids)
        if unknown:
            raise ValueError(f"unknown source ids: {', '.join(unknown)}")
    selected = [
        row
        for row in all_sources
        if row.get("enabled", True)
        and (not groups or row.get("group") in groups)
        and (not platforms or row.get("platform") in platforms)
        and (not source_ids or row.get("id") in source_ids)
    ]
    selected.sort(
        key=lambda row: (-int(row.get("priority", 0)), row["id"])
    )
    worker_count = (
        workers
        if workers is not None
        else env_int("WAR_REPORTER_WORKERS", int(settings["workers"]))
    )
    if worker_count < 1:
        raise ValueError("workers must be at least 1")

    previous_state = load_json(
        root / settings["state_file"], default={}
    )
    if not isinstance(previous_state, dict):
        previous_state = {}
    previous_per_source = previous_state.get("per_source", {})
    if not isinstance(previous_per_source, dict):
        previous_per_source = {}
    per_source: dict[str, Any] = dict(previous_per_source)

    configuration_errors: list[str] = []
    missing_x_token = not os.getenv("X_BEARER_TOKEN")
    due: list[dict[str, Any]] = []
    skipped = 0
    for source in selected:
        source_id = source["id"]
        previous = previous_per_source.get(source_id, {})
        if not isinstance(previous, dict):
            previous = {}
        if source.get("platform") == "x" and missing_x_token:
            message = "X_BEARER_TOKEN is not configured"
            if message not in configuration_errors:
                configuration_errors.append(message)
            per_source[source_id] = next_source_state(
                previous,
                status="skipped_config",
                checked_at=iso(now),
                reason=message,
            )
            skipped += 1
            continue
        is_due, next_due_at = source_is_due(
            source, previous, settings, now, force=force
        )
        if not is_due:
            per_source[source_id] = next_source_state(
                previous,
                status="skipped_cadence",
                checked_at=iso(now),
                next_due_at=next_due_at,
            )
            skipped += 1
            continue
        due.append(source)

    raw_root = root / settings["raw_root"]
    errors: list[dict[str, Any]] = []
    total_added = 0
    total_withheld_recent = 0
    total_withheld_undated = 0
    succeeded = 0
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        future_to_source = {
            pool.submit(collect_one, source, settings, since): source
            for source in due
        }
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            source_id = source["id"]
            previous = previous_per_source.get(source_id, {})
            if not isinstance(previous, dict):
                previous = {}
            try:
                fetched_items = future.result()
                storage_states = [
                    item_storage_state(item, settings, now)
                    for item in fetched_items
                ]
                eligible_items = [
                    item
                    for item, storage_state in zip(fetched_items, storage_states)
                    if storage_state == "storable"
                ]
                items = [
                    public_projection(item, settings) for item in eligible_items
                ]
                withheld_recent = storage_states.count("withheld_recent")
                withheld_undated = storage_states.count("withheld_undated")
                total_withheld_recent += withheld_recent
                total_withheld_undated += withheld_undated
                added = 0
                grouped: dict[Path, list[dict[str, Any]]] = {}
                for item in items:
                    path = raw_path(
                        raw_root,
                        item.get("published_at"),
                        item["collected_at"],
                    )
                    grouped.setdefault(path, []).append(item)
                for path, rows in grouped.items():
                    added += append_unique(path, rows)
                total_added += added
                succeeded += 1
                per_source[source_id] = {
                    "status": "ok",
                    "fetched": len(fetched_items),
                    "stored": len(items),
                    "withheld_recent": withheld_recent,
                    "withheld_undated": withheld_undated,
                    "added": added,
                    "checked_at": iso(),
                    "last_success_at": iso(),
                }
                LOG.info(
                    "%s: fetched=%d added=%d",
                    source_id,
                    len(fetched_items),
                    added,
                )
            except Exception as exc:
                public_error = public_error_summary(exc)
                row = {
                    "source": source_id,
                    "platform": source.get("platform"),
                    "url": public_source_url(source.get("url")),
                    "collected_at": iso(),
                    "error": public_error,
                }
                errors.append(row)
                per_source[source_id] = next_source_state(
                    previous,
                    status="error",
                    checked_at=row["collected_at"],
                    error=public_error,
                )
                LOG.warning("%s: %s", source_id, public_error)

    append_errors(root / settings["error_root"], errors)

    attempted = len(due)
    selected_non_x = sum(
        1 for source in selected if source.get("platform") != "x"
    )
    if attempted and succeeded == 0:
        status = "failed"
    elif attempted == 0 and configuration_errors and selected_non_x == 0:
        status = "blocked"
    elif errors or configuration_errors:
        status = "partial"
    elif attempted == 0:
        status = "idle"
    else:
        status = "ok"

    state = {
        "last_run_at": iso(),
        "since": iso(since),
        "status": status,
        "sources_configured": len(selected),
        "sources_attempted": attempted,
        "sources_succeeded": succeeded,
        "sources_skipped": skipped,
        "items_added": total_added,
        "items_withheld_recent": total_withheld_recent,
        "items_withheld_undated": total_withheld_undated,
        "errors": len(errors),
        "configuration_errors": configuration_errors,
        "per_source": per_source,
    }
    atomic_json(root / settings["state_file"], state)
    return state
