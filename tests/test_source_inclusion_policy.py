from __future__ import annotations

import unittest

from scripts.build_report import render_item
from scripts.collect import item_storage_delay_hours
from scripts.common import ROOT, load_json


class SourceInclusionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = load_json(ROOT / "config/settings.json")
        registry = load_json(ROOT / "config/sources.json")
        assert isinstance(settings, dict)
        assert isinstance(registry, dict)
        self.settings = settings
        self.sources = {
            source["id"]: source
            for source in registry.get("sources", [])
            if isinstance(source, dict) and source.get("id")
        }

    def test_production_config_has_no_group_tag_or_source_collection_delays(self) -> None:
        self.assertEqual(self.settings.get("collection_delay_hours", 0), 0)
        self.assertFalse(self.settings.get("collection_delay_by_group"))
        self.assertFalse(self.settings.get("collection_delay_by_tag"))
        self.assertFalse(self.settings.get("collection_delay_by_source"))

    def test_representative_sources_from_both_sides_are_immediately_storable(self) -> None:
        for source_id in (
            "rybar-tg",
            "wargonzo-tg",
            "butusov-tg",
            "sternenko-tg",
            "ru-mod-tg",
            "ua-general-staff-tg",
            "deepstate-tg",
        ):
            source = self.sources[source_id]
            item = {
                "source": source_id,
                "group": source.get("group", ""),
                "tags": source.get("tags", []),
            }
            with self.subTest(source_id=source_id):
                self.assertEqual(
                    item_storage_delay_hours(item, self.settings),
                    0,
                )

    def test_low_trust_is_report_metadata_not_an_exclusion_rule(self) -> None:
        source = self.sources["rybar-tg"]
        item = {
            "id": "example",
            "source": source["id"],
            "source_name": source["name"],
            "platform": source["platform"],
            "url": "https://t.me/rybar/1",
            "published_at": "2026-08-06T12:00:00Z",
            "collected_at": "2026-08-06T12:01:00Z",
            "title": "",
            "text": "Example source claim",
            "html": "",
            "media": [],
            "author": "",
            "language": "ru",
            "group": source["group"],
            "perspective": source["perspective"],
            "trust": source["trust"],
            "tags": [],
            "raw": {},
        }
        rendered = render_item(item, self.settings)
        self.assertIn("**Rybar**", rendered)
        self.assertIn("trust `low`", rendered)
        self.assertIn("Example source claim", rendered)

    def test_precise_operational_details_remain_redacted(self) -> None:
        self.assertIn(
            "operational-position",
            self.settings.get("public_redact_tags", []),
        )
        self.assertIn(
            "precise-location",
            self.settings.get("public_redact_tags", []),
        )


if __name__ == "__main__":
    unittest.main()
