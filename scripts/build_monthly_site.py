#!/usr/bin/env python3
"""Add monthly editorial reports to the static site built by build_site."""

from __future__ import annotations

import argparse
import calendar
import html
from datetime import date
from pathlib import Path

try:
    from .build_site import page, render_markdown
    from .build_weekly_site import period_days
    from .common import ROOT, load_json
except ImportError:
    from build_site import page, render_markdown
    from build_weekly_site import period_days
    from common import ROOT, load_json


def month_days(path: Path) -> list[str]:
    """Return all calendar days encoded by a YYYY-MM monthly filename."""
    try:
        first = date.fromisoformat(path.stem + "-01")
    except ValueError:
        return []
    last_day = calendar.monthrange(first.year, first.month)[1]
    return [
        date(first.year, first.month, day).isoformat()
        for day in range(1, last_day + 1)
    ]


def monthly_index_body(reports: list[Path]) -> str:
    links = "".join(
        f"<li><a href='{html.escape(path.stem, quote=True)}.html'>"
        f"{html.escape(path.stem)}</a></li>"
        for path in reports
    )
    return (
        "<p>Месячные редакционные сводки объединяют дневные и недельные "
        "отчёты в долгосрочную картину, сохраняя атрибуцию заявлений сторон "
        "и ограничения покрытия.</p>"
        + (f"<ul>{links}</ul>" if links else "<p>Месячных сводок пока нет.</p>")
    )


def month_navigation_html(root: Path, path: Path) -> str:
    """Generate trusted navigation links for the calendar month."""
    days = month_days(path)
    if not days:
        return ""

    summary_root = root / "reports/summary"
    daily_root = root / "reports/daily"
    day_rows: list[str] = []
    for day in days:
        links: list[str] = []
        if (summary_root / f"{day}.md").exists():
            links.append(
                f"<a href='../summaries/{html.escape(day, quote=True)}.html'>сводка</a>"
            )
        if (daily_root / f"{day}.md").exists():
            links.append(
                f"<a href='../reports/{html.escape(day, quote=True)}.html'>источники</a>"
            )
        if links:
            day_rows.append(
                f"<li>{html.escape(day)} — " + " · ".join(links) + "</li>"
            )

    weekly_root = root / "reports/weekly"
    weekly_rows: list[str] = []
    if weekly_root.exists():
        month_prefix = path.stem + "-"
        for weekly in sorted(weekly_root.glob("*.md"), reverse=True):
            if any(day.startswith(month_prefix) for day in period_days(weekly)):
                label = weekly.stem.replace("_", " — ")
                weekly_rows.append(
                    f"<li><a href='../weekly/{html.escape(weekly.stem, quote=True)}.html'>"
                    f"{html.escape(label)}</a></li>"
                )

    sections: list[str] = []
    if weekly_rows:
        sections.append(
            "<h3>Недельные сводки, пересекающие месяц</h3>"
            f"<ul>{''.join(weekly_rows)}</ul>"
        )
    if day_rows:
        sections.append(
            "<h3>Дневные отчёты месяца</h3>"
            f"<ul>{''.join(day_rows)}</ul>"
        )
    if not sections:
        return ""
    return "<section class='card'><h2>Состав месяца</h2>" + "".join(sections) + "</section>"


def inject_monthly_homepage(site: Path, reports: list[Path]) -> None:
    homepage = site / "index.html"
    if not homepage.exists():
        return
    text = homepage.read_text(encoding="utf-8")
    if "id='monthly-reports'" in text:
        return

    if reports:
        links = "".join(
            f"<li><a href='monthly/{html.escape(path.stem, quote=True)}.html'>"
            f"{html.escape(path.stem)}</a></li>"
            for path in reports
        )
        section = (
            "<section id='monthly-reports'><h2>Месячные сводки</h2>"
            f"<ul>{links}</ul></section>"
        )
    else:
        section = (
            "<section id='monthly-reports'><h2>Месячные сводки</h2>"
            "<p>Месячных сводок пока нет.</p></section>"
        )

    marker = "<h2>Дневные отчёты</h2>"
    if marker in text:
        text = text.replace(marker, section + marker, 1)
    else:
        text = text.replace("</body>", section + "</body>", 1)
    homepage.write_text(text, encoding="utf-8")


def build_monthly_site(root: Path) -> Path:
    settings = load_json(root / "config/settings.json")
    if not isinstance(settings, dict):
        raise ValueError("missing config/settings.json")

    site = root / settings["site_root"]
    if not (site / "index.html").exists():
        raise ValueError("base site is missing; run scripts.build_site first")

    monthly_root = root / "reports/monthly"
    reports = (
        sorted(monthly_root.glob("*.md"), reverse=True)
        if monthly_root.exists()
        else []
    )

    monthly_site = site / "monthly"
    monthly_site.mkdir(parents=True, exist_ok=True)
    (monthly_site / "index.html").write_text(
        page("Месячные сводки", monthly_index_body(reports), prefix="../"),
        encoding="utf-8",
    )

    for path in reports:
        body = (
            month_navigation_html(root, path)
            + f"<main class='report'>{render_markdown(path)}</main>"
        )
        (monthly_site / f"{path.stem}.html").write_text(
            page(
                f"Месячная сводка — {path.stem}",
                body,
                prefix="../",
            ),
            encoding="utf-8",
        )

    inject_monthly_homepage(site, reports)
    return monthly_site


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        print(build_monthly_site(args.root))
    except (OSError, ValueError) as exc:
        print(f"monthly site build failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
