from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build_site import build_site, page, public_href
from scripts.collect import run_collection
from scripts.html_safety import sanitize_report_html
from scripts.public_archive import harden_public_projection
from scripts.validate import validate


class SecurityBoundaryTests(unittest.TestCase):
    def test_permanent_redaction_drops_title_hash_and_lengths(self) -> None:
        item = {
            "title": "Exact unit location",
            "text": "secret",
            "html": "<p>secret</p>",
            "media": ["https://example.com/secret.jpg"],
            "tags": ["precise-location"],
        }
        projected = {
            **item,
            "raw": {
                "archive_policy": "public_excerpt_v1",
                "content_sha256": "guessing-oracle",
                "original_text_chars": 6,
                "original_html_chars": 13,
                "media_count": 1,
                "platform": {"post": "source/1"},
            },
        }
        result = harden_public_projection(
            projected,
            item,
            {"public_redact_tags": ["precise-location"]},
        )
        serialized = json.dumps(result)
        for forbidden in (
            "Exact unit location",
            "secret",
            "guessing-oracle",
            "original_text_chars",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(
            result["raw"]["archive_policy"], "public_redacted_v1"
        )
        self.assertEqual(
            result["raw"]["platform"], {"post": "source/1"}
        )

    def test_run_collection_uses_final_redaction_hardening(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        settings = {
            "poll_seconds": 900,
            "workers": 1,
            "request_timeout_seconds": 5,
            "user_agent": "test",
            "raw_root": "data/raw",
            "error_root": "data/errors",
            "state_file": "data/state.json",
            "default_lookback_hours": 24,
            "platform_cadence_minutes": {"web": 60},
            "collection_delay_hours": 0,
            "collection_delay_by_group": {},
            "collection_delay_by_tag": {},
            "collection_delay_by_source": {},
            "public_excerpt_chars": 100,
            "public_media_limit": 2,
            "public_redact_tags": ["precise-location"],
            "x_search_queries": [],
        }
        source = {
            "id": "source-web",
            "name": "Source",
            "platform": "web",
            "url": "https://example.com/news",
            "group": "media",
            "perspective": "mixed",
            "trust": "high",
            "priority": 10,
            "enabled": True,
        }
        (root / "config/settings.json").write_text(json.dumps(settings))
        (root / "config/sources.json").write_text(
            json.dumps({"sources": [source]})
        )
        item = {
            "id": "item-1",
            "source": "source-web",
            "source_name": "Source",
            "platform": "web",
            "url": "https://example.com/story",
            "published_at": "2026-08-01T00:00:00Z",
            "collected_at": "2026-08-06T00:00:00Z",
            "title": "Exact unit location",
            "text": "secret",
            "html": "<p>secret</p>",
            "media": [],
            "author": "",
            "language": "en",
            "group": "media",
            "perspective": "mixed",
            "trust": "high",
            "tags": ["precise-location"],
            "raw": {"content_type": "text/html", "secret": "payload"},
        }
        with patch("scripts.collect.collect_one", return_value=[item]):
            state = run_collection(root, force=True)
        self.assertEqual(state["status"], "ok")
        raw_file = next((root / "data/raw").rglob("items.ndjson"))
        stored = json.loads(raw_file.read_text().strip())
        serialized = json.dumps(stored)
        self.assertNotIn("Exact unit location", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("content_sha256", serialized)
        self.assertEqual(
            stored["raw"]["archive_policy"], "public_redacted_v1"
        )

    def test_report_html_sanitizer_removes_active_content(self) -> None:
        rendered = sanitize_report_html(
            "<h2 onclick='x()'>Title</h2>"
            "<script>alert(1)</script>"
            "<a href='javascript:alert(2)' style='x'>bad</a>"
            "<a href='https://example.com/path'>good</a>"
            "<img src='https://tracker.example/pixel'>"
        )
        self.assertNotIn("script", rendered)
        self.assertNotIn("alert", rendered)
        self.assertNotIn("onclick", rendered)
        self.assertNotIn("style", rendered)
        self.assertNotIn("img", rendered)
        self.assertIn('href="https://example.com/path"', rendered)
        self.assertIn('rel="noopener noreferrer"', rendered)

    def test_page_has_hash_csp_and_no_referrer(self) -> None:
        rendered = page("x", "<p>body</p>", prefix="")
        self.assertIn("Content-Security-Policy", rendered)
        self.assertIn("script-src 'sha256-", rendered)
        self.assertIn(
            "name='referrer' content='no-referrer'", rendered
        )
        self.assertNotIn("script-src 'unsafe-inline'", rendered)

    def test_public_href_rejects_credentials_and_controls(self) -> None:
        self.assertIsNone(
            public_href("https://user:pass@example.com/path")
        )
        self.assertIsNone(public_href("https://example.com/\npath"))
        self.assertEqual(
            public_href("https://example.com/a?b=1"),
            "https://example.com/a?b=1",
        )

    def test_validator_rejects_unsafe_paths_and_source_contract(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        settings = {
            "poll_seconds": 1,
            "workers": 1,
            "request_timeout_seconds": 1,
            "default_lookback_hours": 1,
            "telegram_max_pages": 1,
            "x_max_pages": 1,
            "web_max_links": 1,
            "public_excerpt_chars": 1,
            "public_media_limit": 1,
            "collection_delay_hours": 0,
            "site_publication_delay_hours": 0,
            "site_sensitive_delay_hours": 0,
            "collection_delay_by_group": {},
            "collection_delay_by_tag": {},
            "collection_delay_by_source": {},
            "raw_root": "../outside",
            "error_root": "data/errors",
            "state_file": "data/state.json",
            "report_root": "reports/daily",
            "site_root": "site",
            "report_timezone": "UTC",
            "sensitive_tags": ["precise-location"],
            "public_redact_tags": ["precise-location"],
            "x_search_queries": [],
            "platform_cadence_minutes": {"web": 60},
            "minimum_group_counts": {},
        }
        source = {
            "id": "wrong-rss",
            "name": "Wrong",
            "platform": "web",
            "url": "http://user:pass@example.com/news",
            "group": "media",
            "perspective": "mixed",
            "trust": "high",
            "priority": 10,
            "enabled": True,
        }
        (root / "config/settings.json").write_text(json.dumps(settings))
        (root / "config/sources.json").write_text(
            json.dumps({"sources": [source]})
        )
        joined = "\n".join(validate(root))
        self.assertIn("safe repository-relative path", joined)
        self.assertIn("invalid URL", joined)
        self.assertIn("id suffix expects platform rss", joined)

    def test_build_site_sanitizes_manual_report_html(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        (root / "reports/daily").mkdir(parents=True)
        (root / "data/raw").mkdir(parents=True)
        settings = {
            "site_root": "site",
            "report_root": "reports/daily",
            "raw_root": "data/raw",
            "site_publication_delay_hours": 0,
            "site_sensitive_delay_hours": 0,
            "sensitive_tags": [],
            "public_redact_tags": [],
        }
        (root / "config/settings.json").write_text(json.dumps(settings))
        (root / "reports/daily/2026-08-06.md").write_text(
            "# Safe\n\n<script>alert('x')</script>\n\n"
            "[bad](javascript:alert(1))"
        )
        site = build_site(root)
        text = (site / "reports/2026-08-06.html").read_text()
        self.assertNotIn("<script", text.lower())
        self.assertNotIn('href="javascript:', text.lower())
        self.assertIn("Content-Security-Policy", text)


if __name__ == "__main__":
    unittest.main()
