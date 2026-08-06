from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import requests

from scripts.collector_adapters import collect_rss
from scripts.collector_common import CollectionError
from scripts.publisher_fetch import publisher_get, publisher_url_allowed


class FakeSession:
    def __init__(self, responses: list[requests.Response]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    def get(self, url: str, **_kwargs) -> requests.Response:
        self.calls.append(url)
        response = self.responses.pop(0)
        response.url = url
        return response


def response(status: int, *, location: str | None = None) -> requests.Response:
    value = requests.Response()
    value.status_code = status
    value._content = b"feed"
    if location is not None:
        value.headers["Location"] = location
    return value


class PublisherFetchTests(unittest.TestCase):
    def source(self) -> dict:
        return {
            "id": "news-rss",
            "name": "News",
            "platform": "rss",
            "url": "https://feeds.example.com/rss.xml",
            "group": "media",
            "perspective": "mixed",
            "trust": "high",
            "priority": 10,
            "tags": [],
            "enabled": True,
        }

    def test_source_host_parent_and_subdomains_are_allowed(self) -> None:
        source = self.source()
        settings = {}
        self.assertTrue(
            publisher_url_allowed(
                source, settings, "https://feeds.example.com/story"
            )
        )
        self.assertTrue(
            publisher_url_allowed(
                source, settings, "https://www.example.com/story"
            )
        )
        self.assertTrue(
            publisher_url_allowed(
                source, settings, "https://media.example.com/story"
            )
        )

    def test_explicit_source_allowlist_is_supported(self) -> None:
        settings = {
            "article_host_allowlist": {
                "news-rss": ["publisher.example.org"]
            }
        }
        self.assertTrue(
            publisher_url_allowed(
                self.source(),
                settings,
                "https://www.publisher.example.org/story",
            )
        )

    def test_malformed_allowlist_is_ignored(self) -> None:
        settings = {
            "article_host_allowlist": {
                "news-rss": "evil.example"
            }
        }
        self.assertFalse(
            publisher_url_allowed(
                self.source(), settings, "https://evil.example/story"
            )
        )

    def test_external_http_and_credentialed_urls_are_rejected(self) -> None:
        source = self.source()
        settings = {}
        for url in (
            "https://evil.example/story",
            "http://www.example.com/story",
            "https://user:pass@example.com/story",
        ):
            self.assertFalse(publisher_url_allowed(source, settings, url))

    def test_external_redirect_is_blocked_before_second_request(self) -> None:
        session = FakeSession(
            [response(302, location="https://evil.example/internal")]
        )
        with patch(
            "scripts.publisher_fetch.ensure_public_url",
            side_effect=lambda value: value,
        ):
            with self.assertRaisesRegex(
                CollectionError, "publisher host is not allowed"
            ):
                publisher_get(
                    session,
                    self.source(),
                    {},
                    "https://feeds.example.com/start",
                    timeout=5,
                )
        self.assertEqual(session.calls, ["https://feeds.example.com/start"])

    def test_allowed_redirect_chain_is_fetched(self) -> None:
        session = FakeSession(
            [
                response(302, location="https://www.example.com/story"),
                response(200),
            ]
        )
        with patch(
            "scripts.publisher_fetch.ensure_public_url",
            side_effect=lambda value: value,
        ):
            final = publisher_get(
                session,
                self.source(),
                {},
                "https://feeds.example.com/start",
                timeout=5,
            )
        self.assertEqual(final.status_code, 200)
        self.assertEqual(
            session.calls,
            [
                "https://feeds.example.com/start",
                "https://www.example.com/story",
            ],
        )

    def test_relative_redirect_remains_under_policy(self) -> None:
        session = FakeSession(
            [response(301, location="/article/1"), response(200)]
        )
        with patch(
            "scripts.publisher_fetch.ensure_public_url",
            side_effect=lambda value: value,
        ):
            publisher_get(
                session,
                self.source(),
                {},
                "https://feeds.example.com/start",
                timeout=5,
            )
        self.assertEqual(
            session.calls[-1], "https://feeds.example.com/article/1"
        )

    def test_disallowed_rss_entry_is_not_fetched_or_published(self) -> None:
        parsed = SimpleNamespace(
            bozo=False,
            entries=[
                {
                    "id": "entry-1",
                    "title": "Supplied title",
                    "summary": "Supplied summary",
                    "link": "https://evil.example/phishing",
                }
            ],
        )
        settings = {"request_timeout_seconds": 5}
        feed_response = response(200)
        feed_response.url = self.source()["url"]
        with patch(
            "scripts.collector_adapters.session_for", return_value=object()
        ), patch(
            "scripts.collector_adapters.publisher_get",
            return_value=feed_response,
        ), patch(
            "scripts.collector_adapters.feedparser.parse",
            return_value=parsed,
        ), patch(
            "scripts.collector_adapters.extract_publisher_article"
        ) as article_fetch:
            rows = collect_rss(
                self.source(),
                settings,
                datetime(2026, 8, 1, tzinfo=UTC),
            )
        article_fetch.assert_not_called()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], self.source()["url"])
        self.assertEqual(rows[0]["raw"]["link"], self.source()["url"])
        self.assertNotIn("evil.example", str(rows[0]))


if __name__ == "__main__":
    unittest.main()
