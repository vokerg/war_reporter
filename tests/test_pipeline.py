from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_report import build_report
from scripts.build_site import build_site
from scripts.common import append_unique, stable_id
from scripts.validate import validate


class PipelineTests(unittest.TestCase):
    def make_root(self) -> Path:
        temp = Path(tempfile.mkdtemp())
        (temp / "config").mkdir()
        (temp / "data/raw/2026/08/05").mkdir(parents=True)
        (temp / "config/settings.json").write_text(json.dumps({
            "raw_root": "data/raw", "error_root": "data/errors",
            "state_file": "data/state.json", "report_root": "reports/daily",
            "site_root": "site",
        }), encoding="utf-8")
        (temp / "config/sources.json").write_text(json.dumps({
            "version": 1,
            "sources": [{
                "id": "source-a", "name": "Source A", "platform": "telegram",
                "url": "https://t.me/source_a", "group": "osint",
                "perspective": "mixed", "trust": "high", "priority": 80,
                "languages": ["en"], "tags": ["frontline"], "enabled": True,
            }],
        }), encoding="utf-8")
        return temp

    def item(self) -> dict:
        return {
            "id": "abc", "source": "source-a", "source_name": "Source A",
            "platform": "telegram", "url": "https://t.me/source_a/1",
            "published_at": "2026-08-05T12:00:00Z",
            "collected_at": "2026-08-05T12:01:00Z", "title": "",
            "text": "Complete source text", "html": "<p>Complete source text</p>",
            "media": [], "author": "Source A", "language": "en", "group": "osint",
            "perspective": "mixed", "trust": "high", "tags": ["frontline"],
            "raw": {"post": "source_a/1"},
        }

    def test_append_unique(self) -> None:
        root = self.make_root()
        path = root / "data/raw/2026/08/05/items.ndjson"
        self.assertEqual(append_unique(path, [self.item()]), 1)
        self.assertEqual(append_unique(path, [self.item()]), 0)
        self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_report_and_site(self) -> None:
        root = self.make_root()
        path = root / "data/raw/2026/08/05/items.ndjson"
        append_unique(path, [self.item()])
        report, text = build_report(root, "2026-08-05")
        self.assertTrue(report.exists())
        self.assertIn("Source A", text)
        self.assertIn("Complete source text", text)
        site = build_site(root)
        self.assertTrue((site / "raw/2026-08-05.html").exists())
        self.assertIn("Complete source text", (site / "raw/2026-08-05.html").read_text())

    def test_registry_and_raw_validate(self) -> None:
        root = self.make_root()
        append_unique(root / "data/raw/2026/08/05/items.ndjson", [self.item()])
        self.assertEqual(validate(root), [])

    def test_stable_id(self) -> None:
        first = stable_id("a", "https://example.com/1", "2026-08-05T00:00:00Z", "x")
        second = stable_id("a", "https://example.com/1", "2026-08-05T00:00:00Z", "x")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
