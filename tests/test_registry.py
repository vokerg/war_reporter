from __future__ import annotations

import json
import unittest
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


class SourceRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(
            (ROOT / "config/sources.json").read_text(encoding="utf-8")
        )
        cls.sources = cls.registry["sources"]
        cls.by_id = {row["id"]: row for row in cls.sources}

    def test_registry_has_146_unique_configured_sources(self) -> None:
        self.assertEqual(len(self.sources), 146)
        self.assertEqual(len(self.by_id), len(self.sources))

    def test_explicit_platform_suffix_matches_platform(self) -> None:
        suffixes = {
            "-tg": "telegram",
            "-x": "x",
            "-rss": "rss",
            "-web": "web",
        }
        for source in self.sources:
            for suffix, platform in suffixes.items():
                if source["id"].endswith(suffix):
                    self.assertEqual(
                        source["platform"],
                        platform,
                        source["id"],
                    )
                    break

    def test_registry_urls_have_no_credentials_and_use_https(self) -> None:
        for source in self.sources:
            parsed = urlparse(source["url"])
            self.assertEqual(parsed.scheme, "https", source["id"])
            self.assertIsNone(parsed.username, source["id"])
            self.assertIsNone(parsed.password, source["id"])

    def test_corrected_high_priority_sources_are_explicit(self) -> None:
        expected = {
            "ua-president-web": (
                "web",
                "https://www.president.gov.ua/en/news/all",
            ),
            "cit-web": ("web", "https://notes.citeam.org/"),
            "reuters-web": ("web", "https://www.reuters.com/world/"),
            "ap-web": ("web", "https://apnews.com/hub/world-news"),
            "ru-kremlin-web": (
                "web",
                "https://en.kremlin.ru/events/president/news",
            ),
        }
        for source_id, (platform, url) in expected.items():
            row = self.by_id[source_id]
            self.assertEqual(row["platform"], platform)
            self.assertEqual(row["url"], url)

        for obsolete in ("cit-rss", "reuters-rss", "ap-rss"):
            self.assertNotIn(obsolete, self.by_id)


if __name__ == "__main__":
    unittest.main()
