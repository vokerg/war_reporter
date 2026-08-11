from __future__ import annotations

import unittest

from scripts.summary_context_render import render_summary_context


def item(
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
        "published_at": f"2026-08-05T02:{minute:02d}:00Z",
        "collected_at": f"2026-08-05T02:{minute:02d}:30Z",
        "title": "",
        "text": text,
        "url": f"https://example.com/{item_id}",
        "tags": [],
        "raw": {"archive_policy": "public_excerpt_v1"},
    }


class SummaryContextRankingTests(unittest.TestCase):
    def test_routine_air_alert_does_not_outrank_material_multisource_event(self) -> None:
        rows = [
            item(
                "alert-1",
                "Air Force of Ukraine",
                "official-ua",
                "ukrainian",
                "Реактивний БпЛА в напрямку Києва, курс західний. Не ігноруйте тривогу!",
                trust="primary",
            ),
            item(
                "alert-2",
                "Air Force of Ukraine",
                "official-ua",
                "ukrainian",
                "Загроза БпЛА в бік Києва, залишайтеся в укриттях.",
                trust="primary",
                minute=1,
            ),
            item(
                "impact-ua",
                "Kyiv City Military Administration",
                "official-ua",
                "ukrainian",
                "Після масованої ракетно-дронової атаки у Києві 16 поранених, пошкоджено будинки.",
                trust="primary",
                minute=2,
            ),
            item(
                "impact-media",
                "Reuters",
                "international-media",
                "mixed",
                "Russian missile and drone attack damaged homes in Kyiv and wounded 16 people.",
                platform="rss",
                trust="high",
                minute=3,
            ),
            item(
                "impact-ru",
                "Rybar",
                "ru-milbloggers",
                "russian",
                "Массированный удар ракетами и БПЛА по Киеву.",
                minute=4,
            ),
        ]

        context = render_summary_context("2026-08-05", rows, {}, max_primary=4)
        primary = context.split("### Telegram pulse watchlist", 1)[0]

        self.assertIn("Киев/область", primary)
        self.assertIn("Reuters", primary)
        self.assertNotIn("#### 1. Дальние и воздушные удары — без устойчивой геопривязки", primary)

    def test_ukrainian_kyiv_inflections_are_coalesced_for_editorial_context(self) -> None:
        rows = [
            item(
                "kyiv-1",
                "Air Force of Ukraine",
                "official-ua",
                "ukrainian",
                "Балістичні ракети в бік Києва.",
                trust="primary",
            ),
            item(
                "kyiv-2",
                "Kyiv City Military Administration",
                "official-ua",
                "ukrainian",
                "У Києві після атаки пошкоджено складські споруди.",
                trust="primary",
                minute=1,
            ),
            item(
                "kyiv-3",
                "Kyiv Oblast Administration",
                "official-ua",
                "ukrainian",
                "На Київщині зафіксовано наслідки атаки БпЛА.",
                trust="primary",
                minute=2,
            ),
        ]

        context = render_summary_context("2026-08-05", rows, {}, max_primary=5)

        self.assertIn("Киев/область", context)
        self.assertIn("Публикаций в cluster: **3**", context)
        self.assertIn("Кандидатных event clusters после coalescing: **1**", context)

    def test_primary_list_limits_single_topic_domination(self) -> None:
        rows = []
        for index, location in enumerate(
            ["Києві", "Одесі", "Харкові", "Херсоні", "Сумах", "Запоріжжі"]
        ):
            rows.extend(
                [
                    item(
                        f"strike-{index}-a",
                        f"Official {index}",
                        "official-ua",
                        "ukrainian",
                        f"Після атаки БпЛА у {location} пошкоджено інфраструктуру.",
                        trust="primary",
                        minute=index,
                    ),
                    item(
                        f"strike-{index}-b",
                        f"Media {index}",
                        "international-media",
                        "mixed",
                        f"Drone strike in Ukraine caused damage; report concerns {location}.",
                        platform="rss",
                        trust="high",
                        minute=index + 10,
                    ),
                ]
            )
        rows.extend(
            [
                item(
                    "front-1",
                    "DeepState",
                    "osint",
                    "ukrainian",
                    "OSINT reports Russian frontline advance near Pokrovsk Ukraine.",
                    platform="x",
                    trust="high",
                    minute=20,
                ),
                item(
                    "front-2",
                    "Rybar",
                    "ru-milbloggers",
                    "russian",
                    "Продвижение на фронте в районе Покровска на Украине.",
                    minute=21,
                ),
            ]
        )

        context = render_summary_context("2026-08-05", rows, {}, max_primary=8)
        primary = context.split("### Telegram pulse watchlist", 1)[0]

        self.assertIn("Фронт — Покровск", primary)
        self.assertLessEqual(primary.count("####") , 8)
        self.assertLessEqual(primary.count("Дальние и воздушные удары —"), 4)


if __name__ == "__main__":
    unittest.main()
