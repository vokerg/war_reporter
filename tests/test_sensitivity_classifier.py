from __future__ import annotations

import unittest
from datetime import UTC, datetime

from scripts.collector_runtime import archive_projection, item_storage_state
from scripts.sensitivity import classify_item, detected_sensitive_tags


class SensitivityClassifierTests(unittest.TestCase):
    def item(self, text: str, *, platform: str = "web") -> dict:
        return {
            "id": "content-derived-id",
            "source": "source-web",
            "source_name": "Source",
            "platform": platform,
            "url": "https://news.example.com/story?tracking=1",
            "published_at": "2026-08-05T12:00:00Z",
            "collected_at": "2026-08-06T12:00:00Z",
            "title": "Operational update",
            "text": text,
            "html": f"<p>{text}</p>",
            "media": ["https://cdn.example.com/image.jpg"],
            "author": "Reporter",
            "language": "en",
            "group": "media",
            "perspective": "mixed",
            "trust": "high",
            "tags": [],
            "raw": {"content_type": "web_article"},
        }

    def settings(self) -> dict:
        return {
            "collection_delay_hours": 0,
            "collection_delay_by_group": {},
            "collection_delay_by_tag": {
                "precise-location": 72,
                "operational-position": 72,
            },
            "collection_delay_by_source": {},
            "public_excerpt_chars": 1200,
            "public_media_limit": 8,
            "public_redact_tags": [
                "precise-location",
                "operational-position",
            ],
        }

    def test_decimal_coordinate_pair_is_detected(self) -> None:
        tags = detected_sensitive_tags(
            self.item("Unit position coordinates 50.4501, 30.5234")
        )
        self.assertEqual(
            tags, {"precise-location", "operational-position"}
        )

    def test_dms_and_mgrs_are_detected(self) -> None:
        dms = self.item("Position 50° 27' 00\" N 30° 31' 00\" E")
        mgrs = self.item("Battery grid 36U UV 12345 67890")
        self.assertIn("precise-location", detected_sensitive_tags(dms))
        self.assertIn("precise-location", detected_sensitive_tags(mgrs))

    def test_ordinary_numbers_are_not_detected(self) -> None:
        item = self.item(
            "The report lists 12 units, 45 vehicles and 3.5 percent growth."
        )
        self.assertEqual(detected_sensitive_tags(item), set())
        self.assertEqual(classify_item(item)["tags"], [])

    def test_detected_location_receives_embargo_before_storage(self) -> None:
        item = self.item("Coordinates 50.4501, 30.5234")
        state = item_storage_state(
            item,
            self.settings(),
            datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
        )
        self.assertEqual(state, "withheld_recent")

    def test_old_detected_location_uses_content_neutral_projection(self) -> None:
        item = self.item("Coordinates 50.4501, 30.5234")
        projected = archive_projection(item, self.settings())
        self.assertEqual(projected["title"], "")
        self.assertEqual(projected["text"], "")
        self.assertEqual(projected["html"], "")
        self.assertEqual(projected["media"], [])
        self.assertEqual(projected["author"], "")
        self.assertEqual(projected["url"], "https://news.example.com/")
        self.assertNotEqual(projected["id"], item["id"])
        self.assertEqual(
            projected["raw"]["archive_policy"], "public_redacted_v1"
        )
        self.assertNotIn("content_sha256", projected["raw"])
        self.assertIn("precise-location", projected["tags"])

    def test_redacted_id_does_not_depend_on_hidden_text(self) -> None:
        one = archive_projection(
            self.item("Coordinates 50.4501, 30.5234"), self.settings()
        )
        two = archive_projection(
            self.item("Different secret coordinates 51.0001, 31.0001"),
            self.settings(),
        )
        self.assertEqual(one["id"], two["id"])

    def test_telegram_redaction_keeps_only_opaque_post_path(self) -> None:
        item = self.item(
            "Coordinates 50.4501, 30.5234", platform="telegram"
        )
        item["url"] = "https://t.me/channel/123?single=1"
        item["raw"] = {"post": "channel/123"}
        projected = archive_projection(item, self.settings())
        self.assertEqual(projected["url"], "https://t.me/channel/123")
        self.assertEqual(
            projected["raw"]["platform"], {"post": "channel/123"}
        )


if __name__ == "__main__":
    unittest.main()
