"""Allowlist-based public collection status projection and renderer."""

from __future__ import annotations

import html
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .common import load_json, parse_time, utc_now
except ImportError:
    from common import load_json, parse_time, utc_now


STATUS_SCHEMA = "war-reporter-public-status-v1"
SOURCE_STATUSES = {
    "ok",
    "error",
    "skipped_config",
    "skipped_cadence",
    "unknown",
}
RUN_STATUSES = {"ok", "idle", "partial", "blocked", "failed", "unknown"}


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_time(value: Any) -> str | None:
    try:
        stamp = parse_time(value)
    except (TypeError, ValueError):
        return None
    return stamp.isoformat().replace("+00:00", "Z") if stamp else None


def _latest_time(values: list[Any]) -> str | None:
    parsed: list[datetime] = []
    for value in values:
        try:
            stamp = parse_time(value)
        except (TypeError, ValueError):
            continue
        if stamp is not None:
            parsed.append(stamp)
    if not parsed:
        return None
    return max(parsed).isoformat().replace("+00:00", "Z")


def _latest_archive_day(root: Path, raw_root: str) -> str | None:
    base = root / raw_root
    days = [
        path.parent.relative_to(base).as_posix().replace("/", "-")
        for path in base.glob("*/*/*/items.ndjson")
    ]
    return max(days) if days else None


def _latest_report_day(root: Path, report_root: str) -> str | None:
    days = [path.stem for path in (root / report_root).glob("*.md")]
    return max(days) if days else None


