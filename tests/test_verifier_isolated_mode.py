from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VerifierIsolatedModeTests(unittest.TestCase):
    def test_verifier_starts_under_python_isolated_mode(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(ROOT / "scripts/verify_collection_artifact.py"),
                "--help",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--manifest", result.stdout)


if __name__ == "__main__":
    unittest.main()
