from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from scripts.harden_repository import (
    audit_or_delete_work_branches,
    canonicalize_items,
    canonicalize_profiles,
    migrate_publication_intervals,
    rewrite_all_references,
)
from scripts.worker_queue import queue_status, ready_tasks

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def write_ndjson(path: Path, values: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(value) for value in values) + "\n", encoding="utf-8")


class FakeGitHub:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def paged(self, path: str) -> list[dict]:
        if path == "/branches":
            return [
                {"name": "work/task_merged"},
                {"name": "work/task_active"},
                {"name": "work/task_orphan"},
            ]
        if path == "/pulls?state=open":
            return [{"head": {"ref": "work/task_active"}}]
        raise AssertionError(path)

    def delete_branch(self, branch: str) -> None:
        self.deleted.append(branch)


class HardeningTests(unittest.TestCase):
    def test_duplicate_profiles_items_and_raw_references_are_canonicalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "catalogs/sources/a.json", [{
                "source_entity_id": "src_guardian", "display_name": "Guardian", "entity_type": "outlet",
                "languages": ["en"], "websites": ["https://www.theguardian.com/"],
                "record_status": "draft", "assessments": [], "updated_at": "2026-08-05T00:00:00Z"
            }])
            write_json(root / "catalogs/sources/b.json", [{
                "source_entity_id": "src_the_guardian", "display_name": "The Guardian", "entity_type": "outlet",
                "languages": ["en"], "websites": ["https://theguardian.com"],
                "record_status": "draft", "assessments": [], "updated_at": "2026-08-05T01:00:00Z"
            }])
            url = "https://example.com/article"
            base = {
                "source_entity_id": "src_guardian", "canonical_url": url,
                "published_at": "2026-08-04T09:00:00Z", "published_at_precision": "minute",
                "retrieved_at": "2026-08-05T00:00:00Z", "language": "en", "item_type": "article",
                "content_status": "available", "access_method": "public_web"
            }
            write_ndjson(root / "data/source-items/a.ndjson", [dict(base, source_item_id="item_old")])
            write_ndjson(root / "data/source-items/b.ndjson", [dict(base, source_item_id="item_new", source_entity_id="src_the_guardian")])
            write_json(root / "raw-manifests/a.json", {
                "task_id": "task_a", "worker_run_id": "run_a", "retrieved_at": "2026-08-05T00:00:00Z",
                "window": {"from": "2026-08-04T00:00:00Z", "to": "2026-08-05T00:00:00Z"},
                "included_items": [{"source_item_id": "item_old"}]
            })

            source_aliases, _ = canonicalize_profiles(root)
            rewrite_all_references(root, source_aliases)
            item_aliases, groups = canonicalize_items(root)
            rewrite_all_references(root, item_aliases)

            profiles = []
            for path in (root / "catalogs/sources").glob("*.json"):
                profiles.extend(json.loads(path.read_text()))
            self.assertEqual(["src_the_guardian"], [p["source_entity_id"] for p in profiles])
            items = []
            for path in (root / "data/source-items").glob("*.ndjson"):
                items.extend(json.loads(line) for line in path.read_text().splitlines() if line)
            self.assertEqual(1, len(items))
            self.assertEqual("src_the_guardian", items[0]["source_entity_id"])
            self.assertEqual(1, len(groups))
            raw = json.loads((root / "raw-manifests/a.json").read_text())
            self.assertEqual(items[0]["source_item_id"], raw["included_items"][0]["source_item_id"])

    def test_day_precision_migrates_to_publication_interval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_ndjson(root / "data/source-items/day.ndjson", [{
                "source_item_id": "item_day", "source_entity_id": "src_example",
                "canonical_url": "https://example.com/day", "published_at": "2026-08-04T00:00:00Z",
                "published_at_precision": "day", "retrieved_at": "2026-08-05T00:00:00Z",
                "language": "en", "item_type": "article", "content_status": "available", "access_method": "public_web"
            }])
            self.assertEqual(["item_day"], migrate_publication_intervals(root))
            value = json.loads((root / "data/source-items/day.ndjson").read_text())
            self.assertIsNone(value["published_at"])
            self.assertEqual("2026-08-04T00:00:00Z", value["published_not_before"])
            self.assertEqual("2026-08-04T23:59:59Z", value["published_not_after"])

    def test_task_schema_rejects_terminal_lease_and_missing_merge_metadata(self) -> None:
        schema = json.loads((ROOT / "schemas/task-manifest.schema.json").read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        task = {
            "task_id": "task_example", "task_type": "validation", "state": "merged",
            "window": {"from": "2026-08-04T00:00:00Z", "to": "2026-08-04T01:00:00Z"},
            "scope": {"source_ids": [], "source_groups": [], "regions": [], "topics": [], "content_types": []},
            "exclusions": [], "allowed_output_paths": ["data/x.json"], "definition_of_done": ["done"],
            "idempotency_key": "validation:example",
            "lease": {"worker_run_id": "run_x", "lease_branch": "work/task_example", "base_sha": "0" * 40,
                      "leased_at": "2026-08-04T00:00:00Z", "lease_until": "2026-08-04T01:00:00Z"},
            "result": {"branch": "work/task_example", "pr_number": 1}
        }
        errors = list(validator.iter_errors(task))
        self.assertTrue(any("not of type 'null'" in error.message for error in errors))
        self.assertTrue(any("merge_sha" in error.message or "merged_at" in error.message for error in errors))

    def test_bootstrap_requires_all_backpressure_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tasks_root = Path(directory)
            clear = queue_status(tasks_root, open_worker_prs=0, previous_campaign_closed=True, backlog_limit=10)
            self.assertTrue(clear.bootstrap_allowed)
            write_json(tasks_root / "ready.json", {"task_id": "task_ready", "state": "ready"})
            blocked = queue_status(tasks_root, open_worker_prs=0, previous_campaign_closed=True, backlog_limit=10)
            self.assertFalse(blocked.bootstrap_allowed)
            self.assertIn("ready_tasks_nonzero", blocked.blocking_reasons)
            blocked_pr = queue_status(Path(tempfile.mkdtemp()), open_worker_prs=1, previous_campaign_closed=True, backlog_limit=10)
            self.assertIn("open_worker_prs_nonzero", blocked_pr.blocking_reasons)

    def test_downstream_tasks_are_gated_until_canonicalization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tasks_root = Path(directory)
            write_json(tasks_root / "task.json", {
                "task_id": "task_extract", "task_type": "extract_observations", "state": "ready",
                "priority": 50, "depends_on_task_ids": []
            })
            self.assertEqual([], ready_tasks(tasks_root, canonicalization_is_complete=False))
            self.assertEqual(["task_extract"], [task.task_id for task in ready_tasks(tasks_root, canonicalization_is_complete=True)])

    def test_work_ref_audit_detects_orphan_and_terminal_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "tasks/merged.json", {"task_id": "task_merged", "state": "merged"})
            write_json(root / "tasks/active.json", {"task_id": "task_active", "state": "review"})
            github = FakeGitHub()
            result = audit_or_delete_work_branches(root, github, True)
            self.assertEqual(["work/task_merged", "work/task_orphan"], github.deleted)
            self.assertEqual(["work/task_active"], result["retained"])


if __name__ == "__main__":
    unittest.main()
