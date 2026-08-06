#!/usr/bin/env python3
"""Render reports and delayed raw items into a readable static site."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import markdown

try:
    from .build_report import is_permanently_redacted, is_sensitive
    from .common import (
        ROOT,
        load_json,
        parse_time,
        read_ndjson,
        utc_now,
    )
    from .html_safety import sanitize_report_html
    from .public_status import write_public_status
except ImportError:
    from build_report import is_permanently_redacted, is_sensitive
    from common import (
        ROOT,
        load_json,
        parse_time,
        read_ndjson,
        utc_now,
    )
    from html_safety import sanitize_report_html
    from public_status import write_public_status

CSS = """
body{font-family:system-ui,sans-serif;max-width:1180px;margin:0 auto;padding:24px;line-height:1.55;background:#f6f7f9;color:#18191b}
a{color:#1659a7}.card{background:white;border:1px solid #ddd;border-radius:10px;padding:16px;margin:14px 0}
.meta{font-size:.86rem;color:#60646c}.text{white-space:pre-wrap}.tag{display:inline-block;background:#eef1f5;border-radius:12px;padding:2px 8px;margin:2px}
nav{display:flex;gap:14px;flex-wrap:wrap}.wide{overflow-wrap:anywhere}img{max-width:100%;height:auto;border-radius:8px}
.controls{position:sticky;top:0;background:#f6f7f9;padding:10px 0;display:flex;gap:8px;flex-wrap:wrap;z-index:2}
.controls input,.controls select{font:inherit;padding:8px;min-width:180px}.notice{background:#fff8d8;border:1px solid #e6cf65;padding:12px;border-radius:8px}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:6px;text-align:left}
code,pre{white-space:pre-wrap;overflow-wrap:anywhere}.report{background:#fff;border:1px solid #ddd;border-radius:10px;padding:20px}
.status-ok{background:#e9f7ed}.status-partial,.status-blocked,.status-failed,.status-unknown{background:#fff0e6}
"""

FILTER_JS = """
const q=document.getElementById('q');
const platform=document.getElementById('platform');
const group=document.getElementById('group');
function applyFilters(){
  const needle=(q.value||'').toLowerCase();
  document.querySelectorAll('[data-card]').forEach(card=>{
    const matchesText=!needle||card.dataset.search.includes(needle);
    const matchesPlatform=!platform.value||card.dataset.platform===platform.value;
    const matchesGroup=!group.value||card.dataset.group===group.value;
    card.hidden=!(matchesText&&matchesPlatform&&matchesGroup);
  });
}
[q,platform,group].forEach(node=>node.addEventListener('input',applyFilters));
""".strip()
FILTER_SCRIPT = f"<script>{FILTER_JS}</script>"
FILTER_SCRIPT_HASH = base64.b64encode(
    hashlib.sha256(FILTER_JS.encode("utf-8")).digest()
).decode("ascii")


def page(
    title: str, body: str, *, prefix: str
) -> str:
    nav = (
        f"<a href='{prefix}index.html'>Отчёты</a>"
        f"<a href='{prefix}raw/index.html'>Сырые материалы</a>"
        f"<a href='{prefix}maps/index.html'>Карты из источников</a>"
        f"<a href='{prefix}status/index.html'>Статус сбора</a>"
    )
    csp = (
        "default-src 'none'; style-src 'unsafe-inline'; "
        f"script-src 'sha256-{FILTER_SCRIPT_HASH}'; "
        "base-uri 'none'; form-action 'none'"
    )
    return (
        "<!doctype html><html lang='ru'><head>"
        "<meta charset='utf-8'>"
        "<meta name='referrer' content='no-referrer'>"
        f"<meta http-equiv='Content-Security-Policy' content=\"{csp}\">"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        f"<style>{CSS}</style></head><body>"
        f"<nav>{nav}</nav><h1>{html.escape(title)}</h1>"
        f"{body}</body></html>"
    )


def item_age_hours(
    item: dict[str, Any], now: datetime
) -> float | None:
    stamp = parse_time(item.get("collected_at")) or parse_time(
        item.get("published_at")
    )
    if stamp is None:
        return None
    return max(0.0, (now - stamp).total_seconds() / 3600)


def publication_mode(
    item: dict[str, Any],
    settings: dict[str, Any],
    now: datetime,
) -> str:
    age = item_age_hours(item, now)
    general_delay = float(
        settings.get("site_publication_delay_hours", 24)
    )
    sensitive_delay = float(
        settings.get("site_sensitive_delay_hours", 72)
    )
    if age is None or age < general_delay:
        return "delayed"
    if is_permanently_redacted(item, settings):
        return "redacted"
    if is_sensitive(item, settings) and age < sensitive_delay:
        return "redacted"
    return "full"


def public_href(value: Any) -> str | None:
    url = str(value or "").strip()
    if any(ord(char) < 32 for char in url):
        return None
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return html.escape(url, quote=True)


def media_html(urls: list[str]) -> str:
    rows: list[str] = []
    for raw_url in urls:
        url = public_href(raw_url)
        if url is None:
            continue
        rows.append(
            f"<p><a href='{url}' rel='noopener noreferrer'>"
            "Медиа из источника</a></p>"
        )
    return "".join(rows)


def original_link(item: dict[str, Any]) -> str:
    url = public_href(item.get("url"))
    if url is None:
        return "<p class='wide'>Оригинал недоступен · "
    return (
        f"<p class='wide'><a href='{url}' rel='noopener noreferrer'>"
        "Оригинал</a> · "
    )


def render_item(
    item: dict[str, Any],
    settings: dict[str, Any],
    now: datetime,
) -> str:
    mode = publication_mode(item, settings, now)
    tags = "".join(
        f"<span class='tag'>{html.escape(str(tag))}</span>"
        for tag in item.get("tags", [])
    )
    source = str(
        item.get("title")
        or item.get("source_name")
        or item.get("source", "")
    )
    if mode == "full":
        text = html.escape(item.get("text") or "")
        media = media_html(item.get("media", []))
        notice = ""
    elif mode == "redacted":
        text = (
            "Текст и медиа временно скрыты: запись может содержать "
            "актуальные оперативные детали."
        )
        media = ""
        notice = "<p class='notice'>Оперативная задержка публикации.</p>"
    else:
        text = (
            "Полный текст появится после минимальной задержки "
            "публичной публикации."
        )
        media = ""
        notice = "<p class='notice'>Запись ещё находится в задержке публикации.</p>"

    platform = str(item.get("platform", ""))
    group = str(item.get("group", ""))
    public_search_text = str(item.get("text", "")) if mode == "full" else ""
    searchable = " ".join(
        [
            source,
            str(item.get("source_name", "")),
            public_search_text,
            " ".join(str(tag) for tag in item.get("tags", [])),
        ]
    ).lower()
    return (
        "<article class='card' data-card "
        f"data-search='{html.escape(searchable, quote=True)}' "
        f"data-platform='{html.escape(platform, quote=True)}' "
        f"data-group='{html.escape(group, quote=True)}'>"
        f"<h2>{html.escape(source)}</h2>"
        f"<div class='meta'>{html.escape(str(item.get('published_at') or ''))} · "
        f"{html.escape(platform)} · {html.escape(group)} · "
        f"{html.escape(str(item.get('perspective','')))} · "
        f"trust {html.escape(str(item.get('trust','')))}</div>"
        f"<p>{tags}</p>{notice}<div class='text'>{text}</div>{media}"
        f"{original_link(item)}"
        f"<code>{html.escape(item.get('id',''))}</code></p>"
        "</article>"
    )


def controls(items: list[dict[str, Any]]) -> str:
    platforms = sorted(
        {str(item.get("platform", "")) for item in items}
    )
    groups = sorted({str(item.get("group", "")) for item in items})
    platform_options = "".join(
        f"<option value='{html.escape(value, quote=True)}'>"
        f"{html.escape(value)}</option>"
        for value in platforms
        if value
    )
    group_options = "".join(
        f"<option value='{html.escape(value, quote=True)}'>"
        f"{html.escape(value)}</option>"
        for value in groups
        if value
    )
    return (
        "<div class='controls'>"
        "<input id='q' type='search' placeholder='Поиск по тексту, источнику, тегам'>"
        f"<select id='platform'><option value=''>Все платформы</option>{platform_options}</select>"
        f"<select id='group'><option value=''>Все группы</option>{group_options}</select>"
        "</div>"
    )


def read_day_items(raw_root: Path, day: str) -> list[dict[str, Any]]:
    path = raw_root / day.replace("-", "/") / "items.ndjson"
    items = read_ndjson([path])
    items.sort(
        key=lambda item: (
            item.get("published_at")
            or item.get("collected_at")
            or ""
        ),
        reverse=True,
    )
    return items


def build_site(root: Path) -> Path:
    settings = load_json(root / "config/settings.json")
    if not isinstance(settings, dict):
        raise ValueError("missing config/settings.json")
    site = root / settings["site_root"]
    site.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    public_status, status_body = write_public_status(root, site, now=now)
    status_dir = site / "status"
    status_dir.mkdir(exist_ok=True)
    status_body += (
        "<p><a href='../status.json'>Machine-readable status JSON</a></p>"
    )
    (status_dir / "index.html").write_text(
        page("Статус сбора", status_body, prefix="../"),
        encoding="utf-8",
    )

    report_root = root / settings["report_root"]
    reports = (
        sorted(report_root.glob("*.md"), reverse=True)
        if report_root.exists()
        else []
    )
    links = "".join(
        f"<li><a href='reports/{path.stem}.html'>{path.stem}</a></li>"
        for path in reports
    )
    run_status = str(public_status["run"]["status"])
    stale = bool(public_status["freshness"]["stale"])
    status_class = html.escape(run_status, quote=True)
    status_summary = (
        f"<p class='notice status-{status_class}'>"
        f"Статус сбора: <strong>{html.escape(run_status)}</strong>; "
        f"состояние устарело: {'да' if stale else 'нет'}. "
        "<a href='status/index.html'>Подробности</a></p>"
    )
    (site / "index.html").write_text(
        page(
            "War Reporter",
            status_summary + f"<ul>{links}</ul>",
            prefix="",
        ),
        encoding="utf-8",
    )

    report_site = site / "reports"
    report_site.mkdir(exist_ok=True)
    for path in reports:
        text = path.read_text(encoding="utf-8")
        rendered = markdown.markdown(
            text,
            extensions=["tables", "sane_lists"],
            output_format="html5",
        )
        rendered = sanitize_report_html(rendered)
        body = f"<main class='report'>{rendered}</main>"
        (report_site / f"{path.stem}.html").write_text(
            page(path.stem, body, prefix="../"),
            encoding="utf-8",
        )

    raw_root = root / settings["raw_root"]
    days = sorted(
        {
            path.parent.relative_to(raw_root)
            .as_posix()
            .replace("/", "-")
            for path in raw_root.glob("*/*/*/items.ndjson")
        },
        reverse=True,
    )

    raw_site = site / "raw"
    raw_site.mkdir(exist_ok=True)
    day_links = "".join(
        f"<li><a href='{day}.html'>{day}</a></li>"
        for day in days
    )
    (raw_site / "index.html").write_text(
        page(
            "Сырые материалы",
            (
                "<p>Текст и медиа публикуются с задержкой; "
                "оперативно-чувствительные записи задерживаются дольше.</p>"
                f"<ul>{day_links}</ul>"
            ),
            prefix="../",
        ),
        encoding="utf-8",
    )
    for day in days:
        items = read_day_items(raw_root, day)
        body = (
            f"<p>Материалов: {len(items)}</p>"
            + controls(items)
            + "".join(
                render_item(item, settings, now) for item in items
            )
            + FILTER_SCRIPT
        )
        (raw_site / f"{day}.html").write_text(
            page(
                f"Сырые материалы — {day}",
                body,
                prefix="../",
            ),
            encoding="utf-8",
        )

    map_site = site / "maps"
    map_site.mkdir(exist_ok=True)
    map_days: list[str] = []
    map_items_by_day: dict[str, list[dict[str, Any]]] = {}
    for day in days:
        map_items = [
            item
            for item in read_day_items(raw_root, day)
            if set(item.get("tags") or []).intersection(
                {"map", "maps"}
            )
        ]
        if map_items:
            map_days.append(day)
            map_items_by_day[day] = map_items
    map_links = "".join(
        f"<li><a href='{day}.html'>{day}</a></li>"
        for day in map_days
    )
    (map_site / "index.html").write_text(
        page(
            "Карты из источников",
            (
                "<p>Это сохранённые картографические материалы "
                "источников, а не единая подтверждённая карта контроля. "
                "Медиа публикуются с оперативной задержкой.</p>"
                f"<ul>{map_links}</ul>"
            ),
            prefix="../",
        ),
        encoding="utf-8",
    )
    for day, items in map_items_by_day.items():
        body = controls(items) + "".join(
            render_item(item, settings, now) for item in items
        ) + FILTER_SCRIPT
        (map_site / f"{day}.html").write_text(
            page(
                f"Карты из источников — {day}",
                body,
                prefix="../",
            ),
            encoding="utf-8",
        )
    return site


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        print(build_site(args.root))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"site build failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
