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
    trust: str = "low",
    platform: str = "telegram",
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


class SummaryContextEditorialGuardTests(unittest.TestCase):
    def test_biographical_old_death_is_not_current_donetsk_casualty(self) -> None:
        memorial = row(
            "bio",
            "Donetsk Oblast Administration",
            "official-ua",
            "ukrainian",
            "Старший солдат Олександр поліг 14 травня 2022 року в Маріуполі. Захиснику назавжди 35 років. Олександр народився у Маріуполі та навчався у коледжі.",
            trust="primary",
        )
        context = render_summary_context("2026-08-05", [memorial], {})
        self.assertIn("Accepted публикаций после strict gate: **0**", context)
        self.assertNotIn("#### 1.", context)

    def test_unlocated_casualty_stories_do_not_merge_across_source_families(self) -> None:
        rows = [
            row(
                "a",
                "Outlet A",
                "international-media",
                "mixed",
                "A Russian military executive was wounded in an attack connected to the war in Ukraine.",
                trust="high",
                platform="rss",
            ),
            row(
                "b",
                "Outlet B",
                "international-media",
                "mixed",
                "A Ukrainian volunteer was killed while supporting work related to the war in Ukraine.",
                trust="high",
                platform="rss",
                minute=1,
            ),
        ]
        context = render_summary_context("2026-08-05", rows, {})
        self.assertIn("Situation clusters: **2**", context)
        self.assertNotIn("#### 1.", context)

    def test_thin_single_camp_frontline_claim_stays_out_of_primary(self) -> None:
        rows = [
            row(
                "a",
                "Milblogger A",
                "ru-milbloggers",
                "russian",
                "Продвижение на фронте в районе Константиновки на Украине.",
            ),
            row(
                "b",
                "Milblogger B",
                "ru-milbloggers",
                "russian",
                "Российские подразделения заявляют продвижение у Константиновки на Украине.",
                minute=1,
            ),
        ]
        context = render_summary_context("2026-08-05", rows, {})
        primary = context.split("### Telegram pulse watchlist", 1)[0]
        self.assertNotIn("Фронт — Константиновка", primary)

    def test_osint_plus_claim_can_enter_frontline_primary(self) -> None:
        rows = [
            row(
                "osint",
                "GeoConfirmed",
                "osint",
                "mixed",
                "OSINT reports a frontline advance near Pokrovsk Ukraine.",
                trust="high",
                platform="x",
            ),
            row(
                "claim",
                "Milblogger",
                "ru-milbloggers",
                "russian",
                "Продвижение на фронте в районе Покровска на Украине.",
                minute=1,
            ),
        ]
        context = render_summary_context("2026-08-05", rows, {})
        primary = context.split("### Telegram pulse watchlist", 1)[0]
        self.assertIn("Фронт — Покровск", primary)


if __name__ == "__main__":
    unittest.main()
