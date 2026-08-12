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
    url: str | None = None,
    day: str = "2026-08-05",
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
        "published_at": f"{day}T10:{minute:02d}:00Z",
        "collected_at": f"{day}T10:{minute:02d}:30Z",
        "title": "",
        "text": text,
        "url": url or f"https://example.com/{item_id}",
        "tags": [],
        "raw": {"archive_policy": "public_excerpt_v1"},
    }


class SummaryContextSelfReviewTests(unittest.TestCase):
    def test_legal_sanction_and_inkryminovana_do_not_create_support_crimea_event(self) -> None:
        police = row(
            "police",
            "National Police of Ukraine",
            "official-ua",
            "ukrainian",
            (
                "Столичні поліцейські викрили корупційну схему. "
                "Санкція інкримінованої статті передбачає до 12 років ув’язнення."
            ),
        )
        context = render_summary_context("2026-08-05", [police], {})
        self.assertIn("Accepted публикаций после strict gate: **0**", context)
        self.assertNotIn("Военная помощь и дипломатия", context)
        self.assertNotIn("Крым", context)

    def test_russian_legal_authorization_is_not_geopolitical_sanctions(self) -> None:
        legal = row(
            "legal",
            "Wire Service",
            "international-media",
            "mixed",
            "Суд санкционировал обыск по делу, связанному с гражданином Украины.",
            platform="rss",
            trust="high",
        )
        context = render_summary_context("2026-08-05", [legal], {})
        self.assertIn("Accepted публикаций после strict gate: **0**", context)
        self.assertNotIn("Военная помощь и дипломатия", context)

    def test_strike_and_casualty_reporting_share_one_event_cluster(self) -> None:
        rows = [
            row(
                "impact",
                "Kyiv City Military Administration",
                "official-ua",
                "ukrainian",
                "Після масованої ракетно-дронової атаки у Києві 16 поранених, пошкоджено будинки.",
            ),
            row(
                "media",
                "Reuters",
                "international-media",
                "mixed",
                "Russian missile and drone attack damaged homes in Kyiv Ukraine.",
                platform="rss",
                trust="high",
                minute=1,
            ),
        ]
        context = render_summary_context("2026-08-05", rows, {})
        self.assertIn("Situation clusters: **1**", context)
        self.assertIn("Публикаций в cluster: **2**", context)
        self.assertEqual(context.count("#### "), 1)
        self.assertIn("Дальние и воздушные удары — Киев/область", context)

    def test_newer_location_patterns_participate_in_temporal_matching(self) -> None:
        historical = row(
            "old",
            "Chernihiv Oblast Administration",
            "official-ua",
            "ukrainian",
            "У Чернігові після атаки БпЛА пошкоджено склад.",
            day="2026-08-04",
        )
        current = row(
            "current",
            "Chernihiv Oblast Administration",
            "official-ua",
            "ukrainian",
            "У Чернігові після атаки БпЛА пошкоджено склад.",
        )
        context = render_summary_context(
            "2026-08-05",
            [current],
            {"2026-08-04": [historical]},
        )
        self.assertIn("Чернигов/область", context)
        self.assertIn("`CONTINUING`", context)
        self.assertNotIn("Чернигов/область · `NEW`", context)

    def test_single_source_support_signal_stays_out_of_primary(self) -> None:
        support = row(
            "aid",
            "Ministry of Defence of Ukraine",
            "official-ua",
            "ukrainian",
            "Україна отримала новий пакет військової допомоги від Німеччини.",
        )
        context = render_summary_context("2026-08-05", [support], {})
        self.assertIn("Accepted публикаций после strict gate: **1**", context)
        self.assertNotIn("#### 1.", context)

    def test_credentialed_original_url_is_not_rendered(self) -> None:
        strike = row(
            "unsafe-url",
            "Reuters",
            "international-media",
            "mixed",
            "Russian drone strike in Odesa Ukraine damaged infrastructure.",
            platform="rss",
            trust="high",
            url="https://user:password@example.com/story",
        )
        context = render_summary_context("2026-08-05", [strike], {})
        self.assertIn("оригинал недоступен", context)
        self.assertNotIn("user:password", context)

    def test_casualty_only_topic_does_not_claim_all_losses_are_civilian(self) -> None:
        casualty = row(
            "casualty",
            "Reuters",
            "international-media",
            "mixed",
            "A Ukrainian soldier was killed near Pokrovsk Ukraine during fighting.",
            platform="rss",
            trust="high",
        )
        context = render_summary_context("2026-08-05", [casualty], {})
        self.assertIn("Потери и гражданские последствия — Покровск", context)
        self.assertNotIn("Гражданские последствия — Покровск", context)


if __name__ == "__main__":
    unittest.main()
