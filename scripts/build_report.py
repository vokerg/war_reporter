#!/usr/bin/env python3
"""Build one transparent daily report directly from the raw archive."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

try:
    from .common import ROOT, clean_text, load_json, parse_time, read_ndjson
except ImportError:
    from common import ROOT, clean_text, load_json, parse_time, read_ndjson

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


def item_day(item: dict[str, Any]) -> str | None:
    stamp = parse_time(item.get("published_at")) or parse_time(item.get("collected_at"))
    return stamp.date().isoformat() if stamp else None


def choose_section(item: dict[str, Any]) -> str:
    tags = set(item.get("tags") or [])
    for key, _ in SECTION_ORDER:
        if key in tags:
            return key
    group = str(item.get("group", ""))
    if group == "ru-milbloggers":
        return "frontline"
    if group in {"official-ua", "official-ru"}:
        return "frontline"
    return "other"


def render_item(item: dict[str, Any]) -> str:
    title = clean_text(item.get("title"))
    text = clean_text(item.get("text"))
    summary = text[:700] + ("…" if len(text) > 700 else "")
    label = title or summary or "(материал без текста)"
    source = item.get("source_name") or item.get("source")
    trust = item.get("trust", "unknown")
    perspective = item.get("perspective", "unknown")
    published = item.get("published_at") or "время публикации не указано"
    return (
        f"- **{source}** · `{perspective}` · trust `{trust}` · {published}\n"
        f"  \n  {label}\n"
        f"  \n  [Оригинал]({item.get('url', '')}) · raw id `{item.get('id', '')}`"
    )


def build_report(root: Path, target_day: str) -> tuple[Path, str]:
    settings = load_json(root / "config/settings.json")
    day_path = root / settings["raw_root"] / target_day.replace("-", "/") / "items.ndjson"
    items = [row for row in read_ndjson([day_path]) if item_day(row) == target_day]
    items.sort(
        key=lambda row: (
            row.get("published_at") or row.get("collected_at") or "",
            -len(row.get("text") or ""),
        ),
        reverse=True,
    )
    by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_section[choose_section(item)].append(item)

    sources = Counter(str(row.get("source_name") or row.get("source")) for row in items)
    platforms = Counter(str(row.get("platform", "unknown")) for row in items)
    groups = Counter(str(row.get("group", "other")) for row in items)
    lines = [
        f"# Война России против Украины — массив источников за {target_day}",
        "",
        "> Это raw-first отчёт: он не скрывает исходный массив за цепочкой claims/assessments. "
        "Каждый пункт ведёт к оригиналу и к сохранённой записи.",
        "",
        "## Покрытие",
        "",
        f"- Сохранено материалов: **{len(items)}**",
        f"- Уникальных источников: **{len(sources)}**",
        f"- Платформы: **{', '.join(f'{k}: {v}' for k, v in platforms.most_common()) or 'нет данных'}**",
        f"- Группы: **{', '.join(f'{k}: {v}' for k, v in groups.most_common()) or 'нет данных'}**",
        "",
    ]
    if not items:
        lines += [
            "## Данных пока нет",
            "",
            "Запустите `python -m scripts.collect --lookback-hours 72`, затем повторите генерацию.",
            "",
        ]
    else:
        for key, title in SECTION_ORDER + [("other", "Прочие материалы")]:
            rows = by_section.get(key, [])
            if not rows:
                continue
            lines += [f"## {title}", ""]
            lines += [render_item(row) for row in rows]
            lines.append("")
        lines += [
            "## Реестр источников дня",
            "",
            "| Источник | Материалов |",
            "|---|---:|",
        ]
        lines += [f"| {name} | {count} |" for name, count in sources.most_common()]
        lines.append("")
    output = root / settings["report_root"] / f"{target_day}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines).rstrip() + "\n"
    output.write_text(content, encoding="utf-8")
    return output, content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("day", nargs="?", default=(date.today() - timedelta(days=1)).isoformat())
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        path, _ = build_report(args.root, args.day)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"report build failed: {exc}")
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
