from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from scripts.collector_adapters import collect_web


class FakeResponse:
    url = "https://example.com/news"
    text = """
    <html>
      <head>
        <title>Example news index</title>
        <meta property="article:published_time" content="2026-08-05T12:00:00Z">
      </head>
      <body><main><p>Public source snapshot text.</p></main></body>
    </html>
    """

    def raise_for_status(self) -> None:
        return None


class WebAdapterIntegrationTests(unittest.TestCase):
    def test_web_snapshot_path_resolves_private_article_helper(self) -> None:
        source = {
            "id": "example-web",
            "name": "Example",
            "platform": "web",
            "url": "https://example.com/news",
            "group": "media",
            "perspective": "mixed",
            "trust": "high",
            "priority": 50,
            "languages": ["en"],
            "tags": [],
            "enabled": True,
            "web_mode": "snapshot",
        }
        settings = {
            "user_agent": "test",
            "request_timeout_seconds": 5,
            "web_max_links": 2,
        }

        def fake_get(*_args, **_kwargs):
            return FakeResponse()

        # Patch the function's actual global namespace. This remains stable even
        # when the adapter is re-exported through the public collector facade.
        with patch.dict(collect_web.__globals__, {"safe_get": fake_get}):
            rows = collect_web(
                source,
                settings,
                datetime(2026, 8, 1, tzinfo=UTC),
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["published_at"], "2026-08-05T12:00:00Z")
        self.assertEqual(rows[0]["raw"]["content_type"], "web_snapshot")
        self.assertIn("Public source snapshot text", rows[0]["text"])


if __name__ == "__main__":
    unittest.main()
