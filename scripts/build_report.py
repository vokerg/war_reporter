#!/usr/bin/env python3
"""Build a transparent daily source digest directly from the raw archive."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from .common import (
        ROOT,
        clean_text,
        load_json,
        parse_time,
        read_ndjson,
    )
    from .summary_context_render import render_summary_context
except ImportError:
    from common import (
        ROOT,
        clean_text,
        load_json,
        parse_time,
        read_ndjson,
    )
    from summary_context_render import render_summary_context

SECTION_ORDER = [
    ("frontline", "Фронт и наземные операции"),
    ("strikes", "Ракетные, авиационные и беспилотные удары"),
    ("air-defence", "ПВО"),
    ("drones", "Беспилотные системы"),
    ("naval", "Чёрное море и морская война"),
    ("civilian-harm", "Последствия для гражданских"),
    ("energy", "Энергетика и инфраструктура"),
    ("military-support", "Военная помощь и дипломатия"),
    ("investigations", "OSINT и расследования"),
]


def report_timezone(settings: dict[str, Any]) -> ZoneInfo:
    name = str(settings.get("report_timezone", "UTC"))
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown report_timezone: {name}") from exc


def local_today(settings: dict[str, Any], now: datetime | None = None) -> date:
    stamp = now or datetime.now(UTC)
    return stamp.astimezone(report_timezone(settings)).date()


def item_time(item: dict[str, Any]) -> datetime | None:
    return parse_time(item.get("published_at")) or parse_time(
        item.get("collected_at")
    )


def item_day(item: dict[str, Any], timezone: ZoneInfo) -> str | None:
    stamp = item_time(item)
    return stamp.astimezone(timezone).date().isoformat() if stamp else None


def raw_paths_for_local_day(
    root: Path,
    raw_root: str,
    target_day: str,
    timezone: ZoneInfo,
) -> list[Path]:
    day = date.fromisoformat(target_day)
    start_local = datetime.combine(day, time.min, tzinfo=timezone)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)
    current = start_utc.date()
    last = end_utc.date()
    paths: list[Path] = []
    while current <= last:
        paths.append(
            root
            / raw_root
            / f"{current:%Y/%m/%d}"
            / "items.ndjson"
        )
        current += timedelta(days=1)
    return paths


def load_items_for_local_day(
    root: Path,
    raw_root: str,
    target_day: str,
    timezone: ZoneInfo,
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in read_ndjson(
        raw_paths_for_local_day(root, raw_root, target_day, timezone)
    ):
        if item_day(row, timezone) != target_day:
            continue
        item_id = str(row.get("id", ""))
        if item_id:
            by_id[item_id] = row
    rows = list(by_id.values())
    rows.sort(
        key=lambda row: (
            row.get("published_at")
            or row.get("collected_at")
            or "",
            -len(row.get("text") or ""),
        ),
        reverse=True,
    )
    return rows


def load_summary_history(
    root: Path,
    raw_root: str,
    target_day: str,
    timezone: ZoneInfo,
    *,
    history_days: int = 7,
) -> dict[str, list[dict[str, Any]]]:
    target = date.fromisoformat(target_day)
    history: dict[str, list[dict[str, Any]]] = {}
    for offset in range(1, history_days + 1):
        day = (target - timedelta(days=offset)).isoformat()
        rows = load_items_for_local_day(root, raw_root, day, timezone)
        if rows:
            history[day] = rows
    return history


def choose_section(item: dict[str, Any]) -> str:
    tags = set(item.get("tags") or [])
    for key, _ in SECTION_ORDER:
        if key in tags:
            return key
    if tags.intersection({"map", "maps", "osint"}):
        return "investigations"
    group = str(item.get("group", ""))
    if group == "ru-milbloggers":
        return "frontline"
    if group in {"official-ua", "official-ru"}:
        return "frontline"
    return "other"


def markdown_escape(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for char in ("`", "*", "_", "[", "]", "<", ">"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def markdown_url(value: Any) -> str | None:
    url = str(value or "")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return quote(url, safe=":/%?&=#@+~!$,;'*-._")


def is_sensitive(item: dict[str, Any], settings: dict[str, Any]) -> bool:
    sensitive_tags = set(settings.get("sensitive_tags", []))
    return bool(
        sensitive_tags.intersection(str(tag) for tag in item.get("tags", []))
    )


def is_permanently_redacted(
    item: dict[str, Any], settings: dict[str, Any]
) -> bool:
    redact_tags = set(settings.get("public_redact_tags", []))
    return bool(
        redact_tags.intersection(str(tag) for tag in item.get("tags", []))
    )


def render_item(item: dict[str, Any], settings: dict[str, Any]) -> str:
    source = markdown_escape(
        str(item.get("source_name") or item.get("source") or "")
    )
    trust = markdown_escape(str(item.get("trust", "unknown")))
    perspective = markdown_escape(str(item.get("perspective", "unknown")))
    published = markdown_escape(
        str(item.get("published_at") or "время публикации не указано")
    )
    url = markdown_url(item.get("url"))
    raw_id = markdown_escape(str(item.get("id", "")))

    notes: list[str] = []
    if is_permanently_redacted(item, settings):
        label = (
            "Подробный фрагмент не включён автоматически: "
            "материал может содержать актуальные оперативные детали."
        )
        notes.append("оперативно-чувствительный материал")
    else:
        title = clean_text(item.get("title"))
        text = clean_text(item.get("text"))
        summary = text[:700] + ("…" if len(text) > 700 else "")
        label = title or summary or "(материал без текста)"
    note_line = (
        f"\n  \n  _{markdown_escape('; '.join(notes))}_" if notes else ""
    )
    original = f"[Оригинал]({url})" if url else "Оригинал недоступен"
    return (
        f"- **{source}** · `{perspective}` · trust `{trust}` · {published}\n"
        f"  \n  {markdown_escape(label)}"
        f"{note_line}\n"
        f"  \n  {original} · raw id `{raw_id}`"
    )


def build_report(root: Path, target_day: str) -> tuple[Path, str]:
    settings = load_json(root / "config/settings.json")
    if not isinstance(settings, dict):
        raise ValueError("missing config/settings.json")
    timezone = report_timezone(settings)
    items = load_items_for_local_day(
        root, settings["raw_root"], target_day, timezone
    )

    by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_section[choose_section(item)].append(item)

    sources = Counter(
        str(row.get("source_name") or row.get("source")) for row in items
    )
    platforms = Counter(str(row.get("platform", "unknown")) for row in items)
    groups = Counter(str(row.get("group", "other")) for row in items)
    sensitive = sum(is_permanently_redacted(row, settings) for row in items)
    state = load_json(root / settings["state_file"], default={})
    if not isinstance(state, dict):
        state = {}

    lines = [
        f"# Дайджест источников о войне за {target_day}",
        "",
        (
            "> Автоматический дайджест источников, а не проверенная "
            "аналитическая оценка. Он показывает покрытие, атрибуцию "
            "и ссылки на исходные записи. Независимая проверка и "
            "синтез должны выполняться отдельно."
        ),
        "",
        f"**Часовой пояс отчёта:** `{timezone.key}`",
        "",
        "## Покрытие",
        "",
        f"- Сохранено материалов: **{len(items)}**",
        f"- Уникальных источников: **{len(sources)}**",
        (
            "- Платформы: **"
            + (
                ", ".join(
                    f"{key}: {value}" for key, value in platforms.most_common()
                )
                or "нет данных"
            )
            + "**"
        ),
        (
            "- Группы: **"
            + (
                ", ".join(
                    f"{key}: {value}" for key, value in groups.most_common()
                )
                or "нет данных"
            )
            + "**"
        ),
        (
            f"- Материалов с автоматически скрытым фрагментом: "
            f"**{sensitive}**"
        ),
        (
            f"- Материалов, удержанных временной задержкой в последнем проходе: "
            f"**{state.get('items_withheld_recent', 'unknown')}**"
        ),
        (
            f"- Недатированных материалов, не допущенных в публичный архив: "
            f"**{state.get('items_withheld_undated', 'unknown')}**"
        ),
        (
            f"- Последний collection status: "
            f"**{state.get('status', 'unknown')}**; "
            f"errors: **{state.get('errors', 'unknown')}**"
        ),
        "",
    ]
    if not items:
        lines += [
            "## Данных пока нет",
            "",
            (
                "Запустите `python -m scripts.collect "
                "--lookback-hours 72 --force`, затем повторите генерацию."
            ),
            "",
        ]
    else:
        history = load_summary_history(
            root,
            settings["raw_root"],
            target_day,
            timezone,
        )
        lines += render_summary_context(target_day, items, history).splitlines()
        lines.append("")

        for key, title in SECTION_ORDER + [("other", "Прочие материалы")]:
            rows = by_section.get(key, [])
            if not rows:
                continue
            lines += [f"## {title}", ""]
            lines += [render_item(row, settings) for row in rows]
            lines.append("")
        lines += [
            "## Реестр источников дня",
            "",
            "| Источник | Материалов |",
            "|---|---:|",
        ]
        lines += [
            f"| {markdown_escape(name)} | {count} |"
            for name, count in sources.most_common()
        ]
        lines.append("")

    output = root / settings["report_root"] / f"{target_day}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines).rstrip() + "\n"
    output.write_text(content, encoding="utf-8")
    return output, content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("day", nargs="?")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        settings = load_json(args.root / "config/settings.json")
        if not isinstance(settings, dict):
            raise ValueError("missing config/settings.json")
        target_day = args.day or (
            local_today(settings) - timedelta(days=1)
        ).isoformat()
        path, _ = build_report(args.root, target_day)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"report build failed: {exc}")
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
