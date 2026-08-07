from __future__ import annotations

import unittest

from scripts.public_archive import harden_public_projection


class PublicMediaSafetyTests(unittest.TestCase):
    def test_final_archive_boundary_drops_unsafe_media_urls(self) -> None:
        projected = {
            "media": [
                "https://example.com/image.jpg",
                "http://cdn.example.com/a.png",
                "/relative.jpg",
                "//example.com/protocol-relative.jpg",
                "javascript:alert(1)",
                "https://user:pass@example.com/private.jpg",
                "https://example.com/\ncontrol.jpg",
                "https://example.com/image.jpg",
            ]
        }
        item = {"tags": [], "platform": "web"}

        result = harden_public_projection(
            projected,
            item,
            {"public_redact_tags": ["precise-location"]},
        )

        self.assertEqual(
            result["media"],
            [
                "https://example.com/image.jpg",
                "http://cdn.example.com/a.png",
            ],
        )

    def test_redacted_projection_still_removes_all_media(self) -> None:
        projected = {
            "id": "old",
            "url": "https://example.com/story",
            "title": "title",
            "text": "text",
            "html": "",
            "media": ["https://example.com/image.jpg"],
            "author": "author",
            "raw": {
                "archive_policy": "public_excerpt_v1",
                "platform": {"content_type": "text/html"},
            },
        }
        item = {
            "source": "source-web",
            "platform": "web",
            "url": "https://example.com/story",
            "published_at": "2026-08-06T00:00:00Z",
            "tags": ["precise-location"],
        }

        result = harden_public_projection(
            projected,
            item,
            {"public_redact_tags": ["precise-location"]},
        )

        self.assertEqual(result["media"], [])
        self.assertEqual(result["raw"]["archive_policy"], "public_redacted_v1")


if __name__ == "__main__":
    unittest.main()
