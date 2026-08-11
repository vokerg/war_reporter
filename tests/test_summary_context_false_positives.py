from __future__ import annotations

import unittest

from scripts.summary_context_render import render_summary_context


def row(item_id: str, text: str, *, source: str = "Russian Ministry of Foreign Affairs") -> dict:
    return {
        "id": item_id,
        "source": item_id,
        "source_name": source,
        "group": "official-ru",
        "perspective": "russian",
        "platform": "telegram",
        "trust": "primary",
        "published_at": "2026-08-05T12:00:00Z",
        "collected_at": "2026-08-05T12:01:00Z",
        "title": "",
        "text": text,
        "url": f"https://example.com/{item_id}",
        "tags": [],
        "raw": {"archive_policy": "public_excerpt_v1"},
    }


class SummaryContextFalsePositiveTests(unittest.TestCase):
    def test_gosudarstvennoy_does_not_become_strike(self) -> None:
        election = row(
            "election",
            "Выборы депутатов Государственной Думы Российской Федерации состоятся в сентябре.",
        )
        context = render_summary_context("2026-08-05", [election], {})
        self.assertIn("Accepted публикаций после strict gate: **0**", context)
        self.assertNotIn("#### 1.", context)

    def test_transport_does_not_become_port_event(self) -> None:
        transport = row(
            "transport",
            "Россия и Бразилия обсудили перспективы транспортного сотрудничества и логистики.",
        )
        context = render_summary_context("2026-08-05", [transport], {})
        self.assertIn("Accepted публикаций после strict gate: **0**", context)
        self.assertNotIn("портовая инфраструктура", context)

    def test_historical_war_dead_do_not_become_current_civilian_harm(self) -> None:
        memorial = row(
            "memorial",
            "Посольство почтило российских воинов, погибших в Первой мировой войне, у мемориала в Вене.",
        )
        context = render_summary_context("2026-08-05", [memorial], {})
        self.assertIn("Accepted публикаций после strict gate: **0**", context)
        self.assertNotIn("#### 1.", context)

    def test_current_ukraine_strike_passes_gate_but_unlocated_single_source_is_not_primary(self) -> None:
        strike = row(
            "strike",
            "Минобороны России заявило об ударе беспилотниками по объектам на Украине.",
            source="Russian Ministry of Defence",
        )
        context = render_summary_context("2026-08-05", [strike], {})
        self.assertIn("Accepted публикаций после strict gate: **1**", context)
        self.assertIn("Situation clusters: **1**", context)
        self.assertNotIn("#### 1.", context)


if __name__ == "__main__":
    unittest.main()
