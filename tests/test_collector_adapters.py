from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

import requests

from scripts.collector_adapters import collect_web


HTML = """
<html>
  <head>
    <title>Example news index</title>
    <meta property="article:published_time" content="2026-08-05T12:00:00Z">
  </head>
  <body><main><p>Public source snapshot text.</p></main></body>
</html>
"""


def fake_response() -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response.url = "https://example.com/news"
    response.encoding = "utf-8"
    response._content = HTML.encode("utf-8")
    return response


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
        with (
            patch(
                "requests.sessions.Session.get",
                return_value=fake_response(),
            ),
            patch(
                "scripts.collector_common.ensure_public_url",
                side_effect=lambda value: value,
            ),
        ):
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
