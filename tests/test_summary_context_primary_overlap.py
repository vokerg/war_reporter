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
    trust: str = "primary",
    minute: int = 0,
) -> dict:
    return {
        "id": item_id,
        "source": item_id,
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


class SummaryContextPrimaryOverlapTests(unittest.TestCase):
    def test_weaker_nested_multilocation_cluster_does_not_consume_second_primary_slot(self) -> None:
        rows = [
            row(
                "kyiv-official",
                "Kyiv City Military Administration",
                "official-ua",
                "ukrainian",
                "Після масованої ракетно-дронової атаки у Києві пошкоджено будинки.",
            ),
            row(
                "kyiv-media",
                "Reuters",
                "international-media",
                "mixed",
                "Russian missile and drone attack damaged homes in Kyiv Ukraine.",
                platform="rss",
                trust="high",
                minute=1,
            ),
            row(
                "kyiv-ru",
                "Rybar",
                "ru-milbloggers",
                "russian",
                "Массированный удар ракетами и БПЛА по Киеву на Украине.",
                trust="low",
                minute=2,
            ),
            row(
                "kyiv-ua",
                "Ukrainian outlet",
                "ua-media-bloggers",
                "ukrainian",
                "У Києві після атаки БпЛА зафіксовано пошкодження в Україні.",
                trust="medium",
                minute=3,
            ),
            row(
                "nested",
                "Regional digest",
                "international-media",
                "mixed",
                (
                    "Russian drone attack hit Kyiv Ukraine; officials discussing the aftermath "
                    "had arrived from Odesa earlier in the day."
                ),
                platform="rss",
                trust="high",
                minute=4,
            ),
        ]

        context = render_summary_context("2026-08-05", rows, {}, max_primary=5)
        primary = context.split("### Telegram pulse watchlist", 1)[0]

        self.assertIn("Дальние и воздушные удары — Киев/область", primary)
        self.assertNotIn("Дальние и воздушные удары — Киев/область, Одесса/область", primary)
        self.assertEqual(primary.count("#### "), 1)

    def test_comparably_supported_multiregion_event_is_preserved(self) -> None:
        rows = [
            row(
                "local-a",
                "Kyiv City Military Administration",
                "official-ua",
                "ukrainian",
                "Після атаки БпЛА у Києві пошкоджено будинки.",
            ),
            row(
                "local-b",
                "Kyiv outlet",
                "ua-media-bloggers",
                "ukrainian",
                "У Києві після російської атаки є пошкодження в Україні.",
                trust="medium",
                minute=1,
            ),
            row(
                "multi-a",
                "Reuters",
                "international-media",
                "mixed",
                "Russian missile and drone attacks damaged infrastructure in Kyiv and Odesa Ukraine.",
                platform="rss",
                trust="high",
                minute=2,
            ),
            row(
                "multi-b",
                "National official",
                "official-ua",
                "ukrainian",
                "Ракетно-дронова атака спричинила пошкодження у Києві та Одесі в Україні.",
                minute=3,
            ),
            row(
                "multi-c",
                "Milblogger",
                "ru-milbloggers",
                "russian",
                "Массированные удары ракетами и БПЛА по Киеву и Одессе на Украине.",
                trust="low",
                minute=4,
            ),
        ]

        context = render_summary_context("2026-08-05", rows, {}, max_primary=5)
        primary = context.split("### Telegram pulse watchlist", 1)[0]

        self.assertIn("Дальние и воздушные удары — Киев/область, Одесса/область", primary)
        self.assertIn("Дальние и воздушные удары — Киев/область", primary)
        self.assertEqual(primary.count("#### "), 2)


if __name__ == "__main__":
    unittest.main()
