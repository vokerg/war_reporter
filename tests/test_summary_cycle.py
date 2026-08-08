from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_site import build_site


ROOT = Path(__file__).resolve().parents[1]


class SummaryCycleTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        (root / "reports/daily").mkdir(parents=True)
        (root / "reports/summary").mkdir(parents=True)
        settings = {
            "poll_seconds": 900,
            "report_timezone": "Europe/Kyiv",
            "raw_root": "data/raw",
            "state_file": "data/state.json",
            "report_root": "reports/daily",
            "site_root": "site",
            "status_stale_after_hours": 1,
            "site_publication_delay_hours": 0,
            "site_sensitive_delay_hours": 0,
            "sensitive_tags": [],
            "public_redact_tags": [],
            "x_search_queries": [],
        }
        (root / "config/settings.json").write_text(
            json.dumps(settings), encoding="utf-8"
        )
        (root / "config/sources.json").write_text(
            json.dumps({"version": 1, "sources": []}), encoding="utf-8"
        )
        (root / "data").mkdir()
        (root / "data/state.json").write_text(
            json.dumps(
                {
                    "status": "ok",
                    "last_run_at": "2026-08-08T00:00:00Z",
                    "last_successful_run_at": "2026-08-08T00:00:00Z",
                    "sources_configured": 0,
                    "sources_attempted": 0,
                    "sources_succeeded": 0,
                    "sources_skipped": 0,
                    "errors": 0,
                    "items_added": 0,
                    "per_source": {},
                }
            ),
            encoding="utf-8",
        )
        return root

    def test_site_pairs_summary_with_source_digest(self) -> None:
        root = self.make_root()
        day = "2026-08-07"
        (root / f"reports/daily/{day}.md").write_text(
            "# Source digest\n\nFull attributable source material.",
            encoding="utf-8",
        )
        (root / f"reports/summary/{day}.md").write_text(
            "# Daily summary\n\nImportant synthesis.\n\n<script>alert(1)</script>",
            encoding="utf-8",
        )

        site = build_site(root)
        index = (site / "index.html").read_text(encoding="utf-8")
        summary_index = (site / "summaries/index.html").read_text(
            encoding="utf-8"
        )
        summary = (site / f"summaries/{day}.html").read_text(
            encoding="utf-8"
        )
        digest = (site / f"reports/{day}.html").read_text(
            encoding="utf-8"
        )

        self.assertIn(f"summaries/{day}.html", index)
        self.assertIn(f"reports/{day}.html", index)
        self.assertIn(f"{day}.html", summary_index)
        self.assertIn(f"../reports/{day}.html", summary)
        self.assertIn(f"../summaries/{day}.html", digest)
        self.assertIn("Important synthesis.", summary)
        self.assertNotIn("<script>alert(1)</script>", summary)

    def test_operator_contract_keeps_synthesis_in_chatgpt(self) -> None:
        operator = (ROOT / "docs/chat-operator.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        for text in (operator, agents):
            self.assertIn("reports/summary/YYYY-MM-DD.md", text)
            self.assertIn("ChatGPT", text)
        self.assertIn("There is no OpenAI API key", operator)
        self.assertIn("A chat collection cycle is complete only after", agents)
        self.assertIn("does not invoke ChatGPT", agents)


if __name__ == "__main__":
    unittest.main()
