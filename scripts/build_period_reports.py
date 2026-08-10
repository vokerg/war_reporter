#!/usr/bin/env python3
"""Build missing daily digests and compact weekly source snapshots."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

try:
    from .build_report import (
        SECTION_ORDER,
        build_report,
        choose_section,
        item_day,
        markdown_escape,
        markdown_url,
        raw_paths_for_local_day,
        report_timezone,
    )
    from .common import ROOT, clean_text, load_json, read_ndjson
except ImportError:
    from build_report import (
        SECTION_ORDER,
        build_report,
        choose_section,
        item_day,
        markdown_escape,
        markdown_url,
        raw_paths_for_local_day,
        report_timezone,
    )
    from common import ROOT, clean_text, load_json, read_ndjson


def days_between(start: str, end: str) -> list[str]:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    if last < first:
        raise ValueError("end date precedes start date")
    out: list[str] = []
    current = first
    while current <= last:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


def load_period_items(root: Path, start: str, end: str) -> list[dict[str, Any]]:
    settings = load_json(root / "config/settings.json")
    if not isinstance(settings, dict):
        raise ValueError("missing config/settings.json")
    timezone = report_timezone(settings)
    by_id: dict[str, dict[str, Any]] = {}
    for day in days_between(start, end):
        for path in raw_paths_for_local_day(root, settings["raw_root"], day, timezone):
            for row in read_ndjson([path]):
                local_day = item_day(row, timezone)
                if local_day is None or local_day < start or local_day > end:
                    continue
                item_id = str(row.get("id", ""))
                if item_id:
                    by_id[item_id] = row
    rows = list(by_id.values())
    rows.sort(
        key=lambda row: row.get("published_at") or row.get("collected_at") or "",
        reverse=True,
    )
    return rows


def short_item(item: dict[str, Any]) -> str:
    source = markdown_escape(str(item.get("source_name") or item.get("source") or "unknown"))
    title = clean_text(item.get("title"))
    text = clean_text(item.get("text"))
    label = title or text[:280] or "(материал без текста)"
    if len(label) > 300:
        label = label[:300] + "…"
    url = markdown_url(item.get("url"))
    link = f"[оригинал]({url})" if url else "оригинал недоступен"
    published = markdown_escape(str(item.get("published_at") or "время не указано"))
    return f"- **{source}** · {published} — {markdown_escape(label)} · {link}"


def build_weekly(root: Path, start: str, end: str) -> tuple[Path, str]:
    settings = load_json(root / "config/settings.json")
    if not isinstance(settings, dict):
        raise ValueError("missing config/settings.json")
    timezone = report_timezone(settings)
    items = load_period_items(root, start, end)
    sources = Counter(str(row.get("source_name") or row.get("source") or "unknown") for row in items)
    platforms = Counter(str(row.get("platform", "unknown")) for row in items)
    groups = Counter(str(row.get("group", "other")) for row in items)
    days = Counter(item_day(row, timezone) or "undated" for row in items)
    sections: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in items:
        sections[choose_section(row)].append(row)

    lines = [
        f"# Недельный снепшот источников: {start} — {end}",
        "",
        "> Пилотный недельный source snapshot. Это агрегированная картина публикаций настроенных источников, а не независимо верифицированная разведывательная оценка.",
        "",
        f"**Часовой пояс:** `{timezone.key}`",
        "",
        "## Покрытие недели",
        "",
        f"- Материалов: **{len(items)}**",
        f"- Уникальных источников: **{len(sources)}**",
        "- Платформы: **" + (", ".join(f"{k}: {v}" for k, v in platforms.most_common()) or "нет данных") + "**",
        "- Группы: **" + (", ".join(f"{k}: {v}" for k, v in groups.most_common()) or "нет данных") + "**",
        "",
        "### По дням",
        "",
        "| День | Материалов | Daily digest |",
        "|---|---:|---|",
    ]
    for day in days_between(start, end):
        lines.append(f"| {day} | {days.get(day, 0)} | [отчёт](../daily/{day}.md) |")

    lines += ["", "## Тематическая структура", "", "| Тема | Материалов |", "|---|---:|"]
    titles = dict(SECTION_ORDER)
    titles["other"] = "Прочие материалы"
    for key, title in list(SECTION_ORDER) + [("other", "Прочие материалы")]:
        count = len(sections.get(key, []))
        if count:
            lines.append(f"| {title} | {count} |")

    lines += ["", "## Наиболее активные источники", "", "| Источник | Материалов |", "|---|---:|"]
    for source, count in sources.most_common(25):
        lines.append(f"| {markdown_escape(source)} | {count} |")

    lines += ["", "## Репрезентативные публикации по темам", ""]
    for key, title in list(SECTION_ORDER) + [("other", "Прочие материалы")]:
        rows = sections.get(key, [])
        if not rows:
            continue
        lines += [f"### {title}", ""]
        lines += [short_item(row) for row in rows[:8]]
        if len(rows) > 8:
            lines.append(f"- _Ещё материалов в этой теме: {len(rows) - 8}._")
        lines.append("")

    lines += [
        "## Ограничения",
        "",
        "- Снепшот отражает только сохранённую публичную проекцию источников.",
        "- Повторение одной и той же информации разными публикациями не является независимым подтверждением.",
        "- Оперативно-чувствительные записи остаются редактированными согласно политике репозитория.",
        "- Для аналитической оценки событий поверх этого слоя нужен отдельный corroboration/synthesis pass.",
        "",
    ]
    weekly_root = root / "reports/weekly"
    weekly_root.mkdir(parents=True, exist_ok=True)
    output = weekly_root / f"{start}_{end}.md"
    content = "\n".join(lines).rstrip() + "\n"
    output.write_text(content, encoding="utf-8")
    return output, content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    backfill = sub.add_parser("backfill")
    backfill.add_argument("--from", dest="start", required=True)
    backfill.add_argument("--to", dest="end", required=True)
    weekly = sub.add_parser("weekly")
    weekly.add_argument("--from", dest="start", required=True)
    weekly.add_argument("--to", dest="end", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    if args.command == "backfill":
        for day in days_between(args.start, args.end):
            path, _ = build_report(args.root, day)
            print(path)
        return 0
    path, _ = build_weekly(args.root, args.start, args.end)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
