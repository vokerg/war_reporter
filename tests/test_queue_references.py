from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from reconcile_repository import task_from_proposal
from validate_queue_references import validate_repository


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class QueueReferenceTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        dump(root / "catalogs/sources/source.json", {"source_entity_id": "src_example"})
        (root / "data/source-items").mkdir(parents=True)
        (root / "data/source-items/items.ndjson").write_text(
            json.dumps({"source_item_id": "item_example"}) + "\n",
            encoding="utf-8",
        )
        return root

    def test_resolved_task_and_proposal_scope_pass(self) -> None:
        root = self.make_root()
        scope = {
            "source_ids": ["src_example"],
            "source_item_ids": ["item_example"],
            "source_groups": [],
            "regions": ["example"],
            "topics": ["example"],
            "content_types": ["article"],
        }
        dump(root / "tasks/task_example.json", {"scope": scope})
        dump(root / "queue/proposals/task_example.json", {"proposals": [{"scope": scope}]})
        self.assertEqual(validate_repository(root), [])

    def test_unresolved_references_fail_before_materialization(self) -> None:
        root = self.make_root()
        dump(root / "queue/proposals/task_example.json", {
            "proposals": [{
                "scope": {
                    "source_ids": ["src_missing"],
                    "source_item_ids": ["item_missing"],
                }
            }]
        })
        errors = validate_repository(root)
        self.assertTrue(any("unresolved reference src_missing" in error for error in errors))
        self.assertTrue(any("unresolved reference item_missing" in error for error in errors))

    def test_proposal_and_task_schemas_share_exact_item_scope(self) -> None:
        scope = {
            "source_ids": [],
            "source_item_ids": ["item_example"],
            "source_groups": [],
            "regions": ["example"],
            "topics": ["example"],
            "content_types": ["article"],
        }
        task_schema = json.loads((REPO_ROOT / "schemas/task-manifest.schema.json").read_text(encoding="utf-8"))
        proposal_schema = json.loads((REPO_ROOT / "schemas/task-proposal.schema.json").read_text(encoding="utf-8"))
        task_scope_schema = task_schema["properties"]["scope"]
        proposal_scope_schema = proposal_schema["properties"]["proposals"]["items"]["properties"]["scope"]
        self.assertEqual(list(Draft202012Validator(task_scope_schema).iter_errors(scope)), [])
        self.assertEqual(list(Draft202012Validator(proposal_scope_schema).iter_errors(scope)), [])

        widened = dict(scope)
        widened["unsupported"] = []
        self.assertTrue(list(Draft202012Validator(proposal_scope_schema).iter_errors(widened)))

    def test_materialization_preserves_exact_source_item_scope(self) -> None:
        root = self.make_root()
        producer = {
            "task_id": "task_producer",
            "state": "merged",
            "parent_issue": 33,
        }
        tasks = {
            "task_producer": (root / "tasks/task_producer.json", producer),
        }
        duty = {
            "producer_task_id": "task_producer",
            "proposal": {
                "task_type": "extract_observations",
                "priority": 60,
                "depends_on_task_ids": ["task_producer"],
                "window": {
                    "from": "2026-08-04T18:00:00Z",
                    "to": "2026-08-05T05:00:00Z",
                },
                "scope": {
                    "source_ids": ["src_example"],
                    "source_item_ids": ["item_example"],
                    "source_groups": [],
                    "regions": ["example"],
                    "topics": ["example"],
                    "content_types": ["article"],
                },
                "exclusions": ["No scope broadening"],
                "allowed_output_paths": ["data/observations/example.ndjson"],
                "definition_of_done": ["Exact source-item scope is preserved"],
                "idempotency_key": "extract_observations:example",
            },
        }

        _, task = task_from_proposal(
            root,
            duty,
            "2026-08-05T12:00:00Z",
            tasks,
        )

        self.assertEqual(task["scope"]["source_item_ids"], ["item_example"])
        self.assertEqual(validate_repository(root), [])


if __name__ == "__main__":
    unittest.main()
