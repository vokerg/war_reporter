from __future__ import annotations

import unittest

from scripts.summary_context import EventCluster, evidence_score, prepare_item, telegram_pulse
from scripts.summary_context_render import render_summary_context


def make_item(
    item_id: str,
    source: str,
    group: str,
    perspective: str,
    text: str,
    *,
    platform: str = "telegram",
    trust: str = "low",
    published_at: str = "2026-08-09T10:00:00Z",
    archive_policy: str = "public_excerpt_v1",
) -> dict:
    return {
        "id": item_id,
        "source": source,
        "source_name": source,
        "group": group,
        "perspective": perspective,
        "platform": platform,
        "trust": trust,
        "published_at": published_at,
        "collected_at": published_at,
        "title": "",
        "text": text if archive_policy == "public_excerpt_v1" else "",
        "url": f"https://example.com/{item_id}",
        "tags": [],
        "raw": {"archive_policy": archive_policy},
    }


def make_cluster(rows: list[dict], topic: str = "strikes") -> EventCluster:
    cluster = EventCluster(topic=topic)
    for row in rows:
        cluster.add(prepare_item(row))
    return cluster


class SummaryContextTests(unittest.TestCase):
    def test_milblogger_group_does_not_make_off_topic_post_relevant(self) -> None:
        row = make_item(
            "fires",
            "Boris Rozhin",
            "ru-milbloggers",
            "russian",
            "Лесные пожары во Франции уничтожили тысячи гектаров.",
        )
        self.assertEqual(prepare_item(row).relevance, "irrelevant")

    def test_cross_language_publications_form_one_production_cluster(self) -> None:
        rows = [
            make_item(
                "ua",
                "Odesa Oblast Administration",
                "official-ua",
                "ukrainian",
                "На Одещині 14 постраждалих внаслідок масованої ракетно-дронової атаки.",
                trust="primary",
            ),
            make_item(
                "media",
                "Reuters",
                "international-media",
                "mixed",
                "Russian missile and drone attack on Odesa region wounded 14 people.",
                platform="rss",
                trust="high",
            ),
            make_item(
                "ru",
                "Rybar",
                "ru-milbloggers",
                "russian",
                "Массированный удар ракетами и БПЛА по Одесской области и портам.",
            ),
        ]
        context = render_summary_context("2026-08-09", rows, {})
        self.assertIn("Situation clusters: **1**", context)
        self.assertIn("Публикаций в cluster: **3**", context)
        self.assertIn("Одесса/область", context)

    def test_osint_strength_and_telegram_pulse_are_separate_axes(self) -> None:
        rows = [
            make_item(
                "osint",
                "GeoConfirmed",
                "osint",
                "mixed",
                "Geolocated drone strike damage in Odesa Ukraine.",
                platform="x",
                trust="high",
            ),
            make_item(
                "ua",
                "Odesa Oblast Administration",
                "official-ua",
                "ukrainian",
                "На Одещині наслідки атаки БПЛА.",
                trust="primary",
            ),
            make_item(
                "ru",
                "Rybar",
                "ru-milbloggers",
                "russian",
                "Удар БПЛА по Одесской области.",
            ),
        ]
        cluster = make_cluster(rows)
        evidence_value, evidence_label, groups = evidence_score(cluster)
        pulse_value, pulse_label, families, posts, _ = telegram_pulse(cluster)
        self.assertIn("osint", groups)
        self.assertGreaterEqual(evidence_value, 5.0)
        self.assertIn(evidence_label, {"mixed", "strong"})
        self.assertEqual(families, 2)
        self.assertEqual(posts, 2)
        self.assertLess(pulse_value, 6.0)
        self.assertIn(pulse_label, {"low", "medium"})

    def test_repeated_posts_from_one_channel_do_not_create_high_pulse(self) -> None:
        rows = [
            make_item(
                f"same-{index}",
                "Rybar",
                "ru-milbloggers",
                "russian",
                "Удар БПЛА по Одесской области.",
                published_at=f"2026-08-09T10:{index:02d}:00Z",
            )
            for index in range(12)
        ]
        pulse_value, pulse_label, families, posts, _ = telegram_pulse(
            make_cluster(rows)
        )
        self.assertEqual(families, 1)
        self.assertEqual(posts, 12)
        self.assertLess(pulse_value, 3.0)
        self.assertEqual(pulse_label, "low")

    def test_multichannel_cross_perspective_pulse_surfaces(self) -> None:
        rows = [
            make_item(
                f"channel-{index}",
                f"Channel {index}",
                "ru-milbloggers" if index < 3 else "official-ua",
                "russian" if index < 3 else "ukrainian",
                "Удар БПЛА по Одесской области.",
                published_at=f"2026-08-09T10:{index:02d}:00Z",
            )
            for index in range(6)
        ]
        pulse_value, pulse_label, families, _, perspectives = telegram_pulse(
            make_cluster(rows)
        )
        self.assertEqual(families, 6)
        self.assertEqual(perspectives, 2)
        self.assertGreaterEqual(pulse_value, 6.0)
        self.assertEqual(pulse_label, "high")

    def test_redacted_content_never_enters_production_context(self) -> None:
        rows = [
            make_item(
                "redacted",
                "Sensitive source",
                "osint",
                "mixed",
                "SECRET PRECISE POSITION",
                archive_policy="public_redacted_v1",
            ),
            make_item(
                "visible",
                "Reuters",
                "international-media",
                "mixed",
                "Russian drone strike in Odesa Ukraine.",
                platform="rss",
                trust="high",
            ),
        ]
        context = render_summary_context("2026-08-09", rows, {})
        self.assertIn(
            "Redacted записей, не использованных для синтеза: **1**",
            context,
        )
        self.assertNotIn("SECRET PRECISE POSITION", context)

    def test_context_exposes_change_evidence_and_pulse_contract(self) -> None:
        rows = [
            make_item(
                "osint",
                "GeoConfirmed",
                "osint",
                "mixed",
                "Geolocated Russian drone strike in Odesa Ukraine.",
                platform="x",
                trust="high",
            ),
            make_item(
                "ua",
                "Odesa Oblast Administration",
                "official-ua",
                "ukrainian",
                "На Одещині наслідки масованої атаки БПЛА.",
                trust="primary",
            ),
            make_item(
                "ru",
                "Rybar",
                "ru-milbloggers",
                "russian",
                "Массированный удар БПЛА по Одесской области.",
            ),
            make_item(
                "noise",
                "Rybar",
                "ru-milbloggers",
                "russian",
                "Пожары в Испании и Франции.",
            ),
        ]
        context = render_summary_context("2026-08-09", rows, {})
        self.assertIn("Контекст для редакционного синтеза", context)
        self.assertIn("Evidence mix", context)
        self.assertIn("Telegram pulse", context)
        self.assertIn("7-day delta", context)
        self.assertIn("Отфильтровано как off-topic первым gate: **1**", context)
        self.assertIn("GeoConfirmed", context)


if __name__ == "__main__":
    unittest.main()
