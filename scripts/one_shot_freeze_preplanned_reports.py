from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "scripts/reconcile_repository.py",
    '''    promotable = []\n    for task_id, (_, task) in tasks.items():\n        dependencies = task.get("depends_on_task_ids", [])\n        if task.get("state") == "planned" and dependencies and all(\n            dependency in tasks and tasks[dependency][1].get("state") == "merged"\n            for dependency in dependencies\n        ):\n            promotable.append(task_id)\n    if promotable:\n        duties.append({"kind": "promote_tasks", "task_ids": sorted(promotable)})\n''',
    '''    promotable: list[str] = []\n    report_inputs_by_task: dict[str, dict[str, Any]] = {}\n    for task_id, (_, task) in tasks.items():\n        dependencies = task.get("depends_on_task_ids", [])\n        if not (\n            task.get("state") == "planned"\n            and dependencies\n            and all(\n                dependency in tasks and tasks[dependency][1].get("state") == "merged"\n                for dependency in dependencies\n            )\n        ):\n            continue\n        if task.get("task_type") == "daily_report":\n            report_inputs = task.get("report_inputs")\n            if not isinstance(report_inputs, dict):\n                window = task.get("window")\n                lower = window.get("from") if isinstance(window, dict) else None\n                upper = window.get("to") if isinstance(window, dict) else None\n                if not isinstance(lower, str) or not isinstance(upper, str):\n                    blockers.append(f"daily report task {task_id} remains planned: invalid frozen UTC window")\n                    continue\n                report_inputs = frozen_report_inputs(root, parse(lower), parse(upper))\n            if report_inputs is None:\n                blockers.append(\n                    f"daily report task {task_id} remains planned: no approved claims or assessments "\n                    "overlap the frozen UTC window"\n                )\n                continue\n            report_inputs_by_task[task_id] = report_inputs\n        promotable.append(task_id)\n    if promotable:\n        promotion_duty: dict[str, Any] = {\n            "kind": "promote_tasks",\n            "task_ids": sorted(promotable),\n        }\n        if report_inputs_by_task:\n            promotion_duty["report_inputs_by_task"] = {\n                task_id: report_inputs_by_task[task_id]\n                for task_id in sorted(report_inputs_by_task)\n            }\n        duties.append(promotion_duty)\n''',
)

replace_once(
    "scripts/reconcile_repository.py",
    '''        if kind == "promote_tasks":\n            for task_id in duty["task_ids"]:\n                path, task = tasks[task_id]\n                task["state"] = "ready"\n                task["lease"] = None\n                dump(path, task)\n                promoted.append(task_id)\n''',
    '''        if kind == "promote_tasks":\n            report_inputs_by_task = duty.get("report_inputs_by_task", {})\n            for task_id in duty["task_ids"]:\n                path, task = tasks[task_id]\n                if task.get("task_type") == "daily_report":\n                    report_inputs = task.get("report_inputs")\n                    if not isinstance(report_inputs, dict):\n                        report_inputs = (\n                            report_inputs_by_task.get(task_id)\n                            if isinstance(report_inputs_by_task, dict)\n                            else None\n                        )\n                    if not isinstance(report_inputs, dict):\n                        raise ValueError(\n                            f"daily_report task {task_id} cannot be promoted without approved frozen report inputs"\n                        )\n                    task["report_inputs"] = report_inputs\n                task["state"] = "ready"\n                task["lease"] = None\n                dump(path, task)\n                promoted.append(task_id)\n''',
)

