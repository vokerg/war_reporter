#!/usr/bin/env python3
"""Add weekly editorial reports to the static site built by build_site."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

try:
    from .build_site import page, render_markdown
    from .common import ROOT, load_json
except ImportError:
    from build_site import page, render_markdown
    from common import ROOT, load_json


SUMMARY_LINK_RE = re.compile(r"href=['\"]\.\./summary/(\d{4}-\d{2}-\d{2})\.md['\"]")
DAILY_LINK_RE = re.compile(r"href=['\"]\.\./daily/(\d{4}-\d{2}-\d{2})\.md['\"]")
SUMMARY_NAV_RE = re.compile(
    r"(<a href='([^']*)summaries/index\.html'>Сводки</a>)"
)


def render_weekly_markdown(path: Path) -> str:
    """Render repository markdown and translate repository-relative report links."""
    rendered = render_markdown(path)
    rendered = SUMMARY_LINK_RE.sub(r"href='../summaries/\1.html'", rendered)
    rendered = DAILY_LINK_RE.sub(r"href='../reports/\1.html'", rendered)
    return rendered


def weekly_index_body(reports: list[Path]) -> str:
    links = "".join(
        f"<li><a href='{html.escape(path.stem, quote=True)}.html'>"
        f"{html.escape(path.stem.replace('_', ' — '))}</a></li>"
        for path in reports
    )
    return (
        "<p>Недельные редакционные сводки объединяют дневные отчёты, "
        "дедуплицируют повторяющиеся сюжеты и отделяют подтверждённые "
        "последствия от заявлений сторон.</p>"
        + (f"<ul>{links}</ul>" if links else "<p>Недельных сводок пока нет.</p>")
    )


def inject_weekly_navigation(site: Path, reports: list[Path]) -> None:
    """Expose weekly reports in global navigation and on the site homepage."""
    for path in site.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        if ">Недельные сводки</a>" not in text:
            text = SUMMARY_NAV_RE.sub(
                r"\1<a href='\2weekly/index.html'>Недельные сводки</a>",
                text,
                count=1,
            )
        path.write_text(text, encoding="utf-8")

    homepage = site / "index.html"
    if not homepage.exists() or "id='weekly-reports'" in homepage.read_text(encoding="utf-8"):
        return

    text = homepage.read_text(encoding="utf-8")
    if reports:
        links = "".join(
            f"<li><a href='weekly/{html.escape(path.stem, quote=True)}.html'>"
            f"{html.escape(path.stem.replace('_', ' — '))}</a></li>"
            for path in reports
        )
        section = f"<section id='weekly-reports'><h2>Недельные сводки</h2><ul>{links}</ul></section>"
    else:
        section = "<section id='weekly-reports'><h2>Недельные сводки</h2><p>Недельных сводок пока нет.</p></section>"

    marker = "<h2>Дневные отчёты</h2>"
    if marker in text:
        text = text.replace(marker, section + marker, 1)
    else:
        text = text.replace("</body>", section + "</body>", 1)
    homepage.write_text(text, encoding="utf-8")


def build_weekly_site(root: Path) -> Path:
    settings = load_json(root / "config/settings.json")
    if not isinstance(settings, dict):
        raise ValueError("missing config/settings.json")

    site = root / settings["site_root"]
    if not (site / "index.html").exists():
        raise ValueError("base site is missing; run scripts.build_site first")

    weekly_root = root / "reports/weekly"
    reports = sorted(weekly_root.glob("*.md"), reverse=True) if weekly_root.exists() else []

    weekly_site = site / "weekly"
    weekly_site.mkdir(parents=True, exist_ok=True)
    (weekly_site / "index.html").write_text(
        page("Недельные сводки", weekly_index_body(reports), prefix="../"),
        encoding="utf-8",
    )

    for path in reports:
        body = f"<main class='report'>{render_weekly_markdown(path)}</main>"
        (weekly_site / f"{path.stem}.html").write_text(
            page(
                f"Недельная сводка — {path.stem.replace('_', ' — ')}",
                body,
                prefix="../",
            ),
            encoding="utf-8",
        )

    inject_weekly_navigation(site, reports)
    return weekly_site


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        print(build_weekly_site(args.root))
    except (OSError, ValueError) as exc:
        print(f"weekly site build failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
