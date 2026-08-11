from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_report import build_report
from scripts.common import append_unique


class SummaryContextReportTests(unittest.TestCase):
    def test_daily_digest_embeds_context_and_keeps_full_source_ledger(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        (root / "config/settings.json").write_text(
            json.dumps(
                {
                    "raw_root": "data/raw",
                    "state_file": "data/state.json",
                    "report_root": "reports/daily",
                    "report_timezone": "Europe/Kyiv",
                    "sensitive_tags": [],
                    "public_redact_tags": [],
                }
            ),
            encoding="utf-8",
        )
        state_path = root / "data/state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(
            json.dumps(
                {
                    "status": "ok",
                    "errors": 0,
                    "items_withheld_recent": 0,
                    "items_withheld_undated": 0,
                }
            ),
            encoding="utf-8",
        )
        rows = [
            {
                "id": "odesa-event",
                "source": "ua-odesa-oblast-tg",
                "source_name": "Odesa Oblast Administration",
                "platform": "telegram",
                "url": "https://example.com/odesa-event",
                "published_at": "2026-08-09T10:00:00Z",
                "collected_at": "2026-08-09T10:01:00Z",
                "title": "",
                "text": "На Одещині наслідки масованої атаки БПЛА.",
                "media": [],
                "author": "",
                "language": "uk",
                "group": "official-ua",
                "perspective": "ukrainian",
                "trust": "primary",
                "tags": ["strikes"],
                "html": "",
                "raw": {"archive_policy": "public_excerpt_v1"},
            },
            {
                "id": "off-topic",
                "source": "milblogger",
                "source_name": "Milblogger",
                "platform": "telegram",
                "url": "https://example.com/off-topic",
                "published_at": "2026-08-09T11:00:00Z",
                "collected_at": "2026-08-09T11:01:00Z",
                "title": "",
                "text": "Лесные пожары во Франции продолжаются.",
                "media": [],
                "author": "",
                "language": "ru",
                "group": "ru-milbloggers",
                "perspective": "russian",
                "trust": "low",
                "tags": [],
                "html": "",
                "raw": {"archive_policy": "public_excerpt_v1"},
            },
        ]
        append_unique(root / "data/raw/2026/08/09/items.ndjson", rows)

        _, report = build_report(root, "2026-08-09")

        context_at = report.index("## Контекст для редакционного синтеза")
        ledger_at = report.index("## Ракетные, авиационные и беспилотные удары")
        self.assertLess(context_at, ledger_at)
        self.assertIn("Отфильтровано как off-topic: **1**", report)
        self.assertIn("Odesa Oblast Administration", report)
        self.assertIn("Лесные пожары во Франции продолжаются.", report)
        self.assertIn("## Реестр источников дня", report)


if __name__ == "__main__":
    unittest.main()
