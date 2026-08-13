from __future__ import annotations

import unittest

from scripts.summary_context_render import render_summary_context


class SummaryContextSafetyTests(unittest.TestCase):
    def test_untrusted_markdown_and_html_are_escaped_in_context(self) -> None:
        row = {
            "id": "unsafe",
            "source": "unsafe-source",
            "source_name": "Bad <script>alert(1)</script> [source](https://evil.invalid)",
            "group": "international-media",
            "perspective": "mixed",
            "platform": "rss",
            "trust": "high",
            "published_at": "2026-08-09T10:00:00Z",
            "collected_at": "2026-08-09T10:01:00Z",
            "title": "",
            "text": "Russian drone strike in Odesa Ukraine. <script>alert(2)</script> [click](https://evil.invalid)",
            "url": "https://example.com/story",
            "tags": [],
            "raw": {"archive_policy": "public_excerpt_v1"},
        }

        context = render_summary_context("2026-08-09", [row], {})

        self.assertNotIn("<script>", context)
        self.assertNotIn("[source](https://evil.invalid)", context)
        self.assertNotIn("[click](https://evil.invalid)", context)
        self.assertIn("\\<script\\>", context)
        self.assertIn("[оригинал](https://example.com/story)", context)


if __name__ == "__main__":
    unittest.main()
