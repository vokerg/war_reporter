from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SourceLifecycleContractTests(unittest.TestCase):
    def test_disabled_tombstones_are_the_default_removal_path(self) -> None:
        text = (ROOT / "SOURCE_LIFECYCLE.md").read_text(encoding="utf-8")
        self.assertIn('"enabled": false', text)
        self.assertIn("Historical archive/error rows retain the source ID", text)
        self.assertIn("preserve a disabled registry tombstone", text)
        self.assertIn("does not alter historical archive or error records", text)

    def test_replacement_identity_gets_a_new_id(self) -> None:
        text = (ROOT / "SOURCE_LIFECYCLE.md").read_text(encoding="utf-8")
        self.assertIn("Create a new source ID", text)
        self.assertIn("platform changes", text)
        self.assertIn("publisher/account ownership changes", text)
        self.assertIn("Disable the old row and add the new row", text)


if __name__ == "__main__":
    unittest.main()
