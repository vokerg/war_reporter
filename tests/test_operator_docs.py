from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OperatorDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    def test_docs_use_proven_non_x_smoke_sources(self) -> None:
        for text in (self.readme, self.agents):
            self.assertIn(
                "ua-general-staff-tg,bellingcat-rss,cit-web",
                text,
            )
            self.assertNotIn("ua-president-web", text)

    def test_docs_do_not_treat_missing_x_secret_as_success(self) -> None:
        self.assertIn("missing secret is a red configuration blocker", self.readme)
        self.assertIn("missing secret is a red configuration blocker", self.agents)
        self.assertIn("ua-general-staff-x", self.readme)
        self.assertIn("x-discovery-1", self.readme)

    def test_docs_separate_preview_from_deployed_pages_evidence(self) -> None:
        self.assertIn("does **not** prove that GitHub Pages deployed", self.readme)
        self.assertIn("A ZIP site preview proves", self.agents)
        self.assertIn("deployed GitHub Pages service", self.agents)

    def test_agent_contract_rejects_legacy_control_plane(self) -> None:
        self.assertIn("Do not recreate task manifests", self.agents)
        self.assertIn("one supported", self.readme.lower() + self.agents.lower())


if __name__ == "__main__":
    unittest.main()
