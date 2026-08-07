from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OperationsContractTests(unittest.TestCase):
    def test_incident_runbook_covers_required_boundaries(self) -> None:
        text = (ROOT / "OPERATIONS.md").read_text(encoding="utf-8")
        for required in (
            "disable scheduled collection",
            "X_BEARER_TOKEN",
            "repository-history purge",
            "exact-head hosted CI",
            "targeted source smoke",
            "A normal delete/revert does not erase earlier Git objects",
        ):
            self.assertIn(required, text)

    def test_dependabot_is_pr_only_and_covers_three_ecosystems(self) -> None:
        text = (ROOT / ".github/dependabot.yml").read_text(
            encoding="utf-8"
        )
        for ecosystem in ("pip", "github-actions", "docker"):
            self.assertIn(f"package-ecosystem: {ecosystem}", text)
        self.assertNotIn("auto-merge", text.lower())
        self.assertEqual(text.count("interval: weekly"), 3)


if __name__ == "__main__":
    unittest.main()