def _configured_sources(
    registry: dict[str, Any], settings: dict[str, Any]
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source in registry.get("sources", []):
        if not isinstance(source, dict) or source.get("enabled") is not True:
            continue
        rows.append(
            {
                "id": str(source.get("id", "")),
                "platform": str(source.get("platform", "unknown")),
                "group": str(source.get("group", "other")),
            }
        )
    queries = settings.get("x_search_queries", [])
    if isinstance(queries, list):
        for index, query in enumerate(queries, 1):
            if isinstance(query, str) and query.strip():
                rows.append(
                    {
                        "id": f"x-discovery-{index}",
                        "platform": "x",
                        "group": "x-discovery",
                    }
                )
    return rows


def _aggregate(
    sources: list[dict[str, str]],
    per_source: dict[str, Any],
    key: str,
) -> dict[str, dict[str, int]]:
    buckets: dict[str, Counter[str]] = {}
    for source in sources:
        bucket_name = source.get(key) or "unknown"
        bucket = buckets.setdefault(bucket_name, Counter())
        bucket["configured"] += 1
        row = per_source.get(source["id"], {})
        status = row.get("status") if isinstance(row, dict) else None
        status = status if status in SOURCE_STATUSES else "unknown"
        bucket[status] += 1
    return {
        name: {status: int(count) for status, count in sorted(counts.items())}
        for name, counts in sorted(buckets.items())
    }


def build_public_status(
    root: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    settings = load_json(root / "config/settings.json", default={})
    registry = load_json(root / "config/sources.json", default={})
    if not isinstance(settings, dict) or not isinstance(registry, dict):
        raise ValueError("missing config/settings.json or config/sources.json")
    state = load_json(root / settings["state_file"], default={})
    if not isinstance(state, dict):
        state = {}
    per_source = state.get("per_source", {})
    if not isinstance(per_source, dict):
        per_source = {}

    sources = _configured_sources(registry, settings)
    configured_ids = {source["id"] for source in sources}
    status_counts: Counter[str] = Counter()
    latest_success_values: list[Any] = []
    for source in sources:
        row = per_source.get(source["id"], {})
        status = row.get("status") if isinstance(row, dict) else None
        status = status if status in SOURCE_STATUSES else "unknown"
        status_counts[status] += 1
        if isinstance(row, dict):
            latest_success_values.append(row.get("last_success_at"))

    last_run_at = _safe_time(state.get("last_run_at"))
    current = (now or utc_now()).astimezone(UTC)
    stale_after_hours = max(
        1.0,
        float(
            settings.get(
                "status_stale_after_hours",
                max(1.0, float(settings.get("poll_seconds", 900)) * 4 / 3600),
            )
        ),
    )
    if last_run_at is None:
        age_hours = None
        stale = True
    else:
        last_run = parse_time(last_run_at)
        age_hours = max(
            0.0, (current - last_run).total_seconds() / 3600
        ) if last_run else None
        stale = age_hours is None or age_hours > stale_after_hours

    run_status = state.get("status")
    if run_status not in RUN_STATUSES:
        run_status = "unknown"

    return {
        "schema": STATUS_SCHEMA,
        "scope": "current-state-only",
        "generated_at": current.isoformat().replace("+00:00", "Z"),
        "run": {
            "status": run_status,
            "last_run_at": last_run_at,
            "since": _safe_time(state.get("since")),
            "selected_sources": _nonnegative_int(
                state.get("sources_configured")
            ),
            "attempted": _nonnegative_int(state.get("sources_attempted")),
            "succeeded": _nonnegative_int(state.get("sources_succeeded")),
            "skipped": _nonnegative_int(state.get("sources_skipped")),
            "errors": _nonnegative_int(state.get("errors")),
            "items_added": _nonnegative_int(state.get("items_added")),
        },
        "registry": {
            "configured_enabled": len(sources),
            "orphaned_state_sources": len(set(per_source) - configured_ids),
        },
        "source_status_counts": {
            status: int(status_counts.get(status, 0))
            for status in sorted(SOURCE_STATUSES)
        },
        "by_platform": _aggregate(sources, per_source, "platform"),
        "by_group": _aggregate(sources, per_source, "group"),
        "withholding": {
            "recent": _nonnegative_int(state.get("items_withheld_recent")),
            "undated": _nonnegative_int(state.get("items_withheld_undated")),
        },
        "freshness": {
            "stale": stale,
            "stale_after_hours": stale_after_hours,
            "last_run_age_hours": (
                round(age_hours, 2) if age_hours is not None else None
            ),
            "latest_source_success_at": _latest_time(
                latest_success_values
            ),
            "latest_archive_day": _latest_archive_day(
                root, settings["raw_root"]
            ),
            "latest_digest_day": _latest_report_day(
                root, settings["report_root"]
            ),
        },
        "degradation": {
            "configuration_skips": int(
                status_counts.get("skipped_config", 0)
            ),
            "source_errors": int(status_counts.get("error", 0)),
            "unknown_sources": int(status_counts.get("unknown", 0)),
        },
        "semantics": {
            "configured_is_not_working": True,
            "source_success_does_not_verify_claims": True,
            "error_details_omitted": True,
            "history_available": False,
        },
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "нет данных"
    if isinstance(value, bool):
        return "да" if value else "нет"
    return html.escape(str(value))


def _aggregate_table(
    title: str, rows: dict[str, dict[str, int]]
) -> str:
    statuses = [
        "configured", "ok", "error", "skipped_config",
        "skipped_cadence", "unknown",
    ]
    header = "".join(f"<th>{html.escape(value)}</th>" for value in statuses)
    body = "".join(
        "<tr>"
        f"<td>{html.escape(name)}</td>"
        + "".join(f"<td>{counts.get(status, 0)}</td>" for status in statuses)
        + "</tr>"
        for name, counts in rows.items()
    )
    return (
        f"<h2>{html.escape(title)}</h2>"
        "<table><thead><tr><th>Срез</th>"
        f"{header}</tr></thead><tbody>{body}</tbody></table>"
    )


def render_public_status(status: dict[str, Any]) -> str:
    run = status["run"]
    freshness = status["freshness"]
    withholding = status["withholding"]
    degradation = status["degradation"]
    labels = {
        "ok": "Полный проход завершён без зафиксированной деградации.",
        "idle": "Проход не требовал новых запросов из-за cadence.",
        "partial": "Часть выбранных источников недоступна или не настроена.",
        "blocked": "Проход не мог начаться из-за конфигурационного блокера.",
        "failed": "Ни один из запрошенных источников не завершился успешно.",
        "unknown": "Нет проверенного состояния последнего прохода.",
    }
    return (
        f"<p class='notice'><strong>{html.escape(run['status'])}</strong> — "
        f"{html.escape(labels[run['status']])}</p>"
        "<p>Это безопасная текущая проекция состояния. История доступности "
        "пока не сохраняется; количество настроенных источников не означает "
        "количество работающих источников.</p>"
        "<h2>Последний проход</h2>"
        "<table><tbody>"
        f"<tr><th>Последний запуск</th><td>{_fmt(run['last_run_at'])}</td></tr>"
        f"<tr><th>Устарело</th><td>{_fmt(freshness['stale'])}</td></tr>"
        f"<tr><th>Возраст состояния, часы</th><td>{_fmt(freshness['last_run_age_hours'])}</td></tr>"
        f"<tr><th>Выбрано / попыток / успешно / пропущено</th><td>"
        f"{run['selected_sources']} / {run['attempted']} / "
        f"{run['succeeded']} / {run['skipped']}</td></tr>"
        f"<tr><th>Ошибок источников</th><td>{run['errors']}</td></tr>"
        f"<tr><th>Добавлено записей</th><td>{run['items_added']}</td></tr>"
        f"<tr><th>Удержано embargo</th><td>recent: {withholding['recent']}; "
        f"undated: {withholding['undated']}</td></tr>"
        f"<tr><th>Конфигурационная деградация</th><td>"
        f"{degradation['configuration_skips']}</td></tr>"
        f"<tr><th>Последний успешный источник</th><td>"
        f"{_fmt(freshness['latest_source_success_at'])}</td></tr>"
        f"<tr><th>Последний день архива / дайджеста</th><td>"
        f"{_fmt(freshness['latest_archive_day'])} / "
        f"{_fmt(freshness['latest_digest_day'])}</td></tr>"
        "</tbody></table>"
        + _aggregate_table("По платформам", status["by_platform"])
        + _aggregate_table("По группам", status["by_group"])
    )


def write_public_status(
    root: Path, site: Path, *, now: datetime | None = None
) -> tuple[dict[str, Any], str]:
    status = build_public_status(root, now=now)
    (site / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return status, render_public_status(status)
