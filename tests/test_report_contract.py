from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_report import build_report
from scripts.common import append_unique


class ReportContractTests(unittest.TestCase):
    def test_legacy_refetch_marker_is_not_rendered(self) -> None:
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
        item = {
            "id": "legacy-item",
            "source": "source-a",
            "source_name": "Source A",
            "platform": "web",
            "url": "https://example.com/story",
            "published_at": "2026-08-05T12:00:00Z",
            "collected_at": "2026-08-05T13:00:00Z",
            "title": "A source publication",
            "text": "Public excerpt",
            "media": [],
            "author": "",
            "language": "en",
            "group": "international-media",
            "perspective": "mixed",
            "trust": "high",
            "tags": [],
            "html": "",
            "raw": {"requires_refetch": True},
        }
        append_unique(
            root / "data/raw/2026/08/05/items.ndjson",
            [item],
        )

        _, report = build_report(root, "2026-08-05")
        self.assertIn("A source publication", report)
        self.assertNotIn("refetch", report.lower())
        self.assertNotIn("реконструирован", report.lower())


if __name__ == "__main__":
    unittest.main()
