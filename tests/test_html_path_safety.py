from __future__ import annotations

import unittest

from scripts.html_safety import _safe_href, sanitize_report_html


class HtmlPathSafetyTests(unittest.TestCase):
    def test_safe_relative_and_external_links_remain(self) -> None:
        self.assertEqual(
            _safe_href("reports/2026-08-05.html"),
            "reports/2026-08-05.html",
        )
        self.assertEqual(
            _safe_href("https://example.com/report"),
            "https://example.com/report",
        )

    def test_encoded_traversal_and_active_paths_are_rejected(self) -> None:
        unsafe = (
            "../secret",
            "%2e%2e/secret",
            "%252e%252e/secret",
            "%252f%252fevil.example/path",
            "%255csecret",
            "%250asecret",
            "%256aavascript%253Aalert(1)",
        )
        for href in unsafe:
            with self.subTest(href=href):
                self.assertIsNone(_safe_href(href))

    def test_excessive_percent_encoding_fails_closed(self) -> None:
        nested = "%25" * 6 + "2e%25" * 6 + "2e/secret"
        self.assertIsNone(_safe_href(nested))

    def test_sanitizer_removes_unsafe_href_but_keeps_text(self) -> None:
        rendered = sanitize_report_html(
            '<a href="%252e%252e/secret">read this label</a>'
        )
        self.assertIn("read this label", rendered)
        self.assertNotIn("href=", rendered)
        self.assertNotIn("secret", rendered)


if __name__ == "__main__":
    unittest.main()
