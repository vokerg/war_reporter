from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ContainerContractTests(unittest.TestCase):
    def test_docker_context_excludes_secrets_and_runtime_data(self) -> None:
        entries = {
            line.strip()
            for line in (ROOT / ".dockerignore").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        for required in {".env", ".env.*", ".git", "data", "reports", "site"}:
            self.assertIn(required, entries)

    def test_image_runs_as_non_root(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn("USER warreporter", dockerfile)
        self.assertIn("COPY --chown=warreporter:warreporter . .", dockerfile)
        self.assertNotIn("COPY . .", dockerfile)

    def test_compose_restricts_runtime_privileges(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text()
        for required in (
            "read_only: true",
            "no-new-privileges:true",
            "cap_drop:",
            "- ALL",
            'user: "${WAR_REPORTER_UID:-1000}:${WAR_REPORTER_GID:-1000}"',
            "tmpfs:",
        ):
            self.assertIn(required, compose)


if __name__ == "__main__":
    unittest.main()
