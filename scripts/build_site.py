#!/usr/bin/env python3
"""Render reports and full raw items into a small readable static site."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

try:
    from .common import ROOT, load_json, read_ndjson
except ImportError:
    from common import ROOT, load_json, read_ndjson

CSS = """
body{font-family:system-ui,sans-serif;max-width:1100px;margin:0 auto;padding:24px;line-height:1.5;background:#f6f7f9;color:#18191b}
a{color:#1659a7}.card{background:white;border:1px solid #ddd;border-radius:10px;padding:16px;margin:14px 0}
.meta{font-size:.86rem;color:#60646c}.text{white-space:pre-wrap}.tag{display:inline-block;background:#eef1f5;border-radius:12px;padding:2px 8px;margin:2px}
nav{display:flex;gap:14px;flex-wrap:wrap}.wide{overflow-wrap:anywhere}img{max-width:100%;height:auto}
"""


def page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='ru'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{CSS}</style><body><nav><a href='/'>Отчёты</a><a href='/raw/'>Сырые материалы</a></nav><h1>{html.escape(title)}</h1>{body}</body></html>"


def render_item(item: dict) -> str:
    media = "".join(
        f"<p><a href='{html.escape(url, quote=True)}'>media</a></p>"
        for url in item.get("media", [])
    )
    tags = "".join(f"<span class='tag'>{html.escape(str(tag))}</span>" for tag in item.get("tags", []))
    return (
        "<article class='card'>"
        f"<h2>{html.escape(item.get('title') or item.get('source_name') or item.get('source',''))}</h2>"
        f"<div class='meta'>{html.escape(str(item.get('published_at') or ''))} · "
        f"{html.escape(str(item.get('platform','')))} · {html.escape(str(item.get('perspective','')))} · "
        f"trust {html.escape(str(item.get('trust','')))}</div>"
        f"<p>{tags}</p><div class='text'>{html.escape(item.get('text') or '')}</div>{media}"
        f"<p class='wide'><a href='{html.escape(item.get('url',''), quote=True)}'>Оригинал</a> · "
        f"<code>{html.escape(item.get('id',''))}</code></p>"
        "</article>"
    )


def build_site(root: Path) -> Path:
    settings = load_json(root / "config/settings.json")
    site = root / settings["site_root"]
    site.mkdir(parents=True, exist_ok=True)
    report_root = root / settings["report_root"]
    reports = sorted(report_root.glob("*.md"), reverse=True) if report_root.exists() else []
    links = "".join(
        f"<li><a href='/reports/{path.stem}.html'>{path.stem}</a></li>" for path in reports
    )
    (site / "index.html").write_text(page("War Reporter", f"<ul>{links}</ul>"), encoding="utf-8")

    report_site = site / "reports"
    report_site.mkdir(exist_ok=True)
    for path in reports:
        text = path.read_text(encoding="utf-8")
        body = f"<pre class='card wide'>{html.escape(text)}</pre>"
        (report_site / f"{path.stem}.html").write_text(page(path.stem, body), encoding="utf-8")

    raw_root = root / settings["raw_root"]
    days = sorted({p.parent.relative_to(raw_root).as_posix().replace("/", "-") for p in raw_root.glob("*/*/*/items.ndjson")}, reverse=True)
    raw_site = site / "raw"
    raw_site.mkdir(exist_ok=True)
    day_links = "".join(f"<li><a href='/raw/{day}.html'>{day}</a></li>" for day in days)
    (raw_site / "index.html").write_text(page("Сырые материалы", f"<ul>{day_links}</ul>"), encoding="utf-8")
    for day in days:
        path = raw_root / day.replace("-", "/") / "items.ndjson"
        items = read_ndjson([path])
        body = f"<p>Материалов: {len(items)}</p>" + "".join(render_item(item) for item in items)
        (raw_site / f"{day}.html").write_text(page(f"Сырые материалы — {day}", body), encoding="utf-8")
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
