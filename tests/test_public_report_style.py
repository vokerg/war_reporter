from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = REPO_ROOT / "reports"
INTERNAL_ID_RE = re.compile(
    r"\b(?:asm|clm|obs|item|src|task|rpt|geo)_[A-Za-z0-9_]+\b"
)
HASH_RE = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)
BANNED_PROCESS_PHRASES = (
    "frozen record",
    "frozen evidence",
    "frozen input",
    "input contract",
    "approved set",
    "claim-set",
    "record status",
    "editorial status",
    "зафиксированный набор",
    "зафиксированные доказательства",
    "зафиксированном контракте",
    "редакционный статус",
)


class PublicReportStyleTests(unittest.TestCase):
    def report_paths(self) -> list[Path]:
        return sorted(REPORT_ROOT.rglob("*.md"))

    def test_public_reports_do_not_expose_internal_references(self) -> None:
        paths = self.report_paths()
        self.assertTrue(paths, "expected at least one public report")
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(
                INTERNAL_ID_RE.search(text),
                f"{path.relative_to(REPO_ROOT)} exposes an internal record ID",
            )
            self.assertIsNone(
                HASH_RE.search(text),
                f"{path.relative_to(REPO_ROOT)} exposes an internal hash",
            )

    def test_public_reports_avoid_repository_process_language(self) -> None:
        for path in self.report_paths():
            lower = path.read_text(encoding="utf-8").lower()
            for phrase in BANNED_PROCESS_PHRASES:
                self.assertNotIn(
                    phrase,
                    lower,
                    f"{path.relative_to(REPO_ROOT)} contains internal process language",
                )

    def test_independence_disclaimer_is_not_repeated_throughout_report(self) -> None:
        for path in self.report_paths():
            lower = path.read_text(encoding="utf-8").lower()
            count = len(re.findall(r"\bindependent(?:ly)?\b", lower))
            count += len(re.findall(r"независим\w*", lower))
            self.assertLessEqual(
                count,
                3,
                f"{path.relative_to(REPO_ROOT)} repeats independence caveats {count} times",
            )


if __name__ == "__main__":
    unittest.main()
