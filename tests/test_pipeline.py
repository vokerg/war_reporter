from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from scripts.build_report import (
    build_report,
    item_day,
    local_today,
    report_timezone,
)
from scripts.build_site import build_site, publication_mode, render_item
from scripts.collect import (
    _x_pages,
    discover_article_urls,
    ensure_public_url,
    extract_publication_time,
    item_is_storable,
    item_storage_delay_hours,
    item_storage_state,
    make_item,
    public_projection,
    run_collection,
    source_is_due,
)
from scripts.common import append_unique
from scripts.continuous_loop import run_loop
from scripts.validate import validate


class ReviewedPipelineTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config").mkdir()
        settings = {
            "poll_seconds": 900,
            "workers": 4,
            "request_timeout_seconds": 5,
            "user_agent": "test",
            "report_timezone": "Europe/Kyiv",
            "raw_root": "data/raw",
            "error_root": "data/errors",
            "state_file": "data/state.json",
            "report_root": "reports/daily",
            "site_root": "site",
            "default_lookback_hours": 48,
            "telegram_max_pages": 2,
            "x_max_pages": 2,
            "web_max_links": 4,
            "public_excerpt_chars": 32,
            "public_media_limit": 2,
            "platform_cadence_minutes": {
                "telegram": 15,
                "x": 15,
                "rss": 60,
                "web": 1440,
            },
            "collection_delay_hours": 0,
            "site_publication_delay_hours": 24,
            "site_sensitive_delay_hours": 72,
            "sensitive_tags": [
                "frontline", "map", "maps", "operational-position",
                "precise-location",
            ],
            "public_redact_tags": ["operational-position", "precise-location"],
            "collection_delay_by_group": {"ru-milbloggers": 72},
            "collection_delay_by_tag": {"frontline": 72, "map": 72, "maps": 72},
            "collection_delay_by_source": {},
            "minimum_group_counts": {},
            "x_search_queries": [],
        }
        source = {
            "id": "source-a",
            "name": "Source A",
            "platform": "telegram",
            "url": "https://t.me/source_a",
            "group": "osint",
            "perspective": "mixed",
            "trust": "high",
            "priority": 80,
            "languages": ["en"],
            "tags": ["frontline", "map"],
            "enabled": True,
        }
        (root / "config/settings.json").write_text(
            json.dumps(settings), encoding="utf-8"
        )
        (root / "config/sources.json").write_text(
            json.dumps({"version": 1, "sources": [source]}),
            encoding="utf-8",
        )
        return root

    def item(
        self,
        *,
        published_at: str = "2026-08-05T21:30:00Z",
        collected_at: str = "2026-08-06T12:00:00Z",
        tags: list[str] | None = None,
    ) -> dict:
        return {
            "id": "abc",
            "source": "source-a",
            "source_name": "Source A",
            "platform": "telegram",
            "url": "https://t.me/source_a/1",
            "published_at": published_at,
            "collected_at": collected_at,
            "title": "Operational map",
            "text": "precise operational detail that must not leak",
            "html": "<p>precise operational detail</p>",
            "media": ["https://example.com/map.jpg"],
            "author": "Source A",
            "language": "en",
            "group": "osint",
            "perspective": "mixed",
            "trust": "high",
            "tags": tags if tags is not None else ["frontline", "map"],
            "raw": {"post": "source_a/1"},
        }

    def test_private_network_urls_are_rejected(self) -> None:
        with self.assertRaises(Exception):
            ensure_public_url("http://127.0.0.1/private")
        with self.assertRaises(Exception):
            ensure_public_url("http://169.254.169.254/latest/meta-data")

    def test_x_endpoint_specific_pagination_parameter(self) -> None:
        calls: list[dict] = []
        payloads = [
            {"data": [{"id": "1"}], "meta": {"next_token": "NEXT"}},
            {"data": [{"id": "2"}], "meta": {}},
        ]

        def fake_get(_session, _endpoint, params):
            calls.append(dict(params))
            return payloads[len(calls) - 1]

        with patch("scripts.collect.x_api_get", side_effect=fake_get):
            rows = _x_pages(object(), "endpoint", {"query": "q"}, 5, token_param="next_token")
        self.assertEqual([row["id"] for row in rows], ["1", "2"])
        self.assertNotIn("next_token", calls[0])
        self.assertEqual(calls[1]["next_token"], "NEXT")

    def test_x_ids_converge_across_discovery_and_account_source(self) -> None:
        base = {
            "name": "A", "platform": "x", "group": "osint",
            "perspective": "mixed", "trust": "high", "tags": [],
        }
        one = make_item({**base, "id": "account"}, url="https://x.com/a/status/1", published_at="2026-08-05T00:00:00Z", text="same")
        two = make_item({**base, "id": "discovery"}, url="https://x.com/a/status/1", published_at="2026-08-05T00:00:00Z", text="same")
        self.assertEqual(one["id"], two["id"])

    def test_non_x_ids_retain_source_identity(self) -> None:
        base = {
            "name": "A",
            "platform": "rss",
            "group": "media",
            "perspective": "mixed",
            "trust": "high",
            "tags": [],
        }
        one = make_item({**base, "id": "one"}, url="https://x.test/a", published_at=None, text="same")
        two = make_item({**base, "id": "two"}, url="https://x.test/a", published_at=None, text="same")
        self.assertNotEqual(one["id"], two["id"])

    def test_raw_payload_is_json_serializable(self) -> None:
        item = make_item(
            {
                "id": "a", "name": "A", "platform": "rss", "group": "g",
                "perspective": "mixed", "trust": "high", "tags": [],
            },
            url="https://example.com/a", published_at=None, text="x",
            raw={"parsed": datetime(2026, 8, 5, tzinfo=UTC)},
        )
        json.dumps(item)
        self.assertIsInstance(item["raw"]["parsed"], str)

    def test_kyiv_calendar_boundary(self) -> None:
        root = self.make_root()
        settings = json.loads((root / "config/settings.json").read_text())
        tz = report_timezone(settings)
        self.assertEqual(item_day(self.item(), tz), "2026-08-06")
        self.assertEqual(
            local_today(settings, datetime(2026, 8, 5, 22, 30, tzinfo=UTC)).isoformat(),
            "2026-08-06",
        )

    def test_report_is_honest_and_sensitive_excerpt_is_redacted(self) -> None:
        root = self.make_root()
        path = root / "data/raw/2026/08/05/items.ndjson"
        append_unique(path, [self.item(tags=["precise-location"])])
        _, report = build_report(root, "2026-08-06")
        self.assertIn("не проверенная аналитическая оценка", report)
        self.assertIn("Подробный фрагмент не включён", report)
        self.assertNotIn("precise operational detail", report)

    def test_site_uses_relative_links_and_hidden_text_does_not_leak(self) -> None:
        root = self.make_root()
        path = root / "data/raw/2026/08/05/items.ndjson"
        append_unique(path, [self.item(tags=["precise-location"])])
        build_report(root, "2026-08-06")
        site = build_site(root)
        index = (site / "index.html").read_text()
        raw = (site / "raw/2026-08-05.html").read_text()
        report = (site / "reports/2026-08-06.html").read_text()
        self.assertIn("href='raw/index.html'", index)
        self.assertNotIn("href='/raw/", index)
        self.assertIn("<h1>", report)
        self.assertNotIn("precise operational detail", raw)

    def test_publication_delay_is_based_on_collection_time(self) -> None:
        root = self.make_root()
        settings = json.loads((root / "config/settings.json").read_text())
        old_publication = self.item(
            published_at="2020-01-01T00:00:00Z",
            collected_at="2026-08-06T12:00:00Z",
            tags=[],
        )
        now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
        self.assertEqual(publication_mode(old_publication, settings, now), "delayed")
        card = render_item(old_publication, settings, now)
        self.assertNotIn("precise operational detail", card)

    def test_sensitive_items_are_not_stored_before_delay(self) -> None:
        root = self.make_root()
        settings = json.loads((root / "config/settings.json").read_text())
        now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
        recent = self.item(
            published_at="2026-08-06T11:00:00Z",
            collected_at="2026-08-06T12:00:00Z",
            tags=["frontline"],
        )
        old = self.item(
            published_at="2026-08-03T11:00:00Z",
            collected_at="2026-08-06T12:00:00Z",
            tags=["frontline"],
        )
        undated = self.item(
            published_at=None,
            collected_at="2026-08-01T12:00:00Z",
            tags=["frontline"],
        )
        self.assertEqual(item_storage_delay_hours(recent, settings), 72)
        self.assertFalse(item_is_storable(recent, settings, now))
        self.assertTrue(item_is_storable(old, settings, now))
        self.assertFalse(item_is_storable(undated, settings, now))

    def test_cadence_skip(self) -> None:
        root = self.make_root()
        settings = json.loads((root / "config/settings.json").read_text())
        source = json.loads((root / "config/sources.json").read_text())["sources"][0]
        now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
        due, next_due = source_is_due(
            source,
            {"last_success_at": "2026-08-06T11:55:00Z"},
            settings,
            now,
            force=False,
        )
        self.assertFalse(due)
        self.assertEqual(next_due, "2026-08-06T12:10:00Z")

    def test_missing_x_token_is_visible_without_error_spam(self) -> None:
        root = self.make_root()
        registry = json.loads((root / "config/sources.json").read_text())
        registry["sources"] = [{
            **registry["sources"][0],
            "id": "x-a", "platform": "x", "url": "https://x.com/account",
        }]
        (root / "config/sources.json").write_text(json.dumps(registry))
        with patch.dict(os.environ, {}, clear=True):
            state = run_collection(root, force=True)
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(state["errors"], 0)
        self.assertEqual(state["configuration_errors"], ["X_BEARER_TOKEN is not configured"])
        self.assertFalse((root / "data/errors").exists())

    def test_once_returns_failure_for_partial_or_failed_collection(self) -> None:
        root = self.make_root()
        partial = {
            "status": "partial", "sources_attempted": 1, "sources_succeeded": 1,
            "items_added": 0, "errors": 0, "sources_skipped": 1,
        }
        with patch("scripts.continuous_loop.run_collection", return_value=partial), \
             patch("scripts.continuous_loop.build_report"), \
             patch("scripts.continuous_loop.build_site"):
            self.assertEqual(run_loop(root, once=True), 1)

    def test_public_projection_strips_full_capture(self) -> None:
        root = self.make_root()
        settings = json.loads((root / "config/settings.json").read_text())
        item = self.item(tags=[])
        item["text"] = "x" * 100
        item["html"] = "<article>secret full html</article>"
        item["raw"] = {"post": "source_a/1", "secret": "full payload"}
        projected = public_projection(item, settings)
        self.assertEqual(projected["text"], "x" * 32)
        self.assertEqual(projected["html"], "")
        self.assertNotIn("secret", json.dumps(projected))
        self.assertEqual(projected["raw"]["archive_policy"], "public_excerpt_v1")
        self.assertTrue(projected["raw"]["text_truncated"])

    def test_undated_delayed_item_is_visible_as_policy_withheld(self) -> None:
        root = self.make_root()
        settings = json.loads((root / "config/settings.json").read_text())
        item = self.item(published_at=None, tags=["frontline"])
        now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
        self.assertEqual(
            item_storage_state(item, settings, now),
            "withheld_undated",
        )
        self.assertFalse(item_is_storable(item, settings, now))

    def test_article_discovery_is_bounded_and_same_host(self) -> None:
        html = """
        <main>
          <article><h2><a href='/news/2026/08/story-one'>A sufficiently long article title one</a></h2></article>
          <article><h2><a href='https://example.com/analysis/story-two'>A sufficiently long article title two</a></h2></article>
          <a href='https://evil.example/news/story'>External story must be ignored</a>
          <a href='/tags/war'>Tag listing must be ignored</a>
        </main>
        """
        urls = discover_article_urls(
            "https://example.com/news", html, limit=1
        )
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].startswith("https://example.com/"))

    def test_publication_time_from_metadata(self) -> None:
        soup = BeautifulSoup(
            "<meta property='article:published_time' content='2026-08-05T12:30:00Z'>",
            "html.parser",
        )
        self.assertEqual(
            extract_publication_time(soup),
            "2026-08-05T12:30:00Z",
        )

    def test_source_filter_rejects_unknown_ids(self) -> None:
        root = self.make_root()
        with self.assertRaisesRegex(ValueError, "unknown source ids"):
            run_collection(root, source_ids={"missing"}, force=True)

    def test_report_index_does_not_duplicate_days(self) -> None:
        root = self.make_root()
        path = root / "data/raw/2026/08/05/items.ndjson"
        append_unique(path, [self.item(tags=[])])
        build_report(root, "2026-08-06")
        site = build_site(root)
        index = (site / "index.html").read_text()
        self.assertEqual(index.count("reports/2026-08-06.html"), 1)

    def test_run_collection_persists_only_public_projection(self) -> None:
        root = self.make_root()
        item = self.item(tags=[])
        item["text"] = "source body " * 20
        item["html"] = "<article>full captured html</article>"
        item["raw"] = {"post": "source_a/1", "private_field": "do not persist"}
        with patch("scripts.collect.collect_one", return_value=[item]):
            state = run_collection(root, force=True)
        self.assertEqual(state["status"], "ok")
        rows = [
            json.loads(line)
            for line in (root / "data/raw/2026/08/05/items.ndjson")
            .read_text()
            .splitlines()
        ]
        self.assertEqual(len(rows), 1)
        stored = rows[0]
        self.assertEqual(stored["html"], "")
        self.assertNotIn("private_field", json.dumps(stored))
        self.assertLessEqual(len(stored["text"]), 32)

    def test_general_embargo_does_not_permanently_redact_digest(self) -> None:
        root = self.make_root()
        settings_path = root / "config/settings.json"
        settings = json.loads(settings_path.read_text())
        settings["collection_delay_by_group"] = {"official-ua": 24}
        settings_path.write_text(json.dumps(settings))
        item = self.item(tags=[])
        item["group"] = "official-ua"
        item["title"] = ""
        item["text"] = "safe delayed official excerpt"
        append_unique(root / "data/raw/2026/08/05/items.ndjson", [item])
        _, report = build_report(root, "2026-08-06")
        self.assertIn("safe delayed official excerpt", report)

    def test_site_links_media_instead_of_embedding_it(self) -> None:
        root = self.make_root()
        settings_path = root / "config/settings.json"
        settings = json.loads(settings_path.read_text())
        settings["site_publication_delay_hours"] = 0
        settings["site_sensitive_delay_hours"] = 0
        settings_path.write_text(json.dumps(settings))
        item = self.item(tags=[])
        append_unique(root / "data/raw/2026/08/05/items.ndjson", [item])
        site = build_site(root)
        raw = (site / "raw/2026-08-05.html").read_text()
        self.assertIn("Медиа из источника", raw)
        self.assertNotIn("<img", raw)

    def test_validator_accepts_reviewed_minimal_configuration(self) -> None:
        root = self.make_root()
        self.assertEqual(validate(root), [])

    def test_validator_catches_unknown_source(self) -> None:
        root = self.make_root()
        item = self.item()
        item["source"] = "missing"
        append_unique(root / "data/raw/2026/08/05/items.ndjson", [item])
        self.assertTrue(any("unknown source" in error for error in validate(root)))


if __name__ == "__main__":
    unittest.main()