report_test = Path("tests/test_reconcile_report_inputs.py")
report_text = report_test.read_text(encoding="utf-8")
anchor = '''    def test_hash_is_deterministic_across_file_order(self) -> None:\n'''
addition = '''    def planned_report(self, root: Path) -> Path:\n        dependency_id = "task_backfill_claims"\n        dump(\n            root / "tasks/2026/08/05/task_backfill_claims.json",\n            {\n                "task_id": dependency_id,\n                "task_type": "investigate_claim",\n                "state": "merged",\n                "depends_on_task_ids": [],\n                "window": {"from": "2026-08-05T00:00:00Z", "to": "2026-08-06T00:00:00Z"},\n                "idempotency_key": "backfill_claims:2026-08-05",\n            },\n        )\n        path = root / "tasks/2026/08/05/task_backfill_report.json"\n        dump(\n            path,\n            {\n                "task_id": "task_backfill_report",\n                "task_type": "daily_report",\n                "state": "planned",\n                "depends_on_task_ids": [dependency_id],\n                "window": {"from": "2026-08-05T00:00:00Z", "to": "2026-08-06T00:00:00Z"},\n                "idempotency_key": reconcile.daily_report_key(self.day, "ukraine-war"),\n                "lease": None,\n            },\n        )\n        return path\n\n    def test_planned_report_waits_until_approved_inputs_exist(self) -> None:\n        root = self.make_root()\n        report_path = self.planned_report(root)\n\n        plan = reconcile.plan_duties(root, self.now)\n        promoted = [\n            task_id\n            for duty in plan["duties"]\n            if duty["kind"] == "promote_tasks"\n            for task_id in duty["task_ids"]\n        ]\n        self.assertNotIn("task_backfill_report", promoted)\n        self.assertTrue(any("task_backfill_report remains planned" in value for value in plan["blockers"]))\n        self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["state"], "planned")\n\n    def test_planned_report_freezes_inputs_during_promotion(self) -> None:\n        root = self.make_root()\n        report_path = self.planned_report(root)\n        dump(root / "data/claims/2026/08/05/claim.json", self.approved_claim())\n\n        plan = reconcile.plan_duties(root, self.now)\n        promotion = next(\n            duty\n            for duty in plan["duties"]\n            if duty["kind"] == "promote_tasks" and "task_backfill_report" in duty["task_ids"]\n        )\n        frozen = promotion["report_inputs_by_task"]["task_backfill_report"]\n        self.assertEqual(frozen["claim_ids"], ["clm_reportable"])\n\n        result = reconcile.apply_plan(root, plan)\n        self.assertIn("task_backfill_report", result["promoted_task_ids"])\n        task = json.loads(report_path.read_text(encoding="utf-8"))\n        self.assertEqual(task["state"], "ready")\n        self.assertEqual(task["report_inputs"], frozen)\n\n'''
if report_text.count(anchor) != 1:
    raise SystemExit("report input test anchor not found exactly once")
report_test.write_text(report_text.replace(anchor, addition + anchor, 1), encoding="utf-8")

hardening = Path("tests/test_hardening.py")
hardening_text = hardening.read_text(encoding="utf-8")
hardening_anchor = '''    def test_bootstrap_requires_all_backpressure_conditions(self) -> None:\n'''
hardening_addition = '''    def test_daily_report_inputs_are_required_before_execution_not_while_planned(self) -> None:\n        schema = json.loads((ROOT / "schemas/task-manifest.schema.json").read_text())\n        validator = Draft202012Validator(schema, format_checker=FormatChecker())\n        task = {\n            "task_id": "task_report",\n            "task_type": "daily_report",\n            "state": "planned",\n            "window": {"from": "2026-08-05T00:00:00Z", "to": "2026-08-06T00:00:00Z"},\n            "scope": {"source_ids": [], "source_groups": [], "regions": [], "topics": [], "content_types": []},\n            "exclusions": [],\n            "allowed_output_paths": ["reports/daily/example.md"],\n            "definition_of_done": ["done"],\n            "idempotency_key": "daily_report:planned:test",\n            "lease": None,\n        }\n        self.assertEqual(list(validator.iter_errors(task)), [])\n        task["state"] = "ready"\n        self.assertTrue(any("report_inputs" in error.message for error in validator.iter_errors(task)))\n\n'''
if hardening_text.count(hardening_anchor) != 1:
    raise SystemExit("hardening test anchor not found exactly once")
hardening.write_text(
    hardening_text.replace(hardening_anchor, hardening_addition + hardening_anchor, 1),
    encoding="utf-8",
)

replace_once(
    "docs/architecture/11-continuous-loop.md",
    '7. the supervisor has refreshed `main`.\n',
    '7. the supervisor has refreshed `main`.\n\nA pre-materialized `planned` daily report may omit `report_inputs` while its dependencies are unfinished. Reconciliation must freeze an approved claim/assessment set and persist its deterministic hash in the task before promotion to `ready`; without such inputs the task remains planned.\n',
)

Path(".github/workflows/one-shot-freeze-preplanned-reports.yml").unlink()
Path("scripts/one_shot_freeze_preplanned_reports.py").unlink()
