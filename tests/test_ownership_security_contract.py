from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OwnershipSecurityContractTests(unittest.TestCase):
    def test_critical_boundaries_have_code_owner(self) -> None:
        text = (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")
        for path in (
            "/.github/workflows/",
            "/scripts/collector_runtime.py",
            "/scripts/publisher_fetch.py",
            "/scripts/sensitivity.py",
            "/scripts/public_archive.py",
            "/scripts/validate.py",
            "/schemas/",
            "/SAFETY.md",
            "/OPERATIONS.md",
        ):
            self.assertIn(f"{path} @vokerg", text)

    def test_security_policy_avoids_public_sensitive_reports(self) -> None:
        text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("Do not open a public issue", text)
        self.assertIn("private vulnerability reporting", text)
        self.assertIn("rotate/revoke exposed credentials", text)
        self.assertIn("exact-head CI", text)
        self.assertIn("Actions artifacts", text)


if __name__ == "__main__":
    unittest.main()
