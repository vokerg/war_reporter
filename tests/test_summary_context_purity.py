from __future__ import annotations

import unittest

from scripts.summary_context_render import render_summary_context


def row(
    item_id: str,
    source: str,
    group: str,
    perspective: str,
    text: str,
    *,
    platform: str = "telegram",
    trust: str = "low",
    minute: int = 0,
) -> dict:
    return {
        "id": item_id,
        "source": source,
        "source_name": source,
        "group": group,
        "perspective": perspective,
        "platform": platform,
        "trust": trust,
        "published_at": f"2026-08-05T10:{minute:02d}:00Z",
        "collected_at": f"2026-08-05T10:{minute:02d}:30Z",
        "title": "",
        "text": text,
        "url": f"https://example.com/{item_id}",
        "tags": [],
        "raw": {"archive_policy": "public_excerpt_v1"},
    }


class SummaryContextPurityTests(unittest.TestCase):
    def test_multi_location_roundup_cannot_bridge_single_location_cluster(self) -> None:
        rows = [
            row(
                "kyiv-official",
                "Kyiv City Military Administration",
                "official-ua",
                "ukrainian",
                "У Києві після російської атаки пошкоджено будинки, є постраждалі.",
                trust="primary",
            ),
            row(
                "kyiv-media",
                "Reuters",
                "international-media",
                "mixed",
                "Russian drone attack in Kyiv Ukraine damaged homes and wounded residents.",
                platform="rss",
                trust="high",
                minute=1,
            ),
            row(
                "roundup",
                "Daily Roundup",
                "international-media",
                "mixed",
                "Ukraine roundup: drone attacks reported in Kyiv, Kherson, Odesa, Kharkiv and Sumy; Russia also reported attacks elsewhere.",
                platform="rss",
                trust="high",
                minute=2,
            ),
        ]

        context = render_summary_context("2026-08-05", rows, {}, max_primary=5)
        sections = context.split("#### ")
        kyiv_sections = [part for part in sections if "Киев/область" in part]

        self.assertTrue(kyiv_sections)
        single_kyiv = next(part for part in kyiv_sections if "Reuters" in part)
        self.assertNotIn("Daily Roundup", single_kyiv)
        self.assertIn("Публикаций в cluster: **2**", single_kyiv)

    def test_unrelated_no_location_item_does_not_join_location_event(self) -> None:
        rows = [
            row(
                "kyiv",
                "Kyiv City Military Administration",
                "official-ua",
                "ukrainian",
                "У Києві після атаки БпЛА пошкоджено житловий будинок.",
                trust="primary",
            ),
            row(
                "generic",
                "Political Feed",
                "international-media",
                "mixed",
                "Ukraine and Russia remain at war while parliament discusses a domestic election procedure.",
                platform="rss",
                trust="high",
                minute=1,
            ),
        ]

        context = render_summary_context("2026-08-05", rows, {}, max_primary=5)
        kyiv_section = next(
            part for part in context.split("#### ") if "Киев/область" in part
        )
        self.assertNotIn("Political Feed", kyiv_section)


if __name__ == "__main__":
    unittest.main()
